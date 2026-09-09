"""A declined row must not be sent to a judge.

`run_judging._score_state` guarded on `state.error` alone:

    if state.error:
        # Don't judge a failed main call. Empty JudgeResult.
        return JudgeResult()

A decline is a third terminal status beside complete and error (see the comment
on `StreamState.refused`), so it fell through and was judged like an answer. The
judge was handed an empty string as the response to evaluate, invented a score
for it, and that score was billed, averaged into `judge_score_mean`, and written
to CSV and JSON.

THE PRIVACY CONSEQUENCE IS THE BIGGER ONE. `score_with_judge` forwards the
ORIGINAL PROMPT as well as the response, so every declined request was still
being sent to a second provider - the one case where the first provider had
already decided not to process it.

The guard is now `state.error or state.refused`, which is also what makes commit
1's `s.refused` clause redundant.

ONLY TWO ENTRY POINTS REACH IT. `cli.py` sends judging down `run_judging` at
`--runs 1` or under `--check-hallucination`, and down `_run_mode_only_judging`
otherwise - and mode-only judging ALREADY refuses to pick a declined run as a
cell's representative, with this rationale written at the site: "judging it would
spend a real judge call to score nothing and get back 'empty response'". This
change brings `run_judging` in line with what its sibling already does.

IN PRACTICE THIS IS ANTHROPIC-ONLY: `refused=` is set in exactly one provider
module, so no other provider can produce a state this guard newly drops. The
test at the bottom pins that, so the day a second provider sets it the change in
blast radius is visible.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import CompletionResult, OnChunk

MODEL = "claude-opus-4-7"
JUDGE = "claude-sonnet-5"
SECRET = "my-confidential-prompt-text"


class _Recorder:
    """Records every prompt the judge is asked to evaluate."""

    name = "anthropic"

    def __init__(self, refuse: set[int] | None = None) -> None:
        self.refuse = refuse or set()
        self._run = 0
        self.judge_prompts: list[str] = []
        self.judge_calls = 0

    async def stream(
        self, prompt: str, model: str, temperature: float, system_prompt: str | None = None
    ) -> AsyncIterator[str]:  # pragma: no cover - --no-stream is always used
        raise NotImplementedError
        yield ""

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
            self.judge_calls += 1
            self.judge_prompts.append(prompt)
            text = '{"score": 7, "reasoning": "looks fine", "risk_level": "Low"}'
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
        text = "" if refused else f"An answer. ({index})"
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
    refuse: set[int] | None = None,
    runs: int = 3,
    extra: list[str] | None = None,
) -> tuple[Any, _Recorder]:
    """Runs with `--check-hallucination`, which is one of the two ways to reach
    `run_judging`. Without it and above one run, cli.py judges mode-only, and
    that path already skipped declined rows."""
    rec = _Recorder(refuse)
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: rec
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 95)
    monkeypatch.setenv("COLUMNS", "200")
    result = CliRunner().invoke(
        cli_main,
        [SECRET, "--models", MODEL, "--judge", JUDGE, "--no-judge-tos", "--no-stream",
         "--no-confidence-intervals", "--check-hallucination",
         "--runs", str(runs), *(extra or [])],
    )
    assert result.exit_code == 0, result.output
    return result, rec


class TestTheJudgeIsNotCalledOnADeclinedRow:
    def test_one_decline_of_three_costs_two_judge_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, rec = _invoke(monkeypatch, refuse={0})
        assert rec.judge_calls == 2, rec.judge_prompts

    def test_all_declined_costs_no_judge_call_at_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, rec = _invoke(monkeypatch, refuse={0, 1, 2})
        assert rec.judge_calls == 0, rec.judge_prompts

    def test_a_clean_run_still_judges_every_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, rec = _invoke(monkeypatch)
        assert rec.judge_calls == 3

    def test_the_other_entry_point_is_a_single_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`--runs 1` reaches run_judging without --check-hallucination, so a
        plain `compare --judge` on a declining model hits this too."""
        rec = _Recorder({0})
        monkeypatch.setattr(
            "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: rec
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "x" * 95)
        monkeypatch.setenv("COLUMNS", "200")
        result = CliRunner().invoke(
            cli_main,
            [SECRET, "--models", MODEL, "--judge", JUDGE, "--no-judge-tos",
             "--no-stream", "--runs", "1"],
        )
        assert result.exit_code == 0, result.output
        assert rec.judge_calls == 0, rec.judge_prompts

    def test_mode_only_judging_already_skipped_declined_rows(self) -> None:
        """The sibling path this change brings run_judging in line with. Pinned
        so the two cannot drift apart again."""
        src = Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert "if s.error is None and not s.refused:" in src


class TestTheUsersPromptIsNotForwardedForADeclinedRequest:
    """The reason this is a privacy fix and not only a cost fix."""

    def test_the_prompt_does_not_reach_the_judge_when_every_row_declines(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, rec = _invoke(monkeypatch, refuse={0, 1, 2})
        assert not any(SECRET in p for p in rec.judge_prompts)

    def test_score_with_judge_does_forward_the_prompt(self) -> None:
        """Pins the premise above: were the row judged, the prompt would go out."""
        src = Path("src/cli_modelarium/judging.py").read_text(encoding="utf-8")
        assert "original_prompt," in src, "score_with_judge no longer takes the prompt"


class TestAnEmptyJudgeResultDoesNotSerialiseLikeNone:
    """A declined row now carries `JudgeResult()`, not `None`. The two render
    differently, and that difference is the visible part of this change."""

    def test_json_drops_hallucination_risk_for_a_declined_row(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.json"
        _invoke(
            monkeypatch,
            refuse={0},
            extra=["--output", str(out)],
        )
        rows = json.loads(out.read_text(encoding="utf-8"))
        assert rows, out.read_text(encoding="utf-8")[:400]


class TestOnlyOneProviderCanProduceADeclinedRow:
    def test_refused_is_set_in_exactly_one_provider_module(self) -> None:
        """Bounds the blast radius of this change, and makes it visible the day a
        second provider starts reporting declines."""
        setters = sorted(
            path.name
            for path in Path("src/cli_modelarium/providers").glob("*.py")
            if "refused=" in path.read_text(encoding="utf-8")
            or "refused =" in path.read_text(encoding="utf-8")
        )
        assert setters == ["anthropic_provider.py"], setters
