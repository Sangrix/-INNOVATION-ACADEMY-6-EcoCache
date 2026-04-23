"""
EcoCache RAG 임베딩 파이프라인
- 데이터 로드 → 전처리 → 청킹 → BGE-m3-ko 임베딩 → Qdrant 업서트
"""

import json
import logging
import uuid
from pathlib import Path

import torch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

import config

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def make_point_id(doc_id: str, chunk_index: int) -> str:
    """doc_id + chunk_index 조합으로 고정 UUID 생성 (재실행 시 upsert 덮어쓰기)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{chunk_index}"))


def batched(iterable, size: int):
    """리스트를 size 단위 배치로 분할."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


# ── 데이터 로드 ───────────────────────────────────────────────────────────────

def load_json(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all_docs() -> list[dict]:
    docs = []
    for p in config.DOC_PATHS:
        data = load_json(p)
        docs.extend(data)
        logger.info(f"  로드: {p.name} ({len(data)}건)")
    return docs


def load_all_qas() -> list[dict]:
    qas = []
    for p in config.QA_PATHS:
        data = load_json(p)
        qas.extend(data)
        logger.info(f"  로드: {p.name} ({len(data)}건)")
    return qas


# ── 전처리 및 청킹 ────────────────────────────────────────────────────────────

splitter = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", "。", "."],
    chunk_size=config.CHUNK_SIZE,
    chunk_overlap=config.CHUNK_OVERLAP,
    length_function=len,
)


def build_doc_text(doc: dict) -> str:
    """문서 텍스트를 조립한다. 빈 raw_text 정책을 적용."""
    title = doc["meta"].get("title", "")
    raw   = doc["content"].get("raw_text", "").strip()

    if raw:
        return f"[제목] {title}\n[날짜] {doc['meta'].get('published_at', '')}\n\n{raw}"

    # raw_text 없음 → 첨부파일명 fallback
    attachments = doc["meta"].get("attachments", [])
    if attachments:
        filenames = ", ".join(a.get("filename", "") for a in attachments if a.get("filename"))
        return f"[제목] {title}\n[첨부] {filenames}"

    # 제목만 존재
    logger.warning(f"[WARN] 제목만으로 임베딩: {doc['doc_id']}")
    return f"[제목] {title}"


def prepare_doc_chunks(doc: dict) -> list[dict]:
    """문서 1개를 전처리·청킹하여 chunk dict 리스트로 반환."""
    text = build_doc_text(doc)
    doc_id = doc["doc_id"]

    if len(text) <= config.CHUNK_THRESHOLD:
        chunks_text = [text]
    else:
        chunks_text = splitter.split_text(text)

    result = []
    for i, chunk in enumerate(chunks_text):
        result.append({
            "point_id":    make_point_id(doc_id, i),
            "text":        chunk,
            "payload": {
                "doc_id":       doc_id,
                "chunk_index":  i,
                "chunk_total":  len(chunks_text),
                "title":        doc["meta"].get("title", ""),
                "published_at": doc["meta"].get("published_at", ""),
                "board_type":   doc["source"].get("board_type", ""),
                "board_name":   doc["source"].get("board_name", ""),
                "url":          doc["source"].get("url", ""),
                "text":         chunk,
            },
        })
    return result


def prepare_qa_chunks(qa: dict) -> dict:
    """QA 1개를 단일 청크 dict로 반환."""
    qa_id = qa["qa_id"]
    q_text = qa["question"]["text"]
    a_text = qa["answer"]["text"]
    text   = f"Q: {q_text}\nA: {a_text}"
    return {
        "point_id": make_point_id(qa_id, 0),
        "text":     text,
        "payload": {
            "qa_id":         qa_id,
            "source_doc_id": qa.get("source_doc_id", ""),
            "question":      q_text,
            "answer":        a_text,
            "reference_url": qa["answer"].get("reference_url", ""),
            "text":          text,
        },
    }


# ── 임베딩 ────────────────────────────────────────────────────────────────────

def load_embed_model() -> SentenceTransformer:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"임베딩 모델 로드: {config.EMBED_MODEL_ID} (device={device})")
    kwargs = {}
    if device == "cuda":
        kwargs["torch_dtype"] = torch.float16
    return SentenceTransformer(config.EMBED_MODEL_ID, device=device, model_kwargs=kwargs)


def safe_encode(model: SentenceTransformer, texts: list[str]) -> list | None:
    try:
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
    except Exception as e:
        logger.warning(f"[SKIP] 임베딩 실패 배치 스킵: {e}")
        return None


# ── Qdrant ────────────────────────────────────────────────────────────────────

def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)


def init_collections(client: QdrantClient) -> None:
    """컬렉션이 없으면 생성, 있으면 그대로 유지 (upsert 세만틱)."""
    existing = {c.name for c in client.get_collections().collections}
    for name in (config.COLLECTION_DOCS, config.COLLECTION_QA):
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=config.VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"컬렉션 생성: {name}")
        else:
            logger.info(f"컬렉션 기존 유지: {name}")


def upsert_chunks(client: QdrantClient, collection: str, chunks: list[dict],
                  model: SentenceTransformer) -> int:
    """chunks를 배치 임베딩 후 Qdrant에 upsert. 성공한 포인트 수 반환."""
    total_upserted = 0
    for batch in tqdm(list(batched(chunks, config.EMBED_BATCH_SIZE)),
                      desc=f"  {collection}", unit="batch"):
        texts   = [c["text"] for c in batch]
        vectors = safe_encode(model, texts)
        if vectors is None:
            continue
        points = [
            PointStruct(id=c["point_id"], vector=v, payload=c["payload"])
            for c, v in zip(batch, vectors)
        ]
        client.upsert(collection_name=collection, points=points)
        total_upserted += len(points)
    return total_upserted


# ── 메인 ──────────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    logger.info("=" * 60)
    logger.info("EcoCache 임베딩 파이프라인 시작")
    logger.info("=" * 60)

    # 1. 데이터 로드
    logger.info("[1/5] 문서 로드")
    docs = load_all_docs()
    logger.info(f"      총 {len(docs)}개 문서")

    logger.info("[2/5] QA 로드")
    qas = load_all_qas()
    logger.info(f"      총 {len(qas)}개 QA 페어")

    # 2. 전처리 및 청킹
    logger.info("[3/5] 전처리 및 청킹")
    doc_chunks = []
    for doc in docs:
        doc_chunks.extend(prepare_doc_chunks(doc))
    qa_chunks = [prepare_qa_chunks(qa) for qa in qas]
    logger.info(f"      문서 청크: {len(doc_chunks)}개 / QA 청크: {len(qa_chunks)}개")

    # 3. 임베딩 모델 로드
    logger.info("[4/5] 임베딩 모델 로드")
    model = load_embed_model()

    # 4. Qdrant 연결 및 컬렉션 초기화
    logger.info("[5/5] Qdrant 업서트")
    client = get_qdrant_client()
    init_collections(client)

    # 5. 업서트
    n_docs = upsert_chunks(client, config.COLLECTION_DOCS, doc_chunks, model)
    n_qas  = upsert_chunks(client, config.COLLECTION_QA,  qa_chunks,  model)

    # 6. 검증
    logger.info("=" * 60)
    logger.info("검증")
    info_doc = client.get_collection(config.COLLECTION_DOCS)
    info_qa  = client.get_collection(config.COLLECTION_QA)
    logger.info(f"  documents  벡터 수: {info_doc.vectors_count} (업서트: {n_docs})")
    logger.info(f"  qa_pairs   벡터 수: {info_qa.vectors_count}  (업서트: {n_qas})")

    assert info_doc.vectors_count >= 136, "문서 벡터 수 부족"
    assert info_qa.vectors_count  == 136, "QA 벡터 수 불일치"
    logger.info("검증 통과 ✓")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
