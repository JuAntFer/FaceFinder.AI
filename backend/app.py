# backend/app.py
import os
import shutil
import tempfile
import zipfile
import io
import base64
from pathlib import Path
from typing import List

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.face_recognition import get_face_embeddings, compare_faces, SIMILARITY_THRESHOLD
from core.processor import process_images_in_dir
from core.utils import read_upload_file_to_bgr, extract_zip_to_temp, generate_job_id, JOB_STORE

app = FastAPI(
    title="FaceFinder.AI Backend",
    description="Detect selected faces from reference image(s) in target image(s)",
    version="3.0"
)

# -------------------------
# CORS
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent Reference Storage
# -------------------------
REFS_DIR = os.path.join(tempfile.gettempdir(), "ffai_refs")
os.makedirs(REFS_DIR, exist_ok=True)

# Clear old reference files and memory on startup
for f in os.listdir(REFS_DIR):
    try:
        os.remove(os.path.join(REFS_DIR, f))
    except Exception:
        pass

# REF_STORE: list of dicts { index, ref_source, path, embedding, bbox }
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
# Helper: save UploadFile to disk
# -------------------------
async def _save_upload_to_dir(upload: UploadFile, dest_dir: str) -> str:
    filename = os.path.basename(upload.filename)
    safe_name = f"{len(os.listdir(dest_dir))}_{filename}"
    dest_path = os.path.join(dest_dir, safe_name)
    with open(dest_path, "wb") as f:
        f.write(await upload.read())
    return dest_path

# -------------------------
# Step 1: Upload reference images / zip
# -------------------------
@app.post("/reference-faces/")
async def reference_faces(references: List[UploadFile] = File(...)):
    try:
        new_faces_info = []

        for ref in references:
            validate_upload_file(ref, [".jpg", ".jpeg", ".png", ".zip"], 50)

            if ref.filename.lower().endswith(".zip"):
                tmp_dir = extract_zip_to_temp(ref)
                for root, _, files in os.walk(tmp_dir):
                    for f in files:
                        if f.lower().endswith((".jpg", ".jpeg", ".png")):
                            src = os.path.join(root, f)
                            dest_name = f"{len(os.listdir(REFS_DIR))}_{f}"
                            dest_path = os.path.join(REFS_DIR, dest_name)
                            shutil.copy(src, dest_path)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                dest_path = os.path.join(REFS_DIR, f"{len(os.listdir(REFS_DIR))}_{ref.filename}")
                with open(dest_path, "wb") as out_f:
                    out_f.write(await ref.read())

        # Process new files in REFS_DIR
        existing_paths = {entry["path"] for entry in REF_STORE}
        files_in_dir = sorted([os.path.join(REFS_DIR, f) for f in os.listdir(REFS_DIR)
                               if f.lower().endswith((".jpg", ".jpeg", ".png"))])

        for path in files_in_dir:
            if path in existing_paths:
                continue
            img = cv2.imread(path)
            if img is None:
                continue
            embeddings = get_face_embeddings(img)
            for emb, (x1, y1, x2, y2) in embeddings:
                idx = len(REF_STORE)
                REF_STORE.append({
                    "index": idx,
                    "ref_source": os.path.basename(path),
                    "path": path,
                    "embedding": emb.tolist(),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)]
                })
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
# Step 2: Match selected face(s) with target images / zip
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
        # Determine target dataset
        tmp_data_dir = tempfile.mkdtemp(prefix="target_")
        is_zip_target = target.filename.lower().endswith(".zip")
        
        if is_zip_target:
            tmp_data_dir = extract_zip_to_temp(target)
            subdirs = [os.path.join(tmp_data_dir, d) for d in os.listdir(tmp_data_dir)]
            if len(subdirs) == 1 and os.path.isdir(subdirs[0]):
                tmp_data_dir = subdirs[0]
        else:
            # Single target image → save to tmp_data_dir
            path = os.path.join(tmp_data_dir, target.filename)
            with open(path, "wb") as f:
                f.write(await target.read())

        # Determine reference embeddings to use
        ref_vectors = []
        if REF_STORE:
            all_embeddings = [np.array(entry["embedding"]) for entry in REF_STORE]
            selected_indices = [int(x.strip()) for x in selected_indices_str.split(",") if x.strip()]
            for idx in selected_indices:
                if idx < 0 or idx >= len(all_embeddings):
                    raise HTTPException(status_code=400, detail=f"Invalid face index: {idx}")
                ref_vectors.append(all_embeddings[idx])
        else:
            raise HTTPException(status_code=400, detail="No reference faces available")

        # Process all images in tmp_data_dir
        output_dir = tempfile.mkdtemp(prefix="ffai_out_")
        summary = process_images_in_dir(
            data_dir=tmp_data_dir,
            ref_embeddings=ref_vectors,
            output_dir=output_dir,
            mode=mode,
            max_seconds=max_seconds,
            threshold=SIMILARITY_THRESHOLD
        )

        # Zip all results
        zip_path = os.path.join(tempfile.gettempdir(), "matched_results.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, start=output_dir)
                    zipf.write(file_path, arcname=arcname)

        # Clean up
        shutil.rmtree(tmp_data_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)

        return FileResponse(zip_path, media_type="application/zip", filename="matched_results.zip")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# -------------------------
# Job status
# -------------------------
@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

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
    zip_path = os.path.join(tempfile.gettempdir(), "ilovefacefinder.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=output_dir)
                zipf.write(file_path, arcname=arcname)
    return FileResponse(zip_path, media_type="application/zip", filename="ilovefacefinder.zip")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
