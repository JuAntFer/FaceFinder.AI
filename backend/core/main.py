# core/main.py
import os
import shutil
import logging
import cv2
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
from pathlib import Path

from . import face_recognition, processor, utils
from .schemas import SearchResponse, MatchItem

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="FaceFinder.AI - Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure output folder exists and serve it
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_DIR", "output")).absolute()
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(OUTPUT_ROOT)), name="static")


@app.post("/api/embeddings")
async def embeddings_endpoint(reference: UploadFile = File(...)):
    """
    Returns detected face regions and their thumbnails (base64) and bounding boxes for the reference image.
    Frontend may use this to let the user pick which face(s) from the reference image to use.
    """
    from .utils import read_upload_file_to_bgr
    import base64, cv2

    img = read_upload_file_to_bgr(reference)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image")

    detections = face_recognition.get_face_embeddings(img)
    faces_info = []
    for idx, (emb, bbox) in enumerate(detections):
        x1, y1, x2, y2 = bbox
        crop = img[y1:y2, x1:x2].copy()
        _, jpg = cv2.imencode(".jpg", crop)
        b64 = base64.b64encode(jpg.tobytes()).decode("utf-8")
        faces_info.append({
            "index": idx,
            "bbox": [int(x1), int(y1), int(x2), int(y2)],
            "thumbnail_b64": b64,
            # embed as list so frontend can send embedding directly if needed
            "embedding": emb.tolist()
        })
    return {"faces": faces_info}


@app.post("/api/search", response_model=SearchResponse)
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
    Search endpoint:
      - Upload a reference image (contains one or several faces)
      - Upload either multiple individual images (images[]) OR a zip (zipfile)
      - Returns matched images with scores & bbox
    If async_job=True, a background job is scheduled and a job_id is returned.
    """

    from .utils import save_upload_to_temp, extract_zip_to_temp, generate_job_id, JOB_STORE

    # read reference image and compute embeddings
    ref_tmp = save_upload_to_temp(reference)
    ref_img = cv2.imread(ref_tmp)
    os.remove(ref_tmp)
    if ref_img is None:
        raise HTTPException(status_code=400, detail="Invalid reference image")
    ref_detections = face_recognition.get_face_embeddings(ref_img)
    if not ref_detections:
        return JSONResponse({"matches": []})
    # by default use all ref embeddings
    ref_embeddings = [emb for emb, _ in ref_detections]

    # prepare list of image paths to process
    tmp_dir = None
    image_paths = []
    if images:
        # save uploads to temp files
        for up in images:
            path = save_upload_to_temp(up)
            image_paths.append(path)
    elif zipfile:
        tmp_dir = extract_zip_to_temp(zipfile)
        # collect images in tmp_dir
        for root, _, files in os.walk(tmp_dir):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    image_paths.append(os.path.join(root, f))
    else:
        raise HTTPException(status_code=400, detail="No images provided")

    output_dir = OUTPUT_ROOT / generate_job_id()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir_str = str(output_dir)

    def _run_process(job_id=None):
        try:
            utils.JOB_STORE[job_id]["status"] = "running"
            results = processor.process_images_in_dir(
                data_dir=os.path.dirname(image_paths[0]) if images else tmp_dir,
                ref_embeddings=ref_embeddings,
                output_dir=output_dir_str,
                mode=mode,
                threshold=threshold,
                progress_callback=lambda p: None
            )
            # Patch saved_path to served static URL
            matches = []
            for r in results:
                saved_rel = os.path.relpath(r["saved_path"], OUTPUT_ROOT)
                url = f"/static/{saved_rel.replace(os.path.sep, '/')}"
                # pick best match score
                score = max(m["score"] for m in r["matches"]) if r["matches"] else 0.0
                bbox = r["matches"][0]["bbox"] if r["matches"] else [0,0,0,0]
                matches.append({"filename": r["filename"], "score": score, "bbox": bbox, "saved_path": url})
            utils.JOB_STORE[job_id]["status"] = "done"
            utils.JOB_STORE[job_id]["result"] = matches
        except Exception as e:
            utils.JOB_STORE[job_id]["status"] = "error"
            utils.JOB_STORE[job_id]["error"] = str(e)
        finally:
            # cleanup temp files if any (uploads saved earlier)
            if images:
                for p in image_paths:
                    try: os.remove(p)
                    except: pass
            if tmp_dir:
                try: shutil.rmtree(tmp_dir)
                except: pass

    # If async requested, schedule background job
    if async_job:
        job_id = generate_job_id()
        utils.JOB_STORE[job_id] = {"status": "queued", "result": None}
        # schedule in background
        background_tasks.add_task(_run_process, job_id)
        return {"job_id": job_id}

    # Otherwise run synchronously (blocking)
    job_id = generate_job_id()
    utils.JOB_STORE[job_id] = {"status": "running", "result": None}
    _run_process(job_id)
    # Build response
    if utils.JOB_STORE[job_id]["status"] == "done":
        matches = utils.JOB_STORE[job_id]["result"]
        return {"matches": matches}
    else:
        raise HTTPException(status_code=500, detail=utils.JOB_STORE[job_id].get("error", "Processing failed"))


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Query background job status and results."""
    if job_id not in utils.JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")
    return utils.JOB_STORE[job_id]
