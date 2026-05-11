import time
import os
import psycopg2 # PostgreSQL
from datetime import datetime, timezone
from dotenv import load_dotenv
from carbon_optimizer import get_optimizer

load_dotenv()

EMAPS_ZONE = os.getenv("ELECTRICITY_MAPS_ZONE", "KR")
EMAPS_KEY = os.getenv("ELECTRICITY_MAPS_API_KEY")

# DB 연결 설정 (설정에 맞게 수정 필요)
DB_CONFIG = {
  "dbname": "postgres",
  "user": "postgres",
  "password": "password",
  "host": "localhost",
  "port": 5432
}


def save_to_db(ci_value: float, source: str):
  try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    insert_query = """
                   INSERT INTO carbon_intensity_logs (timestamp, zone_name, g_per_kwh, source)
                   VALUES (%s, %s, %s, %s) \
                   """
    # 현재 UTC 시각으로 저장
    cur.execute(insert_query, (datetime.now(timezone.utc), EMAPS_ZONE, ci_value, source))

    conn.commit()
    print(f"[{datetime.now()}] 저장 완료: {ci_value}g ({source})")

    cur.close()
    conn.close()
  except Exception as e:
    print(f"[{datetime.now()}] DB 오류: {e}")


def run_collector():
  print(f"CI 수집 시작 (지역: {EMAPS_ZONE})")
  opt = get_optimizer()

  while True:
    # 현재 CI 값 획득 (API 키가 없으면, Proxy 사용)
    ci_value = opt.get_current_ci()

    # 출처 확인 (API 호출 성공 시 value가 캐시에)
    source = "API" if EMAPS_KEY and opt._ci_cache["value"] is not None else "Static Proxy"

    # DB 저장
    save_to_db(ci_value, source)

    # 15분 대기
    time.sleep(900)


if __name__ == "__main__":
  run_collector()