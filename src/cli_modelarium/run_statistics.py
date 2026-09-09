"""Statistical analysis of multi-run comparisons.

For the --runs N feature on the compare command. Computes mean, median,
standard deviation, coefficient of variation, frequency analysis, mode
output, and output diversity from a list of StreamState results.

The run-aggregation half uses pure stdlib (statistics, collections.Counter).
The pairwise significance half (v0.1.2) delegates the math to scipy.stats
(Welch's t-test, Mann-Whitney U) and implements Cohen's d plus
Bonferroni/Holm corrections in pure stdlib.

The contract: pass a list of StreamState objects representing N runs of
the SAME (model, temperature, system_prompt) cell. Returns a RunStats
dataclass with all metrics computed only on successful runs.

Refused runs (state.refused) are counted in n_refused. They keep their timing
and cost - those were really measured and really billed - but are excluded from
everything derived from the output, because a refusal contributes an empty
string and would read as perfect consistency.

Failed runs (state.error is not None) are counted in n_failed but excluded
from all numerical statistics. n_succeeded < 2 means stdev is undefined
and returned as None.

Mode tie-breaking: when all outputs are unique, mode_output is None and
mode_count is 0. The user sees this as "no mode" rather than an arbitrary
pick - honest about high model variability.
"""

from __future__ import annotations

import math
import statistics as stdlib_statistics
import warnings
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import scipy.stats as _scipy_stats

from cli_modelarium.streaming import StreamState


@dataclass
class RunStats:
    """Aggregate statistics for N runs of the same cell.

    All numerical stats are computed only on successful runs.
    Values are None when undefined (n_succeeded < 1 for means,
    n_succeeded < 2 for stdev).
    """

    n_runs: int
    # Runs that produced an answer. A refusal is NOT one: it is billed but
    # answered nothing, and counting it here would put it in the denominator
    # of output_diversity.
    n_succeeded: int
    n_refused: int
    n_failed: int
    # Runs the cost ceiling stopped before dispatch. Its own counter because it
    # is in none of the three above: `error is None` keeps it out of n_failed
    # and `_is_cancelled` keeps it out of billed, so without this the three
    # numbers silently failed to add up to n_runs.
    n_cancelled: int

    # Timing statistics
    latency_mean_ms: float | None
    latency_median_ms: float | None
    latency_stdev_ms: float | None
    latency_cv: float | None  # Coefficient of variation = stdev/mean
    ttft_mean_ms: float | None

    # Token statistics
    output_tokens_mean: float | None
    output_tokens_stdev: float | None

    # Cost statistics
    cost_total_usd: float  # Sum across all successful runs
    cost_mean_usd: float | None  # None if no successful runs

    # Output analysis
    unique_outputs: int
    mode_output: str | None  # None when all unique (no mode)
    mode_count: int  # 0 when no mode
    output_diversity: float  # unique_outputs / n_succeeded (1.0 means all unique)


def _is_cancelled(state: object) -> bool:
    """True when the cost ceiling stopped this cell before it returned.

    Read through `getattr`: the significance and paired-sample tests drive these
    filters with duck-typed stand-ins carrying only the fields they exercise, so
    a direct attribute access would raise there rather than fail a meaningful
    assertion - the same reason `refused_arms` reads that way.
    """
    return getattr(state, "status", None) == "cancelled"


def compute_run_stats(states: list[StreamState]) -> RunStats:
    """Compute statistics from a group of N runs.

    Statistics are computed only on successful runs. Failed runs are
    counted in n_failed but don't contribute to means/stdevs.
    """
    n_runs = len(states)
    # `billed` = the call reached the provider and was charged, refusals
    # included. `answered` = it also produced an answer. Timing and cost are
    # real measurements for a refusal and belong in the first group; anything
    # derived from the output belongs in the second, because a refusal
    # contributes an empty string and would make a cell that answered nothing
    # read as maximally consistent.
    # A cancelled cell is excluded from every sample: it has `error is None`, so
    # the old filter counted it as SUCCEEDED and let its partial latency drag
    # the mean. Its cost is unknown rather than zero, so it cannot join a total
    # either.
    billed = [s for s in states if s.error is None and not _is_cancelled(s)]
    answered = [s for s in billed if not s.refused]
    failed = [s for s in states if s.error is not None]
    n_succeeded = len(answered)
    n_refused = len(billed) - len(answered)
    n_failed = len(failed)
    n_cancelled = sum(1 for s in states if s.error is None and _is_cancelled(s))

    latencies = [s.latency_ms for s in billed if s.latency_ms is not None]
    ttfts = [s.ttft_ms for s in billed if s.ttft_ms is not None]
    output_token_counts = [s.output_tokens for s in answered]
    costs = [s.cost_usd for s in billed]

    latency_mean_ms = stdlib_statistics.mean(latencies) if latencies else None
    latency_median_ms = stdlib_statistics.median(latencies) if latencies else None
    latency_stdev_ms = stdlib_statistics.stdev(latencies) if len(latencies) >= 2 else None

    if latency_mean_ms and latency_stdev_ms and latency_mean_ms > 0:
        latency_cv = latency_stdev_ms / latency_mean_ms
    else:
        latency_cv = None

    ttft_mean_ms = stdlib_statistics.mean(ttfts) if ttfts else None

    output_tokens_mean = (
        stdlib_statistics.mean(output_token_counts) if output_token_counts else None
    )
    output_tokens_stdev = (
        stdlib_statistics.stdev(output_token_counts)
        if len(output_token_counts) >= 2
        else None
    )

    cost_total_usd = sum(costs)
    cost_mean_usd = stdlib_statistics.mean(costs) if costs else None

    # Output frequency analysis (exact string matching, no normalization).
    outputs = [s.text for s in answered]
    output_counter = Counter(outputs)
    unique_outputs = len(output_counter)

    # Mode: only when at least one output appears more than once.
    # All-unique returns no mode (honest about high variability).
    if unique_outputs < n_succeeded and output_counter:
        most_common = output_counter.most_common(1)[0]
        mode_output = most_common[0]
        mode_count = most_common[1]
    else:
        mode_output = None
        mode_count = 0

    output_diversity = unique_outputs / n_succeeded if n_succeeded > 0 else 0.0

    return RunStats(
        n_runs=n_runs,
        n_succeeded=n_succeeded,
        n_refused=n_refused,
        n_failed=n_failed,
        n_cancelled=n_cancelled,
        latency_mean_ms=latency_mean_ms,
        latency_median_ms=latency_median_ms,
        latency_stdev_ms=latency_stdev_ms,
        latency_cv=latency_cv,
        ttft_mean_ms=ttft_mean_ms,
        output_tokens_mean=output_tokens_mean,
        output_tokens_stdev=output_tokens_stdev,
        cost_total_usd=cost_total_usd,
        cost_mean_usd=cost_mean_usd,
        unique_outputs=unique_outputs,
        mode_output=mode_output,
        mode_count=mode_count,
        output_diversity=output_diversity,
    )


def group_states_by_cell(
    states: list[StreamState],
) -> dict[tuple[str, float, str | None], list[StreamState]]:
    """Group N x M x T x S states by (model, temperature, system_prompt) cell.

    Returns a dict keyed by cell tuple, values are lists of states sorted
    by run_index for deterministic ordering.
    """
    groups: dict[tuple[str, float, str | None], list[StreamState]] = {}
    for state in states:
        key = (state.model, state.temperature, state.system_prompt)
        groups.setdefault(key, []).append(state)

    for key in groups:
        groups[key].sort(key=lambda s: s.run_index)

    return groups


# ===========================================================================
# v0.1.2: pairwise statistical significance testing
# ===========================================================================


@dataclass
class SignificanceResult:
    """Result of a pairwise statistical significance test.

    Produced for each pair of models when --runs N runs the same prompt
    multiple times on 2+ models. Math is delegated to scipy.stats for
    the test statistic; Cohen's d and corrections are computed locally.
    """

    model_a: str
    model_b: str
    metric: str  # "score", "latency_ms", "output_tokens", "cost_usd"
    n_a: int
    n_b: int
    # None when the model produced no usable observation at all. 0.0 is a
    # real mean a model can score, so it cannot double as "no data": a
    # judging failure used to print "avg 0.000" beside a working model and
    # read as the worst possible result rather than as an absent one.
    mean_a: float | None
    mean_b: float | None
    stdev_a: float | None
    stdev_b: float | None
    # Values: "welch_t_test", "mann_whitney_u", "paired_t_test",
    # "wilcoxon_signed_rank", "trivial", "zero_variance", or
    # "insufficient_samples". The two paired tests were emitted from the day
    # they were added and this list never learned about them; it is the only
    # place the set is written down, so it is the only place to keep in step.
    test_used: str
    test_statistic: float | None
    degrees_of_freedom: float | None  # None for Mann-Whitney / non-applicable
    p_value: float | None  # None when no test could be run
    p_value_corrected: float | None  # None when raw p_value is None
    correction_method: str  # "bonferroni", "holm", or "none"
    # The number of hypotheses the correction was applied over - the pairs that
    # produced a p-value, NOT every pair that was formed. It was the latter, so
    # a pair no test could run on still inflated every other pair's correction.
    n_comparisons: int
    effect_size: float | None  # Cohen's d (None when undefined)
    effect_size_interpretation: str  # "negligible", "small", "medium", "large", "undefined"
    threshold: float  # User-specified significance threshold
    significant_at_threshold: bool  # corrected p < threshold

    # v0.1.3 additions - all optional to preserve v0.1.2 backward compat (F2).
    # When None, the field was not requested or could not be computed.
    bootstrap_ci_low: float | None = None
    bootstrap_ci_high: float | None = None
    bootstrap_method: str | None = None  # "bca", "percentile", "basic"
    bootstrap_resamples: int | None = None
    bootstrap_seed: int | None = None
    effect_size_ci_low: float | None = None
    effect_size_ci_high: float | None = None
    # Pairs that produced no p-value and therefore spend no budget.
    # `n_comparisons + n_pairs_untestable` is the number of pairs formed.
    # Defaulted, like the fields below it, so a caller building this by hand does
    # not have to know about it and the display stubs in tests/ still construct.
    n_pairs_untestable: int = 0
    # How many of each arm's runs were declines. Defaulted so the shape
    # stays backward compatible, and so a caller building this by hand
    # does not have to know about them.
    n_refused_a: int = 0
    n_refused_b: int = 0


def cohens_d(sample_a: list[float], sample_b: list[float]) -> float | None:
    """Cohen's d effect size for two independent samples.

    Pooled standard deviation with (n_a + n_b - 2) denominator (Cohen 1988).
    Returns None when undefined (n < 2 in either group, or both groups
    have zero variance with different means).

    d = (mean_a - mean_b) / s_pooled
    s_pooled = sqrt(((n_a-1)*var_a + (n_b-1)*var_b) / (n_a + n_b - 2))
    """
    n_a = len(sample_a)
    n_b = len(sample_b)
    if n_a < 2 or n_b < 2:
        return None

    mean_a = stdlib_statistics.mean(sample_a)
    mean_b = stdlib_statistics.mean(sample_b)
    var_a = stdlib_statistics.variance(sample_a)  # Bessel's correction (n-1)
    var_b = stdlib_statistics.variance(sample_b)

    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    if pooled_var == 0:
        # Both samples constant. Equal means => d=0; different => undefined.
        return 0.0 if mean_a == mean_b else None

    return (mean_a - mean_b) / math.sqrt(pooled_var)


def cohens_d_interpretation(d: float | None) -> str:
    """Map Cohen's d magnitude to conventional bands (Cohen 1988).

    |d| < 0.2: negligible
    0.2 <= |d| < 0.5: small
    0.5 <= |d| < 0.8: medium
    0.8 <= |d|: large
    """
    if d is None:
        return "undefined"
    abs_d = abs(d)
    if abs_d < 0.2:
        return "negligible"
    if abs_d < 0.5:
        return "small"
    if abs_d < 0.8:
        return "medium"
    return "large"


def bonferroni_correct(
    p_values: list[float], n_comparisons: int | None = None
) -> list[float]:
    """Bonferroni: multiply each p-value by n, cap at 1.0.

    When n_comparisons is None, uses len(p_values).
    """
    if not p_values:
        return []
    n = n_comparisons if n_comparisons is not None else len(p_values)
    return [min(1.0, p * n) for p in p_values]


def holm_correct(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni step-down correction.

    1. Sort p-values ascending (track original indices).
    2. Raw adjusted p[i] = p_sorted[i] * (n - i)  for rank i (0-indexed).
    3. Apply monotone enforcement: running max so adjusted p-values can
       never decrease as raw p-values increase.
    4. Cap at 1.0.
    5. Return in original order.
    """
    if not p_values:
        return []
    n = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    monotone: list[tuple[int, float]] = []
    running_max = 0.0
    for rank, (orig_idx, p) in enumerate(indexed):
        raw_adj = p * (n - rank)
        running_max = max(running_max, raw_adj)
        monotone.append((orig_idx, min(1.0, running_max)))

    result = [0.0] * n
    for orig_idx, adj_p in monotone:
        result[orig_idx] = adj_p
    return result


def welch_t_test(
    sample_a: list[float], sample_b: list[float]
) -> tuple[float, float, float]:
    """Welch's t-test wrapper around scipy.stats.ttest_ind(equal_var=False).

    Returns (t_statistic, degrees_of_freedom, two_tailed_p_value).
    Raises ValueError if either sample has fewer than 2 elements.

    scipy 1.17+ exposes the Welch-Satterthwaite df via result.df; older
    scipy releases don't, so we compute it manually as a fallback.
    """
    if len(sample_a) < 2 or len(sample_b) < 2:
        raise ValueError("Welch's t-test requires at least 2 samples per group")

    result = _scipy_stats.ttest_ind(sample_a, sample_b, equal_var=False)
    df = getattr(result, "df", None)
    if df is None:
        var_a = stdlib_statistics.variance(sample_a)
        var_b = stdlib_statistics.variance(sample_b)
        n_a, n_b = len(sample_a), len(sample_b)
        num = (var_a / n_a + var_b / n_b) ** 2
        den = (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
        df = num / den if den > 0 else 0.0

    return float(result.statistic), float(df), float(result.pvalue)


def mann_whitney_u_test(
    sample_a: list[float], sample_b: list[float]
) -> tuple[float, float]:
    """Mann-Whitney U two-sided test via scipy.stats.mannwhitneyu.

    Uses the default continuity correction and method='auto' (scipy picks
    exact for small samples, asymptotic for large). Returns (U_statistic
    for sample_a, two_tailed_p_value).

    Raises ValueError if either sample is empty.
    """
    if len(sample_a) < 1 or len(sample_b) < 1:
        raise ValueError("Mann-Whitney U test requires at least 1 sample per group")
    result = _scipy_stats.mannwhitneyu(
        sample_a,
        sample_b,
        alternative="two-sided",
        use_continuity=True,
        method="auto",
    )
    return float(result.statistic), float(result.pvalue)


def _score_lookup(
    judge_results: list[Any] | None,
) -> tuple[dict[int, float], set[int]]:
    """Index judge scores by the state each verdict was tagged with.

    Returns (score_by_state_id, state_ids_whose_verdict_is_broadcast). A
    broadcast verdict is one cell's single judgement handed to every run in
    that cell, so it must contribute ONE observation per cell rather than one
    per run - see `_cell_deduped_score`.
    """
    scores_by_state_id: dict[int, float] = {}
    broadcast_state_ids: set[int] = set()
    for jr in judge_results or []:
        avg = getattr(jr, "average_score", None)
        state_id = getattr(jr, "_state_id", None)
        if avg is None or state_id is None:
            continue
        scores_by_state_id[state_id] = float(avg)
        if getattr(jr, "_broadcast", False):
            broadcast_state_ids.add(state_id)
    return scores_by_state_id, broadcast_state_ids


def _cell_deduped_score(
    state: Any,
    scores_by_state_id: dict[int, float],
    broadcast_state_ids: set[int],
    seen_cells: set[tuple[str, float, str | None]],
) -> float | None:
    """One observation per judged unit, or None if this state contributes none.

    Under per-run judging every run has its own verdict, so every successful
    run contributes. Under mode-only judging one verdict is broadcast across a
    cell, so only the first run of that cell contributes and `seen_cells`
    absorbs the rest - otherwise n counts the same judgement once per run.

    Counting by state id alone is not enough: it happens to give one per cell
    while the broadcast verdicts are a single shared object, and stops the
    moment anything copies them.
    """
    if state.error is not None or state.refused:
        # A refused cell has no candidate to score. The judge returns None for
        # it anyway; dropping it here keeps the sample honest instead of
        # relying on that.
        return None
    score = scores_by_state_id.get(id(state))
    if score is None:
        return None
    if id(state) in broadcast_state_ids:
        cell = (state.model, state.temperature, state.system_prompt)
        if cell in seen_cells:
            return None
        seen_cells.add(cell)
    return score


def _extract_metric_samples(
    states_by_model: dict[str, list[Any]],
    judge_results: list[Any] | None,
    metric: str,
) -> dict[str, list[float]]:
    """Pull per-model metric values from states (+ optional judge results).

    For metric="score" the values come from JudgeResult.average_score
    via judge_results. For all other metrics the values come from the
    StreamState fields directly. Failed states (state.error not None)
    are excluded.
    """
    samples: dict[str, list[float]] = {}

    if metric == "score":
        scores_by_state_id, broadcast_state_ids = _score_lookup(judge_results)
        for model, states in states_by_model.items():
            values: list[float] = []
            seen_cells: set[tuple[str, float, str | None]] = set()
            for s in states:
                score = _cell_deduped_score(
                    s, scores_by_state_id, broadcast_state_ids, seen_cells
                )
                if score is not None:
                    values.append(score)
            samples[model] = values
        return samples

    for model, states in states_by_model.items():
        # Latency and cost were really measured and really billed on a
        # refusal; output_tokens was not an answer, so refusals are dropped
        # from that metric only.
        billed = [s for s in states if s.error is None and not _is_cancelled(s)]
        if metric == "latency_ms":
            samples[model] = [float(s.latency_ms) for s in billed if s.latency_ms is not None]
        elif metric == "output_tokens":
            samples[model] = [float(s.output_tokens) for s in billed if not s.refused]
        elif metric == "cost_usd":
            samples[model] = [float(s.cost_usd) for s in billed]
        else:
            raise ValueError(f"Unknown metric: {metric}")
    return samples


def _count_refused(states: list[Any] | None) -> int:
    """Declines among a model's runs.

    Read with a default because the significance functions are driven by
    hand-built states in several tests, and a state without the attribute
    simply had no refusal to report.
    """
    return sum(1 for s in states or [] if getattr(s, "refused", False))


def compute_pairwise_significance(
    states_by_model: dict[str, list[Any]],
    judge_results: list[Any] | None,
    *,
    metric: str = "latency_ms",
    test: Literal[
        "welch", "mann-whitney", "paired-t", "wilcoxon-signed"
    ] = "welch",
    correction: Literal["none", "bonferroni", "holm"] = "bonferroni",
    threshold: float = 0.05,
) -> list[SignificanceResult]:
    """All pairwise significance tests between models, with correction.

    Returns one SignificanceResult per unordered (model_a, model_b) pair.
    Pair order follows insertion order in states_by_model so output is
    deterministic.

    Tests:
      - "welch": Welch's t-test (independent samples, unequal variances)
      - "mann-whitney": Mann-Whitney U (non-parametric, independent)
      - "paired-t": paired t-test (same prompts, requires run_index alignment)
      - "wilcoxon-signed": Wilcoxon signed-rank (non-parametric, paired)

    For paired tests, samples are aligned by run_index so position i on
    model A matches position i on model B by the same original run, even
    when failures are asymmetric.

    Edge cases:
      - n < 3 in either group: test_used="insufficient_samples", p=None
      - both groups zero-variance, same mean: test_used="trivial", p=1.0
      - both groups zero-variance, different means: test_used="zero_variance", p=None
      - judge_results is None and metric="score": empty samples per model
    """
    models = list(states_by_model.keys())
    if len(models) < 2:
        return []

    is_paired = test in ("paired-t", "wilcoxon-signed")
    if is_paired:
        # Per-model dict keyed by run_index; align per-pair below.
        paired_by_model = _extract_paired_metric_samples(
            states_by_model, judge_results, metric
        )
        samples_by_model: dict[str, list[float]] = {
            m: list(d.values()) for m, d in paired_by_model.items()
        }
    else:
        paired_by_model = None
        samples_by_model = _extract_metric_samples(
            states_by_model, judge_results, metric
        )

    pairs: list[tuple[str, str]] = []
    for i, model_a in enumerate(models):
        for model_b in models[i + 1 :]:
            pairs.append((model_a, model_b))

    raw_results: list[dict[str, Any]] = []
    raw_p_values: list[float] = []

    for model_a, model_b in pairs:
        if is_paired and paired_by_model is not None:
            sample_a, sample_b = _align_paired_samples(
                paired_by_model.get(model_a, {}),
                paired_by_model.get(model_b, {}),
            )
        else:
            sample_a = samples_by_model.get(model_a, [])
            sample_b = samples_by_model.get(model_b, [])
        n_a, n_b = len(sample_a), len(sample_b)

        mean_a = stdlib_statistics.mean(sample_a) if sample_a else None
        mean_b = stdlib_statistics.mean(sample_b) if sample_b else None
        stdev_a = stdlib_statistics.stdev(sample_a) if n_a >= 2 else None
        stdev_b = stdlib_statistics.stdev(sample_b) if n_b >= 2 else None

        if n_a < 3 or n_b < 3:
            raw_results.append(
                {
                    "model_a": model_a, "model_b": model_b,
                    "n_a": n_a, "n_b": n_b,
                    "mean_a": mean_a, "mean_b": mean_b,
                    "stdev_a": stdev_a, "stdev_b": stdev_b,
                    "test_used": "insufficient_samples",
                    "test_statistic": None, "degrees_of_freedom": None,
                    "p_value": None, "effect_size": None,
                }
            )
            raw_p_values.append(1.0)
            continue

        if stdev_a == 0 and stdev_b == 0:
            if mean_a == mean_b:
                raw_results.append(
                    {
                        "model_a": model_a, "model_b": model_b,
                        "n_a": n_a, "n_b": n_b,
                        "mean_a": mean_a, "mean_b": mean_b,
                        "stdev_a": 0.0, "stdev_b": 0.0,
                        "test_used": "trivial",
                        "test_statistic": 0.0, "degrees_of_freedom": None,
                        "p_value": 1.0, "effect_size": 0.0,
                    }
                )
                raw_p_values.append(1.0)
            else:
                raw_results.append(
                    {
                        "model_a": model_a, "model_b": model_b,
                        "n_a": n_a, "n_b": n_b,
                        "mean_a": mean_a, "mean_b": mean_b,
                        "stdev_a": 0.0, "stdev_b": 0.0,
                        "test_used": "zero_variance",
                        "test_statistic": None, "degrees_of_freedom": None,
                        "p_value": None, "effect_size": None,
                    }
                )
                raw_p_values.append(1.0)
            continue

        if test == "welch":
            t_stat, df, p_value = welch_t_test(sample_a, sample_b)
            test_used = "welch_t_test"
        elif test == "mann-whitney":
            t_stat, p_value = mann_whitney_u_test(sample_a, sample_b)
            df = None
            test_used = "mann_whitney_u"
        elif test == "paired-t":
            t_stat, df, p_value = paired_t_test(sample_a, sample_b)
            test_used = "paired_t_test"
        elif test == "wilcoxon-signed":
            t_stat, p_value = wilcoxon_signed_rank(sample_a, sample_b)
            df = None
            test_used = "wilcoxon_signed_rank"
        else:
            raise ValueError(f"Unknown test: {test}")

        d = cohens_d(sample_a, sample_b)
        raw_results.append(
            {
                "model_a": model_a, "model_b": model_b,
                "n_a": n_a, "n_b": n_b,
                "mean_a": mean_a, "mean_b": mean_b,
                "stdev_a": stdev_a, "stdev_b": stdev_b,
                "test_used": test_used,
                "test_statistic": t_stat,
                "degrees_of_freedom": df,
                "p_value": p_value,
                "effect_size": d,
            }
        )
        raw_p_values.append(p_value)

    # Only pairs that produced a p-value spend the multiple-comparison budget.
    # Every pair used to, because an untestable one appended a placeholder 1.0 to
    # `raw_p_values` - which inflated Bonferroni's multiplier and occupied a rank
    # slot in Holm's step-down, so every testable pair's PUBLISHED p-value paid for
    # a test that never ran. On three models where one was too small to test, a
    # difference at p=0.036168 was published as 0.108504 and reported as not
    # significant.
    #
    # The vector is FILTERED rather than a divisor redefined, and that is not a
    # style choice: `holm_correct` takes no divisor at all - it reads
    # `len(p_values)` internally - so redefining one never reaches it. Filtering
    # also makes `bonferroni_correct(non_empty, 0)`, which returns all zeros and
    # would read as every pair significant, structurally unreachable: the count and
    # the vector come from the same list, so n == 0 only when the vector is empty,
    # and the empty guard fires first.
    #
    # THE PREDICATE. Three branches above produce no test, and only two of them
    # qualify:
    #   insufficient_samples  p_value None  - no test was run
    #   zero_variance         p_value None  - no test was run (see below)
    #   trivial               p_value 1.0   - a REAL result: two constant, equal
    #                                         samples genuinely do not differ, so
    #                                         it spends the budget like any other
    #                                         tested hypothesis
    # Filtering on a `test_used` allowlist, or on the raw value being 1.0, evicts
    # `trivial` and shrinks the budget on a run where nothing was untestable.
    #
    # `zero_variance` - constant samples with DIFFERENT means - is deliberately
    # out. The difference is certain in the sample and the test is still undefined:
    # with no observed variance there is no sampling distribution, so there is no
    # p-value to correct, and charging the budget for it would make every other
    # pair pay for an inference that was never drawn. The pair stays visible
    # (`test_used` says so and the display renders it) rather than silently
    # spending someone else's budget.
    #
    # `math.isfinite` is not decoration. `paired_t_test` on identical aligned
    # samples returns NaN; `sorted()` cannot order a NaN, so its rank in Holm's
    # step-down is an artifact of list length and input order - which means a
    # filtered vector could REVERSE-flip a real verdict from significant to null,
    # the one direction that hurts someone who already published. A NaN also
    # reaches `min(1.0, running_max)` as 0.0 and publishes itself as significant.
    # For finite p-values a reverse flip is impossible.
    tested_indices = [
        i
        for i, r in enumerate(raw_results)
        if r["p_value"] is not None and math.isfinite(r["p_value"])
    ]
    tested_p_values = [raw_results[i]["p_value"] for i in tested_indices]
    n_comparisons = len(tested_indices)
    n_pairs_untestable = len(raw_results) - n_comparisons

    if correction == "bonferroni":
        tested_corrected = bonferroni_correct(tested_p_values, n_comparisons)
    elif correction == "holm":
        tested_corrected = holm_correct(tested_p_values)
    else:
        tested_corrected = list(tested_p_values)
    # Remapped by original index rather than by re-zipping: the shortened vector no
    # longer aligns with `raw_results`, and the naive alternative - leaving the
    # strict zip in place - raises a ValueError that cli.py catches, dropping the
    # ENTIRE significance block from the saved report at exit 0.
    corrected_by_index = dict(zip(tested_indices, tested_corrected, strict=True))

    final_results: list[SignificanceResult] = []
    for index, r in enumerate(raw_results):
        corrected: float | None = corrected_by_index.get(index)
        significant = corrected is not None and corrected < threshold

        final_results.append(
            SignificanceResult(
                model_a=r["model_a"],
                model_b=r["model_b"],
                metric=metric,
                n_a=r["n_a"],
                n_b=r["n_b"],
                mean_a=r["mean_a"],
                mean_b=r["mean_b"],
                stdev_a=r["stdev_a"],
                stdev_b=r["stdev_b"],
                test_used=r["test_used"],
                test_statistic=r["test_statistic"],
                degrees_of_freedom=r["degrees_of_freedom"],
                p_value=r["p_value"],
                p_value_corrected=corrected,
                correction_method=correction,
                n_comparisons=n_comparisons,
                n_pairs_untestable=n_pairs_untestable,
                effect_size=r["effect_size"],
                effect_size_interpretation=cohens_d_interpretation(r["effect_size"]),
                threshold=threshold,
                significant_at_threshold=significant,
                n_refused_a=_count_refused(states_by_model.get(r["model_a"])),
                n_refused_b=_count_refused(states_by_model.get(r["model_b"])),
            )
        )

    return final_results


# ===========================================================================
# v0.1.3: bootstrap confidence intervals + paired tests + McNemar's test
# ===========================================================================


@dataclass
class ConfidenceInterval:
    """Bootstrap confidence interval for a scalar statistic.

    Used in per-cell statistics to show uncertainty on means alongside
    the point estimate. Recorded with the parameters that produced it
    so output is reproducible given the same seed.
    """

    point_estimate: float
    ci_low: float
    ci_high: float
    ci_level: float  # e.g. 0.95
    method: str  # "bca", "percentile", "basic"
    n_resamples: int
    seed: int | None  # None = non-deterministic (warned in CLI)
    n_samples: int  # Sample size used


@dataclass
class McNemarResult:
    """McNemar's test result for a paired binary comparison.

    Used for hallucination pass/fail comparisons between models. The
    discordant counts (b, c) are the inputs that matter to the test;
    both_pass / both_fail are recorded for the 2x2 table summary.

    Implementation uses Edwards-corrected chi-square or exact binomial
    test (NOT scipy.stats.chi2_contingency, which tests independence).
    """

    model_a: str
    model_b: str
    metric: str  # e.g. "hallucination_rate"
    both_pass: int
    a_pass_b_fail: int  # discordant: b
    a_fail_b_pass: int  # discordant: c
    both_fail: int
    n_discordant: int
    # Runs where BOTH models produced a judged outcome - the denominator of the
    # two rates below, and the table's total. None rates when it is zero: there
    # is no rate over an empty denominator, and 0.0 rendered as "0% pass" beside
    # a genuinely-zero-scoring model.
    n_paired: int
    a_pass_rate: float | None
    b_pass_rate: float | None
    chi2_statistic: float | None  # None for the exact test AND when no test ran
    p_value: float | None  # None when there were no paired runs to test
    p_value_corrected: float | None
    correction_method: str  # "bonferroni", "holm", "none"
    # Pairs that produced a p-value, NOT every pair formed - the same meaning
    # the field carries on SignificanceResult, so one payload has one definition.
    n_comparisons: int
    threshold: float
    significant_at_threshold: bool
    # "exact_binomial", "edwards_chi2", "no_discordant" (paired runs, none of
    # them discordant - a real result) or "no_paired_runs" (nothing to compare).
    method: str
    # Pairs that produced no p-value and therefore spend no budget. Defaulted so
    # a caller building this by hand does not have to know about it.
    n_pairs_untestable: int = 0


def bootstrap_ci(
    samples: list[float],
    statistic: Callable[[Any], float] | None = None,
    *,
    ci_level: float = 0.95,
    method: str = "bca",
    n_resamples: int = 5000,
    seed: int | None = None,
) -> ConfidenceInterval | None:
    """Bootstrap confidence interval for a scalar statistic.

    Thin wrapper around scipy.stats.bootstrap. Default statistic is
    np.mean; default method is "bca" (bias-corrected and accelerated,
    industry standard for publication-grade CIs).

    Returns None when:
      - sample has fewer than 2 observations
      - scipy raises (degenerate data, etc.)
      - the resulting CI bounds are non-finite (zero-variance edge case)
    """
    n = len(samples)
    if n < 2:
        return None

    stat_fn: Callable[[Any], float] = statistic if statistic is not None else np.mean

    data = (samples,)
    try:
        with warnings.catch_warnings():
            # BCa on degenerate data emits a DegenerateDataWarning then
            # returns NaN bounds; we filter the NaN below.
            warnings.simplefilter("ignore")
            result = _scipy_stats.bootstrap(
                data,
                stat_fn,
                n_resamples=n_resamples,
                confidence_level=ci_level,
                method=method,
                random_state=seed,
            )
    except Exception:
        return None

    ci_low = float(result.confidence_interval.low)
    ci_high = float(result.confidence_interval.high)
    if not (math.isfinite(ci_low) and math.isfinite(ci_high)):
        return None

    point = float(stat_fn(samples))
    return ConfidenceInterval(
        point_estimate=point,
        ci_low=ci_low,
        ci_high=ci_high,
        ci_level=ci_level,
        method=method,
        n_resamples=n_resamples,
        seed=seed,
        n_samples=n,
    )


def paired_t_test(
    sample_a: list[float], sample_b: list[float]
) -> tuple[float, float, float]:
    """Paired t-test via scipy.stats.ttest_rel.

    Inputs MUST be same-length and aligned by observation. Use
    `_extract_paired_metric_samples` + `_align_paired_samples` to build
    aligned inputs from raw states_by_model.

    Returns (t_statistic, degrees_of_freedom, two_tailed_p_value).
    Raises ValueError on unequal lengths or n < 2.
    """
    if len(sample_a) != len(sample_b):
        raise ValueError(
            f"Paired t-test requires equal-length samples, "
            f"got {len(sample_a)} and {len(sample_b)}"
        )
    if len(sample_a) < 2:
        raise ValueError("Paired t-test requires at least 2 paired samples")

    result = _scipy_stats.ttest_rel(sample_a, sample_b)
    df = float(len(sample_a) - 1)
    return float(result.statistic), df, float(result.pvalue)


def wilcoxon_signed_rank(
    sample_a: list[float], sample_b: list[float]
) -> tuple[float, float]:
    """Wilcoxon signed-rank paired test via scipy.stats.wilcoxon.

    Non-parametric paired test - more robust than paired_t for non-normal
    or ordinal data. Inputs MUST be same-length and aligned by observation.

    Defaults: zero_method="wilcox" (drops zero differences),
    correction=False, alternative="two-sided".

    Returns (W_statistic, two_tailed_p_value).
    Raises ValueError on unequal lengths or n < 2.
    """
    if len(sample_a) != len(sample_b):
        raise ValueError(
            f"Wilcoxon requires equal-length samples, "
            f"got {len(sample_a)} and {len(sample_b)}"
        )
    if len(sample_a) < 2:
        raise ValueError("Wilcoxon requires at least 2 paired samples")

    with warnings.catch_warnings():
        # All-zero-differences emits a harmless RuntimeWarning.
        warnings.simplefilter("ignore", category=RuntimeWarning)
        result = _scipy_stats.wilcoxon(
            sample_a,
            sample_b,
            zero_method="wilcox",
            correction=False,
            alternative="two-sided",
        )
    return float(result.statistic), float(result.pvalue)


def mcnemar_test(
    b_only_a_pass: int,
    c_only_b_pass: int,
    *,
    exact: bool = False,
) -> tuple[float | None, float]:
    """McNemar's test for paired binary outcomes.

    Critical: do NOT implement via scipy.stats.chi2_contingency on the
    full 2x2 table - that computes a test of independence, not McNemar's.
    McNemar only uses the discordant pairs (off-diagonal entries).

    Args:
        b_only_a_pass: count where model A passes, B fails
        c_only_b_pass: count where model A fails, B passes
        exact: force the exact binomial test (recommended for n < 25)

    Returns:
        (chi2_statistic_or_None, p_value)
        chi2 is None when the exact binomial test is used.

    Algorithm:
      - n_discordant = b + c
      - n_discordant == 0  -> no test possible, returns (None, 1.0)
      - exact OR n_discordant < 25 -> exact binomial test via binomtest
      - otherwise           -> Edwards continuity-corrected chi-square

    References:
      McNemar (1947); Edwards (1948) for continuity correction.
    """
    n_discordant = b_only_a_pass + c_only_b_pass
    if n_discordant == 0:
        return None, 1.0

    if exact or n_discordant < 25:
        result = _scipy_stats.binomtest(b_only_a_pass, n_discordant, p=0.5)
        return None, float(result.pvalue)

    chi2 = (abs(b_only_a_pass - c_only_b_pass) - 1) ** 2 / n_discordant
    p = float(_scipy_stats.chi2.sf(chi2, df=1))
    return float(chi2), p


# One observation's identity within a model: (temperature, system_prompt,
# run_index), with run_index None where a whole cell shares one verdict.
PairKey = tuple[float, str | None, int | None]


def _pair_key(state: Any) -> PairKey:
    """Identify one observation within a model, for pairing against another."""
    return (state.temperature, state.system_prompt, state.run_index)


def _pair_sort_key(key: PairKey) -> tuple[float, str, int]:
    """Total order over PairKey, tolerating the Nones it may carry.

    `sorted` on the raw tuples raises the moment a None meets a str or an
    int, which happens with a mix of judged and unjudged prompts.
    """
    temperature, system_prompt, run_index = key
    return (temperature, "" if system_prompt is None else system_prompt,
            -1 if run_index is None else run_index)


def _extract_paired_metric_samples(
    states_by_model: dict[str, list[Any]],
    judge_results: list[Any] | None,
    metric: str,
) -> dict[str, dict[PairKey, float]]:
    """Pull per-model metric values indexed by observation for paired tests.

    Returns {model: {PairKey: value}}. Failed states (state.error not
    None) and missing values are excluded so the caller can intersect
    keys to get genuine pairs.

    The key is the whole cell plus the run, not run_index alone: with more
    than one temperature or system prompt, run_index repeats in every cell
    and the later cells overwrote the earlier ones, so a 3-temperature x
    5-run comparison silently paired 5 observations instead of 15.

    For metric="score", values come from JudgeResult.average_score via
    the same `_state_id` linkage as `_extract_metric_samples`.
    """
    samples_by_model: dict[str, dict[PairKey, float]] = {}

    if metric == "score":
        scores_by_state_id, broadcast_state_ids = _score_lookup(judge_results)
        for model, states in states_by_model.items():
            paired: dict[PairKey, float] = {}
            seen_cells: set[tuple[str, float, str | None]] = set()
            for s in states:
                score = _cell_deduped_score(
                    s, scores_by_state_id, broadcast_state_ids, seen_cells
                )
                if score is None:
                    continue
                # run_index alone repeats in every cell, so three temperatures
                # would collapse into one entry. A broadcast verdict has no
                # single run to name, so it pairs on the cell instead - both
                # models produce the same key for the same cell either way.
                run = None if id(s) in broadcast_state_ids else s.run_index
                paired[(s.temperature, s.system_prompt, run)] = score
            samples_by_model[model] = paired
        return samples_by_model

    for model, states in states_by_model.items():
        # Same split as the independent path: refusals keep their timing and
        # cost, but are not an output sample.
        billed = [s for s in states if s.error is None and not _is_cancelled(s)]
        if metric == "latency_ms":
            samples_by_model[model] = {
                _pair_key(s): float(s.latency_ms) for s in billed if s.latency_ms is not None
            }
        elif metric == "output_tokens":
            samples_by_model[model] = {
                _pair_key(s): float(s.output_tokens) for s in billed if not s.refused
            }
        elif metric == "cost_usd":
            samples_by_model[model] = {_pair_key(s): float(s.cost_usd) for s in billed}
        else:
            raise ValueError(f"Unknown metric: {metric}")
    return samples_by_model


def _align_paired_samples(
    samples_a: dict[PairKey, float],
    samples_b: dict[PairKey, float],
) -> tuple[list[float], list[float]]:
    """Intersect on observation key, return aligned (a, b) lists.

    Position i in the output pair is the same (temperature, system prompt,
    run) on both models, so paired_t_test / wilcoxon_signed_rank receive
    genuine pairs even when failures were asymmetric.
    """
    common = sorted(samples_a.keys() & samples_b.keys(), key=_pair_sort_key)
    aligned_a = [samples_a[k] for k in common]
    aligned_b = [samples_b[k] for k in common]
    return aligned_a, aligned_b


def _bootstrap_mean(
    samples: list[float],
    *,
    ci_level: float,
    method: str,
    n_resamples: int,
    seed: int | None,
) -> tuple[float | None, float | None]:
    """Convenience for bootstrap CI on a mean - returns (low, high) or (None, None)."""
    ci = bootstrap_ci(
        samples,
        statistic=np.mean,
        ci_level=ci_level,
        method=method,
        n_resamples=n_resamples,
        seed=seed,
    )
    if ci is None:
        return None, None
    return ci.ci_low, ci.ci_high


def compute_stats_with_cis(
    states_by_model: dict[str, list[Any]],
    judge_results: list[Any] | None,
    *,
    ci_level: float = 0.95,
    ci_method: str = "bca",
    n_resamples: int = 5000,
    seed: int | None = None,
) -> dict[tuple[str, float, str | None], dict[str, ConfidenceInterval | None]]:
    """Compute bootstrap CIs on per-CELL metric means.

    Returns {(model, temperature, system): {metric_name: ConfidenceInterval |
    None}} for the four base metrics (latency_ms, output_tokens, cost_usd, plus
    score when judge_results provided).

    Keyed by cell, not by model, because that is the grain the per-cell record
    uses. Pooling a model's cells produced an interval whose width was the
    spread BETWEEN cells rather than sampling error, and stamping it onto every
    cell published a 95% interval that contained neither mean it labelled. The
    tuple is the same one `group_states_by_cell` builds, so it matches the
    record's key exactly.

    Takes the per-model grouping the caller already has and regroups here, so
    no call site needs to know.
    """
    out: dict[tuple[str, float, str | None], dict[str, ConfidenceInterval | None]] = {}
    metrics = ["latency_ms", "output_tokens", "cost_usd"]
    if judge_results:
        metrics.append("score")

    states_by_cell: dict[tuple[str, float, str | None], list[Any]] = {}
    for model_states in states_by_model.values():
        for state in model_states:
            states_by_cell.setdefault(
                (state.model, state.temperature, state.system_prompt), []
            ).append(state)

    for metric in metrics:
        samples_by_cell = _extract_metric_samples(states_by_cell, judge_results, metric)
        for cell, samples in samples_by_cell.items():
            ci = bootstrap_ci(
                samples,
                statistic=np.mean,
                ci_level=ci_level,
                method=ci_method,
                n_resamples=n_resamples,
                seed=seed,
            )
            out.setdefault(cell, {})[metric] = ci
    return out


def compute_mcnemar_pairwise(
    states_by_model: dict[str, list[Any]],
    judge_by_state_id: dict[int, Any],
    *,
    correction: Literal["none", "bonferroni", "holm"] = "bonferroni",
    threshold: float = 0.05,
    metric: str = "hallucination_rate",
) -> list[McNemarResult]:
    """Pairwise McNemar's tests on hallucination pass/fail outcomes.

    "Pass" is defined as judge.aggregated_risk_level != "High". Runs where
    either model's judge result is missing (or the model failed or declined) are
    genuinely skipped for that pair. Intersection on `_pair_key` - the whole
    observation - gives the set of paired runs used for the 2x2 table.

    The key was `run_index` alone, which is not an observation: with more than
    one temperature or system prompt it repeats in every cell, so later cells
    OVERWROTE earlier ones and the "skipped" promise above was false - a run
    skipped in one cell had its slot refilled from another. A two-temperature,
    five-run comparison put twenty observations in and tabulated five, and the
    published pass rate was whichever cell happened to be written last: the same
    data reported 0% or 100% for a model that passed 50%.

    Returns one McNemarResult per unordered (model_a, model_b) pair.
    """
    models = list(states_by_model.keys())
    if len(models) < 2:
        return []

    # Build per-model {observation: pass_bool} using state_id -> judge lookup.
    # `_pair_key` is (temperature, system_prompt, run_index) - the same key
    # `_extract_paired_metric_samples` uses for this exact collision. It is NOT
    # the cell tuple `group_states_by_cell` builds: that one names a cell and
    # includes the model, while this one names one observation WITHIN a model so
    # two models' observations can be intersected. Merging them would be wrong.
    #
    # There is no broadcast-verdict handling here and none is needed: this
    # function runs only under `hallucination_config is not None` (cli.py), and
    # mode-only judging - the only thing that broadcasts one verdict across a
    # cell - runs only when that config is None. The two are mutually exclusive.
    # If those paths are ever joined, this key would count one broadcast verdict
    # once per run and would need the same `_broadcast` guard the paired
    # extractor carries.
    outcomes_by_model: dict[str, dict[PairKey, bool]] = {}
    for model, states in states_by_model.items():
        m: dict[PairKey, bool] = {}
        for s in states:
            if s.error is not None or s.refused:
                # A refusal is neither a hallucination pass nor a fail.
                continue
            jr = judge_by_state_id.get(id(s))
            if jr is None or not getattr(jr, "judges", None):
                continue
            risk = getattr(jr, "aggregated_risk_level", None)
            if risk is None:
                continue
            m[_pair_key(s)] = risk != "High"
        outcomes_by_model[model] = m

    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(models):
        for b in models[i + 1 :]:
            pairs.append((a, b))

    raw: list[dict[str, Any]] = []
    for a, b in pairs:
        outcomes_a = outcomes_by_model.get(a, {})
        outcomes_b = outcomes_by_model.get(b, {})
        common = sorted(
            set(outcomes_a.keys()) & set(outcomes_b.keys()), key=_pair_sort_key
        )

        both_pass = a_pass_b_fail = a_fail_b_pass = both_fail = 0
        for idx in common:
            pa, pb = outcomes_a[idx], outcomes_b[idx]
            if pa and pb:
                both_pass += 1
            elif pa and not pb:
                a_pass_b_fail += 1
            elif not pa and pb:
                a_fail_b_pass += 1
            else:
                both_fail += 1

        n_paired = len(common)
        n_discordant = a_pass_b_fail + a_fail_b_pass

        if n_paired == 0:
            # Nothing was compared. This used to run the test anyway and publish
            # `p_value=1.0` over an empty table beside `0%` pass rates - the same
            # shape a genuinely tested pair takes. `no_discordant` could not tell
            # it apart either: that label also covers ten paired runs the models
            # agreed on, which is a real result.
            chi2_stat, p_value = None, None
            a_pass_rate = b_pass_rate = None
            method_label = "no_paired_runs"
        else:
            a_pass_rate = (both_pass + a_pass_b_fail) / n_paired
            b_pass_rate = (both_pass + a_fail_b_pass) / n_paired
            chi2_stat, p_value = mcnemar_test(a_pass_b_fail, a_fail_b_pass)
            method_label = (
                "no_discordant"
                if n_discordant == 0
                else "exact_binomial"
                if n_discordant < 25
                else "edwards_chi2"
            )

        raw.append(
            {
                "model_a": a,
                "model_b": b,
                "metric": metric,
                "both_pass": both_pass,
                "a_pass_b_fail": a_pass_b_fail,
                "a_fail_b_pass": a_fail_b_pass,
                "both_fail": both_fail,
                "n_discordant": n_discordant,
                "n_paired": n_paired,
                "a_pass_rate": a_pass_rate,
                "b_pass_rate": b_pass_rate,
                "chi2_statistic": chi2_stat,
                "p_value": p_value,
                "method": method_label,
            }
        )

    # Only pairs that were actually compared spend the multiple-comparison budget,
    # so `n_comparisons` means the same thing here as it does on
    # SignificanceResult: pairs tested, not pairs formed. Every pair used to
    # contribute - a pair with no paired runs pushed a placeholder 1.0 into the
    # vector and inflated everyone else's correction.
    #
    # The discriminator is `n_paired == 0`, NOT a None p-value. `mcnemar_test`
    # never returns a None p-value - the None in its `(None, 1.0)` return is the
    # chi2 slot - so filtering on that would remove exactly zero rows. It is only
    # None here because the branch above declines to call it at all.
    tested_indices = [i for i, r in enumerate(raw) if r["p_value"] is not None]
    tested_p_values = [raw[i]["p_value"] for i in tested_indices]
    n_comparisons = len(tested_indices)
    n_pairs_untestable = len(raw) - n_comparisons

    if correction == "bonferroni":
        tested_corrected = bonferroni_correct(tested_p_values, n_comparisons)
    elif correction == "holm":
        tested_corrected = holm_correct(tested_p_values)
    else:
        tested_corrected = list(tested_p_values)
    corrected_by_index = dict(zip(tested_indices, tested_corrected, strict=True))

    results: list[McNemarResult] = []
    for index, r in enumerate(raw):
        corrected_p: float | None = corrected_by_index.get(index)
        sig = corrected_p is not None and corrected_p < threshold
        results.append(
            McNemarResult(
                model_a=r["model_a"],
                model_b=r["model_b"],
                metric=r["metric"],
                both_pass=r["both_pass"],
                a_pass_b_fail=r["a_pass_b_fail"],
                a_fail_b_pass=r["a_fail_b_pass"],
                both_fail=r["both_fail"],
                n_discordant=r["n_discordant"],
                n_paired=r["n_paired"],
                a_pass_rate=r["a_pass_rate"],
                b_pass_rate=r["b_pass_rate"],
                chi2_statistic=r["chi2_statistic"],
                p_value=r["p_value"],
                p_value_corrected=corrected_p,
                correction_method=correction,
                n_comparisons=n_comparisons,
                n_pairs_untestable=n_pairs_untestable,
                threshold=threshold,
                significant_at_threshold=sig,
                method=r["method"],
            )
        )
    return results


def compute_significance_with_ci(
    states_by_model: dict[str, list[Any]],
    judge_results: list[Any] | None,
    *,
    metric: str = "latency_ms",
    test: Literal[
        "welch", "mann-whitney", "paired-t", "wilcoxon-signed"
    ] = "welch",
    correction: Literal["none", "bonferroni", "holm"] = "bonferroni",
    threshold: float = 0.05,
    compute_ci: bool = True,
    ci_level: float = 0.95,
    ci_method: str = "bca",
    n_resamples: int = 5000,
    seed: int | None = None,
) -> list[SignificanceResult]:
    """compute_pairwise_significance + optional bootstrap CIs on Cohen's d.

    When compute_ci is True, attaches a bootstrap CI on the effect size
    (Cohen's d) to each result via paired bootstrap of the d statistic.
    For paired tests the bootstrap samples paired observations; for
    independent tests it bootstraps both samples independently and
    recomputes d each resample.
    """
    results = compute_pairwise_significance(
        states_by_model,
        judge_results,
        metric=metric,
        test=test,
        correction=correction,
        threshold=threshold,
    )

    if not compute_ci or not results:
        return results

    is_paired = test in ("paired-t", "wilcoxon-signed")
    if is_paired:
        paired_by_model = _extract_paired_metric_samples(
            states_by_model, judge_results, metric
        )
    else:
        samples_by_model = _extract_metric_samples(
            states_by_model, judge_results, metric
        )

    rng = np.random.default_rng(seed)

    for sr in results:
        if sr.effect_size is None or sr.test_used in (
            "insufficient_samples",
            "zero_variance",
            "trivial",
        ):
            continue

        if is_paired:
            aligned_a, aligned_b = _align_paired_samples(
                paired_by_model.get(sr.model_a, {}),
                paired_by_model.get(sr.model_b, {}),
            )
            n_pairs = len(aligned_a)
            if n_pairs < 2:
                continue
            arr_a = np.asarray(aligned_a, dtype=float)
            arr_b = np.asarray(aligned_b, dtype=float)
            ds: list[float] = []
            for _ in range(n_resamples):
                idx = rng.integers(0, n_pairs, n_pairs)
                d = _cohens_d_numpy(arr_a[idx], arr_b[idx])
                if d is not None:
                    ds.append(d)
        else:
            arr_a = np.asarray(samples_by_model.get(sr.model_a, []), dtype=float)
            arr_b = np.asarray(samples_by_model.get(sr.model_b, []), dtype=float)
            if len(arr_a) < 2 or len(arr_b) < 2:
                continue
            ds = []
            for _ in range(n_resamples):
                ia = rng.integers(0, len(arr_a), len(arr_a))
                ib = rng.integers(0, len(arr_b), len(arr_b))
                d = _cohens_d_numpy(arr_a[ia], arr_b[ib])
                if d is not None:
                    ds.append(d)

        if len(ds) < 2:
            continue
        alpha = 1.0 - ci_level
        lower_pct = 100.0 * alpha / 2.0
        upper_pct = 100.0 * (1.0 - alpha / 2.0)
        lo = float(np.percentile(ds, lower_pct))
        hi = float(np.percentile(ds, upper_pct))
        if math.isfinite(lo) and math.isfinite(hi):
            sr.effect_size_ci_low = lo
            sr.effect_size_ci_high = hi
            sr.bootstrap_method = ci_method
            sr.bootstrap_resamples = n_resamples
            sr.bootstrap_seed = seed

    return results


def _cohens_d_numpy(a: np.ndarray, b: np.ndarray) -> float | None:
    """Cohen's d on numpy arrays (faster bootstrap inner loop)."""
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return None
    var_a = float(np.var(a, ddof=1))
    var_b = float(np.var(b, ddof=1))
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    if pooled_var == 0:
        return 0.0 if float(np.mean(a)) == float(np.mean(b)) else None
    return (float(np.mean(a)) - float(np.mean(b))) / math.sqrt(pooled_var)
