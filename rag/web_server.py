from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import config
from carbon_monitor import CarbonMonitor
from rag.langchain_pipeline import get_cached_pipeline


BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"


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
        "generation_error": generation.get("error"),
        "source": (result.get("retrieval") or {}).get("source"),
        "threshold": threshold,
        "top_k": top_k,
        "sources": sources,
    }


class EcoCacheRequestHandler(BaseHTTPRequestHandler):
    server_version = "EcoCacheWeb/1.0"

    def do_OPTIONS(self) -> None:
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
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
