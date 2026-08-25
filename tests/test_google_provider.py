"""Tests for cli_modelarium.providers.google_provider.

The google-genai async API is `client.aio.models.generate_content_stream(...)`,
which is a coroutine that resolves to an AsyncIterator. Each chunk has a `.text`
attribute and the final chunk(s) carry `.usage_metadata` with Google-specific
field names (`prompt_token_count`, `candidates_token_count`,
`cached_content_token_count`, `thoughts_token_count`, `total_token_count`).

`thoughts_token_count` is the one that matters and the one the client used to
ignore: Google reports reasoning separately and bills it at the output rate,
where OpenAI, Anthropic and Qwen all fold it into their own output count.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors as genai_errors

from cli_modelarium.exceptions import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
)
from cli_modelarium.pricing import PRICING
from cli_modelarium.providers.google_provider import GoogleProvider

# ===== fake plumbing =====


class _FakeChunk:
    def __init__(self, text: str | None = None, usage: SimpleNamespace | None = None) -> None:
        self.text = text
        self.usage_metadata = usage


class _FakeAsyncIterator:
    def __init__(self, chunks: list[_FakeChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> _FakeAsyncIterator:
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self) -> _FakeChunk:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeAsyncModels:
    def __init__(
        self,
        chunks: list[_FakeChunk] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._chunks = chunks
        self._error = error
        self.last_kwargs: dict[str, Any] = {}

    async def generate_content_stream(self, **kwargs: Any) -> _FakeAsyncIterator:
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return _FakeAsyncIterator(self._chunks or [])


class _FakeAio:
    def __init__(self, models: _FakeAsyncModels) -> None:
        self.models = models


class _FakeClient:
    def __init__(self, models: _FakeAsyncModels) -> None:
        self.aio = _FakeAio(models)


def _build_chunks(
    texts: list[str],
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    thought_tokens: int = 0,
    total_tokens: int | None = None,
) -> list[_FakeChunk]:
    """Build a fake stream whose usage object carries EVERY field the SDK exposes.

    The previous version of this helper set exactly the three fields the client
    read - `prompt_token_count`, `candidates_token_count` and
    `cached_content_token_count` - which is why the missing thought-token count
    survived: a double that models what the code reads can never surface what
    the code misses. Every field on
    `types.GenerateContentResponseUsageMetadata` is populated here, so a field
    the client ignores in future shows up as a total that does not reconcile
    rather than as nothing at all.
    """
    chunks = [_FakeChunk(text=t) for t in texts]
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens + thought_tokens
    usage = SimpleNamespace(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
        cached_content_token_count=cached_tokens,
        thoughts_token_count=thought_tokens,
        total_token_count=total_tokens,
        tool_use_prompt_token_count=0,
        prompt_tokens_details=None,
        candidates_tokens_details=None,
        cache_tokens_details=None,
        tool_use_prompt_tokens_details=None,
    )
    chunks.append(_FakeChunk(text=None, usage=usage))
    return chunks


def _make_provider(
    monkeypatch: pytest.MonkeyPatch,
    chunks: list[_FakeChunk] | None = None,
    error: Exception | None = None,
) -> tuple[GoogleProvider, _FakeAsyncModels]:
    models = _FakeAsyncModels(chunks=chunks, error=error)

    def fake_client_factory(**_kwargs: Any) -> _FakeClient:
        return _FakeClient(models)

    monkeypatch.setattr(
        "cli_modelarium.providers.google_provider.genai.Client", fake_client_factory
    )
    provider = GoogleProvider(api_key="test-google-api-key-123456789012345")
    return provider, models


# ===== happy path =====


async def test_complete_returns_full_text(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = _build_chunks(["Hello", ", ", "world!"], input_tokens=10, output_tokens=3)
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.1-pro-preview", 0.0)

    assert result.output == "Hello, world!"
    assert result.model == "gemini-3.1-pro-preview"
    assert result.provider == "google"
    assert result.error is None


async def test_complete_captures_token_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = _build_chunks(["x"], input_tokens=42, output_tokens=7, cached_tokens=11)
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("p", "gemini-3.1-pro-preview", 0.0)

    assert result.input_tokens == 42
    assert result.output_tokens == 7
    assert result.cached_tokens == 11


async def test_complete_calculates_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    # gemini-3.1-pro-preview: $2.00/M input, $12.00/M output.
    chunks = _build_chunks(["x"], input_tokens=1_000_000, output_tokens=1_000_000)
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("p", "gemini-3.1-pro-preview", 0.0)

    assert result.cost_usd == pytest.approx(14.00)


async def test_system_prompt_in_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google's system prompt goes inside `config["system_instruction"]`."""
    chunks = _build_chunks(["ok"], input_tokens=1, output_tokens=1)
    provider, models = _make_provider(monkeypatch, chunks=chunks)

    await provider.complete(
        "user prompt", "gemini-3.1-pro-preview", 0.0, system_prompt="you are helpful"
    )

    config = models.last_kwargs["config"]
    assert config["system_instruction"] == "you are helpful"
    # And the contents stay just the user prompt.
    assert models.last_kwargs["contents"] == "user prompt"


async def test_no_system_prompt_omits_system_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = _build_chunks(["ok"], input_tokens=1, output_tokens=1)
    provider, models = _make_provider(monkeypatch, chunks=chunks)

    await provider.complete("p", "gemini-3.1-pro-preview", 0.0)

    config = models.last_kwargs["config"]
    assert "system_instruction" not in config


async def test_temperature_passed_in_config(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = _build_chunks(["x"], input_tokens=1, output_tokens=1)
    provider, models = _make_provider(monkeypatch, chunks=chunks)

    await provider.complete("p", "gemini-3.1-pro-preview", 0.7)

    assert models.last_kwargs["config"]["temperature"] == 0.7


async def test_records_ttft_and_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = _build_chunks(["a", "b"], input_tokens=1, output_tokens=2)
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("p", "gemini-3.1-pro-preview", 0.0)

    assert result.ttft_ms is not None
    assert result.latency_ms >= (result.ttft_ms or 0)


# ===== stream() iteration =====


async def test_stream_yields_text_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = _build_chunks(["one", " two", " three"], input_tokens=1, output_tokens=3)
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    collected: list[str] = []
    async for chunk in provider.stream("p", "gemini-3.1-pro-preview", 0.0):
        collected.append(chunk)

    assert collected == ["one", " two", " three"]


# ===== error translation =====


def _client_error(code: int, message: str) -> genai_errors.ClientError:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1/models")
    response = httpx.Response(code, request=request)
    return genai_errors.ClientError(
        code, response_json={"error": {"code": code, "message": message}}, response=response
    )


async def test_401_translated_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    err = _client_error(401, "invalid key AIzaSyNOT_A_REAL_KEY-leaked_0000000000")
    provider, _ = _make_provider(monkeypatch, error=err)

    with pytest.raises(AuthenticationError) as exc_info:
        await provider.complete("p", "gemini-3.1-pro-preview", 0.0)

    assert "Leaked" not in str(exc_info.value)
    assert exc_info.value.provider == "google"


async def test_403_translated_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    err = _client_error(403, "forbidden")
    provider, _ = _make_provider(monkeypatch, error=err)

    with pytest.raises(AuthenticationError):
        await provider.complete("p", "gemini-3.1-pro-preview", 0.0)


async def test_429_translated_to_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    err = _client_error(429, "quota exceeded")
    provider, _ = _make_provider(monkeypatch, error=err)

    with pytest.raises(RateLimitError) as exc_info:
        await provider.complete("p", "gemini-3.1-pro-preview", 0.0)

    assert exc_info.value.provider == "google"


async def test_500_translated_to_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1/models")
    response = httpx.Response(500, request=request)
    err = genai_errors.ServerError(
        500, response_json={"error": {"code": 500, "message": "internal"}}, response=response
    )
    provider, _ = _make_provider(monkeypatch, error=err)

    with pytest.raises(ProviderError):
        await provider.complete("p", "gemini-3.1-pro-preview", 0.0)


# ===== thinking tokens =====
#
# Google reports reasoning in `thoughts_token_count`, a field of its own, and
# prices it at the output rate - its pricing page labels that rate "Output
# price (including thinking tokens)". Reading only `candidates_token_count`
# therefore understated every thinking model's cost, and Google thinks by
# default with no opt-in, so it was understated for real users rather than
# dormant behind a flag.
#
# The fixtures below are measured, not invented. Live calls on 2026-08-20:
#
#     gemini-3.6-flash       "hi"              out=9    thought=170
#     gemini-3.6-flash       "Count to three"  out=8    thought=126
#     gemini-3.6-flash       bat-and-ball      out=206  thought=547
#     gemini-3.1-flash-lite  all three         out=9/8/62  thought=0
#
# Which of the six registered Gemini models think, and by how much each
# under-reported, is not established - two were measured and four were not.


async def test_thought_tokens_count_toward_output(monkeypatch: pytest.MonkeyPatch) -> None:
    # The measured "hi" call: 9 visible output tokens, 170 spent thinking.
    #
    # `total_tokens=0` omits the total deliberately, so the only thing that can
    # supply 179 is reading `thoughts_token_count`. With a coherent total
    # present the cross-check would reconstruct the same number from the
    # remainder and this would pass even if the field were ignored - which is
    # how the original defect hid, and not a shape worth repeating here.
    chunks = _build_chunks(
        ["hi"], input_tokens=2, output_tokens=9, thought_tokens=170, total_tokens=0
    )
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.6-flash", 0.0)

    assert result.output_tokens == 179, "thinking is billed at the output rate"


async def test_cost_reflects_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    chunks = _build_chunks(
        ["hi"], input_tokens=2, output_tokens=9, thought_tokens=170, total_tokens=0
    )
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.6-flash", 0.0)

    entry = PRICING["gemini-3.6-flash"]
    expected = (2 / 1_000_000) * entry["input"] + (179 / 1_000_000) * entry["output"]
    assert result.cost_usd == pytest.approx(expected)
    # What the old code would have reported, for the size of the gap.
    understated = (2 / 1_000_000) * entry["input"] + (9 / 1_000_000) * entry["output"]
    assert result.cost_usd > understated * 15


async def test_a_coherent_total_agrees_with_the_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    # The realistic response: the API reports a total that reconciles with
    # prompt + candidates + thoughts, and the cross-check changes nothing.
    chunks = _build_chunks(
        ["hi"], input_tokens=2, output_tokens=9, thought_tokens=170, total_tokens=181
    )
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.6-flash", 0.0)

    assert result.output_tokens == 179


async def test_a_non_thinking_model_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    # gemini-3.1-flash-lite measured thought=0 on all three prompts. A model
    # that does not think must cost exactly what it did before this change.
    chunks = _build_chunks(["hi"], input_tokens=2, output_tokens=9, thought_tokens=0)
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.1-flash-lite", 0.0)

    assert result.output_tokens == 9
    entry = PRICING["gemini-3.1-flash-lite"]
    expected = (2 / 1_000_000) * entry["input"] + (9 / 1_000_000) * entry["output"]
    assert result.cost_usd == pytest.approx(expected)


async def test_tokens_unaccounted_by_the_known_fields_are_not_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `total_token_count` exceeds prompt + candidates + thoughts, so Google is
    # billing for something none of the three fields names. Folding the
    # remainder into output errs toward the output rate; dropping it would
    # repeat the exact failure this change fixes.
    chunks = _build_chunks(
        ["hi"], input_tokens=2, output_tokens=9, thought_tokens=170, total_tokens=200
    )
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.6-flash", 0.0)

    assert result.output_tokens == 198, "2 + 198 == the 200 the API reported"


async def test_a_smaller_total_does_not_reduce_the_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A total below the sum of the parts is incoherent; trust the parts rather
    # than silently billing less than the fields already reported.
    chunks = _build_chunks(
        ["hi"], input_tokens=2, output_tokens=9, thought_tokens=170, total_tokens=50
    )
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.6-flash", 0.0)

    assert result.output_tokens == 179


async def test_usage_without_the_thoughts_field_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An older SDK, or a response that omits the field entirely.
    chunks = [_FakeChunk(text="hi")]
    chunks.append(
        _FakeChunk(
            text=None,
            usage=SimpleNamespace(
                prompt_token_count=2, candidates_token_count=9, cached_content_token_count=0
            ),
        )
    )
    provider, _ = _make_provider(monkeypatch, chunks=chunks)

    result = await provider.complete("hi", "gemini-3.6-flash", 0.0)

    assert result.output_tokens == 9
