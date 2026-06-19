"""
EcoCache Chat API — FastAPI server wrapping the RAG pipeline.
Run: python server.py  (serves on http://localhost:8000)
"""

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
from query import generate_answer, rag_search

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="EcoCache Chat API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Fallback CO2 estimates when carbon_monitor returns 0 (no GPU) ───────────
_CACHE_HIT_CO2_G = 0.15    # embedding + vector search only
_NEW_GEN_CO2_G = 1.50      # embedding + search + LLM generation

# ── Daily session stats (reset at midnight) ──────────────────────────────────
_session: dict = {"date": None, "total": 0, "hits": 0, "co2_saved_g": 0.0}

# 모델이 "정보 없음"으로 답했는지 판단하는 키워드
_NOT_FOUND_MARKERS = ["찾을 수 없습니다", "찾을 수 없", "정보가 없습니다"]


def _reset_if_new_day() -> None:
    today = str(date.today())
    if _session["date"] != today:
        _session.update({"date": today, "total": 0, "hits": 0, "co2_saved_g": 0.0})


def _sum_measured_co2(metrics: dict) -> float:
    return sum(
        v.get("co2_g", 0.0)
        for v in metrics.values()
        if isinstance(v, dict)
    )


def _is_not_found(text: str) -> bool:
    return any(marker in text for marker in _NOT_FOUND_MARKERS)


class ChatRequest(BaseModel):
    query: str


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    related_for_response = []
    _reset_if_new_day()
    t0 = time.time()

    result = rag_search(req.query)
    cache_hit = result["source"] == "qa_pairs"

    # ── Build response text ───────────────────────────────────────────────────
    if cache_hit:
        top = result["results"][0]
        response_text = top["payload"].get("answer", "")
        similarity = top["score"]
        ref = top["payload"].get("reference_url", "")
        sources = [ref] if ref else []
    else:
        top = result["results"][0] if result["results"] else {}
        similarity = top.get("score", 0.0) if top else 0.0

        # 검색된 관련 문서 (제목 + URL)
        related = [
            {
                "title": item["payload"].get("title", ""),
                "url": item["payload"].get("url", ""),
            }
            for item in result["results"][:2]
            if item["payload"].get("url")
        ]
        sources = [r["url"] for r in related]

        try:
            response_text = generate_answer(req.query, result)
        except Exception:
            fallback_payload = top.get("payload", {}) if top else {}
            response_text = fallback_payload.get("text", "정보를 찾을 수 없습니다.")[:400]

        # ── "찾을 수 없음" 응답이지만 관련 문서가 있는 경우 ──────────────────
        # 완전히 빈 손이 아니라면 "비슷한 주제"로 안내 (정직하게 모르는 척 X)
        if _is_not_found(response_text) and related:
            lines = [f"- {r['title']}" for r in related if r["title"]]
            if lines:
                response_text = (
                    "정확히 일치하는 정보는 찾지 못했지만, 비슷한 주제의 공지가 있습니다:\n\n"
                    + "\n\n".join(lines)
                )
                related_for_response = [r for r in related if r["title"]]
        # related도 없고 진짜 아무것도 못 찾은 경우에만 원래 "찾을 수 없음" 메시지 유지

    latency_s = round(time.time() - t0, 2)

    # ── CO2 calculation ──────────────────────────────────────────────────────
    measured = _sum_measured_co2(result.get("metrics", {}))
    if measured > 0.001:
        co2_grams = -round(measured, 2) if cache_hit else round(measured, 2)
    else:
        co2_grams = -_CACHE_HIT_CO2_G if cache_hit else _NEW_GEN_CO2_G

    # ── Update session stats ─────────────────────────────────────────────────
    _session["total"] += 1
    if cache_hit:
        _session["hits"] += 1
        _session["co2_saved_g"] += abs(co2_grams)

    hit_rate_pct = (
        round(_session["hits"] / _session["total"] * 100, 1)
        if _session["total"] > 0
        else 0.0
    )

    return {
        "response": response_text,
        "cache_hit": cache_hit,
        "similarity": round(similarity, 3),
        "latency_s": latency_s,
        "co2_grams": co2_grams,
        "ci_gkwh": config.CARBON_INTENSITY_G_PER_KWH,
        "sources": [s for s in sources if s],
        "related": related_for_response,
        "stats": {
            "total": _session["total"],
            "hits": _session["hits"],
            "hit_rate_pct": hit_rate_pct,
            "co2_saved_today_g": round(_session["co2_saved_g"], 1),
        },
    }


@app.get("/stats")
def get_stats() -> dict:
    _reset_if_new_day()
    hit_rate_pct = (
        round(_session["hits"] / _session["total"] * 100, 1)
        if _session["total"] > 0
        else 0.0
    )
    return {
        "total": _session["total"],
        "hits": _session["hits"],
        "hit_rate_pct": hit_rate_pct,
        "co2_saved_today_g": round(_session["co2_saved_g"], 1),
    }


# ── Serve frontend static files ──────────────────────────────────────────────
_web_dir = Path(__file__).parent / "web"
if _web_dir.exists():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)