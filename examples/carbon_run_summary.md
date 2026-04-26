# Carbon Monitoring Run Summary

## Validation Scope

- embedding pipeline execution
- retrieval execution
- carbon log output verification

## Sample Query

- Query: `i-PAC 콘테스트 신청 기간은 언제인가요?`
- Source selected: `documents`
- QA top1 score: `0.7188`

## Sample Carbon Results

| Stage | Duration (s) | CO2 (g) | Peak Power (W) | Avg Power (W) |
|------|--------------:|--------:|---------------:|--------------:|
| `documents_embedding` | 16.8450 | 0.0511 | 30.19 | 22.36 |
| `qa_embedding` | 2.6760 | 0.0137 | 27.07 | 14.46 |
| `qa_pairs_retrieval` | 0.4225 | 0.0061 | 8.54 | 6.46 |
| `documents_retrieval` | 0.1497 | 0.0032 | 4.45 | 3.96 |

## Interpretation

- The integration produced per-stage carbon metrics successfully.
- Retrieval stayed below the current QA threshold for the sample query, so the
  pipeline correctly fell back to `documents`.
- No threshold or retrieval values were changed for this branch.
