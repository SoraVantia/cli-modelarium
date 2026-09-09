"""Markdown could not tell two system prompts apart, and nothing caught it.

`_format_markdown` groups by `prompt_id` alone, took `items[0]` and printed one
`**System (default):**` line from it. Every other system prompt in the group
appeared NOWHERE in the report, and the rows carried no column to attribute
them. CSV kept all of them; this was Markdown-only, and it hit the default
console path too, which renders the same string through Rich.

THIS IS LIVE AT HEAD IN `batch`, not something a later change introduces:
`batch --system-prompts a,b,c` on one prompt fans out over a single
`BatchPrompt`, so all three land in one group. `compare` escaped it only
because `_states_to_compare_results` gives every state its own synthetic id.

`_format_markdown` ran 105 times across the suite and exactly one of those
invocations saw more than one distinct system prompt - and in that one they
belonged to two different prompt_ids, so they rendered in separate sections.
Hence the first test below, which is the one the suite did not have.
"""

from __future__ import annotations

from cli_modelarium.output_formatters import (
    BatchResult,
    _format_markdown,
    md_prompt_indices,
)

TERSE = "You are terse."
VERBOSE = "You are verbose and should explain every step at length."


def _r(system: str | None, output: str = "4", run: int = 0, pid: str = "math-1") -> BatchResult:
    return BatchResult(
        prompt_id=pid, prompt="what is 2+2?", system=system, model="gpt-5.5",
        temperature=0.0, latency_ms=42.0, ttft_ms=0.0, input_tokens=10,
        output_tokens=5, cached_tokens=0, cost_usd=0.000123, output=output,
        error=None, retries=0, provider="openai", run_index=run,
    )


def _rows(md: str) -> list[str]:
    return [line for line in md.splitlines() if line.startswith("| `gpt-5.5`")]


def _tags(md: str) -> list[str]:
    return [line for line in md.splitlines() if line.startswith("**`gpt-5.5")]


class TestRowsSharingAPromptIdAndDifferingOnlyInSystem:
    """THE TEST THE SUITE LACKED. It fails on HEAD via the batch path."""

    def test_the_rendered_rows_are_not_all_equal(self) -> None:
        md = _format_markdown([_r(TERSE), _r(VERBOSE, "The answer is four.")], runs=1)
        rows = _rows(md)
        assert len(rows) == 2
        assert rows[0] != rows[1], rows

    def test_the_output_block_tags_are_not_all_equal(self) -> None:
        md = _format_markdown([_r(TERSE), _r(VERBOSE, "The answer is four.")], runs=1)
        tags = _tags(md)
        assert len(tags) == 2
        assert tags[0] != tags[1], tags

    def test_every_system_prompt_appears_in_full(self) -> None:
        """No truncation. The nine READMEs promise the full system prompt, and
        two prompts sharing a long preamble would otherwise render identically.
        """
        md = _format_markdown([_r(TERSE), _r(VERBOSE)], runs=1)
        assert TERSE in md
        assert VERBOSE in md

    def test_the_misleading_default_label_is_gone_when_there_is_no_default(self) -> None:
        md = _format_markdown([_r(TERSE), _r(VERBOSE)], runs=1)
        assert "System (default)" not in md, md

    def test_a_single_system_prompt_keeps_the_old_line(self) -> None:
        """Every byte-identical-output promise survives: with nothing to tell
        apart, the section renders exactly as it did."""
        md = _format_markdown([_r(TERSE)], runs=1)
        assert f"**System (default):** {TERSE}" in md
        assert "**System prompts:**" not in md
        assert "| SP |" not in md


class TestTheRunColumn:
    def test_two_runs_of_one_cell_are_distinguishable(self) -> None:
        """Markdown emitted `run_index` on no surface, so two runs rendered as
        identical rows under identical tags."""
        md = _format_markdown([_r(None, "a", run=0), _r(None, "b", run=1)], runs=2)
        rows, tags = _rows(md), _tags(md)
        assert rows[0] != rows[1], rows
        assert tags[0] != tags[1], tags
        assert "| Run |" in md

    def test_a_single_run_gains_no_run_column(self) -> None:
        assert "| Run |" not in _format_markdown([_r(None)], runs=1)


class TestTheLegendIsScopedToItsGroup:
    """Computed over ALL results and emitted per group, a four-prompt batch
    repeats the whole file's system prompts under every prompt - including
    under one that ran with none."""

    def test_a_group_with_no_system_prompt_gets_no_legend(self) -> None:
        md = _format_markdown(
            [_r(TERSE, pid="p1"), _r(VERBOSE, pid="p1"), _r(None, pid="p2")], runs=1
        )
        after = md.split("## p2", 1)[1]
        assert "**System prompts:**" not in after, after
        assert TERSE not in after, after

    def test_the_group_that_needs_it_still_gets_it(self) -> None:
        md = _format_markdown(
            [_r(TERSE, pid="p1"), _r(VERBOSE, pid="p1"), _r(None, pid="p2")], runs=1
        )
        first = md.split("## p2", 1)[0]
        assert "**System prompts:**" in first
        assert TERSE in first and VERBOSE in first


class TestAMixOfHasOneAndHasNone:
    """`batch` can produce it - each prompt carries its own optional `system`.
    The console's two-or-more-named-prompts rule scores this as one and drops
    the column, leaving the rows indistinguishable."""

    def test_a_missing_system_prompt_counts_as_distinct(self) -> None:
        assert md_prompt_indices([_r(TERSE), _r(None)]) == {TERSE: 1}

    def test_the_rows_are_told_apart(self) -> None:
        md = _format_markdown([_r(TERSE), _r(None, "no system")], runs=1)
        rows = _rows(md)
        assert rows[0] != rows[1], rows
        assert "| SP 1 |" in rows[0]
        assert "| - |" in rows[1], rows[1]

    def test_one_distinct_value_is_still_nothing_to_show(self) -> None:
        assert md_prompt_indices([_r(TERSE), _r(TERSE)]) == {}
        assert md_prompt_indices([_r(None), _r(None)]) == {}


class TestThePerCellSummaryTable:
    """Its rows are keyed by (model, temperature, system) and it printed only
    model and temperature, so N system prompts produced N indistinguishable
    rows - the same table group 2 added OK/Ref/Fail to."""

    def test_it_carries_an_sp_column(self) -> None:
        md = _format_markdown(
            [_r(TERSE, run=0), _r(TERSE, run=1), _r(VERBOSE, run=0), _r(VERBOSE, run=1)],
            runs=2,
        )
        summary = md.split("## Per-cell statistical summary", 1)[1]
        rows = [line for line in summary.splitlines() if line.startswith("| `gpt-5.5`")]
        assert len(rows) == 2
        assert rows[0] != rows[1], rows
        assert "SP 1" in rows[0] and "SP 2" in rows[1]

    def test_one_system_prompt_leaves_it_unchanged(self) -> None:
        md = _format_markdown([_r(None, run=0), _r(None, run=1)], runs=2)
        summary = md.split("## Per-cell statistical summary", 1)[1]
        assert "| SP |" not in summary


class TestTheNumberingIsNotAThirdImplementation:
    def test_it_is_derived_from_the_one_core(self) -> None:
        from cli_modelarium.streaming import index_distinct_prompts

        assert index_distinct_prompts([TERSE, VERBOSE, TERSE]) == {TERSE: 1, VERBOSE: 2}
        assert md_prompt_indices([_r(TERSE), _r(VERBOSE)]) == {TERSE: 1, VERBOSE: 2}

    def test_it_agrees_with_the_console_numbering(self) -> None:
        """A reader matches `SP 2` in one table against `SP 2` in another."""
        from cli_modelarium.streaming import StreamState, prompt_index_map

        def _s(system: str) -> StreamState:
            st = StreamState(model="gpt-5.5", provider_name="openai", temperature=0.0)
            st.system_prompt = system
            return st

        console = prompt_index_map([_s(TERSE), _s(VERBOSE)])
        assert console == md_prompt_indices([_r(TERSE), _r(VERBOSE)])
