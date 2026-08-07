"""Guards on how the suite asserts about Rich output.

Rendered-output tests have failed on Windows CI twice over for reasons that a
green Linux run cannot surface, so both conventions are enforced here rather
than remembered:

    1. Every `Console(...)` a test constructs must pin an explicit `width`.
       Rich falls back to the OS terminal width with no TTY, and CI runners
       disagree about it. Without a pinned width a substring assertion quietly
       becomes a test of where Rich chose to wrap.

    2. No test may hardcode one half of a platform-dependent box glyph. Rich
       renders a Panel with ROUNDED corners (`╭`) on POSIX and substitutes
       SQUARE (`┌`) under legacy Windows. Counting or stripping only one set
       passes on one platform and fails on the other - which is exactly what
       turned all four Windows jobs red on 0.1.5.

Both checks parse the test sources, so they cover files that do not exist yet.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest
from rich.console import Console
from rich.panel import Panel

from tests.conftest import (
    CAPTURE_WIDTH,
    PANEL_BORDER_CHARS,
    count_panels,
    flatten_rendered,
)

TESTS_DIR = Path(__file__).parent
TEST_SOURCES = sorted(TESTS_DIR.glob("*.py"))

# The two corner sets Rich picks between. Each pair is (posix, legacy_windows).
CORNER_PAIRS = [("╭", "┌"), ("╮", "┐"), ("╰", "└"), ("╯", "┘")]


def _console_calls(tree: ast.AST) -> list[ast.Call]:
    """Every `Console(...)` / `rich.console.Console(...)` call in a module."""
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if name == "Console":
            out.append(node)
    return out


def _string_literals(tree: ast.AST) -> list[tuple[int, str]]:
    return [
        (n.lineno, n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


class TestConsoleWidthIsPinned:
    """Convention 1: no bare Console in the test suite."""

    @pytest.mark.parametrize("path", TEST_SOURCES, ids=lambda p: p.name)
    def test_every_console_pins_a_width(self, path: Path) -> None:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders = [
            f"{path.name}:{call.lineno}"
            for call in _console_calls(tree)
            if not any(kw.arg == "width" for kw in call.keywords)
        ]
        assert not offenders, (
            f"Console constructed without an explicit width at {offenders}. "
            f"Use the `capture_console` fixture, or pass width=... explicitly. "
            f"Rich otherwise reads the OS terminal width, which differs between "
            f"CI runners and makes substring assertions platform-dependent."
        )

    def test_the_check_can_actually_see_a_console_call(self) -> None:
        # A parser that matched nothing would make the guard above vacuous.
        found = sum(
            len(_console_calls(ast.parse(p.read_text(encoding="utf-8")))) for p in TEST_SOURCES
        )
        assert found >= 3, f"expected the suite to construct several Consoles, found {found}"

    def test_a_bare_console_would_be_caught(self) -> None:
        # Positive control for the parser, without touching a real file.
        tree = ast.parse("from rich.console import Console\nc = Console(file=buf)\n")
        calls = _console_calls(tree)
        assert len(calls) == 1
        assert not any(kw.arg == "width" for kw in calls[0].keywords)


class TestNoHalfHardcodedBoxGlyph:
    """Convention 2: never hardcode one platform's corner glyph."""

    @pytest.mark.parametrize("path", TEST_SOURCES, ids=lambda p: p.name)
    def test_corner_glyphs_are_handled_in_pairs(self, path: Path) -> None:
        # Checked per FILE, not per literal: a module that names `╭` anywhere
        # must also know about `┌`. That is the invariant that broke, and it
        # exempts the pair DEFINITIONS here and in conftest, which legitimately
        # list one glyph per side.
        literals = [text for _, text in _string_literals(ast.parse(
            path.read_text(encoding="utf-8"), filename=str(path)
        ))]
        blob = "".join(literals)
        offenders = [
            f"{path.name} names {posix!r} but never {windows!r}"
            if posix in blob
            else f"{path.name} names {windows!r} but never {posix!r}"
            for posix, windows in CORNER_PAIRS
            if (posix in blob) != (windows in blob)
        ]
        assert not offenders, (
            f"Half a box-glyph pair hardcoded: {offenders}. Rich substitutes "
            f"ROUNDED for SQUARE under legacy_windows, so a file that names "
            f"only one side passes on one platform and fails on the other. Use "
            f"count_panels() / flatten_rendered() from conftest."
        )


class TestSharedHelpersAreThemselvesPlatformProof:
    """The helpers the conventions point at must survive both renderings."""

    @pytest.mark.parametrize("legacy_windows", [False, True], ids=["posix", "legacy-windows"])
    def test_count_panels_and_flatten_agree_across_platforms(self, legacy_windows: bool) -> None:
        buf = io.StringIO()
        console = Console(
            file=buf,
            force_terminal=False,
            width=CAPTURE_WIDTH,
            legacy_windows=legacy_windows,
        )
        console.print(Panel("the body text", title="A Title"))
        rendered = buf.getvalue()

        assert count_panels(rendered) == 1
        flat = flatten_rendered(rendered)
        assert flat == "A Title the body text", flat
        # No border residue survives flattening on either platform.
        assert not set(flat) & set(PANEL_BORDER_CHARS)

    def test_two_panels_count_as_two(self, legacy_windows: bool = True) -> None:
        buf = io.StringIO()
        console = Console(
            file=buf, force_terminal=False, width=CAPTURE_WIDTH, legacy_windows=legacy_windows
        )
        console.print(Panel("one"))
        console.print(Panel("two"))
        assert count_panels(buf.getvalue()) == 2

    def test_counting_only_the_posix_corner_would_fail_on_windows(self) -> None:
        # Pins the exact regression: the pre-fix helper returned 0 here.
        buf = io.StringIO()
        Console(
            file=buf, force_terminal=False, width=CAPTURE_WIDTH, legacy_windows=True
        ).print(Panel("x"))
        rendered = buf.getvalue()
        assert rendered.count("╭") == 0, "legacy Windows should not emit a rounded corner"
        assert count_panels(rendered) == 1, "but the shared helper must still see one panel"
