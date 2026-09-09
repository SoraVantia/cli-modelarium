"""An unhandled crash must not print a key, and must still print its frames.

Provider errors are already safe: all four `_reraise` shapes redact and
re-raise `from None`, so the SDK exception never reaches a traceback. The gap
was a crash outside that path, where Python prints the traceback itself.

The exposure is narrow but real. Of the four SDK families only
`google.genai.APIError` stringifies the response body, and
`httpx.HTTPStatusError` formats the request URL - Google being the one provider
that carries its key in the URL. Anthropic and OpenAI stringify neither.
"""

from __future__ import annotations

import sys

import pytest

from cli_modelarium import cli

# Synthetic throughout - the shape is what matters, not the value.
GOOGLE_AUTH_KEY = "AQ.AbSyntheticTestKey-not_a_real_credential01"
ANTHROPIC_KEY = "sk-ant-api03-NOT_A_REAL_KEY_test_fixture"


def _boom_with(secret: str):
    def _raise() -> None:
        raise RuntimeError(f"connection failed for key {secret}")

    return _raise


class TestUncaughtTracebackIsRedacted:
    @pytest.mark.parametrize("secret", [GOOGLE_AUTH_KEY, ANTHROPIC_KEY])
    def test_the_key_is_scrubbed_from_the_traceback(
        self, secret: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cli, "main", _boom_with(secret))
        with pytest.raises(SystemExit) as exc:
            cli.run()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert secret not in err
        assert "***REDACTED***" in err

    def test_the_frames_survive(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A one-line message would trade a leak for an unreportable bug, so the
        # whole traceback is reprinted - header, frame, and exception line.
        monkeypatch.setattr(cli, "main", _boom_with(GOOGLE_AUTH_KEY))
        with pytest.raises(SystemExit):
            cli.run()
        err = capsys.readouterr().err
        assert "Traceback (most recent call last)" in err
        assert "_raise" in err  # the raising frame, by name
        assert "test_uncaught_traceback_redaction.py" in err  # and its file
        assert "RuntimeError" in err

    def test_it_goes_to_stderr_not_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cli, "main", _boom_with(ANTHROPIC_KEY))
        with pytest.raises(SystemExit):
            cli.run()
        captured = capsys.readouterr()
        assert "Traceback" in captured.err
        assert "Traceback" not in captured.out


class TestNormalExitsArePassedThrough:
    """`run` must not become a second exit-code policy."""

    @pytest.mark.parametrize("code", [0, 1, 2])
    def test_click_exit_codes_are_untouched(
        self, code: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # click returns every exit code by raising SystemExit; swallowing it
        # would silently rewrite EXIT_ASSERTION_FAILED and EXIT_CALL_FAILED.
        def _exit() -> None:
            sys.exit(code)

        monkeypatch.setattr(cli, "main", _exit)
        with pytest.raises(SystemExit) as exc:
            cli.run()
        assert exc.value.code == code

    def test_keyboard_interrupt_is_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _interrupt() -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli, "main", _interrupt)
        with pytest.raises(KeyboardInterrupt):
            cli.run()


class TestBothEntryPointsUseIt:
    def test_the_module_entry_point_calls_run(self) -> None:
        from cli_modelarium import __main__

        assert __main__.run is cli.run

    def test_the_console_script_points_at_run(self) -> None:
        # A wrapper only reachable through `python -m` would leave the
        # installed `cli-modelarium` command uncovered.
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        assert 'cli-modelarium = "cli_modelarium.cli:run"' in pyproject.read_text()
