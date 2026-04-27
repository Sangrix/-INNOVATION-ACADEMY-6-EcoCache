import requests
from datetime import datetime
import config  # 기존 설정값 참조

class CarbonAdaptiveOptimizer:
    def __init__(self):
        # 1주차 목표: 정적 프록시 데이터 (한국 시간대별 CI 평균)
        self.KR_CI_PROXIES = {
            0: 430, 3: 415, 6: 420, 9: 410, 12: 385, 15: 375, 18: 400, 21: 420
        }

    def get_current_ci(self) -> float:
        """현재 시간 기준 탄소 집약도 조회"""
        hour = datetime.now().hour
        closest_hour = min(self.KR_CI_PROXIES.keys(), key=lambda x: abs(x - hour))
        return self.KR_CI_PROXIES[closest_hour]

    def get_adaptive_threshold(self, ci: float = None) -> float:
        """
        θ(t) 동적 조정 알고리즘
        ci 인자가 없으면 자동으로 현재 CI를 가져와 계산함 (통합 편의성)
        """
        if ci is None:
            ci = self.get_current_ci()

        base_theta = config.QA_SIMILARITY_THRESHOLD  # 0.75
        alpha = 0.15  # 조정 계수 (2주차 실험 대상)

        # CI 350~500 범위를 0~1로 정규화 및 범위 제한(Clamping)
        ci_norm = (ci - 350) / 150
        ci_norm = max(0.0, min(1.0, ci_norm))

        # 핵심 수식: CI가 높을수록 theta는 낮아짐 (캐시 히트 유도)
        theta = base_theta - (alpha * (ci_norm - 0.5))
        return round(theta, 4)

# ── query.py 연동을 위한 싱글톤 인터페이스 (추가 권장) ──────────────────────
_optimizer = None

def get_optimizer():
    global _optimizer
    if _optimizer is None:
        _optimizer = CarbonAdaptiveOptimizer()
    return _optimizer

if __name__ == "__main__":
    # 인자 없이 호출해도 작동하는지 테스트
    opt = get_optimizer()
    print(f"현재 시간 기반 동적 θ(t): {opt.get_adaptive_threshold()}")