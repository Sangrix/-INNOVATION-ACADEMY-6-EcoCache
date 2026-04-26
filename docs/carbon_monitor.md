# Carbon Monitor Integration

## Goal

This module adds carbon and power measurement to the existing EcoCache pipeline
without changing retrieval thresholds, model selection, or prompt logic.

The integration is intentionally small:

- one reusable monitor module
- a few wrapper calls around existing pipeline stages
- one JSONL log file for later analysis

## Files

- `carbon_monitor.py`
- `config.py`
- `embed_pipeline.py`
- `query.py`
- `requirements.txt`

## What The Module Measures

Each monitored stage returns both:

- the original function result
- a metrics dictionary

The metrics dictionary includes:

- `stage`
- `duration_sec`
- `energy_kwh`
- `co2_g`
- `peak_power_W`
- `avg_power_W`
- `extra`

## Integration Points

### Embedding pipeline

`embed_pipeline.py` wraps:

- `documents_embedding`
- `qa_embedding`

### Query pipeline

`query.py` wraps:

- `qa_pairs_retrieval`
- `documents_retrieval`
- `llm_generation`

## Usage Pattern

```python
from carbon_monitor import CarbonMonitor

carbon_monitor = CarbonMonitor.from_config(config)

result, metrics = carbon_monitor.run(
    "documents_embedding",
    some_existing_function,
    *args,
    **kwargs,
)
```

## Configuration

Environment variables:

```dotenv
CARBON_MONITOR_ENABLED=true
CARBON_INTENSITY_G_PER_KWH=350.0
CARBON_GPU_INDEX=0
CARBON_SAMPLE_INTERVAL=0.1
CARBON_LOG_PATH=carbon_metrics.jsonl
```

## Output

The monitor writes a JSON Lines log file.

Example:

```json
{
  "stage": "documents_embedding",
  "duration_sec": 16.845,
  "energy_kwh": 0.00014592237952754716,
  "co2_g": 0.0511,
  "peak_power_W": 30.19,
  "avg_power_W": 22.36,
  "extra": {
    "collection": "documents",
    "chunk_count": 189
  }
}
```

## Notes

- This branch focuses on attaching the carbon monitor only.
- It does not tune thresholds or retrieval logic.
- It does not change the RAG pipeline design.
