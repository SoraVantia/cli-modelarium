"""Parallel streaming orchestration for the compare command.

This module owns the per-call lifecycle for a comparison run:

    * one semaphore per provider (rate-limit hygiene)
    * 429 retry with exponential backoff (respects `retry-after`)
    * 529 (Anthropic overloaded) retry with a longer backoff than 429
    * live token-by-token display via Rich Live
    * accurate TTFT measurement (timestamps captured at the orchestrator
      level, after the semaphore has been acquired - so "queued behind other
      tasks" does not pollute the metric)

`run_streaming_comparison()` is the only public entry point. cli.py routes
both `--stream` and `--no-stream` through it - the only difference is
whether the Live display is enabled (`live_display=False` for --no-stream).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from cli_modelarium.exceptions import (
    ModelariumError,
    ProviderOverloadedError,
    RateLimitError,
)
from cli_modelarium.models_registry import get_provider_for_model
from cli_modelarium.pricing import is_local_model
from cli_modelarium.providers.base import BaseProvider, CompletionResult
from cli_modelarium.security import redact_secrets

# One value applied to every provider, which cannot be right for all of them:
# Moonshot's Tier0 allows 1 concurrent request and its Tier1 allows 50. 5 is
# low enough not to trip the strictest tier on a small run and high enough to
# be worth having. --concurrency overrides it per run.
DEFAULT_CONCURRENCY = 5

# Retries, not attempts: `range(max_retries + 1)` makes this four tries, so a
# failing cell sleeps three times before it gives up. That count is the
# ceiling; the elapsed time has none. With RATE_LIMIT_BASE_DELAY_SECONDS
# doubling each time, a 429 carrying no `retry-after` spends about seven
# seconds (1 + 2 + 4), and the 529 path, which never reads the header, spends
# 35 (5 + 10 + 20). A header that IS sent is honoured as given:
# `_retry_after_seconds` returns `float(raw)` and nothing clamps it, so a
# `Retry-After: 3600` on each of the three sleeps holds one cell for three
# hours, which is indistinguishable from a hang. No flag bounds the wait or
# the attempt count.
DEFAULT_MAX_RETRIES = 3

# Auto-collapse threshold for the live streaming display. Above this many
# concurrent tasks the per-task panels won't fit on a normal terminal, so
# we silently disable Live and print a one-line notice. The user can force
# the expanded view back on with --show-all-runs.
AUTO_COLLAPSE_TASK_THRESHOLD = 12

# Backoff schedule for 429 rate limits. Used when the response has no
# retry-after header. When the header is present, we honor it verbatim and
# this schedule still advances for the next attempt.
RATE_LIMIT_BASE_DELAY_SECONDS = 1.0

# Backoff schedule for Anthropic 529 (service overloaded). Retrying
# immediately does not help while the upstream is over-capacity, so the
# base delay is longer than for 429.
OVERLOADED_BASE_DELAY_SECONDS = 5.0


# Possible state.status values:
#   pending     - task created, not yet entered
#   waiting     - semaphore acquired, request in flight, no chunks yet
#   streaming   - at least one chunk has arrived
#   retrying    - 429/529 hit; sleeping before retry
#   complete    - call finished successfully
#   error       - call failed (after all retries)
Status = str


class CostLedger:
    """Running total of known spend against the user's `--max-cost` ceiling.

    THE CAP STOPS FURTHER DISPATCH. IT DOES NOT PREVENT SPEND, and every part of
    this design follows from that. A request already sent to a provider cannot
    be un-sent, and cancelling it mid-stream is worse than useless: usage is
    read inside the provider's chunk loop, so an abandoned call never yields its
    cost and would report $0.00 for work that really happened. The run's total
    would then be smaller than the bill.

    So a dispatched cell is always finished. Only cells not yet started are
    skipped. The cost of that choice is a bounded overshoot - at most
    `concurrency - 1` extra cells beyond the ceiling, measured at 10% serially,
    50% at the default concurrency of 5, and 100% at 10 - and its benefit is
    that every number the run reports is one it actually measured.

    Shared across BOTH gathers. Judge calls have their own per-provider
    semaphores and run after the main pass, and their cost lands on `JudgeScore`
    rather than on a `StreamState`, so a ledger living on the state would count
    none of it.

    No lock. Single-threaded asyncio makes `+=` atomic because no await sits
    inside the statement; measured at 20 tasks x 10,000 increments with an
    explicit yield between each, zero updates are lost.
    """

    def __init__(self, ceiling: float | None) -> None:
        self._ceiling = ceiling
        self._spent = 0.0
        self._skipped = 0

    @property
    def spent(self) -> float:
        """Total of every cost this ledger was told about."""
        return self._spent

    @property
    def ceiling(self) -> float | None:
        return self._ceiling

    @property
    def skipped(self) -> int:
        """Calls never dispatched because the ceiling had been passed.

        Counted here rather than by inspecting states, because a skipped JUDGE
        call has no `StreamState` to inspect - counting states alone reported
        "0 calls were never started" on a run whose judge phase was cut short.
        """
        return self._skipped

    def skip(self) -> None:
        self._skipped += 1

    @property
    def exhausted(self) -> bool:
        """True once the ceiling has been reached, so no further cell starts.

        `>` rather than `>=`, matching the pre-flight's `estimated > max_cost`.
        The same flag must not change operator between the estimate and the run.
        It also keeps `--max-cost 0` meaning "free models only": with `>=`, a
        zero ceiling is exhausted before the first call and the 17 zero-cost
        registry rows never run, even though they can never cost anything.

        The price is one extra cell at a positive ceiling - spending exactly the
        ceiling does not stop the next dispatch - which is inside the overshoot
        the concurrency already implies.
        """
        if self._ceiling is None:
            return False
        return self._spent > self._ceiling

    def add(self, cost: float) -> None:
        """Record a cell's real, measured cost."""
        self._spent += cost


@dataclass
class StreamState:
    """Per-task state surfaced live in the streaming display.

    Mutated in place by `_run_one()` so the Rich Live renderable can read
    the current state on every refresh.
    """

    model: str
    provider_name: str
    temperature: float
    system_prompt: str | None = None
    run_index: int = 0
    status: Status = "pending"
    text: str = ""
    ttft_ms: float | None = None
    latency_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    # Set when the provider declined the request: HTTP 200, real cost, no
    # answer. Deliberately NOT folded into `error` - see CompletionResult.
    refused: bool = False
    stop_reason: str | None = None
    stop_category: str | None = None
    # The cost ceiling stopped this cell before it returned. Its cost is
    # UNKNOWN rather than zero: usage is read inside the provider's chunk loop,
    # so a cancelled call never yields it and `mark_complete` never runs - while
    # the provider did the work regardless. Reporting 0.0 would understate the
    # run's total, which is worse than reporting nothing.
    cost_unknown: bool = False
    retry_message: str | None = None
    attempts: int = 0  # number of retries attempted (0 == first call only)
    _start: float | None = field(default=None, repr=False)

    def mark_started(self) -> None:
        self._start = time.monotonic()
        self.status = "waiting"

    def mark_attempt_start(self) -> None:
        """Re-base the TTFT clock for a retry attempt.

        `mark_started` runs once per cell, before the first attempt. Without
        this, `_start` keeps that original instant and `append_text`
        recomputes TTFT against it on the attempt that finally succeeds -
        so the reported figure absorbs every failed attempt AND every
        backoff sleep. Measured: 650 ms reported after a single retry whose
        true time-to-first-token was near zero.

        That mattered because rate limiting is not random: it correlates
        with provider and model, so the inflation landed on whichever model
        was throttled and silently reordered a latency comparison.

        `latency_ms` needs no equivalent: it is taken from
        `CompletionResult`, which every provider measures around its own
        attempt, so it already excludes retry time. TTFT now matches it.
        """
        self._start = time.monotonic()

    def append_text(self, chunk: str) -> None:
        """Callback hook passed as `on_chunk=` to provider.complete()."""
        if self.ttft_ms is None and self._start is not None:
            self.ttft_ms = (time.monotonic() - self._start) * 1000
        self.status = "streaming"
        self.text += chunk

    def mark_complete(self, result: CompletionResult) -> None:
        self.refused = result.refused
        self.stop_reason = result.stop_reason
        self.stop_category = result.stop_category
        # "refused" is a third terminal status beside complete and error: the
        # call succeeded and was billed, but produced no answer.
        self.status = "refused" if result.refused else "complete"
        self.input_tokens = result.input_tokens
        self.output_tokens = result.output_tokens
        self.cached_tokens = result.cached_tokens
        self.cost_usd = result.cost_usd
        self.latency_ms = result.latency_ms
        # The provider measures TTFT and latency off the SAME per-attempt
        # clock (its own `start` inside `complete()`), so its TTFT is
        # authoritative and OVERWRITES the orchestrator estimate rather
        # than only filling in for it. `append_text` sets that estimate as
        # chunks arrive so the live display has something to show mid-call;
        # it is measured from a different instant and must not win at the
        # end. Guarded on None only because a provider may not report one,
        # in which case the estimate is all there is.
        if result.ttft_ms is not None:
            self.ttft_ms = result.ttft_ms

    def mark_cancelled(self) -> None:
        """Stopped by the cost ceiling before the provider returned.

        A fourth terminal status beside complete, refused and error. It is not
        folded into `error`: nothing failed, and `error` drives assertion
        skipping, exit codes and the statistics' `billed` filter, all of which
        need to tell "the call broke" from "we stopped waiting for it".

        `retry_message` is cleared because a cell cancelled during a backoff
        sleep would otherwise render as still retrying forever.
        """
        self.status = "cancelled"
        self.cost_unknown = True
        self.retry_message = None

    def mark_error(self, message: str) -> None:
        self.status = "error"
        self.error = redact_secrets(message)

    def mark_retry(self, attempt: int, delay_s: float, reason: str) -> None:
        self.status = "retrying"
        self.attempts = attempt + 1
        self.retry_message = f"{reason}, retry in {delay_s:.1f}s (attempt {attempt + 1})"


def index_distinct_prompts(systems: Iterable[str | None]) -> dict[str, int]:
    """1-based indices for distinct system prompts, in first-seen order.

    THE ONE NUMBERING. Three callers label system prompts `SP N` over three
    different populations - the console runs table over states, the Markdown CI
    section over CI cell keys, the Markdown report over results - and they must
    agree, because a reader matches `SP 2` in one table against `SP 2` in
    another. Written once here so they can differ in population and never in
    logic.

    Empty and None are not assigned an index: there is no prompt to name. The
    "is it worth showing" rule is deliberately NOT applied here, because it
    differs by caller - see `prompt_index_map` for the two-or-more rule and
    `md_prompt_indices` for the one that counts a missing prompt as distinct.
    """
    seen: dict[str, int] = {}
    for system in systems:
        if system and system not in seen:
            seen[system] = len(seen) + 1
    return seen


def prompt_index_map(states: list[StreamState]) -> dict[str, int]:
    """Build an order-preserving map of distinct system prompts to 1-based indices.

    Empty/None system prompts are not assigned indices. Returned map is
    empty if zero or one distinct non-empty system prompts are in play -
    that signals "don't bother showing per-row prompt identifiers".
    """
    seen = index_distinct_prompts(s.system_prompt for s in states)
    return seen if len(seen) > 1 else {}


def render_prompt_legend(states: list[StreamState]) -> Table | None:
    """Build a Rich Table mapping `SP N` indices to truncated prompt previews.

    Returns None if there's nothing to legend (single or zero prompts).
    """
    indices = prompt_index_map(states)
    if not indices:
        return None
    table = Table(
        title="System prompts in use",
        border_style="dim",
        title_justify="left",
        show_header=False,
    )
    table.add_column("Index", style="bold magenta")
    table.add_column("Preview")
    for prompt, idx in indices.items():
        preview = prompt if len(prompt) <= 60 else prompt[:57] + "..."
        # Replace newlines so a multiline system prompt stays on one row.
        preview = preview.replace("\n", " / ")
        # Escaped AFTER the truncation above, so the slice still measures the
        # prompt rather than the backslashes. This table is printed outside the
        # `Live` block, so it renders on the --no-stream path too.
        table.add_row(f"SP {idx}", escape(preview))
    return table


class StreamingDisplay:
    """Rich renderable. `__rich__` is re-evaluated on every Live refresh."""

    def __init__(self, states: list[StreamState]) -> None:
        self.states = states
        self._prompt_indices = prompt_index_map(states)

    def __rich__(self) -> Group:
        return Group(*[self._panel(s) for s in self.states])

    def _panel(self, state: StreamState) -> Panel:
        if state.status == "pending":
            status_text = "[dim]queued[/dim]"
        elif state.status == "waiting":
            status_text = "[cyan]connecting...[/cyan]"
        elif state.status == "streaming":
            ttft_text = f"TTFT {state.ttft_ms / 1000:.2f}s" if state.ttft_ms is not None else ""
            status_text = f"[cyan]streaming[/cyan]  [dim]{ttft_text}[/dim]"
        elif state.status == "retrying":
            retry = escape(state.retry_message) if state.retry_message else "retrying"
            status_text = f"[yellow]{retry}[/yellow]"
        elif state.status == "complete":
            parts: list[str] = []
            if state.ttft_ms is not None:
                parts.append(f"TTFT {state.ttft_ms / 1000:.2f}s")
            # Local models show "Free" - a visual distinction from $0.000000.
            if is_local_model(state.model):
                parts.append("Free")
            else:
                parts.append(f"${state.cost_usd:.6f}")
            status_text = f"[green]done[/green]  [dim]{'  '.join(parts)}[/dim]"
        elif state.status == "refused":
            # The cost is shown because a refusal is billed. The category is
            # rendered verbatim - it is an open set and never branched on - and
            # `escape` is what makes "verbatim" true. Unescaped, Rich consumed
            # the value as markup: a category of `a[b]c` rendered as `ac`, and
            # one containing a `[link=...]` tag became a live terminal
            # hyperlink. The provider chooses this string, so it is escaped
            # rather than trusted.
            cat = f"  {escape(state.stop_category)}" if state.stop_category else ""
            status_text = f"[yellow]refused{cat}[/yellow]  [dim]${state.cost_usd:.6f}[/dim]"
        elif state.status == "error":
            status_text = "[red]error[/red]"
        else:
            status_text = escape(state.status)

        # When multiple distinct system prompts are in play, identify which
        # one this panel is for. We use the index (cheap, deterministic) and
        # put the full text in a one-time legend above the Live block.
        sp_marker = ""
        if state.system_prompt and self._prompt_indices:
            idx = self._prompt_indices.get(state.system_prompt)
            if idx is not None:
                sp_marker = f"  [magenta]SP {idx}[/magenta]"

        # Each untrusted value is escaped AT ITS OWN INTERPOLATION, never as a
        # composed string: `status_text` above already carries an escaped
        # `stop_category`, and escaping the whole title would escape it twice -
        # `escape(escape("a[b]c"))` is `a\\\[b]c`, two visible backslashes.
        title = (
            f"[bold]{escape(state.model)}[/bold] @ "
            f"{state.temperature:.1f}{sp_marker}   {status_text}"
        )

        # The body is the widest untrusted surface in the program: it is the
        # model's own output, rendered live. A model answering a question about
        # markup - "you close a tag with [/]" - raised MarkupError here, mid
        # stream, after the call had been billed.
        if state.error:
            body = f"[red]{escape(state.error)}[/red]"
        elif state.status == "streaming":
            body = escape(state.text) + "[cyan]▌[/cyan]"
        elif state.status in ("pending", "waiting"):
            body = "[dim]...[/dim]"
        else:
            body = escape(state.text) if state.text else "[dim](no output)[/dim]"

        border_style = {
            "complete": "green",
            "error": "red",
            "refused": "yellow",
            "retrying": "yellow",
            "streaming": "cyan",
        }.get(state.status, "dim")

        return Panel(body, title=title, title_align="left", border_style=border_style)


async def _call_with_retry(
    provider: BaseProvider,
    state: StreamState,
    prompt: str,
    max_retries: int,
    sleep: Callable[[float], asyncio.Future[None]] = asyncio.sleep,
) -> CompletionResult:
    """Run `provider.complete()` with 429/529 retry, updating state.

    `state.system_prompt` is forwarded to the provider on every attempt.
    `sleep` is parameterised so tests can monkeypatch it to make backoff
    instantaneous.
    """
    rate_limit_delay = RATE_LIMIT_BASE_DELAY_SECONDS
    overloaded_delay = OVERLOADED_BASE_DELAY_SECONDS

    # Treat empty system prompts as "no system prompt at all": an empty
    # --system-prompt must not reach the provider as a blank system message.
    effective_system_prompt = state.system_prompt or None

    for attempt in range(max_retries + 1):
        if attempt:
            # After the backoff sleep, not before it: this attempt is timed
            # from here, so the sleep is excluded from its TTFT.
            state.mark_attempt_start()
        try:
            return await provider.complete(
                prompt=prompt,
                model=state.model,
                temperature=state.temperature,
                system_prompt=effective_system_prompt,
                on_chunk=state.append_text,
            )
        except RateLimitError as e:
            if attempt >= max_retries:
                raise
            wait = e.retry_after if e.retry_after is not None else rate_limit_delay
            state.mark_retry(attempt, wait, reason="rate limited")
            # Reset partial text so retries don't show duplicated output.
            state.text = ""
            state.ttft_ms = None
            await sleep(wait)
            rate_limit_delay *= 2
        except ProviderOverloadedError:
            if attempt >= max_retries:
                raise
            wait = overloaded_delay
            state.mark_retry(attempt, wait, reason="provider overloaded")
            state.text = ""
            state.ttft_ms = None
            await sleep(wait)
            overloaded_delay *= 2

    # Loop exits via `return` or `raise`, never falls through.
    raise RuntimeError("unreachable: retry loop did not return or raise")


async def _run_one(
    provider: BaseProvider,
    state: StreamState,
    prompt: str,
    semaphore: asyncio.Semaphore,
    max_retries: int,
    ledger: CostLedger | None = None,
    sleep: Callable[[float], asyncio.Future[None]] = asyncio.sleep,
) -> None:
    """Run a single task to completion: semaphore -> retry loop -> state update."""
    async with semaphore:
        # Checked AFTER acquiring the semaphore, which is the last moment before
        # dispatch. A cell already past this point is always finished rather
        # than cancelled: abandoning it would lose its cost and understate the
        # run's total. See CostLedger.
        if ledger is not None and ledger.exhausted:
            ledger.skip()
            state.mark_cancelled()
            return
        state.mark_started()
        try:
            result = await _call_with_retry(
                provider=provider,
                state=state,
                prompt=prompt,
                max_retries=max_retries,
                sleep=sleep,
            )
            state.mark_complete(result)
            if ledger is not None:
                ledger.add(result.cost_usd)
        except ModelariumError as e:
            state.mark_error(str(e))
        except Exception as e:  # noqa: BLE001 - converted to error state, not re-raised
            state.mark_error(f"unexpected: {e}")


async def run_streaming_comparison(
    *,
    prompt: str,
    models: list[str],
    temperatures: list[float],
    system_prompts: list[str | None],
    provider_factory: Callable[[str], BaseProvider],
    console: Console | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_retries: int = DEFAULT_MAX_RETRIES,
    live_display: bool = True,
    ledger: CostLedger | None = None,
    runs: int = 1,
    show_all_runs: bool = False,
    sleep: Callable[[float], asyncio.Future[None]] = asyncio.sleep,
) -> list[StreamState]:
    """Run every (system_prompt x model x temperature) call in parallel.

    `system_prompts` is always a list. Pass `[None]` for "no system prompt".
    Pass multiple entries to run a matrix comparison (one task per
    combination of system_prompt, model, and temperature).

    Returns the list of `StreamState` in the same order as the cartesian
    product: outer loop over system prompts, then models, then temperatures.

    With `live_display=True` (the default) wraps the work in a Rich `Live`
    using `transient=True`, so the streaming panels disappear when the call
    completes and the caller can render a clean final summary. A legend
    mapping `SP N` to prompt previews is printed once before the Live
    block when multiple distinct prompts are in play.

    `provider_factory(name)` is called once per unique provider name to
    obtain the SDK client instance. Reused across all calls for that
    provider.
    """
    if console is None:
        # emoji=False for the same reason as the CLI console: escaping cannot
        # stop `:word:` substitution, and this display renders model output.
        console = Console(emoji=False)
    if not system_prompts:
        # Defensive: callers should pass [None] explicitly, but treat
        # missing/empty as "one task with no system prompt".
        system_prompts = [None]

    states: list[StreamState] = []
    for sp in system_prompts:
        for model in models:
            provider_name = get_provider_for_model(model)
            for temperature in temperatures:
                for run_idx in range(runs):
                    states.append(
                        StreamState(
                            model=model,
                            provider_name=provider_name,
                            temperature=temperature,
                            system_prompt=sp,
                            run_index=run_idx,
                        )
                    )

    # Auto-collapse: too many concurrent panels won't fit on a normal
    # terminal. Disable Live and print a one-line notice. --show-all-runs
    # forces the expanded view back on.
    if live_display and not show_all_runs and len(states) > AUTO_COLLAPSE_TASK_THRESHOLD:
        live_display = False
        console = console or Console(emoji=False)
        console.print(
            "[dim]Many concurrent tasks; live display disabled "
            "(use --show-all-runs to expand).[/dim]"
        )

    # One instance per provider, one semaphore per provider.
    provider_names = sorted({s.provider_name for s in states})
    instances: dict[str, BaseProvider] = {name: provider_factory(name) for name in provider_names}
    semaphores: dict[str, asyncio.Semaphore] = {
        name: asyncio.Semaphore(concurrency) for name in provider_names
    }

    tasks_coro = asyncio.gather(
        *[
            _run_one(
                provider=instances[s.provider_name],
                state=s,
                prompt=prompt,
                semaphore=semaphores[s.provider_name],
                max_retries=max_retries,
                ledger=ledger,
                sleep=sleep,
            )
            for s in states
        ]
    )

    # The legend (if any) is printed OUTSIDE the Live block so it survives
    # the transient=True cleanup and is still on screen alongside the
    # caller's final summary table.
    legend = render_prompt_legend(states)
    if legend is not None:
        console.print(legend)

    if live_display:
        display = StreamingDisplay(states)
        # transient=True clears the streaming panels on exit so the final
        # summary table the caller prints isn't shoved below leftover panels.
        with Live(display, console=console, refresh_per_second=10, transient=True):
            await tasks_coro
    else:
        await tasks_coro

    return states
