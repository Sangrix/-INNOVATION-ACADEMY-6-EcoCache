from datetime import datetime
from zoneinfo import ZoneInfo

import config


class CarbonAdaptiveOptimizer:
    def __init__(self):
        # 한국 시간대별 탄소 집약도 정적 프록시 값(gCO2/kWh).
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

    def get_current_ci(self) -> float:
        """현재 한국 시간 기준 탄소 집약도 값을 반환합니다."""
        if config.CIASC_FIXED_CI is not None:
            return float(config.CIASC_FIXED_CI)

        hour = datetime.now(ZoneInfo("Asia/Seoul")).hour
        closest_hour = min(self.KR_CI_BY_HOUR.keys(), key=lambda x: abs(x - hour))
        return float(self.KR_CI_BY_HOUR.get(closest_hour, self.DEFAULT_KR_CI))

    def get_adaptive_threshold(
        self,
        ci: float | None = None,
        alpha: float = 0.15,
        theta_min: float | None = None,
        theta_max: float | None = None,
    ) -> float:
        """
        CIASC 동적 threshold를 계산합니다.

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


_optimizer = None


def get_optimizer():
    global _optimizer
    if _optimizer is None:
        _optimizer = CarbonAdaptiveOptimizer()
    return _optimizer


if __name__ == "__main__":
    opt = get_optimizer()
    ci = opt.get_current_ci()
    print(f"현재 한국 시간 기준 CI: {ci}")
    for alpha in (0.25, 0.5, 1.0):
        print(f"alpha={alpha}: theta={opt.get_adaptive_threshold(ci=ci, alpha=alpha)}")
