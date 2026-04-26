# Carbon Monitoring Run Summary

## Validation Scope

- embedding pipeline execution
- single-query retrieval sample
- 25-query batch evaluation (`test_queries.json`)
- carbon log output verification

## Single Query Sample

- Query: `i-PAC 콘테스트 신청 기간은 언제인가요?`
- Source selected: `documents`
- QA top1 score: `0.7188`

| Stage | Duration (s) | CO2 (g) | Peak Power (W) | Avg Power (W) |
|------|--------------:|--------:|---------------:|--------------:|
| `documents_embedding` | 16.8450 | 0.0511 | 30.19 | 22.36 |
| `qa_embedding` | 2.6760 | 0.0137 | 27.07 | 14.46 |
| `qa_pairs_retrieval` | 0.4225 | 0.0061 | 8.54 | 6.46 |
| `documents_retrieval` | 0.1497 | 0.0032 | 4.45 | 3.96 |

## 25-Query Batch Evaluation

- Source accuracy: `24/25 (96.0%)`
- Document hit rate: `20/21 (95.2%)`
- QA hit count: `6`
- Document fallback count: `19`
- Average top-1 similarity: `0.6898`
- Total retrieval CO2: `0.3852 g`
- Average retrieval CO2 per query: `0.0154 g`

| Stage | Calls | Total Duration (s) | Avg Duration (s) | Total CO2 (g) | Avg CO2 (g) |
|------|------:|-------------------:|-----------------:|--------------:|------------:|
| `qa_pairs_retrieval` | 25 | 55.5169 | 2.2207 | 0.2197 | 0.0088 |
| `documents_retrieval` | 19 | 41.7692 | 2.1984 | 0.1655 | 0.0087 |

## Notes

- `llm_generation` is integrated in `query.py`.
- This batch evaluation did not record `llm_generation`, because `run_eval.py`
  currently exercises retrieval only.
- No retrieval threshold or model values were changed for this branch.
