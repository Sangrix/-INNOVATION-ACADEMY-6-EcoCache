from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str


class SourceLink(BaseModel):
    url: str
    title: str


class ChatResult(BaseModel):
    response: Optional[str] = None
    similarity: Optional[float] = None
    cache_hit: bool = False
    latency: Optional[float] = None
    co2_grams: Optional[float] = None
    ci_g_per_kwh: Optional[float] = None
    sources: List[SourceLink] = Field(default_factory=list)
    timings: List[Dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    result: Optional[ChatResult] = None
