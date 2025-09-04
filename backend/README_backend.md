# FaceFinder.AI - Backend

1) Install dependencies (preferably in a venv):
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt

2) Put YOLO face weights into `models/`:
   models/yolov8n-face-lindevs.pt
   (or set YOLO_WEIGHTS env var to your weights path)

3) Run dev server:
   uvicorn app.main:app --reload --port 8000

4) Endpoints:
   - POST /api/embeddings
     (form field 'reference' file) -> returns list of detected faces + thumbnails + embeddings
   - POST /api/search
     form fields:
       reference: file
       images[]: multiple image files (OR zipfile: file)
       threshold: float (optional)
       mode: "individually" | "together" (optional)
       async_job: boolean (optional)
     -> returns matches {filename, score, bbox, saved_path}
   - GET /api/jobs/{job_id} for background job status
   - static results are served at http://<host>:8000/static/...

Notes:
- For production, use a reverse proxy, secure CORS, persistent job storage (DB), and object storage for large datasets.
