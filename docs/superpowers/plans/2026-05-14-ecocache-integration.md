# EcoCache 통합 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `feat/vector_embed`(RAG 파이프라인 + FastAPI)와 `origin/develop`(탄소 모니터링 + CIASC)를 기능별 폴더로 분리된 단일 코드베이스로 통합한다.

**Architecture:** `rag/`(검색 파이프라인), `carbon/`(탄소 모니터링), `api/`(FastAPI), `infra/`(Docker) 4개 폴더로 구성. `carbon/` 모듈은 독립적으로 설계되어 `rag/`와 `api/` 양쪽에서 임포트. sys.path 패턴으로 패키지 간 의존성 처리.

**Tech Stack:** Python 3.10+, Qdrant, PostgreSQL 16, FastAPI, codecarbon, pynvml, sentence-transformers(BGE-m3-ko), Docker Compose

---

## 파일 맵

| 액션 | 경로 | 역할 |
|------|------|------|
| 이동 | `sw_upstage_output/` → `data/sw_upstage_output/` | 입력 데이터 |
| 이동 | `sw_upstage_output_2/` → `data/sw_upstage_output_2/` | 입력 데이터 |
| 이동 | `sw_upstage_output_3/` → `data/sw_upstage_output_3/` | 입력 데이터 |
| 이동 | `pr_data/` → `data/pr_data/` | 입력 데이터 |
| 생성 | `infra/docker-compose.yml` | Qdrant + PostgreSQL |
| 생성 | `infra/schema.sql` | carbon_intensity_logs 테이블 |
| 생성 | `carbon/carbon_monitor.py` | CarbonMonitor (codecarbon + pynvml) |
| 생성 | `carbon/carbon_optimizer.py` | CarbonAdaptiveOptimizer (Electricity Maps) |
| 생성 | `carbon/collector.py` | CI 수집 데몬 (15분 주기, PostgreSQL) |
| 생성 | `carbon/requirements.txt` | carbon 의존성 |
| 수정 | `rag/config.py` | 데이터 경로 + 탄소/CIASC 설정 추가 |
| 수정 | `rag/embed_pipeline.py` | develop 버전 교체 (carbon_monitor 통합) |
| 유지 | `rag/retriever_base.py` | 변경 없음 |
| 유지 | `rag/baseline_pure_rag.py` | 변경 없음 |
| 유지 | `rag/baseline_semantic_cache.py` | 변경 없음 |
| 생성 | `rag/baseline_ciasc.py` | CIASCRetriever (BaseRetriever 구현) |
| 수정 | `rag/query.py` | ciasc 모드 + carbon_monitor 추가 |
| 수정 | `rag/run_eval.py` | develop 버전 교체 (b1/b2/ciasc) |
| 수정 | `rag/requirements.txt` | codecarbon, pynvml 추가 |
| 수정 | `api/main.py` | co2_grams 실제 측정 통합 |
| 수정 | `api/requirements.txt` | python-dotenv 추가 |
| 생성 | `.env.example` | 환경변수 템플릿 |
| 생성 | `README.md` | 통합 사용 가이드 |

---

## Task 1: 데이터 폴더 이동

**Files:**
- 이동: `{sw_upstage_output,sw_upstage_output_2,sw_upstage_output_3,pr_data}/` → `data/`

- [ ] **Step 1: data/ 디렉토리 생성 후 git mv로 이동**

```bash
mkdir -p data
git mv sw_upstage_output data/sw_upstage_output
git mv sw_upstage_output_2 data/sw_upstage_output_2
git mv sw_upstage_output_3 data/sw_upstage_output_3
git mv pr_data data/pr_data
```

- [ ] **Step 2: 이동 확인**

```bash
ls data/
# 출력: pr_data  sw_upstage_output  sw_upstage_output_2  sw_upstage_output_3
ls data/sw_upstage_output/
# 출력: inha_notice_data.json  inha_notice_qa.json
```

- [ ] **Step 3: 커밋**

```bash
git add -A
git commit -m "chore: move data folders into data/ directory"
```

---

## Task 2: infra/ — Docker Compose + 스키마

**Files:**
- 생성: `infra/docker-compose.yml`
- 생성: `infra/schema.sql`

- [ ] **Step 1: infra/ 디렉토리 생성**

```bash
mkdir -p infra
```

- [ ] **Step 2: `infra/schema.sql` 작성**

```sql
-- 탄소 집약도(CI) 저장용 테이블 (15분 주기 적재)
CREATE TABLE IF NOT EXISTS carbon_intensity_logs (
    id         SERIAL PRIMARY KEY,
    timestamp  TIMESTAMP WITH TIME ZONE NOT NULL,
    zone_name  VARCHAR(10)  DEFAULT 'KR',
    g_per_kwh  FLOAT        NOT NULL,
    source     VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_timestamp
    ON carbon_intensity_logs (timestamp DESC);
```

- [ ] **Step 3: `infra/docker-compose.yml` 작성**

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: ecocache-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      QDRANT__SERVICE__HTTP_PORT: 6333
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    container_name: ecocache-postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-ecocache}
      POSTGRES_USER: ${POSTGRES_USER:-ecocache}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ecocache}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-ecocache}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  qdrant_data:
  postgres_data:
```

- [ ] **Step 4: Docker Compose 기동 확인**

```bash
cd infra
docker compose up -d
docker compose ps
# 출력: ecocache-qdrant, ecocache-postgres 모두 running 상태 확인
docker compose down  # 확인 후 종료 (실제 작업 시 유지)
cd ..
```

- [ ] **Step 5: 커밋**

```bash
git add infra/
git commit -m "feat: add Docker Compose for Qdrant and PostgreSQL"
```

---

## Task 3: carbon/ 모듈

**Files:**
- 생성: `carbon/carbon_monitor.py`
- 생성: `carbon/carbon_optimizer.py`
- 생성: `carbon/collector.py`
- 생성: `carbon/requirements.txt`

- [ ] **Step 1: `carbon/` 디렉토리 생성**

```bash
mkdir -p carbon
```

- [ ] **Step 2: `carbon/carbon_monitor.py` 작성 (develop 브랜치 그대로)**

```python
import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pynvml
from codecarbon import EmissionsTracker


class CarbonMonitor:
    def __init__(
        self,
        ci_value=350.0,
        enabled=True,
        gpu_index=0,
        sample_interval=0.1,
        log_path=None,
    ):
        self.ci_value = ci_value
        self.enabled = enabled
        self.gpu_index = gpu_index
        self.sample_interval = sample_interval
        self.log_path = Path(log_path) if log_path else None
        self._gpu_handle = None

        if not self.enabled:
            return

        try:
            pynvml.nvmlInit()
            self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(self.gpu_index)
        except pynvml.NVMLError:
            self._gpu_handle = None

    @classmethod
    def from_config(cls, cfg):
        return cls(
            ci_value=cfg.CARBON_INTENSITY_G_PER_KWH,
            enabled=cfg.CARBON_MONITOR_ENABLED,
            gpu_index=cfg.CARBON_GPU_INDEX,
            sample_interval=cfg.CARBON_SAMPLE_INTERVAL,
            log_path=cfg.CARBON_LOG_PATH,
        )

    def _build_tracker(self):
        tracker_kwargs = {
            "save_to_file": False,
            "save_to_api": False,
            "save_to_logger": False,
            "log_level": "error",
            "measure_power_secs": self.sample_interval,
            "allow_multiple_runs": False,
        }
        if self._gpu_handle is not None:
            tracker_kwargs["gpu_ids"] = [self.gpu_index]
        return EmissionsTracker(**tracker_kwargs)

    def _sample_gpu_power(self, stop_event, power_records):
        if self._gpu_handle is None:
            return
        while not stop_event.is_set():
            try:
                power_mw = pynvml.nvmlDeviceGetPowerUsage(self._gpu_handle)
                power_records.append(power_mw / 1000.0)
            except pynvml.NVMLError:
                break
            time.sleep(self.sample_interval)

    def _zero_metrics(self, stage_name, extra):
        metrics = {
            "stage": stage_name,
            "duration_sec": 0.0,
            "energy_kwh": 0.0,
            "co2_g": 0.0,
            "peak_power_W": 0.0,
            "avg_power_W": 0.0,
        }
        if extra:
            metrics["extra"] = extra
        return metrics

    def _write_metrics(self, metrics):
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")

    @contextmanager
    def track(self, stage_name, extra=None):
        if not self.enabled:
            state = {"metrics": self._zero_metrics(stage_name, extra)}
            yield state
            return

        power_records = []
        stop_event = threading.Event()
        monitor_thread = threading.Thread(
            target=self._sample_gpu_power,
            args=(stop_event, power_records),
            daemon=True,
        )
        tracker = self._build_tracker()

        monitor_thread.start()
        tracker.start()
        start_time = time.time()
        state = {"metrics": None}

        try:
            yield state
        finally:
            duration = time.time() - start_time
            tracker.stop()
            stop_event.set()
            monitor_thread.join()

            emissions = tracker.final_emissions_data
            energy_kwh = getattr(emissions, "energy_consumed", 0.0) or 0.0
            metrics = {
                "stage": stage_name,
                "duration_sec": round(duration, 4),
                "energy_kwh": energy_kwh,
                "co2_g": round(energy_kwh * self.ci_value, 4),
                "peak_power_W": round(max(power_records), 2) if power_records else 0.0,
                "avg_power_W": round(sum(power_records) / len(power_records), 2) if power_records else 0.0,
            }
            if extra:
                metrics["extra"] = extra
            state["metrics"] = metrics
            self._write_metrics(metrics)

    def run(self, stage_name, func, *args, extra=None, **kwargs):
        with self.track(stage_name, extra=extra) as state:
            result = func(*args, **kwargs)
        return result, state["metrics"]

    def measure(self, stage_name, extra=None):
        def decorator(func):
            def wrapper(*args, **kwargs):
                result, metrics = self.run(stage_name, func, *args, extra=extra, **kwargs)
                return result, metrics
            return wrapper
        return decorator
```

- [ ] **Step 3: `carbon/carbon_optimizer.py` 작성 (rag/ sys.path 추가)**

```python
import sys
from pathlib import Path

# rag/config.py 참조를 위해 rag/ 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os

import requests
from dotenv import load_dotenv

import config

load_dotenv()

_EMAPS_API_KEY = os.getenv("ELECTRICITY_MAPS_API_KEY")
_EMAPS_ZONE    = os.getenv("ELECTRICITY_MAPS_ZONE", "KR")
_EMAPS_BASE_URL = "https://api.electricitymap.org/v3"
_CACHE_TTL_SEC = 300


class CarbonAdaptiveOptimizer:
    def __init__(self):
        self.KR_CI_BY_HOUR = {
            0: 430, 3: 415, 6: 420, 9: 410,
            12: 385, 15: 375, 18: 400, 21: 420,
        }
        self.DEFAULT_KR_CI = 415
        self._ci_cache: dict = {"value": None, "fetched_at": None}

    def get_current_ci(self) -> float:
        if config.CIASC_FIXED_CI is not None:
            return float(config.CIASC_FIXED_CI)
        if _EMAPS_API_KEY:
            return self._fetch_ci_from_api()
        return self._ci_from_proxy()

    def get_adaptive_threshold(
        self,
        ci: float | None = None,
        alpha: float = 0.15,
        theta_min: float | None = None,
        theta_max: float | None = None,
    ) -> float:
        if ci is None:
            ci = self.get_current_ci()
        theta_min = config.CIASC_THETA_MIN if theta_min is None else theta_min
        theta_max = config.CIASC_THETA_MAX if theta_max is None else theta_max
        ci_range = config.CIASC_CI_MAX - config.CIASC_CI_MIN
        ci_norm = 0.0 if ci_range == 0 else (ci - config.CIASC_CI_MIN) / ci_range
        ci_norm = max(0.0, min(1.0, ci_norm))
        theta = config.CIASC_BASE_THRESHOLD - (alpha * (ci_norm - 0.5))
        return round(max(theta_min, min(theta_max, theta)), 4)

    def _fetch_ci_from_api(self) -> float:
        now = datetime.now(timezone.utc)
        if (
            self._ci_cache["value"] is not None
            and self._ci_cache["fetched_at"] is not None
            and (now - self._ci_cache["fetched_at"]).total_seconds() < _CACHE_TTL_SEC
        ):
            return self._ci_cache["value"]
        try:
            resp = requests.get(
                f"{_EMAPS_BASE_URL}/carbon-intensity/latest",
                params={"zone": _EMAPS_ZONE},
                headers={"auth-token": _EMAPS_API_KEY},
                timeout=5,
            )
            resp.raise_for_status()
            ci = float(resp.json()["carbonIntensity"])
            self._ci_cache = {"value": ci, "fetched_at": now}
            return ci
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            print(f"[WARN] Electricity Maps API HTTP {status}, 정적 프록시로 fallback")
        except requests.exceptions.Timeout:
            print("[WARN] Electricity Maps API 타임아웃, 정적 프록시로 fallback")
        except Exception as e:
            print(f"[WARN] Electricity Maps API 실패, 정적 프록시로 fallback: {e}")
        return self._ci_from_proxy()

    def _ci_from_proxy(self) -> float:
        hour = datetime.now(ZoneInfo("Asia/Seoul")).hour
        closest = min(self.KR_CI_BY_HOUR.keys(), key=lambda x: abs(x - hour))
        return float(self.KR_CI_BY_HOUR.get(closest, self.DEFAULT_KR_CI))


_optimizer = None


def get_optimizer() -> CarbonAdaptiveOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = CarbonAdaptiveOptimizer()
    return _optimizer


if __name__ == "__main__":
    opt = get_optimizer()
    ci = opt.get_current_ci()
    source = (
        f"Electricity Maps API (zone={_EMAPS_ZONE})"
        if _EMAPS_API_KEY and opt._ci_cache["value"] is not None
        else "정적 프록시"
    )
    print(f"현재 CI: {ci} gCO2/kWh  [source: {source}]")
    for alpha in (0.25, 0.5, 1.0):
        print(f"  alpha={alpha}: theta={opt.get_adaptive_threshold(ci=ci, alpha=alpha)}")
```

- [ ] **Step 4: `carbon/collector.py` 작성 (env vars로 DB 설정)**

```python
import sys
import os
import time
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv

# carbon_optimizer가 rag/config를 참조하므로 carbon/ 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from carbon_optimizer import get_optimizer

load_dotenv()

EMAPS_ZONE = os.getenv("ELECTRICITY_MAPS_ZONE", "KR")
EMAPS_KEY  = os.getenv("ELECTRICITY_MAPS_API_KEY")

DB_CONFIG = {
    "dbname":   os.getenv("POSTGRES_DB",       "ecocache"),
    "user":     os.getenv("POSTGRES_USER",     "ecocache"),
    "password": os.getenv("POSTGRES_PASSWORD", "ecocache"),
    "host":     os.getenv("POSTGRES_HOST",     "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", "5432")),
}


def save_to_db(ci_value: float, source: str) -> None:
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO carbon_intensity_logs (timestamp, zone_name, g_per_kwh, source)"
            " VALUES (%s, %s, %s, %s)",
            (datetime.now(timezone.utc), EMAPS_ZONE, ci_value, source),
        )
        conn.commit()
        print(f"[{datetime.now()}] 저장 완료: {ci_value}g/kWh ({source})")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[{datetime.now()}] DB 오류: {e}")


def run_collector() -> None:
    print(f"CI 수집 시작 (지역: {EMAPS_ZONE})")
    opt = get_optimizer()
    while True:
        ci_value = opt.get_current_ci()
        source = "API" if EMAPS_KEY and opt._ci_cache["value"] is not None else "Static Proxy"
        save_to_db(ci_value, source)
        time.sleep(900)  # 15분


if __name__ == "__main__":
    run_collector()
```

- [ ] **Step 5: `carbon/requirements.txt` 작성**

```
codecarbon>=2.4.0
pynvml>=11.5.0
psycopg2-binary>=2.9.0
requests>=2.32.0
python-dotenv>=1.0.0
```

- [ ] **Step 6: 스모크 테스트 — carbon_optimizer**

```bash
cd carbon
python carbon_optimizer.py
# 출력 예: 현재 CI: 415.0 gCO2/kWh  [source: 정적 프록시]
#          alpha=0.25: theta=0.7375
cd ..
```

- [ ] **Step 7: 커밋**

```bash
git add carbon/
git commit -m "feat: add carbon/ module (monitor, optimizer, collector)"
```

---

## Task 4: rag/config.py 업데이트

**Files:**
- 수정: `rag/config.py`

- [ ] **Step 1: `rag/config.py` 전체 교체**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "data"

# ── 입력 데이터 경로 ──────────────────────────────────────────────────────────
DOC_PATHS = [
    DATA_DIR / "sw_upstage_output"  / "inha_notice_data.json",
    DATA_DIR / "sw_upstage_output_2" / "inha_sw_notice_157275_to_166292.json",
    DATA_DIR / "sw_upstage_output_3" / "inha_notice_data3.json",
    DATA_DIR / "pr_data"             / "inha_pr.json",
]

QA_PATHS = [
    DATA_DIR / "sw_upstage_output"  / "inha_notice_qa.json",
    DATA_DIR / "sw_upstage_output_2" / "inha_sw_notice_qa_157275_to_166292.json",
    DATA_DIR / "sw_upstage_output_3" / "swuniv_notice_qa3.json",
    DATA_DIR / "pr_data"             / "inha_pr_qa.json",
]

# ── 임베딩 모델 ───────────────────────────────────────────────────────────────
EMBED_MODEL_ID   = "dragonkue/BGE-m3-ko"
EMBED_BATCH_SIZE = 8

# ── 청킹 ──────────────────────────────────────────────────────────────────────
CHUNK_THRESHOLD = 2000
CHUNK_SIZE      = 1500
CHUNK_OVERLAP   = 150

# ── Qdrant ────────────────────────────────────────────────────────────────────
QDRANT_URL      = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY  = os.getenv("QDRANT_API_KEY") or None
VECTOR_SIZE     = 1024
COLLECTION_DOCS = "documents"
COLLECTION_QA   = "qa_pairs"

# ── 탄소 모니터링 ─────────────────────────────────────────────────────────────
CARBON_MONITOR_ENABLED     = os.getenv("CARBON_MONITOR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
CARBON_INTENSITY_G_PER_KWH = float(os.getenv("CARBON_INTENSITY_G_PER_KWH", "350.0"))
CARBON_GPU_INDEX            = int(os.getenv("CARBON_GPU_INDEX", "0"))
CARBON_SAMPLE_INTERVAL      = float(os.getenv("CARBON_SAMPLE_INTERVAL", "0.1"))
_carbon_log_env             = os.getenv("CARBON_LOG_PATH", "").strip()
CARBON_LOG_PATH             = Path(_carbon_log_env) if _carbon_log_env else BASE_DIR / "logs" / "carbon_metrics.jsonl"

# ── CIASC ─────────────────────────────────────────────────────────────────────
QA_SIMILARITY_THRESHOLD = float(os.getenv("QA_SIMILARITY_THRESHOLD", "0.75"))
TOP_K                   = 5
CIASC_BASE_THRESHOLD    = float(os.getenv("CIASC_BASE_THRESHOLD", "0.75"))
CIASC_CI_MIN            = float(os.getenv("CIASC_CI_MIN", "350"))
CIASC_CI_MAX            = float(os.getenv("CIASC_CI_MAX", "500"))
CIASC_THETA_MIN         = float(os.getenv("CIASC_THETA_MIN", "0.70"))
CIASC_THETA_MAX         = float(os.getenv("CIASC_THETA_MAX", "0.95"))
_ciasc_fixed            = os.getenv("CIASC_FIXED_CI", "").strip()
CIASC_FIXED_CI          = float(_ciasc_fixed) if _ciasc_fixed else None

# ── LM Studio ─────────────────────────────────────────────────────────────────
def _lm_studio_url() -> str:
    url = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
    if "localhost" not in url and "127.0.0.1" not in url:
        return url
    try:
        is_wsl = "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return url
    if not is_wsl:
        return url
    try:
        import subprocess
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=2,
        )
        gateway = result.stdout.split()[2]
        return url.replace("localhost", gateway).replace("127.0.0.1", gateway)
    except Exception:
        return url

LM_STUDIO_URL    = _lm_studio_url()
LM_STUDIO_MODEL  = os.getenv("LM_STUDIO_MODEL", "")
LM_TEMPERATURE   = 0.3
LM_MAX_TOKENS    = 4096
LM_CONTEXT_LIMIT = 2000
LM_SYSTEM_PROMPT = (
    "당신은 인하대학교 SW중심대학사업단 공지사항 안내 도우미입니다.\n"
    "아래 참고 문서를 바탕으로 질문에 간결하고 정확하게 답하세요.\n"
    "참고 문서에 없는 내용은 '해당 정보를 찾을 수 없습니다'라고 답하세요."
)
```

- [ ] **Step 2: config import 확인**

```bash
cd rag
python -c "import config; print(config.DATA_DIR); print(config.DOC_PATHS[0].exists())"
# 출력: .../data
#       True
cd ..
```

- [ ] **Step 3: 커밋**

```bash
git add rag/config.py
git commit -m "feat: update rag/config.py with data/ paths and carbon/CIASC settings"
```

---

## Task 5: rag/embed_pipeline.py 교체

**Files:**
- 수정: `rag/embed_pipeline.py`

develop 브랜치 버전으로 교체. carbon_monitor 통합 + `carbon/` sys.path 추가.

- [ ] **Step 1: `rag/embed_pipeline.py` 전체 교체**

```python
"""
EcoCache RAG 임베딩 파이프라인
데이터 로드 → 전처리 → 청킹 → BGE-m3-ko 임베딩 → Qdrant 업서트
"""

import json
import logging
import sys
import uuid
from pathlib import Path

_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_CARBON_DIR))

import torch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

import config
from carbon_monitor import CarbonMonitor

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
carbon_monitor = CarbonMonitor.from_config(config)


def make_point_id(doc_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{chunk_index}"))


def batched(iterable, size: int):
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def load_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all_docs() -> list[dict]:
    docs = []
    for p in config.DOC_PATHS:
        data = load_json(p)
        docs.extend(data)
        logger.info(f"  로드: {p.name} ({len(data)}건)")
    return docs


def load_all_qas() -> list[dict]:
    qas = []
    for p in config.QA_PATHS:
        data = load_json(p)
        qas.extend(data)
        logger.info(f"  로드: {p.name} ({len(data)}건)")
    return qas


splitter = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", "。", "."],
    chunk_size=config.CHUNK_SIZE,
    chunk_overlap=config.CHUNK_OVERLAP,
    length_function=len,
)


def build_doc_text(doc: dict) -> str:
    title = doc["meta"].get("title", "")
    raw   = doc["content"].get("raw_text", "").strip()
    if raw:
        return f"[제목] {title}\n[날짜] {doc['meta'].get('published_at', '')}\n\n{raw}"
    attachments = doc["meta"].get("attachments", [])
    if attachments:
        filenames = ", ".join(a.get("filename", "") for a in attachments if a.get("filename"))
        return f"[제목] {title}\n[첨부] {filenames}"
    logger.warning(f"[WARN] 제목만으로 임베딩: {doc['doc_id']}")
    return f"[제목] {title}"


def prepare_doc_chunks(doc: dict) -> list[dict]:
    text   = build_doc_text(doc)
    doc_id = doc["doc_id"]
    chunks_text = [text] if len(text) <= config.CHUNK_THRESHOLD else splitter.split_text(text)
    return [
        {
            "point_id": make_point_id(doc_id, i),
            "text":     chunk,
            "payload": {
                "doc_id":       doc_id,
                "chunk_index":  i,
                "chunk_total":  len(chunks_text),
                "title":        doc["meta"].get("title", ""),
                "published_at": doc["meta"].get("published_at", ""),
                "board_type":   doc["source"].get("board_type", ""),
                "board_name":   doc["source"].get("board_name", ""),
                "url":          doc["source"].get("url", ""),
                "text":         chunk,
            },
        }
        for i, chunk in enumerate(chunks_text)
    ]


def prepare_qa_chunks(qa: dict) -> dict:
    qa_id  = qa["qa_id"]
    q_text = qa["question"]["text"]
    a_text = qa["answer"]["text"]
    text   = f"Q: {q_text}\nA: {a_text}"
    return {
        "point_id": make_point_id(qa_id, 0),
        "text":     text,
        "payload": {
            "qa_id":         qa_id,
            "source_doc_id": qa.get("source_doc_id", ""),
            "question":      q_text,
            "answer":        a_text,
            "reference_url": qa["answer"].get("reference_url", ""),
            "text":          text,
        },
    }


def load_embed_model() -> SentenceTransformer:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"임베딩 모델 로드: {config.EMBED_MODEL_ID} (device={device})")
    kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
    return SentenceTransformer(config.EMBED_MODEL_ID, device=device, model_kwargs=kwargs)


def safe_encode(model: SentenceTransformer, texts: list[str]) -> list | None:
    try:
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
    except Exception as e:
        logger.warning(f"[SKIP] 임베딩 실패 배치 스킵: {e}")
        return None


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)


def init_collections(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    for name in (config.COLLECTION_DOCS, config.COLLECTION_QA):
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=config.VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"컬렉션 생성: {name}")
        else:
            logger.info(f"컬렉션 기존 유지: {name}")


def upsert_chunks(client: QdrantClient, collection: str,
                  chunks: list[dict], model: SentenceTransformer) -> int:
    total_upserted = 0
    for batch in tqdm(list(batched(chunks, config.EMBED_BATCH_SIZE)),
                      desc=f"  {collection}", unit="batch"):
        texts   = [c["text"] for c in batch]
        vectors = safe_encode(model, texts)
        if vectors is None:
            continue
        points = [
            PointStruct(id=c["point_id"], vector=v, payload=c["payload"])
            for c, v in zip(batch, vectors)
        ]
        client.upsert(collection_name=collection, points=points)
        total_upserted += len(points)
    return total_upserted


def run_pipeline() -> None:
    logger.info("=" * 60)
    logger.info("EcoCache 임베딩 파이프라인 시작")
    logger.info("=" * 60)

    logger.info("[1/5] 문서 로드")
    docs = load_all_docs()
    logger.info(f"      총 {len(docs)}개 문서")

    logger.info("[2/5] QA 로드")
    qas = load_all_qas()
    logger.info(f"      총 {len(qas)}개 QA 페어")

    logger.info("[3/5] 전처리 및 청킹")
    doc_chunks = []
    for doc in docs:
        doc_chunks.extend(prepare_doc_chunks(doc))
    qa_chunks = [prepare_qa_chunks(qa) for qa in qas]
    logger.info(f"      문서 청크: {len(doc_chunks)}개 / QA 청크: {len(qa_chunks)}개")

    logger.info("[4/5] 임베딩 모델 로드")
    model = load_embed_model()

    logger.info("[5/5] Qdrant 업서트")
    client = get_qdrant_client()
    init_collections(client)

    n_docs, doc_metrics = carbon_monitor.run(
        "documents_embedding", upsert_chunks,
        client, config.COLLECTION_DOCS, doc_chunks, model,
        extra={"collection": config.COLLECTION_DOCS, "chunk_count": len(doc_chunks)},
    )
    n_qas, qa_metrics = carbon_monitor.run(
        "qa_embedding", upsert_chunks,
        client, config.COLLECTION_QA, qa_chunks, model,
        extra={"collection": config.COLLECTION_QA, "chunk_count": len(qa_chunks)},
    )
    logger.info(f"  carbon documents: {doc_metrics}")
    logger.info(f"  carbon qa_pairs:  {qa_metrics}")

    logger.info("검증")
    info_doc = client.get_collection(config.COLLECTION_DOCS)
    info_qa  = client.get_collection(config.COLLECTION_QA)
    logger.info(f"  documents 벡터 수: {info_doc.points_count} (업서트: {n_docs})")
    logger.info(f"  qa_pairs  벡터 수: {info_qa.points_count}  (업서트: {n_qas})")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
```

- [ ] **Step 2: 임포트 확인 (Qdrant 미기동 상태에서 문법 체크만)**

```bash
cd rag
python -c "import embed_pipeline; print('import OK')"
# 출력: import OK
cd ..
```

- [ ] **Step 3: 커밋**

```bash
git add rag/embed_pipeline.py
git commit -m "feat: replace embed_pipeline.py with develop version (carbon_monitor integrated)"
```

---

## Task 6: rag/baseline_ciasc.py 신규 생성

**Files:**
- 생성: `rag/baseline_ciasc.py`

- [ ] **Step 1: `rag/baseline_ciasc.py` 작성**

```python
"""
Baseline 3 — CIASC (Carbon Intensity Adaptive Semantic Cache)

Electricity Maps API로 현재 탄소 집약도(CI)를 조회해 동적으로
QA 캐시 임계값 θ(t)를 결정한다.

θ(t) = CIASC_BASE_THRESHOLD − α × (ci_norm − 0.5)
ci_norm = clamp((CI − CIASC_CI_MIN) / (CIASC_CI_MAX − CIASC_CI_MIN), 0, 1)
범위: [CIASC_THETA_MIN, CIASC_THETA_MAX]

CI가 높을수록(탄소 배출이 많을수록) θ가 낮아져 캐시 히트가 쉬워지고
(문서 재검색을 줄여 전력 절감), CI가 낮을수록 θ가 높아져 더 정확한
문서를 검색한다.
"""

import sys
from pathlib import Path

_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_CARBON_DIR))

import config
from retriever_base import BaseRetriever, search


class CIASCRetriever(BaseRetriever):
    def __init__(self, alpha: float = 0.15):
        self.alpha = alpha

    def retrieve(self, query: str, filters: dict | None = None,
                 top_k: int = config.TOP_K) -> dict:
        threshold = self._get_threshold()

        qa_results = search(query, config.COLLECTION_QA, top_k=top_k, filters=filters)
        qa_top1    = qa_results[0]["score"] if qa_results else None

        if qa_results and qa_top1 >= threshold:
            return {
                "source":        "qa_pairs",
                "results":       qa_results,
                "query":         query,
                "qa_top1_score": qa_top1,
            }

        doc_results = search(query, config.COLLECTION_DOCS, top_k=top_k, filters=filters)
        return {
            "source":        "documents",
            "results":       doc_results,
            "query":         query,
            "qa_top1_score": qa_top1,
        }

    def _get_threshold(self) -> float:
        try:
            from carbon_optimizer import get_optimizer
            opt = get_optimizer()
            ci  = opt.get_current_ci()
            return opt.get_adaptive_threshold(ci=ci, alpha=self.alpha)
        except Exception:
            return config.QA_SIMILARITY_THRESHOLD
```

- [ ] **Step 2: 임포트 확인**

```bash
cd rag
python -c "from baseline_ciasc import CIASCRetriever; print('import OK')"
# 출력: import OK
cd ..
```

- [ ] **Step 3: 커밋**

```bash
git add rag/baseline_ciasc.py
git commit -m "feat: add CIASCRetriever baseline (carbon-intensity adaptive cache)"
```

---

## Task 7: rag/query.py 업데이트

**Files:**
- 수정: `rag/query.py`

`ciasc` 모드 추가 + `carbon_monitor`로 retrieval/LLM 탄소 측정.

- [ ] **Step 1: `rag/query.py` 전체 교체**

```python
"""
EcoCache RAG 쿼리 인터페이스

--mode b1 / pure_rag       : Baseline 1 — documents만 검색
--mode b2 / semantic_cache : Baseline 2 — QA 캐시 → documents fallback (기본값)
--mode ciasc               : Baseline 3 — CI 연동 동적 threshold

사용법:
  python query.py "질문" [--mode b1|b2|ciasc] [옵션]
  python query.py "질문" --generate
  python query.py "질문" --log --log-file logs/my.jsonl
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_CARBON_DIR))

import config
from retriever_base import BaseRetriever
from baseline_pure_rag import PureRAGRetriever
from baseline_semantic_cache import SemanticCacheRetriever
from baseline_ciasc import CIASCRetriever
from carbon_monitor import CarbonMonitor

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)

carbon_monitor = CarbonMonitor.from_config(config)

MODES: dict[str, type[BaseRetriever]] = {
    "b1":             PureRAGRetriever,
    "pure_rag":       PureRAGRetriever,
    "b2":             SemanticCacheRetriever,
    "semantic_cache": SemanticCacheRetriever,
    "ciasc":          CIASCRetriever,
}


def get_retriever(mode: str = "b2") -> BaseRetriever:
    cls = MODES.get(mode)
    if cls is None:
        raise ValueError(f"알 수 없는 mode: {mode!r}. 선택 가능: {list(MODES)}")
    return cls()


def rag_search(query: str, mode: str = "b2",
               filters: dict | None = None) -> dict:
    retriever = get_retriever(mode)
    result, metrics = carbon_monitor.run(
        f"{mode}_retrieval",
        retriever.retrieve,
        query,
        filters=filters,
        extra={"mode": mode},
    )
    result.setdefault("metrics", {})["retrieval"] = metrics
    return result


def _config_snapshot(mode: str) -> dict:
    return {
        "mode":                    mode,
        "embed_model":             config.EMBED_MODEL_ID,
        "vector_size":             config.VECTOR_SIZE,
        "chunk_threshold":         config.CHUNK_THRESHOLD,
        "chunk_size":              config.CHUNK_SIZE,
        "chunk_overlap":           config.CHUNK_OVERLAP,
        "qa_similarity_threshold": config.QA_SIMILARITY_THRESHOLD,
        "top_k":                   config.TOP_K,
        "qdrant_url":              config.QDRANT_URL,
        "collection_docs":         config.COLLECTION_DOCS,
        "collection_qa":           config.COLLECTION_QA,
        "carbon_monitor_enabled":  config.CARBON_MONITOR_ENABLED,
        "carbon_intensity_g_per_kwh": config.CARBON_INTENSITY_G_PER_KWH,
    }


def log_result(result: dict, log_file: str | Path = "eval_log.jsonl",
               filters: dict | None = None, mode: str = "b2") -> None:
    entry = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "config":         _config_snapshot(mode),
        "query":          result["query"],
        "filters":        filters,
        "source":         result["source"],
        "qa_top1_score":  result.get("qa_top1_score"),
        "carbon_metrics": result.get("metrics", {}),
        "results": [
            {
                "rank":  i + 1,
                "score": r["score"],
                **(_qa_summary(r["payload"]) if result["source"] == "qa_pairs"
                   else _doc_summary(r["payload"])),
            }
            for i, r in enumerate(result["results"])
        ],
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _qa_summary(payload: dict) -> dict:
    return {
        "qa_id":    payload.get("qa_id", ""),
        "question": payload.get("question", ""),
        "answer":   payload.get("answer", "")[:120],
    }


def _doc_summary(payload: dict) -> dict:
    return {
        "doc_id":       payload.get("doc_id", ""),
        "chunk_index":  payload.get("chunk_index", 0),
        "title":        payload.get("title", ""),
        "published_at": payload.get("published_at", ""),
        "text_preview": payload.get("text", "")[:120],
    }


def _build_context(result: dict) -> str:
    per_doc = max(1, config.LM_CONTEXT_LIMIT // max(len(result["results"]), 1))
    parts = []
    for r in result["results"]:
        p = r["payload"]
        if result["source"] == "qa_pairs":
            parts.append(f"Q: {p.get('question', '')}\nA: {p.get('answer', '')}")
        else:
            text = p.get("text", "")[:per_doc]
            parts.append(f"[{p.get('title', '')} / {p.get('published_at', '')}]\n{text}")
    return "\n\n---\n\n".join(parts)


def generate_answer(query: str, rag_result: dict) -> str:
    if not config.LM_STUDIO_MODEL:
        raise ValueError(
            "LM_STUDIO_MODEL 환경변수가 설정되지 않았습니다. "
            ".env에 LM_STUDIO_MODEL=<모델명>을 추가하세요."
        )
    from openai import OpenAI

    context   = _build_context(rag_result)
    lm_client = OpenAI(base_url=config.LM_STUDIO_URL, api_key="lm-studio")

    def request_completion():
        resp = lm_client.chat.completions.create(
            model=config.LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content": config.LM_SYSTEM_PROMPT},
                {"role": "user",   "content": f"참고 문서:\n{context}\n\n질문: {query}"},
            ],
            temperature=config.LM_TEMPERATURE,
            max_tokens=config.LM_MAX_TOKENS,
        )
        return resp.choices[0].message.content

    answer, metrics = carbon_monitor.run(
        "llm_generation",
        request_completion,
        extra={"source": rag_result["source"], "context_docs": len(rag_result["results"])},
    )
    rag_result.setdefault("metrics", {})["llm_generation"] = metrics
    return answer


def print_results(result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"쿼리   : {result['query']}")
    print(f"출처   : {result['source']}")
    if result.get("metrics", {}).get("retrieval"):
        m = result["metrics"]["retrieval"]
        print(f"탄소   : {m.get('co2_g', 0)*1000:.4f} mg  ({m.get('duration_sec', 0):.2f}s)")
    print(f"{'='*60}")
    for i, r in enumerate(result["results"], 1):
        score   = r["score"]
        payload = r["payload"]
        print(f"\n[{i}] 유사도: {score:.4f}")
        if result["source"] == "qa_pairs":
            print(f"  Q: {payload.get('question', '')}")
            print(f"  A: {payload.get('answer', '')}")
            print(f"  URL: {payload.get('reference_url', '')}")
        else:
            print(f"  제목: {payload.get('title', '')}")
            print(f"  날짜: {payload.get('published_at', '')}")
            print(f"  청크: {payload.get('chunk_index', 0)+1}/{payload.get('chunk_total', 1)}")
            print(f"  본문: {payload.get('text', '')[:200]}...")
            print(f"  URL: {payload.get('url', '')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python query.py \"질문\" [옵션]")
        print("옵션:")
        print("  --mode <모드>       b1|pure_rag / b2|semantic_cache / ciasc (기본: b2)")
        print("  --log               결과를 eval_log.jsonl에 기록")
        print("  --log-file <경로>   로그 파일 경로 지정")
        print("  --generate          LM Studio로 자연어 답변 생성")
        print("  --board_type <값>   필터: notice | pr")
        sys.exit(1)

    query_text = sys.argv[1]
    mode       = "b2"
    do_log     = False
    do_generate = False
    log_file   = Path("eval_log.jsonl")
    filters: dict = {}

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]; i += 2
        elif args[i] == "--log":
            do_log = True; i += 1
        elif args[i] == "--log-file" and i + 1 < len(args):
            log_file = Path(args[i + 1]); do_log = True; i += 2
        elif args[i] == "--generate":
            do_generate = True; i += 1
        elif args[i].startswith("--") and i + 1 < len(args):
            filters[args[i][2:]] = args[i + 1]; i += 2
        else:
            i += 1

    result = rag_search(query_text, mode=mode, filters=filters if filters else None)
    print_results(result)

    if do_generate:
        try:
            answer = generate_answer(query_text, result)
            print(f"\n{'='*60}")
            print(" 생성된 답변")
            print(f"{'='*60}")
            print(answer)
            print()
        except Exception as e:
            print(f"\n[오류] LLM 답변 생성 실패: {e}")

    if do_log:
        log_result(result, log_file=log_file,
                   filters=filters if filters else None, mode=mode)
        print(f"\n[로그] {log_file} 에 기록됨")
```

- [ ] **Step 2: 임포트 확인**

```bash
cd rag
python -c "import query; print('import OK')"
# 출력: import OK
cd ..
```

- [ ] **Step 3: 커밋**

```bash
git add rag/query.py
git commit -m "feat: update query.py with ciasc mode and carbon_monitor tracking"
```

---

## Task 8: rag/run_eval.py 교체

**Files:**
- 수정: `rag/run_eval.py`

develop 버전으로 교체 (b1/b2/ciasc 모드). `carbon/` sys.path 추가 및 `rag_search` import를 업데이트된 query.py에서 가져옴.

- [ ] **Step 1: `rag/run_eval.py` 전체 교체**

```python
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
    try:
        import sys
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).parent.parent / "carbon"))
        from carbon_optimizer import get_optimizer
        opt   = get_optimizer()
        ci    = opt.get_current_ci()
        theta = opt.get_adaptive_threshold(ci=ci, alpha=alpha)
        print(f"  [CIASC] 현재 CI={ci:.0f} gCO2/kWh, α={alpha} → θ(t)={theta:.4f}")
        return theta
    except ImportError:
        print("  [CIASC] carbon_optimizer 없음 → fallback θ=0.7375")
        return 0.7375


def apply_mode(mode: str, alpha: float = 0.15) -> float:
    cfg = MODES[mode]
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

    records = []
    total_co2_g      = 0.0
    total_latency_ms = 0.0
    cache_hits       = 0

    for idx, test in enumerate(tests, 1):
        if mode == "ciasc":
            threshold = apply_mode("ciasc", alpha=alpha)

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

        status     = "✓" if (hit_source and (hit_doc is None or hit_doc)) else "✗"
        qa_str     = f"  (QA top1={result['qa_top1_score']:.4f})" if result.get("qa_top1_score") else ""
        co2_str    = f"  CO2={query_co2_g*1000:.3f}mg" if query_co2_g else ""
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
        cfg     = group[0]["config"]
        total   = len(group)
        qa_cnt  = sum(1 for e in group if e["source"] == "qa_pairs")
        scores  = [e["results"][0]["score"] for e in group if e["results"]]
        avg     = sum(scores) / len(scores) if scores else 0.0
        qa_sc   = [e["qa_top1_score"] for e in group if e.get("qa_top1_score") is not None]
        avg_qa  = sum(qa_sc) / len(qa_sc) if qa_sc else 0.0

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
```

- [ ] **Step 2: 임포트 확인**

```bash
cd rag
python -c "import run_eval; print('import OK')"
# 출력: import OK
cd ..
```

- [ ] **Step 3: 커밋**

```bash
git add rag/run_eval.py
git commit -m "feat: replace run_eval.py with develop version (b1/b2/ciasc modes)"
```

---

## Task 9: api/main.py — co2_grams 실제 통합

**Files:**
- 수정: `api/main.py`

`CarbonMonitor.track()`으로 `/chat` 핸들러를 감싸 실측 CO2를 반환.

- [ ] **Step 1: `api/main.py` 전체 교체**

```python
"""
EcoCache RAG API

POST /chat  {"query": "..."}
  → retriever.retrieve()  (b2 semantic cache 기본)
  → carbon_monitor로 CO2 측정
  → generate_answer() via LM Studio (없으면 null)
  → ChatResponse (cache_hit, co2_grams 포함)

실행:
  cd api/
  uvicorn main:app --reload --port 8000
"""

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

_RAG_DIR    = Path(__file__).parent.parent / "rag"
_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_RAG_DIR))
sys.path.insert(0, str(_CARBON_DIR))

from fastapi import FastAPI

import config
from baseline_semantic_cache import SemanticCacheRetriever
from query import generate_answer
from carbon_monitor import CarbonMonitor
from schemas import ChatRequest, ChatResponse, ChatResult

carbon_monitor = CarbonMonitor.from_config(config)
_retriever: SemanticCacheRetriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _retriever
    _retriever = SemanticCacheRetriever()
    from retriever_base import get_model, get_client
    get_model()
    get_client()
    yield


app = FastAPI(title="EcoCache RAG API", version="0.2.0", lifespan=lifespan)


def _extract_source_ids(result: dict) -> list[str]:
    ids = []
    for r in result["results"]:
        p     = r["payload"]
        doc_id = p.get("doc_id") or p.get("source_doc_id") or p.get("qa_id")
        if doc_id:
            ids.append(doc_id)
    return list(dict.fromkeys(ids))


def _get_current_ci() -> float | None:
    try:
        from carbon_optimizer import get_optimizer
        return get_optimizer().get_current_ci()
    except Exception:
        return None


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    start = time.perf_counter()

    try:
        with carbon_monitor.track("api_retrieval",
                                  extra={"endpoint": "/chat"}) as state:
            result = _retriever.retrieve(req.query)

        retrieval_metrics = state["metrics"] or {}
        co2_grams         = retrieval_metrics.get("co2_g")
        latency_ms        = round((time.perf_counter() - start) * 1000, 1)

        top1_score = result["results"][0]["score"] if result["results"] else None
        cache_hit  = result["source"] == "qa_pairs"
        sources    = _extract_source_ids(result)

        response_text: str | None = None
        try:
            with carbon_monitor.track("api_llm_generation") as llm_state:
                response_text = generate_answer(req.query, result)
            if llm_state["metrics"] and co2_grams is not None:
                co2_grams = round(co2_grams + llm_state["metrics"].get("co2_g", 0.0), 6)
            elif llm_state["metrics"]:
                co2_grams = llm_state["metrics"].get("co2_g")
        except Exception:
            pass

        return ChatResponse(
            success=True,
            error=None,
            result=ChatResult(
                response=response_text,
                similarity=top1_score,
                cache_hit=cache_hit,
                latency=latency_ms,
                co2_grams=co2_grams,
                ci_g_per_kwh=_get_current_ci(),
                sources=sources,
            ),
        )

    except Exception as exc:
        return ChatResponse(success=False, error=str(exc), result=None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 2: 임포트 확인**

```bash
cd api
python -c "import main; print('import OK')"
# 출력: import OK
cd ..
```

- [ ] **Step 3: 커밋**

```bash
git add api/main.py
git commit -m "feat: integrate CarbonMonitor into /chat endpoint (co2_grams real measurement)"
```

---

## Task 10: requirements 파일 + .env.example

**Files:**
- 수정: `rag/requirements.txt`
- 수정: `api/requirements.txt`
- 생성: `.env.example`

- [ ] **Step 1: `rag/requirements.txt` 업데이트**

```
qdrant-client>=1.9.0
sentence-transformers>=3.0.0
langchain-text-splitters>=0.2.0
python-dotenv>=1.0.0
tqdm>=4.66.0
torch>=2.0.0
streamlit>=1.35.0
altair>=5.0.0
openai>=1.0.0
codecarbon>=2.4.0
pynvml>=11.5.0
```

- [ ] **Step 2: `api/requirements.txt` 업데이트**

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-dotenv>=1.0.0
```

- [ ] **Step 3: `.env.example` 작성**

```
# ── Qdrant ────────────────────────────────────────────────────────────────────
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# ── PostgreSQL (collector + infra/docker-compose.yml) ─────────────────────────
POSTGRES_DB=ecocache
POSTGRES_USER=ecocache
POSTGRES_PASSWORD=ecocache
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# ── Electricity Maps API (탄소 집약도 실시간 조회) ─────────────────────────────
ELECTRICITY_MAPS_API_KEY=
ELECTRICITY_MAPS_ZONE=KR

# ── Carbon Monitor ────────────────────────────────────────────────────────────
CARBON_MONITOR_ENABLED=true
CARBON_INTENSITY_G_PER_KWH=350.0
CARBON_GPU_INDEX=0
CARBON_SAMPLE_INTERVAL=0.1
# CARBON_LOG_PATH=rag/logs/carbon_metrics.jsonl

# ── CIASC (Carbon Intensity Adaptive Semantic Cache) ──────────────────────────
CIASC_BASE_THRESHOLD=0.75
CIASC_CI_MIN=350
CIASC_CI_MAX=500
CIASC_THETA_MIN=0.70
CIASC_THETA_MAX=0.95
# CIASC_FIXED_CI=385     # 고정값 사용 시 주석 해제 (테스트용)

# ── LM Studio ─────────────────────────────────────────────────────────────────
LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=
# LM_STUDIO_MODEL=llama-3.2-3b-instruct
```

- [ ] **Step 4: 커밋**

```bash
git add rag/requirements.txt api/requirements.txt .env.example
git commit -m "chore: update requirements and add .env.example"
```

---

## Task 11: README.md 작성

**Files:**
- 생성: `README.md`

- [ ] **Step 1: `README.md` 작성**

아래 내용 작성 (Task 11 상세 구현 단계 참고).

- [ ] **Step 2: 커밋**

```bash
git add README.md
git commit -m "docs: add integrated README"
```

> README 내용은 `superpowers:writing-plans` 실행 후 별도 생성 (Task 11 본문 참조).

---

## 최종 검증

- [ ] **전체 임포트 체인 확인**

```bash
cd rag
python -c "
import config, retriever_base, baseline_pure_rag
import baseline_semantic_cache, baseline_ciasc
import query, run_eval, embed_pipeline
print('모든 rag/ 임포트 성공')
"
cd ../carbon
python carbon_optimizer.py
cd ../api
python -c "import main; print('api 임포트 성공')"
cd ..
```

- [ ] **디렉토리 구조 확인**

```bash
find . -not -path './.git/*' -not -path './qdrant_data/*' \
       -not -path './__pycache__/*' -not -path './.idea/*' \
       -not -path '*/logs/*' -name '*.py' -o -name '*.yml' \
       -o -name '*.sql' -o -name '*.txt' -o -name '*.md' \
       | sort | grep -v __pycache__
```
