"""`--max-cost` now stops a run that overruns it, instead of only guessing first.

Before this, the ceiling was one pre-flight estimate at a flat 500 input / 500
output tokens per call, evaluated once and never consulted again. Measured, that
let a run estimated at $0.009 against a $0.010 cap actually spend $0.924 and
exit 0.

THE CAP STOPS FURTHER DISPATCH. IT DOES NOT PREVENT SPEND, and the design turns
on that. A cell already sent to the provider is finished rather than cancelled:
usage is read inside the provider's chunk loop, so cancelling loses the cost
entirely and the cell reports $0.00 for work that was really done. Letting it
finish keeps the reported total TRUE. The price is a bounded overshoot, pinned
below, and an honest number beats a tight one that lies.

JUDGE SPEND COUNTS. It is a second gather with its own per-provider semaphores,
so the ledger is shared across both rather than living on `StreamState` - which
judging never touches.
"""

from __future__ import annotations

import asyncio

import pytest

from cli_modelarium.streaming import CostLedger


class TestTheLedger:
    def test_no_ceiling_never_stops(self) -> None:
        ledger = CostLedger(None)
        ledger.add(1_000_000.0)
        assert ledger.exhausted is False

    def test_it_stops_once_the_ceiling_is_passed(self) -> None:
        """`>` not `>=`, matching the pre-flight's operator - so spending
        exactly the ceiling allows one more dispatch."""
        ledger = CostLedger(0.10)
        for _ in range(10):
            ledger.add(0.01)
        assert ledger.spent == pytest.approx(0.10)
        assert ledger.exhausted is False
        ledger.add(0.01)
        assert ledger.exhausted is True

    def test_it_reports_what_it_knows_was_spent(self) -> None:
        ledger = CostLedger(0.10)
        ledger.add(0.03)
        ledger.add(0.04)
        assert ledger.spent == pytest.approx(0.07)

    def test_a_zero_ceiling_admits_free_work(self) -> None:
        """`--max-cost 0` means "free models only" and 17 registry rows cost
        nothing. Adding 0.0 must not trip the ceiling."""
        ledger = CostLedger(0.0)
        ledger.add(0.0)
        ledger.add(0.0)
        assert ledger.exhausted is False

    def test_a_zero_ceiling_stops_the_first_paid_call(self) -> None:
        ledger = CostLedger(0.0)
        ledger.add(0.000001)
        assert ledger.exhausted is True

    def test_no_lock_is_used(self) -> None:
        """Single-threaded asyncio makes `+=` atomic - no await sits inside the
        statement - so a lock would be cargo. Measured at 20x10000 increments
        with an explicit yield between each: zero lost updates."""
        import inspect

        assert "Lock" not in inspect.getsource(CostLedger)

    def test_concurrent_adds_lose_nothing(self) -> None:
        ledger = CostLedger(None)

        async def add_many() -> None:
            for _ in range(2000):
                await asyncio.sleep(0)
                ledger.add(0.001)

        async def drive() -> None:
            await asyncio.gather(*[add_many() for _ in range(10)])

        asyncio.run(drive())
        assert ledger.spent == pytest.approx(20.0)


class TestTheOvershoot:
    """A cap whose overshoot is unmeasured is a cap nobody can reason about.

    Every call costs the same, so the numbers are exact: a $0.10 ceiling is
    crossed by the tenth call, and anything beyond that is overshoot.
    """

    @staticmethod
    async def _run(concurrency: int) -> tuple[int, float]:
        ledger = CostLedger(0.10)
        sem = asyncio.Semaphore(concurrency)
        dispatched = 0

        async def one() -> None:
            nonlocal dispatched
            async with sem:
                if ledger.exhausted:
                    return  # never dispatched
                dispatched += 1
                await asyncio.sleep(0.01)  # in flight; finished, not cancelled
                ledger.add(0.01)

        await asyncio.gather(*[one() for _ in range(60)])
        return dispatched, ledger.spent

    @pytest.mark.parametrize(
        "concurrency,max_dispatched",
        [(1, 11), (5, 15), (10, 20)],
    )
    def test_the_overshoot_is_bounded_by_concurrency(
        self, concurrency: int, max_dispatched: int
    ) -> None:
        dispatched, spent = asyncio.run(self._run(concurrency))
        assert dispatched >= 11, dispatched
        assert dispatched <= max_dispatched, (
            f"concurrency {concurrency}: dispatched {dispatched}, "
            f"expected at most {max_dispatched} (11 + concurrency - 1)"
        )
        # Everything dispatched reported its real cost, so the total is true.
        assert spent == pytest.approx(dispatched * 0.01)

    def test_serial_dispatch_overshoots_by_exactly_one_cell(self) -> None:
        dispatched, _ = asyncio.run(self._run(1))
        assert dispatched == 11

    def test_the_reported_total_matches_what_was_dispatched(self) -> None:
        """The property that makes the total honest: no dispatched cell is
        abandoned, so none contributes an unknown cost to the sum."""
        for c in (1, 5, 10):
            dispatched, spent = asyncio.run(self._run(c))
            assert spent == pytest.approx(dispatched * 0.01), c
