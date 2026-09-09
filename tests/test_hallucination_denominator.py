"""The hallucination rate must divide by the runs that could be classified.

The console cell counted every run that carried a judge result, using a one-part
guard where `compute_mcnemar_pairwise` uses a two-part one:

    jr = judge_by_state_id.get(id(s))
    if jr is None or not jr.judges:
        continue
    judged += 1

A declined run has no answer to classify, but the judge ran on it anyway, so it
landed in the denominator and diluted the rate. Three runs of which one declined
rendered `0/3 (0%)` where the evidence supports `0/2`.

HALF THE NEW GUARD IS DEAD ON ARRIVAL and that is deliberate. `run_judging`
already returns an empty `JudgeResult()` for a state with `error` set, so
`not jr.judges` already excludes a failed run - the `s.error is not None` clause
adds nothing today. It is written anyway so the guard states the whole rule in
one place and matches `run_statistics.py`, rather than depending on a fact about
a different module. `s.refused` is the load-bearing half.

Nothing pinned any of this: no test asserted a hallucination rate string, and
there is no JSON field and no Markdown column for it. It is console-only.

BOTH DIVERGENCES FROM THE STATISTICAL GUARD ARE NOW CLOSED. The refusal half
came first; the `aggregated_risk_level is None` half followed, once it was in
scope. `TestAnUnclassifiableRunAlsoLeavesTheDenominator` below covers the
second, and `TestTheGuardMatchesTheStatisticalOne` pins that the console cell
and `compute_mcnemar_pairwise` now drop the same three kinds of run.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import CompletionResult, OnChunk

MODEL = "claude-opus-4-7"
JUDGE = "claude-sonnet-5"

# Marks a run's output so the judge stub can tell which run it is being asked
# about. Keying on the text rather than on call order matters: judging is
# concurrent, so the Nth judge call is not necessarily about the Nth run.
TAG = "run-{}-of-the-cell"

# A judge verdict carrying neither a score nor a risk level. The second of the
# two routes to an unclassified run; see `_RiskProvider`.
UNSCORED = "<unscored>"


class _RiskProvider:
    """Answers every run, declining the indices in `refuse`.

    `risks` maps a run index to the risk level the judge reports for it. An
    index mapped to None makes the judge name a level OUTSIDE the enum, which is
    how an unclassified run is built: `parse_hallucination_response` rejects it,
    `risk_level` stays None, and the judge still ran so `jr.judges` is non-empty.

    Omitting `risk_level` would NOT do it - the parser derives one from the score
    (1-3 High, 4-6 Medium, 7-10 Low), so a scored verdict is always classified.
    `UNSCORED` below is the other route: no score either, nothing to derive from.
    """

    name = "anthropic"

    def __init__(
        self, risks: dict[int, str | None], refuse: set[int] | None = None
    ) -> None:
        self.risks = risks
        self.refuse = refuse or set()
        self._run = 0
        self.judged_tags: list[str] = []
        # When set, the judge omits `risk_level` entirely rather than naming an
        # invalid one - the parser then derives it from the score.
        self.omit_risk_level = False

    async def stream(
        self, prompt: str, model: str, temperature: float, system_prompt: str | None = None
    ) -> AsyncIterator[str]:  # pragma: no cover - --no-stream is always used
        raise NotImplementedError
        yield ""

    def _judge_text(self, prompt: str) -> str:
        found = re.search(r"run-(\d+)-of-the-cell", prompt)
        # No tag means the judge was handed a declined (empty) output. Record it
        # under a sentinel so a test can assert the call did or did not happen.
        self.judged_tags.append(found.group(0) if found else "<untagged>")
        if found is None:
            return '{"risk_level": "Low", "score": 5, "reasoning": "nothing to check"}'
        if self.omit_risk_level:
            return '{"score": 5, "reasoning": "r"}'
        risk = self.risks.get(int(found.group(1)))
        if risk is None:
            # Outside {Low, Medium, High}: the parser records a parse_error and
            # leaves risk_level None. A judge writing "Critical" or "Severe" is
            # the everyday way this happens.
            return '{"risk_level": "Critical", "score": 5, "reasoning": "r"}'
        if risk == UNSCORED:
            # No score and no risk level - nothing to derive from either.
            return '{"reasoning": "I cannot assess this"}'
        return f'{{"risk_level": "{risk}", "score": 5, "reasoning": "r"}}'

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
        if model == JUDGE:
            text = self._judge_text(prompt)
            if on_chunk is not None:
                on_chunk(text)
            return CompletionResult(
                output=text, input_tokens=200, output_tokens=20, cost_usd=0.0011,
                latency_ms=90.0, ttft_ms=8.0, model=model, provider=self.name,
                temperature=temperature,
            )
        index = self._run
        self._run += 1
        refused = index in self.refuse
        text = "" if refused else f"Paris is the capital of France. {TAG.format(index)}"
        if on_chunk is not None:
            on_chunk(text)
        return CompletionResult(
            output=text, input_tokens=51, output_tokens=0 if refused else 9,
            cost_usd=0.000725, latency_ms=120.0 + index, ttft_ms=10.0, model=model,
            provider=self.name, temperature=temperature, refused=refused,
            stop_reason="refusal" if refused else None,
            stop_category="reasoning_extraction" if refused else None,
        )


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    risks: dict[int, str | None],
    refuse: set[int] | None = None,
    runs: int = 3,
) -> tuple[str, _RiskProvider]:
    provider = _RiskProvider(risks, refuse)
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: provider
    )
    # The judge path pre-checks `is_key_configured` before any provider is
    # built, so patching `_get_provider_instance` alone is not enough.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 95)
    monkeypatch.setenv("COLUMNS", "200")
    result = CliRunner().invoke(
        cli_main,
        ["q", "--models", MODEL, "--judge", JUDGE, "--no-judge-tos", "--no-stream",
         "--no-confidence-intervals", "--check-hallucination", "--runs", str(runs)],
    )
    assert result.exit_code == 0, result.output
    return result.output, provider


def _run(monkeypatch: pytest.MonkeyPatch, *args: Any, **kwargs: Any) -> str:
    return _invoke(monkeypatch, *args, **kwargs)[0]


def _rate(output: str) -> str:
    """The `N/M (P%)` cell from the runs table."""
    flat = " ".join(output.replace("│", " ").split())
    found = re.search(r"(\d+)/(\d+) \((\d+)%\)", flat)
    assert found, flat[:400]
    return found.group(0)


def _no_rate(output: str) -> bool:
    flat = " ".join(output.replace("│", " ").split())
    return re.search(r"\d+/\d+ \(\d+%\)", flat) is None


class TestARefusedRunLeavesTheDenominator:
    def test_one_refusal_of_three(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Was 0/3 (0%): the declined run had no answer to classify and still
        # counted as a run that was classified.
        out = _run(monkeypatch, {1: "Low", 2: "Low"}, refuse={0})
        assert _rate(out) == "0/2 (0%)"

    def test_a_high_among_a_refusal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Was 1/3 (33%). Two runs were classifiable and one of them was High.
        out = _run(monkeypatch, {1: "High", 2: "Low"}, refuse={0})
        assert _rate(out) == "1/2 (50%)"

    def test_a_clean_run_is_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = _run(monkeypatch, {0: "High", 1: "Low", 2: "Low"})
        assert _rate(out) == "1/3 (33%)"

    def test_every_run_refused_renders_no_rate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `if judged > 0` guards the division - the only judge-derived division
        # in the codebase - so an all-declined cell renders a dash, not 0/0.
        assert _no_rate(_run(monkeypatch, {}, refuse={0, 1, 2}))


class TestAnUnclassifiableRunAlsoLeavesTheDenominator:
    """The second divergence from the statistical guard, now closed.

    `compute_mcnemar_pairwise` drops three kinds of run: errored/refused, no
    judge result, and `aggregated_risk_level is None`. The refusal half was
    brought in line first and this class PINNED THE REMAINING GAP rather than
    closing it, because it was not in scope then. It is now: a judge that
    answered without a parseable `risk_level` classified nothing, so the run
    belongs in neither half of the fraction.

    The old assertions are kept below as comments, because the numbers they held
    are what a reader of an earlier report saw.
    """

    def test_an_unclassifiable_run_is_not_counted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Was 1/3 (33%), while compute_mcnemar_pairwise used 1/1 on the same run.
        out = _run(monkeypatch, {0: "High", 1: None, 2: None})
        assert _rate(out) == "1/1 (100%)"

    def test_all_unclassifiable_renders_a_dash_not_a_zero_rate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Was 0/3 (0%) - a confident "no hallucinations" over a cell where
        # nothing was classified at all. `if judged > 0` renders the dash.
        assert _no_rate(_run(monkeypatch, {0: None, 1: None, 2: None}))

    def test_a_refusal_and_an_unclassifiable_run_both_leave(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Was 1/3 (33%): one declined, one unclassifiable, one High.
        out = _run(monkeypatch, {1: None, 2: "High"}, refuse={0})
        assert _rate(out) == "1/1 (100%)"

    def test_an_unscored_verdict_also_leaves(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other route: no score and no risk level, so nothing to derive."""
        out = _run(monkeypatch, {0: "High", 1: UNSCORED, 2: UNSCORED})
        assert _rate(out) == "1/1 (100%)"

    def test_a_verdict_with_only_a_score_is_still_classified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """NOT unclassified. Omitting risk_level derives one from the score, so
        these runs are real observations and stay in the denominator. Pinned
        because it is the case that looks unclassified and is not."""
        provider = _RiskProvider({}, None)
        provider.omit_risk_level = True
        monkeypatch.setattr(
            "cli_modelarium.cli._get_provider_instance", lambda name, **_k: provider
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 95)
        monkeypatch.setenv("COLUMNS", "200")
        result = CliRunner().invoke(
            cli_main,
            ["q", "--models", MODEL, "--judge", JUDGE, "--no-judge-tos",
             "--no-stream", "--no-confidence-intervals", "--check-hallucination",
             "--runs", "3"],
        )
        assert result.exit_code == 0, result.output
        # score 5 -> Medium for all three, so all three are classified.
        assert _rate(result.output) == "0/3 (0%)"

    def test_a_medium_or_low_run_is_still_counted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only an ABSENT classification leaves. A run classified not-High is a
        real observation and stays in the denominator."""
        out = _run(monkeypatch, {0: "High", 1: "Medium", 2: "Low"})
        assert _rate(out) == "1/3 (33%)"


class TestTheGuardMatchesTheStatisticalOne:
    def test_both_guards_read_the_same_two_fields(self) -> None:
        """The console cell and `compute_mcnemar_pairwise` must agree on which
        runs a model was given a chance to answer, or the table and the test
        below it describe different populations."""
        cli_src = Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        stats_src = Path("src/cli_modelarium/run_statistics.py").read_text(
            encoding="utf-8"
        )
        guard = "if s.error is not None or s.refused:"
        assert guard in stats_src, "the statistical guard moved"
        assert guard in cli_src, "the console cell does not use the same guard"

    def test_both_drop_an_unclassified_run(self) -> None:
        """The third exclusion. `compute_mcnemar_pairwise` reads the risk level
        into a local and drops a None; the console cell now does the same."""
        cli_src = Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        stats_src = Path("src/cli_modelarium/run_statistics.py").read_text(
            encoding="utf-8"
        )
        for src, where in ((stats_src, "the statistic"), (cli_src, "the console cell")):
            assert "if risk is None:" in src, f"{where} does not drop an unclassified run"

    def test_the_console_cell_drops_all_three_kinds(self) -> None:
        """Named together so a future edit that removes one is visible as a
        divergence rather than as a tidy-up."""
        import inspect

        from cli_modelarium.cli import _display_results_with_runs

        body = inspect.getsource(_display_results_with_runs)
        cell = body[body.index("Hallucination rate:"):body.index("Judge score")]
        assert "s.error is not None or s.refused" in cell   # errored or declined
        assert "not jr.judges" in cell                       # unjudged
        assert "risk is None" in cell                        # unclassified
