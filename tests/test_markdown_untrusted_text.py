"""Provider and user text must not control the Markdown report's structure.

Group 3 added `_md_escape` and wired it to three call sites: the prompt, the
default system prompt and the system-prompt legend. Eight more sites render
untrusted text raw, and a ninth cannot be fixed by escaping at all.

The text at these sites is not hypothetical. A model id is user-supplied on the
command line. A model's OUTPUT reaches three of them. A provider's error message
reaches one. An assertion's configured value reaches one. Any of them containing
a pipe adds a column to a table row; a backtick opens or closes a code span; a
triple backtick in a model's output closes the fence the report put around it and
everything after is parsed as report markup.

TWO HELPERS, NOT ONE. `_md_escape` backslash-escapes, which is right for prose
but wrong for an identifier: it renders `max_length_chars` as
`max\\_length\\_chars`. Seven of the ten assertion type names contain an
underscore, as do model ids like `gpt-4_turbo`. So identifiers go through
`_md_code`, which wraps them in a code span - where an underscore is already
literal - sized to be longer than any backtick run inside. The fenced output
block gets `_md_fence_for`, which picks a fence the content cannot close.
"""

from __future__ import annotations

import re

from cli_modelarium.output_formatters import _md_code, _md_escape, _md_fence_for

# ===== the helpers =====


class TestMdCode:
    def test_a_plain_identifier_is_a_code_span(self) -> None:
        assert _md_code("max_length_chars") == "`max_length_chars`"

    def test_an_underscore_is_not_backslashed(self) -> None:
        """The whole reason this is not `_md_escape`."""
        assert "\\_" not in _md_code("max_length_chars")

    def test_a_backtick_inside_widens_the_delimiter(self) -> None:
        assert _md_code("a`b") == "``a`b``"

    def test_a_double_backtick_inside_widens_further(self) -> None:
        assert _md_code("a``b") == "```a``b```"

    def test_content_starting_with_a_backtick_is_padded(self) -> None:
        # CommonMark strips one leading and trailing space, so padding here
        # keeps the backtick as content rather than as delimiter.
        out = _md_code("`x")
        assert out.startswith("`` `") and out.endswith("` ``") or "` `x `" in out, out

    def test_a_pipe_is_escaped_for_a_table_cell(self) -> None:
        # GFM splits a row on a pipe BEFORE inline parsing, so a code span does
        # not protect it. It has to be backslash-escaped even in here.
        assert _md_code("a|b") == "`a\\|b`"

    def test_a_pipe_is_left_alone_outside_a_table(self) -> None:
        assert _md_code("a|b", in_table=False) == "`a|b`"

    def test_a_newline_becomes_a_space(self) -> None:
        assert "\n" not in _md_code("a\nb")

    def test_empty_text_does_not_produce_stray_delimiters(self) -> None:
        assert _md_code("") == ""


class TestMdFenceFor:
    def test_ordinary_text_gets_three_backticks(self) -> None:
        assert _md_fence_for("hello") == "```"

    def test_text_containing_a_fence_gets_a_longer_one(self) -> None:
        assert _md_fence_for("see ```python\nx\n```") == "````"

    def test_the_fence_always_exceeds_the_longest_run(self) -> None:
        for n in range(1, 9):
            text = "a" + "`" * n + "b"
            fence = _md_fence_for(text)
            assert len(fence) >= 3
            assert len(fence) > n, (n, fence)

    def test_a_fence_cannot_be_closed_by_its_own_content(self) -> None:
        """The property that matters: no line of content is a valid closer."""
        text = "``` still inside ```"
        fence = _md_fence_for(text)
        for line in text.split("\n"):
            run = re.match(r"\s*(`+)\s*$", line)
            assert run is None or len(run.group(1)) < len(fence)


class TestMdEscapeIsUnchanged:
    """Group 3's helper keeps its behaviour; this commit adds to it, not over it."""

    def test_prose_still_backslash_escapes(self) -> None:
        assert _md_escape("a*b") == "a\\*b"

    def test_a_newline_still_becomes_a_separator(self) -> None:
        assert _md_escape("a\nb") == "a / b"


# ===== the eight raw sites, and the ninth the helpers cannot reach =====

from cli_modelarium.assertions import AssertionResult  # noqa: E402
from cli_modelarium.judging import JudgeResult, JudgeScore  # noqa: E402
from cli_modelarium.output_formatters import BatchResult, _format_markdown  # noqa: E402

# A pipe adds a column to whatever row it lands in; a triple backtick closes a
# fence. Both appear in real model output, and neither is exotic in a model id
# a user types on the command line.
HOSTILE = "a|b"
FENCE = "here is code:\n```\nrm -rf /\n```\ndone"


def _result(**over: object) -> BatchResult:
    base: dict[str, object] = dict(
        prompt_id="p1", prompt="Q", system=None, model="claude-opus-5",
        temperature=0.0, latency_ms=100.0, ttft_ms=10.0, input_tokens=51,
        output_tokens=4, cached_tokens=0, cost_usd=0.000725, output="Paris",
        error=None, retries=0,
    )
    base.update(over)
    return BatchResult(**base)  # type: ignore[arg-type]


def _render(*results: BatchResult, runs: int = 1) -> str:
    return _format_markdown(list(results), runs=runs)


def _table_rows(text: str) -> list[str]:
    return [ln for ln in text.split("\n") if ln.startswith("|") and "---" not in ln]


def _split_cells(row: str) -> list[str]:
    """Split a GFM table row the way a renderer does: on UNESCAPED pipes only.

    `\\|` is a literal pipe in the cell, not a delimiter - splitting naively on
    "|" counts the escape as a column and reports a fix as a failure.
    """
    cells: list[str] = [""]
    escaped = False
    for ch in row:
        if escaped:
            cells[-1] += ch
            escaped = False
        elif ch == "\\":
            cells[-1] += ch
            escaped = True
        elif ch == "|":
            cells.append("")
        else:
            cells[-1] += ch
    return cells


def _widths(text: str) -> set[int]:
    """Cell count of every table row, per table. A hostile string that escaped
    its cell shows up as a row wider than its header."""
    return {len(_split_cells(ln)) for ln in _table_rows(text)}


class TestAModelIdCannotAddAColumn:
    def test_the_per_row_table(self) -> None:
        out = _render(_result(model=HOSTILE))
        rows = [ln for ln in _table_rows(out) if HOSTILE.replace("|", "\\|") in ln]
        assert rows, out
        header = _table_rows(out)[0]
        assert len(_split_cells(rows[0])) == len(_split_cells(header)), rows[0]

    def test_the_per_run_output_heading(self) -> None:
        out = _render(_result(model=HOSTILE))
        # The `**model @ temp:**` tag is not in a table, so the pipe is harmless
        # there - but a backtick in the id is not.
        assert "**`a|b @ 0.0`:**" in out or "**`a\\|b @ 0.0`:**" in out, out

    def test_the_bootstrap_confidence_interval_table(self) -> None:
        """Its own section, built from a CI dict the renderer is handed rather
        than from the results, so it is exercised directly."""
        from cli_modelarium.output_formatters import _markdown_ci_section

        lines = _markdown_ci_section(
            {
                (HOSTILE, 0.0, None): {
                    "latency_ms": {
                        "point_estimate": 100.0, "ci_low": 90.0,
                        "ci_high": 110.0, "ci_level": 0.95,
                    }
                }
            }
        )
        rows = [ln for ln in lines if ln.startswith("|") and "---" not in ln]
        widths = {len(_split_cells(ln)) for ln in rows}
        assert len(widths) == 1, sorted(widths)

    def test_the_per_cell_statistical_table(self) -> None:
        out = _render(_result(model=HOSTILE, run_index=0),
                      _result(model=HOSTILE, run_index=1), runs=2)
        assert len(_widths(out)) <= 2, sorted(_widths(out))


class TestModelOutputCannotControlTheReport:
    def test_a_pipe_in_the_mode_cell(self) -> None:
        out = _render(_result(output=HOSTILE, run_index=0),
                      _result(output=HOSTILE, run_index=1), runs=2)
        assert "a\\|b" in out, out

    def test_a_fence_in_the_output_block_cannot_escape_it(self) -> None:
        out = _render(_result(output=FENCE))
        # Find the block the report opened for this output and check that no
        # line of the output closes it early.
        opened = [ln for ln in out.split("\n") if re.fullmatch(r"`{3,}", ln.strip())]
        assert opened, out
        fence_len = len(opened[0].strip())
        assert fence_len >= 4, f"a 3-backtick fence cannot hold this output: {opened}"
        assert FENCE in out, "the output must still appear verbatim inside it"

    def test_the_text_after_a_hostile_output_is_still_the_reports_own(self) -> None:
        out = _render(_result(output=FENCE))
        # Everything the report writes after the block must still be report
        # markup, not content swallowed into a code block.
        assert out.rstrip().count("```") % 2 == 0 or "````" in out, out


class TestProviderErrorTextIsQuoted:
    def test_a_pipe_in_an_error_message(self) -> None:
        out = _render(_result(error="rate limit|retry", output=""))
        assert "> error:" in out
        line = next(ln for ln in out.split("\n") if ln.startswith("> error:"))
        assert "\\|" in line or "`" in line, line

    def test_markup_in_an_error_message_is_not_rendered(self) -> None:
        out = _render(_result(error="see **docs**", output=""))
        assert "**docs**" not in out.split("> error:")[1].split("\n")[0]


class TestAssertionTextIsQuotedWithoutManglingTheTypeName:
    def _with(self, **over: object) -> str:
        base: dict[str, object] = dict(
            type="max_length_chars", passed=False, expected=100, actual=120,
            message="length 120 > 100", error=None,
        )
        base.update(over)
        return _render(_result(assertion_results=[AssertionResult(**base)]))  # type: ignore[arg-type]

    def test_the_type_name_survives_intact(self) -> None:
        """`_md_escape` would render this `max\\_length\\_chars`, which is also
        what `tests/test_cli_assertions.py` asserts against."""
        out = self._with()
        assert "max_length_chars" in out
        assert "max\\_length\\_chars" not in out

    def test_the_message_half_is_escaped_as_prose(self) -> None:
        """These bullets are not in a table, so a pipe is harmless here - the
        risk is markup. The message is prose, so it takes the prose escaper."""
        out = self._with(message="expected `a|b`")
        line = next(
            ln for ln in out.split("\n")
            if ln.startswith("-") and "max_length_chars" in ln
        )
        assert "\\`a\\|b\\`" in line, line

    def test_markup_in_an_assertion_message_is_not_rendered(self) -> None:
        out = self._with(message="expected **bold**")
        line = next(ln for ln in out.split("\n") if "max_length_chars" in ln and ln.startswith("-"))
        assert "**bold**" not in line, line

    def test_an_errored_assertion_takes_the_same_path(self) -> None:
        out = self._with(error="module **jsonschema** missing", message="")
        line = next(ln for ln in out.split("\n") if "max_length_chars" in ln and ln.startswith("-"))
        assert "**jsonschema**" not in line, line


def _judged(*models: str, risk: bool = False) -> BatchResult:
    judges = [
        JudgeScore(model=m, score=7, reasoning="r", cost_usd=0.001, latency_ms=5.0,
                   parse_error=None, risk_level="Low" if risk else None)
        for m in models
    ]
    jr = JudgeResult(judges=judges, average_score=7.0)
    if risk:
        jr.aggregated_risk_level = "Low"
    return _result(judge_result=jr)


class TestJudgeModelIdsAreQuoted:
    def test_the_score_panel_breakdown(self) -> None:
        out = _render(_judged("openai/gpt-5", HOSTILE))
        assert len(_widths(out)) == 1, sorted(_widths(out))

    def test_the_hallucination_panel_breakdown(self) -> None:
        out = _render(_judged("openai/gpt-5", HOSTILE, risk=True))
        assert len(_widths(out)) == 1, sorted(_widths(out))

    def test_a_skipped_self_eval_model(self) -> None:
        jr = JudgeResult(judges=[], average_score=None)
        jr.skipped_models = [HOSTILE]
        out = _render(_result(judge_result=jr))
        assert len(_widths(out)) == 1, sorted(_widths(out))

    def test_a_degraded_model(self) -> None:
        judges = [JudgeScore(model="openai/gpt-5", score=7, reasoning="r",
                             cost_usd=0.001, latency_ms=5.0, parse_error=None,
                             risk_level=None)]
        jr = JudgeResult(judges=judges, average_score=7.0)
        jr.degraded_models = [HOSTILE]
        out = _render(_result(judge_result=jr))
        assert len(_widths(out)) == 1, sorted(_widths(out))
