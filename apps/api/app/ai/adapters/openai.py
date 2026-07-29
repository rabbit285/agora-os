"""Real OpenAI adapter. Only constructed when OPENAI_API_KEY is set
(see app.ai.gateway.build_adapter) — never marked live without a key
(spec C2, I4)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.ai.gateway import GenerateRequest, GenerateResult

DEFAULT_MODEL = "gpt-4.1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class OpenAIAdapter:
    provider_name = "openai"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": request.prompt}],
        )
        text = response.choices[0].message.content or ""
        return GenerateResult(text=text, model=self._model, provider=self.provider_name)

    async def generate_structured(
        self, request: GenerateRequest, schema: type[BaseModel]
    ) -> BaseModel:
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
        response = await self._client.embeddings.create(model=DEFAULT_EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        raise NotImplementedError("Reranking is not implemented for the OpenAI adapter yet.")
