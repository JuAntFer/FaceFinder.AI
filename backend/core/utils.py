# core/utils.py

import os
import io
import uuid
import zipfile
import tempfile
import shutil
import time
from pathlib import Path
from typing import List

import cv2
import numpy as np

# -------------------------
# Job store (for future async processing)
# -------------------------
JOB_STORE = {}  # {job_id: {"status": "pending|running|done|error", "result": ...}}


# -------------------------
# Image Handling Utilities
# -------------------------
def read_upload_file_to_bgr(upload_file) -> 'np.ndarray':
    """
    Convert FastAPI UploadFile to OpenCV BGR image (numpy array).
    Returns None if decoding fails.
    """
    contents = upload_file.file.read()
    arr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    upload_file.file.seek(0)  # Reset file pointer for reuse
    return img


def save_upload_to_temp(upload_file) -> str:
    """
    Save an uploaded file to a temporary file and return its path.
    """
    suffix = Path(upload_file.filename).suffix
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(upload_file.file.read())
    upload_file.file.seek(0)
    return path


def extract_zip_to_temp(zip_upload) -> str:
    """
    Extract an uploaded ZIP file to a temporary directory.
    Returns the path of the temp directory.
    """
    tmpdir = tempfile.mkdtemp(prefix="ffai_")
    zbytes = zip_upload.file.read()
    with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
        zf.extractall(tmpdir)
    zip_upload.file.seek(0)
    return tmpdir


def extract_zip_to_temp_safe(zip_upload, max_files=500, max_pixels=10000*10000) -> str:
    """
    Extract ZIP safely:
      - Checks number of images (max_files)
      - Checks image resolution (max_pixels)
      - Ignores non-image or corrupted files
    Raises ValueError if no valid images or too many images.
    """
    tmpdir = extract_zip_to_temp(zip_upload)
    valid_files = []

    for f in os.listdir(tmpdir):
        if f.lower().endswith((".jpg", ".jpeg", ".png")):
            fp = os.path.join(tmpdir, f)
            img = cv2.imread(fp)
            if img is None:
                continue
            h, w = img.shape[:2]
            if h * w > max_pixels:
                continue
            valid_files.append(f)

    if not valid_files:
        raise ValueError("No valid images found in ZIP")
    if len(valid_files) > max_files:
        raise ValueError(f"Too many images in dataset: {len(valid_files)} > {max_files}")

    return tmpdir

# -------------------------
# Job / Temp Utilities
# -------------------------
def generate_job_id() -> str:
    """
    Generate a unique job ID (hex string).
    """
    return uuid.uuid4().hex


def cleanup_old_temp_folders(temp_dir_base=None, max_age_seconds=3600):
    """
    Delete old temporary folders to free disk space.
    - temp_dir_base: base directory to scan (defaults to system temp)
    - max_age_seconds: folders older than this will be deleted
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
                # Ignore errors; possibly in-use or permission issue
                pass

def validate_upload_file(upload_file, allowed_types=("image/jpeg", "image/png", "application/zip"), max_size_mb=50):
    """
    Validate upload type and size.
    Raises HTTPException if invalid.
    """
    # Validate MIME type
    if upload_file.content_type not in allowed_types:
        raise ValueError(f"Invalid file type: {upload_file.content_type}")

    # Validate file size
    upload_file.file.seek(0, os.SEEK_END)
    size_mb = upload_file.file.tell() / (1024*1024)
    upload_file.file.seek(0)
    if size_mb > max_size_mb:
        raise ValueError(f"File too large: {size_mb:.2f} MB (max {max_size_mb} MB)")
