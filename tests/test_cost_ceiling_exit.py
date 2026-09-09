"""A cost abort gets its own exit code, and the partial run is still published.

WHY A FOURTH CODE, when the README's row for 2 already reads "The run could not
complete."? Because every other route to 2 - a usage error, a missing key, an
unknown model, the pre-flight refusal - has one thing in common: NOTHING RAN AND
NOTHING WAS SPENT, and the remedy is to fix the command. A cost abort is the
opposite: the run partly succeeded, money was spent, and a real artifact exists
on disk. The remedy is to accept the partial data or raise the ceiling. A CI job
routing exit 2 to "the author typed something wrong" would misroute it.

THE PARTIAL RUN PUBLISHES. The user paid for the completed cells; discarding
them wastes it. That is safe only because a cancelled cell is now excluded from
every statistic and from the assertions, so the file carries what was measured
and says which cells never ran.

TWO ARMS, NOT ONE. `CostLimitExceededError` is a direct `ModelariumError`, and
both commands already end their run block with `except ModelariumError ->
sys.exit(EXIT_CALL_FAILED)`. Exiting 3 from compare alone would leave batch
silently exiting 2 on the same condition.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import EXIT_COST_CEILING
from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import CompletionResult

PER_CALL = 0.05


class _Costly:
    name = "anthropic"

    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, *a, **k):  # pragma: no cover - --no-stream is used
        yield "hi"

    async def complete(self, prompt, model, temperature, system_prompt=None,
                       *, on_chunk=None, **k):
        self.calls += 1
        if on_chunk:
            on_chunk("hi")
        return CompletionResult(
            output="hi", input_tokens=5, output_tokens=2, cost_usd=PER_CALL,
            latency_ms=10.0, ttft_ms=1.0, model=model, provider="anthropic",
            temperature=temperature,
        )


@pytest.fixture
def costly(monkeypatch: pytest.MonkeyPatch) -> _Costly:
    provider = _Costly()
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_k: provider
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 95)
    monkeypatch.setenv("COLUMNS", "200")
    return provider


@pytest.fixture
def suite(tmp_path) -> str:
    path = tmp_path / "s.json"
    path.write_text('[{"id": "p1", "prompt": "hi"}]', encoding="utf-8")
    return str(path)


class TestTheCodeIsNew:
    def test_it_is_three(self) -> None:
        assert EXIT_COST_CEILING == 3

    def test_the_other_codes_are_unmoved(self) -> None:
        from cli_modelarium.cli import (
            EXIT_ASSERTION_FAILED,
            EXIT_CALL_FAILED,
            EXIT_OK,
        )

        assert (EXIT_OK, EXIT_ASSERTION_FAILED, EXIT_CALL_FAILED) == (0, 1, 2)


class TestCompare:
    def test_it_exits_three(self, costly: _Costly) -> None:
        result = CliRunner().invoke(
            cli_main,
            ["hi", "--models", "claude-opus-4-7", "--runs", "10", "--no-stream",
             "--max-cost", "0.20", "--concurrency", "1"],
        )
        assert result.exit_code == EXIT_COST_CEILING, result.output

    def test_the_message_does_not_claim_to_prevent_spend(self, costly: _Costly) -> None:
        out = " ".join(
            CliRunner().invoke(
                cli_main,
                ["hi", "--models", "claude-opus-4-7", "--runs", "10", "--no-stream",
                 "--max-cost", "0.20", "--concurrency", "1"],
            ).output.split()
        )
        assert "Stopped dispatching" in out, out
        assert "prevent" not in out.lower(), out

    def test_a_run_under_its_ceiling_still_exits_zero(self, costly: _Costly) -> None:
        result = CliRunner().invoke(
            cli_main,
            ["hi", "--models", "claude-opus-4-7", "--runs", "2", "--no-stream",
             "--max-cost", "50.0"],
        )
        assert result.exit_code == 0, result.output


class TestBatchGetsTheSameCode:
    """The arm that would have been missed."""

    def test_it_exits_three_too(self, costly: _Costly, suite: str) -> None:
        result = CliRunner().invoke(
            cli_main,
            ["batch", suite, "--models", "claude-opus-4-7,gpt-5.5,claude-opus-5",
             "--max-cost", "0.05", "--concurrency", "1"],
        )
        assert result.exit_code == EXIT_COST_CEILING, result.output

    def test_a_batch_under_its_ceiling_is_unchanged(
        self, costly: _Costly, suite: str
    ) -> None:
        result = CliRunner().invoke(
            cli_main, ["batch", suite, "--models", "claude-opus-4-7", "--max-cost", "50.0"]
        )
        assert result.exit_code == 0, result.output


class TestThePartialRunIsPublished:
    def test_the_file_exists_and_parses(self, costly: _Costly, tmp_path) -> None:
        out = tmp_path / "r.json"
        result = CliRunner().invoke(
            cli_main,
            ["hi", "--models", "claude-opus-4-7", "--runs", "10", "--no-stream",
             "--max-cost", "0.20", "--concurrency", "1", "--output", str(out)],
        )
        assert result.exit_code == EXIT_COST_CEILING, result.output
        assert out.exists(), "the user paid for the completed cells and got no file"
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["results"], payload

    def test_it_marks_which_cells_never_ran(self, costly: _Costly, tmp_path) -> None:
        out = tmp_path / "r.json"
        CliRunner().invoke(
            cli_main,
            ["hi", "--models", "claude-opus-4-7", "--runs", "10", "--no-stream",
             "--max-cost", "0.20", "--concurrency", "1", "--output", str(out)],
        )
        rows = json.loads(out.read_text(encoding="utf-8"))["results"]
        cancelled = [r for r in rows if r["cancelled"]]
        completed = [r for r in rows if not r["cancelled"]]
        assert cancelled, "no cell was marked cancelled"
        assert completed, "no cell completed"
        assert all(r["cost_usd"] is None for r in cancelled)
        assert all(r["cost_usd"] == PER_CALL for r in completed)


class TestTheDocsMatch:
    """Group 4a corrected this table once already; adding a code makes it wrong
    again in nine files, plus a prose bullet in each."""

    def test_every_readme_documents_the_new_code(self) -> None:
        from pathlib import Path

        missing = [
            p.name
            for p in sorted(Path(".").glob("README*.md"))
            if "| `3` |" not in p.read_text(encoding="utf-8")
        ]
        assert not missing, missing

    def test_no_readme_still_advertises_only_three_codes(self) -> None:
        """`0/1/2/3` contains `0/1/2`, so the check has to be for the stale form
        specifically rather than for the substring."""
        import re
        from pathlib import Path

        stale = [
            p.name
            for p in sorted(Path(".").glob("README*.md"))
            if re.search(r"0/1/2(?!/3)", p.read_text(encoding="utf-8"))
        ]
        assert not stale, stale


# ===== SIGINT gets its own code too, for the opposite reason =====


class TestInterruptExitCode:
    """Ctrl-C exits 130, and deliberately publishes nothing.

    Exit 1 is EXIT_ASSERTION_FAILED, so before this a run killed by a CI timeout
    reported the code meaning "an assertion did not pass" - a false verdict about
    the thing the tool exists to measure. 128 + 2 is the POSIX convention.

    THE PARTIAL RUN IS NOT PUBLISHED, which is the opposite of the cost-ceiling
    decision above, and the asymmetry is deliberate. The ceiling stops BETWEEN
    cells and lets every in-flight call finish, so the states it writes are
    complete and their costs are known. SIGINT lands wherever it lands, including
    mid-stream - and usage is read inside the provider's chunk loop, so an
    interrupted cell has no usage and `mark_error` leaves `cost_usd` at 0.0.
    Publishing that would under-report real spend, which is the exact failure the
    truncated-run design exists to prevent.
    """

    def _interrupt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import cli_modelarium.cli as cli_module

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli_module.asyncio, "run", _boom)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-NOT_A_REAL_KEY_test_fixture_0")

    def test_compare_exits_130_and_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        from cli_modelarium.cli import EXIT_INTERRUPTED

        self._interrupt(monkeypatch)
        out = tmp_path / "r.json"  # type: ignore[operator]
        result = CliRunner().invoke(
            cli_main,
            ["hi", "--models", "claude-haiku-4-5", "--no-stream",
             "--output", str(out), "--force"],
        )
        assert result.exit_code == EXIT_INTERRUPTED == 130, result.output
        assert not out.exists()  # type: ignore[attr-defined]
        assert "Interrupted" in result.output

    def test_batch_exits_130_too(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        """Both commands, for the same reason the cost ceiling needed two arms."""
        from cli_modelarium.cli import EXIT_INTERRUPTED

        self._interrupt(monkeypatch)
        suite = tmp_path / "s.json"  # type: ignore[operator]
        suite.write_text(  # type: ignore[attr-defined]
            json.dumps([{"id": "p1", "prompt": "hi"}]), encoding="utf-8"
        )
        result = CliRunner().invoke(
            cli_main,
            ["batch", str(suite), "--models", "claude-haiku-4-5"],
        )
        assert result.exit_code == EXIT_INTERRUPTED, result.output
        assert "Interrupted" in result.output
