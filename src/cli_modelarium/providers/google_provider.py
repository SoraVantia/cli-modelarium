"""Google Gemini provider using the google-genai SDK.

API quirks compared to OpenAI-style providers:

    - The Client is constructed via `genai.Client(api_key=...)`.
    - Async work goes through `client.aio.models.*`.
    - System prompts live inside the `config` dict as `system_instruction`,
      not as a message with `role="system"`.
    - Usage data is on the chunk's `usage_metadata` (with field names like
      `prompt_token_count` rather than OpenAI's `prompt_tokens`).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import errors as genai_errors

from cli_modelarium.exceptions import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
)
from cli_modelarium.pricing import calculate_cost
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk
from cli_modelarium.security import redact_secrets


def _billable_output_tokens(usage: Any, input_tokens: int) -> int:
    """Output tokens as Google bills them, thinking included.

    Google is the only provider in this tool that reports reasoning separately:
    OpenAI, Anthropic and Qwen all fold it into their own output count, so
    summing here makes Gemini consistent with the rest of the registry rather
    than making the shared schema Google-shaped. Google's pricing page labels
    the rate "Output price (including thinking tokens)", so `thoughts_token_count`
    is billed at the output rate and belongs in the same number.

    Reading only `candidates_token_count`, as this did before, understated
    every thinking model's cost. Measured 2026-08-20 against gemini-3.6-flash:
    a two-character prompt returned 9 output tokens and 170 thought tokens, so
    the reported cost was a twentieth of the billed one. Google thinks by
    default with no opt-in, so this was live for every user of such a model.

    `total_token_count` is the cross-check. Anything the three known buckets do
    not account for is still billed, and this errs toward the output rate
    rather than dropping it - understating a cost is the failure being fixed
    here, and a silent zero is how it survived.
    """
    candidates = getattr(usage, "candidates_token_count", 0) or 0
    thoughts = getattr(usage, "thoughts_token_count", 0) or 0
    output_tokens = candidates + thoughts

    total = getattr(usage, "total_token_count", 0) or 0
    if total:
        unaccounted = total - input_tokens - output_tokens
        if unaccounted > 0:
            output_tokens += unaccounted

    return output_tokens


class GoogleProvider(BaseProvider):
    """Provider using the official google-genai SDK for Gemini models."""

    name: str = "google"

    def __init__(self, api_key: str) -> None:
        self.client = genai.Client(api_key=api_key)

    def _build_config(self, temperature: float, system_prompt: str | None) -> dict[str, Any]:
        config: dict[str, Any] = {"temperature": temperature}
        if system_prompt:
            config["system_instruction"] = system_prompt
        return config

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        config = self._build_config(temperature, system_prompt)
        try:
            response_stream = await self.client.aio.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=config,
            )
            async for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        except genai_errors.APIError as e:
            self._reraise(e)

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
        *,
        on_chunk: OnChunk | None = None,
    ) -> CompletionResult:
        config = self._build_config(temperature, system_prompt)

        start = time.monotonic()
        ttft_ms: float | None = None
        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0

        try:
            response_stream = await self.client.aio.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=config,
            )
            async for chunk in response_stream:
                if chunk.text:
                    if ttft_ms is None:
                        ttft_ms = (time.monotonic() - start) * 1000
                    if on_chunk is not None:
                        on_chunk(chunk.text)
                    chunks.append(chunk.text)
                # Final chunk carries the usage_metadata.
                usage = getattr(chunk, "usage_metadata", None)
                if usage is not None:
                    input_tokens = getattr(usage, "prompt_token_count", 0) or 0
                    cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
                    output_tokens = _billable_output_tokens(usage, input_tokens)
        except genai_errors.APIError as e:
            self._reraise(e)

        latency_ms = (time.monotonic() - start) * 1000

        try:
            cost = calculate_cost(model, input_tokens, output_tokens, cached_tokens)
        except Exception:
            cost = 0.0

        return CompletionResult(
            output="".join(chunks),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            ttft_ms=ttft_ms,
            model=model,
            provider=self.name,
            temperature=temperature,
        )

    def _reraise(self, error: genai_errors.APIError) -> None:
        """Translate a google-genai SDK error into a redacted Cli Modelarium exception."""
        message = redact_secrets(str(error))
        # google-genai doesn't expose typed subclasses for 401/429 - route by HTTP code.
        code = getattr(error, "code", None)
        if code in (401, 403):
            raise AuthenticationError(message, provider=self.name) from None
        if code == 429:
            raise RateLimitError(message, provider=self.name, retry_after=None) from None
        raise ProviderError(message, provider=self.name) from None
