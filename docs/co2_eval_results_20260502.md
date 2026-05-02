# CO2 Evaluation Results - 2026-05-02

## Purpose

This run was executed to remeasure the `feat/eval-pipeline` branch on a local GPU environment and fix the issue where the console summary displayed CO2 as `0`.

The evaluation logic was kept as close as possible to the branch implementation. The only code fix in this branch is the CO2 aggregation path in `run_eval.py`.

## Environment

- Base branch/commit: `origin/feat/eval-pipeline` at `d3a1245`
- Local GPU: NVIDIA GeForce RTX 3050 4GB Laptop GPU
- Embedding model: `dragonkue/BGE-m3-ko`
- Vector DB: Qdrant local server
- Test set: `test_queries.json` 50 questions
- Carbon intensity for CO2 conversion: `430 gCO2/kWh`
- LLM generation: disabled
- Result folder: `snapshots/feat_eval_pipeline_original_20260502_190451`

## CO2 Summary Fix

`query.py` returns carbon metrics under `result["metrics"]`, but `run_eval.py` was reading `result["carbon_metrics"]`.

Because of that mismatch, individual JSONL logs contained CO2 values, but the console/batch summary could show `0`.

Fixed line:

```python
carbon_metrics = result.get("metrics") or result.get("carbon_metrics", {})
```

## Result Table

| Setting | Source Accuracy | Cache Hit Rate | Avg Latency | Total CO2 | CO2 / Query | Threshold |
|---|---:|---:|---:|---:|---:|---|
| B1 (No Cache) | 66.0% | 0.0% | 18,204 ms | 1.4236 g | 0.02847 g | 1.10 fixed |
| B2 (Static Cache) | 68.0% | 2.0% | 16,617 ms | 1.0794 g | 0.02159 g | 0.90 fixed |
| CIASC alpha=0.25 | 72.0% | 6.0% | 20,516 ms | 1.0590 g | 0.02118 g | 0.80 -> 0.95 |
| CIASC alpha=0.50 | 72.0% | 6.0% | 16,280 ms | 1.0554 g | 0.02111 g | 0.80 -> 0.95 |
| CIASC alpha=1.00 | 78.0% | 12.0% | 15,827 ms | 1.0154 g | 0.02031 g | 0.76 -> 0.95 |

## Interpretation

The CIASC runs showed lower CO2 than B2 in this run, and `alpha=1.00` had the best source accuracy and cache hit rate.

However, these CIASC numbers should be treated as branch-reproduction results, not final algorithm validation results, because the current branch has two important implementation issues:

- `carbon_optimizer.py` overwrites the CLI alpha value with `alpha = 0.15`, so `--alpha 0.25`, `--alpha 0.5`, and `--alpha 1.0` are not truly reflected in the threshold formula.
- `base_theta = config.QA_SIMILARITY_THRESHOLD` uses the previous threshold as the next baseline, so the threshold accumulates upward across questions until it reaches `0.95`.

Because of those issues, the threshold change is not a clean per-query CI-adaptive calculation. If the team confirms that this is a bug, the next run should fix:

- Remove the hardcoded `alpha = 0.15`.
- Use a stable base threshold, for example `base_theta = 0.75`, or align the implementation with the paper formula.
- Prevent threshold accumulation between questions.

## Raw Artifacts

The raw result files are included under:

```text
snapshots/feat_eval_pipeline_original_20260502_190451/
```

Important files:

- `b1_console.txt`
- `b2_console.txt`
- `ciasc_alpha0.25_console.txt`
- `ciasc_alpha0.5_console.txt`
- `ciasc_alpha1.0_console.txt`
- `b1_eval_log.jsonl`
- `b2_eval_log.jsonl`
- `ciasc_alpha0.25_eval_log.jsonl`
- `ciasc_alpha0.5_eval_log.jsonl`
- `ciasc_alpha1.0_eval_log.jsonl`
- `carbon_metrics.jsonl`
