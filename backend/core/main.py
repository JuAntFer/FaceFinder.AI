# core/main.py
import os
import shutil
import logging
import cv2
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import face_recognition, processor, utils

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="FaceFinder.AI - Backend")

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

# -------------------------
# Output storage
# -------------------------
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_DIR", "output")).absolute()
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# -------------------------
# Embeddings Endpoint
# -------------------------
@app.post("/api/embeddings")
async def embeddings_endpoint(reference: UploadFile = File(...)):
    """
    Detect faces in the uploaded reference image.
    Returns bounding boxes, thumbnails (base64), and embeddings.
    """
    img = utils.read_upload_file_to_bgr(reference)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image")

    detections = face_recognition.get_face_embeddings(img)
    faces_info = []
    for idx, (emb, bbox) in enumerate(detections):
        x1, y1, x2, y2 = bbox
        crop = img[y1:y2, x1:x2].copy()
        _, jpg = cv2.imencode(".jpg", crop)
        b64 = jpg.tobytes()
        import base64
        faces_info.append({
            "index": idx,
            "bbox": [int(x1), int(y1), int(x2), int(y2)],
            "thumbnail_b64": base64.b64encode(b64).decode("utf-8"),
            "embedding": emb.tolist()
        })
    return {"faces": faces_info}


# -------------------------
# Search Endpoint
# -------------------------
@app.post("/api/search")
async def search_endpoint(
    reference: UploadFile = File(...),
    images: Optional[List[UploadFile]] = File(None),
    zipfile: Optional[UploadFile] = File(None),
    threshold: float = Form(face_recognition.SIMILARITY_THRESHOLD),
    mode: str = Form("individually"),
    async_job: bool = Form(False),
    background_tasks: BackgroundTasks = None,
):
    """
    Search faces in uploaded images or ZIP using reference embeddings.
    Supports async jobs with job_id.
    """
    from .utils import save_upload_to_temp, extract_zip_to_temp, generate_job_id, JOB_STORE

    # --- Reference embeddings ---
    ref_tmp = save_upload_to_temp(reference)
    ref_img = cv2.imread(ref_tmp)
    os.remove(ref_tmp)
    if ref_img is None:
        raise HTTPException(status_code=400, detail="Invalid reference image")
    ref_detections = face_recognition.get_face_embeddings(ref_img)
    if not ref_detections:
        return JSONResponse({"matches": []})
    ref_embeddings = [emb for emb, _ in ref_detections]

    # --- Target images ---
    tmp_dir = None
    image_paths = []
    if images:
        for up in images:
            path = save_upload_to_temp(up)
            image_paths.append(path)
    elif zipfile:
        tmp_dir = extract_zip_to_temp(zipfile)
        for root, _, files in os.walk(tmp_dir):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    image_paths.append(os.path.join(root, f))
    else:
        raise HTTPException(status_code=400, detail="No target images provided")

    # --- Output directory ---
    output_dir = OUTPUT_ROOT / generate_job_id()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir_str = str(output_dir)

    # --- Worker function ---
    def _run_process(job_id=None):
        try:
            JOB_STORE[job_id]["status"] = "running"
            results = processor.process_images_in_dir(
                data_dir=os.path.dirname(image_paths[0]) if images else tmp_dir,
                ref_embeddings=ref_embeddings,
                output_dir=output_dir_str,
                mode=mode,
                threshold=threshold,
                progress_callback=lambda p: None
            )
            # Map saved_path to static URL
            matches = []
            for r in results["results"]:
                saved_rel = os.path.relpath(r["saved_path"], OUTPUT_ROOT)
                url = f"/static/{saved_rel.replace(os.path.sep, '/')}"
                score = max(m["score"] for m in r["matches"]) if r["matches"] else 0.0
                bbox = r["matches"][0]["bbox"] if r["matches"] else [0,0,0,0]
                matches.append({"filename": r["filename"], "score": score, "bbox": bbox, "saved_path": url})
            JOB_STORE[job_id]["status"] = "done"
            JOB_STORE[job_id]["result"] = matches
        except Exception as e:
            JOB_STORE[job_id]["status"] = "error"
            JOB_STORE[job_id]["error"] = str(e)
        finally:
            # Cleanup temp files
            for p in image_paths:
                try: os.remove(p)
                except: pass
            if tmp_dir:
                try: shutil.rmtree(tmp_dir)
                except: pass

    # --- Async or sync ---
    if async_job:
        job_id = generate_job_id()
        JOB_STORE[job_id] = {"status": "queued", "result": None}
        background_tasks.add_task(_run_process, job_id)
        return {"job_id": job_id}

    job_id = generate_job_id()
    JOB_STORE[job_id] = {"status": "running", "result": None}
    _run_process(job_id)
    if JOB_STORE[job_id]["status"] == "done":
        return {"matches": JOB_STORE[job_id]["result"]}
    else:
        raise HTTPException(status_code=500, detail=JOB_STORE[job_id].get("error", "Processing failed"))


# -------------------------
# Job Status Endpoint
# -------------------------
@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Query background job status and results."""
    if job_id not in utils.JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")
    return utils.JOB_STORE[job_id]
