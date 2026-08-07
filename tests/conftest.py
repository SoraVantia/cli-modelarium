"""Shared test fixtures for the cli-modelarium suite.

Two autouse fixtures keep tests hermetic:
    * `_mock_keyring`  - swaps in an in-memory keyring backend per test
    * `_clean_env`     - strips any leftover *_API_KEY env vars

Tests that need to set an env var should use monkeypatch explicitly.

Rendered-output tests use `capture_console` plus the `PANEL_CORNERS` /
`flatten_rendered` helpers here, so that assertions about Rich output do not
depend on the platform. See their docstrings for the two ways that bites.
"""

from __future__ import annotations

import io
import os
from types import SimpleNamespace
from typing import Any

import keyring
import keyring.backend
import keyring.errors
import pytest
from rich.console import Console

# Wide enough that no panel this tool renders will wrap.
CAPTURE_WIDTH = 200

# Rich draws a Panel with the ROUNDED box, but substitutes SQUARE when
# `legacy_windows` is set - arcs do not render on a legacy Windows console
# (rich.box.Box.substitute -> LEGACY_WINDOWS_SUBSTITUTIONS). So the top-left
# corner is `╭` on POSIX and `┌` on Windows CI. Any helper that counts
# or strips panel borders must accept both sets or it passes on one platform
# and fails on the other.
PANEL_CORNERS = "╭╮╰╯┌┐└┘"
PANEL_BORDER_CHARS = PANEL_CORNERS + "│─"


class InMemoryKeyring(keyring.backend.KeyringBackend):
    """A keyring backend that stores credentials in a process-local dict."""

    priority = 1

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, servicename: str, username: str, password: str) -> None:
        self._store[(servicename, username)] = password

    def get_password(self, servicename: str, username: str) -> str | None:
        return self._store.get((servicename, username))

    def delete_password(self, servicename: str, username: str) -> None:
        key = (servicename, username)
        if key not in self._store:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._store[key]


@pytest.fixture(autouse=True)
def _mock_keyring() -> Any:
    backend = InMemoryKeyring()
    original = keyring.get_keyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(original)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in list(os.environ):
        if var.endswith("_API_KEY"):
            monkeypatch.delenv(var, raising=False)


# ===== rendered-output helpers =====


@pytest.fixture
def capture_console() -> Console:
    """A Console writing to a buffer with the width pinned.

    Rich falls back to the OS terminal width when there is no TTY, which
    differs by platform in CI. Without a pinned width a substring assertion
    silently becomes a test of where Rich chose to wrap. Read the buffer back
    with `console.file.getvalue()`.
    """
    return Console(file=io.StringIO(), force_terminal=False, width=CAPTURE_WIDTH)


def count_panels(rendered: str) -> int:
    """Number of Rich panels in captured output, counted by top-left corner.

    Counts BOTH corner glyphs: `╭` on POSIX, `┌` under legacy Windows. See
    PANEL_CORNERS above for why the two differ.
    """
    return rendered.count("╭") + rendered.count("┌")


def flatten_rendered(rendered: str) -> str:
    """Panel text with borders stripped and wrapping collapsed.

    Rich hard-wraps the body, so a phrase assertion on raw output silently
    depends on where the wrap happens to fall. Flattening first means such a
    test pins the wording rather than the terminal width. Strips both corner
    sets, so no border residue survives on either platform.
    """
    stripped = "".join(" " if c in PANEL_BORDER_CHARS else c for c in rendered)
    return " ".join(stripped.split())


# ===== OpenAI streaming mock helpers =====


def _make_text_chunk(content: str) -> SimpleNamespace:
    """Build a fake OpenAI ChatCompletionChunk carrying a delta.content payload."""
    delta = SimpleNamespace(content=content)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice], usage=None)


def _make_usage_chunk(
    input_tokens: int, output_tokens: int, cached_tokens: int = 0
) -> SimpleNamespace:
    """Build a fake final chunk that carries the usage payload (no choices)."""
    details = SimpleNamespace(cached_tokens=cached_tokens)
    usage = SimpleNamespace(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        prompt_tokens_details=details,
    )
    return SimpleNamespace(choices=[], usage=usage)


class FakeAsyncStream:
    """Fake AsyncStream that yields a pre-built list of chunks."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> FakeAsyncStream:
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture
def fake_openai_stream() -> Any:
    """Return a builder that produces a FakeAsyncStream from text chunks + usage."""

    def _build(
        text_chunks: list[str],
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
    ) -> FakeAsyncStream:
        chunks: list[Any] = [_make_text_chunk(t) for t in text_chunks]
        chunks.append(_make_usage_chunk(input_tokens, output_tokens, cached_tokens))
        return FakeAsyncStream(chunks)

    return _build
