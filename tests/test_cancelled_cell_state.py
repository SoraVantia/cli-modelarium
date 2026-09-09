"""A cancelled cell must not read as a successful free call.

`state_to_result` discarded `StreamState.status` entirely, so a cell that never
finished produced a `BatchResult` identical to one that did:

    status='streaming'  ->  error=None  refused=False  cost=$0.000000  ->  'ok'
    status='retrying'   ->  error=None  refused=False  cost=$0.000000  ->  'ok'
    status='complete'   ->  error=None  refused=False  cost=$0.000000  ->  'ok'

`BatchResult` carried `error: str | None` and `refused: bool` and no third
channel, so every format reported a cancelled cell as an `ok` row costing
nothing - the same shape group 2 fixed for a refusal and group 4a for an errored
assertion. This adds the fourth state.

IT ALSO POISONED THE STATISTICS AND THE ASSERTIONS. `billed` is
`[s for s in states if s.error is None]` at three sites in `run_statistics`, and
a cancelled cell has `error=None`, so it counted as SUCCEEDED and dragged the
latency mean. And `run_assertions` was reached because the cell missed both the
`state.error` and the `state.refused` branches, so assertions were evaluated
against a truncated answer.

THE COST IS UNKNOWN, NOT ZERO. Usage is read inside `async for chunk in
response`; cancel there and `CompletionResult` never returns, so `mark_complete`
never runs and `cost_usd` keeps its `0.0` default. The provider did the work
regardless. Reporting `0.0` would make the run's total a lie, so a cancelled
cell reports its cost as unknown rather than as free.
"""

from __future__ import annotations

import json

import pytest

from cli_modelarium.batch import BatchPrompt
from cli_modelarium.output_formatters import (
    _build_stats_by_cell,
    _format_csv,
    _format_json,
    _format_markdown,
    state_to_result,
)
from cli_modelarium.run_statistics import compute_run_stats
from cli_modelarium.streaming import StreamState

PROMPT = BatchPrompt(id="p1", prompt="hi", system=None, assertions=[])


def _state(status: str, *, text: str = "partial", cost: float = 0.0,
           latency: float | None = 40.0) -> StreamState:
    s = StreamState(model="claude-opus-4-7", provider_name="anthropic", temperature=0.0)
    s.status = status
    s.text = text
    s.cost_usd = cost
    s.latency_ms = latency
    s.input_tokens, s.output_tokens = 10, 5
    return s


def _cancelled() -> StreamState:
    s = _state("streaming")
    s.mark_cancelled()
    return s


class TestTheStateExists:
    def test_mark_cancelled_sets_its_own_status(self) -> None:
        assert _cancelled().status == "cancelled"

    def test_a_cell_cancelled_during_retry_backoff_is_not_left_retrying(self) -> None:
        """The one real ambiguity: a cell cancelled while sleeping between
        retries kept status 'retrying' with a retry_message and nothing
        resolved it."""
        s = _state("retrying")
        s.retry_message = "rate limited, retry in 2.0s (attempt 1)"
        s.mark_cancelled()
        assert s.status == "cancelled"
        assert s.retry_message is None

    def test_it_does_not_invent_a_cost(self) -> None:
        assert _cancelled().cost_usd == 0.0
        assert _cancelled().cost_unknown is True

    def test_a_completed_cell_has_a_known_cost(self) -> None:
        assert _state("complete", cost=0.01).cost_unknown is False


class TestItSurvivesIntoBatchResult:
    def test_the_flag_is_carried(self) -> None:
        assert state_to_result(_cancelled(), PROMPT).cancelled is True

    def test_an_ordinary_row_is_not_flagged(self) -> None:
        assert state_to_result(_state("complete"), PROMPT).cancelled is False

    def test_it_is_not_an_error_and_not_a_refusal(self) -> None:
        """Kept distinct so the existing error and refusal handling is
        untouched - a cancelled cell is a fourth state, not a rebranded one."""
        r = state_to_result(_cancelled(), PROMPT)
        assert r.error is None
        assert r.refused is False


class TestAllFourFormats:
    def test_console_does_not_say_ok(
        self, monkeypatch: pytest.MonkeyPatch, capture_console
    ) -> None:
        """Through the renderer a user actually hits, not through a helper.

        This used to assert on `cli._status_text_for`, which had a `cancelled`
        branch and ZERO production callers. `_display_results` - the default
        `--runs 1` console path - read `StreamState` and branched only on
        `error` and `refused`, so it printed `ok` at `$0.000000` while this
        test passed. Poisoning the helper to raise left the table byte-identical
        and failed only this test, which is what proved it covered nothing.
        """
        import cli_modelarium.cli as cli_module

        monkeypatch.setattr(cli_module, "console", capture_console)
        cli_module._display_results([_state("complete", cost=0.05), _cancelled()])
        out = capture_console.file.getvalue()
        assert "cancelled" in out, out
        assert "$0.000000" not in out, out

    def test_markdown_does_not_say_ok(self) -> None:
        md = _format_markdown([state_to_result(_cancelled(), PROMPT)], runs=1)
        row = next(line for line in md.splitlines() if line.startswith("| `claude"))
        cells = [c.strip() for c in row.split("|")]
        assert "cancelled" in cells, row
        assert "ok" not in cells, row

    def test_markdown_shows_the_cost_as_unknown(self) -> None:
        md = _format_markdown([state_to_result(_cancelled(), PROMPT)], runs=1)
        row = next(line for line in md.splitlines() if line.startswith("| `claude"))
        assert "$0.000000" not in row, row

    def test_json_flags_it_and_nulls_the_cost(self) -> None:
        row = json.loads(_format_json([state_to_result(_cancelled(), PROMPT)]))["results"][0]
        assert row["cancelled"] is True
        assert row["cost_usd"] is None, row["cost_usd"]

    def test_json_is_unchanged_for_an_ordinary_row(self) -> None:
        row = json.loads(
            _format_json([state_to_result(_state("complete", cost=0.01), PROMPT)])
        )["results"][0]
        assert row["cancelled"] is False
        assert row["cost_usd"] == 0.01

    def test_csv_does_not_report_zero_cost(self) -> None:
        rows = _format_csv([state_to_result(_cancelled(), PROMPT)]).splitlines()
        header, row = rows[0].split(","), rows[1].split(",")
        cost = row[header.index("cost_usd")]
        assert cost != "0.0", rows[1]


class TestItIsExcludedFromTheStatistics:
    """Three cells completed; a fourth was cancelled."""

    def _mixed(self) -> list[StreamState]:
        good = [_state("complete", text="full", cost=0.01, latency=100.0) for _ in range(3)]
        return [*good, _cancelled()]

    def test_it_is_not_counted_as_succeeded(self) -> None:
        assert compute_run_stats(self._mixed()).n_succeeded == 3

    def test_it_does_not_drag_the_latency_mean(self) -> None:
        assert compute_run_stats(self._mixed()).latency_mean_ms == 100.0

    def test_it_adds_nothing_to_the_cost_total(self) -> None:
        assert compute_run_stats(self._mixed()).cost_total_usd == pytest.approx(0.03)

    def test_it_is_not_counted_as_refused_either(self) -> None:
        assert compute_run_stats(self._mixed()).n_refused == 0

    def test_a_clean_cell_set_is_unchanged(self) -> None:
        good = [_state("complete", text="full", cost=0.01, latency=100.0) for _ in range(3)]
        stats = compute_run_stats(good)
        assert (stats.n_succeeded, stats.latency_mean_ms) == (3, 100.0)


class TestAssertionsDoNotRunAgainstIt:
    def test_a_cancelled_state_takes_the_skip_branch(self) -> None:
        """Group 4a covered errored and refused; this is the fourth state, and
        its partial text must not be graded."""
        from pathlib import Path

        src = Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert "or state.status == \"cancelled\"" in src or "state.cancelled" in src


def _never_dispatched() -> StreamState:
    """A cancelled cell exactly as production builds one.

    `_cancelled()` above starts from `_state("streaming")`, which has already
    set a latency and a token count - useful for the flag-carrying tests, wrong
    for the statistics. In production `mark_cancelled` runs BEFORE
    `mark_started` (streaming.py) and returns, so the call never happened:
    `latency_ms` is None, the token counts are 0 and the text is empty. Using
    the optimistic helper here would overstate the damage and invite a "fix" to
    the latency filter, which is not broken.
    """
    s = StreamState(model="claude-opus-4-7", provider_name="anthropic", temperature=0.0)
    s.mark_cancelled()
    return s


def _completed(text: str = "real answer") -> StreamState:
    s = StreamState(model="claude-opus-4-7", provider_name="anthropic", temperature=0.0)
    s.status = "complete"
    s.text = text
    s.cost_usd = 0.05
    s.latency_ms = 100.0
    s.input_tokens, s.output_tokens = 10, 50
    return s


class TestBuildStatsByCellExcludesIt:
    """The FOURTH billed filter. Commit 89aa560 guarded three sites in
    run_statistics and missed this one, so `stats_by_cell` in JSON and the
    Markdown per-cell table counted a cancelled run as SUCCEEDED - while the
    same JSON document carried `"cancelled": true` on the row.
    """

    def _cell(self) -> list:
        rows = [state_to_result(_completed(), PROMPT) for _ in range(3)]
        rows.append(state_to_result(_never_dispatched(), PROMPT))
        return rows

    def test_it_is_not_counted_as_succeeded(self) -> None:
        cell = _build_stats_by_cell(self._cell())[0]
        assert cell["n_runs"] == 4
        assert cell["n_succeeded"] == 3, cell
        assert cell["n_cancelled"] == 1, cell

    def test_the_four_counts_add_up_to_the_run_count(self) -> None:
        cell = _build_stats_by_cell(self._cell())[0]
        total = (
            cell["n_succeeded"] + cell["n_refused"] + cell["n_failed"] + cell["n_cancelled"]
        )
        assert total == cell["n_runs"], cell

    def test_the_output_derived_numbers_are_not_dragged(self) -> None:
        """These are the ones that actually broke: a cancelled row contributes
        `output_tokens=0` and an empty `output` string."""
        cell = _build_stats_by_cell(self._cell())[0]
        assert cell["output_tokens_mean"] == 50, cell
        assert cell["unique_outputs"] == 1, cell
        assert cell["output_diversity"] == pytest.approx(1 / 3), cell

    def test_latency_and_cost_are_unchanged_and_must_stay_that_way(self) -> None:
        """PINNED SO NOBODY "FIXES" THEM.

        A cancelled row's `latency_ms` is None, which the existing None filter
        already drops, and its `cost_usd` is 0.0 joining a list that is only
        summed. Adding a cancelled guard to either line would be dead code that
        reads like a bug fix. If this test starts failing, the guard was added
        to the wrong line.
        """
        with_cancel = _build_stats_by_cell(self._cell())[0]
        clean = _build_stats_by_cell(self._cell()[:3])[0]
        assert with_cancel["latency_mean_ms"] == clean["latency_mean_ms"] == 100.0
        assert with_cancel["latency_cv"] == clean["latency_cv"]
        assert with_cancel["cost_total_usd"] == clean["cost_total_usd"]


class TestTheHeaderTotalsNameIt:
    """`failed_results` counts `r.error` and a cancelled row has none, so it sat
    inside `total_results` and outside every named term: "3 (0 failed)"."""

    def _rows(self) -> list:
        return [
            state_to_result(_completed(), PROMPT),
            state_to_result(_completed(), PROMPT),
            state_to_result(_never_dispatched(), PROMPT),
        ]

    def test_markdown_names_the_cancelled_count(self) -> None:
        md = _format_markdown(self._rows(), runs=1)
        line = next(line for line in md.splitlines() if line.startswith("- Results:"))
        assert "1 cancelled" in line, line

    def test_json_names_the_cancelled_count(self) -> None:
        payload = json.loads(_format_json(self._rows()))
        assert payload["total_results"] == 3
        assert payload["cancelled_results"] == 1, payload

    def test_a_clean_run_reports_zero_rather_than_nothing(self) -> None:
        """Always present, `0` when nothing was cancelled - matching `refused_results`.

        It used to be emitted only when non-zero, which made `0` and "a tool
        too old to count cancellations" the same observation. Markdown is
        unchanged: a report is prose for a reader, and a line saying
        "0 cancelled" on every clean run is noise rather than a contract.
        """
        payload = json.loads(_format_json([state_to_result(_completed(), PROMPT)]))
        assert payload["cancelled_results"] == 0
        md = _format_markdown([state_to_result(_completed(), PROMPT)], runs=1)
        assert "cancelled" not in md


class TestTheConsoleTripleAddsUp:
    def test_ok_r_f_c_sums_to_the_run_count_in_the_title(
        self, monkeypatch: pytest.MonkeyPatch, capture_console
    ) -> None:
        """It read "2/0/0" under a title saying "3 runs each" - the same defect
        group 2 fixed for refusals, one state later."""
        import cli_modelarium.cli as cli_module

        monkeypatch.setattr(cli_module, "console", capture_console)
        cli_module._display_results_with_runs(
            [_completed(), _completed(), _never_dispatched()], None, runs=3
        )
        out = capture_console.file.getvalue()
        assert "3 runs each" in out, out
        assert "OK/R/F/C" in out, out
        assert "2/0/0/1" in out, out

    def test_a_run_with_no_cancellations_keeps_the_three_slot_header(
        self, monkeypatch: pytest.MonkeyPatch, capture_console
    ) -> None:
        import cli_modelarium.cli as cli_module

        monkeypatch.setattr(cli_module, "console", capture_console)
        cli_module._display_results_with_runs([_completed(), _completed()], None, runs=2)
        out = capture_console.file.getvalue()
        assert "OK/R/F" in out
        assert "OK/R/F/C" not in out, out
