"""Stdout must carry the machine payload and nothing else.

Two independent bugs corrupted `--output-format json|csv` on stdout, and the
suite had 1236 tests without one that parsed stdout as JSON - which is why both
survived. Every test here parses the real stdout stream.

    1. Human output shared the stream. Ten sites across `batch` and `compare`
       wrote through the module console - progress, panels, warnings, the run
       summary - none of them gated on output format. JSON raised; CSV read a
       contaminating line as the header or as an extra row and raised nothing.

    2. Rich reflowed the payload at the terminal width. That one passes on a
       wide terminal and fails at 80 columns, which is what CI gives you.

The width tests deliberately do NOT use `capture_console`: CAPTURE_WIDTH is 200
precisely so nothing wraps, and it writes to a StringIO rather than stdout, so
it cannot exercise this path at all. `CliRunner(env={"COLUMNS": "80"})` is the
mechanism that reproduces the bug.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk

# Long enough to exceed 80 columns once serialized, and non-ASCII with a
# non-BMP codepoint so the byte-identity test actually exercises encoding -
# an ASCII fixture passes whether or not encoding is handled.
LONG_NON_ASCII = (
    "La capitale de la France est Paris, ville d'art et d'histoire - "
    "café, 日本語, 𝄞 and an emoji 😀, repeated so the line is comfortably "
    "wider than eighty columns when serialized into a payload."
)


class _FixedProvider(BaseProvider):
    """Returns a deterministic result. Timings are fixed so bytes are stable."""

    def __init__(self) -> None:
        self.name = "fake"

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if False:
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
    ) -> CompletionResult:
        if on_chunk is not None:
            on_chunk(LONG_NON_ASCII)
        return CompletionResult(
            output=LONG_NON_ASCII,
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.000123,
            latency_ms=42.0,
            ttft_ms=12.0,
            model=model,
            provider="fake",
            temperature=temperature,
        )


@pytest.fixture
def fixed_provider(monkeypatch: pytest.MonkeyPatch) -> _FixedProvider:
    fake = _FixedProvider()
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance",
        lambda name, **_kwargs: fake,
    )
    # `_validate_judge_models` reads `is_key_configured` directly rather than
    # going through `_get_provider_instance`, so the judging tests below need a
    # key present for validation to pass.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_test_fixture_00")
    return fake


@pytest.fixture
def prompts_file(tmp_path: Path) -> Path:
    path = tmp_path / "prompts.json"
    path.write_text(
        json.dumps([{"id": "p1", "prompt": "q one"}, {"id": "p2", "prompt": "q two"}]),
        encoding="utf-8",
    )
    return path


def _batch_args(prompts_file: Path, fmt: str, *extra: str) -> list[str]:
    return [
        "batch",
        str(prompts_file),
        "--models",
        "gpt-5.5",
        "--output-format",
        fmt,
        *extra,
    ]


def _compare_args(fmt: str, *extra: str) -> list[str]:
    return [
        "compare",
        "--models",
        "gpt-5.5",
        "--output-format",
        fmt,
        *extra,
        "a prompt",
    ]


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


# `ttft_ms` is measured off the wall clock in `StreamState.append_text`, so two
# invocations of the same command never agree on it. Mask that one field when
# comparing whole payloads; every other byte still has to match exactly.
_TTFT = re.compile(rb'("ttft_ms":\s*)[0-9.eE+-]+|(?<=,)\d+\.\d{6,}(?=,)')


def _mask_measured(payload: bytes) -> bytes:
    return _TTFT.sub(rb"\1<measured>", payload)


# ===== 4a / 4b: stdout parses, in both formats =====


class TestStdoutParses:
    def test_batch_json_stdout_parses(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        # The test whose absence let bug 1 ship: parsed from stdout, not from a
        # file and not from a formatter's return value.
        result = CliRunner().invoke(cli_main, _batch_args(prompts_file, "json"))
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["total_results"] == 2

    def test_batch_csv_stdout_has_full_header_and_exact_rows(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        # Header width alone is not enough in either direction. A leading
        # progress line makes the header one column; a trailing summary adds a
        # ROW while leaving the header at 23. csv.reader raises for neither.
        result = CliRunner().invoke(cli_main, _batch_args(prompts_file, "csv"))
        assert result.exit_code == 0, result.output
        rows = _rows(result.stdout)
        assert len(rows[0]) == 23, f"header should be the full column set, got {rows[0]}"
        assert len(rows) - 1 == 2, f"expected one row per prompt, got {len(rows) - 1}"

    def test_compare_json_stdout_parses(self, fixed_provider: _FixedProvider) -> None:
        result = CliRunner().invoke(cli_main, _compare_args("json"))
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["total_results"] == 1

    def test_compare_csv_stdout_has_full_header_and_exact_rows(
        self, fixed_provider: _FixedProvider
    ) -> None:
        result = CliRunner().invoke(cli_main, _compare_args("csv"))
        assert result.exit_code == 0, result.output
        rows = _rows(result.stdout)
        assert len(rows[0]) == 23
        assert len(rows) - 1 == 1


# ===== 4b2: the judging path, which enumeration missed twice =====


class TestJudgeToSDoesNotShareStdout:
    """The ToS panel fires on the DEFAULT judging path.

    `--no-judge-tos` is the opt-out, so a test that passes it to keep the
    output clean would pass while the bug is live. These deliberately do not.
    """

    def test_batch_json_with_judge_parses(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        result = CliRunner().invoke(
            cli_main, _batch_args(prompts_file, "json", "--judge", "gpt-5.5")
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["total_results"] == 2

    def test_compare_json_with_judge_parses(self, fixed_provider: _FixedProvider) -> None:
        result = CliRunner().invoke(cli_main, _compare_args("json", "--judge", "gpt-5.5"))
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["total_results"] == 1

    def test_compare_csv_with_judge_has_full_header(
        self, fixed_provider: _FixedProvider
    ) -> None:
        result = CliRunner().invoke(cli_main, _compare_args("csv", "--judge", "gpt-5.5"))
        assert result.exit_code == 0, result.output
        rows = _rows(result.stdout)
        assert len(rows[0]) == 23
        assert len(rows) - 1 == 1

    def test_the_tos_panel_still_reaches_the_user(
        self, fixed_provider: _FixedProvider
    ) -> None:
        # Moved, not suppressed: the disclosure is a legal notice, so it has to
        # stay visible somewhere.
        result = CliRunner().invoke(cli_main, _compare_args("json", "--judge", "gpt-5.5"))
        assert "Judge ToS" in result.stderr


# ===== 4c: the width test =====


class TestPayloadSurvivesANarrowTerminal:
    """Bug 2. Passes at 200 columns, fails at 80 - so pin the width."""

    @pytest.mark.parametrize("fmt", ["json", "csv"])
    def test_batch_stdout_at_eighty_columns(
        self, fixed_provider: _FixedProvider, prompts_file: Path, fmt: str
    ) -> None:
        result = CliRunner().invoke(
            cli_main, _batch_args(prompts_file, fmt), env={"COLUMNS": "80"}
        )
        assert result.exit_code == 0, result.output
        if fmt == "json":
            assert json.loads(result.stdout)["total_results"] == 2
        else:
            assert len(_rows(result.stdout)[0]) == 23

    @pytest.mark.parametrize("fmt", ["json", "csv"])
    def test_compare_stdout_at_eighty_columns(
        self, fixed_provider: _FixedProvider, fmt: str
    ) -> None:
        result = CliRunner().invoke(cli_main, _compare_args(fmt), env={"COLUMNS": "80"})
        assert result.exit_code == 0, result.output
        if fmt == "json":
            assert json.loads(result.stdout)["total_results"] == 1
        else:
            assert len(_rows(result.stdout)[0]) == 23

    def test_no_payload_line_is_clipped_to_the_terminal_width(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        # The failure mode directly: Rich wrapping puts every line at or under
        # the width. The response is longer than that, so an unwrapped payload
        # must exceed it.
        result = CliRunner().invoke(
            cli_main, _batch_args(prompts_file, "json"), env={"COLUMNS": "80"}
        )
        assert max(len(line) for line in result.stdout.splitlines()) > 80


# ===== 4d: stdout is byte-identical to the file =====


class TestStdoutMatchesFileOutput:
    """Same input, two destinations, identical bytes.

    Uses a non-ASCII payload with a non-BMP codepoint on purpose: an ASCII
    fixture passes whether or not the encoding is pinned.

    Compares `stdout_bytes`, not `stdout`. Click's `Result.stdout` rewrites
    CRLF to LF when it decodes, and `csv.DictWriter` emits CRLF per RFC 4180 -
    so the decoded accessor reports a difference the stream does not have.
    """

    @pytest.mark.parametrize("fmt", ["json", "csv"])
    def test_batch(
        self, fixed_provider: _FixedProvider, prompts_file: Path, tmp_path: Path, fmt: str
    ) -> None:
        target = tmp_path / f"out.{fmt}"
        runner = CliRunner()
        piped = runner.invoke(cli_main, _batch_args(prompts_file, fmt))
        written = runner.invoke(
            cli_main, ["batch", str(prompts_file), "--models", "gpt-5.5", "--output", str(target)]
        )
        assert piped.exit_code == 0 and written.exit_code == 0
        assert _mask_measured(piped.stdout_bytes) == _mask_measured(target.read_bytes())

    @pytest.mark.parametrize("fmt", ["json", "csv"])
    def test_compare(
        self, fixed_provider: _FixedProvider, tmp_path: Path, fmt: str
    ) -> None:
        target = tmp_path / f"out.{fmt}"
        runner = CliRunner()
        piped = runner.invoke(cli_main, _compare_args(fmt))
        written = runner.invoke(
            cli_main, ["compare", "--models", "gpt-5.5", "--output", str(target), "a prompt"]
        )
        assert piped.exit_code == 0 and written.exit_code == 0
        assert _mask_measured(piped.stdout_bytes) == _mask_measured(target.read_bytes())

    def test_the_non_bmp_codepoint_survives(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        result = CliRunner().invoke(cli_main, _batch_args(prompts_file, "json"))
        output = json.loads(result.stdout)["results"][0]["output"]
        assert "𝄞" in output and "日本語" in output


# ===== 4e: progress moved, not dropped =====


class TestProgressStillReachesTheUser:
    def test_progress_and_summary_are_on_stderr(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        result = CliRunner().invoke(cli_main, _batch_args(prompts_file, "json"))
        assert "Running batch" in result.stderr
        assert "succeeded" in result.stderr

    def test_stdout_holds_none_of_it(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        result = CliRunner().invoke(cli_main, _batch_args(prompts_file, "json"))
        assert "Running batch" not in result.stdout
        assert "succeeded" not in result.stdout


# ===== 4f: the human paths are untouched =====


class TestHumanOutputUnchanged:
    def test_default_batch_markdown_still_renders_on_stdout(
        self, fixed_provider: _FixedProvider, prompts_file: Path
    ) -> None:
        # No --output-format, so stdout is a report for a person to read and
        # the scope rule does not apply.
        result = CliRunner().invoke(
            cli_main, ["batch", str(prompts_file), "--models", "gpt-5.5"]
        )
        assert result.exit_code == 0, result.output
        assert "Cli Modelarium" in result.stdout
        assert "Running batch" in result.stdout

    def test_compare_rich_table_still_on_stdout(self, fixed_provider: _FixedProvider) -> None:
        result = CliRunner().invoke(cli_main, ["compare", "--models", "gpt-5.5", "a prompt"])
        assert result.exit_code == 0, result.output
        assert "gpt-5.5" in result.stdout

    def test_wrote_path_notice_still_on_stdout(
        self, fixed_provider: _FixedProvider, prompts_file: Path, tmp_path: Path
    ) -> None:
        # --output means stdout is not a data pipe, so the notice belongs there.
        target = tmp_path / "out.json"
        result = CliRunner().invoke(
            cli_main,
            ["batch", str(prompts_file), "--models", "gpt-5.5", "--output", str(target)],
        )
        assert result.exit_code == 0, result.output
        assert "Wrote" in result.stdout
