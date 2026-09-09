"""An ordinary answer to an ordinary question must not crash the live display.

    prompt   "What does [/] mean in BBCode?"
    answer   "In BBCode you close a tag with [/]. ..."
    result   rich.errors.MarkupError, mid-stream, AFTER the call was billed

`StreamingDisplay._panel` builds a Rich `Panel` whose title and body are
f-strings, and Rich parses markup in both. Group 1 escaped ONE value in this
function - `stop_category` - and left `state.model`, `state.error` and
`state.text` beside it, so the panel it was fixing still crashed on three of its
four untrusted fields. The system-prompt legend is a fourth.

--no-stream IS NOT EXEMPT. The legend is printed OUTSIDE the `if live_display:`
block (streaming.py, "so it survives the transient=True cleanup"), so a system
prompt containing a bracket crashes on both paths.

EVERY TEST HERE RUNS AT OR BELOW TWELVE TASKS. Above
`AUTO_COLLAPSE_TASK_THRESHOLD` the Live display is switched off entirely and the
panels are never built, so a test written above it passes whether or not this
fix landed - measured: runs=12 crashes, runs=13 renders.

THE PANEL IS TESTED DIRECTLY, not through CliRunner. Only the `Live` WRAPPER
needs a TTY; the renderable itself raises on a plain width-pinned Console, which
is what `TestStopCategoryRendersLiterally` in test_console_markup_escaping.py
has always done. That harness existed before this fix and was pointed at one
field; this file points it at all of them.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from cli_modelarium.streaming import (
    AUTO_COLLAPSE_TASK_THRESHOLD,
    StreamingDisplay,
    StreamState,
    render_prompt_legend,
)

# A stray closing tag: Rich raises rather than rendering oddly.
CRASHER = "x[/]y"
# A tag-shaped run: Rich eats it, so the panel names something never sent.
EATEN = "a[bold]b"
# A tag Rich turns into a real terminal hyperlink.
LINK = "[link=http://x.invalid]tapme[/link]"

# Every status the panel branches on, including the two that reach the
# fall-through `else`.
STATUSES = ["pending", "waiting", "streaming", "retrying", "complete", "refused", "error"]


def _state(**over: object) -> StreamState:
    s = StreamState(model="claude-opus-5", provider_name="anthropic", temperature=0.0)
    s.status = "complete"
    s.text = "ok"
    s.cost_usd = 0.000725
    for k, v in over.items():
        setattr(s, k, v)
    return s


def _render(state: StreamState, *, terminal: bool = False) -> str:
    console = Console(
        file=io.StringIO(), width=200, force_terminal=terminal, legacy_windows=False
    )
    console.print(StreamingDisplay([state])._panel(state))
    return console.file.getvalue()  # type: ignore[attr-defined]


class TestTheMatrix:
    """model, text and error against every status. Each cell crashed before."""

    @pytest.mark.parametrize("status", STATUSES)
    def test_a_model_id_renders_literally(self, status: str) -> None:
        assert CRASHER in _render(_state(status=status, model=CRASHER))

    @pytest.mark.parametrize("status", STATUSES)
    def test_a_model_id_is_not_eaten(self, status: str) -> None:
        assert EATEN in _render(_state(status=status, model=EATEN))

    @pytest.mark.parametrize("status", STATUSES)
    def test_provider_error_text_renders_literally(self, status: str) -> None:
        # `error` is checked before status, so it renders in every one.
        assert CRASHER in _render(_state(status=status, error=f"boom {CRASHER}"))

    @pytest.mark.parametrize("status", ["streaming", "complete", "refused", "error"])
    def test_model_output_renders_literally(self, status: str) -> None:
        assert CRASHER in _render(_state(status=status, text=f"answer {CRASHER}"))

    @pytest.mark.parametrize("status", ["streaming", "complete", "refused", "error"])
    def test_model_output_is_not_eaten(self, status: str) -> None:
        assert EATEN in _render(_state(status=status, text=f"answer {EATEN}"))

    def test_no_live_hyperlink_from_model_output(self) -> None:
        assert "\x1b]8;" not in _render(_state(text=LINK), terminal=True)

    def test_no_live_hyperlink_from_a_model_id(self) -> None:
        assert "\x1b]8;" not in _render(_state(model=LINK), terminal=True)


class TestTheBbcodeAnswer:
    """The reported case, needing nothing unusual."""

    ANSWER = "In BBCode you close a tag with [/]. That closes the innermost tag."

    @pytest.mark.parametrize("status", ["streaming", "complete"])
    def test_both_branches(self, status: str) -> None:
        assert "[/]" in _render(_state(status=status, text=self.ANSWER))


class TestTheSystemPromptLegend:
    """Printed outside the Live block, so it renders on --no-stream too."""

    def _legend(self, *prompts: str) -> str:
        states = []
        for p in prompts:
            s = _state()
            s.system_prompt = p
            states.append(s)
        console = Console(file=io.StringIO(), width=200, force_terminal=False)
        console.print(render_prompt_legend(states))
        return console.file.getvalue()  # type: ignore[attr-defined]

    def test_a_stray_closing_tag_renders_literally(self) -> None:
        assert CRASHER in self._legend("plain prompt", f"answer as {CRASHER}")

    def test_a_tag_shaped_prompt_is_not_eaten(self) -> None:
        assert EATEN in self._legend("plain prompt", f"answer as {EATEN}")

    def test_a_long_prompt_is_still_truncated(self) -> None:
        """Escaping happens after the slice, so the preview stays a preview."""
        out = self._legend("plain prompt", "z" * 200)
        assert "..." in out
        assert "z" * 200 not in out


class TestStopCategoryIsNotDoubleEscaped:
    """Group 1 escaped it at its own interpolation. The title is composed FROM
    that, so escaping the composed string would escape it twice."""

    def test_one_backslash_not_two(self) -> None:
        out = _render(_state(status="refused", stop_category="a[b]c"))
        assert "a[b]c" in out, out
        assert "\\[b]" not in out, out
        assert "\\\\" not in out, out

    def test_an_ordinary_category_is_unchanged(self) -> None:
        assert "reasoning_extraction" in _render(
            _state(status="refused", stop_category="reasoning_extraction")
        )


class TestTheLatentSites:
    """Neither is reachable with a bracket today - `mark_retry` passes one of two
    literals, and `status` is only ever set internally - but both interpolate a
    bare `str` into markup, so both are escaped rather than argued about."""

    def test_a_retry_message_renders_literally(self) -> None:
        assert CRASHER in _render(_state(status="retrying", retry_message=CRASHER))

    def test_an_unknown_status_renders_literally(self) -> None:
        assert CRASHER in _render(_state(status=CRASHER))


class TestOrdinaryValuesAreUnchanged:
    @pytest.mark.parametrize("status", STATUSES)
    def test_a_plain_panel_is_untouched(self, status: str) -> None:
        out = _render(_state(status=status, text="Paris is the capital of France."))
        assert "claude-opus-5" in out
        assert "\\" not in out.replace("\\n", "")


class TestTheThresholdIsRespected:
    def test_every_test_here_uses_one_panel(self) -> None:
        """A test above the threshold would pass with or without the fix, because
        the panels are never built. Recorded so the bound is explicit."""
        assert AUTO_COLLAPSE_TASK_THRESHOLD == 12
