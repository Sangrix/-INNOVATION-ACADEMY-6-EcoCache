# CO2 Evaluation Result Summary - 2026-05-02

This folder contains the local GPU CO2 remeasurement results for the original `feat/eval-pipeline` branch.

## Run Setup

- Base commit: `d3a1245`
- Test set: 50 questions
- Carbon intensity: `430 gCO2/kWh`
- LLM generation: disabled
- CO2 monitor: enabled
- GPU: NVIDIA GeForce RTX 3050 4GB Laptop GPU

## Results

| Setting | Source Accuracy | Cache Hit Rate | Avg Latency | Total CO2 | CO2 / Query | Threshold |
|---|---:|---:|---:|---:|---:|---|
| B1 (No Cache) | 66.0% | 0.0% | 18,204 ms | 1.4236 g | 0.02847 g | 1.10 fixed |
| B2 (Static Cache) | 68.0% | 2.0% | 16,617 ms | 1.0794 g | 0.02159 g | 0.90 fixed |
| CIASC alpha=0.25 | 72.0% | 6.0% | 20,516 ms | 1.0590 g | 0.02118 g | 0.80 -> 0.95 |
| CIASC alpha=0.50 | 72.0% | 6.0% | 16,280 ms | 1.0554 g | 0.02111 g | 0.80 -> 0.95 |
| CIASC alpha=1.00 | 78.0% | 12.0% | 15,827 ms | 1.0154 g | 0.02031 g | 0.76 -> 0.95 |

## Notes

- The CO2 summary issue was caused by `run_eval.py` reading `result["carbon_metrics"]` while `query.py` returns metrics as `result["metrics"]`.
- This branch fixes the aggregation path so the console summary can read CO2 correctly.
- CIASC threshold values still follow the original branch behavior.
- Current branch behavior has two caveats: alpha is hardcoded to `0.15` inside `carbon_optimizer.py`, and threshold values accumulate because the previous threshold is reused as the next base threshold.

## Files

- `*_console.txt`: console output for each mode
- `*_eval_log.jsonl`: per-question retrieval/evaluation logs
- `carbon_metrics.jsonl`: raw CodeCarbon/GPU power measurement records
