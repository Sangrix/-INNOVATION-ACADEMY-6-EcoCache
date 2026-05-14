"""
EcoCache RAG 임베딩 파이프라인
데이터 로드 → 전처리 → 청킹 → BGE-m3-ko 임베딩 → Qdrant 업서트
"""

import json
import logging
import sys
import uuid
from pathlib import Path

_CARBON_DIR = Path(__file__).parent.parent / "carbon"
sys.path.insert(0, str(_CARBON_DIR))

import torch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

import config
from carbon_monitor import CarbonMonitor

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
carbon_monitor = CarbonMonitor.from_config(config)


def make_point_id(doc_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{chunk_index}"))


def batched(iterable, size: int):
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


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


splitter = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", "。", "."],
    chunk_size=config.CHUNK_SIZE,
    chunk_overlap=config.CHUNK_OVERLAP,
    length_function=len,
)


def build_doc_text(doc: dict) -> str:
    title = doc["meta"].get("title", "")
    raw   = doc["content"].get("raw_text", "").strip()
    if raw:
        return f"[제목] {title}\n[날짜] {doc['meta'].get('published_at', '')}\n\n{raw}"
    attachments = doc["meta"].get("attachments", [])
    if attachments:
        filenames = ", ".join(a.get("filename", "") for a in attachments if a.get("filename"))
        return f"[제목] {title}\n[첨부] {filenames}"
    logger.warning(f"[WARN] 제목만으로 임베딩: {doc['doc_id']}")
    return f"[제목] {title}"


def prepare_doc_chunks(doc: dict) -> list[dict]:
    text   = build_doc_text(doc)
    doc_id = doc["doc_id"]
    chunks_text = [text] if len(text) <= config.CHUNK_THRESHOLD else splitter.split_text(text)
    return [
        {
            "point_id": make_point_id(doc_id, i),
            "text":     chunk,
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
        }
        for i, chunk in enumerate(chunks_text)
    ]


def prepare_qa_chunks(qa: dict) -> dict:
    qa_id  = qa["qa_id"]
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


def load_embed_model() -> SentenceTransformer:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"임베딩 모델 로드: {config.EMBED_MODEL_ID} (device={device})")
    kwargs = {"torch_dtype": torch.float16} if device == "cuda" else {}
    return SentenceTransformer(config.EMBED_MODEL_ID, device=device, model_kwargs=kwargs)


def safe_encode(model: SentenceTransformer, texts: list[str]) -> list | None:
    try:
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
    except Exception as e:
        logger.warning(f"[SKIP] 임베딩 실패 배치 스킵: {e}")
        return None


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY)


def init_collections(client: QdrantClient) -> None:
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


def upsert_chunks(client: QdrantClient, collection: str,
                  chunks: list[dict], model: SentenceTransformer) -> int:
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


def run_pipeline() -> None:
    logger.info("=" * 60)
    logger.info("EcoCache 임베딩 파이프라인 시작")
    logger.info("=" * 60)

    logger.info("[1/5] 문서 로드")
    docs = load_all_docs()
    logger.info(f"      총 {len(docs)}개 문서")

    logger.info("[2/5] QA 로드")
    qas = load_all_qas()
    logger.info(f"      총 {len(qas)}개 QA 페어")

    logger.info("[3/5] 전처리 및 청킹")
    doc_chunks = []
    for doc in docs:
        doc_chunks.extend(prepare_doc_chunks(doc))
    qa_chunks = [prepare_qa_chunks(qa) for qa in qas]
    logger.info(f"      문서 청크: {len(doc_chunks)}개 / QA 청크: {len(qa_chunks)}개")

    logger.info("[4/5] 임베딩 모델 로드")
    model = load_embed_model()

    logger.info("[5/5] Qdrant 업서트")
    client = get_qdrant_client()
    init_collections(client)

    n_docs, doc_metrics = carbon_monitor.run(
        "documents_embedding", upsert_chunks,
        client, config.COLLECTION_DOCS, doc_chunks, model,
        extra={"collection": config.COLLECTION_DOCS, "chunk_count": len(doc_chunks)},
    )
    n_qas, qa_metrics = carbon_monitor.run(
        "qa_embedding", upsert_chunks,
        client, config.COLLECTION_QA, qa_chunks, model,
        extra={"collection": config.COLLECTION_QA, "chunk_count": len(qa_chunks)},
    )
    logger.info(f"  carbon documents: {doc_metrics}")
    logger.info(f"  carbon qa_pairs:  {qa_metrics}")

    logger.info("검증")
    info_doc = client.get_collection(config.COLLECTION_DOCS)
    info_qa  = client.get_collection(config.COLLECTION_QA)
    logger.info(f"  documents 벡터 수: {info_doc.points_count} (업서트: {n_docs})")
    logger.info(f"  qa_pairs  벡터 수: {info_qa.points_count}  (업서트: {n_qas})")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
