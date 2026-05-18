from __future__ import annotations

import os
from pathlib import Path

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("QDRANT_LOCAL_PATH", str(ROOT_DIR / "qdrant_local"))

from rag.langchain_pipeline import LangChainRagPipeline, get_cached_pipeline  # noqa: E402


st.set_page_config(
    page_title="EcoCache RAG Demo",
    page_icon="IH",
    layout="centered",
)

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(135deg, #f4f8ee 0%, #eef5f8 45%, #f7f3ea 100%);
    }
    .hero {
        border: 1px solid rgba(33, 64, 41, .15);
        border-radius: 24px;
        padding: 28px 30px;
        background: rgba(255, 255, 255, .78);
        box-shadow: 0 18px 45px rgba(37, 54, 42, .08);
        margin-bottom: 18px;
    }
    .hero h1 {
        margin: 0 0 8px 0;
        color: #173b2a;
        letter-spacing: -0.04em;
    }
    .hero p {
        margin: 0;
        color: #5c6b61;
        font-size: 1.02rem;
    }
    .metric-card {
        border: 1px solid rgba(33, 64, 41, .12);
        border-radius: 18px;
        padding: 16px 18px;
        background: rgba(255, 255, 255, .72);
    }
    .answer-card {
        border-radius: 22px;
        padding: 22px 24px;
        background: #18211c;
        color: #f5f7ee;
        box-shadow: 0 16px 40px rgba(17, 25, 20, .16);
        white-space: pre-wrap;
        line-height: 1.72;
    }
    .source-card {
        border-left: 4px solid #6d8f4f;
        background: rgba(255, 255, 255, .76);
        border-radius: 12px;
        padding: 12px 14px;
        margin: 8px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def get_pipeline(top_k: int, threshold: float) -> LangChainRagPipeline:
    return get_cached_pipeline(top_k=top_k, threshold=threshold)


st.markdown(
    """
    <div class="hero">
      <h1>SW중심대학 학사 도우미</h1>
      <p>EcoCache RAG 데모 · 캐시 히트, 유사도, 출처 URL을 함께 확인합니다.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("실행 설정")
    top_k = st.number_input("top_k", min_value=1, max_value=10, value=5, step=1)
    threshold = st.slider("threshold", min_value=0.5, max_value=0.95, value=0.75, step=0.05)
    generate = st.toggle("답변 생성", value=True)
    use_llm = st.toggle("LM Studio 사용", value=False)
    st.caption("LM Studio를 끄면 문서 검색 결과 기반 fallback 답변을 보여줍니다.")
    st.divider()
    st.caption(f"Qdrant path: {os.environ.get('QDRANT_LOCAL_PATH')}")

default_query = "2025-2학기 i-PAC 인증 콘테스트 신청 기간과 참여 대상은 어떻게 되나요?"
with st.form("query_form", clear_on_submit=False):
    query = st.text_input("질문", value=default_query, placeholder="학사 정보를 물어보세요")
    submitted = st.form_submit_button("질문 보내기", type="primary", use_container_width=True)

if submitted:
    if not query.strip():
        st.warning("질문을 입력하세요.")
        st.stop()

    try:
        with st.spinner("RAG 검색 중입니다..."):
            pipeline = get_pipeline(int(top_k), float(threshold))
            result = pipeline.run(query.strip(), generate=generate, use_llm=use_llm)
    except Exception as exc:
        st.error(f"실행 실패: {exc}")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(
        f"<div class='metric-card'><b>캐시 히트</b><br>{'예' if result['cache_hit'] else '아니오'}</div>",
        unsafe_allow_html=True,
    )
    cache_similarity = result.get("cache_similarity")
    cache_similarity_text = f"{cache_similarity:.4f}" if cache_similarity is not None else "없음"
    col2.markdown(
        f"<div class='metric-card'><b>QA 캐시 유사도</b><br>{cache_similarity_text}</div>",
        unsafe_allow_html=True,
    )
    retrieval_similarity = result.get("retrieval_similarity")
    retrieval_similarity_text = f"{retrieval_similarity:.4f}" if retrieval_similarity is not None else "없음"
    col3.markdown(
        f"<div class='metric-card'><b>검색 유사도</b><br>{retrieval_similarity_text}</div>",
        unsafe_allow_html=True,
    )
    col4.markdown(
        f"<div class='metric-card'><b>지연 시간</b><br>{result['latency_ms']} ms</div>",
        unsafe_allow_html=True,
    )
    retrieval = result.get("retrieval") or {}
    st.info(
        f"캐시 히트는 QA 캐시 유사도({cache_similarity_text})가 "
        f"threshold({retrieval.get('threshold')}) 이상일 때만 '예'로 표시됩니다. "
        "출처 카드의 score는 캐시 점수가 아니라 문서 검색 점수입니다."
    )

    st.subheader("답변")
    answer = result.get("answer") or "답변이 비어 있습니다."
    st.markdown(f"<div class='answer-card'>{answer}</div>", unsafe_allow_html=True)

    generation = result.get("generation") or {}
    st.caption(
        " · ".join(
            [
                f"source={retrieval.get('source')}",
                f"threshold={retrieval.get('threshold')}",
                f"cache_similarity={cache_similarity_text}",
                f"top_k={retrieval.get('top_k')}",
                f"generation={generation.get('mode') if generation else 'none'}",
            ]
        )
    )

    st.subheader("출처")
    sources = result.get("sources") or []
    if not sources:
        st.info("표시할 출처가 없습니다.")
    for source in sources:
        title = source.get("title") or source.get("doc_id") or "출처"
        url = source.get("url") or ""
        score = source.get("score")
        score_text = f"{score:.4f}" if score is not None else "없음"
        st.markdown(
            f"""
            <div class="source-card">
              <b>{source.get('rank')}. {title}</b><br>
              doc_id: <code>{source.get('doc_id')}</code> · 문서 검색 score: {score_text}<br>
              <a href="{url}" target="_blank">{url}</a>
            </div>
            """,
            unsafe_allow_html=True,
        )
