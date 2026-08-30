"""Tests for cli_modelarium.providers.moonshot_provider.

Moonshot AI (Kimi) is a thin OpenAIProvider subclass pointed at
api.moonshot.ai, in the shape of DeepSeek and Z.AI. It adds no request-param
overrides.

This provider is the only one in the registry that has never been called. It
was added from published documentation because Moonshot requires a paid top-up
before any request, so the tests below carry more weight than usual: they are
the only thing standing between a misread page and a wrong cost. Two of them
exist specifically for that.

    `TestUsageShapeContract` pins what the client extracts from each of the two
    candidate `usage` shapes. It cannot prove which one Moonshot sends - only a
    live call does that - but it makes the FLAT shape's silent zero visible, so
    that if anyone later registers a `cached_input` rate against the documented
    flat field, the reason it can never fire is written down and asserted right
    here rather than rediscovered from a wrong invoice.

    `TestNoCachedRateIsRegistered` pins the omission as deliberate, the way
    `test_nvidia_provider.py` does for NVIDIA's absent cache rate.
"""

from __future__ import annotations

import types
from typing import Any

import pytest
from click.testing import CliRunner

from cli_modelarium import security
from cli_modelarium.cli import PROVIDER_REGISTRY
from cli_modelarium.cli import main as cli_main
from cli_modelarium.models_registry import get_provider_for_model
from cli_modelarium.pricing import PRICING, calculate_cost, rejects_sampling_params
from cli_modelarium.providers.moonshot_provider import MoonshotProvider
from cli_modelarium.providers.openai_provider import OpenAIProvider

MOONSHOT_MODELS = [
    "kimi-k3",
    "kimi-k2.7-code",
    "kimi-k2.7-code-highspeed",
    "kimi-k2.6",
]

# Shape-valid and obviously not a credential. Matches the convention every
# entry in `test_cli_configure.VALID_KEYS` follows, which exists because a
# realistic-looking fixture tripped secret scanning in an earlier release.
FIXTURE_KEY = "sk-NOT_A_REAL_KEY_test_fixture_00"


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
) -> tuple[MoonshotProvider, _FakeCompletions]:
    completions = _FakeCompletions(response)

    def fake_async_openai(**_kwargs: Any) -> _FakeClient:
        return _FakeClient(completions)

    monkeypatch.setattr("cli_modelarium.providers.openai_provider.AsyncOpenAI", fake_async_openai)
    provider = MoonshotProvider(api_key=FIXTURE_KEY)
    return provider, completions


# ===== identity / wiring =====


def test_provider_identity() -> None:
    assert MoonshotProvider.name == "moonshot"
    assert MoonshotProvider.BASE_URL == "https://api.moonshot.ai/v1"


def test_subclasses_openai_provider() -> None:
    assert issubclass(MoonshotProvider, OpenAIProvider)


def test_base_url_forwarded_to_async_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("cli_modelarium.providers.openai_provider.AsyncOpenAI", capture)
    MoonshotProvider(api_key=FIXTURE_KEY)

    assert captured["base_url"] == "https://api.moonshot.ai/v1"
    assert captured["api_key"] == FIXTURE_KEY


def test_registry_entry_is_a_lazy_import_string() -> None:
    """PROVIDER_REGISTRY imports by string, so providers/__init__.py needs no edit."""
    import importlib

    assert PROVIDER_REGISTRY["moonshot"] == (
        "cli_modelarium.providers.moonshot_provider:MoonshotProvider"
    )
    module_path, _, class_name = PROVIDER_REGISTRY["moonshot"].partition(":")
    assert getattr(importlib.import_module(module_path), class_name) is MoonshotProvider


@pytest.mark.parametrize("model", MOONSHOT_MODELS)
def test_kimi_models_route_to_moonshot(model: str) -> None:
    assert get_provider_for_model(model) == "moonshot"


def test_no_other_model_routes_to_moonshot() -> None:
    routed = {m for m, e in PRICING.items() if e.get("provider") == "moonshot"}
    assert routed == set(MOONSHOT_MODELS)


def test_no_extra_create_kwargs() -> None:
    # Plain provider: it inherits the base no-op. kimi-k2.6 CAN disable thinking
    # through extra_body, and deliberately does not here - the registered rate
    # is the thinking rate.
    p = MoonshotProvider.__new__(MoonshotProvider)
    assert p._extra_create_kwargs() == {}


async def test_no_extra_body_reaches_create(
    monkeypatch: pytest.MonkeyPatch, fake_openai_stream: Any
) -> None:
    stream = fake_openai_stream(text_chunks=["x"], input_tokens=1, output_tokens=1)
    provider, completions = _make_provider(monkeypatch, response=stream)

    await provider.complete("p", "kimi-k3", 0.0)

    assert "extra_body" not in completions.last_kwargs


# ===== the retired ids stay unknown =====


@pytest.mark.parametrize("model", ["kimi-k2.5", "moonshot-v1-8k", "moonshot-v1-128k"])
def test_sunset_ids_are_unknown_not_retired(model: str) -> None:
    """RETIRED_MODELS is for ids THIS registry once served; these never were.

    An entry would also assert a retirement date the tool has never verified,
    on a sunset dated the day the provider landed.
    """
    from cli_modelarium.exceptions import UnknownModelError
    from cli_modelarium.pricing import RETIRED_MODELS

    assert model not in RETIRED_MODELS
    with pytest.raises(UnknownModelError):
        get_provider_for_model(model)


# ===== cost =====


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # 1000 input + 500 output, at each row's published rates.
        ("kimi-k3", 1000 / 1e6 * 3.00 + 500 / 1e6 * 15.00),
        ("kimi-k2.7-code", 1000 / 1e6 * 0.95 + 500 / 1e6 * 4.00),
        ("kimi-k2.7-code-highspeed", 1000 / 1e6 * 1.90 + 500 / 1e6 * 8.00),
        ("kimi-k2.6", 1000 / 1e6 * 0.95 + 500 / 1e6 * 4.00),
    ],
)
def test_calculate_cost_for_each_model(model: str, expected: float) -> None:
    assert calculate_cost(model, 1000, 500) == pytest.approx(expected)


def test_highspeed_is_exactly_double_its_base() -> None:
    """Moonshot's published relationship, not a copied row - so pin it.

    An exact 2.000x on both columns reads as a typo to anyone who has not seen
    the pricing page. If a future edit corrects one row and not the other, this
    is the line that says which of the two was deliberate.
    """
    base, fast = PRICING["kimi-k2.7-code"], PRICING["kimi-k2.7-code-highspeed"]
    assert float(fast["input"]) == pytest.approx(2 * float(base["input"]))
    assert float(fast["output"]) == pytest.approx(2 * float(base["output"]))


@pytest.mark.parametrize("model", MOONSHOT_MODELS)
def test_cached_tokens_fall_back_to_the_input_rate(model: str) -> None:
    """No cached_input is registered, so a cache hit costs the full input rate.

    That over-reports against a real cache hit, which is the safe direction and
    matches how the Mistral, Groq and OpenRouter rows already behave.
    """
    full = calculate_cost(model, 1000, 500, cached_tokens=0)
    cached = calculate_cost(model, 1000, 500, cached_tokens=900)

    assert cached == pytest.approx(full)


class TestNoCachedRateIsRegistered:
    """The omission is deliberate - the same shape of pin NVIDIA's rows carry."""

    @pytest.mark.parametrize("model", MOONSHOT_MODELS)
    def test_no_cached_input_key(self, model: str) -> None:
        assert "cached_input" not in PRICING[model]

    def test_the_registry_records_why(self) -> None:
        # Moonshot DOES publish a cache-hit rate; the reason it is absent is
        # the wire format, and that reason must survive in the file.
        from pathlib import Path

        source = Path("src/cli_modelarium/pricing.py").read_text(encoding="utf-8")
        block = source.split("# ===== Moonshot AI (Kimi) =====")[1].split("# ===== Local")[0]
        assert "prompt_tokens_details" in block
        assert "flat" in block.lower()


# ===== the usage shape contract =====


class TestUsageShapeContract:
    """What the client extracts from each candidate `usage` shape.

    Moonshot's chat API documents four FLAT usage fields and no
    `prompt_tokens_details`. `OpenAIProvider.complete()` reads `cached_tokens`
    only from inside `prompt_tokens_details`. These two tests hold that
    difference still so it cannot be rediscovered from a wrong cost figure.
    """

    @staticmethod
    def _stream(usage: Any) -> Any:
        class _Delta:
            content = "hi"

        class _Choice:
            delta = _Delta()

        def chunk(u: Any) -> Any:
            c = types.SimpleNamespace()
            c.choices = [_Choice()]
            c.usage = u
            return c

        class _Stream:
            def __aiter__(self) -> Any:
                async def gen() -> Any:
                    yield chunk(None)
                    yield chunk(usage)

                return gen()

        return _Stream()

    async def test_flat_cached_tokens_are_not_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The documented Moonshot shape. A flat field yields zero, silently."""
        flat = types.SimpleNamespace(
            prompt_tokens=1000, completion_tokens=500, total_tokens=1500, cached_tokens=900
        )
        provider, _ = _make_provider(monkeypatch, response=self._stream(flat))

        result = await provider.complete("p", "kimi-k3", 0.0)

        assert result.cached_tokens == 0
        assert result.input_tokens == 1000
        assert result.output_tokens == 500

    async def test_nested_cached_tokens_are_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The shape the client is written for - kept as the contrast case.

        If a live call ever shows Moonshot sending this, the cached rates can be
        registered and this is the test that says they will then fire.
        """
        nested = types.SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            prompt_tokens_details=types.SimpleNamespace(cached_tokens=900),
        )
        provider, _ = _make_provider(monkeypatch, response=self._stream(nested))

        result = await provider.complete("p", "kimi-k3", 0.0)

        assert result.cached_tokens == 900


# ===== temperature =====


@pytest.mark.parametrize("model", MOONSHOT_MODELS)
def test_all_four_reject_sampling_params(model: str) -> None:
    assert rejects_sampling_params(model) is True


@pytest.mark.parametrize("model", MOONSHOT_MODELS)
async def test_temperature_is_omitted_from_the_request(
    monkeypatch: pytest.MonkeyPatch, fake_openai_stream: Any, model: str
) -> None:
    """Moonshot fixes temperature per model; sending another value errors."""
    stream = fake_openai_stream(text_chunks=["x"], input_tokens=1, output_tokens=1)
    provider, completions = _make_provider(monkeypatch, response=stream)

    await provider.complete("p", model, 0.7)

    assert "temperature" not in completions.last_kwargs


# ===== key handling =====


class TestKeyHandling:
    def test_pattern_accepts_a_valid_shape(self) -> None:
        assert security.validate_key("moonshot", FIXTURE_KEY) is True

    def test_pattern_is_deepseek_s(self) -> None:
        # Shared deliberately. Validation is per-provider, so overlap weakens
        # nothing, and inventing a stricter shape from an unverified key format
        # would reject a legitimate key at save_key.
        assert (
            security.KEY_PATTERNS["moonshot"].pattern
            == security.KEY_PATTERNS["deepseek"].pattern
        )

    def test_a_pattern_entry_exists_because_keys_delete_gates_on_it(self) -> None:
        # configure iterates PRICING with no membership gate, but keys
        # set/delete gate on KEY_PATTERNS - a provider in one and not the other
        # lets configure store a key that keys delete then refuses to remove.
        assert "moonshot" in security.KEY_PATTERNS

    def test_key_is_redacted_onto_the_shared_placeholder(self) -> None:
        # No Moonshot-specific redaction rule: the generic sk- rule already
        # catches it, and an appended rule would never be reached.
        assert security.redact_secrets(f"body {FIXTURE_KEY}") == "body sk-***REDACTED***"

    def test_the_fixture_is_obviously_synthetic(self) -> None:
        assert "NOT_A_REAL_KEY" in FIXTURE_KEY


# ===== no key configured =====


def test_no_key_reports_a_key_error_not_unknown_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert the MESSAGE, not the exit code.

    A registered model with no key and an unregistered model BOTH exit 2, so
    the code proves nothing about whether the model reached the registry. Only
    the message distinguishes "you need a key" from "no such model".
    """
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    result = CliRunner().invoke(cli_main, ["hi", "--models", "kimi-k3", "--no-stream"])

    assert result.exit_code == 2
    assert "No API key configured for moonshot" in result.output
    assert "Unknown model" not in result.output
