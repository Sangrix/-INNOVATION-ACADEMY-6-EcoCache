import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
sys.path.insert(0, str(Path(__file__).parent))

from carbon_optimizer import get_optimizer
import config

load_dotenv()

EMAPS_ZONE = os.getenv("ELECTRICITY_MAPS_ZONE", "KR")
EMAPS_KEY  = os.getenv("ELECTRICITY_MAPS_API_KEY")

DB_CONFIG = config.DB_CONFIG


def get_latest_ci_from_db() -> float | None:
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute(
            "SELECT g_per_kwh FROM carbon_intensity_logs"
            " ORDER BY timestamp DESC LIMIT 1"
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return float(row[0]) if row else None
    except Exception as e:
        print(f"[WARN] DB CI 조회 실패: {e}")
        return None


async def save_to_db(ci_value: float, source: str) -> None:
    def _sync_write():
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur  = conn.cursor()
            cur.execute(
                "INSERT INTO carbon_intensity_logs"
                " (timestamp, zone_name, g_per_kwh, source)"
                " VALUES (%s, %s, %s, %s)",
                (datetime.now(timezone.utc), EMAPS_ZONE, ci_value, source),
            )
            conn.commit()
            print(f"[{datetime.now()}] 저장 완료: {ci_value}g/kWh ({source})")
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[{datetime.now()}] DB 오류: {e}")

    await asyncio.to_thread(_sync_write)


async def run_collector() -> None:
    print(f"CI 수집 시작 (지역: {EMAPS_ZONE})")
    opt = get_optimizer()
    while True:
        ci_value = opt.get_current_ci()
        source   = (
            "API"
            if EMAPS_KEY and opt._ci_cache["value"] is not None
            else "Static Proxy"
        )
        await save_to_db(ci_value, source)
        await asyncio.sleep(900)


if __name__ == "__main__":
    asyncio.run(run_collector())
