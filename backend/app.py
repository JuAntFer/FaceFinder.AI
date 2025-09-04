# # backend/app.py

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import StreamingResponse, FileResponse
import cv2, numpy as np, io, tempfile, os, zipfile, shutil, base64
from typing import List

from backend.core.face_recognition import (
    get_face_embeddings,
    compare_faces,
    SIMILARITY_THRESHOLD,
)
from backend.core.utils import read_upload_file_to_bgr, extract_zip_to_temp, generate_job_id
from backend.core.processor import process_images_in_dir

app = FastAPI(
    title="FaceFinder.AI Backend",
    description="Detect selected faces from reference image in target image(s)",
    version="2.3",
)

# --- Step 1: Extract faces from reference image ---
@app.post("/reference-faces/")
async def reference_faces(reference: UploadFile = File(...)):
    try:
        ref_img = read_upload_file_to_bgr(reference)
        if ref_img is None:
            raise ValueError("Cannot decode reference image")

        embeddings = get_face_embeddings(ref_img)
        if not embeddings:
            return {"faces": []}

        faces_info = []
        for idx, (emb, (x1, y1, x2, y2)) in enumerate(embeddings):
            crop = ref_img[y1:y2, x1:x2].copy()
            _, jpg = cv2.imencode(".jpg", crop)
            b64 = base64.b64encode(jpg.tobytes()).decode("utf-8")
            faces_info.append({
                "index": idx,
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "thumbnail_b64": b64
            })

        return {"faces": faces_info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Step 2: Match selected face(s) ---
@app.post("/match-face-selected/")
async def match_face_selected(
    reference: UploadFile = File(...),
    target: UploadFile = File(...),
    selected_indices_str: str = Form(..., description="Comma-separated indices of faces to detect"),
    mode: str = Form("individually", description="Detection mode: 'individually' or 'together'")
):
    """
    Match selected face(s) from reference image against single or multiple target images.
    """
    try:
        # Parse indices
        try:
            selected_indices = [int(x.strip()) for x in selected_indices_str.split(",") if x.strip() != ""]
        except:
            raise HTTPException(status_code=400, detail="selected_indices must be comma-separated integers")

        ref_img = read_upload_file_to_bgr(reference)
        if ref_img is None:
            raise ValueError("Cannot decode reference image")

        embeddings = get_face_embeddings(ref_img)
        if not embeddings:
            raise HTTPException(status_code=400, detail="No faces found in reference image")

        # Filter embeddings by selected indices
        ref_vectors = []
        for idx in selected_indices:
            if idx < 0 or idx >= len(embeddings):
                raise HTTPException(status_code=400, detail=f"Invalid face index: {idx}")
            ref_vectors.append(embeddings[idx][0])  # only embedding

        # --- Case A: ZIP dataset ---
        if target.filename.endswith(".zip"):
            tmp_dir = extract_zip_to_temp(target)

            # Nested folder fix
            subdirs = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir)]
            if len(subdirs) == 1 and os.path.isdir(subdirs[0]):
                tmp_dir = subdirs[0]

            job_id = generate_job_id()
            output_dir = os.path.join(tempfile.gettempdir(), f"ffai_out_{job_id}")
            os.makedirs(output_dir, exist_ok=True)

            results = process_images_in_dir(
                data_dir=tmp_dir,
                ref_embeddings=ref_vectors,
                output_dir=output_dir,
                mode=mode,
                threshold=SIMILARITY_THRESHOLD
            )

            # Create ZIP of annotated images
            zip_path = os.path.join(tempfile.gettempdir(), f"annotated_{job_id}.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for r in results:
                    if r["matches"]:
                        zipf.write(r["saved_path"], arcname=os.path.basename(r["saved_path"]))

            shutil.rmtree(tmp_dir)
            return FileResponse(zip_path, media_type="application/zip", filename=f"annotated_{job_id}.zip")

        # --- Case B: Single image ---
        tgt_img = read_upload_file_to_bgr(target)
        if tgt_img is None:
            raise ValueError("Cannot decode target image")

        tgt_embeddings = get_face_embeddings(tgt_img)
        if not tgt_embeddings:
            return {"detail": "No faces found in target image"}

        found_faces = set()
        for tgt_vector, (x1, y1, x2, y2) in tgt_embeddings:
            for i, ref_vector in enumerate(ref_vectors):
                similarity = compare_faces(ref_vector, tgt_vector)
                if similarity >= SIMILARITY_THRESHOLD:
                    cv2.rectangle(tgt_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    found_faces.add(i)

        # Check mode
        if mode == "together" and len(found_faces) < len(ref_vectors):
            return {"detail": "Not all selected faces found in target image"}
        elif not found_faces:
            return {"detail": "Selected person(s) not found in target image"}

        _, buffer = cv2.imencode(".png", tgt_img)
        return StreamingResponse(io.BytesIO(buffer), media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
