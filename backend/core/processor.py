# core/processor.py
import os
import cv2
import json
import numpy as np
from typing import List, Tuple, Dict, Optional
from .face_recognition import get_face_embeddings, compare_faces, SIMILARITY_THRESHOLD


def annotate_and_save(img, bbox_list, out_path: str):
    """Draw bboxes and scores on image and save to out_path (creates dirs)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    for bbox, score in bbox_list:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(img, f"{score:.2f}", (x1, max(10, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
    cv2.imwrite(out_path, img)


def process_images_in_dir(
    data_dir: str,
    ref_embeddings: List[np.ndarray],
    output_dir: str,
    mode: str = "individually",
    threshold: float = SIMILARITY_THRESHOLD,
    progress_callback=None
) -> List[Dict]:
    """
    Walks images in data_dir, compares faces to ref_embeddings,
    annotates & writes matches into output_dir.
    Returns a list of result dicts:
        {filename, saved_path, matches: [ {bbox, score, ref_index}, ... ] }
    """
    image_files = [f for f in os.listdir(data_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    total = len(image_files)
    results = []

    for i, fname in enumerate(image_files):
        fp = os.path.join(data_dir, fname)
        img = cv2.imread(fp)
        if img is None:
            if progress_callback:
                progress_callback(int((i+1)/total*100))
            continue

        detections = get_face_embeddings(img)
        if not detections:
            if progress_callback:
                progress_callback(int((i+1)/total*100))
            continue

        # For each detection, check similarity to each ref embedding
        found_info = []  # list of (bbox, score, ref_idx)
        for ref_idx, ref_emb in enumerate(ref_embeddings):
            for emb, bbox in detections:
                score = compare_faces(ref_emb, emb)
                if score >= threshold:
                    found_info.append((bbox, score, ref_idx))

        # Decide based on mode
        saved = False
        if mode == "individually" and found_info:
            out_path = os.path.join(output_dir, fname)
            annotate_and_save(img.copy(), [ (bbox, score) for (bbox, score, _) in found_info ], out_path)
            results.append({"filename": fname, "saved_path": out_path, "matches": [
                {"bbox": list(bbox), "score": float(score), "ref_index": int(ref_idx)}
                for (bbox, score, ref_idx) in found_info
            ]})
            saved = True
        elif mode == "together":
            # require that all ref_embeddings have at least one match
            matched_ref_indices = {r for (_, _, r) in found_info}
            if len(matched_ref_indices) == len(ref_embeddings) and len(ref_embeddings) > 0:
                out_path = os.path.join(output_dir, fname)
                annotate_and_save(img.copy(), [ (bbox, score) for (bbox, score, _) in found_info ], out_path)
                results.append({"filename": fname, "saved_path": out_path, "matches": [
                    {"bbox": list(bbox), "score": float(score), "ref_index": int(ref_idx)}
                    for (bbox, score, ref_idx) in found_info
                ]})
                saved = True

        if progress_callback:
            progress_callback(int((i+1)/total*100))

    return results

