from typing import List, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str


class ChatResult(BaseModel):
    response: Optional[str] = None
    similarity: Optional[float] = None
    cache_hit: bool = False
    latency: Optional[float] = None       # ms
    co2_grams: Optional[float] = None     # 미통합 — 항상 null
    ci_g_per_kwh: Optional[float] = None  # 현재 한국 탄소 집약도
    sources: List[str] = []               # doc_id 목록


class ChatResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    result: Optional[ChatResult] = None
