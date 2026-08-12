"""Real OpenAI adapter. Only constructed when OPENAI_API_KEY is set
(see app.ai.gateway.build_adapter) — never marked live without a key
(spec C2, I4)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

from pydantic import BaseModel

from app.ai.exceptions import (
    AiProviderAuthError,
    AiProviderQuotaExceeded,
    AiProviderRateLimited,
    AiProviderUnavailable,
)
from app.ai.gateway import GenerateRequest, GenerateResult, RerankScores, build_rerank_request

DEFAULT_MODEL = "gpt-4.1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


@contextmanager
def _translated_errors() -> Iterator[None]:
    """Maps the OpenAI SDK's exceptions onto this app's normalized ones.

    Applied per call rather than once around the client, because an
    untranslated SDK error escaping to FastAPI becomes a bare 500 with no
    CORS header, which the browser reports only as "Failed to fetch".
    """
    import openai

    try:
        yield
    except openai.AuthenticationError as exc:
        raise AiProviderAuthError("OpenAI rejected the configured API key") from exc
    except openai.PermissionDeniedError as exc:
        raise AiProviderAuthError(
            "The configured OpenAI key does not have access to this model"
        ) from exc
    except openai.RateLimitError as exc:
        # OpenAI returns 429 for two different situations. An exhausted
        # balance is not a rate limit — retrying never clears it — so it
        # gets its own error and its own message.
        if "insufficient_quota" in str(exc):
            raise AiProviderQuotaExceeded(
                "The OpenAI account has no remaining quota"
            ) from exc
        raise AiProviderRateLimited("OpenAI rate limit reached") from exc
    except openai.APIStatusError as exc:
        raise AiProviderUnavailable(f"OpenAI returned HTTP {exc.status_code}") from exc
    except openai.APIConnectionError as exc:
        raise AiProviderUnavailable("OpenAI is unreachable") from exc


class OpenAIAdapter:
    provider_name = "openai"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        with _translated_errors():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": request.prompt}],
            )
        text = response.choices[0].message.content or ""
        return GenerateResult(text=text, model=self._model, provider=self.provider_name)

    async def generate_structured(
        self, request: GenerateRequest, schema: type[BaseModel]
    ) -> BaseModel:
        with _translated_errors():
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": request.prompt}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                    },
                },
            )
        content = response.choices[0].message.content or "{}"
        return schema.model_validate(json.loads(content))

    async def stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        with _translated_errors():
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": request.prompt}],
                stream=True,
            )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def embed(self, texts: list[str]) -> list[list[float]]:
        with _translated_errors():
            response = await self._client.embeddings.create(
                model=DEFAULT_EMBEDDING_MODEL, input=texts
            )
        return [item.embedding for item in response.data]

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        request = build_rerank_request(query, documents)
        result = await self.generate_structured(request, RerankScores)
        assert isinstance(result, RerankScores)
        if len(result.scores) != len(documents):
            raise ValueError(
                f"OpenAI returned {len(result.scores)} rerank scores for "
                f"{len(documents)} documents"
            )
        return result.scores
