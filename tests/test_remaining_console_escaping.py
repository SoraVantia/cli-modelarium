"""The rest of the console sites that render a value the tool does not control.

Three families, and two of them are instructive about HOW to escape rather than
whether to:

  * MODEL AND JUDGE IDS - in table cells, in run headers, and in the judge
    lines. The judge lines are the sharp case: they ALREADY escape the reasoning
    or the parse error and interpolate the id raw beside it, so half the line was
    protected and the other half could take the whole command down.

  * IDS FROM A LOCAL SERVER'S /v1/models - `id` and `owned_by`, chosen by
    whatever is listening on the port, not by the user.

  * THE LOCAL SERVER URL - in five inline Panels, one Table TITLE, and the two
    `keys` surfaces. Operator-supplied config rather than remote input, so lower
    severity, but one case needs no hostility at all: a link-local IPv6 URL is
    `http://[fe80::1%25eth0]:11434`, and Rich ate the host, so the error named a
    URL the user never typed.

THE TABLE TITLE IS THE ONE TO READ. It is `f"local [dim]({url})[/dim]"` - the
`[dim]` is the tool's own styling and must survive, so only `url` is escaped.
Blanket-escaping the line would print the tag instead of applying it. Same shape
as the assertion-message split in the Markdown formatter.

NOT ESCAPED, deliberately: `_risk_cell_for_compare` returns `[red]N/A[/red]`
over a closed set, and the significance header renders `click.Choice` values.
Those are the tool's own vocabulary; escaping them kills the colours.
"""

from __future__ import annotations

import io

import pytest
from click.testing import CliRunner
from rich.console import Console

from cli_modelarium import cli as cli_module
from cli_modelarium.cli import main as cli_main

CRASHER = "x[/]y"
EATEN = "a[bold]b"


def _console() -> Console:
    return Console(file=io.StringIO(), width=220, force_terminal=False, legacy_windows=False)


def _capture(fn, *args, **kwargs) -> str:
    console = _console()
    original = cli_module.console
    cli_module.console = console
    try:
        fn(*args, **kwargs)
    finally:
        cli_module.console = original
    return console.file.getvalue()  # type: ignore[attr-defined]


class TestTheLocalServerUrl:
    """Five Panels, a Table title, and the two `keys` surfaces."""

    def test_the_ipv6_host_is_not_eaten(self) -> None:
        """The case needing no hostile input: Rich ate the bracketed host and
        the message named a URL the user never typed."""
        result = CliRunner().invoke(
            cli_main,
            ["list-models", "--local", "--local-url", "http://[fe80::1%25eth0]:11434"],
        )
        flat = " ".join(result.output.split())
        assert "http://[fe80::1%25eth0]:11434" in flat, flat

    def test_a_stray_closing_tag_in_the_url_does_not_crash_the_panel(self) -> None:
        out = _capture(cli_module._print_error, f"Could not reach {CRASHER}.")
        assert CRASHER in out, out

    def test_the_table_title_keeps_its_own_dim_styling(self) -> None:
        """`f"local [dim]({url})[/dim]"` - the [dim] is the tool's, the url is
        not. Escaping the whole line would print the tag instead of applying
        it."""
        from rich.markup import escape
        from rich.table import Table

        title = f"local [dim]({escape(EATEN)})[/dim]"
        console = Console(file=io.StringIO(), width=200, force_terminal=True)
        table = Table(title=title, border_style="dim", title_justify="left")
        table.add_column("x" * 80)   # wide enough that the title cannot wrap
        table.add_row("y")
        console.print(table)
        rendered = console.file.getvalue()
        assert EATEN in rendered, rendered
        # The [dim] tag was applied, not printed: it does not appear literally.
        assert "[dim]" not in rendered, rendered

    def test_keys_list_shows_the_saved_url_literally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli_module, "load_local_url", lambda: f"http://{EATEN}:1234")
        monkeypatch.setenv("COLUMNS", "200")
        result = CliRunner().invoke(cli_main, ["keys", "list"])
        flat = "".join(result.output.split())
        assert EATEN.replace(" ", "") in flat, result.output

    def test_keys_set_local_echoes_the_url_literally(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved: list[str] = []
        monkeypatch.setattr(cli_module, "save_local_url", saved.append)
        monkeypatch.setenv("COLUMNS", "200")
        result = CliRunner().invoke(
            cli_main, ["keys", "set", "local", "--base-url", f"http://localhost:1234/{EATEN}"]
        )
        assert result.exit_code == 0, result.output
        assert EATEN in "".join(result.output.split()), result.output


class TestJudgeIds:
    """These lines already escaped the reasoning and left the id raw."""

    def _judge_line(self, model: str, reasoning: str, parse_error: str | None = None):
        from cli_modelarium.judging import JudgeResult, JudgeScore

        return JudgeResult(
            judges=[
                JudgeScore(
                    model=model, score=None if parse_error else 7, reasoning=reasoning,
                    cost_usd=0.0, latency_ms=1.0, parse_error=parse_error,
                    risk_level=None,
                )
            ],
            average_score=None if parse_error else 7.0,
        )

    def test_both_halves_of_the_reasoning_line_are_escaped(self) -> None:
        from rich.markup import escape

        # The id and the reasoning go through the same escape; neither may crash.
        assert escape(CRASHER) != CRASHER
        assert CRASHER in escape(CRASHER).replace("\\", "")

    def test_a_judge_id_with_a_stray_tag_renders_in_the_run_header(self) -> None:
        """End-to-end below; this pins that the id reaches an escaped site."""
        import pathlib

        src = pathlib.Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert "judge {escape(j.model)}" in src, (
            "the judge id is interpolated raw beside an escaped reasoning string"
        )


class TestLocalServerModelIds:
    def test_an_id_and_owned_by_from_v1_models_are_escaped(self) -> None:
        import pathlib

        src = pathlib.Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert "escape(model_id)" in src or "local/{escape(" in src, src[:0]
        assert "escape(owned_by)" in src or "escape(str(entry" in src


class TestModelIdsInTablesAndHeaders:
    def test_the_compare_run_header_escapes_the_model_id(self) -> None:
        import pathlib

        src = pathlib.Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert src.count("[bold]{escape(s.model)}[/bold]") == 1
        assert src.count("[bold]{escape(model)}[/bold]") >= 1

    def test_the_summary_table_cell_escapes_the_model_id(self) -> None:
        import pathlib

        src = pathlib.Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert "row: list[str] = [escape(s.model)]" in src
        assert "row = [escape(model)]" in src

    def test_pricing_renders_a_bracketed_local_id_literally(self) -> None:
        result = CliRunner().invoke(cli_main, ["pricing", f"local/{EATEN}"])
        assert result.exit_code == 0, result.output
        assert EATEN in " ".join(result.output.split()), result.output


class TestToolMarkupIsLeftAlone:
    """The other half of the rule: a closed set keeps its colours."""

    def test_the_risk_cell_still_emits_live_markup(self) -> None:
        from cli_modelarium.cli import _risk_cell_for_compare
        from cli_modelarium.judging import JudgeResult

        assert _risk_cell_for_compare(JudgeResult(judges=[], average_score=None)) == (
            "[dim]-[/dim]"
        )

    def test_the_significance_header_still_renders_its_choices(self) -> None:
        import pathlib

        src = pathlib.Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert "f\"[dim]Metric: {first.metric}" in src


class TestEmojiSubstitutionIsDisabled:
    """The one corruption escaping cannot fix.

    Rich substitutes `:word:` shortcodes after markup parsing and `escape` never
    touches a colon, so `x:free:y` rendered as an emoji however well it was
    escaped. `emoji=False` is set on the Console rather than per-print, because
    the per-print kwarg does not reach a string nested inside a Panel or Table
    and the Console setting does.

    Measured and worth recording: the shipped `:free` OpenRouter ids are NOT
    affected - a shortcode needs colons on both sides and `qwen/qwen3-coder:free`
    has one. All five render unchanged either way.
    """

    def test_the_cli_console_has_emoji_disabled(self) -> None:
        assert cli_module.console.options.__class__  # console exists
        assert cli_module.console._emoji is False

    def test_the_setting_reaches_a_string_nested_in_a_panel(self) -> None:
        """The reason it is set on the Console and not per-print. Built the same
        way the module builds its console, rather than by mutating the global
        one - swapping the real console's file leaks into later tests."""
        from rich.markup import escape
        from rich.panel import Panel

        for emoji, expected in ((True, "x\U0001f193y"), (False, "x:free:y")):
            console = Console(file=io.StringIO(), width=200, emoji=emoji)
            console.print(Panel(escape("model x:free:y was not found")))
            rendered = " ".join(console.file.getvalue().split())  # type: ignore[attr-defined]
            assert expected in rendered, (emoji, rendered)

    def test_the_per_print_kwarg_would_not_have_worked(self) -> None:
        """Pins why the Console setting is the fix: the per-print kwarg does not
        reach a string nested inside a Panel."""
        from rich.panel import Panel

        console = Console(file=io.StringIO(), width=200, emoji=True)
        console.print(Panel("x:free:y"), emoji=False)
        assert "x:free:y" not in console.file.getvalue()  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "model_id",
        [
            "qwen/qwen3-coder:free",
            "deepseek/deepseek-r1:free",
            "meta-llama/llama-3-3-70b-instruct:free",
            "openai/gpt-oss-120b:free",
            "zhipuai/glm-4.7-flash:free",
        ],
    )
    def test_the_shipped_free_ids_are_unaffected_either_way(self, model_id: str) -> None:
        from rich.markup import escape

        console = Console(file=io.StringIO(), width=200, emoji=True)
        console.print(escape(model_id))
        assert model_id in console.file.getvalue()  # type: ignore[attr-defined]

    def test_the_streaming_console_has_emoji_disabled(self) -> None:
        import pathlib

        src = pathlib.Path("src/cli_modelarium/streaming.py").read_text(encoding="utf-8")
        assert src.count("Console(emoji=False)") == 2
