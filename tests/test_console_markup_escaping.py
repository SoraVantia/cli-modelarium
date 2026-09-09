"""Provider-controlled strings must render literally, not as Rich markup.

Rich parses `[...]` in every string it prints, so any provider-supplied text
interpolated into a console string was executed as markup rather than shown.
Three consequences, all reproduced below: a `[link=...]` tag became a live
OSC-8 terminal hyperlink, a colour tag broke out of the span it was inside,
and ordinary text containing brackets silently lost characters.

Model output is the widest of these surfaces and the least controlled content
in the system - the same reasoning the 0.1.5 CSV formula-injection fix used,
which never reached the console.

THAT SCOPE WAS TOO NARROW AND IS NOW REVERSED. This file originally said
user-controlled strings were deliberately left unescaped, on the reasoning that
a user putting markup in their own model id is styling their own terminal. The
reasoning does not survive contact with the failure: a model id carrying a stray
closing tag does not style anything, it raises `MarkupError` and takes the
command down after the models were billed. A `local/` id comes from whatever the
local server reports, not from the user at all. Model ids, prompts and provider
messages are escaped now too - see `test_live_display_escaping.py` and
`test_print_error_escaping.py`.

Tool-emitted markup over a closed set is still deliberately NOT escaped:
`_risk_cell_for_compare` returns `[red]N/A[/red]`, and the significance header
renders `click.Choice` values. Escaping those would kill the colours and mangle
the tool's own vocabulary.
"""

from __future__ import annotations

import io
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from click.testing import CliRunner
from rich.console import Console

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import CompletionResult, OnChunk
from cli_modelarium.streaming import StreamingDisplay, StreamState

# A tag Rich turns into a real OSC-8 hyperlink, which is the worst case: it
# renders as innocuous text pointing anywhere.
LINK = "[link=http://x.invalid]tapme[/link]"
# Brackets that are not a valid tag are still consumed - this is the silent
# character-loss case, and it makes escaping a correctness fix as well.
BRACKETS = "a[b]c"

JUDGE_MARKER = "Respond with ONLY a JSON object"


class _HostileProvider:
    """Serves markup as model output, as judge reasoning, and as a category."""

    name = "fake"

    def __init__(self, *, refuse: bool = False, text: str = LINK) -> None:
        self.refuse = refuse
        self.text = text

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if False:  # pragma: no cover - never iterated; --no-stream is used
            yield ""
        raise NotImplementedError

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
        *,
        on_chunk: OnChunk | None = None,
        **_kwargs: Any,
    ) -> CompletionResult:
        if JUDGE_MARKER in prompt:
            output = '{"score": 8, "reasoning": "' + LINK.replace('"', "'") + '"}'
        elif self.refuse:
            output = ""
        else:
            output = self.text
        # `state.text` is accumulated from the chunk callback, not from the
        # returned `output`, so a fake that skips this renders a blank line.
        if on_chunk is not None:
            on_chunk(output)
        return CompletionResult(
            output=output,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.000123,
            latency_ms=100.0,
            ttft_ms=10.0,
            model=model,
            provider=self.name,
            temperature=temperature,
            refused=self.refuse and JUDGE_MARKER not in prompt,
            stop_reason="refusal" if self.refuse else None,
            stop_category=BRACKETS if self.refuse else None,
        )


@pytest.fixture
def hostile(monkeypatch: pytest.MonkeyPatch) -> _HostileProvider:
    fake = _HostileProvider()
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: fake
    )
    # A judge model's key is validated up front, before any call, so the
    # judged cases need one configured even though the provider is faked.
    for env, value in (
        ("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_test_fixture_00"),
        ("ANTHROPIC_API_KEY", "sk-ant-NOT_A_REAL_KEY_test_fixture_0"),
    ):
        monkeypatch.setenv(env, value)
    return fake


def _run(*args: str) -> Any:
    return CliRunner().invoke(cli_main, [*args, "--no-stream"])


def _flat(text: str) -> str:
    """Collapse Rich's hard wrapping so an assertion pins the text, not the
    column the terminal happened to break at."""
    return " ".join(text.split())


class TestModelOutputRendersLiterally:
    """cli.py single-run and --runs per-run listings."""

    def test_single_run_output_is_not_parsed_as_markup(
        self, hostile: _HostileProvider
    ) -> None:
        result = _run("q", "--models", "gpt-5.5")
        assert result.exit_code == 0
        assert LINK in _flat(result.output)

    def test_runs_listing_output_is_not_parsed_as_markup(
        self, hostile: _HostileProvider
    ) -> None:
        result = _run("q", "--models", "gpt-5.5", "--runs", "3")
        assert result.exit_code == 0
        assert LINK in _flat(result.output)

    def test_brackets_in_output_are_not_silently_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Unescaped this rendered as "ac".
        monkeypatch.setattr(
            "cli_modelarium.cli._get_provider_instance",
            lambda name, **_kwargs: _HostileProvider(text=BRACKETS),
        )
        result = _run("q", "--models", "gpt-5.5")
        assert result.exit_code == 0
        assert BRACKETS in _flat(result.output)


class TestJudgeTextRendersLiterally:
    """cli.py judge reasoning, single-run and --runs, under --include-reasoning."""

    @pytest.mark.parametrize("extra", [[], ["--runs", "3"]])
    def test_judge_reasoning_is_not_parsed_as_markup(
        self, hostile: _HostileProvider, extra: list[str]
    ) -> None:
        result = _run(
            "q",
            "--models",
            "gpt-5.5",
            "--judge",
            "claude-opus-4-7",
            "--include-reasoning",
            "--no-judge-tos",
            *extra,
        )
        assert result.exit_code == 0
        assert LINK in _flat(result.output)


class TestModePreviewRendersLiterally:
    """cli.py mode-output preview, which lands in a Rich table cell."""

    def test_mode_cell_is_not_parsed_as_markup(self, hostile: _HostileProvider) -> None:
        result = _run("q", "--models", "gpt-5.5", "--runs", "3")
        assert result.exit_code == 0
        # The same answer three times makes it the cell's mode. The cell is
        # width-constrained, so pin the opening tag rather than the whole
        # payload - unescaped, Rich consumed it and no bracket survived.
        assert "[link=" in _flat(result.output)


class TestProviderErrorRendersLiterally:
    """cli.py error lines, single-run and --runs."""

    @pytest.mark.parametrize("extra", [[], ["--runs", "3"]])
    def test_error_text_is_not_parsed_as_markup(
        self, monkeypatch: pytest.MonkeyPatch, extra: list[str]
    ) -> None:
        from cli_modelarium.exceptions import ProviderError

        class _Failing(_HostileProvider):
            async def complete(self, *a: Any, **k: Any) -> CompletionResult:
                raise ProviderError(LINK, provider="fake")

        monkeypatch.setattr(
            "cli_modelarium.cli._get_provider_instance", lambda name, **_kwargs: _Failing()
        )
        result = _run("q", "--models", "gpt-5.5", *extra)
        assert LINK in _flat(result.output)


class TestStopCategoryRendersLiterally:
    """streaming.py refusal panel.

    Driven through `StreamingDisplay._panel` rather than a CLI run because the
    live display is `transient=True` and is disabled entirely without a TTY, so
    a CliRunner invocation never shows this panel at all.
    """

    def _render(self, category: str, *, terminal: bool) -> str:
        state = StreamState(model="claude-opus-5", provider_name="anthropic", temperature=0.0)
        state.status = "refused"
        state.stop_category = category
        state.cost_usd = 0.000725
        console = Console(
            file=io.StringIO(), width=100, force_terminal=terminal, legacy_windows=False
        )
        console.print(StreamingDisplay([state])._panel(state))
        return console.file.getvalue()

    def test_a_markup_category_renders_as_text(self) -> None:
        assert "[link=" in self._render(LINK, terminal=False)

    def test_no_osc8_hyperlink_is_emitted(self) -> None:
        # The escape Rich uses to open a hyperlink. Present before escaping.
        assert "\x1b]8;" not in self._render(LINK, terminal=True)

    def test_brackets_in_a_category_are_not_dropped(self) -> None:
        assert BRACKETS in self._render(BRACKETS, terminal=False)

    @pytest.mark.parametrize(
        "category",
        ["reasoning_extraction", "bio", "cyber", "policy_violation:self_harm"],
    )
    def test_ordinary_categories_are_unchanged(self, category: str) -> None:
        # Escaping is information-preserving: a category with no markup in it
        # renders exactly as it did before.
        assert category in self._render(category, terminal=False)


class TestOutputPathRendersLiterally:
    """cli.py:1941 - the "Wrote {path}" line escapes the operator-supplied path.

    A path is operator-supplied rather than remote input, but the failure is the
    same shape as the model-output cases above. Unescaped, `r[o].md` printed as
    `r.md` - naming a file that was never written - and a path carrying a close
    tag raised MarkupError *after* the file was on disk, turning a completed,
    billed run into exit 1 (EXIT_ASSERTION_FAILED).
    """

    def test_bracketed_output_path_prints_the_real_path(
        self,
        hostile: _HostileProvider,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A relative path keeps the "Wrote <path>" line short, so the assertion
        # pins the rendered name rather than the column Rich wrapped it at.
        monkeypatch.chdir(tmp_path)
        result = _run(
            "hi", "--models", "gpt-5.5", "--output", "r[o].md", "--force"
        )
        assert result.exit_code == 0, result.output
        assert os.path.exists("r[o].md")
        # Unescaped, the [o] was consumed and the line read "Wrote r.md".
        assert "r[o].md" in _flat(result.output)

    def test_closing_tag_in_output_path_does_not_raise(
        self,
        hostile: _HostileProvider,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # `[/]` is a Rich close tag; it also contains a path separator, so the
        # parent component `a[` is created first and the file lands at `a[/]b.md`.
        # On the release tree the print raised MarkupError and exited 1 after the
        # file was already written.
        monkeypatch.chdir(tmp_path)
        os.makedirs("a[")
        result = _run(
            "hi", "--models", "gpt-5.5", "--output", "a[/]b.md", "--force"
        )
        assert result.exit_code == 0, result.output
        assert "MarkupError" not in result.output
        assert os.path.exists("a[/]b.md")
