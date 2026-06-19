"""
CIASC 그리드 스윕 평가 스크립트

alpha_base × CI 조합별 캐시 히트율·CO₂·정확도를 측정하고 .md 리포트를 생성한다.

사용법:
  python grid_eval.py [OPTIONS]
    --alpha-list  콤마 구분 alpha 값 (기본: 0.10,0.15,0.20,0.25)
    --ci-list     콤마 구분 CI 값 (기본: 350,380,420,460,500)
    --test-file   쿼리 JSON 경로 (기본: ../test_queries.json)
    --output-dir  리포트 출력 디렉토리 (기본: ../docs/eval_reports)
    --log-dir     JSONL 로그 디렉토리 (기본: logs/grid)
    --no-report   리포트 생성 스킵
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# rag/ 디렉토리에서 실행하므로 sys.path 조작 불필요
import config
from baseline_ciasc import CIASCRetriever

# ── 스윕 상수 ───────────────────────────────────────────────────────────────
ALPHA_BASE_SWEEP: list[float] = [0.10, 0.15, 0.20, 0.25]
CI_SWEEP: list[int] = [350, 380, 420, 460, 500]
K_FIXED: float = 0.5

# ── ASCII 히트맵 기호 ────────────────────────────────────────────────────────
_HEATMAP_LEVELS = [
    (0.80, "█"),
    (0.60, "▓"),
    (0.40, "▒"),
    (0.20, "░"),
    (0.00, "·"),
]


# @MX:ANCHOR: [AUTO] GridResult is referenced by run_grid_sweep and generate_report callers
# @MX:REASON: Central data contract shared across sweep execution, report generation, and JSONL logging
@dataclass
class GridResult:
    """단일 (alpha_base, CI) 조합의 집계 결과."""

    alpha_base: float
    ci: int
    alpha_computed: float  # 중립 CI 기준 평균 alpha
    threshold: float       # 평균 θ(t)
    cache_hit_rate: float  # qa_pairs 히트 비율 [0, 1]
    total_co2_mg: float    # 전체 CO₂ (밀리그램)
    avg_top1_score: float  # top-1 유사도 평균
    avg_latency_ms: float  # 평균 지연 (ms)
    n_queries: int         # 처리한 쿼리 수


# @MX:ANCHOR: [AUTO] run_grid_sweep is the primary entry-point for all grid experiments
# @MX:REASON: Called from main() and expected to be called by downstream analysis scripts (fan_in >= 3)
def run_grid_sweep(
    alpha_list: list[float],
    ci_list: list[int],
    test_queries: list[dict],
    log_dir: Path,
) -> list[GridResult]:
    """alpha_base × CI 전체 조합을 순차 실행하고 GridResult 목록을 반환한다.

    각 조합마다 JSONL 로그를 ``log_dir/alpha{A}_ci{CI}_eval.jsonl`` 에 기록한다.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    total_combos = len(alpha_list) * len(ci_list)
    combo_idx = 0
    results: list[GridResult] = []

    for alpha_base in alpha_list:
        for ci in ci_list:
            combo_idx += 1
            log_path = log_dir / f"alpha{alpha_base}_ci{ci}_eval.jsonl"

            hit_count = 0
            total_co2_g = 0.0
            top1_scores: list[float] = []
            latencies_ms: list[float] = []
            alpha_computed_vals: list[float] = []
            threshold_vals: list[float] = []

            for query_item in test_queries:
                query_id = query_item.get("id", "")
                query_text = query_item.get("query", "")

                # CI를 시뮬레이션: config 패치 방식
                config.CIASC_FIXED_CI = float(ci)

                retriever = CIASCRetriever(alpha=alpha_base, k=K_FIXED)

                # alpha 및 threshold 수동 계산 (더 안전한 fallback)
                alpha_computed = retriever._calculate_dynamic_alpha(float(ci))
                ci_norm = max(
                    0.0,
                    min(
                        1.0,
                        (ci - config.CIASC_CI_MIN)
                        / (config.CIASC_CI_MAX - config.CIASC_CI_MIN),
                    ),
                )
                raw_theta = (
                    config.CIASC_BASE_THRESHOLD - alpha_computed * (ci_norm - 0.5)
                )
                threshold = max(
                    config.CIASC_THETA_MIN,
                    min(config.CIASC_THETA_MAX, raw_theta),
                )
                # config에 threshold 적용 (retrieve 내부에서도 참조)
                config.QA_SIMILARITY_THRESHOLD = threshold

                alpha_computed_vals.append(alpha_computed)
                threshold_vals.append(threshold)

                t_start = time.perf_counter()
                try:
                    result = retriever.retrieve(query_text)
                except Exception as exc:  # Qdrant 미연결 등 graceful 처리
                    print(
                        f"  [경고] {query_id} 검색 실패: {exc!r}",
                        file=sys.stderr,
                    )
                    result = {
                        "source": "documents",
                        "results": [],
                        "query": query_text,
                        "qa_top1_score": None,
                        "alpha_used": alpha_computed,
                        "timings": [],
                    }
                latency_ms = (time.perf_counter() - t_start) * 1000

                source = result.get("source", "documents")
                results_list = result.get("results", [])
                top1_score = results_list[0]["score"] if results_list else 0.0
                qa_top1_score = result.get("qa_top1_score")
                cache_hit = source == "qa_pairs"

                # CO₂: carbon_monitor metrics (없으면 0.0)
                carbon_metrics = result.get("metrics", {})
                co2_g = sum(
                    v.get("co2_g", 0.0)
                    for v in carbon_metrics.values()
                    if isinstance(v, dict)
                )

                if cache_hit:
                    hit_count += 1
                total_co2_g += co2_g
                top1_scores.append(top1_score)
                latencies_ms.append(latency_ms)

                # JSONL 로그 기록
                log_entry: dict = {
                    "alpha_base": alpha_base,
                    "ci_simulated": ci,
                    "k": K_FIXED,
                    "alpha_computed": round(alpha_computed, 6),
                    "threshold": round(threshold, 6),
                    "query_id": query_id,
                    "query": query_text,
                    "source": source,
                    "cache_hit": cache_hit,
                    "top1_score": round(top1_score, 6),
                    "qa_top1_score": (
                        round(qa_top1_score, 6) if qa_top1_score is not None else None
                    ),
                    "co2_g": co2_g,
                    "latency_ms": round(latency_ms, 2),
                }
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            n = len(test_queries)
            hit_rate = hit_count / n if n else 0.0
            avg_alpha = sum(alpha_computed_vals) / len(alpha_computed_vals) if alpha_computed_vals else alpha_base
            avg_threshold = sum(threshold_vals) / len(threshold_vals) if threshold_vals else config.CIASC_BASE_THRESHOLD
            avg_top1 = sum(top1_scores) / len(top1_scores) if top1_scores else 0.0
            avg_lat = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0

            grid_result = GridResult(
                alpha_base=alpha_base,
                ci=ci,
                alpha_computed=round(avg_alpha, 6),
                threshold=round(avg_threshold, 6),
                cache_hit_rate=round(hit_rate, 4),
                total_co2_mg=round(total_co2_g * 1000, 6),
                avg_top1_score=round(avg_top1, 4),
                avg_latency_ms=round(avg_lat, 2),
                n_queries=n,
            )
            results.append(grid_result)

            print(
                f"[{combo_idx}/{total_combos}] alpha={alpha_base:.2f} CI={ci}"
                f" → hit_rate={hit_rate*100:.1f}%"
                f" CO₂={total_co2_g*1000:.3f}mg"
            )

    # config 패치 정리
    config.CIASC_FIXED_CI = None

    return results


def _heatmap_char(rate: float) -> str:
    """히트율을 ASCII 히트맵 기호로 변환."""
    for threshold, char in _HEATMAP_LEVELS:
        if rate >= threshold:
            return char
    return "·"


# @MX:ANCHOR: [AUTO] generate_report is called by main() and integration scripts
# @MX:REASON: Produces the final .md artifact consumed by paper writing and result review
def generate_report(
    results: list[GridResult],
    output_path: Path,
    baseline_log_dir: Path | None = None,
) -> None:
    """GridResult 목록으로부터 마크다운 리포트를 생성한다.

    섹션: 실험 설정 | 히트율 표 | CO₂ 표 | ASCII 히트맵 | 최적 조합 요약 | (선택) B1/B2 비교
    """
    if not results:
        print("[경고] 결과 없음 — 리포트 생성 스킵", file=sys.stderr)
        return

    alpha_list = sorted({r.alpha_base for r in results})
    ci_list = sorted({r.ci for r in results})

    # 색인 생성
    result_map: dict[tuple[float, int], GridResult] = {
        (r.alpha_base, r.ci): r for r in results
    }

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines.append("# CIASC 그리드 스윕 평가 리포트\n")
    lines.append(f"생성 시각: {now_str}\n")

    # ── 실험 설정 ──────────────────────────────────────────────────────────
    lines.append("## 실험 설정\n")
    lines.append(f"- alpha_base 범위: {alpha_list}")
    lines.append(f"- CI 범위 (gCO₂/kWh): {ci_list}")
    lines.append(f"- k (고정): {K_FIXED}")
    lines.append(f"- 기준 임계값 (θ_base): {config.CIASC_BASE_THRESHOLD}")
    lines.append(f"- θ 허용 범위: [{config.CIASC_THETA_MIN}, {config.CIASC_THETA_MAX}]")
    lines.append(f"- 쿼리 수 (per cell): {results[0].n_queries if results else 0}")
    lines.append("")

    # ── 히트율 표 ──────────────────────────────────────────────────────────
    lines.append("## 캐시 히트율 (%)\n")
    header_ci = " | ".join(f"CI={c}" for c in ci_list)
    lines.append(f"| alpha \\ CI | {header_ci} |")
    lines.append("|" + "---|" * (len(ci_list) + 1))
    for alpha in alpha_list:
        row_cells = []
        for ci in ci_list:
            r = result_map.get((alpha, ci))
            cell = f"{r.cache_hit_rate*100:.1f}%" if r else "—"
            row_cells.append(cell)
        lines.append(f"| {alpha:.2f} | " + " | ".join(row_cells) + " |")
    lines.append("")

    # ── CO₂ 표 ──────────────────────────────────────────────────────────
    lines.append("## 총 CO₂ (mg)\n")
    lines.append(f"| alpha \\ CI | {header_ci} |")
    lines.append("|" + "---|" * (len(ci_list) + 1))
    for alpha in alpha_list:
        row_cells = []
        for ci in ci_list:
            r = result_map.get((alpha, ci))
            cell = f"{r.total_co2_mg:.4f}" if r else "—"
            row_cells.append(cell)
        lines.append(f"| {alpha:.2f} | " + " | ".join(row_cells) + " |")
    lines.append("")

    # ── ASCII 히트맵 ──────────────────────────────────────────────────────
    lines.append("## ASCII 히트맵 (캐시 히트율)\n")
    lines.append("```")
    lines.append("범례: ≥80%=█  60-80%=▓  40-60%=▒  20-40%=░  <20%=·")
    lines.append("")
    # 헤더 행
    ci_header = "  ".join(f"CI{c}" for c in ci_list)
    lines.append(f"α\\CI   {ci_header}")
    for alpha in alpha_list:
        row_chars = []
        for ci in ci_list:
            r = result_map.get((alpha, ci))
            row_chars.append(_heatmap_char(r.cache_hit_rate if r else 0.0))
        lines.append(f"{alpha:.2f}   " + "     ".join(row_chars))
    lines.append("```")
    lines.append("")

    # ── 최적 조합 요약 ────────────────────────────────────────────────────
    lines.append("## 최적 조합 요약\n")

    # 히트율 최고
    best_hit = max(results, key=lambda r: r.cache_hit_rate)
    lines.append(
        f"- **히트율 최고**: α={best_hit.alpha_base:.2f}, CI={best_hit.ci}"
        f" → {best_hit.cache_hit_rate*100:.1f}%"
    )

    # CO₂ 최소 (히트율 ≥ 30% 조건)
    co2_candidates = [r for r in results if r.cache_hit_rate >= 0.30]
    if co2_candidates:
        best_co2 = min(co2_candidates, key=lambda r: r.total_co2_mg)
        lines.append(
            f"- **CO₂ 최소** (히트율 ≥30%): α={best_co2.alpha_base:.2f}, CI={best_co2.ci}"
            f" → {best_co2.total_co2_mg:.4f} mg"
        )
    else:
        lines.append("- **CO₂ 최소** (히트율 ≥30%): 조건 만족 조합 없음")

    # 균형점: 히트율 / CO₂ 비율 최대 (CO₂ > 0 인 경우만)
    balance_candidates = [r for r in results if r.total_co2_mg > 0]
    if balance_candidates:
        best_balance = max(
            balance_candidates,
            key=lambda r: r.cache_hit_rate / r.total_co2_mg,
        )
        lines.append(
            f"- **균형점** (히트율/CO₂ 비율): α={best_balance.alpha_base:.2f},"
            f" CI={best_balance.ci}"
            f" → 비율={best_balance.cache_hit_rate/best_balance.total_co2_mg:.2f}"
        )
    lines.append("")

    # ── 전체 결과 상세 ────────────────────────────────────────────────────
    lines.append("## 전체 결과 상세\n")
    lines.append(
        "| alpha | CI | α_computed | θ | hit_rate | CO₂(mg) | avg_top1 | avg_lat(ms) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.alpha_base:.2f} | {r.ci}"
            f" | {r.alpha_computed:.4f} | {r.threshold:.4f}"
            f" | {r.cache_hit_rate*100:.1f}%"
            f" | {r.total_co2_mg:.4f}"
            f" | {r.avg_top1_score:.4f}"
            f" | {r.avg_latency_ms:.1f} |"
        )
    lines.append("")

    # ── (선택) B1/B2 비교 ────────────────────────────────────────────────
    if baseline_log_dir and baseline_log_dir.exists():
        b_rows: list[dict] = []
        for label, log_name in [
            ("B1 (No Cache)", "b1_eval_log.jsonl"),
            ("B2 (Static θ=0.90)", "b2_eval_log.jsonl"),
        ]:
            lp = baseline_log_dir / log_name
            if not lp.exists():
                continue
            entries = [
                json.loads(line)
                for line in lp.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not entries:
                continue
            total = len(entries)
            hits = sum(1 for e in entries if e.get("source") == "qa_pairs")
            scores = [
                e["results"][0]["score"]
                for e in entries
                if e.get("results")
            ]
            avg_top1 = sum(scores) / len(scores) if scores else 0.0
            total_co2_mg = (
                sum(
                    v.get("co2_g", 0.0)
                    for e in entries
                    for v in e.get("carbon_metrics", {}).values()
                    if isinstance(v, dict)
                )
                * 1000
            )
            b_rows.append(
                {
                    "label": label,
                    "hit_rate": f"{hits/total*100:.1f}%",
                    "co2_mg": f"{total_co2_mg:.4f}",
                    "avg_top1": f"{avg_top1:.4f}",
                }
            )

        if b_rows:
            lines.append("## 베이스라인 비교\n")
            lines.append("| 설정 | 히트율 | CO₂(mg) | avg_top1 |")
            lines.append("|---|---|---|---|")
            for row in b_rows:
                lines.append(
                    f"| {row['label']} | {row['hit_rate']}"
                    f" | {row['co2_mg']} | {row['avg_top1']} |"
                )
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[리포트] {output_path}")


def main() -> None:
    # @MX:NOTE: [AUTO] argparse defaults mirror ALPHA_BASE_SWEEP / CI_SWEEP constants above
    parser = argparse.ArgumentParser(
        description="CIASC alpha_base × CI 그리드 스윕 평가"
    )
    parser.add_argument(
        "--alpha-list",
        default=",".join(str(a) for a in ALPHA_BASE_SWEEP),
        help="콤마 구분 alpha 값 (기본: 0.10,0.15,0.20,0.25)",
    )
    parser.add_argument(
        "--ci-list",
        default=",".join(str(c) for c in CI_SWEEP),
        help="콤마 구분 CI 값 (기본: 350,380,420,460,500)",
    )
    parser.add_argument(
        "--test-file",
        default="../test_queries.json",
        help="쿼리 JSON 경로",
    )
    parser.add_argument(
        "--output-dir",
        default="../docs/eval_reports",
        help="리포트 출력 디렉토리",
    )
    parser.add_argument(
        "--log-dir",
        default="logs/grid",
        help="JSONL 로그 디렉토리",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="리포트 생성 스킵",
    )
    args = parser.parse_args()

    try:
        alpha_list = [float(a.strip()) for a in args.alpha_list.split(",") if a.strip()]
        ci_list = [int(c.strip()) for c in args.ci_list.split(",") if c.strip()]
    except ValueError as exc:
        print(f"[오류] alpha/CI 파싱 실패: {exc}", file=sys.stderr)
        sys.exit(1)

    test_file = Path(args.test_file)
    if not test_file.exists():
        print(f"[오류] 테스트 파일 없음: {test_file}", file=sys.stderr)
        sys.exit(1)

    test_queries: list[dict] = json.loads(test_file.read_text(encoding="utf-8"))
    log_dir = Path(args.log_dir)
    output_dir = Path(args.output_dir)

    total_combos = len(alpha_list) * len(ci_list)
    print("\n=== CIASC 그리드 스윕 시작 ===")
    print(f"  alpha 범위 : {alpha_list}")
    print(f"  CI 범위    : {ci_list}")
    print(f"  총 조합    : {total_combos}")
    print(f"  쿼리 수    : {len(test_queries)}")
    print(f"  로그 디렉토리: {log_dir}")
    print()

    results = run_grid_sweep(alpha_list, ci_list, test_queries, log_dir)

    if not args.no_report:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"grid_sweep_{timestamp}.md"
        # 베이스라인 로그가 있으면 logs/ 를 기준으로 탐색
        baseline_log_dir = Path("logs")
        generate_report(results, report_path, baseline_log_dir=baseline_log_dir)
        print(f"\n리포트 위치: {report_path.resolve()}")
    else:
        print("\n[리포트 생성 스킵]")

    print("\n=== 그리드 스윕 완료 ===")


if __name__ == "__main__":
    main()
