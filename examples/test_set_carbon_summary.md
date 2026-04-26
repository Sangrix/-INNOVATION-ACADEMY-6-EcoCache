# Test Set Carbon Summary

## Source Routing

- Total questions: `25`
- `qa_pairs` hits: `6`
- `documents` fallbacks: `19`

## Retrieval Quality

- Source accuracy: `24/25 (96.0%)`
- Document hit rate: `20/21 (95.2%)`
- Average top-1 similarity: `0.6898`

## Retrieval Carbon Totals

| Stage | Calls | Total Duration (s) | Avg Duration (s) | Total CO2 (g) | Avg CO2 (g) | Avg Peak Power (W) | Avg Power (W) |
|------|------:|-------------------:|-----------------:|--------------:|------------:|-------------------:|--------------:|
| `qa_pairs_retrieval` | 25 | 55.5169 | 2.2207 | 0.2197 | 0.0088 | 4.52 | 3.85 |
| `documents_retrieval` | 19 | 41.7692 | 2.1984 | 0.1655 | 0.0087 | 4.37 | 3.69 |

## Interpretation

- Every query pays the cost of `qa_pairs_retrieval`.
- Only low-confidence queries (`qa_top1_score < 0.75`) pay the additional cost
  of `documents_retrieval`.
- Total retrieval CO2 for the 25-question batch was `0.3852 g`.
- `llm_generation` is supported by the carbon monitor, but it was not triggered
  in this batch because `run_eval.py` currently does retrieval-only evaluation.
