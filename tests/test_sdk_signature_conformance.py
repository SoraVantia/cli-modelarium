"""Every provider's request kwargs must be accepted by the REAL SDK signature.

This suite's provider doubles all accept `**kwargs`:

    tests/test_anthropic_provider.py   def stream(self, **kwargs)
    tests/test_openai_provider.py      async def create(self, **kwargs)
    tests/test_google_provider.py      async def generate_content_stream(self, **kwargs)
    tests/test_mistral_provider.py     async def stream_async(self, **kwargs)

A double shaped that way accepts a keyword the real, typed SDK method rejects,
so a provider can pass a parameter that no longer exists and the whole suite
stays green while every live call raises `TypeError` before any HTTP request.
That happened when the Anthropic SDK removed `temperature`/`top_p`/`top_k`
from its typed signatures in 1.x.

The doubles are not replaced here - they are useful precisely because they are
permissive. Instead this file adds the check they cannot make: drive each
provider's real code path through a recorder, then assert the kwargs it built
are a subset of the parameters the installed SDK method actually declares.

    set(built_kwargs) <= set(inspect.signature(real_method).parameters)

None of the four SDK methods declares `**kwargs`, so the subset relation is
meaningful for all of them; `test_no_target_method_accepts_var_keyword` pins
that assumption, because the check silently becomes vacuous if an SDK ever
adds one.

No network and no API key: signatures are read by reflection and the recorder
raises before any request is issued.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from cli_modelarium.providers.anthropic_provider import AnthropicProvider
from cli_modelarium.providers.google_provider import GoogleProvider
from cli_modelarium.providers.mistral_provider import MistralProvider
from cli_modelarium.providers.openai_provider import OpenAIProvider

DUMMY_KEY = "not-a-real-key-signature-check-only"
PROMPT = "hello"


class _RecordedError(Exception):
    """Raised by the recorder once kwargs are captured.

    Deliberately NOT an SDK error type, so it propagates through each
    provider's `except <SDKError>` clause instead of being translated into a
    ModelariumError. If a provider ever grows a bare `except Exception`, this
    test fails loudly rather than silently capturing nothing.
    """

    def __init__(self, kwargs: dict[str, Any]) -> None:
        super().__init__("captured")
        self.kwargs = kwargs


def _recorder(sink: dict[str, Any]) -> Callable[..., Any]:
    """A stand-in for an SDK method that records its keywords and stops."""

    def _capture(*_args: Any, **kwargs: Any) -> Any:
        sink.clear()
        sink.update(kwargs)
        raise _RecordedError(kwargs)

    return _capture


# ===== per-family wiring =====


@dataclass(frozen=True)
class _Family:
    """One SDK family: how to build a provider, and what the real method is."""

    name: str
    model: str  # a registry model that DOES send temperature
    build_provider: Callable[[], Any]
    install_recorder: Callable[[Any, dict[str, Any]], None]
    real_method: Callable[[], Any]
    # Some SDKs take a nested settings object; its keys need checking too.
    nested_kwarg: str | None = None
    nested_fields: Callable[[], set[str]] | None = None
    # Which kwarg carries `temperature`, or None when it sits at the top
    # level. Separate from `nested_kwarg` because these are different
    # questions: that one asks "which nested object has a schema to check",
    # this one asks "where did the parameter that broke end up". Anthropic
    # sends it through `extra_body`, which has no schema by design.
    temperature_kwarg: str | None = None


def _anthropic_family() -> _Family:
    def install(provider: Any, sink: dict[str, Any]) -> None:
        provider.client.messages.stream = _recorder(sink)

    def real() -> Any:
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=DUMMY_KEY).messages.stream

    return _Family(
        name="anthropic",
        model="claude-haiku-4-5",
        build_provider=lambda: AnthropicProvider(api_key=DUMMY_KEY),
        install_recorder=install,
        real_method=real,
        # 1.x dropped temperature from the typed signature, so the provider
        # routes it through extra_body. The guard below follows it there.
        temperature_kwarg="extra_body",
    )


def _openai_family() -> _Family:
    def install(provider: Any, sink: dict[str, Any]) -> None:
        provider.client.chat.completions.create = _recorder(sink)

    def real() -> Any:
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=DUMMY_KEY).chat.completions.create

    return _Family(
        name="openai",
        model="gpt-5.4",
        build_provider=lambda: OpenAIProvider(api_key=DUMMY_KEY),
        install_recorder=install,
        real_method=real,
    )


def _google_family() -> _Family:
    def install(provider: Any, sink: dict[str, Any]) -> None:
        provider.client.aio.models.generate_content_stream = _recorder(sink)

    def real() -> Any:
        from google import genai

        return genai.Client(api_key=DUMMY_KEY).aio.models.generate_content_stream

    def nested() -> set[str]:
        from google.genai import types

        return set(types.GenerateContentConfig.model_fields)

    return _Family(
        name="google",
        model="gemini-3.5-flash",
        build_provider=lambda: GoogleProvider(api_key=DUMMY_KEY),
        install_recorder=install,
        real_method=real,
        nested_kwarg="config",
        nested_fields=nested,
        temperature_kwarg="config",
    )


def _mistral_family() -> _Family:
    def install(provider: Any, sink: dict[str, Any]) -> None:
        provider.client.chat.stream_async = _recorder(sink)

    def real() -> Any:
        from mistralai.client import Mistral

        return Mistral(api_key=DUMMY_KEY).chat.stream_async

    return _Family(
        name="mistral",
        model="mistral-large-latest",
        build_provider=lambda: MistralProvider(api_key=DUMMY_KEY),
        install_recorder=install,
        real_method=real,
    )


FAMILIES: list[_Family] = [
    _anthropic_family(),
    _openai_family(),
    _google_family(),
    _mistral_family(),
]
FAMILY_IDS = [f.name for f in FAMILIES]


def _capture_kwargs(family: _Family) -> dict[str, Any]:
    """Drive the provider's real streaming path until the recorder fires."""
    provider = family.build_provider()
    sink: dict[str, Any] = {}
    family.install_recorder(provider, sink)

    async def _drive() -> None:
        agen = provider.stream(PROMPT, family.model, 0.7)
        try:
            await agen.__anext__()
        finally:
            await agen.aclose()

    with pytest.raises(_RecordedError):
        asyncio.run(_drive())

    assert sink, f"{family.name}: recorder fired but captured no keywords"
    return dict(sink)


# ===== the checks =====


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_built_kwargs_are_accepted_by_the_real_sdk(family: _Family) -> None:
    """Every keyword the provider sends must exist on the installed SDK method.

    This is the check the permissive doubles cannot make. It fails on exactly
    the class of breakage that shipped silently before: a parameter the
    provider still sends that the SDK no longer declares.
    """
    built = set(_capture_kwargs(family))
    declared = set(inspect.signature(family.real_method()).parameters)

    unsupported = built - declared
    assert not unsupported, (
        f"{family.name}: the provider sends {sorted(unsupported)}, which the installed "
        f"SDK method does not declare. A live call raises TypeError before any HTTP "
        f"request. Sent: {sorted(built)}. Declared: {sorted(declared)}."
    )


@pytest.mark.parametrize(
    "family",
    [f for f in FAMILIES if f.nested_kwarg],
    ids=[f.name for f in FAMILIES if f.nested_kwarg],
)
def test_nested_config_keys_are_accepted_by_the_real_sdk(family: _Family) -> None:
    """Keys inside a nested settings object are checked the same way.

    Google takes its per-request settings as `config=`, so the outer keyword
    check above would pass even if every key inside it were wrong.
    """
    assert family.nested_kwarg is not None
    assert family.nested_fields is not None

    captured = _capture_kwargs(family)
    config = captured.get(family.nested_kwarg)
    assert isinstance(config, dict), (
        f"{family.name}: expected {family.nested_kwarg}= to be a dict, got {type(config)!r}"
    )

    declared = family.nested_fields()
    unsupported = set(config) - declared
    assert not unsupported, (
        f"{family.name}: {family.nested_kwarg}= carries {sorted(unsupported)}, which the "
        f"installed SDK's config model does not declare."
    )


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_no_target_method_accepts_var_keyword(family: _Family) -> None:
    """The subset check is only meaningful against a typed signature.

    If an SDK method grows `**kwargs`, every keyword becomes 'supported' and
    the check above passes vacuously. Pin the assumption so that change is
    visible rather than silent.
    """
    params = inspect.signature(family.real_method()).parameters
    var_keyword = [
        name for name, p in params.items() if p.kind is inspect.Parameter.VAR_KEYWORD
    ]
    assert not var_keyword, (
        f"{family.name}: the SDK method now declares {var_keyword}, so "
        f"test_built_kwargs_are_accepted_by_the_real_sdk no longer proves anything. "
        f"Check that method's real accepted set another way."
    )


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILY_IDS)
def test_temperature_is_sent_for_a_model_that_accepts_it(family: _Family) -> None:
    """The chosen fixture model must actually exercise the temperature path.

    Each family above is pinned to a registry model that does NOT carry
    `rejects_sampling_params`. If that flag were ever added to one of them the
    conformance check would still pass, but it would stop covering the
    parameter that actually broke. Guard the fixture, not just the result.
    """
    captured = _capture_kwargs(family)
    if family.temperature_kwarg:
        carrier = captured.get(family.temperature_kwarg) or {}
        where = f"{family.temperature_kwarg}="
    else:
        carrier = captured
        where = "the top level"
    assert "temperature" in carrier, (
        f"{family.name}: model {family.model!r} did not send temperature under "
        f"{where}, so this family no longer covers the parameter class that broke. "
        f"Either the model gained rejects_sampling_params, or the provider moved "
        f"the parameter and `temperature_kwarg` needs updating. Captured: "
        f"{sorted(captured)}."
    )
