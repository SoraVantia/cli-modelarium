"""Anthropic provider implementation.

Two things make Anthropic distinct from OpenAI-style providers:

    1. The `system` prompt is a TOP-LEVEL parameter on `messages.create()`,
       NOT a message with `role: "system"` inside the messages array.
    2. `max_tokens` is REQUIRED on every call. We default to 4096 if the
       caller doesn't specify one.

Streaming uses the `messages.stream()` async context manager. The final
usage payload (input/output/cache-read tokens) is read after iteration
via `stream.get_final_message()`.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from cli_modelarium.exceptions import (
    AuthenticationError,
    ProviderError,
    ProviderOverloadedError,
    RateLimitError,
)
from cli_modelarium.pricing import calculate_cost, rejects_sampling_params
from cli_modelarium.providers._utils import extract_retry_after
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk
from cli_modelarium.security import redact_secrets

DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider(BaseProvider):
    """Provider using the official Anthropic Python SDK."""

    name: str = "anthropic"

    def __init__(self, api_key: str) -> None:
        self.client = AsyncAnthropic(api_key=api_key)

    def _build_kwargs(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        # Newer Claude models 400 on any non-default temperature; omitting the
        # field is the documented way to call them. Absent flag means send.
        #
        # Via `extra_body`, not a keyword: the SDK removed temperature, top_p
        # and top_k from its typed signatures in 1.x, so passing one raises
        # TypeError before any HTTP call. `extra_body` is merged into the
        # request JSON as-is, and the models that accept temperature still
        # honour it.
        if not rejects_sampling_params(model):
            kwargs["extra_body"] = {"temperature": temperature}
        if system_prompt:
            kwargs["system"] = system_prompt
        return kwargs

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks. REFUSAL-BLIND BY DESIGN - use `complete()` instead.

        A refused request yields zero chunks and terminates normally, which is
        indistinguishable from a model that answered with nothing. `complete()`
        holds the final message and reads `stop_reason`; nothing in the CLI
        calls this method.
        """
        kwargs = self._build_kwargs(prompt, model, temperature, system_prompt)
        try:
            async with self.client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIError as e:
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
        kwargs = self._build_kwargs(prompt, model, temperature, system_prompt)

        start = time.monotonic()
        ttft_ms: float | None = None
        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0
        stop_reason: str | None = None
        stop_category: str | None = None

        try:
            async with self.client.messages.stream(**kwargs) as stream:
                # `text_stream` yields text deltas only - the SDK filters
                # thinking blocks out of it. Nothing here reads `.content` or
                # indexes `content[0]`, so a response whose content array leads
                # with a ThinkingBlock needs no special handling.
                async for text in stream.text_stream:
                    if ttft_ms is None:
                        ttft_ms = (time.monotonic() - start) * 1000
                    if on_chunk is not None:
                        on_chunk(text)
                    chunks.append(text)
                final = await stream.get_final_message()
                usage = final.usage
                input_tokens = getattr(usage, "input_tokens", 0) or 0
                output_tokens = getattr(usage, "output_tokens", 0) or 0
                cached_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
                stop_reason = getattr(final, "stop_reason", None)
                details = getattr(final, "stop_details", None)
                stop_category = getattr(details, "category", None) if details else None
        except anthropic.APIError as e:
            self._reraise(e)

        # A refusal arrives on HTTP 200 with real cost. It is identified by
        # `stop_reason`, never by an empty content array: claude-opus-5 refuses
        # with a ThinkingBlock and non-zero output tokens, claude-fable-5 with
        # nothing at all, so an emptiness check misses the first of those.
        refused = stop_reason == "refusal"

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
            refused=refused,
            stop_reason=stop_reason,
            stop_category=stop_category,
        )

    def _reraise(self, error: anthropic.APIError) -> None:
        """Translate an Anthropic SDK error into a redacted Cli Modelarium exception."""
        message = redact_secrets(str(error))

        if isinstance(error, anthropic.AuthenticationError):
            raise AuthenticationError(message, provider=self.name) from None
        if isinstance(error, anthropic.RateLimitError):
            retry_after = extract_retry_after(error)
            raise RateLimitError(message, provider=self.name, retry_after=retry_after) from None
        # Anthropic returns 529 when their service is overloaded - distinct from rate limits.
        if (
            isinstance(error, anthropic.APIStatusError)
            and getattr(error, "status_code", None) == 529
        ):
            raise ProviderOverloadedError(message, provider=self.name) from None
        raise ProviderError(message, provider=self.name) from None
