"""Real Anthropic adapter. Only constructed when ANTHROPIC_API_KEY is set
(see app.ai.gateway.build_adapter) — never marked live without a key
(spec C2, I4)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.ai.gateway import GenerateRequest, GenerateResult, RerankScores, build_rerank_request

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicAdapter:
    provider_name = "anthropic"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": request.prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return GenerateResult(text=text, model=self._model, provider=self.provider_name)

    async def generate_structured(
        self, request: GenerateRequest, schema: type[BaseModel]
    ) -> BaseModel:
        tool = {
            "name": "emit_result",
            "description": "Emit the structured result.",
            "input_schema": schema.model_json_schema(),
        }
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            tools=[tool],  # type: ignore[call-overload]
            tool_choice={"type": "tool", "name": "emit_result"},
            messages=[{"role": "user", "content": request.prompt}],
        )
        for block in response.content:
            if block.type == "tool_use":
                return schema.model_validate(block.input)
        raise ValueError("Anthropic did not return a structured tool call")

    async def stream(self, request: GenerateRequest) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": request.prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "Anthropic does not expose an embeddings endpoint; configure an "
            "embedding-capable provider (e.g. OpenAI) for this feature."
        )

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        request = build_rerank_request(query, documents)
        result = await self.generate_structured(request, RerankScores)
        assert isinstance(result, RerankScores)
        if len(result.scores) != len(documents):
            raise ValueError(
                f"Anthropic returned {len(result.scores)} rerank scores for "
                f"{len(documents)} documents"
            )
        return result.scores
