# core/processor.py# core/processor.py
import os
import cv2
import numpy as np
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from .face_recognition import get_face_embeddings, compare_faces, SIMILARITY_THRESHOLD

# -------------------------
# Annotate and save
# -------------------------
def annotate_and_save(img, bbox_list, out_path: str):
    """
    Draw bounding boxes and similarity scores on an image and save to out_path.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    for bbox, score in bbox_list:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, f"{score:.2f}", (x1, max(10, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imwrite(out_path, img)


# -------------------------
# Worker for processing images
# -------------------------
def _process_images_worker(
    data_dir: str,
    ref_embeddings: List[np.ndarray],
    output_dir: str,
    mode: str,
    threshold: float,
    progress_callback=None
) -> Dict:
    image_files = [f for f in os.listdir(data_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    total = len(image_files)
    results = []
    skipped = 0

    for i, fname in enumerate(image_files):
        fp = os.path.join(data_dir, fname)
        try:
            img = cv2.imread(fp)
            if img is None:
                raise ValueError("Failed to read image")

            detections = get_face_embeddings(img)
            if not detections:
                skipped += 1
                continue

            # Compare detections with reference embeddings
            found_info = []
            for ref_idx, ref_emb in enumerate(ref_embeddings):
                for emb, bbox in detections:
                    score = compare_faces(ref_emb, emb)
                    if score >= threshold:
                        found_info.append((bbox, score, ref_idx))

            if mode == "individually" and found_info:
                out_path = os.path.join(output_dir, fname)
                annotate_and_save(img.copy(), [(bbox, score) for (bbox, score, _) in found_info], out_path)
                results.append({
                    "filename": fname,
                    "saved_path": out_path,
                    "matches": [{"bbox": list(bbox), "score": float(score), "ref_index": int(ref_idx)}
                                for (bbox, score, ref_idx) in found_info]
                })
            elif mode == "together":
                matched_ref_indices = {r for (_, _, r) in found_info}
                if len(matched_ref_indices) == len(ref_embeddings) and len(ref_embeddings) > 0:
                    out_path = os.path.join(output_dir, fname)
                    annotate_and_save(img.copy(), [(bbox, score) for (bbox, score, _) in found_info], out_path)
                    results.append({
                        "filename": fname,
                        "saved_path": out_path,
                        "matches": [{"bbox": list(bbox), "score": float(score), "ref_index": int(ref_idx)}
                                    for (bbox, score, ref_idx) in found_info]
                    })
        except Exception as e:
            skipped += 1
            print(f"[WARNING] Skipping image {fname}: {e}")

        if progress_callback:
            progress_callback(int((i + 1) / total * 100))

    matches_found = sum(len(r["matches"]) for r in results)
    return {
        "total_images": total,
        "processed_images": len(results),
        "matches_found": matches_found,
        "skipped_images": skipped,
        "results": results
    }


# -------------------------
# Public API with timeout
# -------------------------
def process_images_in_dir(
    data_dir: str,
    ref_embeddings: List[np.ndarray],
    output_dir: str,
    mode: str = "individually",
    threshold: float = SIMILARITY_THRESHOLD,
    progress_callback=None,
    max_seconds: int = 300
) -> Dict:
    """
    Cross-platform wrapper that runs _process_images_worker with a timeout.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_process_images_worker, data_dir, ref_embeddings, output_dir, mode, threshold, progress_callback)
        try:
            return future.result(timeout=max_seconds)
        except TimeoutError:
            print("[ERROR] Processing timed out")
            return {
                "total_images": len([f for f in os.listdir(data_dir) if f.lower().endswith(('.jpg','.jpeg','.png'))]),
                "processed_images": 0,
                "matches_found": 0,
                "skipped_images": 0,
                "results": [],
                "error": "Processing timed out"
            }
