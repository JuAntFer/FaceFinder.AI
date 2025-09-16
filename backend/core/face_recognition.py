# core/face_recognition.py
import os
import logging
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from facenet_pytorch import InceptionResnetV1

logger = logging.getLogger(__name__)

# -------------------------
# Device setup
# -------------------------
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
logger.info(f"[FaceRecognition] Using device: {DEVICE}")

# -------------------------
# Model paths
# -------------------------
DEFAULT_YOLO_PATH = os.environ.get("YOLO_WEIGHTS", "models/yolov8n-face-lindevs.pt")

# -------------------------
# Load models once at startup
# -------------------------
try:
    face_model = YOLO(DEFAULT_YOLO_PATH)
    logger.info("[FaceRecognition] YOLO model loaded successfully")
except Exception as e:
    logger.exception("[FaceRecognition] Failed to load YOLO model. Check weights path.")
    face_model = None

try:
    rec_model = InceptionResnetV1(pretrained="vggface2").eval().to(DEVICE)
    logger.info("[FaceRecognition] Face embedding model loaded successfully")
except Exception as e:
    logger.exception("[FaceRecognition] Failed to load InceptionResnetV1 model")
    rec_model = None

SIMILARITY_THRESHOLD = float(os.environ.get("SIM_THRESHOLD", 0.7))


# -------------------------
# Utilities
# -------------------------
def l2_normalize(a: np.ndarray, eps: float = 1e-10) -> np.ndarray:
    a = np.asarray(a, dtype=np.float32)
    norm = np.linalg.norm(a)
    if norm < eps:
        return a
    return a / norm


def get_face_embeddings(img_bgr: np.ndarray, resize_to=(160, 160)):
    """
    Detect faces in BGR image and return:
        [(embedding (1D numpy), (x1,y1,x2,y2)), ...]
    """
    if img_bgr is None or face_model is None or rec_model is None:
        return []

    results = face_model(img_bgr, device=DEVICE, verbose=False)[0]

    embeddings = []
    for box in results.boxes:
        try:
            xyxy = box.xyxy[0]
            arr = xyxy.cpu().numpy() if hasattr(xyxy, "cpu") else np.array(xyxy)
            x1, y1, x2, y2 = [int(max(0, v)) for v in arr[:4]]
        except Exception:
            continue

        h, w = img_bgr.shape[:2]
        x1c, y1c, x2c, y2c = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
        if x2c <= x1c or y2c <= y1c:
            continue

        face = img_bgr[y1c:y2c, x1c:x2c]
        if face.size == 0:
            continue

        face_resized = cv2.resize(face, resize_to)
        face_rgb = cv2.cvtColor(face_resized, cv2.COLOR_BGR2RGB)
        face_tensor = torch.from_numpy(face_rgb).permute(2, 0, 1).unsqueeze(0).float().to(DEVICE) / 255.0
        face_tensor = (face_tensor - 0.5) / 0.5

        with torch.no_grad():
            emb_tensor = rec_model(face_tensor).cpu().numpy().flatten()
        emb = l2_normalize(emb_tensor)
        embeddings.append((emb, (x1c, y1c, x2c, y2c)))
    return embeddings


def compare_faces(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """
    Cosine similarity between two normalized embeddings.
    Returns [-1,1] where 1 = same person.
    """
    if emb1 is None or emb2 is None or len(emb1) == 0 or len(emb2) == 0:
        return -1.0
    a = l2_normalize(np.asarray(emb1, dtype=np.float32))
    b = l2_normalize(np.asarray(emb2, dtype=np.float32))
    return float(np.dot(a, b))
