# core/utils.py
import os
import io
import uuid
import zipfile
import tempfile
from pathlib import Path
from typing import Tuple, List
import base64

JOB_STORE = {}  # {job_id: {"status": "pending|running|done|error", "result": ...}}

def read_upload_file_to_bgr(upload_file) -> 'np.ndarray':
    """
    Given a FastAPI UploadFile, return an OpenCV BGR image (numpy array) or None.
    """
    import numpy as np, cv2
    contents = upload_file.file.read()
    arr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    upload_file.file.seek(0)
    return img

def save_upload_to_temp(upload_file) -> str:
    """
    Save upload to a temp file and return path.
    """
    suffix = Path(upload_file.filename).suffix
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(upload_file.file.read())
    upload_file.file.seek(0)
    return path

def extract_zip_to_temp(zip_upload) -> str:
    """
    Extracts uploaded zip to a tempdir and returns the path.
    """
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="ffai_")
    zbytes = zip_upload.file.read()
    zf = zipfile.ZipFile(io.BytesIO(zbytes))
    zf.extractall(tmpdir)
    zip_upload.file.seek(0)
    return tmpdir

def generate_job_id() -> str:
    return uuid.uuid4().hex

