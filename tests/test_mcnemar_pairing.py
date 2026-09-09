"""McNemar must pair runs on the whole observation, not on run_index alone.

`compute_mcnemar_pairwise` built its outcome map as `{run_index: pass_bool}`.
With more than one temperature or system prompt, run_index repeats in every cell,
so later cells overwrote earlier ones and every cell but the last was discarded.
The collision 0.1.8 fixed for the paired metric extractor was never fixed here.

It is not a lost-power bug - it publishes a WRONG pass rate, and the direction is
set by dict iteration order:

    two models, temperatures 0.0 and 0.7, five runs each, A hallucinating at 0.7 only
      cells iterated (0.0, 0.7)   a_pass_rate = 0%     truth 50%
      cells iterated (0.7, 0.0)   a_pass_rate = 100%   truth 50%

Ten runs per model went in; the 2x2 table totalled five.

Three further defects fall out of the same function and are fixed here: a pair
with no overlapping runs published a real-looking p=1.0 over an empty table; the
`p_value is None` branch guarding that was unreachable because `mcnemar_test`
returns the None in its chi2 slot, never its p slot; and untestable pairs spent
the multiple-comparison budget, which for McNemar means pairs with no paired runs,
NOT pairs with a None p-value.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

import cli_modelarium.cli as cli_module
from cli_modelarium.output_formatters import (
    _markdown_mcnemar_section,
    mcnemar_pairing_caveat,
)
from cli_modelarium.run_statistics import compute_mcnemar_pairwise, mcnemar_test
from cli_modelarium.streaming import StreamState

A, B = "gpt-5.5", "claude-opus-4-7"


def _state(
    model: str, *, temperature: float, run: int, system: str | None = None
) -> StreamState:
    state = StreamState(model=model, provider_name="anthropic", temperature=temperature)
    state.latency_ms = 100.0 + run
    state.output_tokens = 40
    state.cost_usd = 0.000725
    state.error = None
    state.refused = False
    state.run_index = run
    state.system_prompt = system
    state.text = "x"
    return state


def _verdict(risk: str) -> Any:
    return SimpleNamespace(judges=[object()], aggregated_risk_level=risk)


def _sweep(
    cell_order: tuple[float, ...], runs: int = 5
) -> tuple[dict[str, list[StreamState]], dict[int, Any]]:
    """A hallucinates at 0.7 and not at 0.0, so its true pass rate is 50%."""
    a_states: list[StreamState] = []
    b_states: list[StreamState] = []
    judges: dict[int, Any] = {}
    for temperature in cell_order:
        for run in range(runs):
            sa = _state(A, temperature=temperature, run=run)
            sb = _state(B, temperature=temperature, run=run)
            a_states.append(sa)
            b_states.append(sb)
            judges[id(sa)] = _verdict("High" if temperature == 0.7 else "Low")
            judges[id(sb)] = _verdict("Low")
    return {A: a_states, B: b_states}, judges


def _only(results: list[Any]) -> Any:
    assert len(results) == 1, results
    return results[0]


class TestEveryCellIsPaired:
    @pytest.mark.parametrize("order", [(0.0, 0.7), (0.7, 0.0)])
    def test_all_twenty_observations_reach_the_table(
        self, order: tuple[float, ...]
    ) -> None:
        r = _only(compute_mcnemar_pairwise(*_sweep(order)))
        total = r.both_pass + r.a_pass_b_fail + r.a_fail_b_pass + r.both_fail
        # Ten runs per model, so ten paired observations. It was five.
        assert r.n_paired == 10
        assert total == 10

    @pytest.mark.parametrize("order", [(0.0, 0.7), (0.7, 0.0)])
    def test_the_pass_rate_matches_the_evidence_in_both_orders(
        self, order: tuple[float, ...]
    ) -> None:
        r = _only(compute_mcnemar_pairwise(*_sweep(order)))
        # A passed the five runs at 0.0 and failed the five at 0.7.
        assert r.a_pass_rate == pytest.approx(0.5)
        assert r.b_pass_rate == pytest.approx(1.0)

    def test_the_two_orders_now_agree(self) -> None:
        first = _only(compute_mcnemar_pairwise(*_sweep((0.0, 0.7))))
        second = _only(compute_mcnemar_pairwise(*_sweep((0.7, 0.0))))
        assert first.a_pass_rate == second.a_pass_rate
        assert first.n_paired == second.n_paired
        assert first.p_value == second.p_value

    def test_system_prompts_separate_observations_too(self) -> None:
        # The key is the whole observation, so a system-prompt sweep is paired
        # the same way a temperature sweep is.
        a_states, b_states, judges = [], [], {}
        for system in ("be terse", "be verbose"):
            for run in range(4):
                sa = _state(A, temperature=0.0, run=run, system=system)
                sb = _state(B, temperature=0.0, run=run, system=system)
                a_states.append(sa)
                b_states.append(sb)
                judges[id(sa)] = _verdict("Low")
                judges[id(sb)] = _verdict("Low")
        r = _only(compute_mcnemar_pairwise({A: a_states, B: b_states}, judges))
        assert r.n_paired == 8

    def test_a_single_cell_is_unchanged(self) -> None:
        # One temperature, one system prompt: run_index alone was already a
        # complete key, so nothing about this case may move.
        r = _only(compute_mcnemar_pairwise(*_sweep((0.0,))))
        assert r.n_paired == 5
        assert r.a_pass_rate == pytest.approx(1.0)


class TestZeroPairedRuns:
    """Two models sharing no observation published p=1.0 over an empty table -
    the same shape a genuinely tested pair takes."""

    @staticmethod
    def _disjoint() -> tuple[dict[str, list[StreamState]], dict[int, Any]]:
        a_states = [_state(A, temperature=0.0, run=i) for i in range(3)]
        b_states = [_state(B, temperature=0.0, run=i) for i in range(5, 8)]
        judges = {id(s): _verdict("Low") for s in a_states + b_states}
        return {A: a_states, B: b_states}, judges

    def test_it_publishes_no_p_value(self) -> None:
        r = _only(compute_mcnemar_pairwise(*self._disjoint()))
        assert r.n_paired == 0
        assert r.p_value is None
        assert r.p_value_corrected is None
        assert r.significant_at_threshold is False

    def test_it_carries_its_own_method_value(self) -> None:
        # "no_discordant" conflates "ten runs, all agreed" with "zero runs
        # compared"; those need telling apart.
        r = _only(compute_mcnemar_pairwise(*self._disjoint()))
        assert r.method == "no_paired_runs"

    def test_the_pass_rates_are_not_rendered_as_zero(self) -> None:
        r = _only(compute_mcnemar_pairwise(*self._disjoint()))
        assert r.a_pass_rate is None
        assert r.b_pass_rate is None

    def test_a_pair_that_agreed_on_every_run_is_told_apart(self) -> None:
        r = _only(compute_mcnemar_pairwise(*_sweep((0.0,))))
        assert r.n_paired == 5
        assert r.n_discordant == 0
        assert r.method == "no_discordant"
        assert r.p_value == 1.0  # a real result: five paired runs, no disagreement


class TestTheBudgetMatchesTheOtherBlock:
    """`n_comparisons` must mean the same thing in both JSON blocks: pairs that
    were tested. For McNemar an untestable pair is one with NO PAIRED RUNS -
    filtering on a None p-value removes nothing, because mcnemar_test never
    returns one."""

    def test_mcnemar_test_never_returns_a_none_p_value(self) -> None:
        # 1600 combinations; the None in `return None, 1.0` is the chi2 slot.
        assert all(
            mcnemar_test(b, c)[1] is not None for b in range(40) for c in range(40)
        )

    def test_a_zero_paired_pair_does_not_spend_the_budget(self) -> None:
        a_states = [_state(A, temperature=0.0, run=i) for i in range(5)]
        b_states = [_state(B, temperature=0.0, run=i) for i in range(5)]
        c_states = [_state("grok-4", temperature=0.0, run=i) for i in range(9, 14)]
        judges: dict[int, Any] = {}
        for i, s in enumerate(a_states):
            judges[id(s)] = _verdict("High" if i < 3 else "Low")
        for s in b_states:
            judges[id(s)] = _verdict("Low")
        for s in c_states:
            judges[id(s)] = _verdict("Low")
        results = compute_mcnemar_pairwise(
            {A: a_states, B: b_states, "grok-4": c_states}, judges
        )
        assert len(results) == 3
        # Only A/B shares any run; the two grok-4 pairs are untestable.
        assert all(r.n_comparisons == 1 for r in results)
        assert all(r.n_pairs_untestable == 2 for r in results)
        tested = [r for r in results if r.n_paired > 0]
        assert len(tested) == 1
        assert tested[0].p_value_corrected == pytest.approx(tested[0].p_value)


class TestTheFieldContractsAreTrue:
    """Three field comments described contracts the producer never satisfied, and
    the first orphaned a branch that could not fire."""

    def test_chi2_is_none_for_the_exact_test_and_set_for_the_chi_square(self) -> None:
        assert mcnemar_test(3, 1)[0] is None  # exact binomial, n_discordant < 25
        assert mcnemar_test(20, 20)[0] is not None  # Edwards chi-square

    def test_the_method_value_set_is_what_the_comment_lists(self) -> None:
        # The comment listed two of the four values it can take.
        from pathlib import Path

        source = Path("src/cli_modelarium/run_statistics.py").read_text(encoding="utf-8")
        block = source[source.index("class McNemarResult") :]
        block = block[: block.index("\ndef ")]
        for value in ("exact_binomial", "edwards_chi2", "no_discordant", "no_paired_runs"):
            assert f'"{value}"' in block, f"{value} missing from the method comment"

    def test_every_method_value_the_producer_emits_is_documented(self) -> None:
        # The contract read the other way: nothing is emitted that the comment
        # does not list.
        from pathlib import Path

        source = Path("src/cli_modelarium/run_statistics.py").read_text(encoding="utf-8")
        body = source[source.index("def compute_mcnemar_pairwise") :]
        body = body[: body.index("\ndef ", 10)]
        emitted = {
            v
            for v in ("exact_binomial", "edwards_chi2", "no_discordant", "no_paired_runs")
            if f'"{v}"' in body
        }
        assert emitted == {
            "exact_binomial", "edwards_chi2", "no_discordant", "no_paired_runs",
        }


class TestTheCaveat:
    """Group 2's significance caveat says a decline stays in the samples the test
    consumes. McNemar drops declines before the table is built, so that sentence
    would state the opposite here."""

    def test_it_says_the_paired_set_shrank(self) -> None:
        text = mcnemar_pairing_caveat([(A, 3)])
        assert "shrink" in text or "shrank" in text
        assert "stays in" not in text

    def test_it_names_the_model_and_the_count(self) -> None:
        text = mcnemar_pairing_caveat([(A, 3)])
        assert A in text
        assert "3" in text

    def test_a_model_id_carrying_markup_is_escaped(self) -> None:
        # A model id is user-supplied: openrouter and local ids are freeform, and
        # _display_mcnemar interpolates into a Rich markup string.
        buffer = io.StringIO()
        console = Console(file=buffer, width=100, force_terminal=False)
        console.print(cli_module._mcnemar_caveat_markup([("local/model[/]", 2)]))
        assert "local/model[/]" in buffer.getvalue()

    def test_it_stays_quiet_when_nothing_declined(self) -> None:
        assert mcnemar_pairing_caveat([]) == ""


class TestTheSurfacesCarryNPaired:
    @staticmethod
    def _results() -> list[Any]:
        return compute_mcnemar_pairwise(*_sweep((0.0, 0.7)))

    def test_the_markdown_table_has_a_paired_column(self) -> None:
        section = "\n".join(_markdown_mcnemar_section(self._results()))
        assert "| Paired |" in section
        assert "| 10 |" in section

    def test_the_json_carries_it(self) -> None:
        from cli_modelarium.output_formatters import _format_json

        # _format_json takes BatchResults; the McNemar block is threaded in
        # separately, so exercise the dict the block is built from.
        payload = json.loads(
            _format_json([], runs=5, mcnemar_results=self._results())
        )
        row = payload["mcnemar_tests"][0]
        assert row["n_paired"] == 10
        assert row["n_comparisons"] == 1
        assert row["n_pairs_untestable"] == 0

    def test_a_zero_paired_row_renders_without_a_fake_rate(self) -> None:
        a_states = [_state(A, temperature=0.0, run=i) for i in range(3)]
        b_states = [_state(B, temperature=0.0, run=i) for i in range(5, 8)]
        judges = {id(s): _verdict("Low") for s in a_states + b_states}
        section = "\n".join(
            _markdown_mcnemar_section(
                compute_mcnemar_pairwise({A: a_states, B: b_states}, judges)
            )
        )
        assert "no_paired_runs" in section
        assert "0%" not in section


class TestRenderedWidthIsPinned:
    def test_the_caveat_wraps_rather_than_truncating(self) -> None:
        buffer = io.StringIO()
        Console(file=buffer, width=80, force_terminal=False).print(
            mcnemar_pairing_caveat([(A, 2)])
        )
        rendered = " ".join(buffer.getvalue().split())
        assert A in rendered
        assert rendered.endswith("compared.")
