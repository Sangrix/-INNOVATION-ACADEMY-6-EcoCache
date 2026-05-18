from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import config
from rag.semantic_cache_retriever import RetrievalResult
from rag.vector_store import SearchHit


@dataclass(frozen=True)
class GeneratedAnswer:
    text: str | None
    mode: str
    model: str | None = None
    error: str | None = None


def build_context(hits: list[SearchHit], *, max_chars: int = config.LM_CONTEXT_LIMIT) -> str:
    """Build compact context text from retrieved documents."""

    if not hits:
        return ""

    per_doc = max(1, max_chars // len(hits))
    parts: list[str] = []
    for index, hit in enumerate(hits, start=1):
        payload = hit.payload
        title = payload.get("title") or payload.get("question") or payload.get("doc_id") or payload.get("qa_id") or ""
        date = payload.get("published_at", "")
        url = payload.get("url") or payload.get("reference_url") or ""
        text = payload.get("text") or payload.get("answer") or ""
        text = text.strip()[:per_doc]
        parts.append(
            "\n".join(
                [
                    f"[source {index}]",
                    f"title: {title}",
                    f"date: {date}",
                    f"url: {url}",
                    f"content: {text}",
                ]
            )
        )
    return "\n\n---\n\n".join(parts)


def build_prompt(query: str, context: str) -> list[dict[str, str]]:
    """Build OpenAI-compatible chat messages for the final answer."""

    return [
        {"role": "system", "content": config.LM_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"참고 문서:\n{context}\n\n질문: {query}\n\n답변은 한국어로 간결하게 작성하세요.",
        },
    ]


class RagAnswerGenerator:
    """Generate final answer from cache, LLM, or retrieval fallback."""

    def __init__(
        self,
        *,
        lm_url: str = config.LM_STUDIO_URL,
        lm_model: str = config.LM_STUDIO_MODEL,
        temperature: float = config.LM_TEMPERATURE,
        max_tokens: int = config.LM_MAX_TOKENS,
        timeout_seconds: float = config.LM_TIMEOUT_SECONDS,
    ) -> None:
        self.lm_url = lm_url
        self.lm_model = lm_model.strip()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self._resolved_model: str | None = self.lm_model or None

    def generate(self, query: str, retrieval: RetrievalResult, *, use_llm: bool = True) -> GeneratedAnswer:
        if retrieval.cache_hit and retrieval.answer:
            return GeneratedAnswer(text=retrieval.answer, mode="cache")

        if not retrieval.results:
            return GeneratedAnswer(text="해당 정보를 찾을 수 없습니다.", mode="empty")

        if use_llm:
            try:
                return self._generate_with_lm_studio(query, retrieval)
            except Exception as error:
                return GeneratedAnswer(
                    text=self._fallback_answer(retrieval),
                    mode="retrieval_fallback",
                    model=self._resolved_model,
                    error=str(error),
                )

        return GeneratedAnswer(text=self._fallback_answer(retrieval), mode="retrieval_fallback")

    def _generate_with_lm_studio(self, query: str, retrieval: RetrievalResult) -> GeneratedAnswer:
        from openai import OpenAI

        context = build_context(retrieval.results)
        client = OpenAI(base_url=self.lm_url, api_key="lm-studio", timeout=self.timeout_seconds)
        model = self._resolve_lm_studio_model(client)
        response = client.chat.completions.create(
            model=model,
            messages=build_prompt(query, context),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return GeneratedAnswer(
            text=response.choices[0].message.content,
            mode="llm",
            model=model,
        )

    def _resolve_lm_studio_model(self, client: Any) -> str:
        """Use the configured model, or auto-detect the loaded LM Studio model."""

        if self._resolved_model:
            return self._resolved_model

        models = client.models.list()
        first_model = next(iter(models.data), None)
        if first_model is None or not getattr(first_model, "id", None):
            raise ValueError(
                "LM Studio 서버는 연결됐지만 로드된 모델을 찾지 못했습니다. "
                "LM Studio에서 모델을 Load한 뒤 Local Server를 켜세요."
            )

        self._resolved_model = first_model.id
        return self._resolved_model

    @staticmethod
    def _fallback_answer(retrieval: RetrievalResult) -> str:
        top = retrieval.results[0].payload
        title = top.get("title") or top.get("question") or "검색된 문서"
        text = (top.get("text") or top.get("answer") or "").strip()
        if not text:
            return "관련 문서는 찾았지만, 답변으로 사용할 본문 내용이 비어 있습니다."
        preview = text[:500].replace("\n\n", "\n")
        return f"가장 관련도가 높은 문서는 '{title}'입니다.\n\n{preview}"


def generation_to_dict(answer: GeneratedAnswer) -> dict[str, Any]:
    return {
        "mode": answer.mode,
        "model": answer.model,
        "error": answer.error,
    }
