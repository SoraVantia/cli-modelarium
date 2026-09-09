"""A refusal must be visible on every surface that counts outcomes.

0.1.9 made a declined request its own state - billed, no answer, `error` left
None so its cost stays in every total. Four surfaces kept reporting outcomes as
a succeeded/failed pair, so a model that declined every run rendered as `0/0`
beside a genuine failure's `0/3`, with a real cost and no label:

    console --runs table    cli.py, n_succeeded/n_failed
    Markdown per-cell       output_formatters.py, the same pair
    Markdown report header  "- Results: 6 (0 failed)" on six results, three declined
    JSON top level          failed_results, from the same computation as the header

The count itself already existed - `RunStats.n_refused` is computed, tested and
published to JSON per cell. These pin that it now reaches the reader.
"""

from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from rich.console import Console

from cli_modelarium.cli import main as cli_main
from cli_modelarium.output_formatters import (
    BatchResult,
    _build_stats_by_cell,
    _format_json,
    _format_markdown,
)
from cli_modelarium.providers.base import CompletionResult, OnChunk

ANSWER = "Paris"


class _PartlyRefusingProvider:
    """Declines the first `refuse_first` runs of `model`, answers the rest."""

    name = "anthropic"

    def __init__(self, refuse_first: dict[str, int]) -> None:
        self.refuse_first = refuse_first
        self._seen: dict[str, int] = {}

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if False:  # pragma: no cover - never iterated; --no-stream is used
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
        **_kwargs: Any,
    ) -> CompletionResult:
        index = self._seen.get(model, 0)
        self._seen[model] = index + 1
        refused = index < self.refuse_first.get(model, 0)
        text = "" if refused else ANSWER
        if on_chunk is not None:
            on_chunk(text)
        return CompletionResult(
            output=text,
            input_tokens=51,
            output_tokens=0 if refused else 4,
            cost_usd=0.000725,
            latency_ms=100.0 + index,
            ttft_ms=10.0,
            model=model,
            provider=self.name,
            temperature=temperature,
            refused=refused,
            stop_reason="refusal" if refused else None,
            stop_category="reasoning_extraction" if refused else None,
        )


def _use(monkeypatch: pytest.MonkeyPatch, refuse_first: dict[str, int]) -> None:
    provider = _PartlyRefusingProvider(refuse_first)
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: provider
    )


def _compare(*args: str) -> Any:
    return CliRunner().invoke(cli_main, [*args, "--no-stream", "--no-confidence-intervals"])


def _flat(text: str) -> str:
    """Collapse Rich's wrapping so an assertion pins text, not the wrap column.

    Only safe for single-token assertions. A wrapped cell cannot be rejoined by
    flattening the whole table, because the continuation lines of the other
    columns are interleaved between its halves - so tests that need a phrase
    widen the terminal instead (see `_wide`).
    """
    return " ".join(text.replace("\u2502", " ").split())


def _wide(monkeypatch: pytest.MonkeyPatch, columns: int = 200) -> None:
    """Pin the terminal width. Rich reads COLUMNS when there is no TTY, so this
    decides where cells wrap rather than leaving it to the CI runner."""
    monkeypatch.setenv("COLUMNS", str(columns))


def _result(model: str, *, refused: bool, run_index: int) -> BatchResult:
    return BatchResult(
        prompt_id=f"p{run_index + 1}",
        prompt="q",
        system=None,
        model=model,
        temperature=0.0,
        latency_ms=100.0 + run_index,
        ttft_ms=10.0,
        input_tokens=51,
        output_tokens=0 if refused else 4,
        cached_tokens=0,
        cost_usd=0.000725,
        output="" if refused else ANSWER,
        error=None,
        retries=0,
        refused=refused,
        stop_reason="refusal" if refused else None,
        run_index=run_index,
    )


class TestConsoleRunsTable:
    def test_an_all_refused_cell_shows_the_refusals(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use(monkeypatch, {"claude-opus-5": 3})
        result = _compare("q", "--models", "claude-opus-5", "--runs", "3")
        assert result.exit_code == 0
        # Three declines out of three, not the "0/0" that read as nothing happening.
        assert "0/3/0" in _flat(result.output)

    def test_a_mixed_cell_sums_to_the_run_count_in_the_title(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use(monkeypatch, {"claude-opus-5": 3})
        result = _compare("q", "--models", "claude-opus-5", "--runs", "5")
        assert result.exit_code == 0
        flat = _flat(result.output)
        assert "5 runs each" in flat
        # 2 + 3 + 0 == 5. The old pair rendered "2/0" on a five-run cell.
        assert "2/3/0" in flat

    def test_an_ordinary_cell_is_unchanged_apart_from_the_new_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use(monkeypatch, {})
        result = _compare("q", "--models", "claude-opus-5", "--runs", "3")
        assert result.exit_code == 0
        assert "3/0/0" in _flat(result.output)

    def test_the_header_is_legible_at_eighty_columns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `OK/Ref/Fail` renders as "OK/Re…" at both 80 and 100 columns, which
        # hides that the cell has three fields. The compact form does not
        # truncate, and 80-no-TTY is what a CI log and a piped run get.
        _use(monkeypatch, {"claude-opus-5": 3})
        _wide(monkeypatch, 80)
        result = _compare("q", "--models", "claude-opus-5", "--runs", "3")
        assert result.exit_code == 0
        assert "OK/R/F" in result.output
        assert "OK/Re" not in result.output

    def test_the_mode_cell_says_no_output_when_nothing_was_produced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "no mode (all unique)" asserted every output was unique when there
        # were none.
        _use(monkeypatch, {"claude-opus-5": 3})
        _wide(monkeypatch)
        result = _compare("q", "--models", "claude-opus-5", "--runs", "3")
        flat = _flat(result.output)
        assert "no output" in flat
        assert "all unique" not in flat


class TestMarkdownPerCellTable:
    def _cells(self, refused: int, total: int) -> str:
        results = [
            _result("claude-opus-5", refused=i < refused, run_index=i)
            for i in range(total)
        ]
        return _format_markdown(results, runs=total)

    def test_an_all_refused_cell_shows_the_refusals(self) -> None:
        assert "| 0/3/0 " in self._cells(3, 3)

    def test_a_mixed_cell_sums_to_the_run_count(self) -> None:
        assert "| 2/3/0 " in self._cells(3, 5)

    def test_an_ordinary_cell_is_unchanged_apart_from_the_new_zero(self) -> None:
        assert "| 3/0/0 " in self._cells(0, 3)

    def test_the_header_carries_the_full_words(self) -> None:
        # A pipe table is not width-bound, so Markdown does not pay the
        # truncation cost the console does.
        out = self._cells(0, 3)
        assert "| OK/Ref/Fail |" in out
        assert "OK/R/F" not in out

    def test_the_mode_cell_says_no_output_when_nothing_was_produced(self) -> None:
        # Markdown's string differs from the console's - it was "(no mode)".
        out = self._cells(3, 3)
        assert "(no output)" in out


class TestMarkdownReportHeader:
    def test_it_no_longer_reports_only_failures(self) -> None:
        results = [
            _result("claude-opus-5", refused=i < 3, run_index=i) for i in range(6)
        ]
        out = _format_markdown(results, runs=6)
        # Was "- Results: 6 (0 failed)" on a run where three calls were declined.
        assert "- Results: 6 (0 failed, 3 refused)" in out

    def test_a_run_with_no_refusals_is_unchanged(self) -> None:
        results = [
            _result("claude-opus-5", refused=False, run_index=i) for i in range(3)
        ]
        out = _format_markdown(results, runs=3)
        assert "- Results: 3 (0 failed)" in out
        assert "refused" not in out


class TestJsonTopLevel:
    def test_refused_results_appears_when_non_zero(self) -> None:
        results = [
            _result("claude-opus-5", refused=i < 3, run_index=i) for i in range(6)
        ]
        payload = json.loads(_format_json(results, runs=6))
        assert payload["refused_results"] == 3
        # The pre-existing terms are untouched.
        assert payload["total_results"] == 6
        assert payload["failed_results"] == 0

    def test_it_reads_zero_on_a_run_with_no_refusals(self) -> None:
        # It was emitted only when non-zero, to keep a clean run's payload
        # byte-identical to v0.1.9 - a property 0.2.0 had already given up when
        # `total_runs` went unconditional. The gate defended nothing and cost a
        # consumer the ability to tell `0` from a tool that never counted
        # declines. Read the value.
        results = [
            _result("claude-opus-5", refused=False, run_index=i) for i in range(3)
        ]
        payload = json.loads(_format_json(results, runs=3))
        assert payload["refused_results"] == 0


class TestNoStatisticMoved:
    """The cell shows a count that already existed; nothing recomputes."""

    def test_latency_cv_and_diversity_are_untouched_on_a_mixed_cell(self) -> None:
        results = [
            _result("claude-opus-5", refused=i < 3, run_index=i) for i in range(5)
        ]
        cell = _build_stats_by_cell(results)[0]
        # Latency spans all five runs - a decline is a real, billed round trip,
        # which 0.1.9 settled deliberately. Diversity divides by the two that
        # answered. Both values are what they were before this change.
        assert cell["latency_mean_ms"] == pytest.approx(102.0)
        assert cell["n_succeeded"] == 2
        assert cell["n_refused"] == 3
        assert cell["n_failed"] == 0
        assert cell["output_diversity"] == pytest.approx(0.5)
        assert cell["cost_total_usd"] == pytest.approx(0.003625)


class TestRenderedWidthIsPinned:
    """A Console built in a test must pin its width, or the assertion becomes a
    test of where Rich chose to wrap on the CI runner."""

    def test_the_compact_header_fits_a_narrow_terminal(self) -> None:
        from rich.table import Table

        table = Table()
        table.add_column("Model")
        table.add_column("OK/R/F", justify="right")
        table.add_column("Latency mean ± stdev", justify="right")
        table.add_row("claude-opus-5", "0/3/0", "681 ± 89 ms")
        buffer = io.StringIO()
        Console(file=buffer, width=80, force_terminal=False).print(table)
        rendered = buffer.getvalue()
        assert "OK/R/F" in rendered
        assert "0/3/0" in rendered


class TestTheReportFileItself:
    def test_a_circulated_report_names_the_declines(self, tmp_path: Path) -> None:
        results = [
            _result("claude-opus-5", refused=i < 3, run_index=i) for i in range(6)
        ]
        path = tmp_path / "report.md"
        path.write_text(_format_markdown(results, runs=6), encoding="utf-8")
        text = path.read_text(encoding="utf-8")
        assert "3 refused" in text
        # One model at one temperature is one cell, so all six runs land in it.
        assert "| 3/3/0 " in text
