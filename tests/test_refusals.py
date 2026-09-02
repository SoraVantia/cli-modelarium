"""A refusal is reported as refused, not counted as an empty success.

`stop_reason: "refusal"` arrives on HTTP 200 with real cost and no answer.
Before this, the tool recorded it as an ordinary successful call with an empty
output, which made a declined-and-billed request indistinguishable from a model
that answered with nothing - and let a CI gate built from cost, latency,
`not_contains` and a length cap report a 100% pass rate on it.

The cases here pin the four things that behaviour rests on:

    detection    by `stop_reason`, never by an empty content array
    accounting   refused is neither succeeded nor failed, and keeps its cost
    assertions   every configured assertion errors rather than being evaluated
    statistics   output-derived metrics drop refusals; timing and cost do not
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from cli_modelarium.assertions import count_assertion_totals, refused_results
from cli_modelarium.batch import BatchPrompt
from cli_modelarium.cli import main as cli_main
from cli_modelarium.output_formatters import (
    CSV_COLUMNS,
    _format_csv,
    _format_json,
    state_to_result,
)
from cli_modelarium.providers.anthropic_provider import AnthropicProvider
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk
from cli_modelarium.run_statistics import compute_run_stats
from cli_modelarium.streaming import StreamState

ALL_TEN_ASSERTIONS: list[dict[str, Any]] = [
    {"type": "contains", "value": "ok"},
    {"type": "not_contains", "value": "banana"},
    {"type": "regex", "value": "^ok$"},
    {"type": "equals", "value": "ok"},
    {"type": "json_valid"},
    {"type": "json_schema", "value": {"type": "object"}},
    {"type": "min_length_chars", "value": 1},
    {"type": "max_length_chars", "value": 100},
    {"type": "latency_under", "value": 5000},
    {"type": "cost_under", "value": 1.0},
]

# The four that PASS against an empty string, which is what made a refusal
# look like a clean run: nothing to not-contain, zero characters is under any
# cap, and the latency and cost of a refusal are real numbers.
VACUOUS_ON_EMPTY = ("not_contains", "max_length_chars", "latency_under", "cost_under")


# ===== provider-level detection =====


class _FakeInnerStream:
    """The object yielded inside `async with messages.stream(...)`."""

    def __init__(self, chunks: list[str], final: Any) -> None:
        self._chunks = chunks
        self._final = final

    @property
    def text_stream(self) -> Any:
        async def gen() -> Any:
            for c in self._chunks:
                yield c

        return gen()

    async def get_final_message(self) -> Any:
        return self._final


class _FakeStreamManager:
    def __init__(self, inner: _FakeInnerStream) -> None:
        self._inner = inner

    async def __aenter__(self) -> _FakeInnerStream:
        return self._inner

    async def __aexit__(self, *_args: Any) -> bool:
        return False


def _opus5_shaped_refusal() -> Any:
    """A refusal shaped like the one claude-opus-5 actually returns.

    Deliberately NOT an empty content array: opus-5 refuses with a thinking
    block present and non-zero output tokens, while fable-5 refuses with
    nothing at all. A detector that tested "is content empty" would pass
    against fable-5 and silently miss this one.
    """
    return SimpleNamespace(
        stop_reason="refusal",
        stop_details=SimpleNamespace(type="refusal", category="reasoning_extraction"),
        content=[SimpleNamespace(type="thinking", thinking="")],
        usage=SimpleNamespace(input_tokens=51, output_tokens=4, cache_read_input_tokens=0),
    )


def _install_anthropic(monkeypatch: pytest.MonkeyPatch, final: Any, chunks: list[str]) -> Any:
    class _Messages:
        def stream(self, **_kwargs: Any) -> _FakeStreamManager:
            return _FakeStreamManager(_FakeInnerStream(chunks, final))

    class _Client:
        def __init__(self, **_kwargs: Any) -> None:
            self.messages = _Messages()

    monkeypatch.setattr("cli_modelarium.providers.anthropic_provider.AsyncAnthropic", _Client)
    return AnthropicProvider(api_key="sk-ant-NOT_A_REAL_KEY_test_fixture")


class TestDetection:
    async def test_a_refusal_is_detected_by_stop_reason_not_empty_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The opus-5 shape: content is non-empty and output_tokens is 4."""
        provider = _install_anthropic(monkeypatch, _opus5_shaped_refusal(), [])
        result = await provider.complete("p", "claude-opus-5", 0.0)

        assert result.refused is True
        assert result.stop_reason == "refusal"
        assert result.stop_category == "reasoning_extraction"
        # The evidence that an emptiness check would have been wrong.
        assert result.output_tokens == 4
        assert result.error is None, "a refusal is not a call failure"

    async def test_an_ordinary_answer_is_not_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        final = SimpleNamespace(
            stop_reason="end_turn",
            stop_details=None,
            content=[SimpleNamespace(type="text", text="ok")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=2, cache_read_input_tokens=0),
        )
        provider = _install_anthropic(monkeypatch, final, ["ok"])
        result = await provider.complete("p", "claude-opus-5", 0.0)

        assert result.refused is False
        assert result.stop_reason == "end_turn"
        assert result.stop_category is None
        assert result.output == "ok"

    async def test_an_empty_answer_that_is_not_a_refusal_stays_a_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty output alone must NOT be read as a refusal - the inverse error."""
        final = SimpleNamespace(
            stop_reason="end_turn",
            stop_details=None,
            content=[],
            usage=SimpleNamespace(input_tokens=10, output_tokens=0, cache_read_input_tokens=0),
        )
        provider = _install_anthropic(monkeypatch, final, [])
        result = await provider.complete("p", "claude-opus-5", 0.0)

        assert result.output == ""
        assert result.refused is False

    def test_stream_is_documented_as_refusal_blind(self) -> None:
        """complete() is the refusal-aware path; stream() cannot be.

        stream() returns AsyncIterator[str] and never calls
        get_final_message(), so a refusal there is zero chunks and no error.
        That is a deliberate limitation and the docstring has to say so, or a
        future caller will reach for it and silently lose refusals.
        """
        doc = AnthropicProvider.stream.__doc__ or ""
        assert "REFUSAL-BLIND" in doc
        assert "complete()" in doc

        complete_doc = AnthropicProvider.complete.__doc__ or ""
        assert AnthropicProvider.complete is not BaseProvider.complete, (
            "complete() must be overridden to read the final message"
        )
        assert complete_doc is not None


# ===== assertions =====


class TestAssertions:
    def test_all_ten_error_instead_of_four_passing(self) -> None:
        results = refused_results(ALL_TEN_ASSERTIONS)

        assert len(results) == 10
        assert all(r.error is not None for r in results), "every assertion must be errored"
        assert not any(r.passed for r in results)
        # Named explicitly: these are the four that would otherwise pass.
        errored_types = {r.type for r in results}
        for vacuous in VACUOUS_ON_EMPTY:
            assert vacuous in errored_types

    def test_pass_rate_is_undefined_not_one(self) -> None:
        """The whole point: no verdict, so no rate - not a perfect score."""
        totals = count_assertion_totals([refused_results(ALL_TEN_ASSERTIONS)])

        assert totals.pass_rate is None
        assert totals.definitive == 0
        assert totals.errored == 10
        assert totals.configured is True
        assert totals.nothing_verified is True

    def test_the_four_vacuous_types_really_do_pass_on_an_empty_string(self) -> None:
        """Pin the defect this guards, so the guard cannot be removed silently.

        If `run_assertions` ever stopped passing these against "", the
        erroring above would look like belt-and-braces instead of the fix.
        """
        from cli_modelarium.assertions import run_assertions

        results = run_assertions("", 10.0, 0.00098, ALL_TEN_ASSERTIONS)
        passing = {r.type for r in results if r.passed}
        assert passing == set(VACUOUS_ON_EMPTY)


# ===== statistics =====


def _state(text: str = "", *, refused: bool = False, error: str | None = None) -> StreamState:
    s = StreamState(model="claude-opus-5", provider_name="anthropic", temperature=0.0)
    s.text = text
    s.refused = refused
    s.error = error
    s.latency_ms = 100.0
    s.ttft_ms = 20.0
    s.cost_usd = 0.000355
    s.output_tokens = 4
    s.input_tokens = 51
    return s


class TestStatistics:
    def test_all_refused_does_not_read_as_perfect_consistency(self) -> None:
        """The inversion this fixes.

        Five refusals used to give five empty strings: one unique output,
        diversity 0.2, mode "" seen five times. A user reads low diversity and
        a stable mode and concludes the model is highly deterministic. It
        refused five times.
        """
        stats = compute_run_stats([_state(refused=True) for _ in range(5)])

        assert stats.n_refused == 5
        assert stats.n_succeeded == 0
        assert stats.n_failed == 0
        assert stats.output_diversity == 0.0
        assert stats.mode_output is None
        assert stats.mode_count == 0
        assert stats.unique_outputs == 0

    def test_timing_and_cost_survive_on_that_same_set(self) -> None:
        """The other half of the split: these were really measured and billed."""
        stats = compute_run_stats([_state(refused=True) for _ in range(5)])

        assert stats.latency_mean_ms == 100.0
        assert stats.ttft_mean_ms == 20.0
        assert stats.cost_total_usd == pytest.approx(0.000355 * 5)

    def test_a_refusal_does_not_dilute_a_mixed_run_set(self) -> None:
        states = [_state("answer"), _state("answer"), _state(refused=True)]
        stats = compute_run_stats(states)

        assert stats.n_succeeded == 2
        assert stats.n_refused == 1
        # Two identical answers: one unique output over two answered runs.
        assert stats.output_diversity == 0.5
        assert stats.mode_output == "answer"
        # But all three were billed.
        assert stats.cost_total_usd == pytest.approx(0.000355 * 3)

    def test_a_refusal_is_not_counted_as_a_failure(self) -> None:
        stats = compute_run_stats([_state(refused=True), _state("x"), _state(error="boom")])
        assert (stats.n_succeeded, stats.n_refused, stats.n_failed) == (1, 1, 1)


# ===== serialisation =====


def _refused_result() -> Any:
    state = _state(refused=True)
    state.stop_reason = "refusal"
    state.stop_category = "reasoning_extraction"
    return state_to_result(state, BatchPrompt(id="p1", prompt="q", assertions=[]))


class TestSerialisation:
    def test_csv_carries_stop_reason_and_category(self) -> None:
        text = _format_csv([_refused_result()])
        header, row = list(csv.reader(io.StringIO(text)))[:2]

        assert tuple(header) == CSV_COLUMNS
        assert len(header) == 23
        cells = dict(zip(header, row, strict=True))
        assert cells["stop_reason"] == "refusal"
        assert cells["stop_category"] == "reasoning_extraction"
        assert cells["output"] == ""
        assert cells["error"] == "", "a refusal is not an error"

    def test_json_carries_the_refusal_and_keeps_its_cost(self) -> None:
        payload = json.loads(_format_json([_refused_result()]))
        row = payload["results"][0]

        assert row["refused"] is True
        assert row["stop_reason"] == "refusal"
        assert row["stop_category"] == "reasoning_extraction"
        assert row["error"] is None
        # Not a failure, and the money still counts.
        assert payload["failed_results"] == 0
        assert payload["total_cost_usd"] == pytest.approx(0.000355)

    def test_an_ordinary_row_reports_no_refusal(self) -> None:
        row = json.loads(
            _format_json(
                [state_to_result(_state("hi"), BatchPrompt(id="p1", prompt="q", assertions=[]))]
            )
        )["results"][0]
        assert row["refused"] is False
        assert row["stop_reason"] is None
        assert row["stop_category"] is None


# ===== the CLI journey =====


class _RefusingProvider(BaseProvider):
    """Returns a refusal for every call: HTTP 200, real cost, no answer."""

    name = "fake"

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if False:  # pragma: no cover - never yields
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
        return CompletionResult(
            output="",
            input_tokens=51,
            output_tokens=4,
            cost_usd=0.000355,
            latency_ms=50.0,
            ttft_ms=10.0,
            model=model,
            provider=self.name,
            temperature=temperature,
            refused=True,
            stop_reason="refusal",
            stop_category="reasoning_extraction",
        )


@pytest.fixture
def refusing_provider(monkeypatch: pytest.MonkeyPatch) -> _RefusingProvider:
    fake = _RefusingProvider()
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: fake
    )
    return fake


class TestTheCiGateJourney:
    def test_a_ci_gate_no_longer_passes_on_a_refusal(
        self, refusing_provider: _RefusingProvider, tmp_path: Path
    ) -> None:
        """The headline: exit 0 at 100% becomes exit 1, nothing verified.

        These are exactly the four assertions that pass against an empty
        string - a plausible CI gate with no content assertion in it.
        """
        prompts = tmp_path / "p.json"
        prompts.write_text(
            json.dumps(
                [
                    {
                        "id": "gate",
                        "prompt": "q",
                        "assertions": [
                            {"type": "cost_under", "value": 1.0},
                            {"type": "latency_under", "value": 60000},
                            {"type": "not_contains", "value": "SECRET"},
                            {"type": "max_length_chars", "value": 100000},
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli_main, ["batch", str(prompts), "--models", "claude-opus-5"]
        )

        assert result.exit_code == 1, result.output
        assert "100.0%" not in result.output

    def test_the_refused_row_serialises_through_the_cli(
        self, refusing_provider: _RefusingProvider, tmp_path: Path
    ) -> None:
        prompts = tmp_path / "p.json"
        prompts.write_text(
            json.dumps([{"id": "r", "prompt": "q", "assertions": []}]), encoding="utf-8"
        )
        out = tmp_path / "out.json"

        result = CliRunner().invoke(
            cli_main,
            ["batch", str(prompts), "--models", "claude-opus-5", "--output", str(out)],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(out.read_text(encoding="utf-8"))
        row = payload["results"][0]
        assert row["refused"] is True
        assert row["stop_reason"] == "refusal"
        assert payload["failed_results"] == 0
        assert payload["total_cost_usd"] == pytest.approx(0.000355)


class TestConsoleTable:
    def test_the_compare_table_says_refused_and_still_shows_the_cost(
        self, refusing_provider: _RefusingProvider
    ) -> None:
        """A refused row must not read as `ok`, and must keep its price.

        The cost column is the point: showing `refused` while hiding what it
        cost would trade one silent failure for another.
        """
        result = CliRunner().invoke(
            cli_main, ["compare", "q", "--models", "claude-opus-5", "--no-stream"]
        )

        assert result.exit_code == 0, result.output
        assert "refused" in result.output
        assert "$0.000355" in result.output
        assert "Total cost: $0.000355" in result.output
