#!/usr/bin/env bash
set -euo pipefail

# CIASC 그리드 스윕 평가 실행 스크립트
# 사용법: bash scripts/run_grid_eval.sh [grid_eval.py 옵션...]
# 예시  : bash scripts/run_grid_eval.sh --alpha-list 0.10,0.15 --ci-list 350,420,500

# ── 경로 설정 ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ── 기본값 ───────────────────────────────────────────────────────────────────
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

# ── 1. Qdrant 연결 확인 ──────────────────────────────────────────────────────
echo "Qdrant 연결 확인: ${QDRANT_URL}"
if curl -sf "${QDRANT_URL}/healthz" > /dev/null 2>&1; then
    echo "[OK] Qdrant 연결 성공"
else
    echo "[오류] Qdrant 연결 실패: ${QDRANT_URL}"
    echo "  Qdrant를 실행하거나 QDRANT_URL 환경변수를 설정하세요."
    echo "  예: docker run -p 6333:6333 qdrant/qdrant"
    exit 1
fi

# ── 2. Python venv 활성화 (있을 경우) ────────────────────────────────────────
if [ -f "${PROJECT_ROOT}/rag/.venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/rag/.venv/bin/activate"
    echo "[OK] venv 활성화: rag/.venv"
elif [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.venv/bin/activate"
    echo "[OK] venv 활성화: .venv"
else
    echo "[INFO] venv 없음 — 시스템 Python 사용"
fi

# ── 3. 출력 디렉토리 생성 ─────────────────────────────────────────────────────
mkdir -p "${PROJECT_ROOT}/docs/eval_reports"
mkdir -p "${PROJECT_ROOT}/rag/logs/grid"

# ── 4. 실험 실행 ─────────────────────────────────────────────────────────────
cd "${PROJECT_ROOT}/rag"
echo ""
echo "=== CIASC 그리드 스윕 평가 시작 ==="
python grid_eval.py \
    --output-dir "${PROJECT_ROOT}/docs/eval_reports" \
    --log-dir "${PROJECT_ROOT}/rag/logs/grid" \
    "$@"
echo "=== 완료 ==="

echo ""
echo "리포트 위치: ${PROJECT_ROOT}/docs/eval_reports/"
echo "로그 위치  : ${PROJECT_ROOT}/rag/logs/grid/"
