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
    description="Detect selected faces from reference image(s) in target image(s)",
    version="3.0",
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Simple server-side persistent reference store (in-memory + files)
# -------------------------
REFS_DIR = os.path.join(tempfile.gettempdir(), "ffai_refs")
os.makedirs(REFS_DIR, exist_ok=True)

# REF_STORE: list of dicts { index: int, ref_source: str, path: str, embedding: list, bbox: [x1,y1,x2,y2] }
REF_STORE = []


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
# Helper: save UploadFile to disk and return path
# -------------------------
async def _save_upload_to_dir(upload: UploadFile, dest_dir: str) -> str:
    filename = os.path.basename(upload.filename)
    safe_name = f"{len(os.listdir(dest_dir))}_{filename}"
    dest_path = os.path.join(dest_dir, safe_name)
    with open(dest_path, "wb") as f:
        f.write(await upload.read())
    return dest_path


# -------------------------
# Step 1: Extract faces from reference images (multiple or zip)
# - Persist saved reference images in REFS_DIR
# - Append their faces/embeddings into REF_STORE with global stable indices
# -------------------------
@app.post("/reference-faces/")
async def reference_faces(references: List[UploadFile] = File(...)):
    try:
        # Accept uploaded images or a zip containing images.
        # Save images into REFS_DIR (persistent across calls).
        new_faces_info = []

        for ref in references:
            # Validate
            validate_upload_file(ref, [".jpg", ".jpeg", ".png", ".zip"], 50)

            # If zip: extract images into a temp dir then move them into REFS_DIR
            if ref.filename.lower().endswith(".zip"):
                tmp_dir = extract_zip_to_temp(ref)
                for root, _, files in os.walk(tmp_dir):
                    for f in files:
                        if f.lower().endswith((".jpg", ".jpeg", ".png")):
                            src = os.path.join(root, f)
                            dest_name = f"{len(os.listdir(REFS_DIR))}_{os.path.basename(src)}"
                            dest_path = os.path.join(REFS_DIR, dest_name)
                            shutil.copy(src, dest_path)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                dest_path = os.path.join(REFS_DIR, f"{len(os.listdir(REFS_DIR))}_{os.path.basename(ref.filename)}")
                with open(dest_path, "wb") as out_f:
                    out_f.write(await ref.read())

        # Now scan REFS_DIR for any images that are NOT yet in REF_STORE.
        # We'll identify new files by path not present in existing REF_STORE entries.
        existing_paths = {entry["path"] for entry in REF_STORE}
        files_in_dir = sorted([
            os.path.join(REFS_DIR, f) for f in os.listdir(REFS_DIR)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ])

        for path in files_in_dir:
            if path in existing_paths:
                continue  # already processed
            # compute embeddings and store each face found in this image
            img = cv2.imread(path)
            if img is None:
                continue
            embeddings = get_face_embeddings(img)
            for emb, (x1, y1, x2, y2) in embeddings:
                idx = len(REF_STORE)  # global stable index
                # store embedding as list for JSON-friendly structure; keep original as numpy when used
                REF_STORE.append({
                    "index": idx,
                    "ref_source": os.path.basename(path),
                    "path": path,
                    "embedding": emb.tolist(),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)]
                })

                # create thumbnail base64 to return to frontend for immediate display
                crop = img[y1:y2, x1:x2].copy()
                _, jpg = cv2.imencode(".jpg", crop)
                b64 = base64.b64encode(jpg.tobytes()).decode("utf-8")
                new_faces_info.append({
                    "index": idx,
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "thumbnail_b64": b64,
                    "ref_source": os.path.basename(path)
                })

        return {"faces": new_faces_info}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------
# Step 2: Match selected face(s)
# - By default uses embeddings present in REF_STORE (server-side persistent)
# - If REF_STORE empty, accepts references uploaded in the same request (backward-compatible)
# -------------------------
@app.post("/match-face-selected/")
async def match_face_selected(
    references: List[UploadFile] = File([]),
    target: UploadFile = File(...),
    selected_indices_str: str = Form(...),
    mode: str = Form("individually"),
    max_seconds: int = Form(300),
    background_tasks: BackgroundTasks = None
):
    try:
        # Build target dataset (single image or zip -> tmp dir)
        is_zip_target = target.filename.lower().endswith(".zip")
        tmp_data_dir = None
        if is_zip_target:
            tmp_data_dir = extract_zip_to_temp(target)
            # if zip contains a single top-level folder, use it
            subdirs = [os.path.join(tmp_data_dir, d) for d in os.listdir(tmp_data_dir)]
            if len(subdirs) == 1 and os.path.isdir(subdirs[0]):
                tmp_data_dir = subdirs[0]
        else:
            # single image target will be handled later by read_upload_file_to_bgr
            pass

        # Determine reference embeddings to use:
        # 1) Prefer server-side REF_STORE if it has entries (stable global indices)
        # 2) If REF_STORE empty, process uploaded references in this request (backward compatibility)
        ref_vectors = []
        if REF_STORE:
            # Convert stored embedding lists back to numpy arrays
            all_embeddings = [np.array(entry["embedding"]) for entry in REF_STORE]
            # parse selected_indices_str (these are global indices)
            try:
                selected_indices = [int(x.strip()) for x in selected_indices_str.split(",") if x.strip()]
            except:
                raise HTTPException(status_code=400, detail="selected_indices must be comma-separated integers")
            for idx in selected_indices:
                if idx < 0 or idx >= len(all_embeddings):
                    raise HTTPException(status_code=400, detail=f"Invalid face index: {idx}")
                ref_vectors.append(all_embeddings[idx])
        else:
            # no server-side refs; fall back to provided references param (old behavior)
            ref_files = []
            if len(references) == 1 and references[0].filename.lower().endswith(".zip"):
                tmp_refs_dir = extract_zip_to_temp(references[0])
                for root, _, files in os.walk(tmp_refs_dir):
                    for f in files:
                        if f.lower().endswith((".jpg", ".jpeg", ".png")):
                            ref_files.append(os.path.join(root, f))
            else:
                tmp_refs_dir = tempfile.mkdtemp(prefix="refs_")
                for ref in references:
                    validate_upload_file(ref, [".jpg", ".jpeg", ".png", ".zip"], 50)
                    path = os.path.join(tmp_refs_dir, ref.filename)
                    with open(path, "wb") as f:
                        f.write(await ref.read())
                    ref_files.append(path)

            all_embeddings = []
            for ref_path in ref_files:
                img = cv2.imread(ref_path)
                if img is None:
                    continue
                embs = get_face_embeddings(img)
                for emb, bbox in embs:
                    all_embeddings.append(emb)

            if not all_embeddings:
                raise HTTPException(status_code=400, detail="No faces found in provided reference images")

            try:
                selected_indices = [int(x.strip()) for x in selected_indices_str.split(",") if x.strip()]
            except:
                raise HTTPException(status_code=400, detail="selected_indices must be comma-separated integers")
            for idx in selected_indices:
                if idx < 0 or idx >= len(all_embeddings):
                    raise HTTPException(status_code=400, detail=f"Invalid face index: {idx}")
                ref_vectors.append(all_embeddings[idx])

            # Clean temporary refs dir
            try:
                shutil.rmtree(tmp_refs_dir, ignore_errors=True)
            except:
                pass

        # -------------------------
        # If target is a ZIP -> background or synchronous job over a folder
        # -------------------------
        if is_zip_target:
            job_id = generate_job_id()
            output_dir = os.path.join(tempfile.gettempdir(), f"ffai_out_{job_id}")
            os.makedirs(output_dir, exist_ok=True)

            # Background job support
            if background_tasks:
                JOB_STORE[job_id] = {"status": "pending", "result": None, "output_dir": output_dir}
                def background_job():
                    try:
                        summary = process_images_in_dir(
                            data_dir=tmp_data_dir,
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
                        shutil.rmtree(tmp_data_dir, ignore_errors=True)
                background_tasks.add_task(background_job)
                return {"job_id": job_id, "status": "pending"}

            # synchronous processing
            try:
                summary = process_images_in_dir(
                    data_dir=tmp_data_dir,
                    ref_embeddings=ref_vectors,
                    output_dir=output_dir,
                    mode=mode,
                    max_seconds=max_seconds,
                    threshold=SIMILARITY_THRESHOLD
                )
                # create zip
                zip_path = os.path.join(tempfile.gettempdir(), f"annotated_{generate_job_id()}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(output_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, start=output_dir)
                            zipf.write(file_path, arcname=arcname)
                summary["zip_file"] = os.path.basename(zip_path)
                return JSONResponse(summary)
            finally:
                shutil.rmtree(tmp_data_dir, ignore_errors=True)

        # -------------------------
        # Single target image case
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
# Job status
# -------------------------
@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOB_STORE[job_id]


# -------------------------
# Download job output
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
