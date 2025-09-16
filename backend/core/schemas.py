# core/schemas.py
from typing import List, Optional
from pydantic import BaseModel, Field

# -------------------------
# Bounding Box
# -------------------------
class BBox(BaseModel):
    x1: int = Field(..., description="Top-left X coordinate")
    y1: int = Field(..., description="Top-left Y coordinate")
    x2: int = Field(..., description="Bottom-right X coordinate")
    y2: int = Field(..., description="Bottom-right Y coordinate")

# -------------------------
# Reference Face Item
# -------------------------
class ReferenceFace(BaseModel):
    index: int = Field(..., description="Unique face index in REF_STORE")
    bbox: List[int] = Field(..., description="[x1,y1,x2,y2]")
    thumbnail_b64: str = Field(..., description="Base64 thumbnail of face")
    ref_source: str = Field(..., description="Source image filename")

# -------------------------
# Match item for search results
# -------------------------
class MatchItem(BaseModel):
    filename: str = Field(..., description="Target image filename")
    score: float = Field(..., description="Similarity score (0-1)")
    bbox: List[int] = Field(..., description="[x1,y1,x2,y2]")
    saved_path: str = Field(..., description="Path to annotated image (served via /static or zip)")

# -------------------------
# Search response
# -------------------------
class SearchResponse(BaseModel):
    matches: List[MatchItem] = Field(default_factory=list)

# -------------------------
# Job status model for async tasks
# -------------------------
class JobStatus(BaseModel):
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status: queued, running, done, error")
    result: Optional[dict] = Field(None, description="Job result or error message")
    output_dir: Optional[str] = Field(None, description="Path to job output directory")

# -------------------------
# Reference faces response
# -------------------------
class ReferenceFacesResponse(BaseModel):
    faces: List[ReferenceFace] = Field(default_factory=list)


