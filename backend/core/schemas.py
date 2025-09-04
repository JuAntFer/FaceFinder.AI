# core/schemas.py
from typing import List
from pydantic import BaseModel

class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

class MatchItem(BaseModel):
    filename: str
    score: float
    bbox: List[int]  # [x1,y1,x2,y2]
    saved_path: str

class SearchResponse(BaseModel):
    matches: List[MatchItem]
