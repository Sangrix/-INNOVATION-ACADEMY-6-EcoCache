import sys
import os
import time
from pathlib import Path
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv

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
        source   = "API" if EMAPS_KEY and opt._ci_cache["value"] is not None else "Static Proxy"
        save_to_db(ci_value, source)
        time.sleep(900)  # 15분


if __name__ == "__main__":
    run_collector()
