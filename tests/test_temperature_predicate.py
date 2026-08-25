"""Tests for the rejects_sampling_params predicate and its wiring.

Twelve models 400 unless temperature is exactly the provider default; omitting
the field always works. The predicate flags those twelve in PRICING and both
request builders consult it.

The default direction is load-bearing: ABSENT MEANS SEND. Anything not carrying
the flag - the other registry entries, local ids, OpenRouter passthrough ids,
and any model added in future - keeps receiving temperature. These tests pin
that, so an inversion cannot land quietly.
"""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from cli_modelarium import cli as cli_module
from cli_modelarium.cli import _models_without_temperature
from cli_modelarium.judging import JudgeResult, JudgeScore, run_judging
from cli_modelarium.models_registry import MODEL_GROUPS
from cli_modelarium.output_formatters import (
    BatchResult,
    _format_json,
    _format_markdown,
    write_json,
)
from cli_modelarium.pricing import PRICING, RETIRED_MODELS, rejects_sampling_params
from cli_modelarium.providers.anthropic_provider import AnthropicProvider
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk
from cli_modelarium.providers.local_provider import LocalProvider
from cli_modelarium.providers.openai_provider import OpenAIProvider
from cli_modelarium.streaming import StreamState
from tests.conftest import count_panels, flatten_rendered

# The measured rejecting models, DERIVED from the registry flag rather than
# hardcoded. A second hardcoded copy would be a second thing to update.
REJECTING = sorted(m for m, v in PRICING.items() if v.get("rejects_sampling_params"))

ANTHROPIC_REJECTING = [m for m in REJECTING if PRICING[m]["provider"] == "anthropic"]
OPENAI_REJECTING = [m for m in REJECTING if PRICING[m]["provider"] == "openai"]


# ===== fake plumbing =====


class _FakeCompletions:
    """Records the kwargs an OpenAI-compatible request was built with."""

    def __init__(self) -> None:
        self.last_kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        raise _StopCallError


class _StopCallError(Exception):
    """Aborts the call once kwargs are captured; we only care about the request."""


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = _FakeChat(completions)


def _openai_kwargs(cls: type, model: str, temperature: float = 0.7) -> dict[str, Any]:
    """Build a request through `cls` and return the kwargs that reached create()."""
    completions = _FakeCompletions()
    provider = cls.__new__(cls)
    provider.client = _FakeClient(completions)
    try:
        asyncio.run(provider.complete("p", model, temperature))
    except _StopCallError:
        pass
    except Exception:
        pass
    return completions.last_kwargs


def _anthropic_kwargs(model: str, temperature: float = 0.7) -> dict[str, Any]:
    provider = AnthropicProvider.__new__(AnthropicProvider)
    return provider._build_kwargs("p", model, temperature, None)


# ===== 7d: contract-checking fake =====


class ContractCheckingProvider(OpenAIProvider):
    """A fake that enforces the real API contract locally.

    Every other fake in this suite accepts **kwargs and never validates
    model-versus-parameter compatibility. Nine models were completely
    uncallable against a green suite. This one raises a
    simulated 400 when temperature reaches a model that rejects it, turning an
    external API fact into a local invariant.

    Its reject set is DERIVED from PRICING's flag, so the fake and the registry
    cannot disagree.
    """

    def __init__(self) -> None:  # noqa: D107 - no API key needed
        self.seen: list[dict[str, Any]] = []

    def simulate(self, model: str, kwargs: dict[str, Any]) -> None:
        self.seen.append({"model": model, **kwargs})
        if "temperature" in kwargs and rejects_sampling_params(model):
            raise AssertionError(
                f"simulated 400: 'temperature' is not supported by {model}. "
                f"Only the default value is supported."
            )


def _assert_contract(model: str, kwargs: dict[str, Any]) -> None:
    ContractCheckingProvider().simulate(model, kwargs)


# ===== the predicate itself =====


class TestPredicate:
    def test_the_flagged_set_is_exactly_the_measured_twelve(self) -> None:
        # A tripwire, not a fact about the registry's size: the flag may only
        # be set for a model someone has actually measured a 400 from, so
        # growing this number must be a deliberate edit. Nine in 0.1.5; the
        # three gpt-5.6 models were measured 2026-08-07 and added.
        assert len(REJECTING) == 12, REJECTING

    def test_no_entry_carries_a_false_flag(self) -> None:
        # Absent means send; an explicit False would be a confusing second way
        # to say the same thing.
        explicit_false = [
            m for m, v in PRICING.items() if v.get("rejects_sampling_params") is False
        ]
        assert explicit_false == []

    def test_local_short_circuit_is_first(self) -> None:
        # A local id whose stripped form collides with a rejecting id must
        # still send. This is the structural backstop for the Section 3 trap.
        assert rejects_sampling_params("local/gpt-5") is False
        assert rejects_sampling_params("local/claude-opus-5-gguf") is False

    def test_absent_from_pricing_defaults_to_send(self) -> None:
        assert rejects_sampling_params("someorg/not-in-registry-v9") is False


# ===== 7c item 1: the flagged models omit =====


@pytest.mark.parametrize("model", ANTHROPIC_REJECTING)
def test_anthropic_rejecting_models_omit_temperature(model: str) -> None:
    kwargs = _anthropic_kwargs(model)
    assert "temperature" not in kwargs, model
    _assert_contract(model, kwargs)


@pytest.mark.parametrize("model", OPENAI_REJECTING)
def test_openai_rejecting_models_omit_temperature(model: str) -> None:
    kwargs = _openai_kwargs(OpenAIProvider, model)
    assert "temperature" not in kwargs, model
    _assert_contract(model, kwargs)


# ===== 7c item 2: unaffected models still send =====


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    ],
)
def test_unaffected_anthropic_models_send_temperature(model: str) -> None:
    kwargs = _anthropic_kwargs(model)
    assert kwargs["temperature"] == 0.7, model
    _assert_contract(model, kwargs)


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-4o-mini",
        "grok-4.3",
        "llama-3.3-70b-versatile",
        "glm-5.2",
        "qwen3.7-max",
        "qwen/qwen3.7-max",
        "deepseek-v4-pro",
    ],
)
def test_unaffected_openai_compatible_models_send_temperature(model: str) -> None:
    kwargs = _openai_kwargs(OpenAIProvider, model)
    assert kwargs["temperature"] == 0.7, model
    _assert_contract(model, kwargs)


# ===== 7c item 3: HIGHEST VALUE - local ids are never stripped =====


@pytest.mark.parametrize("model", ["local/gpt-5", "local/claude-opus-5-gguf"])
def test_local_ids_keep_temperature_despite_name_collision(model: str) -> None:
    """Pins the Section 3 trap.

    _transform_model rewrites these to bare `gpt-5` / `claude-opus-5-gguf` on
    the wire. If the predicate read `actual_model` instead of `model`, the
    first would match the reject set and lose temperature silently, on a local
    server that supports it perfectly.
    """
    kwargs = _openai_kwargs(LocalProvider, model)
    assert kwargs["temperature"] == 0.7, model
    # And the wire id really is the stripped form - proving the collision is
    # live and the test is not passing for the wrong reason.
    assert kwargs["model"] == model.removeprefix("local/")


# ===== 7c item 4: OpenRouter passthrough =====


def test_openrouter_passthrough_not_in_pricing_sends_temperature() -> None:
    model = "someorg/some-brand-new-model-v3"
    assert model not in PRICING
    kwargs = _openai_kwargs(OpenAIProvider, model)
    assert kwargs["temperature"] == 0.7


# ===== 7c item 5: hypothetical future ids default to SEND =====


@pytest.mark.parametrize("model", ["claude-opus-6", "gpt-5.7"])
def test_future_model_ids_default_to_sending_temperature(model: str) -> None:
    """Documents the default direction so the choice stays reviewable.

    A newly-restricted model added without the flag throws a loud 400 naming
    the parameter. Under a default-omit design it would instead lose
    temperature silently, with no error and no test failure.
    """
    assert model not in PRICING
    assert rejects_sampling_params(model) is False


# ===== 7c item 7: the six removals =====


class TestRemovedEntries:
    REMOVED = [
        "gpt-5.5-pro",
        "gpt-5.4-pro",
        "gpt-5.3-codex",
        "gpt-5.3-codex-spark",
        "gpt-oss-120b",
        "gpt-oss-20b",
    ]

    @pytest.mark.parametrize("model", REMOVED)
    def test_absent_from_pricing(self, model: str) -> None:
        assert model not in PRICING

    @pytest.mark.parametrize("model", REMOVED)
    def test_absent_from_retired_models(self, model: str) -> None:
        # None were provider-retired: three work on a different endpoint and
        # three never existed. "Unknown model" is the accurate error.
        assert model not in RETIRED_MODELS

    def test_all_open_weight_has_four_working_members(self) -> None:
        members = MODEL_GROUPS["all-open-weight"]
        assert len(members) == 4
        assert all(m in PRICING for m in members), members
        assert "openai/gpt-oss-120b" in members
        assert "openai/gpt-oss-safeguard-20b" in members
        # The Groq-served replacements, not the removed openai-provider ones.
        assert all(PRICING[m]["provider"] == "groq" for m in members[:2])


# ===== 7c item 8: the JSON key, on BOTH output paths =====


def _result(model: str) -> BatchResult:
    return BatchResult(
        prompt_id="p1",
        prompt="hi",
        system=None,
        model=model,
        temperature=0.0,
        latency_ms=1.0,
        ttft_ms=1.0,
        input_tokens=1,
        output_tokens=1,
        cached_tokens=0,
        cost_usd=0.0,
        output="x",
        error=None,
        retries=0,
    )


class TestModelsWithoutTemperatureKey:
    """The key must be present unconditionally, on both call sites.

    A parameter threaded through only one of _format_json / write_json would
    put the key on one output path and not the other, which nothing else in
    the suite would catch.
    """

    def test_empty_list_when_no_rejecting_model_stdout_path(self) -> None:
        payload = json.loads(_format_json([_result("gpt-5.4")], models_without_temperature=[]))
        assert payload["models_without_temperature"] == []

    def test_empty_list_when_no_rejecting_model_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "o.json"
            write_json([_result("gpt-5.4")], out, models_without_temperature=[])
            payload = json.loads(out.read_text())
        assert payload["models_without_temperature"] == []

    def test_present_when_runs_unset(self) -> None:
        # runs defaults to 1; the methodology block is absent here, which is
        # exactly the case this key exists to cover.
        payload = json.loads(_format_json([_result("gpt-5.4")], models_without_temperature=[]))
        assert "models_without_temperature" in payload
        assert "methodology" not in payload

    def test_top_level_alongside_version_and_pricing_as_of(self) -> None:
        payload = json.loads(_format_json([_result("gpt-5.4")], models_without_temperature=[]))
        for key in ("version", "pricing_as_of", "models_without_temperature"):
            assert key in payload

    def test_populated_with_only_the_rejecting_model_stdout_path(self) -> None:
        models = ["claude-opus-5", "gpt-5.4"]
        payload = json.loads(
            _format_json(
                [_result(m) for m in models],
                models_without_temperature=_models_without_temperature(models),
            )
        )
        assert payload["models_without_temperature"] == ["claude-opus-5"]

    def test_populated_with_only_the_rejecting_model_file_path(self) -> None:
        models = ["claude-opus-5", "gpt-5.4"]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "o.json"
            write_json(
                [_result(m) for m in models],
                out,
                models_without_temperature=_models_without_temperature(models),
            )
            payload = json.loads(out.read_text())
        assert payload["models_without_temperature"] == ["claude-opus-5"]

    def test_helper_never_lists_a_user_supplied_id(self) -> None:
        # A passthrough id is absent from PRICING, so the predicate is False and
        # it can never enter this list. Keeps user-typed strings out of a file
        # someone might share or commit.
        assert _models_without_temperature(["someorg/sk-looks-like-a-secret"]) == []


# ===== 7c item 6: the judge path omits AND records =====


class _BuilderBackedJudgeProvider(BaseProvider):
    """A judge provider whose wire kwargs come from the REAL request builder.

    The other judge fakes in this suite swallow `temperature` into a recorded
    dict, so they would happily "succeed" against a model the live API rejects.
    This one routes the judge's temperature through
    AnthropicProvider._build_kwargs, then hands the result to the Section 7d
    contract checker - so the assertion under test is the same fact the API
    enforces, not a restatement of the fake.
    """

    name = "anthropic"

    def __init__(self) -> None:
        self.wire_kwargs: list[dict[str, Any]] = []

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if False:  # pragma: no cover - judges never stream
            yield ""
        raise NotImplementedError

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
        *,
        on_chunk: OnChunk | None = None,
    ) -> CompletionResult:
        builder = AnthropicProvider.__new__(AnthropicProvider)
        kwargs = builder._build_kwargs(prompt, model, temperature, system_prompt)
        self.wire_kwargs.append(kwargs)
        _assert_contract(model, kwargs)
        return CompletionResult(
            output='{"score": 8, "reasoning": "ok"}',
            model=model,
            temperature=temperature,
            input_tokens=1,
            output_tokens=1,
            cached_tokens=0,
            cost_usd=0.0,
            latency_ms=1.0,
            ttft_ms=1.0,
        )


def _state(model: str) -> StreamState:
    return StreamState(model=model, provider_name="anthropic", temperature=0.7, text="answer")


class TestJudgeDegradation:
    """A rejecting judge must both survive the call and be declared degraded.

    Only asserting on `degraded_models` would pass even if the judge call
    still put temperature on the wire - which is the failure that makes the
    judge uncallable. Only asserting on the kwargs would pass even if the
    caveat never reached the user. Both halves are checked together.
    """

    def test_rejecting_judge_omits_temperature_and_is_recorded(self) -> None:
        judge = "claude-opus-5"
        assert rejects_sampling_params(judge)
        provider = _BuilderBackedJudgeProvider()
        results = asyncio.run(
            run_judging(
                [(_state("gpt-5.4"), "orig")],
                [judge],
                ["accuracy"],
                lambda _name: provider,
            )
        )
        # The judge really ran and really scored.
        assert len(provider.wire_kwargs) == 1
        assert results[0].judges[0].score == 8
        # ...with no temperature on the wire...
        assert "temperature" not in provider.wire_kwargs[0]
        # ...and the loss of determinism declared.
        assert results[0].degraded_models == [judge]

    def test_unaffected_judge_sends_zero_and_is_not_recorded(self) -> None:
        judge = "claude-sonnet-4-6"
        provider = _BuilderBackedJudgeProvider()
        results = asyncio.run(
            run_judging(
                [(_state("gpt-5.4"), "orig")],
                [judge],
                ["accuracy"],
                lambda _name: provider,
            )
        )
        # score_with_judge still asks for 0.0; the builder passes it through.
        assert provider.wire_kwargs[0]["temperature"] == 0.0
        assert results[0].degraded_models == []

    def test_mixed_panel_records_only_the_rejecting_judge(self) -> None:
        provider = _BuilderBackedJudgeProvider()
        results = asyncio.run(
            run_judging(
                [(_state("gpt-5.4"), "orig")],
                ["claude-opus-5", "claude-sonnet-4-6"],
                ["accuracy"],
                lambda _name: provider,
            )
        )
        assert results[0].degraded_models == ["claude-opus-5"]
        assert len(results[0].judges) == 2

    def test_failed_main_call_reports_no_degradation(self) -> None:
        # An errored state is never judged, so claiming a degraded judge here
        # would be a caveat about a call that never happened.
        state = _state("gpt-5.4")
        state.error = "boom"
        results = asyncio.run(
            run_judging([(state, "orig")], ["claude-opus-5"], ["accuracy"], lambda _n: None)
        )
        assert results[0].degraded_models == []


# ===== 7c item 9: the MARKDOWN surface renders the caveat =====


def _judged(model: str, judge_result: JudgeResult) -> BatchResult:
    r = _result(model)
    r.judge_result = judge_result
    return r


def _scored(*, degraded: list[str], judges: list[JudgeScore]) -> JudgeResult:
    successful = [j.score for j in judges if j.score is not None]
    return JudgeResult(
        judges=judges,
        average_score=sum(successful) / len(successful) if successful else None,
        degraded_models=degraded,
    )


def _score(model: str, score: int | None, parse_error: str | None = None) -> JudgeScore:
    return JudgeScore(
        model=model,
        score=score,
        reasoning="r",
        cost_usd=0.0,
        latency_ms=1.0,
        parse_error=parse_error,
    )


class TestMarkdownDegradedCaveat:
    """Rendered markdown, not the dataclass.

    A degraded judge still produces a score, so it never reaches the "no
    judges" early return. If the caveat had been attached there it would be
    invisible in exactly the case it exists for - which asserting on
    `degraded_models` alone would not catch.
    """

    def test_single_judge_row_carries_the_caveat(self) -> None:
        md = _format_markdown(
            [
                _judged(
                    "gpt-5.4",
                    _scored(degraded=["claude-opus-5"], judges=[_score("claude-opus-5", 8)]),
                )
            ]
        )
        assert "degraded: claude-opus-5" in md

    def test_panel_row_carries_the_caveat_alongside_the_average(self) -> None:
        md = _format_markdown(
            [
                _judged(
                    "gpt-5.4",
                    _scored(
                        degraded=["claude-opus-5"],
                        judges=[_score("claude-opus-5", 8), _score("claude-sonnet-4-6", 6)],
                    ),
                )
            ]
        )
        assert "Avg 7.0" in md
        assert "degraded: claude-opus-5" in md

    def test_parse_failed_row_still_carries_the_caveat(self) -> None:
        md = _format_markdown(
            [
                _judged(
                    "gpt-5.4",
                    _scored(
                        degraded=["claude-opus-5"],
                        judges=[_score("claude-opus-5", None, "bad")],
                    ),
                )
            ]
        )
        assert "N/A (judge parse failed)" in md
        assert "degraded: claude-opus-5" in md

    def test_undegraded_row_says_nothing(self) -> None:
        md = _format_markdown(
            [_judged("gpt-5.4", _scored(degraded=[], judges=[_score("claude-sonnet-4-6", 8)]))]
        )
        assert "degraded" not in md


# ===== 7c item 10: the CONSOLE surface renders text =====


@pytest.fixture
def captured_console(
    monkeypatch: pytest.MonkeyPatch, capture_console: Console
) -> io.StringIO:
    """Swap cli's module-level console for the width-pinned shared one."""
    monkeypatch.setattr(cli_module, "console", capture_console)
    return capture_console.file  # type: ignore[return-value]


class TestConsoleDegradedNote:
    """The console is the primary surface; it must print real words.

    The Score column never displayed `skipped_models` either, so reusing that
    plumbing would have produced a caveat nobody sees. These assert on the
    rendered buffer.
    """

    def test_note_names_the_model_and_explains_the_consequence(
        self, captured_console: io.StringIO
    ) -> None:
        cli_module._display_results(
            [_state("gpt-5.4")],
            judge_results=[
                _scored(degraded=["claude-opus-5"], judges=[_score("claude-opus-5", 8)])
            ],
        )
        out = captured_console.getvalue()
        assert "claude-opus-5" in out
        assert "determinism not guaranteed" in out
        assert "not reproducible" in out

    def test_note_absent_when_no_judge_is_degraded(self, captured_console: io.StringIO) -> None:
        cli_module._display_results(
            [_state("gpt-5.4")],
            judge_results=[_scored(degraded=[], judges=[_score("claude-sonnet-4-6", 8)])],
        )
        assert "determinism not guaranteed" not in captured_console.getvalue()

    def test_note_absent_when_judging_was_not_requested(
        self, captured_console: io.StringIO
    ) -> None:
        cli_module._display_results([_state("gpt-5.4")])
        assert "determinism not guaranteed" not in captured_console.getvalue()

    def test_one_note_lists_every_degraded_judge_once(
        self, captured_console: io.StringIO
    ) -> None:
        # Two rows judged by the same degraded panel must not repeat the model.
        degraded = ["claude-opus-5", "claude-opus-4-8"]
        cli_module._display_results(
            [_state("gpt-5.4"), _state("grok-4.3")],
            judge_results=[
                _scored(degraded=degraded, judges=[_score(m, 8) for m in degraded]),
                _scored(degraded=degraded, judges=[_score(m, 8) for m in degraded]),
            ],
        )
        out = captured_console.getvalue()
        note = out[out.index("determinism not guaranteed") :]
        assert note.count("claude-opus-5") == 1
        assert note.count("claude-opus-4-8") == 1


# ===== the Section 6 sweep warning =====


class TestSweepWarning:
    """Section 9 verifies this by hand and notes nothing else covers it.

    Both call sites take the same helper, so testing the helper covers compare
    and batch alike; a missing call site is what the manual step catches.
    """

    def test_fires_for_a_rejecting_model_on_a_multi_value_sweep(
        self, captured_console: io.StringIO
    ) -> None:
        cli_module._warn_temperature_sweep(["claude-opus-5", "gpt-5.4"], [0.0, 0.5, 1.0])
        out = captured_console.getvalue()
        assert "Temperature not applied" in out
        assert "claude-opus-5" in out
        # The accepting model in the same run must not be implicated.
        assert "gpt-5.4" not in out
        assert "identical rather than a sweep" in out
        assert "what was requested, not what was applied" in out

    def test_names_group_members_the_user_never_typed(
        self, captured_console: io.StringIO
    ) -> None:
        # Group expansion runs before the warning, so `all-premium` has already
        # become concrete ids. This is the case the warning matters most for.
        expanded = MODEL_GROUPS["all-premium"]
        assert "gpt-5.6-sol" in expanded and "claude-opus-5" in expanded
        cli_module._warn_temperature_sweep(list(expanded), [0.0, 1.0])
        out = captured_console.getvalue()
        assert "gpt-5.6-sol" in out
        assert "claude-opus-5" in out

    def test_silent_when_only_one_temperature_requested(
        self, captured_console: io.StringIO
    ) -> None:
        cli_module._warn_temperature_sweep(["claude-opus-5"], [0.0])
        assert captured_console.getvalue() == ""

    def test_silent_when_no_model_rejects(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_sweep(["gpt-5.4", "grok-4.3"], [0.0, 0.5, 1.0])
        assert captured_console.getvalue() == ""

    def test_agrees_in_number_with_the_models_it_names(
        self, captured_console: io.StringIO
    ) -> None:
        cli_module._warn_temperature_sweep(["claude-opus-5"], [0.0, 1.0])
        assert "does not accept" in captured_console.getvalue()

    def test_plural_form_for_several_models(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_sweep(["claude-opus-5", "gpt-5.5"], [0.0, 1.0])
        assert "do not accept" in captured_console.getvalue()


# ===== the significance/temperature mixing caveat =====

# Both halves DERIVED from the registry flag, never hardcoded. The unaffected
# half is additionally filtered to priced cloud entries so a compare invocation
# produces a non-zero estimate and the --max-cost gate below actually bites.
UNAFFECTED = sorted(
    m
    for m, v in PRICING.items()
    if not v.get("rejects_sampling_params")
    and not v.get("is_local")
    and float(v.get("input", 0.0)) > 0.0
)

MIXED_PAIR = [REJECTING[0], UNAFFECTED[0]]
ALL_AFFECTED_PAIR = REJECTING[:2]
ALL_UNAFFECTED_PAIR = UNAFFECTED[:2]

# Signature phrases, one per message, so a merged panel can be told apart from
# a panel carrying only half its content.
SWEEP_PHRASE = "identical rather than a sweep"
VERDICT_PHRASE = "rather than a difference in model quality"


# Both delegate to conftest, which handles the POSIX/Windows corner-glyph
# split. Counting only `╭` is what turned all four Windows CI jobs red.
_panel_count = count_panels
_flat = flatten_rendered


def _compare(*args: str) -> Any:
    """Invoke `compare` with a cost ceiling that halts it before any network call.

    The temperature warning is emitted during argument resolution, well before
    the --max-cost gate, so the warning renders and the run then exits 2 without
    touching a provider. Every model used here is priced above zero, which is
    what makes the gate fire.
    """
    from click.testing import CliRunner

    from cli_modelarium.cli import main as cli_main

    return CliRunner().invoke(
        cli_main, ["compare", "--max-cost", "0.0000001", "--no-stream", *args, "hi"]
    )


class TestMixesTemperatureHandling:
    """Item j3: the split itself, on its return value rather than rendered text."""

    def test_every_model_affected_is_not_mixed(self) -> None:
        omitted, honoured = cli_module._mixes_temperature_handling(list(ALL_AFFECTED_PAIR))
        assert omitted == sorted(ALL_AFFECTED_PAIR)
        assert honoured == []

    def test_no_model_affected_is_not_mixed(self) -> None:
        omitted, honoured = cli_module._mixes_temperature_handling(list(ALL_UNAFFECTED_PAIR))
        assert omitted == []
        assert honoured == sorted(ALL_UNAFFECTED_PAIR)

    def test_a_mix_of_both_is_mixed(self) -> None:
        omitted, honoured = cli_module._mixes_temperature_handling(list(MIXED_PAIR))
        assert omitted == [REJECTING[0]]
        assert honoured == [UNAFFECTED[0]]
        assert omitted and honoured

    def test_halves_partition_the_input(self) -> None:
        # No model may be lost or counted twice: the two halves must reconstruct
        # the de-duplicated input exactly.
        models = [*MIXED_PAIR, REJECTING[0], MODEL_GROUPS["all-flagship"][0]]
        omitted, honoured = cli_module._mixes_temperature_handling(models)
        assert set(omitted) | set(honoured) == set(models)
        assert set(omitted).isdisjoint(honoured)

    def test_omitted_half_matches_the_existing_helper(self) -> None:
        # The two must not drift; the split is defined in terms of that helper.
        models = list(MODEL_GROUPS["all-flagship"])
        omitted, _ = cli_module._mixes_temperature_handling(models)
        assert omitted == _models_without_temperature(models)

    def test_unregistered_ids_land_in_the_honoured_half(self) -> None:
        # Local and OpenRouter passthrough ids keep receiving temperature, so
        # they are honoured - never named as having run at a default.
        omitted, honoured = cli_module._mixes_temperature_handling(
            ["local/llama-3.3-70b", "vendor/some-passthrough-id", REJECTING[0]]
        )
        assert omitted == [REJECTING[0]]
        assert honoured == ["local/llama-3.3-70b", "vendor/some-passthrough-id"]


class TestSignificanceWillRun:
    """The tri-state gate, pinned exhaustively.

    `--significance` is `bool | None`; None means auto-enable. An implementation
    written as `if significance` reads the DEFAULT path as off, which is exactly
    the path with no signal before this change.
    """

    @pytest.mark.parametrize(
        ("significance", "runs", "models", "expected"),
        [
            (None, 10, 2, True),  # the default path - the case this exists for
            (None, 1, 2, False),
            (None, 10, 1, False),
            (True, 10, 2, True),
            (True, 1, 2, False),  # explicit opt-in cannot beat the runs gate
            (True, 10, 1, False),
            (False, 10, 2, False),  # explicit opt-out always wins
            (False, 1, 2, False),
            (False, 10, 1, False),
        ],
    )
    def test_gate(self, significance: bool | None, runs: int, models: int, expected: bool) -> None:
        assert cli_module._significance_will_run(significance, runs, models) is expected

    def test_none_is_not_treated_as_false(self) -> None:
        # The single assertion that a falsy-None implementation fails.
        assert cli_module._significance_will_run(None, 10, 2) is True
        assert cli_module._significance_will_run(False, 10, 2) is False

    def test_matches_the_rule_compare_computes(self) -> None:
        # Equivalence with the documented guard across every input combination.
        for sig in (None, True, False):
            for runs in (1, 2, 10):
                for n in (1, 2, 5):
                    expected = sig is not False and runs > 1 and n >= 2
                    assert cli_module._significance_will_run(sig, runs, n) is expected


class TestTemperatureConditionsPanel:
    """Items a-e and j/j2: the panel the emitter renders, as rendered text."""

    def test_mixed_significance_run_warns(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_conditions(
            list(MIXED_PAIR), [0.0], significance_runs=True
        )
        out = _flat(captured_console.getvalue())
        assert "Temperature not applied" in out
        assert VERDICT_PHRASE in out
        assert "not sampled under identical" in out

    def test_it_names_the_models_that_ran_at_the_default(
        self, captured_console: io.StringIO
    ) -> None:
        cli_module._warn_temperature_conditions(
            list(MIXED_PAIR), [0.0], significance_runs=True
        )
        out = _flat(captured_console.getvalue())
        assert REJECTING[0] in out
        # By name, not by count: a message saying "1 model" must not pass.
        assert "1 model" not in out
        # And the honoured model is not implicated, nor rendered at all.
        assert UNAFFECTED[0] not in out

    def test_all_affected_run_does_not_warn(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_conditions(
            list(ALL_AFFECTED_PAIR), [0.0], significance_runs=True
        )
        assert captured_console.getvalue() == ""

    def test_all_unaffected_run_does_not_warn(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_conditions(
            list(ALL_UNAFFECTED_PAIR), [0.0], significance_runs=True
        )
        assert captured_console.getvalue() == ""

    def test_absence_tests_above_are_not_vacuous(self, captured_console: io.StringIO) -> None:
        # Positive control for the two silent cases: the SAME fixture and the
        # SAME call shape do render when the run is genuinely mixed. Without
        # this, a mis-wired fixture would make both silence assertions pass.
        cli_module._warn_temperature_conditions(
            list(MIXED_PAIR), [0.0], significance_runs=True
        )
        assert captured_console.getvalue() != ""

    def test_fires_with_a_single_temperature_value(
        self, captured_console: io.StringIO
    ) -> None:
        # The regression test for the actual gap: one temperature, no sweep, and
        # the old warning is silent here.
        cli_module._warn_temperature_conditions(
            list(MIXED_PAIR), [0.0], significance_runs=True
        )
        out = _flat(captured_console.getvalue())
        assert VERDICT_PHRASE in out
        assert SWEEP_PHRASE not in out
        assert _panel_count(captured_console.getvalue()) == 1

    def test_multi_temperature_not_mixed_keeps_the_sweep_warning_alone(
        self, captured_console: io.StringIO
    ) -> None:
        # Item j2, the suppression regression test. All models affected, so the
        # run is not mixed - the sweep warning must survive untouched.
        cli_module._warn_temperature_conditions(
            list(ALL_AFFECTED_PAIR), [0.0, 1.0], significance_runs=True
        )
        out = _flat(captured_console.getvalue())
        assert SWEEP_PHRASE in out
        assert VERDICT_PHRASE not in out
        assert _panel_count(captured_console.getvalue()) == 1

    def test_multi_temperature_mixed_merges_into_one_panel(
        self, captured_console: io.StringIO
    ) -> None:
        # Item j. Both assertions matter: counting panels alone would pass an
        # implementation that merged by discarding half the content.
        cli_module._warn_temperature_conditions(
            list(MIXED_PAIR), [0.0, 0.5, 1.0], significance_runs=True
        )
        out = _flat(captured_console.getvalue())
        assert _panel_count(captured_console.getvalue()) == 1
        assert SWEEP_PHRASE in out
        assert VERDICT_PHRASE in out

    def test_significance_off_leaves_the_sweep_warning_untouched(
        self, captured_console: io.StringIO
    ) -> None:
        # The fourth case: multi-temperature AND mixed, but no verdict is being
        # computed (compare left at the default --runs 1). Caveating a verdict
        # that does not exist would be wrong; the sweep warning still fires.
        cli_module._warn_temperature_conditions(
            list(MIXED_PAIR), [0.0, 1.0], significance_runs=False
        )
        out = _flat(captured_console.getvalue())
        assert SWEEP_PHRASE in out
        assert VERDICT_PHRASE not in out
        assert _panel_count(captured_console.getvalue()) == 1

    def test_silent_when_neither_condition_holds(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_conditions(
            list(MIXED_PAIR), [0.0], significance_runs=False
        )
        assert captured_console.getvalue() == ""

    def test_single_model_cannot_be_mixed(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_conditions(
            [REJECTING[0]], [0.0], significance_runs=True
        )
        assert captured_console.getvalue() == ""

    def test_empty_model_list_is_silent(self, captured_console: io.StringIO) -> None:
        # `all-local` with no server running expands to nothing.
        cli_module._warn_temperature_conditions([], [0.0, 1.0], significance_runs=True)
        assert captured_console.getvalue() == ""

    def test_local_only_run_is_silent(self, captured_console: io.StringIO) -> None:
        cli_module._warn_temperature_conditions(
            ["local/a", "local/b"], [0.0], significance_runs=True
        )
        assert captured_console.getvalue() == ""

    def test_the_honoured_half_is_never_rendered(self, captured_console: io.StringIO) -> None:
        # The omitted half is a subset of PRICING keys; the honoured half can be
        # any string the user typed. Rendering it would put unescaped
        # user-supplied text into a Rich panel.
        cli_module._warn_temperature_conditions(
            [REJECTING[0], "vendor/[red]not-a-model[/red]"], [0.0], significance_runs=True
        )
        out = _flat(captured_console.getvalue())
        assert VERDICT_PHRASE in out
        assert "not-a-model" not in out


class TestTemperatureWarningWiring:
    """Items f, h and i: the guard as `compare` actually computes it."""

    def test_fires_on_the_default_path_with_no_significance_flag(
        self, captured_console: io.StringIO
    ) -> None:
        # Item i, the tri-state regression test end to end. --significance is
        # never passed; auto-enablement must still produce the caveat.
        result = _compare("--models", ",".join(MIXED_PAIR), "--runs", "10")
        out = _flat(captured_console.getvalue())
        assert result.exit_code == 2, out
        assert VERDICT_PHRASE in out
        assert REJECTING[0] in out

    def test_does_not_fire_with_no_significance(
        self, captured_console: io.StringIO
    ) -> None:
        # Item h: without a verdict there is nothing to caveat.
        result = _compare(
            "--models", ",".join(MIXED_PAIR), "--runs", "10", "--no-significance"
        )
        out = _flat(captured_console.getvalue())
        assert result.exit_code == 2, out
        assert VERDICT_PHRASE not in out

    def test_does_not_fire_at_the_default_single_run(
        self, captured_console: io.StringIO
    ) -> None:
        result = _compare("--models", ",".join(MIXED_PAIR))
        out = _flat(captured_console.getvalue())
        assert result.exit_code == 2, out
        assert VERDICT_PHRASE not in out

    def test_fires_for_a_model_the_user_never_typed(
        self, captured_console: io.StringIO
    ) -> None:
        # Item f. all-flagship is verified mixed here rather than trusted by
        # name: membership drifts, and a group that stopped qualifying would
        # otherwise turn this into a silently vacuous test.
        group = MODEL_GROUPS["all-flagship"]
        omitted, honoured = cli_module._mixes_temperature_handling(list(group))
        assert omitted and honoured, "all-flagship is no longer a mixed group"

        result = _compare("--models", "all-flagship", "--runs", "5")
        out = _flat(captured_console.getvalue())
        assert result.exit_code == 2, out
        assert VERDICT_PHRASE in out
        for model in omitted:
            assert model in out

    def test_group_expansion_happens_before_the_warning(
        self, captured_console: io.StringIO
    ) -> None:
        # The group NAME must not appear; the concrete ids must. A warning
        # emitted before expansion would print "all-flagship" and name nothing.
        result = _compare("--models", "all-flagship", "--runs", "5")
        out = _flat(captured_console.getvalue())
        assert result.exit_code == 2, out
        assert "all-flagship" not in out


class TestBatchCannotCaveatAVerdict:
    """Item g, corrected: `batch` has no verdict to caveat.

    The changeset asked for a batch warning on the grounds that "both can run
    significance". It cannot: `batch` exposes neither --runs nor --significance
    and never calls compute_significance_with_ci, so the mixed-sampling caveat
    has nothing to attach to there. These pin that, so the day `batch` gains
    --runs the omission surfaces as a failure rather than as silence.
    """

    def test_batch_exposes_no_significance_or_runs_flag(self) -> None:
        from cli_modelarium.cli import main as cli_main

        params = {
            opt
            for p in cli_main.commands["batch"].params
            for opt in getattr(p, "opts", [])
        }
        assert "--runs" not in params
        assert "--significance" not in params
        assert "--no-significance" not in params

    def test_compare_does_expose_them(self) -> None:
        from cli_modelarium.cli import main as cli_main

        params = {
            opt
            for p in cli_main.commands["compare"].params
            for opt in getattr(p, "opts", [])
        }
        assert "--runs" in params
        assert "--significance" in params

    def test_batch_still_emits_the_sweep_warning(
        self, captured_console: io.StringIO
    ) -> None:
        # What batch CAN say about temperature is unchanged by this change.
        cli_module._warn_temperature_sweep(list(MIXED_PAIR), [0.0, 1.0])
        out = _flat(captured_console.getvalue())
        assert SWEEP_PHRASE in out
        assert VERDICT_PHRASE not in out

    def test_batch_json_carries_the_key_as_false(self) -> None:
        payload = json.loads(
            _format_json([], models_without_temperature=[], significance_temperature_mixed=False)
        )
        assert payload["significance_temperature_mixed"] is False


class TestSignificanceTemperatureMixedJson:
    """Item k: the machine surface, on BOTH output paths."""

    def test_present_and_true_for_a_mixed_run_on_stdout_path(self) -> None:
        payload = json.loads(
            _format_json(
                [],
                runs=10,
                models_without_temperature=[REJECTING[0]],
                significance_temperature_mixed=True,
            )
        )
        assert payload["significance_temperature_mixed"] is True

    def test_present_and_false_for_a_reachable_unmixed_run(self) -> None:
        # The reachable unmixed case: JSON is produced, significance did not
        # mix anything, and the key must still be there.
        payload = json.loads(_format_json([], runs=10, models_without_temperature=[]))
        assert "significance_temperature_mixed" in payload
        assert payload["significance_temperature_mixed"] is False

    def test_present_on_the_file_path_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for expected in (True, False):
                path = Path(tmp) / f"out-{expected}.json"
                write_json(
                    [],
                    path,
                    runs=10,
                    models_without_temperature=[REJECTING[0]] if expected else [],
                    significance_temperature_mixed=expected,
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
                assert payload["significance_temperature_mixed"] is expected

    def test_key_is_always_present_even_at_runs_one(self) -> None:
        payload = json.loads(_format_json([]))
        assert "significance_temperature_mixed" in payload
        assert payload["significance_temperature_mixed"] is False

    def test_it_is_a_real_bool_not_a_truthy_value(self) -> None:
        # A consumer doing `is True` must not be broken by a list or an int.
        payload = json.loads(_format_json([], significance_temperature_mixed=1))
        assert payload["significance_temperature_mixed"] is True

    def test_it_sits_at_top_level_beside_models_without_temperature(self) -> None:
        payload = json.loads(_format_json([], runs=10))
        assert "significance_temperature_mixed" in payload
        assert "models_without_temperature" in payload
        # NOT in the methodology block, which is gated on runs > 1.
        assert "significance_temperature_mixed" not in payload.get("methodology", {})

    def test_models_without_temperature_still_behaves_as_before(self) -> None:
        payload = json.loads(_format_json([], models_without_temperature=[REJECTING[0]]))
        assert payload["models_without_temperature"] == [REJECTING[0]]
        assert json.loads(_format_json([]))["models_without_temperature"] == []

    def test_it_reaches_json_through_emit_batch_results_on_both_paths(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The forwards inside _emit_batch_results are the sites most easily
        # missed: a key wired into the file branch but not the stdout branch
        # would pass every direct _format_json test above.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            cli_module._emit_batch_results(
                [],
                output_path=path,
                output_fmt="json",
                significance_temperature_mixed=True,
            )
            assert json.loads(path.read_text(encoding="utf-8"))[
                "significance_temperature_mixed"
            ] is True
        # Drain the "Wrote <path>" notice so the stdout branch below is read
        # from an empty buffer.
        capsys.readouterr()

        cli_module._emit_batch_results(
            [],
            output_path=None,
            output_fmt="json",
            significance_temperature_mixed=True,
        )
        stdout = capsys.readouterr().out
        assert json.loads(stdout)["significance_temperature_mixed"] is True


class TestCsvUntouchedByTheMixedKey:
    """The key must not reach CSV; CSV_COLUMNS is byte-identical this change."""

    def test_csv_columns_unchanged(self) -> None:
        from cli_modelarium.output_formatters import CSV_COLUMNS

        assert len(CSV_COLUMNS) == 21
        assert "significance_temperature_mixed" not in CSV_COLUMNS
        assert CSV_COLUMNS[4] == "temperature"

    def test_write_csv_takes_no_such_parameter(self) -> None:
        import inspect

        from cli_modelarium.output_formatters import write_csv

        assert "significance_temperature_mixed" not in inspect.signature(write_csv).parameters


class TestCompareComputesTheJsonFlag:
    """The value `compare` actually passes, not just the plumbing that carries it.

    Every other JSON test here calls the formatters directly, so all of them
    would still pass if `compare` hardcoded the flag to False. These drive the
    real command and capture what it hands to the writer, with the network stub
    replacing only the execution step - model resolution, the tri-state guard
    and the mixing decision all run for real.
    """

    @staticmethod
    def _flag_for(
        monkeypatch: pytest.MonkeyPatch, capture_console: Console, *args: str
    ) -> object:
        import types

        from click.testing import CliRunner

        from cli_modelarium.cli import main as cli_main

        captured: dict[str, Any] = {}

        def fake_emit(results: list, **kwargs: Any) -> None:
            captured.update(kwargs)

        def fake_run(coro: Any) -> tuple[list, None]:
            coro.close()  # never awaited; avoids an un-awaited-coroutine warning
            return [], None

        monkeypatch.setattr(cli_module, "_emit_batch_results", fake_emit)
        monkeypatch.setattr(cli_module, "asyncio", types.SimpleNamespace(run=fake_run))
        monkeypatch.setattr(cli_module, "console", capture_console)

        result = CliRunner().invoke(
            cli_main, ["compare", "--output-format", "json", "--no-stream", *args, "hi"]
        )
        assert result.exit_code == 0, result.output
        assert "significance_temperature_mixed" in captured, "compare never passed the key"
        return captured["significance_temperature_mixed"]

    def test_true_for_a_mixed_significance_run(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        assert (
            self._flag_for(
                monkeypatch, capture_console, "--models", ",".join(MIXED_PAIR), "--runs", "5"
            )
            is True
        )

    def test_false_for_an_unmixed_run(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        assert (
            self._flag_for(
                monkeypatch,
                capture_console,
                "--models",
                ",".join(ALL_UNAFFECTED_PAIR),
                "--runs",
                "5",
            )
            is False
        )

    def test_false_for_an_all_affected_run(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        assert (
            self._flag_for(
                monkeypatch, capture_console, "--models", ",".join(ALL_AFFECTED_PAIR), "--runs", "5"
            )
            is False
        )

    def test_false_when_significance_is_disabled(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        # Mixed models, but no verdict is computed - so nothing to flag.
        assert (
            self._flag_for(
                monkeypatch,
                capture_console,
                "--models",
                ",".join(MIXED_PAIR),
                "--runs",
                "5",
                "--no-significance",
            )
            is False
        )

    def test_false_at_the_default_single_run(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        assert (
            self._flag_for(monkeypatch, capture_console, "--models", ",".join(MIXED_PAIR))
            is False
        )

    def test_true_for_a_group_the_user_never_typed(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        assert (
            self._flag_for(monkeypatch, capture_console, "--models", "all-flagship", "--runs", "5")
            is True
        )
