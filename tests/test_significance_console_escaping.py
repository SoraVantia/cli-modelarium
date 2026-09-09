"""A model id must not be able to eat characters or crash the significance display.

Group 4b escaped `_display_mcnemar` and built `_mcnemar_caveat_markup` to escape
the caveat it prints. Its sibling `_display_significance` was left as it was, and
it renders a model id at SIX places across its three display branches plus its
caveat:

    the refusal caveat                     [yellow]{significance_refusal_caveat(...)}[/yellow]
    2 models, no p-value                   "  {model_a} vs {model_b}: ..."
    2 models, with a p-value               "  {model_a} (avg ...) vs {model_b} ..."
    3-5 models, the matrix column headers   table.add_column(m)
    3-5 models, the matrix row label        table.add_row(m_a, ...)
    6+ models, the top-K list              "  {i}. {model_a} vs {model_b}: ..."

A model id is user-supplied - OpenRouter and `local/` ids are freeform - so all
six parse markup the user wrote. Two outcomes, both measured:

    a tag-shaped id      characters are silently eaten, so the row names a model
                         that was never run
    a stray closing tag  rich.errors.MarkupError, which takes the whole command
                         down after the models were called and paid for

THE MATRIX BRANCH IS THE ONE THAT WAS NOT OBVIOUS. `Table.add_column` and
`Table.add_row` render their arguments as markup exactly like `console.print`
does, so the two crash there as readily as in an f-string. Verified against Rich
directly in `TestRichReallyParsesTableParts` below, so the premise of this whole
file is pinned rather than assumed.

The header line is deliberately NOT escaped: `metric`, `test_used`,
`correction_method` and `threshold` are `click.Choice` values and a float - the
tool's own closed vocabulary, not anyone's input.
"""

from __future__ import annotations

import pytest
from rich.console import Console
from rich.table import Table

from cli_modelarium import cli as cli_module

# A tag-shaped id: Rich eats `[secret]` and prints a model that was never run.
EATEN = "openrouter/a[secret]b"
# A stray closing tag: Rich raises MarkupError rather than rendering oddly.
CRASHER = "local/model[/]"


class _Stub:
    """The fields `_display_significance` reads, and no more.

    A duck-typed stand-in rather than a real `SignificanceResult`, matching
    `tests/test_display_gaps.py` - the renderers read through `getattr` for
    exactly this reason.
    """

    metric = "latency_ms"
    test_used = "welch_t_test"
    correction_method = "bonferroni"
    threshold = 0.05
    p_value = 0.04
    p_value_corrected = 0.04
    significant_at_threshold = True
    mean_a = 1.0
    mean_b = 2.0
    effect_size = 0.5
    effect_size_interpretation = "medium"
    n_comparisons = 1
    n_pairs_untestable = 0
    n_refused_a = 0
    n_refused_b = 0

    def __init__(self, model_a: str, model_b: str, **over: object) -> None:
        self.model_a = model_a
        self.model_b = model_b
        for key, value in over.items():
            setattr(self, key, value)


def _render(results: list, monkeypatch: pytest.MonkeyPatch, console: Console) -> str:
    monkeypatch.setattr(cli_module, "console", console)
    cli_module._display_significance(results)
    return console.file.getvalue()  # type: ignore[attr-defined]


def _pairs(models: list[str]) -> list[_Stub]:
    """Every unordered pair, which is the shape the display is handed."""
    out = []
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            out.append(_Stub(a, b))
    return out


class TestRichReallyParsesTableParts:
    """The premise. If Rich ever stopped rendering markup in a header or a cell,
    the matrix half of this file would be testing nothing."""

    def test_a_column_header_raises_on_a_stray_closing_tag(self) -> None:
        table = Table()
        table.add_column("Model")
        table.add_column(CRASHER)
        table.add_row("x", "y")
        import io

        from rich.errors import MarkupError

        with pytest.raises(MarkupError):
            Console(file=io.StringIO(), width=200).print(table)

    def test_a_row_cell_raises_on_a_stray_closing_tag(self) -> None:
        table = Table()
        table.add_column("Model")
        table.add_row(CRASHER)
        import io

        from rich.errors import MarkupError

        with pytest.raises(MarkupError):
            Console(file=io.StringIO(), width=200).print(table)


class TestTwoModels:
    """The single-line branch - both of its prints."""

    def test_a_tag_shaped_id_renders_literally(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render([_Stub(EATEN, "b")], monkeypatch, capture_console)
        assert EATEN in out, out

    def test_a_stray_closing_tag_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render([_Stub(CRASHER, "b")], monkeypatch, capture_console)
        assert CRASHER in out, out

    def test_the_no_p_value_line_is_escaped_too(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(
            [_Stub(CRASHER, EATEN, p_value=None)], monkeypatch, capture_console
        )
        assert CRASHER in out and EATEN in out, out
        assert "no p-value" in out, out

    def test_the_second_model_is_escaped_as_well_as_the_first(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render([_Stub("a", CRASHER)], monkeypatch, capture_console)
        assert CRASHER in out, out


class TestTheRefusalCaveat:
    """4b escaped the McNemar caveat through `_mcnemar_caveat_markup` and left
    this one, which names model ids the same way."""

    def test_a_stray_closing_tag_in_the_caveat_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(
            [_Stub(CRASHER, "b", n_refused_a=2)], monkeypatch, capture_console
        )
        assert "did not answer every run" in out, out
        assert CRASHER in out, out

    def test_a_tag_shaped_id_in_the_caveat_renders_literally(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(
            [_Stub(EATEN, "b", n_refused_a=1)], monkeypatch, capture_console
        )
        assert EATEN in out, out


class TestTheMatrix:
    """3-5 models. Both the column headers and the row labels carry model ids."""

    def test_a_stray_closing_tag_in_a_column_header_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(_pairs([CRASHER, "b", "c"]), monkeypatch, capture_console)
        assert "Pairwise p-values" in out, out

    def test_a_tag_shaped_id_survives_the_matrix(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(_pairs([EATEN, "b", "c"]), monkeypatch, capture_console)
        # It appears twice: once as a column header, once as a row label.
        assert out.count("a[secret]b") >= 2, out

    def test_five_models_still_render(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(
            _pairs([CRASHER, "b", "c", "d", EATEN]), monkeypatch, capture_console
        )
        assert CRASHER in out and EATEN in out, out


class TestTopK:
    """6+ models. The top-K list is the third branch."""

    def test_a_stray_closing_tag_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(
            _pairs([CRASHER, "b", "c", "d", "e", "f"]), monkeypatch, capture_console
        )
        assert "Top significant pairs" in out, out
        assert CRASHER in out, out

    def test_a_tag_shaped_id_renders_literally(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        out = _render(
            _pairs([EATEN, "b", "c", "d", "e", "f"]), monkeypatch, capture_console
        )
        assert EATEN in out, out


class TestTheToolsOwnVocabularyIsLeftAlone:
    def test_the_header_line_still_renders_its_values(
        self, monkeypatch: pytest.MonkeyPatch, capture_console: Console
    ) -> None:
        """`metric`, `test_used` and `correction_method` are click.Choice values,
        so escaping them would be noise, not safety."""
        out = _render([_Stub("a", "b")], monkeypatch, capture_console)
        assert "latency_ms" in out and "welch_t_test" in out, out
        assert "bonferroni" in out, out


class TestTheSiblingIsStillEscaped:
    """A regression guard on 4b's half of the pair."""

    def test_mcnemar_still_escapes(self) -> None:
        from pathlib import Path

        src = Path("src/cli_modelarium/cli.py").read_text(encoding="utf-8")
        assert "escape(r.model_a)" in src
        assert "escape(mcnemar_pairing_caveat(affected))" in src
