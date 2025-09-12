# backend/app.py
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
import cv2, numpy as np, io, tempfile, os, zipfile, shutil, base64
from pathlib import Path
from typing import List

from backend.core.face_recognition import (
    get_face_embeddings,
    compare_faces,
    SIMILARITY_THRESHOLD,
)
from backend.core.utils import (
    read_upload_file_to_bgr,
    extract_zip_to_temp,
    generate_job_id,
    cleanup_old_temp_folders,
    JOB_STORE
)
from backend.core.processor import process_images_in_dir

app = FastAPI(
    title="FaceFinder.AI Backend",
    description="Detect selected faces from reference image in target image(s)",
    version="2.7",
)

from fastapi.middleware.cors import CORSMiddleware
# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://127.0.0.1:5500"] for stricter rules
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# File validation
# -------------------------
def validate_upload_file(upload_file: UploadFile, allowed_extensions: list, max_size_mb: int):
    ext = Path(upload_file.filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {allowed_extensions}")

    upload_file.file.seek(0, os.SEEK_END)
    size = upload_file.file.tell() / (1024*1024)
    upload_file.file.seek(0)
    if size > max_size_mb:
        raise HTTPException(status_code=400, detail=f"File too large: {size:.2f} MB. Max allowed: {max_size_mb} MB")

# -------------------------
# Step 1: Extract faces from reference image
# -------------------------
@app.post("/reference-faces/")
async def reference_faces(reference: UploadFile = File(...)):
    try:
        cleanup_old_temp_folders()
        validate_upload_file(reference, allowed_extensions=[".jpg", ".jpeg", ".png"], max_size_mb=50)

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

# -------------------------
# Step 2: Match selected face(s)
# -------------------------
@app.post("/match-face-selected/")
async def match_face_selected(
    reference: UploadFile = File(...),
    target: UploadFile = File(...),
    selected_indices_str: str = Form(..., description="Comma-separated indices of faces to detect"),
    mode: str = Form("individually", description="Detection mode: 'individually' or 'together'"),
    max_seconds: int = Form(300, description="Maximum processing time in seconds for the dataset"),
    background_tasks: BackgroundTasks = None
):
    try:
        cleanup_old_temp_folders()
        validate_upload_file(reference, allowed_extensions=[".jpg", ".jpeg", ".png"], max_size_mb=50)
        validate_upload_file(target, allowed_extensions=[".jpg", ".jpeg", ".png", ".zip"], max_size_mb=200)

        try:
            selected_indices = [int(x.strip()) for x in selected_indices_str.split(",") if x.strip()]
        except:
            raise HTTPException(status_code=400, detail="selected_indices must be comma-separated integers")

        ref_img = read_upload_file_to_bgr(reference)
        if ref_img is None:
            raise ValueError("Cannot decode reference image")

        embeddings = get_face_embeddings(ref_img)
        if not embeddings:
            raise HTTPException(status_code=400, detail="No faces found in reference image")

        ref_vectors = []
        for idx in selected_indices:
            if idx < 0 or idx >= len(embeddings):
                raise HTTPException(status_code=400, detail=f"Invalid face index: {idx}")
            ref_vectors.append(embeddings[idx][0])

        # -------------------------
        # Case A: ZIP dataset
        # -------------------------
        if target.filename.endswith(".zip"):
            tmp_dir = extract_zip_to_temp(target)

            subdirs = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir)]
            if len(subdirs) == 1 and os.path.isdir(subdirs[0]):
                tmp_dir = subdirs[0]

            job_id = generate_job_id()
            output_dir = os.path.join(tempfile.gettempdir(), f"ffai_out_{job_id}")
            os.makedirs(output_dir, exist_ok=True)

            # Background job
            if background_tasks:
                JOB_STORE[job_id] = {"status": "pending", "result": None, "output_dir": output_dir}

                def background_job():
                    try:
                        summary = process_images_in_dir(
                            data_dir=tmp_dir,
                            ref_embeddings=ref_vectors,
                            output_dir=output_dir,
                            mode=mode,
                            max_seconds=max_seconds,
                            threshold=SIMILARITY_THRESHOLD
                        )
                        JOB_STORE[job_id]["status"] = "done"
                        JOB_STORE[job_id]["result"] = summary
                    except Exception as e:
                        JOB_STORE[job_id]["status"] = "error"
                        JOB_STORE[job_id]["result"] = str(e)
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)

                background_tasks.add_task(background_job)
                return {"job_id": job_id, "status": "pending"}

            # Synchronous processing
            try:
                summary = process_images_in_dir(
                    data_dir=tmp_dir,
                    ref_embeddings=ref_vectors,
                    output_dir=output_dir,
                    mode=mode,
                    max_seconds=max_seconds,
                    threshold=SIMILARITY_THRESHOLD
                )
                # Add thumbnails to each matched image
                for r in summary["results"]:
                    if r["matches"]:
                        img = cv2.imread(r["saved_path"])
                        if img is not None:
                        # Resize thumbnail to 128px height while keeping aspect ratio
                            h, w = img.shape[:2]
                            new_h = 128
                            new_w = int(w * (new_h / h))
                            thumb = cv2.resize(img, (new_w, new_h))
                            _, jpg = cv2.imencode(".jpg", thumb)
                            b64 = base64.b64encode(jpg.tobytes()).decode("utf-8")
                            r["thumbnail_b64"] = b64


                # ZIP the output folder
                zip_path = os.path.join(tempfile.gettempdir(), f"annotated_{job_id}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(output_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, start=output_dir)
                            zipf.write(file_path, arcname=arcname)
                summary["zip_file"] = os.path.basename(zip_path)

                return JSONResponse(summary)
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # -------------------------
        # Case B: Single image
        # -------------------------
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

        if mode == "together" and len(found_faces) < len(ref_vectors):
            return {"detail": "Not all selected faces found in target image"}
        elif not found_faces:
            return {"detail": "Selected person(s) not found in target image"}

        _, buffer = cv2.imencode(".png", tgt_img)
        return StreamingResponse(io.BytesIO(buffer), media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# -------------------------
# Job status endpoint
# -------------------------
@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOB_STORE[job_id]

# -------------------------
# Download output folder for finished job
# -------------------------
@app.get("/download/{job_id}")
async def download_job_output(job_id: str):
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not finished yet")

    output_dir = job.get("output_dir")
    if not output_dir or not os.path.exists(output_dir):
        raise HTTPException(status_code=404, detail="Output folder not found")

    zip_path = os.path.join(tempfile.gettempdir(), f"{job_id}_output.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=output_dir)
                zipf.write(file_path, arcname=arcname)
    return FileResponse(zip_path, media_type="application/zip", filename=f"{job_id}_output.zip")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
