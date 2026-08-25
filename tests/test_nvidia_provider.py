"""Tests for cli_modelarium.providers.nvidia_provider.

NVIDIA NIM is a thin OpenAIProvider subclass pointed at NVIDIA's
OpenAI-compatible endpoint. Like Z.AI it adds no request-param overrides.

Nine models are registered, all at 0.0/0.0 because NVIDIA publishes no
per-token rate. The zero is what the schema forces, not a price, so a caveat
panel fires whenever one is in a run - covered here too, since the panel exists
only for these rows.

Follows the per-provider file precedent (test_zai_provider.py) rather than
extending tests/test_provider_inheritance.py, whose three hand-maintained
literal lists already skip ZAIProvider entirely.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from rich.console import Console

from cli_modelarium import cli as cli_module
from cli_modelarium.cli import PROVIDER_REGISTRY
from cli_modelarium.models_registry import (
    MODEL_GROUPS,
    all_known_providers,
    get_provider_for_model,
)
from cli_modelarium.pricing import PRICING
from cli_modelarium.providers.nvidia_provider import NVIDIAProvider
from cli_modelarium.providers.openai_provider import OpenAIProvider
from tests.conftest import count_panels, flatten_rendered


@pytest.fixture
def captured_console(
    monkeypatch: pytest.MonkeyPatch, capture_console: Console
) -> io.StringIO:
    """Swap cli's module-level console for the width-pinned shared one."""
    monkeypatch.setattr(cli_module, "console", capture_console)
    return capture_console.file  # type: ignore[return-value]

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
        self.init_kwargs: dict[str, Any] = {}


def _make_provider(
    monkeypatch: pytest.MonkeyPatch, response: Any
) -> tuple[NVIDIAProvider, _FakeCompletions, dict[str, Any]]:
    completions = _FakeCompletions(response)
    captured: dict[str, Any] = {}

    def fake_async_openai(**kwargs: Any) -> _FakeClient:
        captured.update(kwargs)
        return _FakeClient(completions)

    monkeypatch.setattr("cli_modelarium.providers.openai_provider.AsyncOpenAI", fake_async_openai)
    provider = NVIDIAProvider(api_key="nvapi-NOT_A_REAL_KEY_test_fixture_0")
    return provider, completions, captured


# ===== identity / wiring =====


def test_provider_identity() -> None:
    assert NVIDIAProvider.name == "nvidia"
    assert NVIDIAProvider.BASE_URL == "https://integrate.api.nvidia.com/v1"


def test_subclasses_openai_provider() -> None:
    assert issubclass(NVIDIAProvider, OpenAIProvider)


def test_registered_in_provider_registry() -> None:
    assert PROVIDER_REGISTRY["nvidia"] == (
        "cli_modelarium.providers.nvidia_provider:NVIDIAProvider"
    )


def test_registry_import_string_resolves() -> None:
    """PROVIDER_REGISTRY uses lazy import strings, so providers/__init__.py needs no edit."""
    import importlib

    module_path, _, class_name = PROVIDER_REGISTRY["nvidia"].partition(":")
    resolved = getattr(importlib.import_module(module_path), class_name)
    assert resolved is NVIDIAProvider


def test_forwards_api_key_and_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, captured = _make_provider(monkeypatch, response=None)
    assert captured["api_key"] == "nvapi-NOT_A_REAL_KEY_test_fixture_0"
    assert captured["base_url"] == "https://integrate.api.nvidia.com/v1"


def test_no_default_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only OpenRouter sends default headers; NVIDIA must not."""
    _, _, captured = _make_provider(monkeypatch, response=None)
    assert "default_headers" not in captured


def test_no_extra_create_kwargs() -> None:
    # Plain provider: it inherits the base no-op (no thinking-toggle).
    p = NVIDIAProvider.__new__(NVIDIAProvider)
    assert p._extra_create_kwargs() == {}


def test_does_not_override_stream_or_complete() -> None:
    for method in ("stream", "complete", "_transform_model", "_reraise"):
        assert method not in NVIDIAProvider.__dict__, f"NVIDIAProvider must not override {method}"


# ===== the nine registered rows =====

NIM_MODELS = [
    "google/gemma-4-31b-it",
    "google/diffusiongemma-26b-a4b-it",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "nvidia/nemotron-mini-4b-instruct",
    "mistralai/mistral-nemotron",
    "minimaxai/minimax-m3",
    "poolside/laguna-xs-2.1",
    "meta/llama-3.1-8b-instruct",
]


def test_exactly_nine_nvidia_rows() -> None:
    registered = sorted(m for m, v in PRICING.items() if v.get("provider") == "nvidia")
    assert registered == sorted(NIM_MODELS)


@pytest.mark.parametrize("model_id", NIM_MODELS)
def test_row_fields(model_id: str) -> None:
    """Zero in / zero out, no cache rate, and NOT flagged as rejecting temperature.

    The `rejects_sampling_params` absence is load-bearing: a tripwire test pins
    the count of models carrying that flag, so adding it here would break it.
    """
    entry = PRICING[model_id]
    assert entry["input"] == 0.0
    assert entry["output"] == 0.0
    assert "cached_input" not in entry
    assert "rejects_sampling_params" not in entry


@pytest.mark.parametrize("model_id", NIM_MODELS)
def test_each_row_routes_to_nvidia(model_id: str) -> None:
    assert get_provider_for_model(model_id) == "nvidia"


def test_nvidia_present_in_all_known_providers() -> None:
    """all_known_providers() derives from PRICING, so the rows make it appear."""
    assert "nvidia" in all_known_providers()


def test_no_nvidia_model_in_any_static_group() -> None:
    for group, members in MODEL_GROUPS.items():
        for model in members:
            entry = PRICING.get(model)
            assert entry is not None, f"{group} references unregistered {model}"
            assert entry.get("provider") != "nvidia", f"{group} contains an NVIDIA model"


def test_all_resolution_excludes_nvidia(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--models all` must not pull in an unpriced model even with a key set.

    The pre-existing pinning test asserts only what IS excluded, so it stays
    green either way; this is the assertion that makes the new exclusion tested.
    """
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-NOT_A_REAL_KEY_test_fixture_1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_test_fixture_00")
    resolved = cli_module._resolve_all_cloud()
    assert [m for m in resolved if PRICING.get(m, {}).get("provider") == "nvidia"] == []
    # The control: a priced provider with a key set still resolves.
    assert [m for m in resolved if PRICING.get(m, {}).get("provider") == "openai"]


# ===== the caveat panel =====


def test_panel_fires_for_a_nim_model(captured_console: io.StringIO) -> None:
    cli_module._warn_unpriced_models(["meta/llama-3.1-8b-instruct"])
    out = flatten_rendered(captured_console.getvalue())
    assert "Cost is not tracked for meta/llama-3.1-8b-instruct" in out
    assert "--max-cost and cost_under provide no protection" in out
    assert "--significance-metric cost_usd should not be trusted" in out
    assert "credit-metered" in out


@pytest.mark.parametrize(
    "model_id",
    ["gpt-5.5", "local/llama3", "openai/gpt-oss-120b:free", "glm-4.7-flash", "made-up-id"],
)
def test_panel_silent_without_a_nim_model(
    captured_console: io.StringIO, model_id: str
) -> None:
    """Priced, local, genuinely-free and unregistered ids must not trigger it."""
    cli_module._warn_unpriced_models([model_id])
    assert captured_console.getvalue() == ""


def test_panel_does_not_use_the_temperature_title(captured_console: io.StringIO) -> None:
    """The temperature panel's title is hardcoded; a cost caveat must not wear it."""
    cli_module._warn_unpriced_models(["minimaxai/minimax-m3"])
    out = flatten_rendered(captured_console.getvalue())
    assert "Cost not tracked" in out
    assert "Temperature not applied" not in out


def test_both_caveats_render_neither_suppressed(captured_console: io.StringIO) -> None:
    """Two panels, both present. Separate emitters, so neither can swallow the other."""
    models = ["claude-opus-5", "gpt-4o", "meta/llama-3.1-8b-instruct"]
    cli_module._warn_temperature_conditions(models, [0.0, 1.0], significance_runs=True)
    cli_module._warn_unpriced_models(models)
    raw = captured_console.getvalue()
    out = flatten_rendered(raw)
    assert "identical rather than a sweep" in out
    assert "not sampled under identical" in out
    assert "Cost is not tracked" in out
    assert count_panels(raw) == 2
