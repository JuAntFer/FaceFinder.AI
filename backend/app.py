# FaceFinderW/backend/app.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import cv2
import numpy as np
import io

# ✅ import face_recognition from your backend package
from backend.core.face_recognition import get_face_embeddings, compare_faces, SIMILARITY_THRESHOLD

app = FastAPI(title="FaceFinder.AI Backend",
              description="API for detecting and annotating faces in images",
              version="1.0")

@app.post("/detect-faces/")
async def detect_faces(file: UploadFile = File(...)):
    """
    Detect faces in an uploaded image and return bounding boxes as JSON.
    """
    try:
        contents = await file.read()
        npimg = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Cannot decode image")

        embeddings = get_face_embeddings(img)
        return {
            "faces_detected": len(embeddings),
            "boxes": [(int(x1), int(y1), int(x2), int(y2)) for _, (x1, y1, x2, y2) in embeddings]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/detect-faces-image/")
async def detect_faces_image(file: UploadFile = File(...)):
    """
    Detect faces in an uploaded image and return an annotated image with bounding boxes.
    """
    try:
        contents = await file.read()
        npimg = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Cannot decode image")

        embeddings = get_face_embeddings(img)
        for _, (x1, y1, x2, y2) in embeddings:
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

        _, buffer = cv2.imencode(".png", img)
        io_buf = io.BytesIO(buffer)

        return StreamingResponse(io_buf, media_type="image/png")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ⚡ Entry point for running directly with `python backend/app.py`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
