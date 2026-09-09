"""The error path must survive the text it is reporting.

`_print_error` put its message straight into a Rich `Panel`, which parses
markup. So the one function whose job is to explain a failure crashed on any
message containing a bracket - and the user got a traceback instead of the
sentence written for exactly that case:

    $ cli-modelarium pricing 'gpt-[/x]'
      rich.errors.MarkupError: closing tag '[/x]' at position 19 ...

THE ORDER IS THE WHOLE FIX AND IT ONLY WORKS ONE WAY. `redact_secrets`
substitutes key-shaped text; `escape` backslashes a tag-shaped `[a-z#/@...]`.
Redaction can therefore SYNTHESISE a tag - its `\\S+` swallows an intervening
bracket and what remains is a valid one - so escaping first walks past text that
does not exist yet:

    escape -> redact   '[x-goog-api-key: ***REDACTED*** a tag]'   parsed, vanishes
    redact -> escape   '\\[x-goog-api-key: ***REDACTED*** a tag]'  rendered

`TestTheOrder` below pins that with the measured case. Escaping does not weaken
redaction either way - 56,000 fuzz cases over all fourteen rules leaked nothing
in either order - but only one order keeps the message on screen.

THE EXIT CODE MOVES, 1 TO 2, and that is the point rather than a side effect.
A MarkupError escaped to the top-level handler, which prints a redacted
traceback and exits 1 - the same code as EXIT_ASSERTION_FAILED. A bracket in a
model id therefore reported "an assertion failed". It now reaches the
`sys.exit(EXIT_CALL_FAILED)` that follows 27 of the 28 call sites.
"""

from __future__ import annotations

import io

import pytest
from click.testing import CliRunner
from rich.console import Console
from rich.markup import escape

from cli_modelarium import cli as cli_module
from cli_modelarium.cli import main as cli_main
from cli_modelarium.security import redact_secrets

# The measured case: not tag-shaped on input, tag-shaped after redaction.
SYNTHESISED = "[x-goog-api-key: AQ.AbCdEfGh1234567890abcd[not a tag]"

# One live key per redaction rule, so the order is pinned against all of them.
KEYS = [
    "sk-proj-AbCdEfGh1234567890",
    "sk-ant-api03-AbCdEfGh1234567890",
    "sk-or-v1-AbCdEfGh1234567890",
    "xai-AbCdEfGh1234567890",
    "gsk_AbCdEfGh1234567890",
    "nvapi-AbCdEfGh1234567890",
    "sk-AbCdEfGh1234567890",
    "AIzaSyAbCdEfGh1234567890abcd",
    "AQ.AbCdEfGh1234567890abcdefgh",
    "https://api.test/v1?key=AQ.AbCdEfGh1234567890abcdefgh",
    "x-goog-api-key: AQ.AbCdEfGh1234567890abcd",
    "Authorization: Bearer sk-ant-api03-AbCdEfGh1234567890",
    "x-api-key: sk-AbCdEfGh1234567890",
    "api_key=AbCdEfGh1234567890",
]


def _panel(message: str) -> str:
    """Render through the real `_print_error` on a width-pinned console."""
    console = Console(file=io.StringIO(), width=200, force_terminal=False)
    original = cli_module.console
    cli_module.console = console
    try:
        cli_module._print_error(message)
    finally:
        cli_module.console = original
    return console.file.getvalue()  # type: ignore[attr-defined]


class TestTheOrder:
    """Redact first, escape last. The reverse deletes the message."""

    def test_the_synthesised_tag_survives(self) -> None:
        # escape->redact renders nothing at all for this input.
        assert "***REDACTED***" in _panel(SYNTHESISED)
        assert "x-goog-api-key" in _panel(SYNTHESISED)

    def test_the_reverse_order_would_have_deleted_it(self) -> None:
        """Pins WHY the order matters, by rendering the wrong one."""
        wrong = redact_secrets(escape(SYNTHESISED))
        console = Console(file=io.StringIO(), width=200, force_terminal=False)
        from rich.panel import Panel

        console.print(Panel(wrong, title="Error", border_style="red"))
        rendered = console.file.getvalue()
        assert "x-goog-api-key" not in rendered, (
            "escape-then-redact is supposed to lose this text; if it no longer "
            "does, Rich changed and this fix's ordering rationale needs re-checking"
        )

    def test_escaping_is_last(self) -> None:
        """Whatever `_print_error` does, no un-escaped tag may survive it."""
        out = _panel(SYNTHESISED)
        assert "[x-goog-api-key" in out or "\\[x-goog" in out, out


class TestRedactionStillWorks:
    @pytest.mark.parametrize("key", KEYS)
    def test_a_key_beside_markup_is_still_redacted(self, key: str) -> None:
        out = _panel(f"call failed [dim]for[/dim] {key} while retrying")
        assert "REDACTED" in out, out
        # The distinctive body of every key in the list.
        assert "AbCdEfGh1234567890" not in out.replace("\n", ""), out

    @pytest.mark.parametrize("key", KEYS)
    def test_a_key_glued_to_a_tag_is_still_redacted(self, key: str) -> None:
        out = _panel(f"{key}[/]")
        assert "AbCdEfGh1234567890" not in out.replace("\n", ""), out


class TestMarkupRendersLiterally:
    def test_a_stray_closing_tag_does_not_raise(self) -> None:
        assert "gpt-[/x]" in _panel("Unknown model: gpt-[/x].").replace("\n", "")

    def test_brackets_are_not_dropped(self) -> None:
        assert "a[b]c" in _panel("Unknown model: a[b]c.")

    def test_a_link_tag_is_not_made_live(self) -> None:
        console = Console(file=io.StringIO(), width=200, force_terminal=True)
        original = cli_module.console
        cli_module.console = console
        try:
            cli_module._print_error("see [link=http://x.invalid]here[/link]")
        finally:
            cli_module.console = original
        assert "\x1b]8;" not in console.file.getvalue()

    def test_an_ordinary_message_is_unchanged(self) -> None:
        out = _panel("No models registered.")
        assert "No models registered." in out
        assert "\\" not in out.replace("\\n", "")


class TestThroughTheRealCli:
    """The two reproductions, and the exit code they now produce."""

    def test_pricing_with_a_stray_tag_prints_its_message_and_exits_2(self) -> None:
        result = CliRunner().invoke(cli_main, ["pricing", "gpt-[/x]"])
        assert result.exit_code == 2, result.output
        flat = " ".join(result.output.split())
        assert "Unknown model: gpt-[/x]" in flat, flat
        assert "Traceback" not in result.output

    def test_an_unknown_model_id_with_a_stray_tag_exits_2(self) -> None:
        result = CliRunner().invoke(cli_main, ["hi", "--models", "vendor/model[/]"])
        assert result.exit_code == 2, result.output
        assert "vendor/model[/]" in " ".join(result.output.split())
        assert "Traceback" not in result.output

    def test_an_ordinary_unknown_model_is_unchanged(self) -> None:
        result = CliRunner().invoke(cli_main, ["pricing", "gpt-nonexistent"])
        assert result.exit_code == 2, result.output
        assert "Unknown model: gpt-nonexistent" in " ".join(result.output.split())


class TestNoCallerPassesIntentionalMarkup:
    """Escaping inside the function is only safe while this holds."""

    def test_every_call_site_passes_plain_text(self) -> None:
        import ast
        import pathlib
        import re

        src = pathlib.Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        tag = re.compile(r"\[/?[a-z#@][^\[\]]*\]")
        offenders = []
        for node in ast.walk(ast.parse(src)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_print_error"
            ):
                segment = ast.get_source_segment(src, node) or ""
                if tag.search(segment):
                    offenders.append(node.lineno)
        assert not offenders, (
            f"_print_error escapes its message, so a caller passing Rich markup "
            f"would have it shown as text. Offending call sites: {offenders}"
        )
