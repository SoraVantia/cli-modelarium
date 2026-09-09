"""Compare two JSON payloads the user already has, and report what moved.

WHY THIS EXISTS. 0.2.0 added `started_at`, `run_id`, `experiment_key` and
`invocation` because before them two runs of one command were indistinguishable
except by timing noise: a probe against the published 0.1.9 diffed two identical
runs and the whole difference was `latency_ms` and `ttft_ms` - with the SECOND
run faster, so even "higher latency ran earlier" ordered that pair backwards.
Those fields made two payloads joinable. This module joins them.

It reads. It does not write, store, watch or alert - `atomic_write_bytes`
widens `0600` to `0644` on rewrite, because `os.replace` swaps the inode and
the destination inherits the tmp file's mode, and a second write path would
inherit that while holding prompts and model responses.

THE JOIN KEY, and why it is not the obvious one. A key has to be UNIQUE within
a payload and STABLE across two of them. Three candidates fail differently:

    (model, temperature, system)        stable, NOT unique
    prompt_id                           unique, NOT stable
    + run_index                         stable, still NOT unique

`_parse_temperatures` and `_resolve_system_prompts` do not de-duplicate (only
the model list does, at `_resolve_dynamic_groups`), so `--temperatures 0,0` is
two cells carrying one triple and two different costs. `run_index` does not
separate them - they are two cells at ONE run, so both read 0. `prompt_id` does,
but it is a positional ordinal over the whole fan-out, so reordering
`--models a,b` to `b,a` shifts every id; `experiment_key` deliberately does not
sort the model list for exactly this reason.

The collision rows are identical in every SEMANTIC dimension - `--temperatures
0,0` asks for the same cell twice - and differ only positionally. So the key
carries exactly that much position and no more:

    (prompt, model, temperature, system, run_index, occurrence)

`occurrence` is the row's index among rows already sharing the preceding tuple,
in payload order. It is strictly better than `prompt_id` here: `prompt_id`
counts across the whole fan-out, while `occurrence` counts only WITHIN a cell
group, so reordering models reorders the groups and leaves each group's internal
sequence intact. `prompt` leads the tuple so that batch (many prompts) and
pre-0.2.0 payloads (where row text is the only cell identity available) key
correctly with no special case.

COMPARABILITY IS DECIDED ON COMPONENTS, NEVER ON `experiment_key`. Adding a
model changes that hash by design while every overlapping cell stays perfectly
comparable, so the hash answers a coarser question than the one being asked.
`invocation` carries models, temperatures, system prompts and judges as separate
lists; those are compared one at a time. A changed prompt or run count refuses
(n=1 and n=10 are not the same experiment - pooling them compares a point
estimate against a distribution); an added or removed model proceeds and the
dropped cells are named.

A PRE-0.2.0 PAYLOAD IS COMPARED, NOT REFUSED. It carries no `invocation` and no
`experiment_key`, but every row carries `prompt`, `system`, `model` and
`temperature` in plain text, so three of `invocation`'s four lists are
recoverable from row content - and the run count is determinate too, because
0.1.9 emitted `total_runs` only when `runs > 1`, so absence means one run. What
is genuinely lost is `judges` and `command`: two things, not everything. So the
verdict refuses to ASSERT comparability and names those two gaps, rather than
refusing to compare at all.

`pricing_as_of` IS READ AND FLAGGED, NEVER HASHED. It is in neither the key's
hash material nor `invocation`, so two runs across a pricing update carry the
same key, identical components and a different cost on every row. Hashing it
would fork every key on every pricing sweep and break the case the key exists
for; moving it into `methodology` would lose it on every batch payload, which
builds none. Reading it from both and saying so before any cost figure is the
only option that costs nothing and covers both commands.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The metrics a delta is computed for, in render order. Every one of them can
# arrive as `null` - `cost_usd` on a cancelled row, `latency_ms` and `ttft_ms`
# on a row that never completed - so no arithmetic here assumes a number.
METRICS: tuple[str, ...] = (
    "cost_usd",
    "latency_ms",
    "ttft_ms",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
)

# What the console shows. The rest reach JSON. Six metrics x three columns is a
# table nobody reads; these three are the ones a person re-running a comparison
# is looking for, and the JSON carries the full set for anything that filters
# itself.
CONSOLE_METRICS: tuple[str, ...] = ("cost_usd", "latency_ms", "output_tokens")

# A payload at twelve models x ten runs with 4 KB outputs measures about 0.8 MB,
# so this is roughly twelve times the largest realistic input. It exists to stop
# a stray gigabyte file, not to bound normal use - there is no streaming or
# chunking here and none is needed.
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024


class PayloadError(ValueError):
    """The file is not a payload this command can read.

    Subclasses `ValueError` so a caller that already catches one is unchanged.
    The message is rendered to the user, so it says which file and what was
    wrong rather than naming a Python type.
    """


@dataclass(frozen=True)
class CellKey:
    """One comparable cell. See the module docstring for the derivation."""

    prompt: str
    model: str
    temperature: float | None
    system: str | None
    run_index: int
    occurrence: int

    def label(self) -> str:
        """A short human label. Never includes prompt or system text.

        Both are user-supplied and can be long; the system prompt is rendered
        as an index into a legend by every other surface in this tool, and the
        prompt is identical across a comparable pair by construction (a changed
        prompt refuses). So neither belongs in a table cell.
        """
        parts = [self.model]
        if self.temperature is not None:
            parts.append(f"t={self.temperature:g}")
        if self.run_index:
            parts.append(f"run {self.run_index}")
        if self.occurrence:
            parts.append(f"#{self.occurrence + 1}")
        return " ".join(parts)


@dataclass
class MetricDelta:
    """One metric on one cell, before and after.

    `delta` and `pct` are None when either side is null, which is a real state
    rather than a gap: a cancelled row's `cost_usd` is unknown, not zero, and
    subtracting from it would invent a number.
    """

    name: str
    before: float | int | None
    after: float | int | None
    delta: float | None = None
    pct: float | None = None

    @property
    def moved(self) -> bool:
        """True only on a computable, non-zero change.

        A null on either side is NOT movement - it is an unanswerable question,
        surfaced separately as `uncomparable` so it cannot be silently read as
        "nothing happened".
        """
        return self.delta is not None and self.delta != 0

    @property
    def uncomparable(self) -> bool:
        return (self.before is None) != (self.after is None) or (
            self.before is None and self.after is None
        )


@dataclass
class CellDiff:
    """One cell, before and after: its metrics, and whether the answer changed.

    `output_changed` is a THREE-STATE fact and not a metric:

        False  both sides answered, and the text is byte-identical
        True   both sides answered, and the text differs
        None   at least one side did not answer, so the question has no answer

    It is a boolean rather than a similarity score on purpose. "94% the same"
    is an invented number, and this command invents none - the same rule that
    keeps a threshold out of the delta columns.
    """

    key: CellKey
    metrics: list[MetricDelta] = field(default_factory=list)
    output_changed: bool | None = None

    @property
    def moved(self) -> bool:
        """Something definitely changed. Drives the exit code.

        A CHANGED ANSWER COUNTS, and that is a deliberate widening of what
        "moved" means: it is no longer purely numeric. Before this, a model
        that returned a different answer at an identical token count moved
        nothing and was hidden by the unchanged-cell filter - which is the
        single most important thing a diff can report, silently dropped
        because the arithmetic happened to agree.

        `output_changed is None` does NOT count. An unanswerable question is
        not a change, exactly as a null-sided metric is not one; it is
        surfaced through `notable` instead so it cannot be read as "nothing
        happened".
        """
        return any(m.moved for m in self.metrics) or self.output_changed is True

    @property
    def notable(self) -> bool:
        """Worth showing, which is a wider set than worth counting.

        A cell where a side did not answer, or where a metric is null on one
        side, has no delta to report and still must not vanish - hiding it
        would make "we cannot tell" and "nothing changed" render identically,
        which is the failure this whole distinction exists to prevent.
        """
        return (
            self.moved
            or self.output_changed is None
            or any(m.uncomparable for m in self.metrics)
        )


@dataclass
class Verdict:
    """Whether two payloads may be compared, and everything qualifying it.

    Three levels, deliberately distinct:

        refusals  the comparison is not meaningful and must not be printed
        warnings  it is meaningful but a number in it means less than it looks
        notes     something is unknowable from these payloads
    """

    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refusals


@dataclass
class DiffResult:
    verdict: Verdict
    cells: list[CellDiff] = field(default_factory=list)
    only_in_before: list[CellKey] = field(default_factory=list)
    only_in_after: list[CellKey] = field(default_factory=list)
    # (name, before, after) for the top-level counts that actually moved. A
    # clean pair reports nothing here: `failed_results`, `refused_results` and
    # `cancelled_results` all read 0 on a clean run, and "0 -> 0" on every pair
    # is noise that buries the line that matters.
    totals: list[tuple[str, Any, Any]] = field(default_factory=list)
    # Significance and McNemar verdicts, carried side by side and NEVER
    # subtracted. A p-value is not a measurement of the model, it is a verdict
    # about one sample; two verdicts from independent runs are both valid and
    # differencing them invents a quantity neither one contains.
    p_values: list[dict[str, Any]] = field(default_factory=list)

    @property
    def moved(self) -> bool:
        return (
            any(c.moved for c in self.cells)
            or bool(self.only_in_before)
            or bool(self.only_in_after)
            or bool(self.totals)
        )


def load_payload(path: Path) -> dict[str, Any]:
    """Read one payload, or say clearly why it is not one.

    Three failures a user actually hits, each with its own message: the file is
    not JSON, the file is JSON but not this tool's output, and the file is a
    payload whose `results` is not a list of rows. A bare `KeyError` or
    `JSONDecodeError` for any of them would be a traceback where a sentence
    belongs.
    """
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PayloadError(f"{path.name} is not UTF-8 text: {exc}") from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PayloadError(
            f"{path.name} is not valid JSON: {exc.msg} at line {exc.lineno}, "
            f"column {exc.colno}."
        ) from None
    if not isinstance(payload, dict):
        raise PayloadError(
            f"{path.name} holds a {type(payload).__name__}, not a JSON object. "
            f"Pass a file written by `--output-format json`."
        )
    results = payload.get("results")
    if not isinstance(results, list):
        raise PayloadError(
            f"{path.name} has no `results` array, so it is not a "
            f"cli-modelarium payload. Pass a file written by "
            f"`--output-format json`."
        )
    for i, row in enumerate(results):
        if not isinstance(row, dict):
            raise PayloadError(
                f"{path.name}: results[{i}] is a {type(row).__name__}, not an "
                f"object. The file is JSON but not a cli-modelarium payload."
            )
    return payload


def payload_command(payload: dict[str, Any]) -> str | None:
    """Which command wrote this, or None on a pre-0.2.0 payload.

    `invocation.command` is unconditional as of 636a132, and it is the ONLY
    field that answers this. A batch payload and a compare payload share every
    row key, and `batch._parse_txt` mints `p1, p2, p3` exactly like compare's
    synthetic ids, so neither row shape nor id shape can be read as a signal.
    """
    invocation = payload.get("invocation")
    if isinstance(invocation, dict):
        command = invocation.get("command")
        if isinstance(command, str):
            return command
    return None


def payload_runs(payload: dict[str, Any]) -> int:
    """The run count, correct for both payload eras.

    `total_runs` is unconditional in 0.2.0 and was emitted only when `runs > 1`
    before it, so a missing key means one run rather than an unknown one. This
    is the one place absence is a determinate answer instead of a gap, and it
    is determinate only because the older behaviour is known.
    """
    value = payload.get("total_runs", 1)
    return value if isinstance(value, int) and value > 0 else 1


def cell_keys(payload: dict[str, Any]) -> dict[CellKey, dict[str, Any]]:
    """Key every row. See the module docstring for why the key has six parts."""
    seen: Counter[tuple[Any, ...]] = Counter()
    keyed: dict[CellKey, dict[str, Any]] = {}
    for row in payload.get("results", []):
        base = (
            row.get("prompt", ""),
            row.get("model", ""),
            row.get("temperature"),
            row.get("system"),
            row.get("run_index", 0),
        )
        occurrence = seen[base]
        seen[base] += 1
        keyed[CellKey(*base, occurrence)] = row
    return keyed


def _number(value: Any) -> float | int | None:
    """A metric's value, or None when it is not a number.

    `bool` is excluded deliberately: it is an `int` subclass in Python, and a
    boolean field arriving in a numeric column should read as "not a number"
    rather than as 0 or 1.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _delta(name: str, before_row: dict[str, Any], after_row: dict[str, Any]) -> MetricDelta:
    before = _number(before_row.get(name))
    after = _number(after_row.get(name))
    if before is None or after is None:
        return MetricDelta(name=name, before=before, after=after)
    delta = after - before
    # Percent is undefined against a zero baseline rather than infinite. A
    # local model costs $0.00 and every cloud row can legitimately read zero on
    # `cached_tokens`, so this is the ordinary case, not an edge one.
    pct = (delta / before * 100.0) if before else None
    return MetricDelta(name=name, before=before, after=after, delta=delta, pct=pct)


def _answered(row: dict[str, Any]) -> bool:
    """Did this row produce a model answer at all?

    A refused, errored or cancelled row carries an empty `output` by
    construction, so comparing two of them would compare two absences and
    report "unchanged" about a question neither side answered. `.get` on every
    field because a pre-0.2.0 row has `refused` but no `cancelled`.
    """
    return (
        row.get("error") is None
        and not row.get("refused", False)
        and not row.get("cancelled", False)
    )


def _output_changed(before_row: dict[str, Any], after_row: dict[str, Any]) -> bool | None:
    """Whether the answer text changed. None when one side did not answer.

    Byte equality, and nothing finer. A thinking model returns the same text
    at a different token count routinely - measured live on
    `gemini-3.8-flash`, byte-identical output with cost moving 11.7% - so
    "the numbers moved and the answer did not" is the ordinary reading, and a
    reader cannot reach it unless the command says so.
    """
    if not _answered(before_row) or not _answered(after_row):
        return None
    return before_row.get("output") != after_row.get("output")


def assess(
    before: dict[str, Any],
    after: dict[str, Any],
    before_name: str = "the first payload",
    after_name: str = "the second payload",
) -> Verdict:
    """Decide whether these two payloads may be compared, component by component.

    Never on `experiment_key`: adding a model changes that hash by design while
    the overlapping cells stay comparable, so it answers a coarser question than
    the one being asked. The components are compared one at a time so the
    verdict can say WHICH input moved.
    """
    verdict = Verdict()

    before_cmd, after_cmd = payload_command(before), payload_command(after)
    if before_cmd and after_cmd and before_cmd != after_cmd:
        verdict.refusals.append(
            f"One payload is from `{before_cmd}` and the other from `{after_cmd}`. "
            f"They measure different things and their rows are not comparable."
        )

    before_runs, after_runs = payload_runs(before), payload_runs(after)
    if before_runs != after_runs:
        verdict.refusals.append(
            f"Run counts differ ({before_runs} and {after_runs}). A single run is "
            f"a point estimate and a repeated run is a distribution; comparing "
            f"them would read sampling spread as a change."
        )

    # Prompts come from row content, so this check works on both payload eras.
    before_prompts = {r.get("prompt", "") for r in before.get("results", [])}
    after_prompts = {r.get("prompt", "") for r in after.get("results", [])}
    if before_prompts != after_prompts:
        verdict.refusals.append(
            "The prompts differ, so no row in one payload measures the same "
            "question as any row in the other."
        )

    before_inv, after_inv = before.get("invocation"), after.get("invocation")
    if isinstance(before_inv, dict) and isinstance(after_inv, dict):
        before_judges = list(before_inv.get("judges") or [])
        after_judges = list(after_inv.get("judges") or [])
        if before_judges != after_judges:
            verdict.warnings.append(
                f"Judge models differ ({before_judges or 'none'} and "
                f"{after_judges or 'none'}). Any score below was produced by a "
                f"different judge on each side."
            )
    else:
        # The two things a pre-0.2.0 payload genuinely cannot tell us. Named
        # rather than glossed: the comparison below is still worth having, and
        # a reader is entitled to know what it does not cover.
        missing = [
            name
            for name, payload in ((before_name, before), (after_name, after))
            if not isinstance(payload.get("invocation"), dict)
        ]
        verdict.notes.append(
            f"{' and '.join(missing)} predates 0.2.0 and records no `invocation`. "
            f"Cells are matched on row content instead, which cannot see two "
            f"things: which command wrote the payload, and which judge models ran."
        )

    before_price = before.get("pricing_as_of")
    after_price = after.get("pricing_as_of")
    if before_price != after_price:
        verdict.warnings.append(
            f"Priced from different rate tables ({before_price} and {after_price}). "
            f"Any cost difference below is partly a change in the price list "
            f"rather than in what the models did."
        )

    for name, payload in ((before_name, before), (after_name, after)):
        if payload.get("cancelled_results"):
            verdict.warnings.append(
                f"{name} is a truncated run: {payload['cancelled_results']} cell(s) "
                f"were stopped by the cost ceiling. Their cost is unknown rather "
                f"than zero, and the payload's own total does not include it."
            )

    return verdict


def ordering_warning(
    before: dict[str, Any],
    after: dict[str, Any],
    before_name: str = "the first payload",
    after_name: str = "the second payload",
) -> str | None:
    """Warn when argument order contradicts `started_at`, and only then.

    NAMED BY THE PATH THE READER TYPED, like every other message here. This
    said `a.json` and `b.json` whatever the files were called, so the one
    message about which file came first named two files that need not exist.

    Argument order decides direction: it is the only rule that is total.
    Nothing in a payload can order two runs written in the same second -
    `started_at` is second-precision and `run_id` is a uuid4, which carries no
    timestamp - and latency cannot substitute, having ordered the original
    probe's pair backwards.

    STRICT INEQUALITY ONLY. On equal timestamps "contradicts" and "agrees" are
    indistinguishable, and a warning that fires on every same-second pair is a
    warning users learn to skip past - which is what happened to the
    warn-and-proceed design this command deliberately does not have.
    """
    before_at, after_at = before.get("started_at"), after.get("started_at")
    if not isinstance(before_at, str) or not isinstance(after_at, str):
        return None
    if before_at > after_at:
        return (
            f"{before_name} started at {before_at}, after {after_name} at "
            f"{after_at}. Argument order decides direction, so this is being "
            f"read as {before_name} -> {after_name}. Swap the arguments if "
            f"that is backwards."
        )
    return None


def _p_value_rows(payload: dict[str, Any], side: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block, kind in (("significance_tests", "significance"), ("mcnemar_tests", "mcnemar")):
        for entry in payload.get(block, []) or []:
            if not isinstance(entry, dict):
                continue
            out.append(
                {
                    "side": side,
                    "kind": kind,
                    "model_a": entry.get("model_a"),
                    "model_b": entry.get("model_b"),
                    "metric": entry.get("metric"),
                    "p_value": entry.get("p_value"),
                    "p_value_corrected": entry.get("p_value_corrected"),
                }
            )
    return out


# Top-level counts worth reporting when they move. `total_runs` is absent
# because a change in it refuses above, and the identity fields are absent
# because they differ by design on every honest pair.
TOTAL_KEYS: tuple[str, ...] = (
    "total_results",
    "failed_results",
    "refused_results",
    "cancelled_results",
    "total_cost_usd",
    "total_assertions",
    "total_assertions_passed",
    "total_assertions_refused",
    "pass_rate",
)


def diff_payloads(
    before: dict[str, Any],
    after: dict[str, Any],
    before_name: str = "the first payload",
    after_name: str = "the second payload",
) -> DiffResult:
    """Join two payloads and report what moved. Pure; renders nothing."""
    result = DiffResult(verdict=assess(before, after, before_name, after_name))
    if not result.verdict.ok:
        return result

    before_cells, after_cells = cell_keys(before), cell_keys(after)

    for key, before_row in before_cells.items():
        after_row = after_cells.get(key)
        if after_row is None:
            result.only_in_before.append(key)
            continue
        result.cells.append(
            CellDiff(
                key=key,
                metrics=[_delta(m, before_row, after_row) for m in METRICS],
                output_changed=_output_changed(before_row, after_row),
            )
        )
    result.only_in_after.extend(k for k in after_cells if k not in before_cells)

    for name in TOTAL_KEYS:
        if name in before or name in after:
            b, a = before.get(name), after.get(name)
            if b != a:
                result.totals.append((name, b, a))

    result.p_values = _p_value_rows(before, before_name) + _p_value_rows(after, after_name)
    return result


def to_json(result: DiffResult, before_name: str, after_name: str) -> str:
    """The complete record: every cell, moved or not, and every qualifier.

    Written here rather than through `_format_json`, which is the compare/batch
    payload writer and would need a run identity this command has none of - and
    stamping a partial one raises, by design, since 636a132 made that block
    all-or-nothing. A diff is not a run and does not pretend to be one: it
    carries no `run_id`, no `started_at` and no `experiment_key`.

    JUDGE REASONING IS NOT CARRIED. It is model-generated text written to the
    payload unconditionally, it differs on every run, and reproducing it here
    would put attacker-influenced prose into a second file for no signal.
    """
    return json.dumps(
        {
            "before": before_name,
            "after": after_name,
            "comparable": result.verdict.ok,
            "refusals": result.verdict.refusals,
            "warnings": result.verdict.warnings,
            "notes": result.verdict.notes,
            "moved": result.moved,
            "cells": [
                {
                    "model": cell.key.model,
                    "temperature": cell.key.temperature,
                    "system": cell.key.system,
                    "run_index": cell.key.run_index,
                    "occurrence": cell.key.occurrence,
                    "moved": cell.moved,
                    # true / false / null - see CellDiff. Never a score.
                    "output_changed": cell.output_changed,
                    "metrics": {
                        m.name: {
                            "before": m.before,
                            "after": m.after,
                            "delta": m.delta,
                            "pct": m.pct,
                        }
                        for m in cell.metrics
                    },
                }
                for cell in result.cells
            ],
            "only_in_before": [k.label() for k in result.only_in_before],
            "only_in_after": [k.label() for k in result.only_in_after],
            "totals": [{"name": n, "before": b, "after": a} for n, b, a in result.totals],
            # Side by side, never subtracted. See DiffResult.p_values.
            "p_values": result.p_values,
        },
        indent=2,
    )
