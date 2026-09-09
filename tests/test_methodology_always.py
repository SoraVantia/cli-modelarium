"""`total_runs` and `methodology` are emitted at every run count.

They used to appear only when `runs > 1`, which made `"total_runs" not in
payload` a working test for "this was a single run". It is not one now, and
that is the point: absence was indistinguishable from a version that never
emitted the key, and a consumer testing `total_runs` got a different answer
from one testing `stats_by_cell`, which is still runs-gated.

THE BUG WAS NEVER THE SEED. `bootstrap.enabled` echoed the request flag
resolved before any bootstrap ran, so it reported `true` in two situations
where no interval exists anywhere in the payload: a zero-variance cell, and a
cell whose every run failed. Both are reachable on a pristine tree with no
patch at all. `enabled` now means ATTEMPTED and a separate `produced_intervals`
carries the outcome, rather than flipping `enabled` and losing the record of
what was asked for.
"""

from __future__ import annotations

import json

from cli_modelarium.output_formatters import BatchResult, _format_json, _format_markdown


def _r(**kw) -> BatchResult:
    f = dict(
        prompt_id="p1", prompt="q", system=None, model="claude-opus-5",
        temperature=0.0, latency_ms=100.0, ttft_ms=1.0, input_tokens=10,
        output_tokens=20, cached_tokens=0, cost_usd=0.001, output="x",
        error=None, retries=0, provider="anthropic",
    )
    f.update(kw)
    return BatchResult(**f)


def _methodology(*, enabled: bool, produced: bool, n_runs: int = 1) -> dict:
    return {
        "tool_version": "0.1.9",
        "scipy_version": "1.17.1",
        "python_version": "3.11.15",
        "n_runs": n_runs,
        "bootstrap": {
            "enabled": enabled,
            "produced_intervals": produced,
            "method": "bca" if enabled else None,
            "n_resamples": 5000 if enabled else None,
            "ci_level": 0.95 if enabled else None,
            "seed": 42 if enabled else None,
        },
        "significance": {
            "enabled": False, "test": None, "correction": None, "threshold": None
        },
    }


class TestTotalRunsIsNoLongerAnAbsenceDetector:
    def test_it_is_present_and_reads_one_at_a_single_run(self) -> None:
        payload = json.loads(_format_json([_r()], runs=1))
        assert payload["total_runs"] == 1

    def test_the_runs_gated_keys_are_still_gated(self) -> None:
        """Which is exactly why presence is no longer a coherent test: one key
        answers "multi-run?" by value and the others still answer by presence.
        """
        payload = json.loads(_format_json([_r()], runs=1))
        assert "stats_by_cell" not in payload

    def test_it_still_reads_the_real_count_above_one(self) -> None:
        payload = json.loads(_format_json([_r(), _r(run_index=1)], runs=2))
        assert payload["total_runs"] == 2
        assert "stats_by_cell" in payload


class TestBootstrapEnabledReportsWhatWasAttempted:
    def test_a_bootstrap_that_produced_nothing_says_so(self) -> None:
        """The live defect: a zero-variance cell publishes a complete seeded
        BCa configuration beside a payload with no interval in it."""
        payload = json.loads(
            _format_json([_r()], runs=4, methodology=_methodology(
                enabled=True, produced=False, n_runs=4))
        )
        bs = payload["methodology"]["bootstrap"]
        assert bs["enabled"] is True
        assert bs["produced_intervals"] is False
        assert bs["seed"] == 42

    def test_the_markdown_report_does_not_advertise_intervals_it_lacks(self) -> None:
        md = _format_markdown(
            [_r()], runs=4, methodology=_methodology(enabled=True, produced=False, n_runs=4)
        )
        line = next(x for x in md.splitlines() if x.startswith("- Bootstrap:"))
        assert "attempted, no intervals produced" in line, line

    def test_a_bootstrap_that_worked_reads_clean(self) -> None:
        md = _format_markdown(
            [_r()], runs=4, methodology=_methodology(enabled=True, produced=True, n_runs=4)
        )
        line = next(x for x in md.splitlines() if x.startswith("- Bootstrap:"))
        assert "attempted, no intervals produced" not in line
        assert "seed=`42`" in line

    def test_nothing_attempted_reports_nothing(self) -> None:
        payload = json.loads(
            _format_json([_r()], runs=1, methodology=_methodology(enabled=False, produced=False))
        )
        bs = payload["methodology"]["bootstrap"]
        assert bs == {
            "enabled": False, "produced_intervals": False, "method": None,
            "n_resamples": None, "ci_level": None, "seed": None,
        }


class TestTheVersionGrainIsUniform:
    def test_python_is_recorded_at_patch_precision_like_scipy(self) -> None:
        """A split grain makes the record useless: it pinned the dependency
        more precisely than the interpreter running it."""
        import platform

        import cli_modelarium.cli as cli_module

        assert cli_module.platform.python_version() == platform.python_version()
        assert platform.python_version().count(".") == 2
