"""The `diff` command: what it joins, what it refuses, and what it will not claim.

WHAT THESE PIN. Not that the command runs - that a set of payload shapes which
each broke an earlier design of it now behave. The first design of this command
was killed by one of them, and it is the first class below.

THE COLLISION IS THE LOAD-BEARING CASE. `_parse_temperatures` and
`_resolve_system_prompts` do not de-duplicate, so `--temperatures 0,0` produces
two rows carrying one `(model, temperature, system)` triple and two different
costs. A key built on that triple silently drops one row or matches
arbitrarily - it does not crash, it reports a confident wrong answer. So the
first class below is mutation-verified against the source: forcing `occurrence`
to 0 in `cell_keys` fails two of its tests, and that is what makes them worth
having.

WHAT IS DELIBERATELY NOT TESTED HERE: that a p-value delta is correct, because
there is none; that a threshold fires, because there is none.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import (
    EXIT_CALL_FAILED,
    EXIT_DIFF_CHANGED,
    EXIT_OK,
)
from cli_modelarium.cli import main as cli_main
from cli_modelarium.diffing import (
    PayloadError,
    assess,
    cell_keys,
    diff_payloads,
    load_payload,
    ordering_warning,
)


def _row(
    model: str = "gpt-5.5",
    *,
    prompt: str = "capital of France?",
    temperature: float = 0.0,
    system: str | None = None,
    run_index: int = 0,
    cost_usd: float | None = 0.00025125,
    latency_ms: float | None = 900.0,
    output_tokens: int = 65,
    **extra: Any,
) -> dict[str, Any]:
    row = {
        "prompt_id": "p1",
        "prompt": prompt,
        "system": system,
        "model": model,
        "provider": "openai",
        "temperature": temperature,
        "latency_ms": latency_ms,
        "ttft_ms": 810.0,
        "input_tokens": 10,
        "output_tokens": output_tokens,
        "cached_tokens": 0,
        "cost_usd": cost_usd,
        "cancelled": False,
        "output": "Paris",
        "error": None,
        "retries": 0,
        "refused": False,
        "stop_reason": None,
        "stop_category": None,
        "assertions": [],
        "run_index": run_index,
    }
    row.update(extra)
    return row


def _payload(
    rows: list[dict[str, Any]],
    *,
    command: str = "compare",
    pricing_as_of: str = "2026-09-06",
    started_at: str = "2026-09-06T12:00:00Z",
    total_runs: int = 1,
    legacy: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "0.1.9" if legacy else "0.2.0",
        "pricing_as_of": pricing_as_of,
        "total_cost_usd": sum(r["cost_usd"] or 0.0 for r in rows),
        "total_results": len(rows),
        "failed_results": 0,
        "models_without_temperature": [],
        "significance_temperature_mixed": False,
        "results": rows,
    }
    if not legacy:
        payload.update(
            {
                "started_at": started_at,
                "run_id": "11111111-2222-3333-4444-555555555555",
                "experiment_key": "0123456789abcdef",
                "invocation": {
                    "command": command,
                    "models": sorted({r["model"] for r in rows}),
                    "temperatures": [0.0],
                    "system_prompts": [None],
                },
                "refused_results": 0,
                "cancelled_results": 0,
                "total_runs": total_runs,
            }
        )
    elif total_runs > 1:
        # 0.1.9 emitted `total_runs` ONLY when runs > 1, which is what makes
        # its absence a determinate answer rather than a gap.
        payload["total_runs"] = total_runs
    payload.update(extra)
    return payload


def _write(tmp_path: Path, name: str, payload: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _run(*args: str) -> Any:
    return CliRunner().invoke(cli_main, ["diff", *args])


# ===== the collision =====


class TestTheCollisionDoesNotMisalign:
    """Two rows, one cell triple, different costs. The case that killed design 1."""

    ROWS_BEFORE = [_row(cost_usd=0.001, latency_ms=100.0), _row(cost_usd=0.002, latency_ms=200.0)]
    ROWS_AFTER = [_row(cost_usd=0.010, latency_ms=110.0), _row(cost_usd=0.020, latency_ms=220.0)]

    def test_the_premise_holds(self) -> None:
        # If a future change de-duplicates temperatures this fails, which is
        # the right place to learn it - the key below would then be moot.
        triples = {(r["model"], r["temperature"], r["system"]) for r in self.ROWS_BEFORE}
        assert len(triples) == 1, "expected a genuine cell-key collision"

    def test_each_row_keys_distinctly(self) -> None:
        keys = cell_keys(_payload(self.ROWS_BEFORE))
        assert len(keys) == 2
        assert {k.occurrence for k in keys} == {0, 1}

    def test_the_two_rows_are_matched_in_order_not_pooled(self) -> None:
        result = diff_payloads(_payload(self.ROWS_BEFORE), _payload(self.ROWS_AFTER))
        assert result.verdict.ok
        assert len(result.cells) == 2
        by_occurrence = {c.key.occurrence: c for c in result.cells}
        first = {m.name: m for m in by_occurrence[0].metrics}["cost_usd"]
        second = {m.name: m for m in by_occurrence[1].metrics}["cost_usd"]
        # 0.001 -> 0.010 and 0.002 -> 0.020. A pooled or arbitrary match would
        # pair 0.001 with 0.020, which is a confident wrong answer rather than
        # a crash - the whole reason this class exists.
        assert (first.before, first.after) == (0.001, 0.010)
        assert (second.before, second.after) == (0.002, 0.020)

    # MUTATION-VERIFIED. Forcing `occurrence` to 0 in `cell_keys` fails the two
    # tests above - the first on the key count, the second on the pairing. An
    # earlier draft of this class monkeypatched `CellKey` to prove the same
    # thing and was deleted: it asserted against the patched class rather than
    # the real one, so it passed under the very mutation it existed to catch.


# ===== direction =====


class TestArgumentOrderDecidesDirection:
    def test_swapping_inverts_every_delta(self) -> None:
        before = _payload([_row(cost_usd=0.001, latency_ms=100.0)])
        after = _payload([_row(cost_usd=0.002, latency_ms=150.0)])
        forward = {m.name: m.delta for m in diff_payloads(before, after).cells[0].metrics}
        backward = {m.name: m.delta for m in diff_payloads(after, before).cells[0].metrics}
        assert forward["cost_usd"] == pytest.approx(0.001)
        assert backward["cost_usd"] == pytest.approx(-0.001)
        assert forward["latency_ms"] == pytest.approx(50.0)
        assert backward["latency_ms"] == pytest.approx(-50.0)

    def test_warns_when_argument_order_contradicts_started_at(self) -> None:
        late = _payload([_row()], started_at="2026-09-06T12:00:09Z")
        early = _payload([_row()], started_at="2026-09-06T12:00:00Z")
        message = ordering_warning(late, early, "monday-run.json", "friday-run.json")
        assert message is not None
        assert "Swap the arguments" in message

    def test_the_warning_names_the_files_the_user_typed(self) -> None:
        # This message hardcoded "a.json" and "b.json" and shipped that way:
        # the one line about which file came first named two files that need
        # not exist. Asserting the names appear is not enough on its own - the
        # hardcoded pair has to be absent, or the literals pass again.
        late = _payload([_row()], started_at="2026-09-06T12:00:09Z")
        early = _payload([_row()], started_at="2026-09-06T12:00:00Z")
        message = ordering_warning(late, early, "monday-run.json", "friday-run.json")
        assert message is not None
        assert "monday-run.json" in message
        assert "friday-run.json" in message
        assert "a.json" not in message
        assert "b.json" not in message
        # Direction is stated with the same names, not just the timestamps.
        assert "monday-run.json -> friday-run.json" in message

    def test_silent_on_equal_timestamps(self) -> None:
        # STRICT INEQUALITY ONLY. `started_at` is second-precision, so a
        # same-second pair is ordinary - and a warning that fires on every one
        # of them is a warning users learn to skip.
        same = "2026-09-06T12:00:00Z"
        assert ordering_warning(_payload([_row()], started_at=same),
                                _payload([_row()], started_at=same)) is None

    def test_silent_when_in_agreement(self) -> None:
        early = _payload([_row()], started_at="2026-09-06T12:00:00Z")
        late = _payload([_row()], started_at="2026-09-06T12:00:09Z")
        assert ordering_warning(early, late) is None


# ===== comparability =====


class TestWhatItRefusesAndWhatItProceedsOn:
    def test_an_added_model_proceeds_and_names_the_extra_cell(self) -> None:
        before = _payload([_row("gpt-5.5")])
        after = _payload([_row("gpt-5.5"), _row("gpt-5.6-terra")])
        result = diff_payloads(before, after)
        assert result.verdict.ok, result.verdict.refusals
        assert [k.model for k in result.only_in_after] == ["gpt-5.6-terra"]
        assert result.moved

    def test_a_removed_model_proceeds_too(self) -> None:
        before = _payload([_row("gpt-5.5"), _row("gpt-5.6-terra")])
        after = _payload([_row("gpt-5.5")])
        result = diff_payloads(before, after)
        assert result.verdict.ok
        assert [k.model for k in result.only_in_before] == ["gpt-5.6-terra"]

    def test_a_changed_prompt_refuses(self) -> None:
        verdict = assess(_payload([_row()]), _payload([_row(prompt="something else")]))
        assert not verdict.ok
        assert any("prompts differ" in r for r in verdict.refusals)

    def test_a_changed_run_count_refuses(self) -> None:
        # n=1 and n=10 are not the same experiment: pooling them compares a
        # point estimate against a distribution.
        verdict = assess(_payload([_row()]), _payload([_row()], total_runs=10))
        assert not verdict.ok
        assert any("Run counts differ" in r for r in verdict.refusals)

    def test_it_does_not_decide_on_the_hash(self) -> None:
        # Same key, different prompts -> still refuses. Different key, same
        # everything else -> still proceeds. The hash is never consulted.
        same_key_different_prompt = assess(
            _payload([_row()], experiment_key="aaaa"),
            _payload([_row(prompt="other")], experiment_key="aaaa"),
        )
        assert not same_key_different_prompt.ok
        different_key_same_inputs = assess(
            _payload([_row()], experiment_key="aaaa"),
            _payload([_row()], experiment_key="bbbb"),
        )
        assert different_key_same_inputs.ok


class TestBatchPayloads:
    def test_a_batch_payload_diffs_like_any_other(self) -> None:
        before = _payload([_row(cost_usd=0.001)], command="batch")
        after = _payload([_row(cost_usd=0.002)], command="batch")
        result = diff_payloads(before, after)
        assert result.verdict.ok
        assert result.moved

    def test_batch_against_compare_refuses(self) -> None:
        verdict = assess(_payload([_row()], command="compare"),
                         _payload([_row()], command="batch"))
        assert not verdict.ok
        assert any("`compare`" in r and "`batch`" in r for r in verdict.refusals)


class TestPre020Payloads:
    """Compared, not refused - and honest about the two things it cannot see."""

    def test_it_compares_rather_than_raising(self) -> None:
        before = _payload([_row(cost_usd=0.001)], legacy=True)
        after = _payload([_row(cost_usd=0.002)])
        result = diff_payloads(before, after)
        assert result.verdict.ok
        assert len(result.cells) == 1
        assert result.moved

    def test_it_names_both_gaps(self) -> None:
        verdict = assess(_payload([_row()], legacy=True), _payload([_row()]))
        note = " ".join(verdict.notes)
        assert "which command wrote the payload" in note
        assert "judge models" in note

    def test_the_note_names_the_file_the_user_typed(self) -> None:
        # Found by running the real command: the note hardcoded "a.json" and
        # said it about a file called something else.
        verdict = assess(
            _payload([_row()], legacy=True), _payload([_row()]), "yesterday.json", "today.json"
        )
        assert any("yesterday.json predates 0.2.0" in n for n in verdict.notes)

    def test_run_count_is_read_correctly_from_a_legacy_payload(self) -> None:
        # 0.1.9 emitted `total_runs` only above one run, so absence means 1 -
        # and a legacy single-run payload must NOT refuse against a 0.2.0 one.
        assert assess(_payload([_row()], legacy=True), _payload([_row()])).ok


class TestPricingProvenance:
    def test_a_differing_pricing_as_of_is_flagged(self) -> None:
        verdict = assess(
            _payload([_row()], pricing_as_of="2026-09-06"),
            _payload([_row()], pricing_as_of="2027-01-01"),
        )
        assert verdict.ok, "a pricing change does not make a run incomparable"
        assert any("different rate tables" in w for w in verdict.warnings)

    def test_it_is_flagged_before_any_cost_number(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.001)]))
        b = _write(tmp_path, "b.json",
                   _payload([_row(cost_usd=0.002)], pricing_as_of="2027-01-01"))
        result = _run(str(a), str(b))
        assert result.exit_code == EXIT_DIFF_CHANGED, result.output
        warning_at = result.output.index("rate tables")
        cost_at = result.output.index("cost_usd")
        assert warning_at < cost_at, "the qualifier must precede the number it qualifies"


class TestTruncatedRuns:
    def test_a_cancelled_cell_is_flagged(self) -> None:
        truncated = _payload([_row()], cancelled_results=1)
        verdict = assess(_payload([_row()]), truncated, "a.json", "b.json")
        assert any("truncated run" in w for w in verdict.warnings)


# ===== arithmetic that must not break =====


class TestNullsDoNotBreakArithmetic:
    def test_a_null_cost_yields_no_delta_rather_than_a_crash(self) -> None:
        before = _payload([_row(cost_usd=None, latency_ms=None)])
        after = _payload([_row(cost_usd=0.002)])
        metrics = {m.name: m for m in diff_payloads(before, after).cells[0].metrics}
        assert metrics["cost_usd"].delta is None
        assert metrics["cost_usd"].uncomparable
        assert not metrics["cost_usd"].moved

    def test_a_zero_baseline_gives_no_percent_rather_than_infinity(self) -> None:
        # A local model costs $0.00 and `cached_tokens` is legitimately zero on
        # most rows, so this is the ordinary case rather than an edge one.
        before = _payload([_row(cost_usd=0.0)])
        after = _payload([_row(cost_usd=0.5)])
        cost = {m.name: m for m in diff_payloads(before, after).cells[0].metrics}["cost_usd"]
        assert cost.delta == pytest.approx(0.5)
        assert cost.pct is None

    def test_a_boolean_is_not_read_as_a_number(self) -> None:
        # `bool` is an `int` subclass in Python; a boolean landing in a numeric
        # column must read as "not a number", not as 0 or 1.
        before = _payload([_row(output_tokens=True)])  # type: ignore[arg-type]
        after = _payload([_row(output_tokens=5)])
        tokens = {m.name: m for m in diff_payloads(before, after).cells[0].metrics}
        assert tokens["output_tokens"].before is None


# ===== p-values =====


class TestPValuesAreReportedNotCompared:
    SIG = [{"model_a": "gpt-5.5", "model_b": "gpt-5.6-terra", "metric": "latency_ms",
            "p_value": 0.06, "p_value_corrected": 0.06}]

    def test_both_sides_are_carried_and_neither_is_subtracted(self) -> None:
        before = _payload([_row()], significance_tests=self.SIG)
        after = _payload(
            [_row()],
            significance_tests=[{**self.SIG[0], "p_value": 0.04, "p_value_corrected": 0.04}],
        )
        result = diff_payloads(before, after, "a.json", "b.json")
        assert [e["p_value"] for e in result.p_values] == [0.06, 0.04]
        assert {e["side"] for e in result.p_values} == {"a.json", "b.json"}
        # No key anywhere in the record holds a p-value difference.
        assert all("delta" not in entry for entry in result.p_values)

    def test_a_moved_p_value_alone_is_not_movement(self) -> None:
        # A p-value is a verdict about a sample, not a measurement of the
        # model. Two verdicts differing is not a change in what was measured,
        # so it must not flip the exit code on its own.
        before = _payload([_row()], significance_tests=self.SIG)
        after = _payload([_row()], significance_tests=[{**self.SIG[0], "p_value": 0.04}])
        assert not diff_payloads(before, after).moved


# ===== input handling =====


class TestUnreadableInput:
    def test_malformed_json_says_where(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('{"results": [ oops', encoding="utf-8")
        with pytest.raises(PayloadError) as exc:
            load_payload(bad)
        assert "not valid JSON" in str(exc.value)
        assert "line 1" in str(exc.value)

    def test_valid_json_that_is_not_a_payload_says_so(self, tmp_path: Path) -> None:
        other = tmp_path / "other.json"
        other.write_text('{"hello": "world"}', encoding="utf-8")
        with pytest.raises(PayloadError) as exc:
            load_payload(other)
        assert "no `results` array" in str(exc.value)

    def test_a_json_array_is_rejected_with_its_type(self, tmp_path: Path) -> None:
        arr = tmp_path / "arr.json"
        arr.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(PayloadError) as exc:
            load_payload(arr)
        assert "list" in str(exc.value)

    def test_results_holding_non_objects_is_rejected(self, tmp_path: Path) -> None:
        weird = tmp_path / "weird.json"
        weird.write_text('{"results": ["a string"]}', encoding="utf-8")
        with pytest.raises(PayloadError) as exc:
            load_payload(weird)
        assert "results[0]" in str(exc.value)

    def test_a_missing_file_exits_two_not_a_traceback(self, tmp_path: Path) -> None:
        real = _write(tmp_path, "a.json", _payload([_row()]))
        result = _run(str(real), str(tmp_path / "nope.json"))
        assert result.exit_code == EXIT_CALL_FAILED
        assert "AFTER" in result.output


# ===== exit codes =====


class TestExitCodes:
    def test_unchanged_exits_zero(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row()]))
        b = _write(tmp_path, "b.json", _payload([_row()]))
        assert _run(str(a), str(b)).exit_code == EXIT_OK

    def test_moved_exits_four(self, tmp_path: Path) -> None:
        # Its own code, not 1: exit 1 is EXIT_ASSERTION_FAILED, and a diff that
        # found movement succeeded rather than failed.
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.001)]))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.002)]))
        assert _run(str(a), str(b)).exit_code == EXIT_DIFF_CHANGED

    def test_incomparable_exits_two(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row()]))
        b = _write(tmp_path, "b.json", _payload([_row()], total_runs=5))
        result = _run(str(a), str(b))
        assert result.exit_code == EXIT_CALL_FAILED
        assert "not comparable" in result.output

    def test_an_added_cell_alone_counts_as_movement(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row("gpt-5.5")]))
        b = _write(tmp_path, "b.json", _payload([_row("gpt-5.5"), _row("gpt-5.6-terra")]))
        assert _run(str(a), str(b)).exit_code == EXIT_DIFF_CHANGED


# ===== rendering =====


class TestWhatTheSurfacesCarry:
    def test_unchanged_cells_are_hidden_and_counted(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row("gpt-5.5"), _row("gpt-5.6-terra")]))
        b = _write(tmp_path, "b.json", _payload([_row("gpt-5.5"), _row("gpt-5.6-terra")]))
        out = _run(str(a), str(b)).output
        assert "2 cells unchanged" in out
        assert "gpt-5.5" not in out

    def test_all_shows_them(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row("gpt-5.5")]))
        b = _write(tmp_path, "b.json", _payload([_row("gpt-5.5")]))
        assert "gpt-5.5" in _run(str(a), str(b), "--all").output

    def test_json_carries_every_metric_and_console_carries_three(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.001)]))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.002)]))
        payload = json.loads(_run(str(a), str(b), "--output-format", "json").output)
        assert set(payload["cells"][0]["metrics"]) == {
            "cost_usd", "latency_ms", "ttft_ms",
            "input_tokens", "output_tokens", "cached_tokens",
        }
        console = _run(str(a), str(b)).output
        assert "ttft_ms" not in console

    def test_judge_reasoning_never_reaches_the_diff_output(self, tmp_path: Path) -> None:
        # Model-generated, different every run, and attacker-influenced. It is
        # written to the source payload unconditionally; nothing here repeats it.
        canary = "REASONING-CANARY-should-not-appear"
        judged = _row(cost_usd=0.001, judges=[{"model": "j", "score": 1, "reasoning": canary}])
        a = _write(tmp_path, "a.json", _payload([judged]))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.002)]))
        for args in ((), ("--output-format", "json")):
            assert canary not in _run(str(a), str(b), *args).output

    def test_the_diff_output_is_not_a_run_and_claims_no_identity(self, tmp_path: Path) -> None:
        # 636a132 made run identity all-or-nothing and it raises on a partial
        # dict, so a synthetic `{"command": "diff"}` block would crash. The
        # output carries no identity at all rather than a plausible fake.
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.001)]))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.002)]))
        payload = json.loads(_run(str(a), str(b), "--output-format", "json").output)
        for field_name in ("run_id", "started_at", "experiment_key", "invocation"):
            assert field_name not in payload

    def test_clean_zero_counts_do_not_render(self, tmp_path: Path) -> None:
        # `failed_results`, `refused_results` and `cancelled_results` all read 0
        # on a clean run. "0 -> 0" on every pair buries the line that matters.
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.001)]))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.002)]))
        out = _run(str(a), str(b)).output
        for name in ("failed_results", "refused_results", "cancelled_results"):
            assert name not in out


# ===== the answer text =====


class TestOutputTextIsReported:
    """Whether the answer changed - the fact the numbers alone cannot carry.

    Two OPPOSITE findings used to render identically: a thinking model
    returning the SAME answer at a different token cost (ordinary, means
    nothing changed) and a model returning a DIFFERENT answer (the single most
    important thing a diff can say). Measured live on `gemini-3.8-flash`:
    byte-identical output with cost moving 11.7%.

    MUTATION-VERIFIED against the source, three ways: making
    `_output_changed` always return False fails 6 of these; dropping
    `output_changed` from `CellDiff.moved` fails 2; returning False instead
    of None for an unanswered side fails 5. Nothing here monkeypatches the
    thing it tests - an earlier class in this file did exactly that, and
    passed under the very mutation it existed to catch.
    """

    def test_identical_text_with_a_moved_cost_reads_as_unchanged(self) -> None:
        before = _payload([_row(cost_usd=0.00024375, output_tokens=62, output="Paris")])
        after = _payload([_row(cost_usd=0.00024000, output_tokens=61, output="Paris")])
        cell = diff_payloads(before, after).cells[0]
        assert cell.output_changed is False
        assert cell.moved, "the cost moved, so the cell is still a change"

    def test_changed_text_is_distinguishable_from_it(self) -> None:
        before = _payload([_row(output="Paris")])
        after = _payload([_row(output="Lyon")])
        cell = diff_payloads(before, after).cells[0]
        assert cell.output_changed is True

    def test_a_changed_answer_at_identical_metrics_is_not_hidden(self) -> None:
        # THE LOAD-BEARING CASE. Same token count, same cost, same latency -
        # a different answer. Before this, nothing moved and the
        # unchanged-cell filter dropped the row entirely.
        before = _payload([_row(output="Paris")])
        after = _payload([_row(output="Lyon")])
        result = diff_payloads(before, after)
        cell = result.cells[0]
        assert not any(m.moved for m in cell.metrics), "no metric may move in this case"
        assert cell.moved and cell.notable
        assert result.moved, "the run as a whole moved, so the exit code must say so"

    def test_it_reaches_the_console_and_the_exit_code(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row(output="Paris")]))
        b = _write(tmp_path, "b.json", _payload([_row(output="Lyon")]))
        result = _run(str(a), str(b))
        assert result.exit_code == EXIT_DIFF_CHANGED
        assert "text changed" in result.output
        assert "unchanged" not in result.output

    def test_the_unchanged_case_says_so_rather_than_staying_silent(
        self, tmp_path: Path
    ) -> None:
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.001, output="Paris")]))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.002, output="Paris")]))
        out = _run(str(a), str(b)).output
        assert "text unchanged" in out

    def test_json_carries_it_as_three_states(self, tmp_path: Path) -> None:
        a = _write(tmp_path, "a.json", _payload([_row(output="Paris")]))
        b = _write(tmp_path, "b.json", _payload([_row(output="Lyon")]))
        payload = json.loads(_run(str(a), str(b), "--output-format", "json").output)
        assert payload["cells"][0]["output_changed"] is True

    def test_no_similarity_score_is_invented(self, tmp_path: Path) -> None:
        # "94% the same" is a number the payload does not contain. The command
        # invents none, for the same reason it carries no threshold.
        a = _write(tmp_path, "a.json", _payload([_row(output="Paris is the capital")]))
        b = _write(tmp_path, "b.json", _payload([_row(output="Paris is the capitol")]))
        payload = json.loads(_run(str(a), str(b), "--output-format", "json").output)
        assert payload["cells"][0]["output_changed"] is True
        assert "similarity" not in json.dumps(payload)
        assert "distance" not in json.dumps(payload)


class TestAnUnansweredSideHasNoAnswer:
    """A refused, errored or cancelled row did not produce text to compare."""

    @pytest.mark.parametrize(
        "flags",
        [
            {"refused": True, "output": ""},
            {"error": "boom", "output": ""},
            {"cancelled": True, "output": "", "cost_usd": None},
        ],
        ids=["refused", "errored", "cancelled"],
    )
    def test_it_is_null_rather_than_unchanged(self, flags: dict[str, Any]) -> None:
        # Two empty strings are not "the same answer" - they are two absences,
        # and calling that unchanged would claim the models agreed.
        before = _payload([_row(**flags)])
        after = _payload([_row(**flags)])
        cell = diff_payloads(before, after).cells[0]
        assert cell.output_changed is None

    def test_it_does_not_count_as_movement(self) -> None:
        before = _payload([_row(refused=True, output="")])
        after = _payload([_row(refused=True, output="")])
        result = diff_payloads(before, after)
        assert not result.cells[0].moved
        assert not result.moved

    def test_but_it_is_still_shown_rather_than_filtered_away(
        self, tmp_path: Path
    ) -> None:
        # `notable` is wider than `moved`: hiding this would make "we cannot
        # tell" and "nothing happened" render identically.
        assert diff_payloads(
            _payload([_row(refused=True, output="")]),
            _payload([_row(refused=True, output="")]),
        ).cells[0].notable
        a = _write(tmp_path, "a.json", _payload([_row(refused=True, output="")]))
        b = _write(tmp_path, "b.json", _payload([_row(refused=True, output="")]))
        result = _run(str(a), str(b))
        assert result.exit_code == EXIT_OK, "nothing moved, so exit 0"
        assert "no answer on one side" in result.output

    def test_one_answered_side_and_one_not_is_also_null(self) -> None:
        before = _payload([_row(output="Paris")])
        after = _payload([_row(refused=True, output="")])
        assert diff_payloads(before, after).cells[0].output_changed is None

    def test_a_missing_output_key_does_not_crash(self) -> None:
        row = _row()
        del row["output"]
        result = diff_payloads(_payload([row]), _payload([_row(output="Paris")]))
        assert result.verdict.ok
        assert result.cells[0].output_changed is True


# ===== number formatting =====


class TestNumbersRenderConsistently:
    def test_the_totals_line_formats_like_the_table(self, tmp_path: Path) -> None:
        # Live, this printed `0.00059625 -> 0.0006187499999999999` two lines
        # under a table that formatted the same quantity to six places.
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.00027750),
                                                 _row(cost_usd=0.00031875)]))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.00037125),
                                                 _row(cost_usd=0.00024750)]))
        out = _run(str(a), str(b)).output
        assert "total_cost_usd: $0.000596 → $0.000619" in out
        assert "999999" not in out, "a binary-float tail reached the console"

    def test_a_p_value_is_formatted_too(self, tmp_path: Path) -> None:
        sig = [{"model_a": "m1", "model_b": "m2", "metric": "latency_ms",
                "p_value": 0.1 + 0.2, "p_value_corrected": 0.3}]
        a = _write(tmp_path, "a.json", _payload([_row(cost_usd=0.001)], significance_tests=sig))
        b = _write(tmp_path, "b.json", _payload([_row(cost_usd=0.002)]))
        out = _run(str(a), str(b)).output
        assert "0.30000000000000004" not in out
        assert "p=0.3" in out
