import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# ── 입력 데이터 경로 ──────────────────────────────────────────────────────────
DOC_PATHS = [
    BASE_DIR / "sw_upstage_output"  / "inha_notice_data.json",
    BASE_DIR / "sw_upstage_output_2" / "inha_sw_notice_157275_to_166292.json",
    BASE_DIR / "sw_upstage_output_3" / "inha_notice_data3.json",
    BASE_DIR / "pr_data"             / "inha_pr.json",
]

QA_PATHS = [
    BASE_DIR / "sw_upstage_output"  / "inha_notice_qa.json",
    BASE_DIR / "sw_upstage_output_2" / "inha_sw_notice_qa_157275_to_166292.json",
    BASE_DIR / "sw_upstage_output_3" / "swuniv_notice_qa3.json",
    BASE_DIR / "pr_data"             / "inha_pr_qa.json",
]

# ── 임베딩 모델 ───────────────────────────────────────────────────────────────
EMBED_MODEL_ID   = "dragonkue/BGE-m3-ko"
EMBED_BATCH_SIZE = 8   # CPU 환경 기본값; GPU 사용 시 32로 늘릴 것

# ── 청킹 (모두 문자 수 기준) ──────────────────────────────────────────────────
CHUNK_THRESHOLD = 2000   # 이 이하면 단일 청크
CHUNK_SIZE      = 1500   # 청킹 적용 시 청크 크기
CHUNK_OVERLAP   = 150    # 오버랩

# ── Qdrant ────────────────────────────────────────────────────────────────────
QDRANT_URL      = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY  = os.getenv("QDRANT_API_KEY") or None
VECTOR_SIZE     = 1024
COLLECTION_DOCS = "documents"
COLLECTION_QA   = "qa_pairs"

CARBON_MONITOR_ENABLED = os.getenv("CARBON_MONITOR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
CARBON_INTENSITY_G_PER_KWH = float(os.getenv("CARBON_INTENSITY_G_PER_KWH", "350.0"))
CARBON_GPU_INDEX = int(os.getenv("CARBON_GPU_INDEX", "0"))
CARBON_SAMPLE_INTERVAL = float(os.getenv("CARBON_SAMPLE_INTERVAL", "0.1"))
_carbon_log_path = os.getenv("CARBON_LOG_PATH", "").strip()
CARBON_LOG_PATH = Path(_carbon_log_path) if _carbon_log_path else BASE_DIR / "carbon_metrics.jsonl"

# ── 검색 ──────────────────────────────────────────────────────────────────────
QA_SIMILARITY_THRESHOLD = 0.75
TOP_K = 5

# CIASC threshold settings
CIASC_BASE_THRESHOLD = float(os.getenv("CIASC_BASE_THRESHOLD", "0.75"))
CIASC_CI_MIN = float(os.getenv("CIASC_CI_MIN", "350"))
CIASC_CI_MAX = float(os.getenv("CIASC_CI_MAX", "500"))
CIASC_THETA_MIN = float(os.getenv("CIASC_THETA_MIN", "0.70"))
CIASC_THETA_MAX = float(os.getenv("CIASC_THETA_MAX", "0.95"))
_ciasc_fixed_ci = os.getenv("CIASC_FIXED_CI", "").strip()
CIASC_FIXED_CI = float(_ciasc_fixed_ci) if _ciasc_fixed_ci else None

# ── LM Studio ─────────────────────────────────────────────────────────────────
LM_STUDIO_URL    = os.getenv("LM_STUDIO_URL",   "http://localhost:1234/v1")
LM_STUDIO_MODEL  = os.getenv("LM_STUDIO_MODEL", "")
LM_TEMPERATURE   = 0.3
LM_MAX_TOKENS    = 512
LM_CONTEXT_LIMIT = 2000
LM_SYSTEM_PROMPT = (
    "당신은 인하대학교 SW중심대학사업단 공지사항 안내 도우미입니다.\n"
    "아래 참고 문서를 바탕으로 질문에 간결하고 정확하게 답하세요.\n"
    "참고 문서에 없는 내용은 '해당 정보를 찾을 수 없습니다'라고 답하세요."
)
