# core/utils.py
import os
import io
import uuid
import zipfile
import tempfile
import shutil
import time
import logging
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
from fastapi import UploadFile, HTTPException

logger = logging.getLogger(__name__)

# -------------------------
# In-memory job store for background tasks
# -------------------------
JOB_STORE = {}  # { job_id: {"status": "pending|running|done|error", "result": ... , "output_dir": ...} }


# -------------------------
# File Upload Utilities
# -------------------------
def read_upload_file_to_bgr(upload_file: UploadFile) -> Optional[np.ndarray]:
    """
    Convert FastAPI UploadFile to OpenCV BGR image.
    Returns None if decoding fails.
    """
    try:
        contents = upload_file.file.read()
        arr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        upload_file.file.seek(0)
        return img
    except Exception as e:
        logger.warning(f"[read_upload_file_to_bgr] Failed to read image: {e}")
        return None


def save_upload_to_temp(upload_file: UploadFile, prefix="ffai_") -> str:
    """
    Save uploaded file to a temporary file and return its path.
    """
    suffix = Path(upload_file.filename).suffix
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(upload_file.file.read())
        upload_file.file.seek(0)
        return path
    except Exception as e:
        logger.error(f"[save_upload_to_temp] Failed to save file: {e}")
        raise


def extract_zip_to_temp(upload_file: UploadFile, max_files: int = 500, max_pixels: int = 10000*10000) -> str:
    """
    Safely extract ZIP file to a temporary directory.
    Checks:
      - max number of files
      - max resolution per image
      - skips corrupted or non-image files
    Returns temp directory path.
    """
    tmpdir = tempfile.mkdtemp(prefix="ffai_zip_")
    try:
        zbytes = upload_file.file.read()
        with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
            image_files = [f for f in zf.namelist() if f.lower().endswith((".jpg", ".jpeg", ".png"))]
            if len(image_files) > max_files:
                raise HTTPException(status_code=400, detail=f"Too many images in ZIP: {len(image_files)} > {max_files}")
            zf.extractall(tmpdir)
        # Validate resolution
        valid_images = []
        for root, _, files in os.walk(tmpdir):
            for f in files:
                if not f.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                fp = os.path.join(root, f)
                img = cv2.imread(fp)
                if img is None:
                    os.remove(fp)
                    continue
                h, w = img.shape[:2]
                if h * w > max_pixels:
                    os.remove(fp)
                    continue
                valid_images.append(fp)
        if not valid_images:
            raise HTTPException(status_code=400, detail="No valid images found in ZIP")
        upload_file.file.seek(0)
        return tmpdir
    except zipfile.BadZipFile:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid ZIP file")
    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"Failed to extract ZIP: {e}")


def validate_upload_file(
    upload_file: UploadFile,
    allowed_extensions: tuple = (".jpg", ".jpeg", ".png", ".zip"),
    max_size_mb: int = 50
):
    """
    Validate file type and size.
    Raises HTTPException if invalid.
    """
    ext = Path(upload_file.filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Allowed: {allowed_extensions}")
    upload_file.file.seek(0, os.SEEK_END)
    size_mb = upload_file.file.tell() / (1024 * 1024)
    upload_file.file.seek(0)
    if size_mb > max_size_mb:
        raise HTTPException(status_code=400, detail=f"File too large: {size_mb:.2f} MB. Max allowed: {max_size_mb} MB")


# -------------------------
# Job / Temp Utilities
# -------------------------
def generate_job_id() -> str:
    """Generate a unique job ID"""
    return uuid.uuid4().hex


def cleanup_old_temp_folders(temp_dir_base: Optional[str] = None, max_age_seconds: int = 3600):
    """
    Delete old temporary folders to free disk space.
    """
    if temp_dir_base is None:
        temp_dir_base = tempfile.gettempdir()
    now = time.time()
    for d in os.listdir(temp_dir_base):
        full_path = os.path.join(temp_dir_base, d)
        if os.path.isdir(full_path):
            try:
                if now - os.path.getmtime(full_path) > max_age_seconds:
                    shutil.rmtree(full_path, ignore_errors=True)
            except Exception:
                continue


# -------------------------
# Helper to save multiple UploadFiles to a directory
# -------------------------
def save_uploads_to_dir(uploads: List[UploadFile], dest_dir: str) -> List[str]:
    """
    Save multiple UploadFile objects into dest_dir.
    Returns list of saved paths.
    """
    os.makedirs(dest_dir, exist_ok=True)
    saved_paths = []
    for upload in uploads:
        safe_name = f"{len(os.listdir(dest_dir))}_{Path(upload.filename).name}"
        dest_path = os.path.join(dest_dir, safe_name)
        with open(dest_path, "wb") as f:
            f.write(upload.file.read())
        upload.file.seek(0)
        saved_paths.append(dest_path)
    return saved_paths
