import time
import sqlite3
from datetime import datetime, timezone
from carbon_optimizer import get_optimizer
import os

EMAPS_ZONE = os.getenv("ELECTRICITY_MAPS_ZONE", "KR")
EMAPS_KEY = os.getenv("ELECTRICITY_MAPS_API_KEY")

def save_to_db(ci_value: float, source: str):
  try:
    # 로컬 파일 'carbon.db'에 연결 (없으면 자동 생성)
    conn = sqlite3.connect('carbon.db')
    cur = conn.cursor()

    # 테이블이 없으면 생성 (스키마 반영)
    cur.execute("""
                CREATE TABLE IF NOT EXISTS carbon_intensity_logs(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    zone_name TEXT,
                    g_per_kwh FLOAT, 
                    source TEXT
                )
          """)

    insert_query = """
                   INSERT INTO carbon_intensity_logs (timestamp, zone_name, g_per_kwh, source)
                   VALUES (?, ?, ?, ?) \
                   """
    cur.execute(insert_query, (datetime.now(timezone.utc).isoformat(), "KR", ci_value, source))

    conn.commit()
    print(f"[{datetime.now()}] 로컬 DB 저장 완료: {ci_value}g ({source})")
    conn.close()
  except Exception as e:
    print(f"DB 오류: {e}")


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
    time.sleep(10)


if __name__ == "__main__":
  run_collector()