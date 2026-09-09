"""A prompt must appear in the report as the prompt that was sent.

`_md_escape` escaped `\\`, `|` and newline and nothing else, so every other
Markdown construct in a user's prompt was interpreted rather than quoted. The
report is the artifact a team circulates and the prompt is the one thing it has
to reproduce exactly, so a prompt containing a backtick, `**`, a link or a raw
`<img>` tag was silently rewritten by the file describing it.

These pin that the rendered text reads back as the input, and that the escapes
land in the file rather than only in the renderer's head.
"""

from __future__ import annotations

import re

from cli_modelarium.output_formatters import BatchResult, _format_markdown, _md_escape

# Every construct that used to survive unescaped, with the reading a Markdown
# renderer gave it before.
FORMATTING = [
    ("`rm -rf /`", "code span"),
    ("**not bold**", "strong emphasis"),
    ("_not italic_", "emphasis"),
    ("[click](http://example.test)", "a live link"),
    ("<img src=x onerror=alert(1)>", "raw HTML"),
    ("<https://example.test>", "an autolink"),
    ("# Not a heading", "a heading"),
]


class TestConstructsAreNeutralised:
    def test_every_construct_is_escaped(self) -> None:
        for text, reading in FORMATTING:
            escaped = _md_escape(text)
            # The characters that carry the meaning are all backslash-prefixed.
            for ch in "`*_[]<>#":
                assert f"\\{ch}" in escaped or ch not in text, f"{reading}: {escaped}"

    def test_the_visible_text_is_preserved(self) -> None:
        # Escaping must not delete or reorder anything - stripping the added
        # backslashes gives back exactly what was passed in.
        for text, _ in FORMATTING:
            assert re.sub(r"\\(.)", r"\1", _md_escape(text)) == text


class TestThePreExistingBehaviourIsKept:
    def test_a_pipe_still_cannot_break_a_table_cell(self) -> None:
        assert _md_escape("a|b") == "a\\|b"

    def test_a_newline_still_collapses_to_one_line(self) -> None:
        assert "\n" not in _md_escape("line one\nline two")
        assert _md_escape("line one\nline two") == "line one / line two"

    def test_a_backslash_is_doubled(self) -> None:
        assert _md_escape("C:\\path") == "C:\\\\path"

    def test_empty_stays_empty(self) -> None:
        assert _md_escape("") == ""

    def test_ordinary_text_is_untouched(self) -> None:
        assert _md_escape("What is the capital of France?") == (
            "What is the capital of France?"
        )


class TestItReachesTheReport:
    def _report(self, prompt: str, system: str) -> str:
        return _format_markdown(
            [
                BatchResult(
                    prompt_id="p1",
                    prompt=prompt,
                    system=system,
                    model="claude-opus-5",
                    temperature=0.0,
                    latency_ms=100.0,
                    ttft_ms=10.0,
                    input_tokens=51,
                    output_tokens=4,
                    cached_tokens=0,
                    cost_usd=0.000725,
                    output="Paris",
                    error=None,
                    retries=0,
                )
            ],
            runs=1,
        )

    def test_a_prompt_with_markup_is_quoted_not_rendered(self) -> None:
        out = self._report("Answer **only** with `JSON`", "You are <b>terse</b>")
        assert "Answer \\*\\*only\\*\\* with \\`JSON\\`" in out
        # The system prompt goes through the same path and carried raw HTML.
        assert "You are \\<b\\>terse\\</b\\>" in out
        assert "<b>terse</b>" not in out
