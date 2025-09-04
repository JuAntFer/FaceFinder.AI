# core/face_recognition.py
import os
import logging
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from facenet_pytorch import InceptionResnetV1

logger = logging.getLogger(__name__)

# Select device string for ultralytics and torch
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device: {DEVICE}")

# Paths
DEFAULT_YOLO_PATH = os.environ.get("YOLO_WEIGHTS", "backend/models/yolov8n-face-lindevs.pt")

# Load models once
try:
    face_model = YOLO(DEFAULT_YOLO_PATH)
except Exception as e:
    logger.exception("Failed to load YOLO model. Make sure weights are in models/ and path is correct.")
    face_model = None

rec_model = InceptionResnetV1(pretrained="vggface2").eval().to(DEVICE)

SIMILARITY_THRESHOLD = float(os.environ.get("SIM_THRESHOLD", 0.7))


def l2_normalize(a: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    norm = np.linalg.norm(a)
    if norm < eps:
        return a
    return a / norm


def _xyxy_to_int(xyxy):
    arr = np.array(xyxy).flatten()[:4]
    return [int(max(0, v)) for v in arr]


def get_face_embeddings(img_bgr: np.ndarray, resize_to=(160, 160)):
    """
    Detect faces in the BGR image and return list of tuples:
        [(embedding (1D numpy), (x1,y1,x2,y2)), ...]
    Embeddings are L2-normalized 1D numpy arrays.
    """
    if img_bgr is None:
        return []

    # Run YOLO detection (ultralytics). Pass device string; model returns Results
    results = face_model(img_bgr, device=DEVICE, verbose=False)[0]

    embeddings = []
    # results.boxes is a list-like of Box objects
    for box in results.boxes:
        try:
            # robust extraction of coords
            xyxy = box.xyxy[0]  # might be tensor or numpy
            try:
                arr = xyxy.cpu().numpy()
            except Exception:
                arr = np.array(xyxy)
            x1, y1, x2, y2 = [int(max(0, int(v))) for v in arr[:4]]
        except Exception:
            continue

        # guard against invalid crop
        h, w = img_bgr.shape[:2]
        x1c, y1c, x2c, y2c = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
        if x2c <= x1c or y2c <= y1c:
            continue

        face = img_bgr[y1c:y2c, x1c:x2c]
        if face.size == 0:
            continue

        # preprocess for facenet-pytorch
        face_resized = cv2.resize(face, resize_to)
        face_rgb = cv2.cvtColor(face_resized, cv2.COLOR_BGR2RGB)
        # convert to tensor and normalize to [-1,1]
        face_tensor = torch.from_numpy(face_rgb).permute(2, 0, 1).unsqueeze(0).float().to(DEVICE) / 255.0
        face_tensor = (face_tensor - 0.5) / 0.5

        with torch.no_grad():
            emb_tensor = rec_model(face_tensor).cpu().numpy().flatten()
        emb = l2_normalize(emb_tensor)
        embeddings.append((emb, (x1c, y1c, x2c, y2c)))
    return embeddings


def compare_faces(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """
    Compute cosine similarity between two 1-D embeddings (already l2-normalized).
    Returns float in [-1,1] (1==same)
    """
    a = np.asarray(emb1, dtype=np.float32).ravel()
    b = np.asarray(emb2, dtype=np.float32).ravel()
    if a.size == 0 or b.size == 0:
        return -1.0
    # embeddings should be normalized; but normalize to be safe
    a = l2_normalize(a)
    b = l2_normalize(b)
    return float(np.dot(a, b))
