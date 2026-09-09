"""A refusing model must not launder its failure through one that answered.

`pass_rate` excludes errored assertions from both halves of the ratio, so a
refusal removes itself from the denominator. One definitive assertion anywhere
in the batch makes `rate is not None`, which skips the refusal-catching branch
for the WHOLE run - so adding a model that answers turns exit 1 into exit 0:

    gpt-5.5 + claude-opus-4-7, opus declining everything
        3 succeeded  0 failed  3 refused   assertions 8/8 (100%)   EXIT 0
    claude-opus-4-7 alone, the same refusals
        0 succeeded  0 failed  3 refused   assertions 0/8 errored  EXIT 1

No gate flag caught it. `--min-pass-rate 1.0` - the strictest the CLI accepts -
passed, because the rate genuinely IS 1.0 over a denominator the refusals left.
`--strict-assertions` reads `totals.failed`, and `count_failed` is
`not r.passed and r.error is None`, so a refusal is never a failure.

The mechanism is a distinct error CATEGORY rather than a match on the error
string, and `TestTheMechanismSurvivesAnEnrichedMessage` below is the reason:
a string match ties on every other measure and then silently reopens the defect
the first time someone enriches the human-readable message.

These run against `examples/ci_eval_suite.json` with the command from
`examples/github_actions_workflow.yml` - this project's own published workflow,
whose first prompt is literally `"id": "no_refusals"`.
"""

from __future__ import annotations

import ast
import csv
import io
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from rich.console import Console

import cli_modelarium.cli as cli_module
from cli_modelarium.assertions import (
    AssertionResult,
    AssertionTotals,
    count_assertion_totals,
    count_refused,
    refused_results,
)
from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import CompletionResult, OnChunk

SUITE = "examples/ci_eval_suite.json"
ANSWERING = "gpt-5.5"
REFUSING = "claude-opus-4-7"

ROMEO = (
    "Romeo and Juliet is a tragedy by William Shakespeare about two young lovers from "
    "feuding families in Verona. They meet at a masked ball, marry in secret with Friar "
    "Laurence's help, and a street brawl leaves Mercutio and Tybalt dead and Romeo "
    "banished. A sleeping-potion plan miscarries and both lovers die by their own hands, "
    "which finally reconciles the two households."
)


class _SuiteProvider:
    """Answers the shipped suite. `refusing` names models that decline.

    `only` limits the refusal to prompts containing that substring, which is
    how the partial case is built.
    """

    name = "anthropic"

    def __init__(self, refusing: set[str], only: str | None = None) -> None:
        self.refusing = refusing
        self.only = only

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
        if "Romeo" in prompt:
            text = ROMEO
        elif "47 times" in prompt:
            text = "47 times 23 is 1081."
        else:
            text = "Photosynthesis converts light into chemical energy in plants."
        refused = model in self.refusing and (self.only is None or self.only in prompt)
        if refused:
            text = ""
        if on_chunk is not None:
            on_chunk(text)
        return CompletionResult(
            output=text,
            input_tokens=51,
            output_tokens=0 if refused else 40,
            cost_usd=0.000725,
            latency_ms=120.0,
            ttft_ms=10.0,
            model=model,
            provider=self.name,
            temperature=temperature,
            refused=refused,
            stop_reason="refusal" if refused else None,
            stop_category="reasoning_extraction" if refused else None,
        )


def _use(
    monkeypatch: pytest.MonkeyPatch, refusing: str = "", only: str | None = None
) -> None:
    provider = _SuiteProvider(set(refusing.split(",")) if refusing else set(), only)
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: provider
    )


def _batch(*args: str, suite: str = SUITE) -> Any:
    return CliRunner().invoke(cli_main, ["batch", suite, *args])


def _write_suite(tmp_path: Path, entries: list[dict[str, Any]]) -> str:
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return str(path)


# The four gate configurations. `--strict-assertions` and `--min-pass-rate` are
# mutually exclusive, so they are separate rows rather than one command.
GATES: list[list[str]] = [
    ["--min-pass-rate", "0.9"],
    ["--min-pass-rate", "1.0"],
    ["--strict-assertions"],
    [],
]


class TestTheShippedWorkflowCatchesIt:
    """The published workflow against the published suite - the reproduction."""

    def test_the_shipped_command_exits_non_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # examples/github_actions_workflow.yml, verbatim but for the output path.
        _use(monkeypatch, REFUSING)
        result = _batch(
            "--models",
            f"{ANSWERING},{REFUSING}",
            "--output",
            str(tmp_path / "results.json"),
            "--min-pass-rate",
            "0.9",
        )
        assert result.exit_code == 1, result.output

    @pytest.mark.parametrize("gate", GATES, ids=lambda g: " ".join(g) or "default")
    def test_every_gate_configuration_catches_it(
        self, monkeypatch: pytest.MonkeyPatch, gate: list[str]
    ) -> None:
        _use(monkeypatch, REFUSING)
        result = _batch("--models", f"{ANSWERING},{REFUSING}", *gate)
        assert result.exit_code == 1, result.output

    @pytest.mark.parametrize("gate", GATES, ids=lambda g: " ".join(g) or "default")
    def test_a_clean_run_is_untouched(
        self, monkeypatch: pytest.MonkeyPatch, gate: list[str]
    ) -> None:
        _use(monkeypatch)
        result = _batch("--models", f"{ANSWERING},{REFUSING}", *gate)
        assert result.exit_code == 0, result.output

    def test_the_refusing_model_alone_still_exits_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # It already did, through the "nothing was verified" path. The new gate
        # must not change which message that run gets.
        _use(monkeypatch, REFUSING)
        result = _batch("--models", REFUSING, "--min-pass-rate", "0.9")
        assert result.exit_code == 1, result.output
        assert "Nothing was verified" in result.output

    def test_the_message_names_the_count_and_says_what_it_means(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _use(monkeypatch, REFUSING)
        result = _batch("--models", f"{ANSWERING},{REFUSING}", "--min-pass-rate", "0.9")
        flat = " ".join(result.output.split())
        # Eight configured assertions on the refusing model's three prompts.
        assert "8 configured assertion" in flat
        assert "refused" in flat


class TestOnlySkippedAssertionsCount:
    """A refusal that removed nothing from the denominator is not a gate failure."""

    def test_a_refused_prompt_with_no_assertions_still_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        suite = _write_suite(
            tmp_path,
            [
                {
                    "id": "asserted",
                    "prompt": "What is 47 times 23?",
                    "assertions": [{"type": "contains", "value": "1081"}],
                },
                {"id": "bare", "prompt": "Define photosynthesis briefly."},
            ],
        )
        _use(monkeypatch, REFUSING, only="photosynthesis")
        result = _batch(
            "--models", f"{ANSWERING},{REFUSING}", "--min-pass-rate", "0.9", suite=suite
        )
        assert result.exit_code == 0, result.output

    def test_a_refused_prompt_with_assertions_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        suite = _write_suite(
            tmp_path,
            [
                {
                    "id": "asserted",
                    "prompt": "What is 47 times 23?",
                    "assertions": [{"type": "contains", "value": "1081"}],
                },
                {"id": "bare", "prompt": "Define photosynthesis briefly."},
            ],
        )
        _use(monkeypatch, REFUSING, only="47 times")
        result = _batch(
            "--models", f"{ANSWERING},{REFUSING}", "--min-pass-rate", "0.9", suite=suite
        )
        assert result.exit_code == 1, result.output

    def test_the_partial_case_one_prompt_of_three(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The refusing model answers two prompts and declines one, so its own
        # answered assertions land in the denominator and dilute rather than
        # vanish. The two it skipped still have to fire the gate.
        _use(monkeypatch, REFUSING, only="47 times")
        result = _batch("--models", f"{ANSWERING},{REFUSING}", "--min-pass-rate", "0.9")
        assert result.exit_code == 1, result.output

    def test_no_assertions_with_a_refusal_still_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # --no-assertions skips them all, so a refusal removed nothing.
        _use(monkeypatch, REFUSING)
        result = _batch("--models", f"{ANSWERING},{REFUSING}", "--no-assertions")
        assert result.exit_code == 0, result.output


class TestTheOptionalDependencyGuaranteeSurvives:
    """A missing jsonschema errors that assertion identically for EVERY model,
    so it cannot create a differential and no other model's passes can launder
    it. A refusal errors on ONE model, ONE prompt - which is exactly the
    differential another model's passes absorb. That difference is why the fix
    keys on the cause rather than on `error` being set."""

    @staticmethod
    def _no_jsonschema(monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins
        import sys

        monkeypatch.delitem(sys.modules, "jsonschema", raising=False)
        real_import = builtins.__import__

        def fake_import(name: str, *a: object, **k: object) -> object:
            if name == "jsonschema" or name.startswith("jsonschema."):
                raise ImportError("simulated")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)

    def test_a_missing_dependency_still_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        suite = _write_suite(
            tmp_path,
            [
                {
                    "id": "p1",
                    "prompt": "What is 47 times 23?",
                    "assertions": [
                        {"type": "json_schema", "value": {"type": "object"}},
                        {"type": "contains", "value": "1081"},
                    ],
                }
            ],
        )
        self._no_jsonschema(monkeypatch)
        _use(monkeypatch)
        result = _batch("--models", ANSWERING, suite=suite)
        assert result.exit_code == 0, result.output

    def test_an_environment_error_is_not_counted_as_a_refusal(self) -> None:
        from cli_modelarium.assertions import run_assertions

        results = run_assertions(
            output="{}",
            latency_ms=100.0,
            cost_usd=0.0007,
            assertions=[{"type": "regex", "value": "([unclosed"}],
        )
        assert results[0].error is not None
        assert results[0].error_kind == "environment"
        assert count_refused(results) == 0


class TestTheMechanismSurvivesAnEnrichedMessage:
    """The test that separates a category from a string match.

    A mechanism matching `r.error == REFUSAL_ERROR` ties on every other measure
    in this file. It then reports zero the first time the message gains
    per-refusal context - and 0.1.9 spent a commit putting `stop_category` on
    four other surfaces, so this message is the obvious next one.
    """

    ENRICHED = "model refused (reasoning_extraction); no output to assert against"

    def test_the_count_does_not_depend_on_the_message_text(self) -> None:
        results = refused_results([{"type": "contains", "value": "x"}] * 2)
        for r in results:
            r.error = self.ENRICHED
        assert count_refused(results) == 2
        assert count_assertion_totals([results]).refused == 2

    def test_the_gate_still_fires_after_the_message_is_enriched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cli_modelarium import assertions as assertions_module

        real = assertions_module.refused_results

        def enriched(configs: list[dict[str, Any]]) -> list[AssertionResult]:
            out = real(configs)
            for r in out:
                r.error = self.ENRICHED
            return out

        monkeypatch.setattr(cli_module, "refused_results", enriched)
        _use(monkeypatch, REFUSING)
        result = _batch("--models", f"{ANSWERING},{REFUSING}", "--min-pass-rate", "0.9")
        assert result.exit_code == 1, result.output

    def test_the_tag_is_what_is_matched(self) -> None:
        # Same message, no tag: not a refusal. This is the inverse of the two
        # above and pins that the tag alone decides.
        untagged = AssertionResult(
            type="contains",
            passed=False,
            expected=None,
            actual=None,
            message="not evaluated: the model refused",
            error="model refused; no output to assert against",
        )
        assert count_refused([untagged]) == 0


class TestEveryErrorSiteIsCategorised:
    """Thirteen non-refusal sites set `error`. None may be left implicit: the
    day someone writes the inverse predicate, an uncategorised site becomes a
    silent misclassification."""

    @staticmethod
    def _error_constructions() -> list[tuple[int, set[str]]]:
        source = Path("src/cli_modelarium/assertions.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        out = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "AssertionResult":
                continue
            kwargs = {k.arg for k in node.keywords if k.arg}
            err = [k for k in node.keywords if k.arg == "error"]
            if not err:
                continue
            value = err[0].value
            if isinstance(value, ast.Constant) and value.value is None:
                continue
            out.append((node.lineno, kwargs))
        return out

    def test_all_fourteen_error_constructions_carry_a_kind(self) -> None:
        rows = self._error_constructions()
        # 14 total: the refusal plus thirteen environment causes.
        assert len(rows) == 14, [ln for ln, _ in rows]
        missing = [ln for ln, kwargs in rows if "error_kind" not in kwargs]
        assert not missing, (
            f"AssertionResult sets `error` without `error_kind` at lines {missing}. "
            f"Leaving it None makes None mean 'environment' implicitly."
        )

    def test_exactly_one_of_them_is_the_refusal(self) -> None:
        # Read the kwarg VALUES, not the source text: the field is discussed in
        # prose above its own definition, and a text count picks that up.
        kinds: list[str] = []
        source = Path("src/cli_modelarium/assertions.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "AssertionResult":
                continue
            for kw in node.keywords:
                if kw.arg == "error_kind" and isinstance(kw.value, ast.Constant):
                    kinds.append(kw.value.value)
        assert kinds.count("refused") == 1
        assert kinds.count("environment") == 13
        assert set(kinds) == {"refused", "environment"}


class TestTheReportAgreesWithTheExitCode:
    """A red build attached to a report reading 100% is the first bug a CI
    owner files. The count reaches every surface that shows the ratio."""

    def _run(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ext: str) -> str:
        _use(monkeypatch, REFUSING)
        path = tmp_path / f"out.{ext}"
        result = _batch(
            "--models", f"{ANSWERING},{REFUSING}", "--output", str(path),
            "--min-pass-rate", "0.9",
        )
        assert result.exit_code == 1, result.output
        return path.read_text(encoding="utf-8")

    def test_the_json_carries_the_count(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        payload = json.loads(self._run(monkeypatch, tmp_path, "json"))
        assert payload["total_assertions_refused"] == 8
        # The pre-existing terms are untouched: the ratio still describes the
        # requests that were answered, which is what it has always meant.
        assert payload["total_assertions"] == 8
        assert payload["total_assertions_passed"] == 8
        assert payload["pass_rate"] == 1.0

    def test_it_reads_zero_on_a_clean_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Always present whenever the assertions block fires, matching
        # `total_assertions_errored` - which sits two fields above it and had
        # the opposite rule, so one field said absence must not mean "nothing
        # errored" while its neighbour made absence mean "nothing refused".
        _use(monkeypatch)
        path = tmp_path / "clean.json"
        assert _batch(
            "--models", f"{ANSWERING},{REFUSING}", "--output", str(path)
        ).exit_code == 0
        assert json.loads(path.read_text(encoding="utf-8"))["total_assertions_refused"] == 0

    def test_the_markdown_header_no_longer_reads_as_a_clean_pass(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        report = self._run(monkeypatch, tmp_path, "md")
        # Was "- Assertions: 8/8 (100.0% pass rate)" beside "3 refused".
        assert "8 not evaluated (refused)" in report
        assert "- Results: 6 (0 failed, 3 refused)" in report

    def test_the_markdown_is_unchanged_on_a_clean_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _use(monkeypatch)
        path = tmp_path / "clean.md"
        assert _batch(
            "--models", f"{ANSWERING},{REFUSING}", "--output", str(path)
        ).exit_code == 0
        text = path.read_text(encoding="utf-8")
        # Two models x eight assertions, all answered.
        assert "- Assertions: 16/16 (100.0% pass rate)" in text
        assert "refused" not in text

    def test_the_console_line_says_it_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _use(monkeypatch, REFUSING)
        result = _batch("--models", f"{ANSWERING},{REFUSING}", "--min-pass-rate", "0.9")
        flat = " ".join(result.output.split())
        assert "8 refused" in flat

    def test_the_csv_schema_is_untouched(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # The per-row CSV cells still cannot tell a refused row from one with no
        # assertions configured; that needs new columns and belongs to the
        # layout group. What must not happen here is a column appearing.
        from cli_modelarium.output_formatters import CSV_COLUMNS

        text = self._run(monkeypatch, tmp_path, "csv")
        assert list(csv.reader(io.StringIO(text)))[0] == list(CSV_COLUMNS)


class TestNoStatisticMoved:
    """The ratio itself is untouched: it still describes the requests that were
    answered. Only a count is added beside it."""

    def test_the_totals_arithmetic_is_what_it_was(self) -> None:
        from cli_modelarium.assertions import run_assertions

        answered = run_assertions(
            output="47 times 23 is 1081.",
            latency_ms=120.0,
            cost_usd=0.000725,
            assertions=[
                {"type": "contains", "value": "1081"},
                {"type": "latency_under", "value": 5000},
            ],
        )
        declined = refused_results(
            [{"type": "contains", "value": "1081"}, {"type": "latency_under", "value": 5000}]
        )
        totals = count_assertion_totals([answered, declined])
        assert (totals.passed, totals.definitive, totals.failed, totals.errored) == (2, 2, 0, 2)
        assert totals.pass_rate == 1.0
        assert totals.configured is True
        assert totals.nothing_verified is False
        assert totals.refused == 2

    def test_refused_defaults_to_zero(self) -> None:
        # Constructed without the new field, as any caller predating it would.
        assert AssertionTotals(passed=1, definitive=1, failed=0, errored=0).refused == 0


class TestRenderedWidthIsPinned:
    """A Console built in a test must pin its width, or the assertion becomes a
    test of where Rich chose to wrap on the CI runner."""

    def test_the_new_error_line_wraps_rather_than_truncating(self) -> None:
        buffer = io.StringIO()
        console = Console(file=buffer, width=80, force_terminal=False)
        console.print(
            "8 configured assertions were not evaluated because the model refused."
        )
        rendered = " ".join(buffer.getvalue().split())
        assert rendered.endswith("because the model refused.")


class TestTheTrueTotalIsPublishedBesideTheDefinitiveOne:
    """`total_assertions` publishes the DEFINITIVE count under a name that reads
    as the whole suite. It is not renamed or redefined: it is the denominator of
    `pass_rate`, and `total_assertions_passed / total_assertions == pass_rate`
    holds exactly today. A sibling carries the true total instead."""

    def _payload(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, refusing: str) -> dict:
        _use(monkeypatch, refusing)
        path = tmp_path / "out.json"
        _batch("--models", f"{ANSWERING},{REFUSING}", "--output", str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def test_the_sibling_carries_the_whole_suite(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        payload = self._payload(monkeypatch, tmp_path, REFUSING)
        # Sixteen configured: eight answered and definitive, eight refused.
        assert payload["total_assertions_configured"] == 16
        assert payload["total_assertions"] == 8
        assert payload["total_assertions_errored"] == 8

    def test_the_identity_that_forbids_redefining_it_still_holds(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        payload = self._payload(monkeypatch, tmp_path, REFUSING)
        assert (
            payload["total_assertions_passed"] / payload["total_assertions"]
            == payload["pass_rate"]
        )

    def test_it_is_always_present_and_equals_the_definitive_count_when_clean(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Unconditional, so a consumer never has to read absence as zero - the
        # precedent `total_assertions_errored` set, and which the refusal count
        # beside it now follows too rather than contradicting from inside the
        # same block.
        payload = self._payload(monkeypatch, tmp_path, "")
        assert payload["total_assertions_configured"] == 16
        assert payload["total_assertions"] == 16
        assert payload["total_assertions_refused"] == 0
