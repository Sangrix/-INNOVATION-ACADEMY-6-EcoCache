"""
EcoCache 임베딩 성능 평가 스크립트

사용법:
  python run_eval.py                                      # semantic_cache, 전체
  python run_eval.py --mode pure_rag                      # Baseline 1
  python run_eval.py --mode semantic_cache                # Baseline 2 (기본값)
  python run_eval.py --category exact_match               # 카테고리 필터
  python run_eval.py --log-file my_run.jsonl              # 출력 파일 지정
  python run_eval.py --summary-only                       # 기존 로그 요약만 출력
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import query as Q
from query import get_retriever, log_result


# ── 평가 실행 ─────────────────────────────────────────────────────────────────

def run_eval(test_file: Path, log_file: Path, mode: str = "semantic_cache",
             category_filter: str | None = None) -> list[dict]:
    tests = json.loads(test_file.read_text(encoding="utf-8"))

    if category_filter:
        tests = [t for t in tests if t.get("category") == category_filter]
        if not tests:
            print(f"[경고] '{category_filter}' 카테고리 질문 없음")
            return []

    retriever = get_retriever(mode)

    print(f"\n{'='*60}")
    print(f" EcoCache 평가 실행")
    print(f" 모드  : {mode}")
    print(f" 질문 수: {len(tests)} | 로그: {log_file}")
    if category_filter:
        print(f" 카테고리 필터: {category_filter}")
    print(f"{'='*60}\n")

    records = []
    for i, test in enumerate(tests, 1):
        tid      = test["id"]
        query    = test["query"]
        expected = test.get("expected_source", "either")
        exp_docs = test.get("expected_doc_ids", [])

        print(f"[{i:02d}/{len(tests)}] {tid} ({test.get('category','')}) — {query[:50]}")

        result = retriever.retrieve(query)
        log_result(result, log_file=log_file, mode=mode)

        hit_source   = result["source"] == expected or expected == "either"
        returned_ids = _extract_ids(result)
        hit_doc      = any(d in returned_ids for d in exp_docs) if exp_docs else None
        top1_score   = result["results"][0]["score"] if result["results"] else 0.0

        status = "✓" if (hit_source and (hit_doc is None or hit_doc)) else "✗"
        qa_score_str = (f"  (QA top1={result['qa_top1_score']:.4f})"
                        if result["qa_top1_score"] else "")
        print(f"  {status} source={result['source']} top1={top1_score:.4f}{qa_score_str}")
        if exp_docs and not hit_doc:
            print(f"  ⚠ 예상 doc_id 미포함: {exp_docs}")

        records.append({
            "test":       test,
            "result":     result,
            "hit_source": hit_source,
            "hit_doc":    hit_doc,
            "top1_score": top1_score,
            "mode":       mode,
        })

    return records


def _extract_ids(result: dict) -> list[str]:
    ids = []
    for r in result["results"]:
        p = r["payload"]
        for key in ("doc_id", "source_doc_id", "qa_id"):
            val = p.get(key)
            if val:
                ids.append(val)
    return ids


# ── 요약 출력 ─────────────────────────────────────────────────────────────────

def print_summary(records: list[dict]) -> None:
    if not records:
        return

    total    = len(records)
    src_hits = sum(1 for r in records if r["hit_source"])
    doc_eval = [r for r in records if r["hit_doc"] is not None]
    doc_hits = sum(1 for r in doc_eval if r["hit_doc"])
    avg_top1 = sum(r["top1_score"] for r in records) / total
    mode     = records[0].get("mode", "unknown")

    by_cat: dict[str, list[float]] = {}
    for r in records:
        cat = r["test"].get("category", "unknown")
        by_cat.setdefault(cat, []).append(r["top1_score"])

    print(f"\n{'='*60}")
    print(f" 평가 요약  [mode: {mode}]")
    print(f"{'='*60}")
    print(f" 총 질문 수     : {total}")
    print(f" Source 정확도  : {src_hits}/{total} ({src_hits/total*100:.1f}%)")
    if doc_eval:
        print(f" Doc Hit율      : {doc_hits}/{len(doc_eval)} ({doc_hits/len(doc_eval)*100:.1f}%)")
    print(f" Top-1 유사도   : 평균 {avg_top1:.4f}")
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


# ── 기존 로그 요약 ─────────────────────────────────────────────────────────────

def summarize_log(log_file: Path) -> None:
    if not log_file.exists():
        print(f"[오류] 파일 없음: {log_file}")
        return

    lines = [l for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        print("로그 항목 없음")
        return

    entries = [json.loads(l) for l in lines]

    print(f"\n{'='*60}")
    print(f" 로그 분석: {log_file}  ({len(entries)}건)")
    print(f"{'='*60}")

    groups: dict[str, list] = {}
    for e in entries:
        cfg = e["config"]
        key = (cfg.get("mode", "unknown"), cfg["embed_model"],
               cfg["qa_similarity_threshold"], cfg["chunk_size"])
        groups.setdefault(str(key), []).append(e)

    for key_str, group in groups.items():
        cfg    = group[0]["config"]
        total  = len(group)
        qa_cnt = sum(1 for e in group if e["source"] == "qa_pairs")
        doc_cnt = total - qa_cnt
        scores  = [e["results"][0]["score"] for e in group if e["results"]]
        avg     = sum(scores) / len(scores) if scores else 0.0
        qa_sc   = [e["qa_top1_score"] for e in group if e.get("qa_top1_score") is not None]
        avg_qa  = sum(qa_sc) / len(qa_sc) if qa_sc else 0.0

        print(f"\n 모드  : {cfg.get('mode', 'unknown')}")
        print(f" 모델  : {cfg['embed_model']}")
        print(f" 임계값: {cfg['qa_similarity_threshold']}  청크: {cfg['chunk_size']}  top_k: {cfg['top_k']}")
        print(f" 질문 수: {total}  →  qa_pairs: {qa_cnt}  documents: {doc_cnt}")
        print(f" Top-1 유사도 평균: {avg:.4f}  QA top1 평균: {avg_qa:.4f}")

    print(f"\n{'='*60}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EcoCache 평가 스크립트")
    parser.add_argument("--mode",         default="semantic_cache",
                        choices=["pure_rag", "semantic_cache"],
                        help="검색 모드 선택 (기본: semantic_cache)")
    parser.add_argument("--test-file",    default="test_queries.json")
    parser.add_argument("--log-file",     default="eval_log.jsonl")
    parser.add_argument("--category",     default=None)
    parser.add_argument("--summary-only", action="store_true",
                        help="기존 로그 파일 요약만 출력")
    args = parser.parse_args()

    log_path  = Path(args.log_file)
    test_path = Path(args.test_file)

    if args.summary_only:
        summarize_log(log_path)
        sys.exit(0)

    if not test_path.exists():
        print(f"[오류] 테스트 파일 없음: {test_path}")
        sys.exit(1)

    records = run_eval(test_path, log_path, mode=args.mode,
                       category_filter=args.category)
    print_summary(records)
    print("전체 로그 요약:")
    summarize_log(log_path)
