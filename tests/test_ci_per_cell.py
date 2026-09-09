"""A confidence interval must describe the sample it is printed beside.

`compute_stats_with_cis` grouped by model while the per-cell record groups by
(model, temperature, system), so one pooled interval was stamped onto every one
of that model's cells. On a two-temperature run the published 95% interval
contained neither mean it labelled:

     temp  cell mean      CI attached to that cell   contains mean?
      0.0     202.0   [     401.7,     1002.1]   NO
      0.7    1202.0   [     401.7,     1002.1]   NO

The suite could not see it: every CLI-level CI test used a single temperature
and no system prompts, and the one test pinning the brackets-the-mean invariant
(tests/test_bootstrap_ci.py) runs on the dataclass, before `_flatten_cell_cis`
reattaches it to the wrong record. These close that hole.

The pooled interval was wide because it was wrong - its width was the spread
BETWEEN cells, not sampling error - so the correct per-cell intervals are much
narrower, not wider.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner
from rich.console import Console

import cli_modelarium.cli as cli_module
from cli_modelarium.cli import main as cli_main
from cli_modelarium.output_formatters import _markdown_ci_section
from cli_modelarium.providers.base import CompletionResult, OnChunk
from cli_modelarium.run_statistics import compute_stats_with_cis
from cli_modelarium.streaming import StreamState

# Cell A answers in ~200ms, cell B in ~1200ms. Pooled, that spread dominates
# any interval; per cell, each is tight.
FAST, SLOW = 200.0, 1200.0


class _CellVaryingProvider:
    """Latency depends on the CELL, so the cells genuinely differ.

    Token counts vary run to run as a real model's do, which keeps the token
    and cost samples non-degenerate - see TestDeterministicRunsLoseIntervals
    for the opposite case.
    """

    name = "anthropic"

    def __init__(self, base: Any) -> None:
        self.base = base
        self._seen: dict[Any, int] = {}

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
        key = (model, temperature, system_prompt)
        index = self._seen.get(key, 0)
        self._seen[key] = index + 1
        tokens = 40 + (index % 5)
        if on_chunk is not None:
            on_chunk("Paris " * (index % 3 + 1))
        return CompletionResult(
            output="Paris " * (index % 3 + 1),
            input_tokens=51,
            output_tokens=tokens,
            cost_usd=tokens * 3e-6,
            latency_ms=self.base(model, temperature, system_prompt) + index * 2.0,
            ttft_ms=10.0,
            model=model,
            provider=self.name,
            temperature=temperature,
        )


class _DeterministicProvider(_CellVaryingProvider):
    """Every run of a cell returns the identical answer, so tokens and cost are
    constant within the cell - what a model at temperature 0 actually does."""

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
        key = (model, temperature, system_prompt)
        index = self._seen.get(key, 0)
        self._seen[key] = index + 1
        # Tokens and cost depend on the cell, never on the run.
        tokens = 40 if temperature == 0.0 else 60
        if on_chunk is not None:
            on_chunk("Paris")
        return CompletionResult(
            output="Paris",
            input_tokens=51,
            output_tokens=tokens,
            cost_usd=tokens * 3e-6,
            latency_ms=self.base(model, temperature, system_prompt) + index * 2.0,
            ttft_ms=10.0,
            model=model,
            provider=self.name,
            temperature=temperature,
        )


def _use(monkeypatch: pytest.MonkeyPatch, provider: Any) -> None:
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: provider
    )


def _run_json(*args: str) -> dict:
    path = os.path.join(tempfile.mkdtemp(), "r.json")
    result = CliRunner().invoke(
        cli_main, [*args, "--bootstrap-seed", "42", "--no-stream", "--output", path]
    )
    assert result.exit_code == 0, result.output
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _by_temperature(payload: dict) -> Any:
    """Two temperatures give two cells."""
    return {c["temperature"]: c for c in payload["stats_by_cell"]}


class TestEachCellGetsItsOwnInterval:
    def test_a_temperature_sweep_brackets_each_cell_mean(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use(monkeypatch, _CellVaryingProvider(lambda m, t, s: FAST if t == 0.0 else SLOW))
        payload = _run_json(
            "q", "--models", "gpt-5.5", "--temperatures", "0,0.7", "--runs", "5"
        )
        cells = _by_temperature(payload)
        assert len(cells) == 2
        for cell in cells.values():
            mean = cell["latency_mean_ms"]
            low = cell["latency_ms_ci_low"]
            high = cell["latency_ms_ci_high"]
            # Before the fix both cells carried [401.7, 1002.1], which contains
            # neither 202.0 nor 1202.0.
            assert low <= mean <= high, f"{low} <= {mean} <= {high}"

    def test_a_system_prompt_run_brackets_each_cell_mean(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The cell key has three parts; a system-prompt sweep is the other
        # trigger and was never covered.
        _use(
            monkeypatch,
            _CellVaryingProvider(
                lambda m, t, s: FAST if (s or "").startswith("terse") else SLOW
            ),
        )
        payload = _run_json(
            "q", "--models", "gpt-5.5", "--system-prompts", "terse,verbose", "--runs", "5"
        )
        cells = {c["system"]: c for c in payload["stats_by_cell"]}
        assert len(cells) == 2
        for cell in cells.values():
            mean = cell["latency_mean_ms"]
            assert cell["latency_ms_ci_low"] <= mean <= cell["latency_ms_ci_high"]

    def test_the_two_cells_get_different_intervals(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The sharpest statement of the defect: one interval for two samples.
        _use(monkeypatch, _CellVaryingProvider(lambda m, t, s: FAST if t == 0.0 else SLOW))
        cells = _by_temperature(
            _run_json("q", "--models", "gpt-5.5", "--temperatures", "0,0.7", "--runs", "5")
        )
        assert cells[0.0]["latency_ms_ci_low"] != cells[0.7]["latency_ms_ci_low"]

    def test_per_cell_intervals_are_narrower_than_the_pooled_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The pooled width WAS the between-cell spread, so removing it collapses
        # the interval. Pinned so nobody "restores" the wide one.
        _use(monkeypatch, _CellVaryingProvider(lambda m, t, s: FAST if t == 0.0 else SLOW))
        cells = _by_temperature(
            _run_json("q", "--models", "gpt-5.5", "--temperatures", "0,0.7", "--runs", "5")
        )
        for cell in cells.values():
            width = cell["latency_ms_ci_high"] - cell["latency_ms_ci_low"]
            assert width < (SLOW - FAST) / 2, f"width {width} looks pooled"


class TestCsvCellsArePopulated:
    """The regression this fix nearly shipped.

    Rekeying the dict without updating the CSV lookup leaves every CI cell an
    empty string while the header survives - and the only CSV CI assertions in
    the suite check the header, so nothing would have caught it.
    """

    def _csv_rows(self, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[list[str]]]:
        import csv

        _use(monkeypatch, _CellVaryingProvider(lambda m, t, s: FAST if t == 0.0 else SLOW))
        path = os.path.join(tempfile.mkdtemp(), "r.csv")
        result = CliRunner().invoke(
            cli_main,
            ["q", "--models", "gpt-5.5", "--temperatures", "0,0.7", "--runs", "5",
             "--bootstrap-seed", "42", "--no-stream", "--output", path],
        )
        assert result.exit_code == 0, result.output
        with open(path, encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        return rows[0], rows[1:]

    def test_every_ci_cell_carries_a_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        header, rows = self._csv_rows(monkeypatch)
        ci_columns = [i for i, name in enumerate(header) if name.endswith(("_ci_low", "_ci_high"))]
        assert ci_columns, "no CI columns in the CSV header"
        populated = sum(1 for row in rows for i in ci_columns if row[i] != "")
        total = len(rows) * len(ci_columns)
        assert populated == total, f"{populated} of {total} CI cells populated"

    def test_rows_from_different_cells_carry_different_intervals(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        header, rows = self._csv_rows(monkeypatch)
        low = header.index("latency_ms_ci_low")
        temp = header.index("temperature")
        by_temp = {row[temp]: row[low] for row in rows}
        assert len(set(by_temp.values())) == 2, by_temp


class TestDeterministicRunsLoseIntervals:
    """The categorical cost of the fix, pinned so nobody 'fixes' it back.

    When a metric is constant within a cell, the per-cell bootstrap is
    degenerate. Pooled it produced an interval - but that interval's width was
    the difference BETWEEN the cells, which is not sampling error and not a
    confidence interval on a mean.

    Degenerate shows up two ways, both measured here at --runs 3, 5 and 10:
    the interval is dropped, or it survives as zero-width (BCa's jackknife
    acceleration is 0/0 on constant data, and whether the result lands finite
    is floating-point luck). Neither is informative, which is the point. The
    zero-width case is left as-is deliberately - suppressing it is a change to
    what the bootstrap reports, not to which sample it is reported against.
    """

    @staticmethod
    def _informative(cell: dict, prefix: str) -> bool:
        low, high = cell.get(f"{prefix}_ci_low"), cell.get(f"{prefix}_ci_high")
        return low is not None and high is not None and high > low

    def test_token_and_cost_intervals_stop_being_informative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use(monkeypatch, _DeterministicProvider(lambda m, t, s: FAST if t == 0.0 else SLOW))
        cells = _by_temperature(
            _run_json("q", "--models", "gpt-5.5", "--temperatures", "0,0.7", "--runs", "5")
        )
        assert len(cells) == 2
        for cell in cells.values():
            # Latency still varies run to run, so it keeps a real interval.
            assert self._informative(cell, "latency_ms")
            assert not self._informative(cell, "output_tokens")
            assert not self._informative(cell, "cost_usd")

    def test_it_is_not_a_sample_size_effect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The guard is n < 2. Raising --runs does not bring these back, which is
        # how you tell degeneracy from too few samples.
        for runs in ("3", "10"):
            _use(
                monkeypatch,
                _DeterministicProvider(lambda m, t, s: FAST if t == 0.0 else SLOW),
            )
            cells = _by_temperature(
                _run_json("q", "--models", "gpt-5.5", "--temperatures", "0,0.7", "--runs", runs)
            )
            for cell in cells.values():
                assert not self._informative(cell, "cost_usd"), f"--runs {runs}"
                assert not self._informative(cell, "output_tokens"), f"--runs {runs}"
                assert self._informative(cell, "latency_ms"), f"--runs {runs}"


class TestModeOnlyJudgingLosesTheScoreInterval:
    """The second categorical cost, and the clearest case of the old defect.

    Under mode-only judging one verdict is broadcast across a whole cell, so a
    cell contributes exactly ONE score observation. Pooled across two cells that
    made n=2, and the resulting "95% CI on the mean score" was built from the two
    cells' verdicts - its width was the gap between the cells, which is the thing
    a reader is comparing, not the uncertainty in either. Per cell there is one
    observation and the bootstrap correctly declines.
    """

    @staticmethod
    def _states(temperatures: tuple[float, ...], runs: int = 5) -> list[StreamState]:
        out = []
        for temperature in temperatures:
            for index in range(runs):
                state = StreamState(
                    model="gpt-5.5", provider_name="anthropic", temperature=temperature
                )
                state.latency_ms = 200.0 + temperature * 1000 + index * 2
                state.output_tokens = 40 + index
                state.cost_usd = (40 + index) * 3e-6
                state.error = None
                state.refused = False
                state.run_index = index
                state.system_prompt = None
                out.append(state)
        return out

    def test_a_broadcast_verdict_yields_no_score_interval(self) -> None:
        states = self._states((0.0, 0.7))
        # One verdict per cell, tagged onto that cell's first run.
        judge_results = [
            SimpleNamespace(average_score=7.0 + k / 5, _state_id=id(states[k]), _broadcast=True)
            for k in range(0, len(states), 5)
        ]
        cis = compute_stats_with_cis(
            {"gpt-5.5": states}, judge_results, seed=42, n_resamples=500
        )
        assert len(cis) == 2
        for metrics in cis.values():
            assert metrics["score"] is None

    def test_per_run_judging_still_gets_one_interval_per_cell(self) -> None:
        # The contrast: five verdicts per cell is five observations per cell, and
        # each cell keeps a real interval.
        states = self._states((0.0, 0.7))
        judge_results = [
            SimpleNamespace(average_score=7.0 + (i % 3), _state_id=id(s), _broadcast=False)
            for i, s in enumerate(states)
        ]
        cis = compute_stats_with_cis(
            {"gpt-5.5": states}, judge_results, seed=42, n_resamples=500
        )
        assert len(cis) == 2
        for metrics in cis.values():
            ci = metrics["score"]
            assert ci is not None
            assert ci.n_samples == 5


class TestSingleCellIsUnchanged:
    """The majority case. One cell means per-cell and per-model are the same
    grouping, so nothing may move."""

    def test_a_single_cell_still_gets_its_interval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use(monkeypatch, _CellVaryingProvider(lambda m, t, s: FAST))
        payload = _run_json("q", "--models", "gpt-5.5", "--runs", "5")
        cell = payload["stats_by_cell"][0]
        mean = cell["latency_mean_ms"]
        assert cell["latency_ms_ci_low"] <= mean <= cell["latency_ms_ci_high"]


class TestCellLabelsAreRendered:
    """A per-cell interval needs a per-cell label, or two rows read as
    duplicates of one model."""

    def _cis(self, monkeypatch: pytest.MonkeyPatch) -> dict:
        from cli_modelarium.run_statistics import compute_stats_with_cis
        from cli_modelarium.streaming import StreamState

        states = []
        for temp, base in ((0.0, FAST), (0.7, SLOW)):
            for i in range(5):
                state = StreamState(
                    model="gpt-5.5", provider_name="anthropic", temperature=temp
                )
                state.latency_ms = base + i * 2.0
                state.refused = False
                state.error = None
                state.text = "Paris"
                state.output_tokens = 40 + i
                state.cost_usd = (40 + i) * 3e-6
                states.append(state)
        return cli_module._flatten_cell_cis(
            compute_stats_with_cis({"gpt-5.5": states}, None, seed=42, n_resamples=2000)
        )

    def test_markdown_distinguishes_the_two_cells(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        section = "\n".join(_markdown_ci_section(self._cis(monkeypatch)))
        assert "0.0" in section and "0.7" in section
        # And it must not print a raw tuple.
        assert "('gpt-5.5'" not in section

    def test_the_console_distinguishes_the_two_cells(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        monkeypatch.setattr(cli_module, "console", capture_console)
        cli_module._display_confidence_intervals(self._cis(monkeypatch))
        rendered = capture_console.file.getvalue()  # type: ignore[attr-defined]
        assert "0.0" in rendered and "0.7" in rendered
        assert "('gpt-5.5'" not in rendered


class TestRenderedWidthIsPinned:
    def test_the_ci_line_fits_a_pinned_console(self) -> None:
        buffer = io.StringIO()
        Console(file=buffer, width=100, force_terminal=False).print(
            "gpt-5.5 @ 0.0: latency [95% CI: 201.600, 206.400]"
        )
        assert "gpt-5.5 @ 0.0" in buffer.getvalue()
