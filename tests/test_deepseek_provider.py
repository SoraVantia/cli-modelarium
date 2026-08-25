"""Tests for cli_modelarium.providers.deepseek_provider.

DeepSeek is a thin OpenAIProvider subclass pointed at api.deepseek.com. Like
Z.AI (and unlike DashScope) it adds no request-param overrides.

It deliberately does NOT send enable_thinking=False. DashScope forces thinking
off because Alibaba publishes separate thinking and non-thinking rates and the
registry stores the non-thinking one; DeepSeek publishes a single rate per model
regardless of mode, so that rationale does not transfer - and all-reasoning
needs thinking enabled anyway.
"""

from __future__ import annotations

from typing import Any

import pytest

from cli_modelarium.models_registry import get_provider_for_model
from cli_modelarium.providers.deepseek_provider import DeepSeekProvider
from cli_modelarium.providers.openai_provider import OpenAIProvider

# ===== fake client plumbing (mirrors test_zai_provider.py) =====


class _FakeCompletions:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.last_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        return self._response


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = _FakeChat(completions)


def _make_provider(
    monkeypatch: pytest.MonkeyPatch, response: Any
) -> tuple[DeepSeekProvider, _FakeCompletions]:
    completions = _FakeCompletions(response)

    def fake_async_openai(**_kwargs: Any) -> _FakeClient:
        return _FakeClient(completions)

    monkeypatch.setattr("cli_modelarium.providers.openai_provider.AsyncOpenAI", fake_async_openai)
    provider = DeepSeekProvider(api_key="sk-NOT_A_REAL_KEY_test_fixture_0000")
    return provider, completions


# ===== identity / wiring =====


def test_provider_identity() -> None:
    assert DeepSeekProvider.name == "deepseek"
    assert DeepSeekProvider.BASE_URL == "https://api.deepseek.com/v1"


def test_subclasses_openai_provider() -> None:
    assert issubclass(DeepSeekProvider, OpenAIProvider)


def test_deepseek_models_route_to_deepseek() -> None:
    # Routing is data-driven from PRICING["provider"].
    assert get_provider_for_model("deepseek-v4-pro") == "deepseek"
    assert get_provider_for_model("deepseek-v4-flash") == "deepseek"


# ===== thinking-mode hook =====


def test_no_extra_create_kwargs() -> None:
    # DeepSeek is plain - it inherits the base no-op (no thinking-toggle).
    p = DeepSeekProvider.__new__(DeepSeekProvider)
    assert p._extra_create_kwargs() == {}


async def test_no_thinking_param_sent(
    monkeypatch: pytest.MonkeyPatch, fake_openai_stream: Any
) -> None:
    """Plain provider: no extra_body / thinking-toggle reaches create()."""
    stream = fake_openai_stream(text_chunks=["x"], input_tokens=1, output_tokens=1)
    provider, completions = _make_provider(monkeypatch, response=stream)

    await provider.complete("p", "deepseek-v4-pro", 0.0)

    assert "extra_body" not in completions.last_kwargs
    assert "enable_thinking" not in completions.last_kwargs
    assert "thinking" not in completions.last_kwargs
    assert "reasoning_effort" not in completions.last_kwargs


# ===== cost =====


async def test_complete_calculates_cost(
    monkeypatch: pytest.MonkeyPatch, fake_openai_stream: Any
) -> None:
    # deepseek-v4-pro: $0.435/M input, $0.87/M output.
    # 1000 input + 500 output = $0.000435 + $0.000435 = $0.00087
    stream = fake_openai_stream(
        text_chunks=["hi"],
        input_tokens=1000,
        output_tokens=500,
    )
    provider, _ = _make_provider(monkeypatch, response=stream)

    result = await provider.complete("p", "deepseek-v4-pro", 0.0)

    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-pro"
    assert result.cost_usd == pytest.approx(0.00087)
