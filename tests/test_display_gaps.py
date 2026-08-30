"""Four places a console or a report dropped something the data carried.

Each is a surface that reported less than the run knew: a caveat rendered on
one display and not the sibling one, a risk level the JSON published and the
console called N/A, a warning that reached every format except the one people
circulate, and a panel average that hid how much of the panel it averaged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from rich.console import Console

from cli_modelarium.cli import (
    _print_degraded_judge_notice,
    _risk_cell_for_compare,
    _score_cell_for_compare,
)
from cli_modelarium.judging import JudgeResult, JudgeScore
from cli_modelarium.output_formatters import (
    BatchResult,
    _hallucination_summary_cell,
    significance_temperature_caveat,
    write_markdown,
)


def _score(model: str, score: int | None, risk: str | None = None) -> JudgeScore:
    return JudgeScore(
        model=model,
        score=score,
        reasoning="r",
        cost_usd=0.0,
        latency_ms=1.0,
        parse_error=None if score is not None else "no json",
        risk_level=risk,
    )


@dataclass
class _Row:
    """The slice of BatchResult the hallucination cell reads."""

    judge_result: JudgeResult | None = None


# ===== the degraded-judge notice, on both displays =====


class TestDegradedNoticeReachesBothDisplays:
    def test_notice_names_the_degraded_judge(
        self, capture_console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("cli_modelarium.cli.console", capture_console)
        jr = JudgeResult(judges=[_score("gpt-5.5", 8)], average_score=8.0)
        jr.degraded_models = ["gpt-5.5"]

        _print_degraded_judge_notice([jr])

        out = capture_console.file.getvalue()  # type: ignore[attr-defined]
        assert "gpt-5.5" in out
        assert "not reproducible" in out

    def test_silent_when_no_judge_degraded(
        self, capture_console: Console, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("cli_modelarium.cli.console", capture_console)

        _print_degraded_judge_notice([JudgeResult(judges=[_score("gpt-4.1-mini", 8)])])
        _print_degraded_judge_notice(None)

        assert capture_console.file.getvalue() == ""  # type: ignore[attr-defined]

    def test_the_multi_run_display_emits_it(self) -> None:
        """It lived only in the single-run display until now.

        Pinned by call site rather than by rendering a whole comparison: the
        point is that both displays reach the same emitter.
        """
        import inspect

        from cli_modelarium import cli

        for fn in (cli._display_results, cli._display_results_with_runs):
            assert "_print_degraded_judge_notice" in inspect.getsource(fn)


# ===== a risk level with no parsable score is still a risk level =====


class TestRiskLevelSurvivesAnUnparsableScore:
    def test_console_shows_the_risk_the_json_publishes(self) -> None:
        """`aggregated_risk_level` needs only the classification.

        A judge that classified High and returned no parsable score put
        "High" in the JSON and "N/A" on the console - the console hiding the
        worse of the two answers.
        """
        jr = JudgeResult(judges=[_score("gpt-5.5", None, risk="High")])
        jr.aggregated_risk_level = "High"

        cell = _risk_cell_for_compare(jr)

        assert "High" in cell
        assert "N/A" not in cell
        assert "no score" in cell

    def test_markdown_shows_it_too(self) -> None:
        jr = JudgeResult(judges=[_score("gpt-5.5", None, risk="Medium")])
        jr.aggregated_risk_level = "Medium"

        cell = _hallucination_summary_cell(_Row(judge_result=jr))

        assert cell == "Medium (no score)"

    def test_still_na_when_there_is_genuinely_no_classification(self) -> None:
        jr = JudgeResult(judges=[_score("gpt-5.5", None)])

        assert _risk_cell_for_compare(jr) == "[red]N/A[/red]"
        assert _hallucination_summary_cell(_Row(judge_result=jr)) == "N/A"

    def test_a_scored_row_is_unchanged(self) -> None:
        jr = JudgeResult(judges=[_score("gpt-5.5", 8, risk="Low")])
        jr.aggregated_risk_level = "Low"

        assert _risk_cell_for_compare(jr) == "[green]Low[/green] (8)"


# ===== a panel average names how much of the panel answered =====


class TestPartialPanelNamesTheDenominator:
    def test_one_of_three_says_so(self) -> None:
        """"7.0 (1)" is indistinguishable from a single judge answering."""
        jr = JudgeResult(
            judges=[
                _score("a", 7),
                _score("b", None),
                _score("c", None),
            ],
            average_score=7.0,
        )

        assert _score_cell_for_compare(jr) == "7.0 (1 of 3)"

    def test_a_complete_panel_is_unchanged(self) -> None:
        jr = JudgeResult(
            judges=[_score("a", 7), _score("b", 8)],
            average_score=7.5,
        )

        assert _score_cell_for_compare(jr) == "7.5 (2)"

    def test_a_single_judge_is_unchanged(self) -> None:
        jr = JudgeResult(judges=[_score("a", 7)], average_score=7.0)

        assert _score_cell_for_compare(jr) == "7"


# ===== the temperature caveat reaches the circulated format =====


@dataclass
class _Sig:
    model_a: str = "gpt-5.5"
    model_b: str = "gpt-4.1-mini"
    metric: str = "score"
    n_a: int = 5
    n_b: int = 5
    mean_a: float | None = 7.0
    mean_b: float | None = 6.0
    stdev_a: float | None = 1.0
    stdev_b: float | None = 1.0
    test_used: str = "welch_t_test"
    test_statistic: float | None = 1.0
    degrees_of_freedom: float | None = 8.0
    p_value: float | None = 0.04
    p_value_corrected: float | None = 0.04
    correction_method: str = "bonferroni"
    n_comparisons: int = 1
    threshold: float = 0.05
    significant_at_threshold: bool = True
    effect_size: float | None = 1.0
    effect_size_interpretation: str = "large"


def _result() -> BatchResult:
    return BatchResult(
        prompt_id="p1",
        prompt="q",
        system=None,
        model="gpt-5.5",
        temperature=0.0,
        latency_ms=10.0,
        ttft_ms=1.0,
        input_tokens=1,
        output_tokens=1,
        cached_tokens=0,
        cost_usd=0.001,
        output="hello",
        error=None,
        retries=0,
    )


class TestMarkdownCarriesTheTemperatureCaveat:
    def test_caveat_appears_beside_the_p_value(self, tmp_path: Path) -> None:
        """It reached the console and the JSON, never the markdown.

        Markdown is the format written to a file and passed on, so its reader
        is the one least likely to have seen the console warning.
        """
        out = tmp_path / "r.md"

        write_markdown(
            [_result()],
            out,
            runs=5,
            significance_results=[_Sig()],
            models_without_temperature=["gpt-5.5"],
            significance_temperature_mixed=True,
        )

        text = out.read_text(encoding="utf-8")
        assert "Temperature not applied" in text
        assert significance_temperature_caveat(["gpt-5.5"]) in text

    def test_absent_when_the_run_was_not_mixed(self, tmp_path: Path) -> None:
        out = tmp_path / "r.md"

        write_markdown(
            [_result()],
            out,
            runs=5,
            significance_results=[_Sig()],
            models_without_temperature=["gpt-5.5"],
            significance_temperature_mixed=False,
        )

        assert "Temperature not applied" not in out.read_text(encoding="utf-8")

    def test_console_and_markdown_use_one_wording(self) -> None:
        """cli.py renders the same builder, so the two cannot drift."""
        import inspect

        from cli_modelarium import cli

        source = inspect.getsource(cli._warn_temperature_conditions)
        assert "significance_temperature_caveat" in source
