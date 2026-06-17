from __future__ import annotations

import argparse
import json
import mimetypes
import os
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import unquote, urlparse

import config
from carbon_monitor import CarbonMonitor
from rag.langchain_pipeline import get_cached_pipeline


BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
DEFAULT_LLM_BASELINE_CO2_G = float(os.getenv("WEB_LLM_BASELINE_CO2_G", "0.084"))
_STATS_LOCK = Lock()
_DAILY_STATS: dict[str, Any] = {
    "date": date.today().isoformat(),
    "total_requests": 0,
    "cache_hits": 0,
    "llm_calls": 0,
    "co2_saved_g": 0.0,
    "llm_co2_total_g": 0.0,
    "llm_samples": 0,
}
_RECENT_EVENTS: list[dict[str, Any]] = []


def _reset_daily_stats_if_needed() -> None:
    today = date.today().isoformat()
    if _DAILY_STATS["date"] == today:
        return

    _DAILY_STATS.update(
        {
            "date": today,
            "total_requests": 0,
            "cache_hits": 0,
            "llm_calls": 0,
            "co2_saved_g": 0.0,
            "llm_co2_total_g": 0.0,
            "llm_samples": 0,
        }
    )
    _RECENT_EVENTS.clear()


def _current_llm_baseline_co2_g() -> float:
    if _DAILY_STATS["llm_samples"] > 0:
        return _DAILY_STATS["llm_co2_total_g"] / _DAILY_STATS["llm_samples"]
    return DEFAULT_LLM_BASELINE_CO2_G


def get_daily_stats() -> dict[str, Any]:
    with _STATS_LOCK:
        _reset_daily_stats_if_needed()
        total = _DAILY_STATS["total_requests"]
        cache_hits = _DAILY_STATS["cache_hits"]
        hit_rate = cache_hits / total if total else 0.0
        return {
            "date": _DAILY_STATS["date"],
            "total_requests": total,
            "cache_hits": cache_hits,
            "llm_calls": _DAILY_STATS["llm_calls"],
            "cache_hit_rate": round(hit_rate, 4),
            "co2_saved_g": round(_DAILY_STATS["co2_saved_g"], 4),
            "llm_baseline_co2_g": round(_current_llm_baseline_co2_g(), 4),
            "recent_events": list(_RECENT_EVENTS),
            "cache_candidates": [
                event
                for event in _RECENT_EVENTS
                if not event.get("cache_hit") and (event.get("similarity") or 0) >= 0.65
            ][:5],
        }


def record_daily_stats(result: dict[str, Any], *, query: str) -> dict[str, Any]:
    actual_co2_g = float(result.get("co2_grams") or 0.0)
    generation = result.get("generation") or {}
    generation_mode = generation.get("mode")

    with _STATS_LOCK:
        _reset_daily_stats_if_needed()
        _DAILY_STATS["total_requests"] += 1

        if generation_mode == "llm":
            _DAILY_STATS["llm_calls"] += 1

        if generation_mode == "llm" and actual_co2_g > 0:
            _DAILY_STATS["llm_samples"] += 1
            _DAILY_STATS["llm_co2_total_g"] += actual_co2_g

        baseline_co2_g = _current_llm_baseline_co2_g()
        if result.get("cache_hit"):
            _DAILY_STATS["cache_hits"] += 1
            _DAILY_STATS["co2_saved_g"] += max(baseline_co2_g - actual_co2_g, 0.0)

        total = _DAILY_STATS["total_requests"]
        cache_hits = _DAILY_STATS["cache_hits"]
        hit_rate = cache_hits / total if total else 0.0
        _RECENT_EVENTS.insert(
            0,
            {
                "query": query,
                "cache_hit": bool(result.get("cache_hit")),
                "mode": generation_mode,
                "similarity": result.get("similarity"),
                "latency_ms": result.get("latency_ms"),
                "co2_g": result.get("co2_grams"),
                "source": (result.get("retrieval") or {}).get("source"),
            },
        )
        del _RECENT_EVENTS[12:]

        return {
            "date": _DAILY_STATS["date"],
            "total_requests": total,
            "cache_hits": cache_hits,
            "llm_calls": _DAILY_STATS["llm_calls"],
            "cache_hit_rate": round(hit_rate, 4),
            "co2_saved_g": round(_DAILY_STATS["co2_saved_g"], 4),
            "llm_baseline_co2_g": round(baseline_co2_g, 4),
            "recent_events": list(_RECENT_EVENTS),
            "cache_candidates": [
                event
                for event in _RECENT_EVENTS
                if not event.get("cache_hit") and (event.get("similarity") or 0) >= 0.65
            ][:5],
        }


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _compact_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": source.get("rank"),
        "score": source.get("score"),
        "doc_id": source.get("doc_id"),
        "title": source.get("title"),
        "url": source.get("url"),
    }


def run_chat(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError("query 값이 비어 있습니다.")

    top_k = _as_int(payload.get("top_k"), config.TOP_K, minimum=1, maximum=10)
    threshold = _as_float(payload.get("threshold"), config.QA_SIMILARITY_THRESHOLD, minimum=0.0, maximum=1.0)
    lm_max_tokens = _as_int(payload.get("lm_max_tokens"), config.LM_MAX_TOKENS, minimum=32, maximum=2048)
    lm_timeout_seconds = _as_float(
        payload.get("lm_timeout_seconds"),
        config.LM_TIMEOUT_SECONDS,
        minimum=5.0,
        maximum=600.0,
    )
    use_llm = _as_bool(payload.get("use_llm"), True)
    generate = _as_bool(payload.get("generate"), True)
    measure_carbon = _as_bool(payload.get("measure_carbon"), True)
    selected_model = str(payload.get("selected_model") or "LM Studio(Local)").strip()
    carbon_intensity = _as_float(
        payload.get("carbon_intensity"),
        config.CARBON_INTENSITY_G_PER_KWH,
        minimum=0.0,
    )

    pipeline = get_cached_pipeline(
        top_k=top_k,
        threshold=threshold,
        lm_max_tokens=lm_max_tokens,
        lm_timeout_seconds=lm_timeout_seconds,
    )

    def execute_rag() -> dict[str, Any]:
        return pipeline.run(
            query,
            generate=generate,
            use_llm=use_llm,
        )

    carbon_metrics: dict[str, Any] | None = None
    if measure_carbon:
        monitor = CarbonMonitor(
            ci_value=carbon_intensity,
            enabled=True,
            gpu_index=config.CARBON_GPU_INDEX,
            sample_interval=config.CARBON_SAMPLE_INTERVAL,
            log_path=config.CARBON_LOG_PATH,
        )
        result, carbon_metrics = monitor.run(
            "web_chat_request",
            execute_rag,
            extra={
                "query": query,
                "top_k": top_k,
                "threshold": threshold,
                "use_llm": use_llm,
            },
        )
        result["co2_grams"] = carbon_metrics.get("co2_g")
        result["ci_g_per_kwh"] = carbon_intensity
        result["carbon_metrics"] = carbon_metrics
    else:
        result = execute_rag()

    generation = result.get("generation") or {}
    sources = [_compact_source(source) for source in result.get("sources", [])]
    similarity = result.get("cache_similarity") if result.get("cache_hit") else result.get("retrieval_similarity")
    stats = record_daily_stats(result, query=query)

    return {
        "response": result.get("answer"),
        "cache_hit": result.get("cache_hit"),
        "similarity": similarity,
        "cache_similarity": result.get("cache_similarity"),
        "retrieval_similarity": result.get("retrieval_similarity"),
        "latency": result.get("latency_ms"),
        "co2_grams": result.get("co2_grams"),
        "ci_g_per_kwh": result.get("ci_g_per_kwh"),
        "avg_power_W": (carbon_metrics or {}).get("avg_power_W"),
        "peak_power_W": (carbon_metrics or {}).get("peak_power_W"),
        "energy_kwh": (carbon_metrics or {}).get("energy_kwh"),
        "generation_mode": generation.get("mode"),
        "model": generation.get("model"),
        "selected_model": selected_model,
        "generation_error": generation.get("error"),
        "source": (result.get("retrieval") or {}).get("source"),
        "threshold": threshold,
        "top_k": top_k,
        "sources": sources,
        "stats": stats,
    }


class EcoCacheRequestHandler(BaseHTTPRequestHandler):
    server_version = "EcoCacheWeb/1.0"

    def do_OPTIONS(self) -> None:
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if self.path in {"/admin", "/admin.html"}:
            self._send_file(WEB_DIR / "admin.html", "text/html; charset=utf-8")
            return
        if self.path == "/stats":
            self._send_json({"ok": True, "stats": get_daily_stats()})
            return
        static_path = self._resolve_static_path()
        if static_path is not None:
            content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
            self._send_file(static_path, content_type)
            return

        self._send_json({"ok": False, "error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/chat":
            self._send_json({"ok": False, "error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body or "{}")
            result = run_chat(payload)
            self._send_json({"ok": True, "result": result})
        except Exception as error:
            self._send_json(
                {"ok": False, "error": str(error)},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} - {format % args}")

    def _send_empty(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self._send_common_headers()
        self.end_headers()

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"ok": False, "error": f"Missing file: {path}"}, status=HTTPStatus.NOT_FOUND)
            return

        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._send_common_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _resolve_static_path(self) -> Path | None:
        request_path = unquote(urlparse(self.path).path)
        if not request_path.startswith("/assets/"):
            return None

        web_root = WEB_DIR.resolve()
        static_path = (WEB_DIR / request_path.lstrip("/")).resolve()
        try:
            static_path.relative_to(web_root)
        except ValueError:
            return None
        if not static_path.is_file():
            return None
        return static_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the EcoCache web demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), EcoCacheRequestHandler)
    print(f"EcoCache web demo: http://{args.host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
