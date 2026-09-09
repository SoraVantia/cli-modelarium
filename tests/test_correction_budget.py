"""The multiple-comparison budget must be spent only on hypotheses that were tested.

`n_comparisons` was `len(pairs)` - every pair - and an untestable pair appended a
placeholder 1.0 to the vector both corrections consume. So a pair that produced no
statistic still inflated Bonferroni's multiplier and occupied a rank slot in Holm's
step-down, and every testable pair's published p-value paid for it:

    three models, one model too small to test
      BEFORE  gpt-5.5 / claude-opus-4-7  p=0.036168  p_corr=0.108504  n=3  not significant
      AFTER                              p=0.036168  p_corr=0.036168  n=1  SIGNIFICANT

Every published p-value moves whenever any pair is untestable - all of them, not some.
One under-powered model kills (n-1) pairs, so the effect is not rare.

THE PREDICATE IS THE WHOLE FIX. "Untestable" names three states and only two of them
qualify:

    n < 3                    insufficient_samples  p_value None    not tested
    constant, means differ   zero_variance         p_value None    not tested
    constant, means EQUAL    trivial               p_value 1.0     TESTED, keep it

Filtering on a `test_used` allowlist, or on the raw value being 1.0, evicts `trivial`
and flips a verdict on a run where nothing was untestable at all - and both wrong
readings pass the whole suite, because nothing else here mixes the two kinds of pair.
`TestATrivialPairChangesNothing` is that missing guard.

The predicate also demands `math.isfinite`: `paired_t_test` on identical aligned
samples returns NaN, `sorted()` cannot order a NaN, and a NaN in the vector both
publishes itself as significant and lets a filtered vector reverse-flip a real
verdict from significant to null. See `TestANaNPairIsNotATest`.
"""

from __future__ import annotations

import io
import json
import math
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from rich.console import Console

import cli_modelarium.cli as cli_module
from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import CompletionResult, OnChunk
from cli_modelarium.run_statistics import compute_pairwise_significance
from cli_modelarium.streaming import StreamState

CORRECTIONS = ["bonferroni", "holm"]


def _state(
    model: str,
    *,
    tokens: float,
    run: int,
    temperature: float = 0.0,
    latency: float | None = None,
) -> StreamState:
    state = StreamState(model=model, provider_name="anthropic", temperature=temperature)
    state.latency_ms = 1000.0 + run if latency is None else latency
    state.output_tokens = int(tokens)
    state.cost_usd = 0.000725
    state.error = None
    state.refused = False
    state.run_index = run
    state.system_prompt = None
    state.text = "x" * max(int(tokens), 1)
    return state


def _by_model(plan: dict[str, list[float]], **kwargs: Any) -> dict[str, list[StreamState]]:
    return {
        model: [_state(model, tokens=t, run=i, **kwargs) for i, t in enumerate(values)]
        for model, values in plan.items()
    }


def _significance(
    plan: dict[str, list[float]], correction: str, *, test: str = "welch"
) -> list[Any]:
    return compute_pairwise_significance(
        _by_model(plan),
        None,
        metric="output_tokens",
        test=test,
        correction=correction,
        threshold=0.05,
    )


def _pair(results: list[Any], a: str, b: str) -> Any:
    for r in results:
        if {r.model_a, r.model_b} == {a, b}:
            return r
    raise AssertionError(f"no {a}/{b} pair in {[(x.model_a, x.model_b) for x in results]}")


# A and B differ modestly; C answered twice, so both of C's pairs are untestable.
A_B_C = {
    "gpt-5.5": [120, 131, 124, 138, 127],
    "claude-opus-4-7": [130, 141, 134, 148, 143],
    "claude-fable-5-1": [150, 151],
}


class TestTheBudgetIsSpentOnlyOnTestedPairs:
    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_the_verdict_flips_to_significant(self, correction: str) -> None:
        r = _pair(_significance(A_B_C, correction), "gpt-5.5", "claude-opus-4-7")
        assert r.p_value == pytest.approx(0.036168, abs=1e-6)
        # Was 0.108504 over a budget of three, one of which was never tested.
        assert r.p_value_corrected == pytest.approx(0.036168, abs=1e-6)
        assert r.significant_at_threshold is True
        assert r.n_comparisons == 1

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_it_matches_the_same_two_models_run_alone(self, correction: str) -> None:
        # The point of the fix: a third model nobody could test must not change the
        # verdict on the two that could.
        pair_only = {k: v for k, v in A_B_C.items() if k != "claude-fable-5-1"}
        alone = _pair(_significance(pair_only, correction), "gpt-5.5", "claude-opus-4-7")
        with_third = _pair(_significance(A_B_C, correction), "gpt-5.5", "claude-opus-4-7")
        assert with_third.p_value_corrected == pytest.approx(alone.p_value_corrected)
        assert with_third.n_comparisons == alone.n_comparisons == 1

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_the_untestable_pairs_publish_no_corrected_value(self, correction: str) -> None:
        for r in _significance(A_B_C, correction):
            if r.p_value is None:
                assert r.test_used == "insufficient_samples"
                assert r.p_value_corrected is None
                assert r.significant_at_threshold is False

    def test_n_pairs_untestable_counts_them(self) -> None:
        for r in _significance(A_B_C, "holm"):
            assert r.n_pairs_untestable == 2
            assert r.n_comparisons == 1

    def test_a_clean_run_is_untouched(self) -> None:
        clean = {k: v for k, v in A_B_C.items()}
        clean["claude-fable-5-1"] = [150, 163, 157, 171, 160]
        results = _significance(clean, "bonferroni")
        assert all(r.n_comparisons == 3 for r in results)
        assert all(r.n_pairs_untestable == 0 for r in results)
        # Bonferroni over three, as before.
        r = _pair(results, "gpt-5.5", "claude-opus-4-7")
        assert r.p_value_corrected == pytest.approx(min(1.0, r.p_value * 3))


class TestATrivialPairChangesNothing:
    """The guard the suite lacked. `trivial` is a REAL result - two constant, equal
    samples genuinely do not differ, and p=1.0 is the answer, not a placeholder. It
    spends the budget like any other tested hypothesis. Both wrong predicates evict
    it and flip a verdict on a run where nothing was untestable."""

    # A vs B differ; C is constant and equal to nothing else, but A/C and B/C are
    # only `trivial` when BOTH sides are constant and equal - so make C equal to a
    # constant D. Simplest faithful shape: two constant-and-equal models plus a pair
    # that genuinely differs.
    PLAN = {
        "gpt-5.5": [120, 131, 124, 138, 127],
        "claude-opus-4-7": [130, 141, 134, 148, 143],
        "const-a": [90] * 5,
        "const-b": [90] * 5,
    }

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_the_trivial_pair_is_a_tested_hypothesis(self, correction: str) -> None:
        r = _pair(_significance(self.PLAN, correction), "const-a", "const-b")
        assert r.test_used == "trivial"
        assert r.p_value == 1.0
        # It was tested, so it is corrected and counted.
        assert r.p_value_corrected is not None
        assert r.n_pairs_untestable == 0

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_nothing_moves_when_no_pair_is_untestable(self, correction: str) -> None:
        results = _significance(self.PLAN, correction)
        # Six pairs, every one of them tested. A predicate that evicted `trivial`
        # would report 5 here and shrink every other pair's correction.
        assert all(r.n_comparisons == 6 for r in results)
        assert all(r.n_pairs_untestable == 0 for r in results)

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_the_ordinary_pair_keeps_its_full_budget(self, correction: str) -> None:
        r = _pair(_significance(self.PLAN, correction), "gpt-5.5", "claude-opus-4-7")
        assert r.n_comparisons == 6
        if correction == "bonferroni":
            assert r.p_value_corrected == pytest.approx(min(1.0, r.p_value * 6))


class TestZeroVarianceIsNotATest:
    """Constant data with DIFFERENT means. The difference is certain in the sample
    and the test is still undefined - there is no sampling distribution to draw a
    p-value from. It leaves the budget, and the reasoning is recorded in the code."""

    PLAN = {
        "gpt-5.5": [120, 131, 124, 138, 127],
        "claude-opus-4-7": [130, 141, 134, 148, 143],
        "const-low": [40] * 5,
        "const-high": [90] * 5,
    }

    def test_it_publishes_no_p_value_and_leaves_the_budget(self) -> None:
        results = _significance(self.PLAN, "holm")
        r = _pair(results, "const-low", "const-high")
        assert r.test_used == "zero_variance"
        assert r.p_value is None
        assert r.p_value_corrected is None
        assert r.n_pairs_untestable == 1
        assert all(x.n_comparisons == 5 for x in results)


class TestANaNPairIsNotATest:
    """`paired_t_test` on identical aligned samples returns NaN. A NaN is not a
    p-value: `sorted()` cannot order it, so its rank in Holm's step-down is an
    artifact of list length, and a filtered vector could reverse-flip a real verdict
    from significant to null. The predicate demands `math.isfinite`."""

    IDENTICAL = {
        "gpt-5.5": [40, 41, 42, 43, 44],
        "claude-opus-4-7": [40, 41, 42, 43, 44],
        "claude-sonnet-5": [80, 82, 84, 86, 88],
    }

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_the_nan_pair_is_not_published_as_significant(self, correction: str) -> None:
        r = _pair(
            _significance(self.IDENTICAL, correction, test="paired-t"),
            "gpt-5.5",
            "claude-opus-4-7",
        )
        assert r.p_value is not None and math.isnan(r.p_value)
        # It used to receive a corrected value of 0.003 and a True verdict.
        assert r.p_value_corrected is None
        assert r.significant_at_threshold is False

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_a_nan_never_enters_the_budget(self, correction: str) -> None:
        results = _significance(self.IDENTICAL, correction, test="paired-t")
        finite = [
            r for r in results if r.p_value is not None and math.isfinite(r.p_value)
        ]
        assert all(r.n_comparisons == len(finite) for r in results)
        assert all(r.n_pairs_untestable == 3 - len(finite) for r in results)

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_the_other_pairs_are_corrected_over_the_finite_ones_only(
        self, correction: str
    ) -> None:
        results = _significance(self.IDENTICAL, correction, test="paired-t")
        for r in results:
            if r.p_value is not None and math.isfinite(r.p_value):
                assert r.p_value_corrected is not None
                assert math.isfinite(r.p_value_corrected)


class TestEveryPairUntestable:
    """No p-value may become 0.0, and the block must still render. `bonferroni_correct`
    returns zeros when handed n=0 with a non-empty vector - filtering makes that
    unreachable, because the count and the vector are derived from the same list."""

    PLAN = {"a": [1, 2], "b": [3, 4], "c": [5, 6]}

    @pytest.mark.parametrize("correction", CORRECTIONS)
    def test_no_corrected_value_is_fabricated(self, correction: str) -> None:
        results = _significance(self.PLAN, correction)
        assert len(results) == 3
        for r in results:
            assert r.p_value is None
            assert r.p_value_corrected is None
            assert r.significant_at_threshold is False
            assert r.n_comparisons == 0
            assert r.n_pairs_untestable == 3


class TestHolmIsCorrectedNotRelabelled:
    """Holm takes no divisor - it reads len(p_values) - so the fix has to change the
    vector it receives, not a number beside it."""

    def test_holm_differs_from_bonferroni_on_the_same_filtered_vector(self) -> None:
        plan = {
            "a": [40, 41, 42, 43, 44],
            "b": [60, 61, 62, 63, 64],
            "c": [61, 63, 62, 65, 64],
            "d": [200, 201],
        }
        bonf = _significance(plan, "bonferroni")
        holm = _significance(plan, "holm")
        assert all(r.n_comparisons == 3 for r in bonf + holm)
        pairs = [("a", "b"), ("a", "c"), ("b", "c")]
        b_vals = [_pair(bonf, x, y).p_value_corrected for x, y in pairs]
        h_vals = [_pair(holm, x, y).p_value_corrected for x, y in pairs]
        # Holm is uniformly no more conservative, and strictly less somewhere -
        # which is only true if it actually ran over the filtered vector.
        assert all(h <= b + 1e-12 for h, b in zip(h_vals, b_vals, strict=True))
        assert any(h < b - 1e-12 for h, b in zip(h_vals, b_vals, strict=True))


# ===== the CLI surfaces =====


class _PlanProvider:
    """Serves a scripted token count per model, in call order."""

    name = "openai"

    def __init__(self, plan: dict[str, list[int]]) -> None:
        self.plan = plan
        self._seen: dict[str, int] = {}

    async def stream(
        self, prompt: str, model: str, temperature: float, system_prompt: str | None = None
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
        tokens = self.plan[model][index]
        refused = tokens == 0
        text = "" if refused else "x" * tokens
        if on_chunk is not None:
            on_chunk(text)
        return CompletionResult(
            output=text,
            input_tokens=51,
            output_tokens=0 if refused else tokens,
            cost_usd=0.000725,
            latency_ms=100.0 + index,
            ttft_ms=10.0,
            model=model,
            provider=self.name,
            temperature=temperature,
            refused=refused,
            stop_reason="refusal" if refused else None,
        )


# gpt-4.1-mini answers twice then declines, so its pairs are untestable on tokens.
CLI_PLAN = {
    "gpt-5.4": [120, 131, 124, 138, 127],
    "gpt-4o": [130, 141, 134, 148, 143],
    "gpt-4.1-mini": [150, 151, 0, 0, 0],
}


def _run_cli(monkeypatch: pytest.MonkeyPatch, out: Path, *extra: str) -> Any:
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance",
        lambda name, **_kwargs: _PlanProvider(CLI_PLAN),
    )
    return CliRunner().invoke(
        cli_main,
        [
            "q", "--models", ",".join(CLI_PLAN), "--runs", "5", "--no-stream",
            "--significance-metric", "output_tokens", "--bootstrap-seed", "42",
            "--output", str(out), *extra,
        ],
    )


class TestTheSignificanceBlockSurvivesFiltering:
    """The naive filter - shorten the vector, leave the strict zip - raises a
    ValueError that cli.py catches, so the whole significance block silently
    disappears from the saved report at exit 0. It must still be there."""

    def test_the_json_still_carries_every_pair(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.json"
        result = _run_cli(monkeypatch, out, "--correction", "bonferroni")
        assert result.exit_code == 0, result.output
        assert "Significance test skipped" not in result.output
        payload = json.loads(out.read_text(encoding="utf-8"))
        rows = payload["significance_tests"]
        assert len(rows) == 3
        assert all(r["n_comparisons"] == 1 for r in rows)
        assert all(r["n_pairs_untestable"] == 2 for r in rows)

    def test_the_console_says_how_many_could_not_be_tested(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No --output: writing a machine payload to a file moves the human
        # console to stderr, which CliRunner does not fold into `.output`.
        monkeypatch.setattr(
            "cli_modelarium.cli._get_provider_instance",
            lambda name, **_kwargs: _PlanProvider(CLI_PLAN),
        )
        result = CliRunner().invoke(
            cli_main,
            ["q", "--models", ",".join(CLI_PLAN), "--runs", "5", "--no-stream",
             "--significance-metric", "output_tokens", "--bootstrap-seed", "42",
             "--correction", "holm"],
        )
        assert result.exit_code == 0, result.output
        flat = " ".join(result.output.split())
        assert "2 of 3 model pairs could not be tested" in flat
        assert "over the 1 that was" in flat

    def test_a_clean_run_says_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            "cli_modelarium.cli._get_provider_instance",
            lambda name, **_kwargs: _PlanProvider(
                {**CLI_PLAN, "gpt-4.1-mini": [150, 163, 157, 171, 160]}
            ),
        )
        result = CliRunner().invoke(
            cli_main,
            ["q", "--models", ",".join(CLI_PLAN), "--runs", "5", "--no-stream",
             "--significance-metric", "output_tokens", "--bootstrap-seed", "42"],
        )
        assert result.exit_code == 0, result.output
        assert "could not be tested" not in result.output


class TestTheNewFieldIsReadThroughGetattr:
    """`tests/test_display_gaps.py` and `tests/test_significance_refusal_caveat.py`
    drive the renderers with stubs carrying 20 of the dataclass's fields. Every read
    of a field added after them uses a default, as group 2 established."""

    class _StubWithoutTheNewField:
        model_a = "gpt-5.5"
        model_b = "claude-opus-4-7"
        metric = "latency_ms"
        test_used = "welch_t_test"
        correction_method = "bonferroni"
        threshold = 0.05
        p_value = 0.04
        p_value_corrected = 0.04
        significant_at_threshold = True
        mean_a = 1.0
        mean_b = 2.0
        effect_size = 0.5
        effect_size_interpretation = "medium"
        n_a = 5
        n_b = 5
        stdev_a = 0.1
        stdev_b = 0.1
        test_statistic = 1.0
        degrees_of_freedom = 8.0
        n_comparisons = 1

    def test_the_console_tolerates_a_stub(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        monkeypatch.setattr(cli_module, "console", capture_console)
        cli_module._display_significance([self._StubWithoutTheNewField()])
        rendered = capture_console.file.getvalue()  # type: ignore[attr-defined]
        assert "could not be tested" not in rendered

    def test_the_markdown_section_tolerates_a_stub(self) -> None:
        # `_significance_result_to_dict` reads the v0.1.3 bootstrap fields
        # directly and never took a stub, so the JSON path is not one of the
        # surfaces this applies to. These two are.
        from cli_modelarium.output_formatters import (
            _markdown_significance_section,
            refused_arms,
        )

        section = "\n".join(
            _markdown_significance_section([self._StubWithoutTheNewField()])
        )
        assert "could not be tested" not in section
        assert refused_arms([self._StubWithoutTheNewField()]) == []


class TestRenderedWidthIsPinned:
    """A Console built in a test must pin its width, or the assertion becomes a test
    of where Rich chose to wrap on the CI runner."""

    def test_the_notice_wraps_rather_than_truncating_at_eighty(self) -> None:
        from cli_modelarium.output_formatters import untestable_pairs_notice

        buffer = io.StringIO()
        Console(file=buffer, width=80, force_terminal=False).print(
            untestable_pairs_notice(2, 3)
        )
        rendered = " ".join(buffer.getvalue().split())
        assert "2 of 3 model pairs could not be tested" in rendered
        assert rendered.endswith("over the 1 that was.")
