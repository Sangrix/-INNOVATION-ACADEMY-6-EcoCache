"""
EcoCache 임베딩 성능 평가 스크립트

test_queries.json의 질문 세트를 일괄 실행하고
결과를 eval_log.jsonl에 기록 + 콘솔 요약 출력.

사용법:
  python run_eval.py                          # 기본 (B2 모드, test_queries.json 전체)
  python run_eval.py --mode b1               # B1: 캐시 없음
  python run_eval.py --mode b2               # B2: 정적 캐시 (θ=0.90)
  python run_eval.py --mode ciasc            # CIASC: CI 연동 동적 θ
  python run_eval.py --category exact_match  # 카테고리 필터
  python run_eval.py --log-file my_run.jsonl # 출력 파일 지정
  python run_eval.py --summary-only          # 기존 로그 파일 요약만 출력

모드별 동작:
  b1    QA_SIMILARITY_THRESHOLD=1.1 → 캐시 히트 불가 → 항상 documents fallback
  b2    QA_SIMILARITY_THRESHOLD=0.90 고정
  ciasc 민상님 CI 연동 모듈로 θ(t)를 동적으로 결정 (config.CIASC_* 설정 참고)
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import config
import query as Q
from query import log_result, rag_search

# ── 모드 설정 ─────────────────────────────────────────────────────────────────

MODES = {
    "b1": {
        "label": "B1 (No Cache)",
        "threshold": 1.1,       # 사실상 캐시 비활성 — 어떤 QA도 히트 불가
        "log_suffix": "b1",
    },
    "b2": {
        "label": "B2 (Static Cache θ=0.90)",
        "threshold": 0.90,
        "log_suffix": "b2",
    },
    "ciasc": {
        "label": "CIASC (CI-Adaptive)",
        "threshold": None,      # 동적 결정 — _get_ciasc_threshold() 사용
        "log_suffix": "ciasc",
    },
}

def _get_ciasc_threshold(alpha: float = 0.15) -> float:
    """
    민상님 carbon_optimizer.py의 CarbonAdaptiveOptimizer를 통해
    현재 한국 시간 기준 CI를 조회하고 θ(t)를 동적으로 반환합니다.

    수식: θ = 0.75 − alpha × (ci_norm − 0.5)
    ci_norm = clamp((CI − 350) / 150, 0, 1)
    범위: [0.70, 0.95]
    """
    try:
        from carbon_optimizer import get_optimizer
        opt   = get_optimizer()
        ci    = opt.get_current_ci()
        theta = opt.get_adaptive_threshold(alpha=alpha)
        print(f"  [CIASC] 현재 CI={ci:.0f} gCO2/kWh, α={alpha} → θ(t)={theta:.4f}")
        return theta
    except ImportError:
        print("  [CIASC] ⚠ carbon_optimizer 모듈 없음 → fallback θ=0.7375 사용")
        return 0.7375


def apply_mode(mode: str, alpha: float = 0.15) -> float:
    """
    모드에 맞게 config.QA_SIMILARITY_THRESHOLD를 덮어쓰고
    실제 적용된 threshold를 반환합니다.
    """
    cfg = MODES[mode]
    if mode == "ciasc":
        threshold = _get_ciasc_threshold(alpha=alpha)
    else:
        threshold = cfg["threshold"]

    config.QA_SIMILARITY_THRESHOLD = threshold
    Q.config.QA_SIMILARITY_THRESHOLD = threshold
    return threshold


# ── 평가 실행 ─────────────────────────────────────────────────────────────────

def run_eval(test_file: Path, log_file: Path,
             category_filter: str | None = None,
             mode: str = "b2",
             alpha: float = 0.15) -> list[dict]:
    """test_queries.json을 읽어 전체 실행, 결과 반환."""
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

    records = []
    total_co2_g  = 0.0
    total_latency_ms = 0.0
    cache_hits   = 0

    for i, test in enumerate(tests, 1):
        tid      = test["id"]
        query    = test["query"]
        expected = test.get("expected_source", "either")
        exp_docs = test.get("expected_doc_ids", [])

        # CIASC는 질문마다 θ(t) 재계산
        if mode == "ciasc":
            threshold = apply_mode("ciasc", alpha=alpha)

        print(f"[{i:02d}/{len(tests)}] {tid} ({test.get('category','')}) — {query[:50]}")

        t_start = time.perf_counter()
        result  = rag_search(query)
        latency_ms = (time.perf_counter() - t_start) * 1000

        log_result(result, log_file=log_file)

        # 탄소 수집 (carbon_monitor가 result에 metrics를 붙여주는 경우)
        carbon_metrics = result.get("metrics") or result.get("carbon_metrics", {})
        query_co2_g    = sum(
            v.get("co2_g", 0.0)
            for v in carbon_metrics.values()
            if isinstance(v, dict)
        )
        total_co2_g    += query_co2_g
        total_latency_ms += latency_ms

        # 평가 지표
        hit_source   = result["source"] == expected or expected == "either"
        returned_ids = _extract_ids(result)
        hit_doc      = any(d in returned_ids for d in exp_docs) if exp_docs else None
        top1_score   = result["results"][0]["score"] if result["results"] else 0.0

        if result["source"] == "qa_pairs":
            cache_hits += 1

        status = "✓" if (hit_source and (hit_doc is None or hit_doc)) else "✗"
        qa_score_str = (
            f"  (QA top1={result['qa_top1_score']:.4f})"
            if result["qa_top1_score"] else ""
        )
        co2_str = f"  CO2={query_co2_g*1000:.3f}mg" if query_co2_g else ""
        print(f"  {status} source={result['source']} top1={top1_score:.4f}"
              f"  latency={latency_ms:.0f}ms{qa_score_str}{co2_str}")

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

    # 배치 전체 탄소 요약
    total = len(records)
    hit_rate = cache_hits / total * 100 if total else 0
    avg_latency = total_latency_ms / total if total else 0
    print(f"\n {'─'*40}")
    print(f"  모드        : {mode_label}")
    print(f"  캐시 히트율 : {cache_hits}/{total} ({hit_rate:.1f}%)")
    print(f"  총 CO2      : {total_co2_g*1000:.3f} mg  ({total_co2_g:.6f} g)")
    print(f"  평균 지연   : {avg_latency:.0f} ms")
    print(f" {'─'*40}")

    return records


def _extract_ids(result: dict) -> list[str]:
    """검색 결과에서 doc_id / source_doc_id / qa_id 목록 추출."""
    ids = []
    for r in result["results"]:
        p = r["payload"]
        for key in ("doc_id", "source_doc_id", "qa_id"):
            val = p.get(key)
            if val:
                ids.append(val)
    return ids


# ── 요약 출력 ─────────────────────────────────────────────────────────────────

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
    avg_latency= sum(r["latency_ms"] for r in records) / total

    by_cat: dict[str, list[float]] = {}
    for r in records:
        cat = r["test"].get("category", "unknown")
        by_cat.setdefault(cat, []).append(r["top1_score"])

    mode_label = MODES[mode]["label"]

    print(f"\n{'='*60}")
    print(f" 평가 요약 — {mode_label}")
    print(f"{'='*60}")
    print(f" 총 질문 수     : {total}")
    print(f" Source 정확도  : {src_hits}/{total} ({src_hits/total*100:.1f}%)")
    if doc_eval:
        print(f" Doc Hit율      : {doc_hits}/{len(doc_eval)} ({doc_hits/len(doc_eval)*100:.1f}%)")
    print(f" 캐시 히트율    : {cache_hits}/{total} ({cache_hits/total*100:.1f}%)")
    print(f" Top-1 유사도   : 평균 {avg_top1:.4f}")
    print(f" 총 CO2         : {total_co2*1000:.3f} mg  ({total_co2:.6f} g)")
    print(f" 평균 지연      : {avg_latency:.0f} ms")
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
            print(f"  {t['id']} | {t['category']} | {t['query'][:55]}")
            print(f"    expected={t.get('expected_source')}  got={r['result']['source']}"
                  f"  top1={r['top1_score']:.4f}")
    print()


# ── 비교 요약 (3개 로그 파일 → 표 1) ─────────────────────────────────────────

def print_comparison(base_dir: Path = Path(".")) -> None:
    """
    b1_eval_log.jsonl / b2_eval_log.jsonl / ciasc_eval_log.jsonl 을 읽어
    논문 표 1 형식으로 비교 출력합니다.
    """
    rows = []
    for mode, cfg in MODES.items():
        log_path = base_dir / f"{cfg['log_suffix']}_eval_log.jsonl"
        if not log_path.exists():
            continue
        entries = [
            json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()
        ]
        if not entries:
            continue

        total      = len(entries)
        cache_hits = sum(1 for e in entries if e.get("source") == "qa_pairs")
        scores     = [e["results"][0]["score"] for e in entries if e.get("results")]
        avg_top1   = sum(scores) / len(scores) if scores else 0.0

        # 탄소: carbon_metrics가 있으면 합산
        total_co2 = 0.0
        for e in entries:
            cm = e.get("carbon_metrics", {})
            total_co2 += sum(
                v.get("co2_g", 0.0) for v in cm.values() if isinstance(v, dict)
            )

        rows.append({
            "label":      cfg["label"],
            "accuracy":   f"{avg_top1:.2f}",
            "co2_g":      f"{total_co2:.4f}",
            "hit_rate":   f"{cache_hits/total*100:.1f}%",
        })

    if not rows:
        print("[비교] 로그 파일 없음 — 먼저 --mode b1/b2/ciasc 로 평가를 실행하세요.")
        return

    print(f"\n{'='*60}")
    print(f" 논문 표 1 비교")
    print(f"{'='*60}")
    print(f"  {'설정':<28} {'정확도':>8} {'탄소(g)':>10} {'히트율':>8}")
    print(f"  {'─'*56}")
    for r in rows:
        print(f"  {r['label']:<28} {r['accuracy']:>8} {r['co2_g']:>10} {r['hit_rate']:>8}")
    print(f"{'='*60}\n")


# ── 기존 로그 요약 ─────────────────────────────────────────────────────────────

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

    for key_str, group in groups.items():
        cfg   = group[0]["config"]
        total = len(group)
        qa_cnt  = sum(1 for e in group if e["source"] == "qa_pairs")
        doc_cnt = total - qa_cnt
        scores  = [e["results"][0]["score"] for e in group if e["results"]]
        avg     = sum(scores) / len(scores) if scores else 0.0
        qa_scores = [e["qa_top1_score"] for e in group if e["qa_top1_score"] is not None]
        avg_qa  = sum(qa_scores) / len(qa_scores) if qa_scores else 0.0

        print(f"\n 모델  : {cfg['embed_model']}")
        print(f" 임계값: {cfg['qa_similarity_threshold']}  "
              f"청크크기: {cfg['chunk_size']}  top_k: {cfg['top_k']}")
        print(f" 질문 수: {total}  →  qa_pairs: {qa_cnt}  documents: {doc_cnt}")
        print(f" Top-1 유사도 평균: {avg:.4f}  QA top1 평균: {avg_qa:.4f}")

    print(f"\n{'='*60}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EcoCache 평가 스크립트")
    parser.add_argument(
        "--mode", default="b2", choices=["b1", "b2", "ciasc"],
        help="평가 모드: b1=캐시없음 / b2=정적캐시(θ=0.90) / ciasc=CI적응형 (기본: b2)"
    )
    parser.add_argument("--test-file",    default="test_queries.json")
    parser.add_argument("--log-file",     default=None,
                        help="결과 로그 파일 (기본: {mode}_eval_log.jsonl)")
    parser.add_argument("--category",     default=None)
    parser.add_argument("--alpha",         type=float, default=0.15,
                        help="CIASC α값 (기본: 0.15, 논문 실험: 0.25 / 0.50 / 1.00)")
    parser.add_argument("--summary-only", action="store_true",
                        help="기존 로그 파일 요약만 출력")
    parser.add_argument("--compare",      action="store_true",
                        help="b1/b2/ciasc 로그를 읽어 표 1 형식으로 비교 출력")
    args = parser.parse_args()

    # 로그 파일 기본값: ciasc 모드는 alpha값 포함 (예: ciasc_0.25_eval_log.jsonl)
    if args.log_file:
        log_path = Path(args.log_file)
    elif args.mode == "ciasc":
        log_path = Path(f"ciasc_alpha{args.alpha}_eval_log.jsonl")
    else:
        log_path = Path(f"{args.mode}_eval_log.jsonl")
    test_path = Path(args.test_file)

    if args.compare:
        print_comparison()
        sys.exit(0)

    if args.summary_only:
        summarize_log(log_path)
        sys.exit(0)

    if not test_path.exists():
        print(f"[오류] 테스트 파일 없음: {test_path}")
        sys.exit(1)

    records = run_eval(test_path, log_path,
                       category_filter=args.category,
                       mode=args.mode,
                       alpha=args.alpha)
    print_summary(records, args.mode)
    print(f"전체 로그 요약:")
    summarize_log(log_path)
