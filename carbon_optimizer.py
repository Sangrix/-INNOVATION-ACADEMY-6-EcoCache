from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os

import requests
from dotenv import load_dotenv

import config

# 프로젝트 루트의 .env 로드 (.gitignore 처리된 파일)
load_dotenv()

_EMAPS_API_KEY = os.getenv("ELECTRICITY_MAPS_API_KEY")
_EMAPS_ZONE    = os.getenv("ELECTRICITY_MAPS_ZONE", "KR")

# 학생 플랜: zone 제한 없음, 엔드포인트는 Free Tier와 동일
_EMAPS_BASE_URL = "https://api.electricitymap.org/v3"

# 5분 캐시 — 동일 시간대에 쿼리가 몰려도 API 호출 1회로 처리
_CACHE_TTL_SEC = 300


class CarbonAdaptiveOptimizer:
    def __init__(self):
        # 한국 시간대별 탄소 집약도 정적 프록시 값(gCO2/kWh).
        # API 호출 실패 시 fallback으로 사용합니다.
        self.KR_CI_BY_HOUR = {
            0: 430,
            3: 415,
            6: 420,
            9: 410,
            12: 385,
            15: 375,
            18: 400,
            21: 420,
        }
        self.DEFAULT_KR_CI = 415

        # 인메모리 캐시: {"value": float | None, "fetched_at": datetime | None}
        self._ci_cache: dict = {"value": None, "fetched_at": None}

    # ------------------------------------------------------------------ #
    # Public: 외부에서 호출하는 매서드                                   #
    # ------------------------------------------------------------------ #

    def get_current_ci(self) -> float:
        """현재 탄소 집약도(gCO2/kWh)를 반환합니다.

        우선순위
        --------
        1. config.CIASC_FIXED_CI 설정 시 고정값 사용
        2. .env 에 ELECTRICITY_MAPS_API_KEY 있으면 실시간 API 호출
        3. API 키 없거나 호출 실패 시 정적 프록시로 fallback
        """
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
        """CIASC 동적 threshold를 계산합니다.

        원본 브랜치 수식:
            theta = base_theta - alpha * (ci_norm - 0.5)

        수정 사항:
        - CLI로 받은 alpha를 그대로 사용합니다.
        - 직전 threshold가 아닌 고정 base_theta를 기준으로 매번 새로 계산합니다.
        """
        if ci is None:
            ci = self.get_current_ci()

        theta_min = config.CIASC_THETA_MIN if theta_min is None else theta_min
        theta_max = config.CIASC_THETA_MAX if theta_max is None else theta_max

        ci_range = config.CIASC_CI_MAX - config.CIASC_CI_MIN
        ci_norm = 0.0 if ci_range == 0 else (ci - config.CIASC_CI_MIN) / ci_range
        ci_norm = max(0.0, min(1.0, ci_norm))

        theta = config.CIASC_BASE_THRESHOLD - (alpha * (ci_norm - 0.5))
        theta = max(theta_min, min(theta_max, theta))
        return round(theta, 4)

    # ------------------------------------------------------------------ #
    # Private : 클래스 내부에서만 쓰이는 매서드                          #
    # ------------------------------------------------------------------ #

    def _fetch_ci_from_api(self) -> float:
        """Electricity Maps API 에서 실시간 CI를 가져옵니다.

        - 학생 플랜: 엔드포인트 동일, zone 제한 없음
        - 5분 TTL 캐시로 불필요한 중복 호출 방지
        - 호출 실패 시 정적 프록시로 자동 fallback
        """
        now = datetime.now(timezone.utc)

        # 캐시 유효 여부 확인
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
            print(f"[WARN] Electricity Maps API HTTP {status} 오류, 정적 프록시로 fallback: {e}")
        except requests.exceptions.Timeout:
            print("[WARN] Electricity Maps API 타임아웃, 정적 프록시로 fallback")
        except Exception as e:
            print(f"[WARN] Electricity Maps API 호출 실패, 정적 프록시로 fallback: {e}")

        return self._ci_from_proxy()

    def _ci_from_proxy(self) -> float:
        """KST 시간대 기반 정적 프록시 테이블에서 CI를 반환합니다."""
        hour = datetime.now(ZoneInfo("Asia/Seoul")).hour
        closest_hour = min(self.KR_CI_BY_HOUR.keys(), key=lambda x: abs(x - hour))
        return float(self.KR_CI_BY_HOUR.get(closest_hour, self.DEFAULT_KR_CI))


# ------------------------------------------------------------------ #
# Singleton: _optimizer 전역 변수와 get_optimizer() 함수             #
# ------------------------------------------------------------------ #

_optimizer = None


def get_optimizer() -> CarbonAdaptiveOptimizer:
    global _optimizer
    if _optimizer is None:
        _optimizer = CarbonAdaptiveOptimizer()
    return _optimizer


# ------------------------------------------------------------------ #
# Quick smoke-test: 단위 테스트                                      #
# ------------------------------------------------------------------ #

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