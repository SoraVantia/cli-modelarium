"""`--judge` combined with `--runs`, which nothing else in the suite covers.

That gap is why a cluster of judging defects survived: mode-only judging makes
ONE judge call per (model, temperature, system_prompt) cell and broadcasts the
verdict to every run in that cell, and no test ever exercised the combination.

The invariants pinned here:

    * one judge call per cell, never per run - the call count must not move
    * the score sample is one observation per cell, carrying that cell's verdict
    * judge cost counts each call once, across every surface that reports it
    * paired tests key on the cell AND the run, so neither judging mode loses
      observations to a key collision
"""

from __future__ import annotations

import itertools
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk
from cli_modelarium.run_statistics import group_states_by_cell

# Substrings that mark a judge prompt, covering the plain and hallucination
# templates. A harness that misses one silently counts judge calls as main
# calls, which would make every assertion below vacuous.
JUDGE_MARKERS = (
    "Respond with ONLY a JSON object",
    "hallucination risk",
    "Respond ONLY with JSON",
)


def _is_judge_prompt(prompt: str) -> bool:
    return any(m in prompt for m in JUDGE_MARKERS)


class _CountingProvider(BaseProvider):
    """Counts REAL judge calls separately from main calls.

    The point of these tests is what actually reached a provider, so the count
    is taken here rather than from anything the tool reports about itself.
    """

    def __init__(self, judge_score: int = 8, judge_cost: float = 0.0001) -> None:
        self.name = "fake"
        self.judge_calls = 0
        self.main_calls = 0
        self._judge_score = judge_score
        self._judge_cost = judge_cost
        self._counter = itertools.count()

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if False:
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
    ) -> CompletionResult:
        judging = _is_judge_prompt(prompt)
        if judging:
            self.judge_calls += 1
            text = json.dumps({"score": self._judge_score, "reasoning": "ok"})
        else:
            self.main_calls += 1
            text = f"answer for {model} v{next(self._counter) % 3}"
        if on_chunk is not None:
            on_chunk(text)
        return CompletionResult(
            output=text,
            input_tokens=10,
            output_tokens=5,
            cost_usd=self._judge_cost if judging else 0.001,
            latency_ms=42.0,
            ttft_ms=1.0,
            model=model,
            provider="fake",
            temperature=temperature,
        )


@pytest.fixture
def counting_provider(monkeypatch: pytest.MonkeyPatch) -> _CountingProvider:
    fake = _CountingProvider()
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance",
        lambda name, **_kwargs: fake,
    )
    for env, value in (
        ("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_test_fixture_00"),
        ("ANTHROPIC_API_KEY", "sk-ant-NOT_A_REAL_KEY_test_fixture_0"),
        ("GOOGLE_API_KEY", "AIzaNOT_A_REAL_KEY_test_fixture_00000"),
    ):
        monkeypatch.setenv(env, value)
    return fake


def _judged_run(
    tmp_path: Path, extra: list[str] | None = None
) -> tuple[Any, dict[str, Any]]:
    """Run a judged multi-run comparison and return (result, json payload)."""
    out = tmp_path / "out.json"
    result = CliRunner().invoke(
        cli_main,
        [
            "q", "--models", "gpt-5.5,claude-opus-4-7",
            "--runs", "5", "--judge", "gemini-3.1-pro-preview",
            "--no-stream", "--no-judge-tos",
            *(extra or []),
            "--output", str(out), "--output-format", "json",
        ],
    )
    assert result.exit_code == 0, result.output
    return result, json.loads(out.read_text(encoding="utf-8"))


# ===== one judge call per cell, never per run =====


class TestJudgeCallCount:
    @pytest.mark.parametrize(
        ("temperatures", "cells_per_model"),
        [("0.0", 1), ("0.0,0.5,1.0", 3), ("0.0,0.3,0.6,0.9", 4)],
    )
    def test_calls_scale_with_cells_not_runs(
        self,
        counting_provider: _CountingProvider,
        tmp_path: Path,
        temperatures: str,
        cells_per_model: int,
    ) -> None:
        _judged_run(tmp_path, ["--temperatures", temperatures])

        # Two models, so two cells per temperature. --runs 5 must not multiply.
        assert counting_provider.judge_calls == 2 * cells_per_model

    @pytest.mark.parametrize("runs", ["5", "20"])
    def test_runs_does_not_multiply_the_call_count(
        self, counting_provider: _CountingProvider, tmp_path: Path, runs: str
    ) -> None:
        out = tmp_path / "out.json"
        result = CliRunner().invoke(
            cli_main,
            [
                "q", "--models", "gpt-5.5,claude-opus-4-7", "--runs", runs,
                "--judge", "gemini-3.1-pro-preview", "--no-stream", "--no-judge-tos",
                "--output", str(out), "--output-format", "json",
            ],
        )
        assert result.exit_code == 0, result.output
        assert counting_provider.judge_calls == 2


# ===== the score sample is one observation per cell =====


class TestScoreSampleIsPerCell:
    @pytest.mark.parametrize(
        ("temperatures", "cells_per_model"),
        [("0.0", 1), ("0.0,0.5,1.0", 3), ("0.0,0.3,0.6,0.9", 4)],
    )
    def test_n_equals_the_cell_count(
        self,
        counting_provider: _CountingProvider,
        tmp_path: Path,
        temperatures: str,
        cells_per_model: int,
    ) -> None:
        """n is the number of cells - not the number of runs, and not 1.

        This is the invariant the cell key preserves. An id()-keyed lookup
        gives the same answer only while the verdicts stay aliased.
        """
        _, payload = _judged_run(tmp_path, ["--temperatures", temperatures])

        entry = payload["significance_tests"][0]
        assert entry["metric"] == "score"
        assert entry["n_a"] == cells_per_model
        assert entry["n_b"] == cells_per_model

    def test_system_prompts_form_cells_too(
        self, counting_provider: _CountingProvider, tmp_path: Path
    ) -> None:
        """The cell is (model, temperature, system_prompt) - all three."""
        _, payload = _judged_run(
            tmp_path, ["--system-prompts", "Be terse,Be verbose,Be formal"]
        )

        assert counting_provider.judge_calls == 6
        assert payload["significance_tests"][0]["n_a"] == 3

    def test_the_cell_key_is_the_documented_tuple(self) -> None:
        """Guards the key the extractor relies on against a silent widening."""
        from types import SimpleNamespace

        states = [
            SimpleNamespace(model="m", temperature=0.0, system_prompt=None, run_index=i)
            for i in range(3)
        ]
        states.append(
            SimpleNamespace(model="m", temperature=0.5, system_prompt=None, run_index=0)
        )
        cells = group_states_by_cell(states)  # type: ignore[arg-type]

        assert set(cells) == {("m", 0.0, None), ("m", 0.5, None)}


# ===== judge cost counts each call once, everywhere it is reported =====


class TestJudgeCostCountsEachCallOnce:
    @pytest.mark.parametrize("runs", [5, 20])
    def test_reported_cost_is_the_cost_actually_incurred(
        self, counting_provider: _CountingProvider, tmp_path: Path, runs: int
    ) -> None:
        """The whole point: $ reported == $ spent, at any --runs.

        Broadcasting one verdict object to N runs billed the same call N
        times, so --runs 20 over-reported judge spend twentyfold.
        """
        _, payload = _judged_run(tmp_path, ["--runs", str(runs)])

        spent = counting_provider.judge_calls * 0.0001
        assert payload["judge_cost_usd"] == pytest.approx(spent)

    def test_runs_does_not_change_the_reported_judge_cost(
        self, counting_provider: _CountingProvider, tmp_path: Path
    ) -> None:
        _, five = _judged_run(tmp_path / "a", ["--runs", "5"])
        _, twenty = _judged_run(tmp_path / "b", ["--runs", "20"])

        assert five["judge_cost_usd"] == twenty["judge_cost_usd"]

    def test_exactly_one_row_per_cell_carries_the_cost(
        self, counting_provider: _CountingProvider, tmp_path: Path
    ) -> None:
        """The inherited rows are zero-cost copies - not empty ones."""
        _, payload = _judged_run(tmp_path, ["--runs", "5"])
        rows = payload["results"]

        priced = [r for r in rows if r["judges"][0]["cost_usd"] > 0]
        assert len(priced) == counting_provider.judge_calls
        assert len(rows) == 10  # two models x five runs
        # Every row still displays its cell's verdict.
        assert all(r["judges"][0]["score"] is not None for r in rows)

    def test_per_row_costs_sum_to_the_reported_total(
        self, counting_provider: _CountingProvider, tmp_path: Path
    ) -> None:
        """The JSON and markdown formatters re-sum the rows themselves."""
        _, payload = _judged_run(tmp_path, ["--runs", "5"])

        row_sum = sum(j["cost_usd"] for r in payload["results"] for j in r["judges"])
        assert row_sum == pytest.approx(payload["judge_cost_usd"])

    def test_private_markers_do_not_reach_the_output(
        self, counting_provider: _CountingProvider, tmp_path: Path
    ) -> None:
        _, payload = _judged_run(tmp_path, ["--runs", "5"])

        blob = json.dumps(payload)
        for marker in ("_broadcast", "_inherited", "_state_id"):
            assert marker not in blob

    def test_console_reports_the_calls_that_were_made(
        self, counting_provider: _CountingProvider, tmp_path: Path
    ) -> None:
        result = CliRunner().invoke(
            cli_main,
            [
                "q", "--models", "gpt-5.5,claude-opus-4-7", "--runs", "20",
                "--judge", "gemini-3.1-pro-preview", "--no-stream", "--no-judge-tos",
            ],
        )

        assert result.exit_code == 0, result.output
        assert counting_provider.judge_calls == 2
        assert "Judge cost: $0.000200 (2 judge calls)" in result.output


class TestJudgeCallCountIsNotDerivedFromCost:
    def test_a_free_judge_model_still_counts_its_calls(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """17 registry rows are legitimately $0, so cost cannot stand in.

        Counting non-zero costs would report "0 judge calls" for a free
        judge - the exact silent undercount this replaces.
        """
        free = _CountingProvider(judge_cost=0.0)
        monkeypatch.setattr(
            "cli_modelarium.cli._get_provider_instance", lambda name, **_k: free
        )
        for env, value in (
            ("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_test_fixture_00"),
            ("ANTHROPIC_API_KEY", "sk-ant-NOT_A_REAL_KEY_test_fixture_0"),
            ("GOOGLE_API_KEY", "AIzaNOT_A_REAL_KEY_test_fixture_00000"),
        ):
            monkeypatch.setenv(env, value)

        result = CliRunner().invoke(
            cli_main,
            [
                "q", "--models", "gpt-5.5,claude-opus-4-7", "--runs", "5",
                "--judge", "gemini-3.1-pro-preview", "--no-stream", "--no-judge-tos",
            ],
        )

        assert result.exit_code == 0, result.output
        assert free.judge_calls == 2
        assert "Judge cost: $0.000000 (2 judge calls)" in result.output


class TestPerRunJudgingIsUntouched:
    def test_hallucination_mode_still_bills_and_counts_every_run(
        self, counting_provider: _CountingProvider, tmp_path: Path
    ) -> None:
        """--check-hallucination judges every run, so nothing is inherited."""
        _, payload = _judged_run(tmp_path, ["--check-hallucination"])

        assert counting_provider.judge_calls == 10  # two models x five runs
        assert payload["judge_cost_usd"] == pytest.approx(10 * 0.0001)
        priced = [r for r in payload["results"] if r["judges"][0]["cost_usd"] > 0]
        assert len(priced) == 10
