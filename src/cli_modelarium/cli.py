"""Click CLI entry point for Cli Modelarium."""

from __future__ import annotations

import asyncio
import functools
import math
import platform
import sys
import traceback
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import click
import httpx
import keyring.errors
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from cli_modelarium import __version__
from cli_modelarium.assertions import (
    ERROR_MARK,
    AssertionResult,
    count_assertion_totals,
    refused_results,
    run_assertions,
)
from cli_modelarium.banner import render_banner, should_show_banner
from cli_modelarium.batch import (
    ESTIMATE_INPUT_TOKENS,
    ESTIMATE_OUTPUT_TOKENS,
    MAX_PROMPTS_PER_BATCH,
    MAX_TOTAL_CALLS,
    BatchPrompt,
    build_batch_states,
    check_batch_size_limits,
    detect_output_format,
    estimate_batch_cost,
    estimate_compare_cost,
    load_batch_file,
    output_overlaps_input,
    run_batch,
)
from cli_modelarium.diffing import (
    CONSOLE_METRICS,
    MAX_PAYLOAD_BYTES,
    DiffResult,
    MetricDelta,
    PayloadError,
    diff_payloads,
    load_payload,
    ordering_warning,
    to_json,
)
from cli_modelarium.exceptions import (
    BatchSizeError,
    BatchValidationError,
    KeyNotConfiguredError,
    ModelariumError,
    OutputFormatError,
    RetiredModelError,
    UnknownModelError,
    UnknownProviderError,
)
from cli_modelarium.hallucination import (
    HALLUCINATION_TOS_EXTENSION,
    annotate_risk_levels,
    parse_hallucination_response,
    resolve_hallucination_config,
)
from cli_modelarium.io_safety import load_system_prompt, safe_input_path, split_escaped_csv
from cli_modelarium.judging import (
    DEFAULT_CRITERIA,
    JUDGE_PROMPT_TEMPLATE,
    JudgeResult,
    print_tos_disclosure,
    run_judging,
    total_judge_calls,
    total_judge_cost,
)
from cli_modelarium.models_registry import (
    all_known_providers,
    list_models_for_provider,
    parse_models_arg,
)
from cli_modelarium.output_formatters import (
    CI_CONSOLE_LABELS,
    CI_METRIC_ORDER,
    STATUS_CANCELLED,
    BatchResult,
    ci_cell_label,
    ci_prompt_indices,
    format_ci_value,
    mcnemar_pairing_caveat,
    refused_arms,
    render_markdown_to_console,
    significance_refusal_caveat,
    significance_temperature_caveat,
    state_to_result,
    status_word,
    untestable_pairs_notice,
    write_csv,
    write_json,
    write_markdown,
)
from cli_modelarium.pricing import (
    PRICING,
    RETIRED_MODELS,
    is_local_model,
    pricing_freshness_note,
    rejects_sampling_params,
)
from cli_modelarium.providers.base import BaseProvider
from cli_modelarium.providers.local_provider import LocalProvider
from cli_modelarium.run_identity import build_run_identity, utc_now_iso
from cli_modelarium.security import (
    KEY_PATTERNS,
    delete_key,
    delete_local_url,
    is_key_configured,
    load_local_url,
    redact_secrets,
    save_key,
    save_local_url,
)
from cli_modelarium.streaming import (
    DEFAULT_CONCURRENCY,
    CostLedger,
    StreamState,
    run_streaming_comparison,
)

# Lazy provider import map. Each value is `module_path:ClassName` and is
# resolved via importlib at call time so we don't pay for every SDK import
# on every CLI invocation (matters for fast `--help` and `list-models`).
PROVIDER_REGISTRY: dict[str, str] = {
    "openai": "cli_modelarium.providers.openai_provider:OpenAIProvider",
    "anthropic": "cli_modelarium.providers.anthropic_provider:AnthropicProvider",
    "google": "cli_modelarium.providers.google_provider:GoogleProvider",
    "xai": "cli_modelarium.providers.xai_provider:XAIProvider",
    "deepseek": "cli_modelarium.providers.deepseek_provider:DeepSeekProvider",
    "groq": "cli_modelarium.providers.groq_provider:GroqProvider",
    "openrouter": "cli_modelarium.providers.openrouter_provider:OpenRouterProvider",
    "mistral": "cli_modelarium.providers.mistral_provider:MistralProvider",
    "dashscope": "cli_modelarium.providers.dashscope_provider:DashScopeProvider",
    "zai": "cli_modelarium.providers.zai_provider:ZAIProvider",
    "nvidia": "cli_modelarium.providers.nvidia_provider:NVIDIAProvider",
    "moonshot": "cli_modelarium.providers.moonshot_provider:MoonshotProvider",
    "local": "cli_modelarium.providers.local_provider:LocalProvider",
}

# Exit codes used across the CLI.
EXIT_OK = 0
EXIT_ASSERTION_FAILED = 1  # batch mode: at least one assertion failed
EXIT_CALL_FAILED = 2
# The cost ceiling stopped the run. Its own code rather than folding into 2:
# every other route to 2 - a usage error, a missing key, an unknown model, the
# pre-flight refusal - has nothing run and nothing spent, and the remedy is to
# fix the command. A cost abort is the opposite. The run partly succeeded, money
# was spent, and a real artifact is on disk; the remedy is to accept the partial
# data or raise the ceiling. A CI job routing 2 to "the author typed something
# wrong" would misroute it.
EXIT_COST_CEILING = 3
# Interrupted by SIGINT. 128 + 2 is the POSIX convention, and the point is
# that it is NOT 1: exit 1 is EXIT_ASSERTION_FAILED, so a run killed by a CI
# timeout used to report the code meaning "an assertion did not pass".
#
# The partial run is deliberately NOT published, which is the opposite of
# what the cost ceiling does, and the difference is real rather than an
# oversight. The ceiling stops BETWEEN cells: it lets every in-flight call
# finish, so the states it publishes are complete and their costs are known.
# SIGINT lands wherever it lands, including mid-stream - and usage is read
# inside the provider's chunk loop, so an interrupted cell has no usage and
# `mark_error` leaves `cost_usd` at 0.0. Writing that file would under-report
# what was actually spent, which is the failure the truncated-run design
# exists to avoid. Publishing on SIGINT is worth doing only once an
# interrupted cell can say its cost is unknown rather than zero.
EXIT_INTERRUPTED = 130
# `diff` found a difference. Its own code, and NOT one of the four above,
# because every one of those means something went wrong: 1 is an assertion
# failure, 2 is a run that could not complete, 3 is a spend abort. A diff that
# reports movement did none of those - it succeeded, and what it found is a
# true fact about two files. Reusing 1 would repeat exactly the misrouting that
# earned EXIT_INTERRUPTED its own code, with a CI job reading "something moved"
# as "an assertion did not pass".
#
# `diff` still exits 2 when it cannot compare at all - a malformed file, a file
# that is not a payload, a pair whose prompts or run counts differ. That is
# "the run could not complete", which is what 2 already means.
EXIT_DIFF_CHANGED = 4

class FiniteFloatRange(click.FloatRange):
    """A `FloatRange` that also refuses NaN and the infinities.

    `click.FloatRange` accepts NaN, because every comparison with NaN is False
    and so neither bound ever trips. That was not a cosmetic hole: `--max-cost
    nan` made `estimated > max_cost` always False and silently disabled the cost
    gate, and `--ci-level nan` wrote `NaN` into the JSON payload, which RFC 8259
    has no syntax for - a strict parser rejects the file, and `jq`, the recipe
    the READMEs document, silently reads it as `null`.

    The tool's own hand-rolled `not (0.0 <= x <= 1.0)` check on `--min-pass-rate`
    was already immune for the same reason click's is not, which is what this is
    modelled on. Applied to every FloatRange flag rather than to the ones that
    were reported.
    """

    name = "finite float"

    def convert(self, value, param, ctx):  # type: ignore[no-untyped-def]
        converted = super().convert(value, param, ctx)
        if not math.isfinite(converted):
            self.fail(f"{value!r} is not a finite number.", param, ctx)
        return converted


# `emoji=False` because escaping cannot reach this one. Rich substitutes
# `:word:` shortcodes AFTER markup parsing, and `escape` never touches a colon,
# so a model id or an answer containing `:free:` rendered as an emoji however
# well it was escaped. Set on the Console rather than per-print: the per-print
# kwarg does not reach a string nested inside a Panel or a Table, and this does.
# It costs nothing here - the tool writes no shortcodes of its own, and its
# marks are literal characters rather than `:check:`-style names.
console = Console(emoji=False)

# Formats whose bytes a program parses rather than a person reads.
MACHINE_FORMATS = frozenset({"json", "csv"})


def _payload_owns_stdout(output: str | None, output_format: str | None) -> bool:
    """True when stdout carries a machine payload and nothing else may share it.

    Read from the raw option values rather than `_resolve_batch_output`, because
    the first console write in `batch` happens before that resolution runs. The
    two agree: `--output` absent means no file, and the format is whatever
    `--output-format` says.
    """
    return output is None and (output_format or "").lower() in MACHINE_FORMATS


def _stderr_console_when_piping(func: Callable) -> Callable:
    """Send a command's human output to stderr when stdout is a data pipe.

    A scope decision, not a per-site one. Ten call sites across `batch` and
    `compare` write through the module `console` - progress, panels, warnings,
    the run summary - and none of them knows the output format. Enumerating
    them has been tried and missed sites twice; rebinding the console once
    covers every site, including any added later.

    `banner.py` reaches for the same tool for the same reason: output on stderr
    physically cannot land in a stdout data pipeline.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        global console
        if not _payload_owns_stdout(kwargs.get("output"), kwargs.get("output_format")):
            return func(*args, **kwargs)
        original = console
        console = Console(stderr=True)
        try:
            return func(*args, **kwargs)
        finally:
            # Restored even on SystemExit: CliRunner invokes commands in-process,
            # so a leaked stderr console would follow into the next test.
            console = original

    return wrapper


class _DefaultCommandGroup(click.Group):
    """Routes unknown bare arguments to the `compare` subcommand.

    Lets users run `cli-modelarium "prompt" --models X` without typing the
    `compare` verb explicitly.
    """

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            if args and not args[0].startswith("-"):
                # A prompt is not a file that exists. Forgetting the `batch`
                # verb used to land here and send the FILENAME to the model as
                # a prompt - a billed call, the suite never parsed, and exit 0
                # from a command the user believed was running their gate.
                #
                # No extension check: `batch` accepts only .txt and .json, so
                # gating on the extension would narrow this to exactly the
                # cases batch would have accepted anyway, and a suite saved as
                # .yaml would still silently run as a prompt.
                if Path(args[0]).is_file():
                    raise click.UsageError(
                        f"{args[0]!r} is a file, not a prompt. "
                        f"Did you mean: cli-modelarium batch {args[0]}\n"
                        f"To send the path itself as a prompt, run it through "
                        f"the verb: cli-modelarium compare {args[0]!r}"
                    ) from None
                args.insert(0, "compare")
                return super().resolve_command(ctx, args)
            raise


@click.group(
    cls=_DefaultCommandGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(version=__version__, prog_name="cli-modelarium")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Cli Modelarium - compare LLM outputs side-by-side from your terminal."""
    if ctx.invoked_subcommand is None:
        if should_show_banner():
            render_banner()
        click.echo(ctx.get_help())


# ===== compare =====


@main.command()
@click.argument("prompt", required=True)
@click.option("--models", required=True, help="Comma-separated model IDs or group names.")
@click.option("--temperatures", default="0.0", help="Comma-separated temperatures (default: 0.0).")
@click.option("--system-prompt", help="System prompt applied to every model.")
@click.option(
    "--system-prompts",
    help=(
        "Comma-separated system prompts; the comparison fans out across them. "
        "Use \\, for a literal comma."
    ),
)
@click.option(
    "--system-prompt-file",
    type=click.Path(),
    help="Load a single system prompt from a UTF-8 file (max 1 MB).",
)
@click.option("--judge", help="Score outputs using this model as judge.")
@click.option(
    "--judges",
    help="Comma-separated panel of judges (scores averaged). Use \\, for a literal comma.",
)
@click.option(
    "--judge-criteria",
    help="Comma-separated custom scoring criteria. Use \\, for a literal comma.",
)
@click.option(
    "--judge-template",
    type=click.Path(),
    help="Load a custom judge prompt template from a UTF-8 file (max 1 MB).",
)
@click.option(
    "--include-reasoning", is_flag=True, help="Show each judge's reasoning in the output."
)
@click.option(
    "--no-judge-tos",
    is_flag=True,
    help="Suppress the judge-use ToS reminder (for CI/CD where it's been acknowledged).",
)
@click.option(
    "--check-hallucination",
    is_flag=True,
    help="Apply the hallucination detection preset. Requires --judge or --judges.",
)
@click.option(
    "--expected-facts",
    help="Comma-separated reference facts for hallucination check. Use \\, for a literal comma.",
)
@click.option(
    "--expected-facts-file",
    type=click.Path(),
    help="Load expected facts from a .txt (one per line) or .json (array of strings) file.",
)
@click.option(
    "--hallucination-template",
    type=click.Path(),
    help="Override the hallucination criteria text with a custom UTF-8 file (max 1 MB).",
)
@click.option(
    "--output",
    type=click.Path(),
    help=(
        "Write results to this file. Format inferred from extension "
        "(.csv, .json, .md). Default: render Rich table to stdout."
    ),
)
@click.option(
    "--output-format",
    type=click.Choice(["csv", "json", "markdown"], case_sensitive=False),
    help="Override the output format inferred from --output's extension (csv | json | markdown).",
)
@click.option(
    "--max-cost",
    type=FiniteFloatRange(min=0.0),
    help="Refuse to run if estimated cost exceeds this USD (excludes judge cost).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite the output file if it exists.",
)
@click.option(
    "--concurrency",
    # A minimum of 1, and deliberately no maximum. `asyncio.Semaphore(0)` is a
    # valid semaphore that never admits anyone, so 0 hung forever with nothing
    # printed; a negative value raised a bare ValueError that exited 1, the same
    # code as a failed assertion. A ceiling would refuse a working
    # configuration to prevent nothing: a Semaphore allocates no memory per
    # slot, and a value above the task count is already a no-op.
    type=click.IntRange(min=1),
    default=DEFAULT_CONCURRENCY,
    help=f"Max concurrent calls per provider (default: {DEFAULT_CONCURRENCY}).",
)
@click.option(
    "--local-url",
    help=(
        "Override the default URL for the local model server "
        "(default: http://localhost:11434/v1, Ollama)."
    ),
)
@click.option("--no-stream", is_flag=True, help="Disable live streaming display.")
@click.option(
    "--runs",
    type=click.IntRange(1, 100),
    default=1,
    show_default=True,
    help=(
        "Number of times to run each (model, temperature, system_prompt) "
        "combination. Statistical analysis shown when > 1. Range: 1-100. "
        "Cost multiplies by this value - use --max-cost for safety."
    ),
)
@click.option(
    "--show-all-runs",
    is_flag=True,
    help=(
        "Override the auto-collapse heuristic that disables the live display "
        "when --runs creates more than 12 concurrent tasks. Forces every "
        "run to render its own streaming panel."
    ),
)
@click.option(
    "--significance/--no-significance",
    default=None,
    help=(
        "Compute pairwise statistical significance tests between models. "
        "Auto-enabled when --runs > 1 with 2+ models. Use --no-significance "
        "to disable."
    ),
)
@click.option(
    "--significance-threshold",
    type=FiniteFloatRange(0.0, 1.0, min_open=True, max_open=True),
    default=0.05,
    show_default=True,
    help=(
        "P-value threshold for declaring significance. Common values: "
        "0.05 (default), 0.01 (strict), 0.001 (very strict)."
    ),
)
@click.option(
    "--significance-test",
    type=click.Choice(["welch", "mann-whitney", "paired-t", "wilcoxon-signed"]),
    default="welch",
    show_default=True,
    help=(
        "Statistical test to use. 'welch' (default) handles unequal "
        "variances. 'mann-whitney' is non-parametric (no normality "
        "assumption). 'paired-t' uses scipy.stats.ttest_rel for "
        "same-prompt paired comparisons (more statistical power). "
        "'wilcoxon-signed' is the non-parametric paired alternative."
    ),
)
@click.option(
    "--correction",
    type=click.Choice(["none", "bonferroni", "holm"]),
    default="bonferroni",
    show_default=True,
    help=(
        "Multiple comparison correction. 'bonferroni' (default) is "
        "conservative. 'holm' is less conservative while still "
        "controlling family-wise error rate. 'none' is risky with 3+ "
        "models."
    ),
)
@click.option(
    "--significance-metric",
    type=click.Choice(["score", "latency_ms", "output_tokens", "cost_usd"]),
    default=None,
    help=(
        "Metric to test for significance. Default: 'score' when --judge "
        "enabled, 'latency_ms' otherwise."
    ),
)
@click.option(
    "--confidence-intervals/--no-confidence-intervals",
    default=None,
    help=(
        "Compute bootstrap confidence intervals on per-cell means. "
        "Auto-enabled when --runs > 1. Use --no-confidence-intervals to "
        "disable."
    ),
)
@click.option(
    "--ci-level",
    type=FiniteFloatRange(0.0, 1.0, min_open=True, max_open=True),
    default=0.95,
    show_default=True,
    help="Confidence level for bootstrap CIs (e.g. 0.95 for 95% CI).",
)
@click.option(
    "--ci-method",
    type=click.Choice(["bca", "percentile", "basic"]),
    default="bca",
    show_default=True,
    help=(
        "Bootstrap CI method. 'bca' (default) is bias-corrected and "
        "accelerated - the publication-grade standard. 'percentile' is "
        "simpler but less accurate near distribution tails. 'basic' is "
        "the reverse-percentile method."
    ),
)
@click.option(
    "--bootstrap-resamples",
    type=click.IntRange(min=100),
    default=5000,
    show_default=True,
    help=(
        "Number of bootstrap resamples for CI computation. "
        "Publication standard: 5000. Faster: 1000. More accurate: 10000."
    ),
)
@click.option(
    "--bootstrap-seed",
    type=int,
    default=None,
    help=(
        "Random seed for reproducible bootstrap CIs. REQUIRED for "
        "publication-grade output - without a seed, CIs vary slightly "
        "across invocations."
    ),
)
@_stderr_console_when_piping
def compare(
    prompt: str,
    models: str,
    temperatures: str,
    system_prompt: str | None,
    system_prompts: str | None,
    system_prompt_file: str | None,
    judge: str | None,
    judges: str | None,
    judge_criteria: str | None,
    judge_template: str | None,
    include_reasoning: bool,
    no_judge_tos: bool,
    check_hallucination: bool,
    expected_facts: str | None,
    expected_facts_file: str | None,
    hallucination_template: str | None,
    output: str | None,
    output_format: str | None,
    max_cost: float | None,
    force: bool,
    concurrency: int,
    local_url: str | None,
    no_stream: bool,
    runs: int,
    show_all_runs: bool,
    significance: bool | None,
    significance_threshold: float,
    significance_test: str,
    correction: str,
    significance_metric: str | None,
    confidence_intervals: bool | None,
    ci_level: float,
    ci_method: str,
    bootstrap_resamples: int,
    bootstrap_seed: int | None,
) -> None:
    """Run a side-by-side comparison of LLMs on a single prompt."""
    # RUN START - the first statement of the body, before any resolution.
    # Everything below can block on I/O of unbounded length (a keyring unlock,
    # a local-server discovery round-trip), and `_format_json` is entered only
    # after the last provider call returns, so a timestamp taken there is a
    # finish time. Those two moments are seconds apart on a small run and
    # minutes apart on `--models all-flagship --runs 10`.
    started_at = utc_now_iso()
    try:
        model_list = parse_models_arg(models)
        if not model_list:
            raise click.UsageError("--models must include at least one model ID or group.")
        model_list = _resolve_dynamic_groups(model_list, local_url)
        temp_list = _parse_temperatures(temperatures)
        # After group expansion, so an id that arrived via `all-flagship` is
        # named even though the user never typed it.
        significance_runs = _significance_will_run(significance, runs, len(model_list))
        omitted_models, honoured_models = _mixes_temperature_handling(model_list)
        temperature_mixed = significance_runs and bool(omitted_models and honoured_models)
        _warn_temperature_conditions(
            model_list, temp_list, significance_runs=significance_runs
        )
        _warn_unpriced_models(model_list)
        system_prompt_list = _resolve_system_prompts(
            system_prompt=system_prompt,
            system_prompts=system_prompts,
            system_prompt_file=system_prompt_file,
        )
        judge_models = _resolve_judge_models(judge=judge, judges=judges)
        # Built here rather than at write time: every value below is RESOLVED,
        # so a run launched with `--models all-flagship` records the ids that
        # actually ran. Group membership is registry state and moves between
        # versions, so the group name alone would not let anyone reproduce it.
        run_identity = build_run_identity(
            command="compare",
            started_at=started_at,
            prompts=[prompt],
            models=model_list,
            temperatures=temp_list,
            system_prompts=list(system_prompt_list),
            judges=judge_models,
            runs=runs,
        )
        judge_criteria_list, judge_template_text = _resolve_judge_criteria_and_template(
            judge_criteria=judge_criteria,
            judge_template=judge_template,
        )
        # The hallucination preset overrides judge criteria + template
        # AND swaps in the hallucination response parser. None when not active.
        hallucination_config = resolve_hallucination_config(
            check_hallucination=check_hallucination,
            expected_facts=expected_facts,
            expected_facts_file=expected_facts_file,
            hallucination_template=hallucination_template,
            judge_models_present=bool(judge_models),
        )
        if hallucination_config is not None:
            judge_criteria_list = hallucination_config.criteria
            judge_template_text = hallucination_config.template
        # Validate judge models BEFORE the main comparison runs - misconfigured
        # judges should not fail late after burning money on the comparison.
        if judge_models:
            _validate_judge_models(judge_models, local_url=local_url)
    except click.UsageError:
        raise
    except (
        UnknownModelError,
        KeyNotConfiguredError,
        BatchValidationError,
        FileNotFoundError,
        ValueError,
    ) as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)

    # Resolve --output / --output-format up front so a misconfigured path
    # fails before we burn any API calls. output_path is None when the
    # caller wants the default Rich display.
    try:
        output_path, output_fmt = _resolve_output_path(output, output_format, force)
    except OutputFormatError as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)

    # --max-cost pre-flight (excludes judge cost, matching batch).
    # With --runs N, multiply the estimate by N before checking the ceiling.
    if max_cost is not None:
        per_run = estimate_compare_cost(model_list, temp_list, system_prompt_list)
        estimated_total = per_run * runs
        if estimated_total > max_cost:
            if runs > 1:
                _print_error(
                    f"Estimated cost ${estimated_total:.4f} "
                    f"(= ${per_run:.4f} x {runs} runs) exceeds --max-cost "
                    f"${max_cost:.4f}. Refusing to run."
                )
            else:
                _print_error(
                    f"Estimated cost ${estimated_total:.4f} exceeds --max-cost "
                    f"${max_cost:.4f}. Refusing to run."
                )
            sys.exit(EXIT_CALL_FAILED)

    # Print a prominent cost warning when --runs > 1 is used without
    # --max-cost, so the user is reminded that costs multiply by N.
    if runs > 1 and max_cost is None:
        per_run = estimate_compare_cost(model_list, temp_list, system_prompt_list)
        estimated_total = per_run * runs
        if estimated_total > 0:
            console.print(
                f"[yellow]Note: --runs {runs} multiplies cost. "
                f"Estimated total: ${estimated_total:.4f} "
                f"(= ${per_run:.4f} x {runs}).[/yellow]"
            )

    if judge_models and not no_judge_tos:
        print_tos_disclosure(console)
        if hallucination_config is not None:
            console.print(
                Panel(
                    HALLUCINATION_TOS_EXTENSION,
                    title="Hallucination detection",
                    border_style="yellow",
                )
            )

    def provider_factory(name: str) -> BaseProvider:
        return _get_provider_instance(name, local_url=local_url)

    # One ledger for the whole run. Judge spend counts toward the same ceiling,
    # which is a behaviour change: the pre-flight estimate never included it.
    ledger = CostLedger(max_cost)

    async def _run_all() -> tuple[list[StreamState], list[JudgeResult] | None]:
        states = await run_streaming_comparison(
            prompt=prompt,
            models=model_list,
            temperatures=temp_list,
            system_prompts=system_prompt_list,
            provider_factory=provider_factory,
            console=console,
            concurrency=concurrency,
            live_display=not no_stream,
            runs=runs,
            show_all_runs=show_all_runs,
            ledger=ledger,
        )
        jrs: list[JudgeResult] | None = None
        if judge_models:
            # Judging strategy with --runs N:
            #   * Default: mode-only - judge one canonical output per cell
            #     (cheap; answers "what does this model usually say?").
            #   * --check-hallucination: per-run - judge every run so we can
            #     compute the hallucination rate across N runs.
            #   * runs == 1: existing behavior, one judge call per state.
            if runs > 1 and hallucination_config is None:
                jrs = await _run_mode_only_judging(
                    states=states,
                    prompt=prompt,
                    judge_models=judge_models,
                    criteria=judge_criteria_list,
                    template=judge_template_text,
                    provider_factory=provider_factory,
                    concurrency=concurrency,
                    ledger=ledger,
                )
            else:
                jrs = await run_judging(
                    items=[(s, prompt) for s in states],
                    judge_models=judge_models,
                    criteria=judge_criteria_list,
                    provider_factory=provider_factory,
                    template=judge_template_text,
                    response_parser=(
                        parse_hallucination_response
                        if hallucination_config is not None
                        else None
                    ),
                    skip_self_eval=True,
                    concurrency=concurrency,
                    ledger=ledger,
                )
                if hallucination_config is not None:
                    annotate_risk_levels(jrs)
        return states, jrs

    try:
        # Single asyncio.run keeps all httpx client cleanup on one event loop,
        # so we don't get "Event loop is closed" warnings on shutdown.
        states, judge_results = asyncio.run(_run_all())
    except KeyboardInterrupt:
        _print_error("Interrupted. Nothing was written; calls already made were billed.")
        sys.exit(EXIT_INTERRUPTED)
    except KeyNotConfiguredError as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)
    except ModelariumError as e:
        _print_error(redact_secrets(str(e)))
        sys.exit(EXIT_CALL_FAILED)

    # Pairwise significance: auto-enable when runs > 1 with 2+ models,
    # unless the user explicitly opted out with --no-significance. Shared with
    # the temperature warning above so the caveat and the verdict cannot
    # disagree about whether a verdict is being produced.
    should_compute_significance = significance_runs

    # v0.1.3: bootstrap CIs auto-enable when runs > 1 (matching significance
    # pattern). User can opt out with --no-confidence-intervals.
    if confidence_intervals is None:
        should_compute_ci = runs > 1
    else:
        should_compute_ci = confidence_intervals
    # `and runs > 1` because the whole statistics block below is gated on it, so
    # at a single run nothing is attempted whatever the flag says. Without this
    # an unconditional methodology block would publish `enabled: true` with a
    # complete 5000-resample BCa configuration and a pinned seed for a bootstrap
    # that provably never ran - in a file people cite.
    should_compute_ci = should_compute_ci and runs > 1

    significance_results = None
    stats_by_cell_with_ci: dict | None = None
    mcnemar_results = None
    methodology: dict | None = None

    if runs > 1 and len(model_list) >= 1:
        # Always tag judge results with their state id so paired/score
        # extractors can match them back.
        if judge_results is not None:
            for state, jr in zip(states, judge_results, strict=True):
                jr._state_id = id(state)  # type: ignore[attr-defined]

        states_by_model: dict[str, list[StreamState]] = {}
        for state in states:
            states_by_model.setdefault(state.model, []).append(state)

        if should_compute_significance and len(model_list) >= 2:
            from cli_modelarium.run_statistics import (
                compute_significance_with_ci,
            )

            sig_metric = significance_metric
            if sig_metric is None:
                sig_metric = "score" if judge_results is not None else "latency_ms"

            try:
                significance_results = compute_significance_with_ci(
                    states_by_model,
                    judge_results,
                    metric=sig_metric,
                    test=significance_test,  # type: ignore[arg-type]
                    correction=correction,  # type: ignore[arg-type]
                    threshold=significance_threshold,
                    compute_ci=should_compute_ci,
                    ci_level=ci_level,
                    ci_method=ci_method,
                    n_resamples=bootstrap_resamples,
                    seed=bootstrap_seed,
                )
            except ValueError as e:
                console.print(
                    f"[yellow]Significance test skipped: {escape(str(e))}[/yellow]"
                )
                significance_results = None

        if should_compute_ci:
            from cli_modelarium.run_statistics import compute_stats_with_cis

            cis = compute_stats_with_cis(
                states_by_model,
                judge_results,
                ci_level=ci_level,
                ci_method=ci_method,
                n_resamples=bootstrap_resamples,
                seed=bootstrap_seed,
            )
            stats_by_cell_with_ci = _flatten_cell_cis(cis)

        if (
            hallucination_config is not None
            and len(model_list) >= 2
            and judge_results is not None
        ):
            from cli_modelarium.run_statistics import compute_mcnemar_pairwise

            judge_by_state_id = {
                id(state): jr
                for state, jr in zip(states, judge_results, strict=True)
            }
            mcnemar_results = compute_mcnemar_pairwise(
                states_by_model,
                judge_by_state_id,
                correction=correction,  # type: ignore[arg-type]
                threshold=significance_threshold,
            )


    # Recorded for reproducibility, UNCONDITIONALLY. It used to be built inside
    # the `runs > 1` block, so a single-run payload carried no methodology at
    # all and a consumer had to read that absence as "no statistics ran" -
    # indistinguishable from a version that never emitted the key. The tool,
    # scipy and Python versions are worth recording at one run too.
    #
    # COMPARE ONLY. `batch` builds no methodology and this does not give it one:
    # batch has no `--runs`, calls no `run_statistics` function and never
    # imports scipy, so a `scipy_version` there would name a library the command
    # did not load.
    import scipy as _scipy

    # `{cell: {metric: {...}}}`, and a cell whose every metric was degenerate
    # arrives as an empty inner dict, so the truth test has to reach the metric
    # level rather than stopping at the cell.
    produced_intervals = any(
        bool(metrics) for metrics in (stats_by_cell_with_ci or {}).values()
    )
    methodology = {
        "tool_version": __version__,
        # Both at PATCH precision. They are one reproducibility record and a
        # split grain makes it useless: scipy patch releases have changed
        # statistical behaviour, and so have CPython's. `python_version` was
        # major.minor while `scipy_version` was full, which recorded the
        # dependency more precisely than the interpreter running it.
        "scipy_version": _scipy.__version__,
        "python_version": platform.python_version(),
        "n_runs": runs,
        "bootstrap": {
            # ATTEMPTED, not succeeded. The bootstrap can be attempted and
            # return nothing - a zero-variance cell, or a cell whose every run
            # failed - and this field said `true` beside a payload holding no
            # interval at all. `produced_intervals` is the outcome; keep them
            # separate rather than flipping this one, which is what the seed
            # and the method describe.
            "enabled": should_compute_ci,
            "produced_intervals": produced_intervals,
            "method": ci_method if should_compute_ci else None,
            "n_resamples": bootstrap_resamples if should_compute_ci else None,
            "ci_level": ci_level if should_compute_ci else None,
            "seed": bootstrap_seed if should_compute_ci else None,
        },
        "significance": {
            "enabled": bool(significance_results),
            "test": significance_test if significance_results else None,
            "correction": correction if significance_results else None,
            "threshold": significance_threshold if significance_results else None,
        },
    }

    if output_path is not None or output_fmt is not None:
        # File or explicit-format output path: serialize via batch's writers.
        results = _states_to_compare_results(states, prompt, judge_results)
        _emit_batch_results(
            results,
            output_path=output_path,
            output_fmt=output_fmt or "markdown",
            runs=runs,
            significance_results=significance_results,
            stats_by_cell_cis=stats_by_cell_with_ci,
            mcnemar_results=mcnemar_results,
            methodology=methodology,
            models_without_temperature=_models_without_temperature(model_list),
            significance_temperature_mixed=temperature_mixed,
            run_identity=run_identity,
        )
    elif runs > 1:
        _display_results_with_runs(
            states,
            judge_results=judge_results,
            runs=runs,
            include_reasoning=include_reasoning,
            hallucination_mode=hallucination_config is not None,
            hallucination_facts=(hallucination_config.facts if hallucination_config else None),
            significance_results=significance_results,
            stats_by_cell_cis=stats_by_cell_with_ci,
            mcnemar_results=mcnemar_results,
        )
    else:
        _display_results(
            states,
            judge_results=judge_results,
            include_reasoning=include_reasoning,
            hallucination_mode=hallucination_config is not None,
            hallucination_facts=(hallucination_config.facts if hallucination_config else None),
        )

    # Checked AFTER the output is written and displayed: the user paid for the
    # cells that completed, so the artifact is published rather than discarded.
    # That is only safe because a cancelled cell is excluded from every
    # statistic and from the assertions, and is NAMED wherever it is counted -
    # the console status, the OK/R/F/C triple, `stats_by_cell` and the header
    # totals - so the file reports what was measured. That claim was false when
    # it was first written: four surfaces still read a cancelled cell as a
    # success, and this comment is the reason to keep them honest.
    if ledger.exhausted:
        _print_error(_cost_ceiling_message(ledger))
        sys.exit(EXIT_COST_CEILING)
    if any(s.error for s in states):
        sys.exit(EXIT_CALL_FAILED)
    sys.exit(EXIT_OK)


# ===== batch =====


@main.command()
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--models", required=True, help="Comma-separated model IDs or group names.")
@click.option("--temperatures", default="0.0", help="Comma-separated temperatures (default: 0.0).")
@click.option(
    "--system-prompt",
    help=(
        "System prompt applied to every prompt (per-prompt 'system' field in "
        "the input file wins for that prompt)."
    ),
)
@click.option(
    "--system-prompts",
    help=(
        "Comma-separated system prompts; the matrix fans out across them. "
        "Use \\, for a literal comma."
    ),
)
@click.option(
    "--system-prompt-file",
    type=click.Path(),
    help="Load a single system prompt from a UTF-8 file (max 1 MB).",
)
@click.option("--judge", help="Score outputs using this model as judge.")
@click.option(
    "--judges",
    help="Comma-separated panel of judges (scores averaged). Use \\, for a literal comma.",
)
@click.option(
    "--judge-criteria",
    help="Comma-separated custom scoring criteria. Use \\, for a literal comma.",
)
@click.option(
    "--judge-template",
    type=click.Path(),
    help="Load a custom judge prompt template from a UTF-8 file (max 1 MB).",
)
@click.option(
    "--include-reasoning",
    is_flag=True,
    help=(
        "Not supported on `batch` - judge reasoning is always present in JSON "
        "output. Accepted only so that passing it reports that, rather than "
        "failing as an unknown option. Use it on `compare`, where it works."
    ),
)
@click.option(
    "--no-judge-tos",
    is_flag=True,
    help="Suppress the judge-use ToS reminder (for CI/CD where it's been acknowledged).",
)
@click.option(
    "--check-hallucination",
    is_flag=True,
    help="Apply the hallucination detection preset. Requires --judge or --judges.",
)
@click.option(
    "--expected-facts",
    help="Comma-separated reference facts. Use \\, for a literal comma.",
)
@click.option(
    "--expected-facts-file",
    type=click.Path(),
    help="Load expected facts from a .txt (one per line) or .json (array of strings) file.",
)
@click.option(
    "--hallucination-template",
    type=click.Path(),
    help="Override the hallucination criteria text with a custom UTF-8 file (max 1 MB).",
)
@click.option(
    "--output",
    type=click.Path(),
    help=(
        "Output file path. Format auto-detected from extension; omit to render Markdown on stdout."
    ),
)
@click.option(
    "--output-format",
    type=click.Choice(["csv", "json", "markdown"], case_sensitive=False),
    help="Override the output format inferred from --output extension.",
)
@click.option(
    "--max-cost",
    type=FiniteFloatRange(min=0.0),
    help="Refuse to run if the estimated cost exceeds this USD (excludes judge cost).",
)
@click.option(
    "--concurrency",
    # A minimum of 1, and deliberately no maximum. `asyncio.Semaphore(0)` is a
    # valid semaphore that never admits anyone, so 0 hung forever with nothing
    # printed; a negative value raised a bare ValueError that exited 1, the same
    # code as a failed assertion. A ceiling would refuse a working
    # configuration to prevent nothing: a Semaphore allocates no memory per
    # slot, and a value above the task count is already a no-op.
    type=click.IntRange(min=1),
    default=DEFAULT_CONCURRENCY,
    help=f"Max concurrent calls per provider (default: {DEFAULT_CONCURRENCY}).",
)
@click.option("--local-url", help="Override the default URL for the local model server.")
@click.option(
    "--min-pass-rate",
    type=float,
    help=(
        "Exit 1 if assertion pass rate falls below this threshold (0.0-1.0). "
        "Default behaviour without this flag is strict: ANY assertion failure "
        "exits 1."
    ),
)
@click.option(
    "--no-assertions",
    is_flag=True,
    help=(
        "Skip assertion checks entirely. Pass/fail counts are zeroed and "
        "exit code reflects only call status."
    ),
)
@click.option(
    "--strict-assertions",
    is_flag=True,
    help=(
        "Make the default strict behaviour explicit (any assertion failure "
        "exits 1). Mutually exclusive with --min-pass-rate."
    ),
)
@click.option(
    "--no-judge",
    is_flag=True,
    help="Skip judge scoring even if --judge or --judges is configured.",
)
@click.option("--force", is_flag=True, help="Overwrite the output file if it exists.")
@click.option(
    "--force-large",
    is_flag=True,
    help=(
        f"Bypass safety caps (max {MAX_PROMPTS_PER_BATCH} prompts, "
        f"max {MAX_TOTAL_CALLS} calls)."
    ),
)
@_stderr_console_when_piping
def batch(
    file: str,
    models: str,
    temperatures: str,
    system_prompt: str | None,
    system_prompts: str | None,
    system_prompt_file: str | None,
    judge: str | None,
    judges: str | None,
    judge_criteria: str | None,
    judge_template: str | None,
    include_reasoning: bool,
    no_judge_tos: bool,
    check_hallucination: bool,
    expected_facts: str | None,
    expected_facts_file: str | None,
    hallucination_template: str | None,
    output: str | None,
    output_format: str | None,
    max_cost: float | None,
    concurrency: int,
    local_url: str | None,
    min_pass_rate: float | None,
    no_assertions: bool,
    strict_assertions: bool,
    no_judge: bool,
    force: bool,
    force_large: bool,
) -> None:
    """Run a multi-prompt batch evaluation from a file.

    The input file is parsed by extension (.txt or .json). Output format is
    inferred from --output's extension (.csv / .json / .md), or pass
    --output-format to override. Omit --output to render Markdown to stdout.

    Per-prompt system prompts: include `"system": "..."` in a JSON prompt
    object to override the command-line system prompt for that one prompt.

    Assertions (JSON input only): include `"assertions": [...]` on a prompt
    object. Exit codes: 0 = all passed, 1 = assertion failure(s) or pass
    rate below --min-pass-rate, 2 = call failure or IO error. Call failures
    win over assertion failures (2 > 1).
    """
    # RUN START, for the same reason as in `compare`: everything below this
    # line can block, and the formatter runs after the last call returns.
    started_at = utc_now_iso()
    # --strict-assertions and --min-pass-rate are alternatives; combining
    # them is ambiguous, so reject upfront.
    if strict_assertions and min_pass_rate is not None:
        raise click.UsageError("--strict-assertions and --min-pass-rate are mutually exclusive.")
    # --include-reasoning has never done anything on batch: the parameter was
    # accepted and never read, while --help advertised it. Rejected rather
    # than wired, because wiring it would put judge reasoning into markdown
    # and CSV and falsify the privacy note in nine READMEs, which says those
    # two do not carry it. Rejected rather than removed, because a documented
    # flag disappearing into "no such option" is the worse message.
    if include_reasoning:
        raise click.UsageError(
            "--include-reasoning is not supported on `batch`. Judge reasoning "
            "is always present in JSON output (`--output-format json`), so "
            "there is nothing for the flag to switch on. It works on `compare`."
        )
    # --no-assertions disarms the gate the other two flags set up, so asking
    # for both is self-contradictory in the same way. It used to be accepted
    # silently: failing assertions exited 0, with nothing printed to say the
    # gate had been switched off.
    if no_assertions and (strict_assertions or min_pass_rate is not None):
        other = "--strict-assertions" if strict_assertions else "--min-pass-rate"
        raise click.UsageError(
            f"--no-assertions and {other} are mutually exclusive: "
            f"--no-assertions skips every assertion, so there is nothing for "
            f"{other} to gate on."
        )
    if min_pass_rate is not None and not (0.0 <= min_pass_rate <= 1.0):
        raise click.UsageError(
            f"--min-pass-rate must be between 0.0 and 1.0 (got {min_pass_rate})."
        )

    try:
        prompts = load_batch_file(file)
        if not prompts:
            # Exit 2, not 0. Nothing ran: no model was called, no output was
            # written, and any --min-pass-rate went unapplied. Under the JSON
            # recipe in the README stdout was 0 bytes, so a truncated suite
            # was indistinguishable from a green run. 2 rather than 1 because
            # there is no assertion verdict here to report - the run could not
            # proceed, which is what the other pre-flight failures use.
            _print_error(
                f"No prompts to run - the file at {file} parsed as empty.\n"
                "Nothing was evaluated."
            )
            sys.exit(EXIT_CALL_FAILED)

        model_list = parse_models_arg(models)
        if not model_list:
            raise click.UsageError("--models must include at least one model ID or group.")
        model_list = _resolve_dynamic_groups(model_list, local_url)
        temp_list = _parse_temperatures(temperatures)
        _warn_temperature_sweep(model_list, temp_list)
        _warn_unpriced_models(model_list)
        command_sp_list = _resolve_system_prompts(
            system_prompt=system_prompt,
            system_prompts=system_prompts,
            system_prompt_file=system_prompt_file,
        )
        judge_models = _resolve_judge_models(judge=judge, judges=judges)
        judge_criteria_list, judge_template_text = _resolve_judge_criteria_and_template(
            judge_criteria=judge_criteria,
            judge_template=judge_template,
        )
        # `prompts` hashes the suite's resolved prompt TEXT, not the file path:
        # moving the file changes nothing about the experiment, and a path would
        # leak a home directory into the key material.
        run_identity = build_run_identity(
            command="batch",
            started_at=started_at,
            prompts=[bp.prompt for bp in prompts],
            models=model_list,
            temperatures=temp_list,
            system_prompts=list(command_sp_list),
            judges=judge_models,
            runs=1,
        )
        # The hallucination preset; None when not active. Overrides
        # judge criteria and template, and swaps in the hallucination
        # response parser later.
        hallucination_config = resolve_hallucination_config(
            check_hallucination=check_hallucination,
            expected_facts=expected_facts,
            expected_facts_file=expected_facts_file,
            hallucination_template=hallucination_template,
            judge_models_present=bool(judge_models and not no_judge),
        )
        if hallucination_config is not None:
            judge_criteria_list = hallucination_config.criteria
            judge_template_text = hallucination_config.template
        # Validate judge models BEFORE the batch starts - misconfigured
        # judges should not fail late after burning batch money.
        if judge_models and not no_judge:
            _validate_judge_models(judge_models, local_url=local_url)
    except click.UsageError:
        raise
    except (
        BatchValidationError,
        UnknownModelError,
        KeyNotConfiguredError,
        FileNotFoundError,
        ValueError,
    ) as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)

    # Resolve output target + format.
    try:
        output_path, output_fmt = _resolve_batch_output(
            input_path=file,
            output=output,
            output_format=output_format,
            force=force,
        )
    except OutputFormatError as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)

    # Size limits.
    try:
        total = check_batch_size_limits(
            prompts,
            model_list,
            temp_list,
            command_sp_list,
            force_large=force_large,
        )
    except BatchSizeError as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)

    # Cost ceiling.
    if max_cost is not None:
        est = estimate_batch_cost(prompts, model_list, temp_list, command_sp_list)
        if est > max_cost:
            _print_error(
                f"Estimated cost ${est:.4f} exceeds --max-cost ${max_cost:.4f}.\n"
                f"  Estimate assumes {ESTIMATE_INPUT_TOKENS} input + "
                f"{ESTIMATE_OUTPUT_TOKENS} output tokens per call across "
                f"{total} call{'s' if total != 1 else ''}.\n"
                f"  Reduce dimensions or raise --max-cost to proceed."
            )
            sys.exit(EXIT_CALL_FAILED)

    # One ledger for the whole run - the main gather and the judge gather share
    # it, so judge spend counts toward the same ceiling.
    ledger = CostLedger(max_cost)

    # Build states + run.
    def provider_factory(name: str) -> BaseProvider:
        return _get_provider_instance(name, local_url=local_url)

    # `build_batch_states` resolves every model through `get_provider_for_model`,
    # and it is the ONLY user input batch resolved outside a handler - so a typo
    # in --models produced a raw traceback at exit 1 where `compare` printed a
    # panel at exit 2. Exit 1 is EXIT_ASSERTION_FAILED, so a mistyped model
    # reported the same code as a failing assertion.
    #
    # BOTH exceptions are caught. `RetiredModelError` is not a subclass of
    # `UnknownModelError` - they are siblings under `ConfigurationError` - so
    # catching only the one a typo raises would have left the three retired ids
    # crashing.
    #
    # Wrapped here rather than hoisted into the resolution guard above: the
    # size check and the cost ceiling sit between them, and building states
    # first would allocate one StreamState per call for a batch those gates
    # were about to refuse.
    try:
        pairs = build_batch_states(prompts, model_list, temp_list, command_sp_list)
    except (UnknownModelError, RetiredModelError) as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)
    console.print(
        f"[dim]Running batch: {total} call{'s' if total != 1 else ''} "
        f"({len(prompts)} prompt{'s' if len(prompts) != 1 else ''} x "
        f"{len(model_list)} model{'s' if len(model_list) != 1 else ''} x "
        f"{len(temp_list)} temperature{'s' if len(temp_list) != 1 else ''})[/dim]"
    )

    if judge_models and not no_judge and not no_judge_tos:
        print_tos_disclosure(console)
        if hallucination_config is not None:
            console.print(
                Panel(
                    HALLUCINATION_TOS_EXTENSION,
                    title="Hallucination detection",
                    border_style="yellow",
                )
            )

    async def _run_batch_and_judge() -> list[JudgeResult] | None:
        await run_batch(
            pairs=pairs,
            provider_factory=provider_factory,
            console=console,
            concurrency=concurrency,
            show_progress=True,
            ledger=ledger,
        )
        if judge_models and not no_judge:
            jrs = await run_judging(
                items=[(s, bp.prompt) for s, bp in pairs],
                judge_models=judge_models,
                criteria=judge_criteria_list,
                provider_factory=provider_factory,
                template=judge_template_text,
                response_parser=(
                    parse_hallucination_response if hallucination_config is not None else None
                ),
                skip_self_eval=True,
                concurrency=concurrency,
                ledger=ledger,
            )
            if hallucination_config is not None:
                annotate_risk_levels(jrs)
            return jrs
        return None

    try:
        # Single asyncio.run keeps all httpx client cleanup on one event loop.
        judge_results = asyncio.run(_run_batch_and_judge())
    except KeyboardInterrupt:
        _print_error("Interrupted. Nothing was written; calls already made were billed.")
        sys.exit(EXIT_INTERRUPTED)
    except KeyNotConfiguredError as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)
    except ModelariumError as e:
        _print_error(redact_secrets(str(e)))
        sys.exit(EXIT_CALL_FAILED)

    # Run assertions per-state. Failed-call states skip assertion execution
    # (no real output to check). Successful-call states with no configured
    # assertions get an empty list (not None) so they show as "0/0" - which
    # is vacuously fine.
    assertion_results_per_state: list[list[AssertionResult] | None] = []
    for state, bp in pairs:
        # A cancelled cell joins the errored one here rather than being graded.
        # It has `error is None` and `refused is False`, so it used to fall
        # through to `run_assertions` and have its TRUNCATED text checked -
        # `contains` on half an answer is not a verdict about the answer.
        if no_assertions or state.error or state.status == "cancelled":
            assertion_results_per_state.append(None)
        elif state.refused and bp.assertions:
            # The call succeeded and was billed but produced no answer, so no
            # assertion is a verdict about it. Erroring them (rather than
            # running them against "") stops four of the ten types passing
            # vacuously and leaves pass_rate undefined, which the existing
            # "nothing was verified" gate turns into exit 1.
            assertion_results_per_state.append(refused_results(bp.assertions))
        elif not bp.assertions:
            assertion_results_per_state.append([])
        else:
            assertion_results_per_state.append(
                run_assertions(
                    output=state.text,
                    latency_ms=state.latency_ms,
                    cost_usd=state.cost_usd,
                    assertions=bp.assertions,
                )
            )

    # Convert StreamStates to BatchResults and emit.
    results = []
    for i, (state, bp) in enumerate(pairs):
        jr = judge_results[i] if judge_results is not None else None
        ar = assertion_results_per_state[i]
        results.append(state_to_result(state, bp, judge_result=jr, assertion_results=ar))
    _emit_batch_results(
        results,
        output_path=output_path,
        output_fmt=output_fmt,
        models_without_temperature=_models_without_temperature(model_list),
        # `batch` has no --runs and no --significance, so it never computes a
        # verdict and the mixed-sampling caveat cannot apply. Threaded
        # explicitly rather than left to the default so the reason is on record
        # at the call site: the day batch gains --runs, this is what moves.
        significance_temperature_mixed=False,
        run_identity=run_identity,
    )

    # Ahead of every assertion gate: a pass rate over a truncated population is
    # not a verdict about the suite. The output above has already been written,
    # so the completed cells are kept.
    if ledger.exhausted:
        _print_error(_cost_ceiling_message(ledger))
        sys.exit(EXIT_COST_CEILING)

    failed = sum(1 for r in results if r.error)
    refused = sum(1 for r in results if r.error is None and r.refused)
    success = len(results) - failed - refused
    # Refusals keep their cost: `error` stays None on them precisely so this
    # total, and the two others like it, still charge for what was billed.
    total_cost = sum(r.cost_usd for r in results if r.error is None)

    # Tally assertion outcomes. `error` rows are excluded from both numerator
    # and denominator, so a missing-jsonschema doesn't poison the pass rate.
    # They ARE counted separately, because "every assertion errored" and
    # "there were no assertions" both leave the denominator empty and need
    # telling apart - see AssertionTotals.
    totals = count_assertion_totals(assertion_results_per_state)

    summary_parts = [
        f"[green]{success} succeeded[/green]",
        f"[red]{failed} failed[/red]",
    ]
    # Only shown when it happened: a "0 refused" on every ordinary run would
    # be noise, and the succeeded/failed pair has always been unconditional.
    if refused:
        summary_parts.append(f"[yellow]{refused} refused[/yellow]")
    summary_parts.append(f"[dim]total cost ${total_cost:.6f}[/dim]")
    if judge_results is not None:
        j_cost = total_judge_cost(judge_results)
        j_calls = total_judge_calls(judge_results)
        summary_parts.append(
            f"[dim]judge cost ${j_cost:.6f} ({j_calls} call{'s' if j_calls != 1 else ''})[/dim]"
        )
    # The old guard was `definitive > 0 or failed > 0`, which is false when
    # every assertion errored - so the one line a reader scans said nothing
    # about assertions on exactly the run where it mattered most.
    if totals.configured:
        if totals.pass_rate is not None:
            # A refusal is never a `failed`, so the colour rule alone painted a
            # 100% green beside a model that declined every request. The ratio
            # is unchanged - it describes the requests that were answered - but
            # it is no longer allowed to read as a clean pass on its own.
            rate_color = (
                "green" if totals.failed == 0 and not totals.refused else "red"
            )
            summary = (
                f"assertions {totals.passed}/{totals.definitive} "
                f"({totals.pass_rate * 100:.0f}%)"
            )
            if totals.refused:
                summary += f" + {totals.refused} refused"
            summary_parts.append(f"[{rate_color}]{summary}[/{rate_color}]")
        else:
            summary_parts.append(
                f"[red]assertions {ERROR_MARK} 0/{totals.errored} errored[/red]"
            )
    console.print("  ".join(summary_parts))

    # Exit-code logic. Call failures dominate - usually they mean the user
    # needs to fix credentials/infra before they can even evaluate
    # assertions, so we surface that as 2 rather than the softer 1.
    if failed > 0:
        sys.exit(EXIT_CALL_FAILED)

    if not no_assertions:
        rate = totals.pass_rate
        if rate is None:
            # Nothing produced a verdict, so there is no rate to compare and
            # no basis for reporting success. Two causes, two remedies, one
            # outcome - previously both exited 0 claiming a 100% pass rate.
            if totals.configured:
                _print_error(
                    f"No assertion produced a verdict: all {totals.errored} errored. "
                    "Nothing was verified.\n"
                    "The per-assertion errors are listed above."
                )
                sys.exit(EXIT_ASSERTION_FAILED)
            if min_pass_rate is not None or strict_assertions:
                _print_error(
                    "No assertions to evaluate, so the requested gate cannot be "
                    "satisfied. Nothing was verified.\n"
                    "Add assertions to the suite, or drop --min-pass-rate / "
                    "--strict-assertions."
                )
                sys.exit(EXIT_ASSERTION_FAILED)
        if totals.refused:
            # A refusal removed its own assertions from BOTH halves of the
            # ratio, so the rate above covers only what was answered. With one
            # definitive assertion anywhere in the batch the `rate is None`
            # branch never runs, and every gate flag - `--min-pass-rate 1.0`
            # included - passed a run where a model declined everything.
            #
            # This is checked ahead of the ratio rather than folded into it:
            # the ratio is a real measurement of the answered requests and
            # stays that. What was missing was a gate on what it does not
            # cover.
            #
            # `_print_error` now escapes as well as redacts, so interpolating
            # an assertion value or an `error` string here would be shown as
            # text rather than parsed. The message stays literal anyway: the
            # counts are what a gate reader needs, and naming one failing
            # assertion out of many would read as though it were the only one.
            _print_error(
                f"{totals.refused} configured assertion(s) were not evaluated "
                "because the model refused. The pass rate above covers only "
                "the requests that were answered."
            )
            sys.exit(EXIT_ASSERTION_FAILED)
        if min_pass_rate is not None:
            # --min-pass-rate threshold mode: tolerate some failures.
            if rate < min_pass_rate:
                sys.exit(EXIT_ASSERTION_FAILED)
        elif totals.failed > 0:
            # Default / --strict-assertions: ANY failure exits 1.
            sys.exit(EXIT_ASSERTION_FAILED)

    sys.exit(EXIT_OK)


def _resolve_output_path(
    output: str | None,
    output_format: str | None,
    force: bool,
) -> tuple[Path | None, str | None]:
    """Decide where to write and which format to use.

    Returns (output_path_or_None, format_name_or_None).
        output_path is None when no file output is configured.
        format_name is one of: csv, json, markdown - or None when output_path
            is None AND no --output-format was supplied (callers may treat
            that as "use the native display path").

    Raises OutputFormatError for unknown extensions when --output-format
    isn't passed, and refuses to overwrite an existing file without --force.

    Does NOT check input/output overlap - callers that have an input file
    must perform that check themselves.
    """
    if output is None:
        if output_format:
            return None, output_format.lower()
        return None, None

    output_path = Path(output).expanduser().resolve()

    if output_path.exists() and not force:
        raise OutputFormatError(
            f"Output file already exists: {output_path}\n"
            f"  Use --force to overwrite, or pick a different --output path."
        )

    if output_format:
        fmt = output_format.lower()
    else:
        detected = detect_output_format(output_path)
        if detected is None:
            raise OutputFormatError(
                f"Cannot infer output format from {output_path.suffix!r}.\n"
                f"  Pass --output-format csv|json|markdown explicitly, "
                f"or use a recognized extension (.csv .json .md)."
            )
        fmt = detected

    # Ensure the parent directory exists - users sometimes pass
    # `./results/today.csv` without creating ./results/ first.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path, fmt


def _resolve_batch_output(
    *,
    input_path: str,
    output: str | None,
    output_format: str | None,
    force: bool,
) -> tuple[Path | None, str]:
    """Decide where to write and which format to use for the batch command.

    Returns (output_path_or_None, format_name).
        output_path is None when writing to stdout.
        format_name is one of: csv, json, markdown (defaults to markdown
            for stdout when --output-format is not supplied).

    Raises OutputFormatError for unknown extensions when --output-format
    isn't passed, refuses to overwrite an existing file without --force,
    and refuses to write output over the input file.
    """
    # Overlap check runs BEFORE format detection so a user pointing --output
    # at an input file (no known output extension) sees the "input file"
    # error rather than the less-actionable "can't infer format" one.
    if output is not None:
        prospective = Path(output).expanduser().resolve()
        if output_overlaps_input(Path(input_path), prospective):
            raise OutputFormatError(
                f"Refusing to write output over the input file ({prospective}).\n"
                f"  Choose a different --output path."
            )

    output_path, fmt = _resolve_output_path(output, output_format, force)

    if output_path is None:
        # Stdout default for batch: markdown.
        return None, (fmt or "markdown")

    assert fmt is not None  # _resolve_output_path guarantees this when path is non-None
    return output_path, fmt


def _inherited_verdict(verdict: JudgeResult) -> JudgeResult:
    """A run's copy of its cell's verdict: same scores, no cost, no call.

    `_inherited` says this row is not a judge call of its own, only a copy of
    one - the fact `total_judge_calls` needs and cannot recover from the row
    itself, since a zero cost is also what genuinely-free judge models report.
    It is narrower than `_broadcast`, which is true of the billed row as well:
    the statistics need to know a verdict is shared across a cell, the call
    count needs to know which single row paid for it. Both are documented on
    `JudgeResult`, where a reader meets them.
    """
    copy = replace(
        verdict,
        judges=[replace(j, cost_usd=0.0) for j in verdict.judges],
        skipped_models=list(verdict.skipped_models),
        degraded_models=list(verdict.degraded_models),
    )
    copy._broadcast = True  # type: ignore[attr-defined]
    copy._inherited = True  # type: ignore[attr-defined]
    return copy


async def _run_mode_only_judging(
    *,
    states: list[StreamState],
    prompt: str,
    judge_models: list[str],
    criteria: list[str] | None,
    template: str,
    provider_factory: Callable[[str], BaseProvider],
    concurrency: int,
    ledger: CostLedger | None = None,
) -> list[JudgeResult]:
    """Judge only the mode output per cell, then expand the verdict to every run.

    With --runs N, judging every run is expensive. We pick one canonical
    representative per (model, temperature, system_prompt) cell - the
    mode output when a clear winner exists, otherwise the first
    successful run - and assign that single verdict to every state in
    the cell. Returns a list of JudgeResult parallel to `states`.
    """
    from cli_modelarium.run_statistics import compute_run_stats, group_states_by_cell

    groups = group_states_by_cell(states)

    # Pick one representative state per cell.
    representatives: list[tuple[tuple[str, float, str | None], StreamState]] = []
    for key, cell_states in groups.items():
        stats = compute_run_stats(cell_states)
        chosen: StreamState | None = None
        if stats.mode_output is not None:
            for s in cell_states:
                if s.error is None and not s.refused and s.text == stats.mode_output:
                    chosen = s
                    break
        if chosen is None:
            # No mode (all unique) or all failed: fall back to first state
            # that actually answered; if none, the cell stays unjudged.
            # A refused run is never chosen - judging it would spend a real
            # judge call to score nothing and get back "empty response".
            for s in cell_states:
                if s.error is None and not s.refused:
                    chosen = s
                    break
        if chosen is not None:
            representatives.append((key, chosen))

    if not representatives:
        return [JudgeResult() for _ in states]

    cell_verdicts = await run_judging(
        items=[(s, prompt) for _, s in representatives],
        judge_models=judge_models,
        criteria=criteria,
        provider_factory=provider_factory,
        template=template,
        response_parser=None,
        skip_self_eval=True,
        concurrency=concurrency,
        ledger=ledger,
    )

    verdict_by_cell: dict[tuple[str, float, str | None], JudgeResult] = {
        key: verdict for (key, _), verdict in zip(representatives, cell_verdicts, strict=True)
    }

    # Mark the verdicts as broadcast BEFORE expanding, so every consumer can
    # tell "this row was judged" from "this row inherited its cell's verdict".
    # Nothing else records that: `_state_id` distinguishes the two only while
    # the objects stay aliased, because the tag is then overwritten down to one
    # surviving state per cell. Anything that de-aliases them - copying to fix
    # the duplicated cost, say - destroys that signal, so it is recorded here
    # rather than inferred downstream. See `JudgeResult` for what it means.
    for verdict in verdict_by_cell.values():
        verdict._broadcast = True  # type: ignore[attr-defined]

    # Expand: every state in a cell gets that cell's single verdict. The first
    # run of each cell keeps the verdict that was actually paid for; the rest
    # get zero-cost copies.
    #
    # Handing the SAME object to all N runs made one call bill N times. Three
    # separate sums of `judges[].cost_usd` - `total_judge_cost`, and one in
    # each of the JSON and markdown formatters - feed five reported totals,
    # and not one of them can see that the rows share a call. At --runs 20 the
    # reported judge spend was 20x the truth. Zeroing the copies here fixes
    # every one of them, and keeps the per-row score and reasoning that make
    # the inherited verdict worth showing.
    billed_cells: set[tuple[str, float, str | None]] = set()
    expanded: list[JudgeResult] = []
    for s in states:
        key = (s.model, s.temperature, s.system_prompt)
        verdict = verdict_by_cell.get(key)
        if verdict is None:
            expanded.append(JudgeResult())
        elif key in billed_cells:
            expanded.append(_inherited_verdict(verdict))
        else:
            billed_cells.add(key)
            expanded.append(verdict)
    return expanded


def _states_to_compare_results(
    states: list[StreamState],
    prompt: str,
    judge_results: list[JudgeResult] | None = None,
) -> list[BatchResult]:
    """Convert compare's flat StreamState list to BatchResult shape.

    Each state becomes a BatchResult with a synthetic BatchPrompt
    (id=p1, p2, ... matching batch's auto-id convention from
    `batch._parse_txt`) so that the existing batch formatters can
    serialize compare results without a parallel codepath.
    """
    results: list[BatchResult] = []
    for i, state in enumerate(states):
        bp = BatchPrompt(
            id=f"p{i + 1}",
            prompt=prompt,
            system=state.system_prompt,
        )
        jr = judge_results[i] if judge_results is not None else None
        results.append(state_to_result(state, bp, judge_result=jr, assertion_results=None))
    return results


def _flatten_cell_cis(
    cis: dict,
) -> dict:
    """Convert {cell: {metric: ConfidenceInterval}} to a flat dict for
    formatter consumption, keyed by the same cell tuple.

    The key passes through untouched - `(model, temperature, system)` - so the
    formatters can look a cell's own interval up by the key they already build.

    Output shape (per cell):
      {(model, temperature, system): {
        "latency_ms": {"ci_low": .., "ci_high": .., "ci_level": ..,
                      "method": .., "n_resamples": .., "seed": ..,
                      "point_estimate": .., "n_samples": ..},
        ...
      }}

    `point_estimate` and `n_samples` are computed by the bootstrap and were
    dropped here, which left every consumer with two bounds and no centre: the
    Markdown "Point estimate" column had nothing to print and hard-coded a
    dash, and nothing on any surface said how many observations an interval
    rests on.
    """
    out: dict = {}
    for model, metrics in cis.items():
        out[model] = {}
        for metric, ci in metrics.items():
            if ci is None:
                continue
            out[model][metric] = {
                "ci_low": ci.ci_low,
                "ci_high": ci.ci_high,
                "ci_level": ci.ci_level,
                "method": ci.method,
                "n_resamples": ci.n_resamples,
                "seed": ci.seed,
                "point_estimate": ci.point_estimate,
                "n_samples": ci.n_samples,
            }
    return out


def _write_machine_payload(payload: str) -> None:
    """Write a serialized payload to stdout without letting Rich touch it.

    Bypasses the console entirely. Rich reflows at the terminal width, consumes
    square-bracket markup, and colours numbers and URLs - all fine for a table
    and all corruption for a payload. Encoding is pinned to UTF-8 so the bytes
    match `write_json` / `write_csv` exactly, rather than following the locale
    and picking up CRLF translation on Windows.

    The flush keeps ordering independent of whether the text layer above this
    buffer happens to be write-through.
    """
    data = payload.encode("utf-8")
    sys.stdout.flush()
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        # Exotic capture shim with no binary layer: still avoid Rich.
        sys.stdout.write(payload)
        return
    buffer.write(data)
    buffer.flush()


def _emit_batch_results(
    results: list,
    *,
    output_path: Path | None,
    output_fmt: str,
    runs: int = 1,
    significance_results: list | None = None,
    stats_by_cell_cis: dict | None = None,
    mcnemar_results: list | None = None,
    methodology: dict | None = None,
    models_without_temperature: list[str] | None = None,
    significance_temperature_mixed: bool = False,
    run_identity: dict | None = None,
) -> None:
    """Dispatch to the right writer/renderer based on resolved format.

    JSON and markdown both receive every run-level extra, the temperature
    caveat included - markdown is the format that gets written to a file and
    circulated, so the reader of a p-value there is the least likely to have
    seen the console warning that qualifies it. CSV receives only
    stats_by_cell_cis: it is a per-row export and `_format_csv` has no
    parameter for the others, so a significance verdict written to CSV is
    computed and discarded.
    """
    if output_path is None:
        # Stdout: only markdown is rendered natively; csv/json get printed raw.
        if output_fmt == "markdown":
            render_markdown_to_console(
                results,
                console,
                runs=runs,
                significance_results=significance_results,
                stats_by_cell_cis=stats_by_cell_cis,
                mcnemar_results=mcnemar_results,
                methodology=methodology,
                models_without_temperature=models_without_temperature,
                significance_temperature_mixed=significance_temperature_mixed,
                run_identity=run_identity,
            )
        elif output_fmt == "csv":
            from cli_modelarium.output_formatters import _format_csv

            _write_machine_payload(
                _format_csv(
                    results,
                    runs=runs,
                    stats_by_cell_cis=stats_by_cell_cis,
                )
            )
        elif output_fmt == "json":
            from cli_modelarium.output_formatters import _format_json

            _write_machine_payload(
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
                )
            )
        else:
            _print_error(f"Unsupported output format: {output_fmt!r}")
            sys.exit(EXIT_CALL_FAILED)
        return

    if output_fmt == "csv":
        write_csv(
            results,
            output_path,
            runs=runs,
            stats_by_cell_cis=stats_by_cell_cis,
        )
    elif output_fmt == "json":
        write_json(
            results,
            output_path,
            runs=runs,
            significance_results=significance_results,
            stats_by_cell_cis=stats_by_cell_cis,
            mcnemar_results=mcnemar_results,
            methodology=methodology,
            models_without_temperature=models_without_temperature,
            significance_temperature_mixed=significance_temperature_mixed,
            run_identity=run_identity,
        )
    elif output_fmt == "markdown":
        write_markdown(
            results,
            output_path,
            runs=runs,
            significance_results=significance_results,
            stats_by_cell_cis=stats_by_cell_cis,
            mcnemar_results=mcnemar_results,
            methodology=methodology,
            models_without_temperature=models_without_temperature,
            significance_temperature_mixed=significance_temperature_mixed,
            run_identity=run_identity,
        )
    else:
        _print_error(f"Unsupported output format: {output_fmt!r}")
        sys.exit(EXIT_CALL_FAILED)
    console.print(f"[dim]Wrote {escape(str(output_path))}[/dim]")


# ===== diff =====


def _fmt_value(name: str, value: object) -> str:
    """One number, in the unit a reader expects. `-` when it is null.

    A dash rather than `0`: a cancelled cell's cost is unknown, and rendering
    the unknown and the measured zero identically is the inference-by-absence
    this release spent three commits removing from the payload.

    NAMED, and no longer `_fmt_metric`, because it now has three callers. The
    run-totals line used to interpolate its values raw and printed
    `total_cost_usd: 0.00059625 -> 0.0006187499999999999` two lines under a
    table that formatted the same quantity to six places - a float artefact
    that reads as an arithmetic bug in a tool whose subject is cost. The
    p-value line had the same shape. One formatter, so the surfaces cannot
    drift apart again.
    """
    if value is None:
        return "[dim]-[/dim]"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    if name == "cost_usd" or name.endswith("_cost_usd"):
        return f"${value:.6f}"
    if name.endswith("_ms"):
        return f"{value:.1f}"
    if isinstance(value, float):
        # `pass_rate`, a p-value, anything else fractional. `:g` drops the
        # binary-float tail without inventing precision the value never had.
        return f"{value:g}"
    return f"{value:,}"


def _fmt_delta(metric: MetricDelta) -> str:
    """The change, signed, with a percent when there is a baseline to take it against.

    No colour and no threshold. Cost moving up is not "bad" - a slower, dearer
    model may be the one that got the answer right - and thinking-token
    variance alone moves cost between byte-identical outputs, at the magnitude
    measured in `diffing._output_changed`, so any fixed band would fire on
    that and nothing else.
    """
    if metric.delta is None:
        return "[dim]-[/dim]"
    if metric.delta == 0:
        return "[dim]0[/dim]"
    body = _fmt_value(metric.name, abs(metric.delta))
    sign = "+" if metric.delta > 0 else "-"
    if metric.pct is None:
        return f"{sign}{body}"
    return f"{sign}{body} ({metric.pct:+.1f}%)"


def _fmt_output_change(changed: bool | None) -> str:
    """Whether the answer text changed, as words rather than a number.

    Text equality is a boolean and does not belong in a column of signed
    percentages, so it renders in the Change column with the before/after
    cells left empty - there is no number to put in them, and a `0` there
    would read as a measurement.

    Three phrasings for three states, because two of them are opposite
    findings that used to render identically: a model returning the SAME
    answer at a different thinking cost, and a model returning a DIFFERENT
    answer. `None` is neither - it means a side did not answer at all.
    """
    if changed is None:
        return "[dim]no answer on one side[/dim]"
    if changed:
        return "[bold]text changed[/bold]"
    return "[dim]text unchanged[/dim]"


def _render_diff(result: DiffResult, before_name: str, after_name: str, show_all: bool) -> None:
    """Print the human view: what moved, and everything that qualifies it.

    Every qualifier prints BEFORE the numbers. A pricing-table mismatch read
    after a cost table has already been believed is a footnote; read before it,
    it is the reason the table means less than it looks.
    """
    for note in result.verdict.notes:
        console.print(f"[dim]Note: {escape(note)}[/dim]")
    for warning in result.verdict.warnings:
        console.print(
            Panel(escape(warning), title="Qualified", border_style="yellow")
        )

    # DISPLAY is `notable`, the exit code is `moved`. The two differ by the
    # cells nothing can be said about - a side that did not answer, a metric
    # null on one side. Those are not changes and must not flip the exit code,
    # and they are also not "unchanged", so hiding them would make "we cannot
    # tell" and "nothing happened" render the same way.
    shown = result.cells if show_all else [c for c in result.cells if c.notable]

    if shown:
        # One row per (cell, metric). The alternative - a column per metric
        # holding "before -> after (delta)" - puts three numbers in one cell and
        # wraps to four lines at any realistic terminal width, which is how a
        # table stops being read. The cell name prints once per group.
        table = Table(title=f"{before_name} \u2192 {after_name}", border_style="dim")
        table.add_column("Cell", style="bold")
        table.add_column("Metric")
        table.add_column(before_name, justify="right")
        table.add_column(after_name, justify="right")
        table.add_column("Change", justify="right")
        for cell in shown:
            by_name = {m.name: m for m in cell.metrics}
            # `output` FIRST, and on every shown cell. It is the fact that
            # makes the numbers under it readable: "cost moved and the answer
            # did not" is the ordinary case for a thinking model, and a reader
            # who meets the cost delta first has already drawn a conclusion.
            table.add_row(
                escape(cell.key.label()),
                "output",
                "",
                "",
                _fmt_output_change(cell.output_changed),
            )
            for metric in (
                by_name[n]
                for n in CONSOLE_METRICS
                if show_all or by_name[n].moved or by_name[n].uncomparable
            ):
                table.add_row(
                    "",
                    metric.name,
                    _fmt_value(metric.name, metric.before),
                    _fmt_value(metric.name, metric.after),
                    _fmt_delta(metric),
                )
        console.print(table)

    unchanged = len(result.cells) - len(shown)
    if unchanged and not show_all:
        console.print(
            f"[dim]{unchanged} cell{'s' if unchanged != 1 else ''} unchanged "
            f"(--all to show).[/dim]"
        )
    if not result.cells:
        console.print("[dim]No cells in common.[/dim]")

    # Dropped and added cells get their own lines rather than a dash in the
    # delta column: a cell that ran on one side only has no delta, and a dash
    # in a numeric column invites reading it as zero.
    for label, keys in (
        (f"Only in {before_name}", result.only_in_before),
        (f"Only in {after_name}", result.only_in_after),
    ):
        if keys:
            console.print(f"\n[bold]{escape(label)}[/bold]")
            for key in keys:
                console.print(f"  {escape(key.label())}")

    if result.totals:
        console.print("\n[bold]Run totals[/bold]")
        for name, before_value, after_value in result.totals:
            console.print(
                f"  {name}: {_fmt_value(name, before_value)} \u2192 "
                f"{_fmt_value(name, after_value)}"
            )

    if result.p_values:
        # Side by side, never subtracted - see `DiffResult.p_values` in
        # diffing.py for why differencing them invents a quantity.
        console.print("\n[bold]Significance verdicts[/bold] [dim](reported, not compared)[/dim]")
        for entry in result.p_values:
            pair = f"{entry['model_a']} vs {entry['model_b']}"
            console.print(
                f"  [dim]{entry['side']}[/dim] {escape(str(pair))} "
                f"[dim]{entry['kind']}[/dim] "
                f"p={_fmt_value('p_value', entry['p_value'])}"
            )


@main.command("diff")
@click.argument("before", required=True)
@click.argument("after", required=True)
@click.option(
    "--output-format",
    type=click.Choice(["console", "json"], case_sensitive=False),
    default="console",
    help="console (default) shows what moved; json carries every cell and qualifier.",
)
@click.option("--all", "show_all", is_flag=True, help="Show unchanged cells too.")
def diff_cmd(before: str, after: str, output_format: str, show_all: bool) -> None:
    """Compare two JSON payloads and report what moved.

    BEFORE and AFTER are JSON files from `compare` or `batch` - written with
    `--output results.json` or `--output-format json`. Argument order sets the
    direction: BEFORE is read as the earlier run, whatever the timestamps say.

    Exits 0 when nothing moved, 4 when something did, and 2 when the two
    payloads cannot be compared.
    """
    paths = []
    for label, raw in (("BEFORE", before), ("AFTER", after)):
        try:
            paths.append(safe_input_path(raw, max_size_bytes=MAX_PAYLOAD_BYTES))
        except (FileNotFoundError, ValueError) as exc:
            _print_error(f"{label}: {exc}")
            sys.exit(EXIT_CALL_FAILED)

    payloads = []
    for path in paths:
        try:
            payloads.append(load_payload(path))
        except PayloadError as exc:
            _print_error(str(exc))
            sys.exit(EXIT_CALL_FAILED)

    before_name, after_name = paths[0].name, paths[1].name
    result = diff_payloads(payloads[0], payloads[1], before_name, after_name)

    if not result.verdict.ok:
        _print_error(
            "These payloads are not comparable:\n  "
            + "\n  ".join(result.verdict.refusals)
        )
        sys.exit(EXIT_CALL_FAILED)

    if output_format.lower() == "json":
        _write_machine_payload(to_json(result, before_name, after_name))
    else:
        ordering = ordering_warning(payloads[0], payloads[1], before_name, after_name)
        if ordering:
            console.print(f"[yellow]{escape(ordering)}[/yellow]")
        _render_diff(result, before_name, after_name, show_all)

    sys.exit(EXIT_DIFF_CHANGED if result.moved else EXIT_OK)



# ===== configure =====


_KEYS_SET_HINT = "cli-modelarium keys set <provider>"


def _configure_summary(
    *,
    total: int,
    first_provider: str,
    configured: int,
    skipped: int,
    invalid: int,
    not_stored: int,
    not_reached: int,
    no_backend: bool,
    interrupted: bool,
) -> tuple[str, str, str]:
    """Return (body, title, border_style) for what `configure` actually did.

    Five counters rather than one, because `saved` alone rendered a run that
    skipped ten providers identically to one that rejected ten. `invalid` and
    `not_stored` stay separate for the same reason: a user whose keychain is
    locked, told their keys were "invalid", goes and checks the keys.

    `not_reached` exists because stopping early - on a missing backend or on
    Ctrl-C - leaves providers that were neither configured, skipped nor
    failed. A summary that omits them is the defect this function replaces.
    """
    counts = [
        (configured, "configured"),
        (invalid, "invalid"),
        (not_stored, "not stored"),
        (skipped, "skipped"),
    ]
    parts = [f"{n} {label}" for n, label in counts if n]
    if not_reached:
        parts.append(f"{not_reached} not reached")
    tally = ", ".join(parts) if parts else f"all {total} providers skipped"

    if interrupted:
        # The user asked to stop, so nothing here claims completion - but the
        # keys already in the keychain are still theirs and must be named.
        body = f"{tally}.\nAnything not configured can be added with:\n{_KEYS_SET_HINT}"
        return body, "Setup cancelled", "yellow" if configured else "dim"

    if no_backend:
        env_example = f"{first_provider.upper()}_API_KEY"
        # A backend can only vanish mid-run, but if it does, earlier saves
        # stand - so the opening line must not claim nothing was stored.
        opening = (
            "The OS keychain stopped responding partway through."
            if configured
            else "No keys were stored - this machine has no OS keychain."
        )
        body = (
            f"{opening}\n"
            f"{tally}.\n"
            f"Use environment variables instead ({env_example}, one per provider).\n"
            f'See "Headless Linux servers" in the README.'
        )
        if configured:
            return body, "Configured with errors", "yellow"
        return body, "Configuration failed", "red"

    if configured and not (invalid or not_stored):
        # Only offer the recovery command when there is something to recover;
        # "add a skipped provider" reads as a contradiction after a run that
        # skipped none.
        follow_up = (
            f"Add a skipped provider later with:\n{_KEYS_SET_HINT}"
            if skipped
            else "Run: cli-modelarium list-models"
        )
        return f"{tally}.\n{follow_up}", "Configuration complete", "green"

    if configured:
        body = f"{tally}.\nThose keys were not stored. Retry with:\n{_KEYS_SET_HINT}"
        return body, "Configured with errors", "yellow"

    if invalid or not_stored:
        # "Check the key format" is only true advice when a format was the
        # problem. A locked keychain sent there goes and inspects a key that
        # was never wrong.
        guidance = (
            "Check the key format and retry with:"
            if invalid and not not_stored
            else "Retry with:"
        )
        return (
            f"No keys were stored. {tally}.\n{guidance}\n{_KEYS_SET_HINT}",
            "Configuration failed",
            "red",
        )

    return f"No changes. {tally}.", "No changes", "dim"


@main.command()
def configure() -> None:
    """Interactively set API keys for each provider."""
    providers = [p for p in all_known_providers() if p != "local"]

    console.print(
        Panel(
            "Configure API keys. Keys are stored in your OS-native keychain.\n"
            "Press Enter to skip any provider.",
            title="cli-modelarium setup",
            border_style="cyan",
        )
    )

    configured = skipped = invalid = not_stored = not_reached = 0
    no_backend = interrupted = False

    for index, provider in enumerate(providers):
        try:
            key = Prompt.ask(
                f"{provider.capitalize()} API key",
                password=True,
                default="",
                show_default=False,
            )
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Setup cancelled.[/yellow]")
            interrupted = True
            not_reached = len(providers) - index
            break

        if not key.strip():
            skipped += 1
            console.print(f"  [dim]Skipped {provider}[/dim]")
            continue

        try:
            save_key(provider, key)
        except ValueError as e:
            # Format rejected locally - nothing was sent anywhere. Redacted
            # because only security.py's wording keeps the key out of it, and
            # nothing enforces that.
            invalid += 1
            console.print(f"  [red]Invalid format - {redact_secrets(str(e))}[/red]")
            continue
        except keyring.errors.NoKeyringError as e:
            # There is no backend. It will not appear between two prompts, so
            # every remaining provider would raise identically - stop asking
            # for credentials that cannot be stored anywhere.
            not_stored += 1
            no_backend = True
            not_reached = len(providers) - index - 1
            console.print(f"  [red]Could not save: {redact_secrets(str(e))}[/red]")
            break
        except keyring.errors.KeyringError as e:
            # Deliberately NOT a break. This arm covers KeyringLocked, InitError
            # and PasswordSetError - and PasswordSetError is what KWallet raises
            # when someone dismisses one OS auth dialog. Abandoning ten more
            # providers because a user pressed Escape once would be worse than
            # the defect this replaces.
            not_stored += 1
            console.print(f"  [red]Could not save: {redact_secrets(str(e))}[/red]")
            continue
        except Exception as e:  # noqa: BLE001 - see comment
            # Windows calls win32cred.CredWrite unwrapped, so a write failure
            # arrives as a bare pywintypes.error that is not a KeyringError at
            # all. This arm is the only thing covering that platform.
            not_stored += 1
            console.print(f"  [red]Could not save: {redact_secrets(str(e))}[/red]")
            continue

        configured += 1
        console.print(f"  [green]Saved {provider} to keychain[/green]")

    body, title, border_style = _configure_summary(
        total=len(providers),
        first_provider=providers[0] if providers else "openai",
        configured=configured,
        skipped=skipped,
        invalid=invalid,
        not_stored=not_stored,
        not_reached=not_reached,
        no_backend=no_backend,
        interrupted=interrupted,
    )
    console.print()
    console.print(Panel(body, title=title, border_style=border_style))

    if interrupted:
        sys.exit(EXIT_CALL_FAILED)

    # `attempted` is derived, not counted: every branch that increments it also
    # increments exactly one of the three, so `failed > 0 while attempted == 0`
    # cannot arise. Guarding on `configured == 0` alone would fail a run where
    # the user simply skipped everything, which is not an error.
    attempted = configured + invalid + not_stored
    if attempted > 0 and configured == 0:
        sys.exit(EXIT_CALL_FAILED)


# ===== keys =====


@main.group()
def keys() -> None:
    """Manage API keys (stored in OS-native keychain)."""


@keys.command("list")
def keys_list() -> None:
    """Show which providers have keys configured."""
    providers = [p for p in all_known_providers() if p != "local"]

    table = Table(title="API key status", border_style="dim")
    table.add_column("Provider", style="bold")
    table.add_column("Status")

    for provider in providers:
        if is_key_configured(provider):
            table.add_row(provider, "[green]configured[/green]")
        else:
            table.add_row(provider, "[dim]not configured[/dim]")

    saved_local = load_local_url()
    if saved_local:
        table.add_row("local", f"[green]{escape(saved_local)}[/green]")
    else:
        table.add_row("local", f"[dim]default ({LocalProvider.DEFAULT_URL})[/dim]")

    console.print(table)


@keys.command("set")
@click.argument("provider")
@click.option("--base-url", help="(local provider only) Override default base URL.")
def keys_set(provider: str, base_url: str | None) -> None:
    """Set or update the API key for a provider (prompts securely).

    For the local provider, pass --base-url to persist a default URL
    instead of prompting for an API key.
    """
    if provider == "local":
        if not base_url:
            _print_error(
                "Local provider takes --base-url, not an API key.\n"
                "  Example: cli-modelarium keys set local --base-url http://localhost:1234/v1"
            )
            sys.exit(EXIT_CALL_FAILED)
        try:
            LocalProvider._validate_local_url(base_url)
        except ModelariumError as e:
            _print_error(str(e))
            sys.exit(EXIT_CALL_FAILED)
        save_local_url(base_url)
        console.print(f"[green]Saved local provider URL: {escape(base_url)}[/green]")
        return

    if provider not in KEY_PATTERNS:
        _print_error(
            f"Unknown provider: {provider}.\n"
            f"Supported providers: {', '.join(sorted(KEY_PATTERNS))}, local"
        )
        sys.exit(EXIT_CALL_FAILED)

    try:
        key = Prompt.ask(f"{provider.capitalize()} API key", password=True)
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/yellow]")
        sys.exit(EXIT_CALL_FAILED)

    try:
        save_key(provider, key)
    except ValueError as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)
    except Exception as e:
        _print_error(redact_secrets(str(e)))
        sys.exit(EXIT_CALL_FAILED)

    console.print(f"[green]Saved {provider} key to keychain.[/green]")


@keys.command("delete")
@click.argument("provider")
def keys_delete(provider: str) -> None:
    """Remove the API key for a provider from the keychain."""
    if provider != "local" and provider not in KEY_PATTERNS:
        _print_error(
            f"Unknown provider: {provider}.\n"
            f"Supported providers: {', '.join(sorted(KEY_PATTERNS))}, local"
        )
        sys.exit(EXIT_CALL_FAILED)

    if provider == "local":
        if delete_local_url():
            console.print("[green]Removed saved local provider URL.[/green]")
        else:
            console.print("[dim]No saved local provider URL.[/dim]")
        return

    if delete_key(provider):
        console.print(f"[green]Removed {provider} key from keychain.[/green]")
    else:
        console.print(f"[dim]No {provider} key was stored.[/dim]")


# ===== list-models =====


@main.command("list-models")
@click.option(
    "--local", "local_only", is_flag=True, help="Show only local models (queries the local server)."
)
@click.option("--local-url", help="Override default URL for local-model discovery.")
def list_models(local_only: bool, local_url: str | None) -> None:
    """List supported models, grouped by provider."""
    if local_only:
        _list_local_models(local_url)
        return

    providers = all_known_providers()

    any_shown = False
    for provider in providers:
        models = list_models_for_provider(provider)
        if provider == "local":
            # Local models are dynamic - skip the static section; we show
            # discovered models when --local is passed.
            continue
        if not models:
            continue

        any_shown = True
        configured = "configured" if is_key_configured(provider) else "not configured"
        title = f"{provider} [dim]({configured})[/dim]"

        table = Table(title=title, border_style="dim", title_justify="left")
        table.add_column("Model", style="bold")
        table.add_column("Input $/MTok", justify="right")
        table.add_column("Output $/MTok", justify="right")
        table.add_column("Cached $/MTok", justify="right", style="dim")

        for model in models:
            entry = PRICING[model]
            cached = entry.get("cached_input")
            cached_text = f"${float(cached):.4f}" if cached is not None else "-"
            table.add_row(
                model,
                f"${float(entry['input']):.4f}",
                f"${float(entry['output']):.4f}",
                cached_text,
            )

        console.print(table)
        console.print()

    if not any_shown:
        _print_error("No models registered.")
        sys.exit(EXIT_CALL_FAILED)

    console.print(
        "[dim]Local models are routed by the `local/` prefix.[/dim] "
        "[dim]Run `cli-modelarium list-models --local` to discover what's running locally.[/dim]"
    )
    console.print(f"[dim]{pricing_freshness_note()}[/dim]")


def _list_local_models(local_url: str | None) -> None:
    """Query the local server's /models endpoint and render the result."""
    url = local_url or load_local_url() or LocalProvider.DEFAULT_URL

    try:
        # Validate the URL up front - we want LocalURLError BEFORE any I/O.
        LocalProvider._validate_local_url(url)
    except ModelariumError as e:
        _print_error(str(e))
        sys.exit(EXIT_CALL_FAILED)

    try:
        models = asyncio.run(LocalProvider.discover_models(url))
    except httpx.ConnectError:
        console.print(
            Panel(
                f"Could not reach local server at {escape(url)}.\n\n"
                f"Possible causes:\n"
                f"  - Server not running (try: ollama serve)\n"
                f"  - Wrong URL (use --local-url to override)\n"
                f"  - Firewall blocking the connection",
                title="Local models",
                border_style="yellow",
            )
        )
        return
    except httpx.TimeoutException:
        console.print(
            Panel(
                f"Timed out connecting to {escape(url)} "
                f"(waited {LocalProvider.DISCOVERY_TIMEOUT_SECONDS:.0f}s).\n"
                f"The server may be starting up or under heavy load.",
                title="Local models",
                border_style="yellow",
            )
        )
        return
    except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as e:
        console.print(
            Panel(
                f"Local server at {escape(url)} returned an unexpected response:\n"
                f"  {redact_secrets(str(e))}",
                title="Local models",
                border_style="yellow",
            )
        )
        return

    if not models:
        console.print(
            Panel(
                f"Local server at {escape(url)} responded but has no models installed.\n"
                f"For Ollama: ollama pull llama3.3",
                title="Local models",
                border_style="cyan",
            )
        )
        return

    table = Table(
        # Only the url is escaped: the `[dim]` is the tool's own styling and
        # must still be applied rather than printed.
        title=f"local [dim]({escape(url)})[/dim]",
        border_style="dim",
        title_justify="left",
    )
    table.add_column("Model ID for cli-modelarium", style="bold")
    table.add_column("Created", style="dim")
    table.add_column("Owned by", style="dim")
    table.add_column("Cost", justify="right")

    for entry in models:
        model_id = entry.get("id", "(unnamed)")
        created = entry.get("created")
        created_text = _format_unix_timestamp(created) if created else "-"
        owned_by = str(entry.get("owned_by", "-"))
        table.add_row(
            f"local/{escape(model_id)}", created_text, escape(owned_by),
            "[dim]Free[/dim]",
        )

    console.print(table)
    first_id = models[0].get("id", "<name>")
    console.print(
        f"\n[dim]Use these via: cli-modelarium 'prompt' "
        f"--models local/{escape(first_id)}[/dim]"
    )


def _format_unix_timestamp(ts: object) -> str:
    """Format a unix timestamp (int or float) as YYYY-MM-DD, or '-' if unparseable."""
    try:
        from datetime import UTC, datetime

        return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return "-"


# ===== pricing =====


@main.command("pricing")
@click.argument("model", required=False)
@click.option("--all", "show_all", is_flag=True, help="Show pricing for every model.")
def pricing_cmd(model: str | None, show_all: bool) -> None:
    """Show pricing for a model or all models."""
    if show_all or model is None:
        table = Table(title="Pricing (per 1M tokens, USD)", border_style="dim")
        table.add_column("Model", style="bold")
        table.add_column("Provider")
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
        table.add_column("Cached", justify="right", style="dim")

        for name in sorted(PRICING):
            if name.endswith("/*"):
                continue
            entry = PRICING[name]
            if entry.get("is_local"):
                table.add_row(
                    name,
                    str(entry["provider"]),
                    "[dim]Free[/dim]",
                    "[dim]Free[/dim]",
                    "[dim]-[/dim]",
                )
                continue
            cached = entry.get("cached_input")
            cached_text = f"${float(cached):.4f}" if cached is not None else "-"
            table.add_row(
                name,
                str(entry["provider"]),
                f"${float(entry['input']):.4f}",
                f"${float(entry['output']):.4f}",
                cached_text,
            )

        console.print(table)
        console.print(f"[dim]{pricing_freshness_note()}[/dim]")
        return

    if is_local_model(model):
        console.print(f"[bold]{escape(model)}[/bold]: [dim]Free (local model)[/dim]")
        return

    # This path reads PRICING directly and bypasses get_provider_for_model(),
    # so the retirement check has to be repeated here - otherwise a retired ID
    # would report as a generic not-found.
    retired = RETIRED_MODELS.get(model)
    if retired is not None:
        replacement, retired_on = retired
        _print_error(str(RetiredModelError(model, replacement, retired_on)))
        sys.exit(EXIT_CALL_FAILED)

    entry = PRICING.get(model)
    if entry is None:
        _print_error(f"Unknown model: {model}. Run `cli-modelarium list-models` to see options.")
        sys.exit(EXIT_CALL_FAILED)

    cached = entry.get("cached_input")
    # `provider` is a PRICING literal, so only the id needs escaping.
    console.print(f"[bold]{escape(model)}[/bold] ([dim]{entry['provider']}[/dim])")
    console.print(f"  Input:   ${float(entry['input']):.4f} / 1M tokens")
    console.print(f"  Output:  ${float(entry['output']):.4f} / 1M tokens")
    if cached is not None:
        console.print(f"  Cached:  ${float(cached):.4f} / 1M tokens")
    console.print(f"\n[dim]{pricing_freshness_note()}[/dim]")


# ===== helpers =====


def _sweep_caveat(affected: list[str], temperature_count: int) -> str:
    """The sweep half of the temperature caveat: every value produces one request."""
    verb, pronoun = ("does not", "it") if len(affected) == 1 else ("do not", "them")
    return (
        f"{', '.join(affected)} {verb} accept a temperature setting, so the "
        f"field is omitted for {pronoun}. The {temperature_count} runs of each "
        f"are not a sweep - the same request is sent each time, and the "
        f"temperature shown in the results reflects what was requested, not "
        f"what was applied."
    )


def _models_without_pricing(models: list[str]) -> list[str]:
    """Registered models whose provider publishes no per-token rate.

    Provider-keyed rather than value-keyed on purpose: `cost_usd == 0.0` is also
    true of local models and of the seven genuinely-free rows, so the value
    cannot distinguish an unpriced model from a free one. Absent from PRICING
    means priced, matching every other predicate in this module.
    """
    return sorted({m for m in models if PRICING.get(m, {}).get("provider") == "nvidia"})


def _pricing_caveat(affected: list[str]) -> str:
    """Cost is unavailable for these models, and three guards silently do not apply."""
    return (
        f"Cost is not tracked for {', '.join(affected)}. NVIDIA publishes no "
        f"per-token rate for hosted NIM, so the cost column shows zero, which is "
        f"not a price - access is credit-metered, so you can exhaust credits "
        f"rather than be billed.\n\n"
        f"--max-cost and cost_under provide no protection on this provider.\n\n"
        f"--significance-metric cost_usd should not be trusted while one of these "
        f"is in the comparison: its cost is a constant placeholder rather than a "
        f"measurement."
    )


def _warn_unpriced_models(models: list[str]) -> None:
    """Warn that cost is unavailable for any NIM model in this run.

    A SEPARATE panel rather than a condition merged into the temperature one.
    That panel's title is hardcoded to "Temperature not applied", so a cost
    caveat merged into it renders under a heading about temperature. Emitting
    separately also keeps `_warn_temperature_sweep` untouched - routing this
    through it would hit its `len(temperatures) < 2` early return, which a NIM
    model at a single temperature would never pass.

    Call this AFTER group expansion, alongside the temperature emitter. Neither
    suppresses the other; both panels render when both conditions hold.
    """
    affected = _models_without_pricing(models)
    if not affected:
        return
    console.print(
        Panel(
            _pricing_caveat(affected),
            title="Cost not tracked",
            border_style="yellow",
        )
    )


def _warn_temperature_sweep(models: list[str], temperatures: list[float]) -> None:
    """Warn when a multi-value sweep includes a model that ignores temperature.

    Those models have the field omitted entirely, so every value in the sweep
    produces an identical request. Fires for group-expanded ids too - by this
    point `all-premium` is already eight concrete ids, which is the case where
    the user never typed the affected name and most needs telling.

    This is `batch`'s emitter. `batch` has no `--runs` and no `--significance`,
    so the sweep is the only temperature caveat that can arise there. `compare`
    uses `_warn_temperature_conditions()`, which can merge this text with the
    significance caveat.
    """
    if len(temperatures) < 2:
        return
    affected = _models_without_temperature(models)
    if not affected:
        return
    console.print(
        Panel(
            _sweep_caveat(affected, len(temperatures)),
            title="Temperature not applied",
            border_style="yellow",
        )
    )


def _warn_temperature_conditions(
    models: list[str],
    temperatures: list[float],
    *,
    significance_runs: bool,
) -> None:
    """Emit the temperature caveats for this run as a SINGLE panel.

    Two conditions each produce a caveat and can hold at once:

      * a multi-value sweep containing a model with the field omitted - every
        value in the sweep produces an identical request
      * a significance run mixing models that omit the field with models that
        honour it - the two groups were sampled under different conditions, so
        the p-value can be reporting that rather than model quality

    When both hold the two messages are MERGED into one panel rather than either
    being suppressed. Suppressing the sweep half would not deduplicate it: it
    fires today on runs this one cannot cover (`batch`, and any `compare` left
    at the default `--runs 1`, where no verdict is computed), so suppression
    would delete it from those runs entirely.

    Call this AFTER group expansion, so an id that arrived via `all-flagship` is
    named even though the user never typed it.
    """
    omitted, honoured = _mixes_temperature_handling(models)
    parts: list[str] = []
    if len(temperatures) >= 2 and omitted:
        parts.append(_sweep_caveat(omitted, len(temperatures)))
    if significance_runs and omitted and honoured:
        parts.append(significance_temperature_caveat(omitted))
    if not parts:
        return
    console.print(
        Panel(
            "\n\n".join(parts),
            title="Temperature not applied",
            border_style="yellow",
        )
    )


def _mixes_temperature_handling(models: list[str]) -> tuple[list[str], list[str]]:
    """Split a resolved model list into (omitted, honoured).

    Both non-empty means the models were sampled under different conditions.

    Both halves are sorted and de-duplicated. The omitted half is exactly
    `_models_without_temperature()`; the honoured half is everything else, which
    includes ids absent from `PRICING` - local and unregistered - since
    those keep receiving `temperature`. Only the omitted half is ever rendered:
    it is a subset of the registry keys, whereas the honoured half can contain
    arbitrary user-supplied text.
    """
    omitted = _models_without_temperature(models)
    honoured = sorted({m for m in models if m not in set(omitted)})
    return omitted, honoured


def _significance_will_run(significance: bool | None, runs: int, model_count: int) -> bool:
    """Whether this invocation will actually compute a significance verdict.

    `--significance/--no-significance` is TRI-STATE: `None` means auto-enable,
    so `if significance` reads the DEFAULT path as "off" - which is precisely the
    path with no signal today. The enablement decision and the `runs`/model-count
    gate it is later applied under are collapsed here so the warning and the
    computation cannot drift apart.
    """
    if significance is None:
        enabled = runs > 1 and model_count >= 2
    else:
        enabled = significance
    return enabled and runs > 1 and model_count >= 2


def _models_without_temperature(models: list[str]) -> list[str]:
    """Models in this run whose `temperature` was omitted from the request.

    Sorted and de-duplicated. Always safe to emit: the predicate is False for
    anything absent from PRICING, so local and unregistered ids can
    never appear here - the list is a subset of the flagged registry entries.
    """
    return sorted({m for m in models if rejects_sampling_params(m)})


def _parse_temperatures(raw: str) -> list[float]:
    """Parse a comma-separated temperatures string into floats. Defaults to [0.0]."""
    if not raw.strip():
        return [0.0]
    out: list[float] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            parsed = float(token)
        except ValueError:
            raise ValueError(f"Invalid temperature value: {token!r}") from None
        # `float()` happily returns nan/inf, and a non-finite temperature was
        # written straight into the JSON payload as `NaN` - which RFC 8259 has
        # no syntax for. No BOUND is enforced: there is no client-side limit
        # anywhere and every provider forwards the raw value, so refusing 2.0
        # would reject a temperature that works today.
        if not math.isfinite(parsed):
            raise ValueError(
                f"Temperature must be a finite number, got {token!r}."
            ) from None
        out.append(parsed)
    return out or [0.0]


def _resolve_all_cloud() -> list[str]:
    """Every cloud PRICING model whose provider has a configured API key.

    Excludes local models and the OpenRouter entries (the latter are a few
    registered rows, not OpenRouter's full catalog).

    NVIDIA is excluded for three reasons. `all` otherwise means every model whose
    cost can be stated, and the NIM rows cannot. The registry already holds four
    duplicate-weight pairs, each neutralised only because OpenRouter is excluded,
    so NVIDIA would be the first provider able to put a genuine duplicate here.
    And a run exits 2 if any cell errors: roughly half NVIDIA's catalog was
    unreachable when screened and availability moves between runs, so one
    unreachable model would fail an otherwise-successful run while the exit code
    suggests a credential problem.
    """
    out: list[str] = []
    for model, entry in PRICING.items():
        provider = str(entry.get("provider", ""))
        if provider in ("local", "openrouter", "nvidia") or model.endswith("/*"):
            continue
        if is_key_configured(provider):
            out.append(model)
    return out


def _resolve_all_local(local_url: str | None) -> list[str]:
    """Models reported by a running local server, mapped to `local/<id>`.

    Catches discovery failures (unreachable / timeout / bad response), prints a
    friendly notice, and returns an empty list rather than raising - the outer
    compare/batch try/except does NOT catch httpx errors, so they must be handled
    here or they become an uncaught traceback.
    """
    url = local_url or load_local_url() or LocalProvider.DEFAULT_URL
    try:
        entries = asyncio.run(LocalProvider.discover_models(url))
    except (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.HTTPStatusError,
        httpx.RequestError,
    ):
        console.print(
            Panel(
                f"Could not reach a local server at {escape(url)}.\n"
                f"Is Ollama / LM Studio / vLLM / llama.cpp running? "
                f"Override the URL with --local-url.",
                title="all-local",
                border_style="yellow",
            )
        )
        return []
    except ModelariumError as e:
        # Localhost guard (LocalURLError) is a config error, not an unreachable
        # server - convert to ValueError so the outer block surfaces it as exit 2.
        raise ValueError(str(e)) from None
    return [f"local/{entry['id']}" for entry in entries if entry.get("id")]


def _resolve_dynamic_groups(model_list: list[str], local_url: str | None) -> list[str]:
    """Resolve the dynamic group tokens `all` / `all-local` against runtime state.

    `all`       -> every cloud model with a configured API key (cloud half).
    `all-local` -> every model a running local server reports (live half).
    Other tokens pass through unchanged. The result is de-duplicated,
    order-preserving (first occurrence wins).

    Resolution lives in the caller (not in parse_models_arg) so token parsing
    stays a pure, network-free function.
    """
    resolved: list[str] = []
    requested_all = False
    for token in model_list:
        if token == "all":
            requested_all = True
            resolved.extend(_resolve_all_cloud())
        elif token == "all-local":
            resolved.extend(_resolve_all_local(local_url))
        else:
            resolved.append(token)

    deduped = list(dict.fromkeys(resolved))
    if not deduped:
        if requested_all:
            raise ValueError(
                "No API keys configured for any cloud provider. Configure one with "
                "`cli-modelarium keys set <provider>`, or pass explicit model IDs."
            )
        raise ValueError(
            "No models to run: no local server models were found. Start a local "
            "server, or pass explicit model IDs."
        )
    return deduped


def _resolve_system_prompts(
    *,
    system_prompt: str | None,
    system_prompts: str | None,
    system_prompt_file: str | None,
) -> list[str | None]:
    """Resolve the three mutually-exclusive system-prompt flags into a list.

    Returns `[None]` when no system prompt is configured (the orchestrator
    treats this as "one task with no system prompt"). Returns a list of
    strings otherwise - never an empty list.

    Raises:
        click.UsageError: if more than one of the three flags is set.
        FileNotFoundError / ValueError: from `load_system_prompt`.
    """
    used = [
        name
        for name, val in (
            ("--system-prompt", system_prompt),
            ("--system-prompts", system_prompts),
            ("--system-prompt-file", system_prompt_file),
        )
        if val
    ]
    if len(used) > 1:
        raise click.UsageError(f"{', '.join(used)} are mutually exclusive - pick one.")

    if system_prompt_file:
        return [load_system_prompt(system_prompt_file)]
    if system_prompts:
        parsed = _split_system_prompts(system_prompts)
        return parsed or [None]
    if system_prompt:
        # Empty-string case is also caught here; we'd have failed the `if`
        # above. But guard anyway: a stripped-empty value means no prompt.
        stripped = system_prompt.strip()
        return [stripped] if stripped else [None]
    return [None]


# Re-export under the cli.py namespace for backward compatibility with the
# system-prompt and judging tests that import these private aliases directly.
_split_escaped_csv = split_escaped_csv
_split_system_prompts = split_escaped_csv


def _resolve_judge_models(*, judge: str | None, judges: str | None) -> list[str]:
    """Resolve --judge / --judges into a list of judge model IDs.

    Returns [] when neither flag is set. Raises click.UsageError if both
    flags are set simultaneously (they're mutually exclusive).
    """
    if judge and judges:
        raise click.UsageError("--judge and --judges are mutually exclusive - pick one.")
    if judges:
        return _split_escaped_csv(judges)
    if judge and judge.strip():
        return [judge.strip()]
    return []


def _resolve_judge_criteria_and_template(
    *,
    judge_criteria: str | None,
    judge_template: str | None,
) -> tuple[list[str], str]:
    """Resolve --judge-criteria and --judge-template into (criteria, template).

    Returns (DEFAULT_CRITERIA, JUDGE_PROMPT_TEMPLATE) when neither is set.
    Raises click.UsageError if both are set simultaneously.

    --judge-template loads a custom prompt template from disk (UTF-8, max 1 MB).
    --judge-criteria splits on commas with the same `\\,` escape as system prompts.
    """
    if judge_criteria and judge_template:
        raise click.UsageError(
            "--judge-criteria and --judge-template are mutually exclusive - pick one."
        )
    criteria = list(DEFAULT_CRITERIA)
    template = JUDGE_PROMPT_TEMPLATE
    if judge_criteria:
        criteria = _split_escaped_csv(judge_criteria) or list(DEFAULT_CRITERIA)
    if judge_template:
        # Reuse the system-prompt-file loader: same size + encoding contract.
        template = load_system_prompt(judge_template)
    return criteria, template


def _validate_judge_models(judge_models: list[str], *, local_url: str | None) -> None:
    """Ensure every judge model is in the registry AND has a configured key.

    This runs BEFORE any main API calls - the contract is
    that a misconfigured judge fails the run immediately, not after burning
    money on the comparison.
    """
    from cli_modelarium.models_registry import get_provider_for_model
    from cli_modelarium.security import is_key_configured

    seen_providers: set[str] = set()
    for model in judge_models:
        provider_name = get_provider_for_model(model)  # raises UnknownModelError
        if provider_name in seen_providers:
            continue
        seen_providers.add(provider_name)
        if provider_name == "local":
            # Local needs no key; the URL check happens at construction time.
            continue
        if not is_key_configured(provider_name):
            raise KeyNotConfiguredError(provider_name)


def _get_provider_instance(provider_name: str, *, local_url: str | None = None) -> BaseProvider:
    """Instantiate the provider for `provider_name`.

    For cloud providers: loads the API key from env var / keychain and
    raises `KeyNotConfiguredError` if missing.

    For the local provider: skips the API-key path entirely. The URL is taken
    from `local_url` if provided, else from the keychain/env var, else
    `LocalProvider.DEFAULT_URL`.
    """
    if provider_name not in PROVIDER_REGISTRY:
        raise UnknownProviderError(
            f"Provider '{provider_name}' is not yet wired up. "
            f"Currently supported: {', '.join(sorted(PROVIDER_REGISTRY))}."
        )

    if provider_name == "local":
        url = local_url or load_local_url()
        return LocalProvider(base_url=url)

    from cli_modelarium.security import load_key

    api_key = load_key(provider_name)
    if not api_key:
        raise KeyNotConfiguredError(provider_name)

    module_path, _, class_name = PROVIDER_REGISTRY[provider_name].partition(":")
    import importlib

    module = importlib.import_module(module_path)
    provider_cls = getattr(module, class_name)
    return provider_cls(api_key=api_key)


def _display_results(
    states: list[StreamState],
    judge_results: list[JudgeResult] | None = None,
    include_reasoning: bool = False,
    hallucination_mode: bool = False,
    hallucination_facts: list[str] | None = None,
) -> None:
    """Render the comparison results as a Rich table plus per-model output blocks.

    `judge_results` is parallel to `states` when provided; it adds a Score
    column to the table and a Reasoning line under each output block when
    `include_reasoning=True`.

    When `hallucination_mode=True`, the Score column is relabeled
    "Hallucination Risk" and each cell shows the worst-case panel risk
    plus the score (e.g. "Low (8)"). Color: Low=green, Medium=yellow,
    High=red.
    """
    # Only surface the SP column when there are 2+ distinct non-empty
    # system prompts. The streaming legend has already printed the full
    # mapping; we just need the index here.
    from cli_modelarium.streaming import prompt_index_map

    prompt_indices = prompt_index_map(states)
    show_sp_column = bool(prompt_indices)
    show_score_column = judge_results is not None

    table = Table(
        title=f"Comparing {len(states)} completion{'s' if len(states) != 1 else ''}",
        border_style="dim",
        title_justify="left",
    )
    table.add_column("Model", style="bold")
    if show_sp_column:
        table.add_column("SP", style="magenta", justify="right")
    table.add_column("Temp", justify="right")
    table.add_column("TTFT", justify="right", style="dim")
    table.add_column("Latency", justify="right", style="dim")
    table.add_column("In", justify="right")
    table.add_column("Out", justify="right")
    table.add_column("Cost", justify="right")
    if show_score_column:
        score_header = "Hallucination Risk" if hallucination_mode else "Score"
        table.add_column(score_header, style="magenta", justify="right")
    table.add_column("Status")

    total_cost = 0.0
    for i, s in enumerate(states):
        word = status_word(s.error, s.refused, s.status == "cancelled")
        if s.error:
            status = "[red]error[/red]"
            cost_text = "[dim]-[/dim]"
            ttft_text = "[dim]-[/dim]"
            latency_text = "[dim]-[/dim]"
            in_text = "[dim]-[/dim]"
            out_text = "[dim]-[/dim]"
        elif word == STATUS_CANCELLED:
            # Never dispatched, so there is no timing and no cost to show. It
            # printed `ok` at `$0.000000` until this branch existed - a cell
            # that never ran, rendered as a free success, on the DEFAULT
            # surface. Its cost is not summed: nothing was spent.
            status = "[cyan]cancelled[/cyan]"
            cost_text = "[dim]-[/dim]"
            ttft_text = "[dim]-[/dim]"
            latency_text = "[dim]-[/dim]"
            in_text = "[dim]-[/dim]"
            out_text = "[dim]-[/dim]"
        else:
            # A refusal reached the provider and was billed, so it keeps its
            # cost and its timings - only the verdict differs from "ok".
            status = "[yellow]refused[/yellow]" if s.refused else "[green]ok[/green]"
            total_cost += s.cost_usd
            cost_text = "[dim]Free[/dim]" if is_local_model(s.model) else f"${s.cost_usd:.6f}"
            ttft_text = f"{s.ttft_ms / 1000:.2f}s" if s.ttft_ms is not None else "[dim]-[/dim]"
            latency_text = (
                f"{s.latency_ms / 1000:.2f}s" if s.latency_ms is not None else "[dim]-[/dim]"
            )
            in_text = str(s.input_tokens)
            out_text = str(s.output_tokens)

        row: list[str] = [escape(s.model)]
        if show_sp_column:
            if s.system_prompt and s.system_prompt in prompt_indices:
                row.append(f"SP {prompt_indices[s.system_prompt]}")
            else:
                row.append("[dim]-[/dim]")
        row.extend(
            [
                f"{s.temperature:.1f}",
                ttft_text,
                latency_text,
                in_text,
                out_text,
                cost_text,
            ]
        )
        if show_score_column:
            assert judge_results is not None
            if hallucination_mode:
                row.append(_risk_cell_for_compare(judge_results[i]))
            else:
                row.append(_score_cell_for_compare(judge_results[i]))
        row.append(status)
        table.add_row(*row)

    console.print(table)

    _print_degraded_judge_notice(judge_results)
    console.print()

    # Per-model output blocks. When multiple SPs are in play, identify which
    # one produced each block so the reader can cross-reference the legend.
    for i, s in enumerate(states):
        header = (
            f"[bold cyan]>[/bold cyan] [bold]{escape(s.model)}[/bold] "
            f"@ {s.temperature:.1f}"
        )
        if show_sp_column and s.system_prompt and s.system_prompt in prompt_indices:
            header += f"  [magenta]SP {prompt_indices[s.system_prompt]}[/magenta]"
        console.print(header)
        if s.error:
            console.print(f"  [red]{escape(s.error)}[/red]")
        else:
            for line in s.text.splitlines() or [""]:
                console.print(f"  {escape(line)}")
        # Optional judge reasoning lines.
        if include_reasoning and judge_results is not None:
            for j in judge_results[i].judges:
                score_str = j.score if j.score is not None else "?"
                if j.parse_error:
                    console.print(
                        f"  [magenta dim]judge {escape(j.model)}: parse error - "
                        f"{escape(str(j.parse_error))}[/magenta dim]"
                    )
                else:
                    console.print(
                        f"  [magenta dim]judge {escape(j.model)} ({score_str}/10): "
                        f"{escape(str(j.reasoning))}[/magenta dim]"
                    )
        console.print()

    console.print(f"[dim]Total cost: ${total_cost:.6f}[/dim]")
    if judge_results is not None:
        j_cost = total_judge_cost(judge_results)
        j_calls = total_judge_calls(judge_results)
        console.print(
            f"[dim]Judge cost: ${j_cost:.6f} "
            f"({j_calls} judge call{'s' if j_calls != 1 else ''})[/dim]"
        )
    if hallucination_mode and hallucination_facts:
        console.print(
            f"[dim]Hallucination check: "
            f"{len(hallucination_facts)} reference fact"
            f"{'s' if len(hallucination_facts) != 1 else ''} provided[/dim]"
        )
    console.print(f"[dim]{pricing_freshness_note()}[/dim]")


def _display_results_with_runs(
    states: list[StreamState],
    judge_results: list[JudgeResult] | None,
    runs: int,
    include_reasoning: bool = False,
    hallucination_mode: bool = False,
    hallucination_facts: list[str] | None = None,
    significance_results: list | None = None,
    stats_by_cell_cis: dict | None = None,
    mcnemar_results: list | None = None,
) -> None:
    """Render the runs > 1 path: one summary row per cell with RunStats.

    Groups states by (model, temperature, system_prompt) cell, computes
    RunStats per cell, and prints a Rich table with statistical summary
    columns. Per-run outputs are shown below the table as a collapsed
    listing.

    `judge_results` is parallel to `states` when provided. With mode-only
    judging, every state in a cell shares the same JudgeResult, so we pull
    the cell verdict from the first state.

    When `hallucination_mode=True`, an additional "Hallucination Rate"
    summary is computed (fraction of runs flagged as High risk per cell).
    """
    from cli_modelarium.run_statistics import compute_run_stats, group_states_by_cell

    groups = group_states_by_cell(states)
    judge_by_state_id: dict[int, JudgeResult] = {}
    if judge_results is not None:
        for state, jr in zip(states, judge_results, strict=True):
            judge_by_state_id[id(state)] = jr

    distinct_sps = {s.system_prompt for s in states if s.system_prompt}
    show_sp_column = len(distinct_sps) > 1
    # Only when it happened, on the same rule as the SP column: a run with no
    # cancelled cells keeps the three-slot header byte-identical. Without the
    # fourth slot the triple silently failed to add up to the run count printed
    # in this table's own title - "2/0/0" under "3 runs each".
    show_cancelled = any(s.status == "cancelled" for s in states)
    show_hallucination_rate = hallucination_mode and judge_results is not None
    show_judge_column = judge_results is not None and not show_hallucination_rate

    plural = "s" if len(groups) != 1 else ""
    title = f"Comparing {len(groups)} configuration{plural}, {runs} runs each"
    table = Table(title=title, border_style="dim", title_justify="left")
    table.add_column("Model", style="bold")
    if show_sp_column:
        table.add_column("SP", style="magenta", justify="right")
    table.add_column("Temp", justify="right")
    # `OK/R/F`, not `OK/Ref/Fail`: the long form renders as "OK/Re…" at
    # both 80 and 100 columns, which hides that the cell carries a third
    # number. The compact form shows three slots at every width, and "R"
    # has no competitor here - retries are a CSV/JSON field and appear on
    # neither console table. Markdown uses the full words; a pipe table is
    # not width-bound.
    table.add_column("OK/R/F/C" if show_cancelled else "OK/R/F", justify="right")
    table.add_column("Latency mean ± stdev", justify="right", style="dim")
    table.add_column("CV", justify="right", style="dim")
    table.add_column("Tokens mean", justify="right")
    table.add_column("Cost total", justify="right")
    table.add_column("Diversity", justify="right")
    if show_hallucination_rate:
        table.add_column("Halluc. rate", justify="right", style="magenta")
    if show_judge_column:
        table.add_column("Score (mode)", justify="right", style="magenta")
    table.add_column("Mode", justify="left")

    from cli_modelarium.streaming import prompt_index_map

    prompt_indices = prompt_index_map(states)

    grand_total_cost = 0.0
    cell_stats: list[tuple[tuple[str, float, str | None], list[StreamState], object]] = []
    for key, cell_states in groups.items():
        stats = compute_run_stats(cell_states)
        cell_stats.append((key, cell_states, stats))
        grand_total_cost += stats.cost_total_usd

        model, temp, sp = key

        # Hallucination rate: fraction of runs in this cell with risk_level "High".
        hallucination_rate_text = "[dim]-[/dim]"
        if show_hallucination_rate:
            high_count = 0
            judged = 0
            for s in cell_states:
                if s.error is not None or s.refused:
                    # A refusal is neither a hallucination pass nor a fail: there
                    # is no answer to classify, so it belongs in neither half of
                    # this fraction. Same guard as compute_mcnemar_pairwise, so
                    # the cell and the test below it count the same population.
                    #
                    # The `s.error` clause is redundant today - run_judging
                    # returns an empty JudgeResult() for an errored state, which
                    # `not jr.judges` below already drops - and the `s.refused`
                    # clause becomes redundant too once run_judging stops judging
                    # declined rows. Both are stated anyway so the rule lives
                    # here rather than in a fact about another module.
                    continue
                jr = judge_by_state_id.get(id(s))
                if jr is None or not jr.judges:
                    continue
                risk = jr.aggregated_risk_level
                if risk is None:
                    # The judge answered but named no risk level, so this run was
                    # not classified. Counting it as "judged" made the cell say
                    # 1/3 where compute_mcnemar_pairwise, which drops it, used
                    # 1/1 on the same data. The two now drop the same three
                    # kinds of run: errored or declined, unjudged, unclassified.
                    continue
                judged += 1
                if risk == "High":
                    high_count += 1
            if judged > 0:
                rate = high_count / judged
                color = (
                    "red" if rate >= 0.5 else "yellow" if rate >= 0.2 else "green"
                )
                pct = f"{rate * 100:.0f}%"
                hallucination_rate_text = f"[{color}]{high_count}/{judged} ({pct})[/{color}]"

        # Judge score (mode-only judging): pull the first non-empty JudgeResult.
        score_text = "[dim]-[/dim]"
        if show_judge_column:
            for s in cell_states:
                jr = judge_by_state_id.get(id(s))
                if jr is not None and jr.judges:
                    score_text = _score_cell_for_compare(jr)
                    break

        if stats.latency_mean_ms is not None and stats.latency_stdev_ms is not None:
            latency_cell = f"{stats.latency_mean_ms:.0f} ± {stats.latency_stdev_ms:.0f} ms"
        elif stats.latency_mean_ms is not None:
            latency_cell = f"{stats.latency_mean_ms:.0f} ms"
        else:
            latency_cell = "[dim]-[/dim]"

        cv_text = f"{stats.latency_cv:.3f}" if stats.latency_cv is not None else "[dim]-[/dim]"
        tokens_text = (
            f"{stats.output_tokens_mean:.0f}"
            if stats.output_tokens_mean is not None
            else "[dim]-[/dim]"
        )
        cost_text = (
            "[dim]Free[/dim]"
            if is_local_model(model)
            else f"${stats.cost_total_usd:.6f}"
        )
        diversity_text = f"{stats.output_diversity:.2f}"

        if stats.n_succeeded == 0:
            # "all unique" is false when nothing was produced. A cell whose
            # runs were all refused or all failed answered nothing at all.
            mode_text = "[dim]no output[/dim]"
        elif stats.mode_output is None:
            mode_text = "[dim]no mode (all unique)[/dim]"
        else:
            preview = stats.mode_output.replace("\n", " ").strip()
            if len(preview) > 50:
                preview = preview[:47] + "..."
            mode_text = f'"{escape(preview)}" ({stats.mode_count}x)'

        row = [escape(model)]
        if show_sp_column:
            if sp and sp in prompt_indices:
                row.append(f"SP {prompt_indices[sp]}")
            else:
                row.append("[dim]-[/dim]")
        row.extend(
            [
                f"{temp:.1f}",
                (
                    f"{stats.n_succeeded}/{stats.n_refused}/{stats.n_failed}"
                    f"/{stats.n_cancelled}"
                    if show_cancelled
                    else f"{stats.n_succeeded}/{stats.n_refused}/{stats.n_failed}"
                ),
                latency_cell,
                cv_text,
                tokens_text,
                cost_text,
                diversity_text,
            ]
        )
        if show_hallucination_rate:
            row.append(hallucination_rate_text)
        if show_judge_column:
            row.append(score_text)
        row.append(mode_text)
        table.add_row(*row)

    console.print(table)

    # Degraded-judge caveat, same as the single-run display. It was missing
    # here, which is the run where it matters more: --runs N is what a user
    # reaches for to measure reproducibility, and this is the notice saying
    # the judge's own scores are not reproducible.
    _print_degraded_judge_notice(judge_results)
    console.print()

    # Per-cell expanded view: list every run's output beneath its cell header.
    for key, cell_states, _stats in cell_stats:
        model, temp, sp = key
        header = (
            f"[bold cyan]>[/bold cyan] [bold]{escape(model)}[/bold] @ {temp:.1f}"
        )
        if show_sp_column and sp and sp in prompt_indices:
            header += f"  [magenta]SP {prompt_indices[sp]}[/magenta]"
        console.print(header)
        for s in cell_states:
            tag = f"  [dim]run {s.run_index + 1}/{runs}:[/dim]"
            if s.error:
                console.print(f"{tag} [red]{escape(s.error)}[/red]")
            else:
                lines = s.text.splitlines() or [""]
                console.print(f"{tag} {escape(lines[0])}")
                for line in lines[1:]:
                    console.print(f"          {escape(line)}")
        if include_reasoning and judge_results is not None:
            for s in cell_states:
                jr = judge_by_state_id.get(id(s))
                if jr is None:
                    continue
                for j in jr.judges:
                    score_str = j.score if j.score is not None else "?"
                    if j.parse_error:
                        console.print(
                            f"  [magenta dim]judge {escape(j.model)}: parse error - "
                            f"{escape(str(j.parse_error))}[/magenta dim]"
                        )
                    else:
                        console.print(
                            f"  [magenta dim]judge {escape(j.model)} ({score_str}/10): "
                            f"{escape(str(j.reasoning))}[/magenta dim]"
                        )
                # Mode-only judging: one verdict per cell, no need to repeat.
                if runs > 1 and not hallucination_mode:
                    break
        console.print()

    console.print(f"[dim]Total cost across all runs: ${grand_total_cost:.6f}[/dim]")
    if judge_results is not None:
        j_cost = total_judge_cost(judge_results)
        j_calls = total_judge_calls(judge_results)
        console.print(
            f"[dim]Judge cost: ${j_cost:.6f} "
            f"({j_calls} judge call{'s' if j_calls != 1 else ''})[/dim]"
        )
    if hallucination_mode and hallucination_facts:
        console.print(
            f"[dim]Hallucination check: "
            f"{len(hallucination_facts)} reference fact"
            f"{'s' if len(hallucination_facts) != 1 else ''} provided[/dim]"
        )
    console.print(
        "[dim]Coefficient of variation (CV) < 0.05 indicates stable model behavior.[/dim]"
    )
    console.print(f"[dim]{pricing_freshness_note()}[/dim]")

    if stats_by_cell_cis:
        _display_confidence_intervals(stats_by_cell_cis)

    if significance_results:
        _display_significance(significance_results)

    if mcnemar_results:
        _display_mcnemar(mcnemar_results)


def _display_confidence_intervals(stats_by_cell_cis: dict) -> None:
    """Render bootstrap CIs on per-cell means below the runs table.

    One line per cell, labelled the way the runs table above labels its rows -
    model, temperature, and `SP N` when more than one system prompt is in play.
    A bare model name identified nothing once the same model appeared in
    several cells.
    """
    if not stats_by_cell_cis:
        return
    has_any = any(metrics for metrics in stats_by_cell_cis.values())
    if not has_any:
        return

    prompt_indices = ci_prompt_indices(stats_by_cell_cis.keys())
    console.print()
    console.print("[bold]Bootstrap Confidence Intervals[/bold]")
    for key, metrics in stats_by_cell_cis.items():
        if not metrics:
            continue
        parts: list[str] = []
        for metric_name in CI_METRIC_ORDER:
            ci = metrics.get(metric_name)
            if ci is None:
                continue
            label = CI_CONSOLE_LABELS[metric_name]
            level_pct = int(round(ci["ci_level"] * 100))
            low = format_ci_value(metric_name, ci["ci_low"])
            high = format_ci_value(metric_name, ci["ci_high"])
            parts.append(f"{label} [{level_pct}% CI: {low}, {high}]")
        if parts:
            console.print(f"  {escape(ci_cell_label(key, prompt_indices))}: " + " | ".join(parts))


def _mcnemar_caveat_markup(affected: list[tuple[str, int]]) -> str:
    """The McNemar decline caveat, wrapped for Rich with the model ids escaped.

    A model id is user-supplied - OpenRouter and `local/` ids are freeform - and
    this console site parses markup. An id carrying a stray closing tag raises
    MarkupError rather than merely rendering oddly.
    """
    return f"[yellow]{escape(mcnemar_pairing_caveat(affected))}[/yellow]"


def _significance_caveat_markup(affected: list[tuple[str, int]]) -> str:
    """The significance decline caveat, wrapped for Rich with the ids escaped.

    The twin of `_mcnemar_caveat_markup` above, and it exists for the same
    reason: the caveat names model ids, a model id is user-supplied, and this
    console site parses markup. The two caveats say different things - see
    `mcnemar_pairing_caveat` - but they are equally unsafe to print raw.
    """
    return f"[yellow]{escape(significance_refusal_caveat(affected))}[/yellow]"


def _display_mcnemar(mcnemar_results: list) -> None:
    """Render McNemar test results for paired binary outcomes."""
    if not mcnemar_results:
        return

    console.print()
    console.print("[bold]Binary Outcome Significance (McNemar)[/bold]")
    first = mcnemar_results[0]
    console.print(
        f"[dim]Metric: hallucination pass/fail | Correction: "
        f"{first.correction_method} | Threshold: p < {first.threshold}[/dim]"
    )
    n_untestable = getattr(first, "n_pairs_untestable", 0)
    if n_untestable:
        console.print(
            f"[yellow]{untestable_pairs_notice(n_untestable, len(mcnemar_results))}"
            f"[/yellow]"
        )
    affected = refused_arms(mcnemar_results)
    if affected:
        # Not the significance caveat: this test drops declines rather than
        # consuming them, so the two say different things.
        console.print(_mcnemar_caveat_markup(affected))

    for r in mcnemar_results:
        if getattr(r, "n_paired", 0) == 0:
            console.print(
                f"  {escape(r.model_a)} vs {escape(r.model_b)}: "
                f"no runs in common (nothing to compare)"
            )
            continue
        if r.n_discordant == 0:
            console.print(
                f"  {escape(r.model_a)} ({r.a_pass_rate:.0%} pass) vs "
                f"{escape(r.model_b)} ({r.b_pass_rate:.0%} pass): "
                f"no discordant runs of {r.n_paired} paired (test undefined)"
            )
            continue
        sig_marker = "*" if r.significant_at_threshold else ""
        p_display = (
            r.p_value_corrected if r.p_value_corrected is not None else r.p_value
        )
        method_label = {
            "exact_binomial": "exact",
            "edwards_chi2": "Edwards",
        }.get(r.method, r.method)
        console.print(
            f"  {escape(r.model_a)} ({r.a_pass_rate:.0%} pass) vs "
            f"{escape(r.model_b)} ({r.b_pass_rate:.0%} pass): "
            f"p={p_display:.4f}{sig_marker} "
            f"({method_label}, {r.n_paired} paired, discordant={r.n_discordant})"
        )


def _display_significance(significance_results: list) -> None:
    """Render pairwise statistical significance results below the runs table.

    Display strategy depends on the number of models:
      * 2 models: single-line summary
      * 3-5 models: matrix table
      * 6+ models: top-K significant pairs (full matrix in JSON)
    """
    if not significance_results:
        return

    models = sorted(
        {r.model_a for r in significance_results}
        | {r.model_b for r in significance_results}
    )
    n_models = len(models)
    first = significance_results[0]

    console.print()
    console.print("[bold]Statistical Significance Tests[/bold]")
    console.print(
        f"[dim]Metric: {first.metric} | Test: {first.test_used} | "
        f"Correction: {first.correction_method} | Threshold: p < {first.threshold}[/dim]"
    )
    # Both notices print before the verdicts rather than after, so they are read
    # first and so they render once whichever of the three display branches below
    # runs. Read through getattr: the display stubs in tests/ carry the fields
    # that predate this one.
    n_untestable = getattr(first, "n_pairs_untestable", 0)
    if n_untestable:
        console.print(
            f"[yellow]{untestable_pairs_notice(n_untestable, len(significance_results))}"
            f"[/yellow]"
        )

    affected = refused_arms(significance_results)
    if affected:
        console.print(_significance_caveat_markup(affected))

    if n_models == 2:
        r = significance_results[0]
        if r.p_value is None:
            console.print(
                f"  {escape(r.model_a)} vs {escape(r.model_b)}: "
                f"{r.test_used} (no p-value)"
            )
        else:
            sig_marker = "*" if r.significant_at_threshold else ""
            p_display = (
                r.p_value_corrected if r.p_value_corrected is not None else r.p_value
            )
            d_text = (
                f", d={r.effect_size:.3f} ({r.effect_size_interpretation})"
                if r.effect_size is not None
                else ""
            )
            avg_a = f"{r.mean_a:.3f}" if r.mean_a is not None else "no data"
            avg_b = f"{r.mean_b:.3f}" if r.mean_b is not None else "no data"
            console.print(
                f"  {escape(r.model_a)} (avg {avg_a}) vs "
                f"{escape(r.model_b)} (avg {avg_b}): "
                f"p={p_display:.4f}{sig_marker}{d_text}"
            )
        return

    if n_models <= 5:
        table = Table(title="Pairwise p-values (corrected)", border_style="dim")
        table.add_column("Model", style="cyan")
        for m in models:
            # A Table header is rendered as markup exactly like a printed
            # string, so an id carrying a stray closing tag crashes here too.
            table.add_column(escape(m), justify="right")

        result_map: dict[tuple[str, str], object] = {}
        for r in significance_results:
            result_map[(r.model_a, r.model_b)] = r
            result_map[(r.model_b, r.model_a)] = r

        for m_a in models:
            # Escaped for display only - the lookup below keys on the raw id.
            row = [escape(m_a)]
            for m_b in models:
                if m_a == m_b:
                    row.append("-")
                    continue
                r = result_map.get((m_a, m_b))
                if r is None or r.p_value is None:  # type: ignore[union-attr]
                    row.append("-")
                else:
                    p = (
                        r.p_value_corrected  # type: ignore[union-attr]
                        if r.p_value_corrected is not None  # type: ignore[union-attr]
                        else r.p_value  # type: ignore[union-attr]
                    )
                    marker = "*" if r.significant_at_threshold else ""  # type: ignore[union-attr]
                    row.append(f"{p:.4f}{marker}")
            table.add_row(*row)

        console.print(table)
        console.print("[dim]* = significant after correction[/dim]")
        return

    # 6+ models: top-K significant
    significant = [r for r in significance_results if r.significant_at_threshold]
    significant.sort(key=lambda x: x.p_value_corrected or 1.0)
    top_k = significant[:5]

    if top_k:
        console.print(
            f"[bold]Top significant pairs (of {len(significant)} total):[/bold]"
        )
        for i, r in enumerate(top_k, 1):
            p = r.p_value_corrected if r.p_value_corrected is not None else r.p_value
            d_text = (
                f", d={r.effect_size:.3f} ({r.effect_size_interpretation})"
                if r.effect_size is not None
                else ""
            )
            console.print(
                f"  {i}. {escape(r.model_a)} vs {escape(r.model_b)}: "
                f"p={p:.4f}{d_text}"
            )
    else:
        console.print("[dim]No statistically significant pairs found.[/dim]")

    console.print("[dim]Full matrix available in JSON output.[/dim]")


def _print_degraded_judge_notice(judge_results: list[JudgeResult] | None) -> None:
    """Warn that a judge's scores are not reproducible, if any judge degraded.

    The console user is the primary audience, so this renders real text rather
    than reusing the Score-column plumbing, which never displayed
    skipped_models at all. Shared by the single-run and multi-run displays: it
    lived in only one of them, and the multi-run one is where a reader is
    explicitly measuring reproducibility.
    """
    if judge_results is None:
        return
    degraded = sorted({m for jr in judge_results for m in jr.degraded_models})
    if not degraded:
        return
    console.print(
        f"[yellow]Note: judge determinism not guaranteed for "
        f"{', '.join(degraded)}. These models reject a temperature "
        f"setting, so the judge ran at the provider default instead of "
        f"0.0 and its scores are not reproducible run to run.[/yellow]"
    )


def _score_cell_for_compare(jr: JudgeResult) -> str:
    """Render the Score column cell for the compare command's results table."""
    if not jr.judges:
        return "[dim]-[/dim]"
    successful = [j for j in jr.judges if j.score is not None]
    if not successful:
        return "[red]N/A[/red]"
    if len(jr.judges) == 1 and successful:
        # Single judge: just the score.
        return str(successful[0].score)
    # Panel: average + how many of the panel it was taken over. A bare "(1)"
    # after a three-judge average is indistinguishable from a single-judge
    # panel that answered, so two of three judges failing to parse read as a
    # complete result. std_dev is None at n=1 for the same reason and says
    # nothing on this line, so the count is the only place it can show.
    if jr.average_score is not None:
        if len(successful) < len(jr.judges):
            return f"{jr.average_score:.1f} ({len(successful)} of {len(jr.judges)})"
        return f"{jr.average_score:.1f} ({len(successful)})"
    return "[red]N/A[/red]"


_RISK_COLOR = {"Low": "green", "Medium": "yellow", "High": "red"}


def _risk_cell_for_compare(jr: JudgeResult) -> str:
    """Render the Hallucination Risk cell for one row.

    Single judge: "[Low] (8)" colorized by risk level.
    Panel: worst-case risk + score range, e.g. "[High] (3-7)".
    No data: dim dash.
    """
    if not jr.judges:
        return "[dim]-[/dim]"
    successful = [j for j in jr.judges if j.score is not None and j.risk_level]

    risk = jr.aggregated_risk_level or "?"
    color = _RISK_COLOR.get(risk, "magenta")

    if not successful:
        # A judge can classify the risk and still return no parsable score.
        # `aggregated_risk_level` - the value JSON reports - only needs the
        # classification, so the console said "N/A" for a row the JSON called
        # High. Show the risk; say only the score is missing.
        if jr.aggregated_risk_level is not None:
            return f"[{color}]{risk}[/{color}] (no score)"
        return "[red]N/A[/red]"

    if len(successful) == 1:
        s = successful[0]
        return f"[{color}]{s.risk_level}[/{color}] ({s.score})"

    scores = sorted(j.score for j in successful if j.score is not None)
    if scores[0] == scores[-1]:
        score_text = str(scores[0])
    else:
        score_text = f"{scores[0]}-{scores[-1]}"
    return f"[{color}]{risk}[/{color}] ({score_text}, n={len(successful)})"


def _cost_ceiling_message(ledger: CostLedger) -> str:
    """What the user is told when the ceiling stopped the run.

    Deliberately says STOPPED FURTHER DISPATCH rather than "prevented spend".
    A request already with a provider cannot be recalled, and this design
    finishes it rather than abandoning it - abandoning would lose its cost and
    make the reported total smaller than the bill. So the honest claim is that
    no further cell was started, and the figure quoted is what was measured.
    """
    return (
        f"Cost ceiling reached: spent ${ledger.spent:.6f} against "
        f"--max-cost ${ledger.ceiling:.6f}.\n"
        f"  Stopped dispatching; {ledger.skipped} call"
        f"{'s were' if ledger.skipped != 1 else ' was'} never started.\n"
        f"  Calls already sent to a provider were allowed to finish, so the "
        f"total above is what was actually measured - the ceiling bounds "
        f"further dispatch, not spend already committed."
    )


def _print_error(message: str) -> None:
    """Print an error inside a red-bordered panel.

    ESCAPE IS LAST AND THE ORDER IS THE WHOLE FIX. `redact_secrets` substitutes
    key-shaped text, so it can SYNTHESISE a Rich tag: its `\\S+` swallows an
    intervening bracket and what is left parses as one. Escaping first therefore
    walks past a tag that does not exist yet, and Rich eats the message -
    measured on `[x-goog-api-key: AQ.Ab...abcd[not a tag]`, which rendered as an
    empty panel. Redacting first and escaping the result cannot go wrong,
    because nothing runs after the escape.

    Escaping does not weaken redaction in either order (56,000 fuzz cases over
    all fourteen rules, zero survivals), and redaction is idempotent, so the
    three callers that redact before calling here are harmless.

    No caller may pass Rich markup - the message is now shown as text. A test
    asserts that across every call site.
    """
    console.print(
        Panel(escape(redact_secrets(message)), title="Error", border_style="red")
    )


def run() -> None:
    """Console entry point: redact the traceback of an unhandled crash.

    Every provider error already arrives redacted - all four `_reraise` shapes
    call `redact_secrets` and re-raise `from None`, so the SDK exception never
    reaches a traceback. What was uncovered is a crash OUTSIDE that path, where
    Python prints the traceback itself and nothing scrubs it.

    Only one SDK stringifies a key at all: `google.genai.APIError` includes the
    response body, and `httpx.HTTPStatusError` formats the request URL - and
    Google is the one provider that carries its key in the URL. Anthropic and
    OpenAI stringify neither headers nor body, so the exposure is narrow, but
    it is not empty.

    The traceback is reprinted in full rather than replaced with a summary
    line. It is the only thing that localises a crash, and a one-line message
    would trade a leak for an unreportable bug. `SystemExit` (which is how
    click returns every exit code) and `KeyboardInterrupt` are not caught.
    """
    try:
        main()
    except Exception:  # noqa: BLE001 - re-raised as a redacted traceback below
        formatted = "".join(traceback.format_exception(*sys.exc_info()))
        print(redact_secrets(formatted), file=sys.stderr, end="")
        # Matches the exit code an unredacted traceback already produced, so
        # this changes what is printed and nothing else.
        sys.exit(1)


if __name__ == "__main__":
    run()
