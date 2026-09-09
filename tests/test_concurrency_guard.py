"""`--concurrency 0` hung forever, and it was the only unguarded numeric flag.

    --concurrency  0   exit 124  TIMED OUT, no error, no diagnostic
    --concurrency -1   exit 1    ValueError: Semaphore initial value must be >= 0
    --concurrency  1   exit 2    proceeds normally

`asyncio.Semaphore(0)` is a valid semaphore that never admits anyone, so every
provider call waited on a permit that could not arrive. Nothing timed out and
nothing printed - the process simply stopped.

THE HANG NEEDS A KEY. With no key configured all three values exit 2 on the
key check, so a first run is unaffected; only someone who already configured a
key could reach it. No test here waits on anything.

`-1` exited 1, which is EXIT_ASSERTION_FAILED - a raw ValueError reported the
same code as a failing assertion.

NO UPPER BOUND. `asyncio.Semaphore` allocates nothing per slot: 5, 10_000 and
10_000_000 all cost about 300 bytes and a few microseconds, and a value above
the task count is a no-op. A ceiling would refuse a working configuration to
prevent nothing.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main

# Both commands take the flag; both must refuse the same values.
COMMANDS = [
    pytest.param(["q", "--models", "claude-opus-4-7"], id="compare"),
    pytest.param(["batch", "SUITE", "--models", "claude-opus-4-7"], id="batch"),
]


def _invoke(argv: list[str], suite: str, *flag: str):
    argv = [suite if a == "SUITE" else a for a in argv]
    return CliRunner().invoke(cli_main, [*argv, *flag])


@pytest.fixture
def suite(tmp_path) -> str:
    path = tmp_path / "suite.json"
    path.write_text('[{"id": "p1", "prompt": "hi"}]', encoding="utf-8")
    return str(path)


class TestRefusedValues:
    @pytest.mark.parametrize("argv", COMMANDS)
    @pytest.mark.parametrize("value", ["0", "-1", "-100"])
    def test_a_non_positive_value_is_refused(
        self, argv: list[str], value: str, suite: str
    ) -> None:
        result = _invoke(argv, suite, "--concurrency", value)
        assert result.exit_code == 2, result.output
        flat = " ".join(result.output.split())
        assert "--concurrency" in flat, flat
        # click's range message, not a traceback and not a hang.
        assert "Traceback" not in result.output
        assert "is not in the range" in flat, flat

    @pytest.mark.parametrize("argv", COMMANDS)
    def test_the_message_names_the_bound(self, argv: list[str], suite: str) -> None:
        flat = " ".join(_invoke(argv, suite, "--concurrency", "0").output.split())
        assert "x>=1" in flat or ">=1" in flat, flat


class TestAcceptedValues:
    """A legal value must still reach the run. These stop at the key check,
    which is as far as they need to go to prove the flag was accepted."""

    @pytest.mark.parametrize("argv", COMMANDS)
    @pytest.mark.parametrize("value", ["1", "5", "10000"])
    def test_a_positive_value_is_accepted(
        self, argv: list[str], value: str, suite: str
    ) -> None:
        result = _invoke(argv, suite, "--concurrency", value)
        flat = " ".join(result.output.split())
        assert "is not in the range" not in flat, flat
        # It got past parsing: the next gate is the missing API key.
        assert "No API key configured" in flat, flat

    @pytest.mark.parametrize("argv", COMMANDS)
    def test_omitting_the_flag_is_unchanged(self, argv: list[str], suite: str) -> None:
        flat = " ".join(_invoke(argv, suite).output.split())
        assert "No API key configured" in flat, flat


class TestNoUpperBound:
    """Pinned because a ceiling is the obvious thing to add and it would refuse
    a working configuration."""

    def test_a_very_large_value_is_accepted(self, suite: str) -> None:
        flat = " ".join(
            _invoke(COMMANDS[0].values[0], suite, "--concurrency", "10000000").output.split()
        )
        assert "is not in the range" not in flat, flat

    def test_a_semaphore_allocates_nothing_per_slot(self) -> None:
        import asyncio
        import tracemalloc

        async def measure(n: int) -> int:
            tracemalloc.start()
            asyncio.Semaphore(n)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return peak

        small = asyncio.run(measure(5))
        huge = asyncio.run(measure(10_000_000))
        assert huge < small * 4, (small, huge)


class TestTheDefaultIsShared:
    """`judging.py` carried its own hard-coded 5 rather than importing the
    constant, so the two defaults could drift apart silently."""

    def test_run_judging_defaults_to_the_shared_constant(self) -> None:
        import inspect

        from cli_modelarium.judging import run_judging
        from cli_modelarium.streaming import DEFAULT_CONCURRENCY

        default = inspect.signature(run_judging).parameters["concurrency"].default
        assert default == DEFAULT_CONCURRENCY

    def test_the_literal_is_gone(self) -> None:
        from pathlib import Path

        src = Path("src/cli_modelarium/judging.py").read_text(encoding="utf-8")
        assert "concurrency: int = 5" not in src
        assert "DEFAULT_CONCURRENCY" in src
