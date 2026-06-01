"""
EcoCache 배치 평가 스크립트

사용법:
  python run_eval.py --mode b1               # B1: 캐시 없음 (Pure RAG)
  python run_eval.py --mode b2               # B2: 정적 캐시 (θ=0.90)
  python run_eval.py --mode ciasc            # CIASC: CI 연동 동적 θ
  python run_eval.py --alpha 0.5 --mode ciasc
  python run_eval.py --summary-only --log-file logs/b1_eval_log.jsonl
  python run_eval.py --compare               # b1/b2/ciasc 비교 표
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import config
from query import log_result, rag_search

_CARBON_DIR = str(Path(__file__).parent.parent / "carbon")
if _CARBON_DIR not in sys.path:
    sys.path.insert(0, _CARBON_DIR)

try:
    from collector import get_latest_ci_from_db
    from carbon_optimizer import get_optimizer
except ImportError:
    get_latest_ci_from_db = None  # type: ignore[assignment]
    get_optimizer = None          # type: ignore[assignment]

MODES = {
    "b1": {
        "label":      "B1 (No Cache / Pure RAG)",
        "threshold":  1.1,
        "log_suffix": "b1",
    },
    "b2": {
        "label":      "B2 (Static Cache θ=0.90)",
        "threshold":  0.90,
        "log_suffix": "b2",
    },
    "ciasc": {
        "label":      "CIASC (CI-Adaptive)",
        "threshold":  None,
        "log_suffix": "ciasc",
    },
}


def _get_ciasc_threshold(alpha: float = 0.15) -> float:
    if get_latest_ci_from_db is None or get_optimizer is None:
        print("  [CIASC] carbon 모듈 없음 → fallback θ=0.7375")
        return 0.7375
    ci = get_latest_ci_from_db()
    if ci is None:
        ci = get_optimizer().get_current_ci()
        print("  [CIASC] DB에 CI 없음 → optimizer fallback")
        theta = get_optimizer().get_adaptive_threshold(ci=ci, alpha=alpha)
    else:
        ci_range = config.CIASC_CI_MAX - config.CIASC_CI_MIN
        ci_norm  = 0.0 if ci_range == 0 else (ci - config.CIASC_CI_MIN) / ci_range
        ci_norm  = max(0.0, min(1.0, ci_norm))
        raw      = config.CIASC_BASE_THRESHOLD - (alpha * (ci_norm - 0.5))
        theta    = round(max(config.CIASC_THETA_MIN, min(config.CIASC_THETA_MAX, raw)), 4)
    print(f"  [CIASC] CI={ci:.0f} gCO2/kWh, α={alpha} → θ(t)={theta:.4f}")
    return theta


def apply_mode(mode: str, alpha: float = 0.15) -> float:
    cfg       = MODES[mode]
    threshold = _get_ciasc_threshold(alpha=alpha) if mode == "ciasc" else cfg["threshold"]
    config.QA_SIMILARITY_THRESHOLD = threshold
    return threshold


def _extract_ids(result: dict) -> list[str]:
    ids = []
    for r in result["results"]:
        p = r["payload"]
        for key in ("doc_id", "source_doc_id", "qa_id"):
            val = p.get(key)
            if val:
                ids.append(val)
    return ids


def run_eval(
    test_file: Path,
    log_file: Path,
    category_filter: str | None = None,
    mode: str = "b2",
    alpha: float = 0.15,
) -> list[dict]:
    tests = json.loads(test_file.read_text(encoding="utf-8"))
    if category_filter:
        tests = [t for t in tests if t.get("category") == category_filter]
        if not tests:
            print(f"[경고] '{category_filter}' 카테고리 질문 없음")
            return []

    mode_label = MODES[mode]["label"]
    threshold  = apply_mode(mode, alpha=alpha)

    print(f"\n{'='*60}")
    print(f" EcoCache 평가 실행")
    print(f" 모드    : {mode_label}")
    print(f" 임계값  : {threshold:.4f}")
    print(f" 질문 수 : {len(tests)} | 로그: {log_file}")
    if category_filter:
        print(f" 카테고리 필터: {category_filter}")
    print(f"{'='*60}\n")

    records          = []
    total_co2_g      = 0.0
    total_latency_ms = 0.0
    cache_hits       = 0

    for idx, test in enumerate(tests, 1):
        tid      = test["id"]
        query    = test["query"]
        expected = test.get("expected_source", "either")
        exp_docs = test.get("expected_doc_ids", [])

        print(f"[{idx:02d}/{len(tests)}] {tid} ({test.get('category', '')}) — {query[:50]}")

        t_start    = time.perf_counter()
        result     = rag_search(query, mode=mode)
        latency_ms = (time.perf_counter() - t_start) * 1000

        log_result(result, log_file=log_file, mode=mode)

        carbon_metrics = result.get("metrics", {})
        query_co2_g = sum(
            v.get("co2_g", 0.0)
            for v in carbon_metrics.values()
            if isinstance(v, dict)
        )
        total_co2_g      += query_co2_g
        total_latency_ms += latency_ms

        hit_source   = result["source"] == expected or expected == "either"
        returned_ids = _extract_ids(result)
        hit_doc      = any(d in returned_ids for d in exp_docs) if exp_docs else None
        top1_score   = result["results"][0]["score"] if result["results"] else 0.0

        if result["source"] == "qa_pairs":
            cache_hits += 1

        status  = "✓" if (hit_source and (hit_doc is None or hit_doc)) else "✗"
        qa_str  = f"  (QA top1={result['qa_top1_score']:.4f})" if result.get("qa_top1_score") else ""
        co2_str = f"  CO2={query_co2_g*1000:.3f}mg" if query_co2_g else ""
        print(f"  {status} source={result['source']} top1={top1_score:.4f}"
              f"  latency={latency_ms:.0f}ms{qa_str}{co2_str}")

        if exp_docs and not hit_doc:
            print(f"  ⚠ 예상 doc_id 미포함: {exp_docs}")

        records.append({
            "mode":       mode,
            "threshold":  threshold,
            "test":       test,
            "result":     result,
            "hit_source": hit_source,
            "hit_doc":    hit_doc,
            "top1_score": top1_score,
            "latency_ms": latency_ms,
            "co2_g":      query_co2_g,
        })

    total    = len(records)
    hit_rate = cache_hits / total * 100 if total else 0
    avg_lat  = total_latency_ms / total if total else 0
    print(f"\n {'─'*40}")
    print(f"  모드        : {mode_label}")
    print(f"  캐시 히트율 : {cache_hits}/{total} ({hit_rate:.1f}%)")
    print(f"  총 CO2      : {total_co2_g*1000:.3f} mg  ({total_co2_g:.6f} g)")
    print(f"  평균 지연   : {avg_lat:.0f} ms")
    print(f" {'─'*40}")

    return records


def print_summary(records: list[dict], mode: str) -> None:
    if not records:
        return
    total      = len(records)
    src_hits   = sum(1 for r in records if r["hit_source"])
    doc_eval   = [r for r in records if r["hit_doc"] is not None]
    doc_hits   = sum(1 for r in doc_eval if r["hit_doc"])
    avg_top1   = sum(r["top1_score"] for r in records) / total
    cache_hits = sum(1 for r in records if r["result"]["source"] == "qa_pairs")
    total_co2  = sum(r["co2_g"] for r in records)
    avg_lat    = sum(r["latency_ms"] for r in records) / total

    by_cat: dict[str, list[float]] = {}
    for r in records:
        cat = r["test"].get("category", "unknown")
        by_cat.setdefault(cat, []).append(r["top1_score"])

    print(f"\n{'='*60}")
    print(f" 평가 요약 — {MODES[mode]['label']}")
    print(f"{'='*60}")
    print(f" 총 질문 수     : {total}")
    print(f" Source 정확도  : {src_hits}/{total} ({src_hits/total*100:.1f}%)")
    if doc_eval:
        print(f" Doc Hit율      : {doc_hits}/{len(doc_eval)} ({doc_hits/len(doc_eval)*100:.1f}%)")
    print(f" 캐시 히트율    : {cache_hits}/{total} ({cache_hits/total*100:.1f}%)")
    print(f" Top-1 유사도   : 평균 {avg_top1:.4f}")
    print(f" 총 CO2         : {total_co2*1000:.3f} mg  ({total_co2:.6f} g)")
    print(f" 평균 지연      : {avg_lat:.0f} ms")
    print()
    print(" [카테고리별 Top-1 평균]")
    for cat, scores in sorted(by_cat.items()):
        print(f"  {cat:<25} {sum(scores)/len(scores):.4f}  (n={len(scores)})")
    print(f"{'='*60}")

    failures = [r for r in records
                if not r["hit_source"] or (r["hit_doc"] is not None and not r["hit_doc"])]
    if failures:
        print("\n [실패 케이스]")
        for r in failures:
            t = r["test"]
            print(f"  {t['id']} | {t.get('category','')} | {t['query'][:55]}")
            print(f"    expected={t.get('expected_source')}  got={r['result']['source']}"
                  f"  top1={r['top1_score']:.4f}")
    print()


def print_comparison(base_dir: Path = Path(".")) -> None:
    rows = []
    for mode, cfg in MODES.items():
        log_path = base_dir / f"{cfg['log_suffix']}_eval_log.jsonl"
        if not log_path.exists():
            continue
        entries = [
            json.loads(l)
            for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        if not entries:
            continue
        total      = len(entries)
        cache_hits = sum(1 for e in entries if e.get("source") == "qa_pairs")
        scores     = [e["results"][0]["score"] for e in entries if e.get("results")]
        avg_top1   = sum(scores) / len(scores) if scores else 0.0
        total_co2  = sum(
            v.get("co2_g", 0.0)
            for e in entries
            for v in e.get("carbon_metrics", {}).values()
            if isinstance(v, dict)
        )
        rows.append({
            "label":    cfg["label"],
            "accuracy": f"{avg_top1:.2f}",
            "co2_g":    f"{total_co2:.4f}",
            "hit_rate": f"{cache_hits/total*100:.1f}%",
        })

    if not rows:
        print("[비교] 로그 없음 — 먼저 --mode b1/b2/ciasc 로 평가를 실행하세요.")
        return

    print(f"\n{'='*60}")
    print(f" 논문 표 1 비교")
    print(f"{'='*60}")
    print(f"  {'설정':<28} {'정확도':>8} {'탄소(g)':>10} {'히트율':>8}")
    print(f"  {'─'*56}")
    for r in rows:
        print(f"  {r['label']:<28} {r['accuracy']:>8} {r['co2_g']:>10} {r['hit_rate']:>8}")
    print(f"{'='*60}\n")


def summarize_log(log_file: Path) -> None:
    if not log_file.exists():
        print(f"[오류] 파일 없음: {log_file}")
        return
    entries = [
        json.loads(line)
        for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not entries:
        print("로그 항목 없음")
        return

    print(f"\n{'='*60}")
    print(f" 로그 분석: {log_file}  ({len(entries)}건)")
    print(f"{'='*60}")

    groups: dict[str, list] = {}
    for e in entries:
        key = (
            e["config"]["embed_model"],
            e["config"]["qa_similarity_threshold"],
            e["config"]["chunk_size"],
        )
        groups.setdefault(str(key), []).append(e)

    for _, group in groups.items():
        cfg    = group[0]["config"]
        total  = len(group)
        qa_cnt = sum(1 for e in group if e["source"] == "qa_pairs")
        scores = [e["results"][0]["score"] for e in group if e["results"]]
        avg    = sum(scores) / len(scores) if scores else 0.0
        qa_sc  = [e["qa_top1_score"] for e in group if e.get("qa_top1_score") is not None]
        avg_qa = sum(qa_sc) / len(qa_sc) if qa_sc else 0.0

        print(f"\n 모델  : {cfg['embed_model']}")
        print(f" 임계값: {cfg['qa_similarity_threshold']}  청크: {cfg['chunk_size']}  top_k: {cfg['top_k']}")
        print(f" 질문 수: {total}  →  qa_pairs: {qa_cnt}  documents: {total - qa_cnt}")
        print(f" Top-1 유사도 평균: {avg:.4f}  QA top1 평균: {avg_qa:.4f}")
    print(f"\n{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EcoCache 배치 평가")
    parser.add_argument("--mode", default="b2", choices=["b1", "b2", "ciasc"])
    parser.add_argument("--test-file",    default="../test_queries.json")
    parser.add_argument("--log-file",     default=None)
    parser.add_argument("--category",     default=None)
    parser.add_argument("--alpha",        type=float, default=0.15)
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--compare",      action="store_true")
    args = parser.parse_args()

    if args.log_file:
        log_path = Path(args.log_file)
    elif args.mode == "ciasc":
        log_path = Path(f"logs/ciasc_alpha{args.alpha}_eval_log.jsonl")
    else:
        log_path = Path(f"logs/{args.mode}_eval_log.jsonl")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    test_path = Path(args.test_file)

    if args.compare:
        print_comparison(log_path.parent)
        sys.exit(0)

    if args.summary_only:
        summarize_log(log_path)
        sys.exit(0)

    if not test_path.exists():
        print(f"[오류] 테스트 파일 없음: {test_path}")
        sys.exit(1)

    records = run_eval(test_path, log_path,
                       category_filter=args.category,
                       mode=args.mode, alpha=args.alpha)
    print_summary(records, args.mode)
    summarize_log(log_path)
