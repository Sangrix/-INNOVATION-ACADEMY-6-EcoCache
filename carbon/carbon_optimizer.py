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

_EMAPS_API_KEY  = os.getenv("ELECTRICITY_MAPS_API_KEY")
_EMAPS_ZONE     = os.getenv("ELECTRICITY_MAPS_ZONE", "KR")
_EMAPS_BASE_URL = "https://api.electricitymap.org/v3"
_CACHE_TTL_SEC  = 300


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
        ci_norm  = 0.0 if ci_range == 0 else (ci - config.CIASC_CI_MIN) / ci_range
        ci_norm  = max(0.0, min(1.0, ci_norm))
        theta    = config.CIASC_BASE_THRESHOLD - (alpha * (ci_norm - 0.5))
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
        hour    = datetime.now(ZoneInfo("Asia/Seoul")).hour
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
    ci  = opt.get_current_ci()
    source = (
        f"Electricity Maps API (zone={_EMAPS_ZONE})"
        if _EMAPS_API_KEY and opt._ci_cache["value"] is not None
        else "정적 프록시"
    )
    print(f"현재 CI: {ci} gCO2/kWh  [source: {source}]")
    for alpha in (0.25, 0.5, 1.0):
        print(f"  alpha={alpha}: theta={opt.get_adaptive_threshold(ci=ci, alpha=alpha)}")
