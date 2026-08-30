"""CLI-level tests for the `batch` command.

Strategy: monkeypatch `_get_provider_instance` to return a fake that records
every call and returns a deterministic CompletionResult. Then drive the
command via Click's CliRunner with various flag combinations.
"""

from __future__ import annotations

import csv
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk

# ===== fake provider =====


class _RecordingProvider(BaseProvider):
    """Returns a preset CompletionResult and records every call."""

    def __init__(self) -> None:
        self.name = "fake"
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "temperature": temperature,
                "system_prompt": system_prompt,
            }
        )
        text = f"answer for {prompt[:20]}"
        if on_chunk is not None:
            on_chunk(text)
        return CompletionResult(
            output=text,
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
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> _RecordingProvider:
    """Install the fake provider for every provider name the CLI requests."""
    fake = _RecordingProvider()
    monkeypatch.setattr(
        "cli_modelarium.cli._get_provider_instance",
        lambda name, **_kwargs: fake,
    )
    return fake


# ===== helpers =====


def _write_txt(path: Path, prompts: list[str]) -> None:
    path.write_text("\n".join(prompts) + "\n", encoding="utf-8")


def _write_json(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items), encoding="utf-8")


# ===== happy paths =====


class TestBasicBatchFlow:
    def test_csv_output(self, fake_provider: _RecordingProvider, tmp_path: Path) -> None:
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["what is 2+2?", "what is 3+3?"])
        output = tmp_path / "results.csv"

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--output",
                str(output),
            ],
        )

        assert result.exit_code == 0, result.output
        assert output.exists()
        # Parse and verify shape.
        with output.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["prompt_id"] == "p1"
        assert rows[0]["model"] == "gpt-5.5"
        assert rows[0]["output"].startswith("answer for")

    def test_json_output(self, fake_provider: _RecordingProvider, tmp_path: Path) -> None:
        prompts_file = tmp_path / "p.json"
        _write_json(prompts_file, [{"id": "q1", "prompt": "hi"}, {"id": "q2", "prompt": "bye"}])
        output = tmp_path / "results.json"

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--output",
                str(output),
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["total_results"] == 2
        ids = [r["prompt_id"] for r in payload["results"]]
        assert "q1" in ids and "q2" in ids

    def test_output_format_override(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        """--output-format wins over the inferred extension."""
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["a"])
        # Deliberately use .data extension which detect_output_format can't handle.
        output = tmp_path / "results.data"

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--output",
                str(output),
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        # Content should parse as JSON regardless of the .data extension.
        json.loads(output.read_text(encoding="utf-8"))

    def test_stdout_default_is_markdown(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["hi"])

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            ["batch", str(prompts_file), "--models", "gpt-5.5"],
        )

        assert result.exit_code == 0
        assert "Cli Modelarium" in result.output  # markdown title rendered


# ===== input/output validation =====


class TestOutputFileValidation:
    def test_missing_input_file_fails(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            ["batch", str(tmp_path / "missing.txt"), "--models", "gpt-5.5"],
        )
        assert result.exit_code != 0
        # Click's exists=True catches this.
        assert "does not exist" in result.output.lower() or "not found" in result.output.lower()

    def test_missing_models_flag(self, fake_provider: _RecordingProvider, tmp_path: Path) -> None:
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["hi"])

        runner = CliRunner()
        result = runner.invoke(cli_main, ["batch", str(prompts_file)])

        assert result.exit_code != 0
        # Click's required=True for --models triggers this.
        assert "models" in result.output.lower()

    def test_existing_output_without_force_refused(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["hi"])
        existing = tmp_path / "existing.csv"
        existing.write_text("pre-existing", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--output",
                str(existing),
            ],
        )

        assert result.exit_code != 0
        assert "already exists" in result.output.lower()
        assert "--force" in result.output
        # The existing file is untouched.
        assert existing.read_text(encoding="utf-8") == "pre-existing"

    def test_existing_output_with_force_overwrites(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["hi"])
        existing = tmp_path / "existing.csv"
        existing.write_text("pre-existing", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--output",
                str(existing),
                "--force",
            ],
        )

        assert result.exit_code == 0, result.output
        # Real CSV data replaced the placeholder.
        assert "prompt_id" in existing.read_text(encoding="utf-8")

    def test_overlapping_input_and_output_refused(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        """Defensive: refuse to write output over the input file."""
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["hi"])

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--output",
                str(prompts_file),
                "--force",
            ],
        )
        assert result.exit_code != 0
        assert "input" in result.output.lower()


# ===== per-prompt system override =====


class TestPerPromptSystemOverride:
    def test_json_system_beats_command_line(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "p.json"
        _write_json(
            prompts_file,
            [
                {"id": "p1", "prompt": "a", "system": "per-prompt-system"},
                {"id": "p2", "prompt": "b"},
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--system-prompt",
                "command-line-system",
            ],
        )

        assert result.exit_code == 0, result.output
        # p1 used its own system. p2 used the command-line one.
        sps_for_p1 = [c["system_prompt"] for c in fake_provider.calls if c["prompt"] == "a"]
        sps_for_p2 = [c["system_prompt"] for c in fake_provider.calls if c["prompt"] == "b"]
        assert sps_for_p1 == ["per-prompt-system"]
        assert sps_for_p2 == ["command-line-system"]


# ===== --max-cost =====


class TestMaxCost:
    def test_estimate_over_max_cost_refuses(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "p.txt"
        # Set up a batch that estimates to ~$0.0175 per call (gpt-5.5 with
        # 500 in + 500 out tokens). With --max-cost 0.001 we refuse.
        _write_txt(prompts_file, ["one"])

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--max-cost",
                "0.001",
            ],
        )

        assert result.exit_code != 0
        assert "estimated cost" in result.output.lower()
        # No provider calls happened.
        assert fake_provider.calls == []

    def test_estimate_under_max_cost_proceeds(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["one"])

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5",
                "--max-cost",
                "10.0",
            ],
        )

        assert result.exit_code == 0, result.output
        assert len(fake_provider.calls) == 1


# ===== --force-large =====


class TestForceLarge:
    def test_over_prompt_cap_without_force_refused(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        # 1001 prompts (just over the cap).
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, [f"prompt {i}" for i in range(1001)])

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            ["batch", str(prompts_file), "--models", "gpt-5.5"],
        )

        assert result.exit_code != 0
        assert "--force-large" in result.output


# ===== empty input =====


class TestEmptyBatch:
    def test_empty_file_exits_non_zero_and_makes_no_calls(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        """An empty suite evaluated nothing, so it must not report success.

        It used to exit 0, which made a truncated or mis-generated suite
        indistinguishable from a green run - and silently skipped any
        --min-pass-rate the caller had set.
        """
        prompts_file = tmp_path / "empty.txt"
        prompts_file.write_text("", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            ["batch", str(prompts_file), "--models", "gpt-5.5"],
        )

        assert result.exit_code == 2
        assert "no prompts" in result.output.lower() or "empty" in result.output.lower()
        assert fake_provider.calls == []

    def test_empty_file_does_not_silently_satisfy_a_gate(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "empty.json"
        prompts_file.write_text("[]", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch", str(prompts_file), "--models", "gpt-5.5",
                "--min-pass-rate", "0.99",
            ],
        )

        assert result.exit_code != 0, result.output
        assert fake_provider.calls == []


# ===== matrix expansion =====


class TestMatrixExpansion:
    def test_two_prompts_two_models_two_temps_makes_eight_calls(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts_file = tmp_path / "p.txt"
        _write_txt(prompts_file, ["one", "two"])

        runner = CliRunner()
        result = runner.invoke(
            cli_main,
            [
                "batch",
                str(prompts_file),
                "--models",
                "gpt-5.5,gpt-5.4",
                "--temperatures",
                "0.0,1.0",
            ],
        )

        assert result.exit_code == 0, result.output
        # 2 prompts x 2 models x 2 temps = 8
        assert len(fake_provider.calls) == 8


# ===== gate bypasses: a run that evaluated nothing must not report success =====


class TestForgottenBatchVerb:
    """`cli-modelarium suite.json --models X` used to send the FILENAME to the
    model as a prompt, bill the call, never parse the suite, and exit 0.
    """

    def test_bare_filename_is_rejected_and_reaches_no_provider(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        suite = tmp_path / "eval_suite.json"
        suite.write_text(
            json.dumps([{"id": "p1", "prompt": "x", "assertions": []}]), encoding="utf-8"
        )

        result = CliRunner().invoke(cli_main, [str(suite), "--models", "gpt-5.5"])

        assert result.exit_code == 2, result.output
        assert "is a file, not a prompt" in result.output
        assert "cli-modelarium batch" in result.output
        assert fake_provider.calls == []

    def test_any_existing_file_is_rejected_not_just_batch_extensions(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        """No extension check: a suite saved as .yaml would otherwise still
        run silently as a prompt.
        """
        suite = tmp_path / "eval_suite.yaml"
        suite.write_text("- prompt: x\n", encoding="utf-8")

        result = CliRunner().invoke(cli_main, [str(suite), "--models", "gpt-5.5"])

        assert result.exit_code == 2, result.output
        assert fake_provider.calls == []

    def test_bare_prompt_shorthand_still_works(
        self, fake_provider: _RecordingProvider
    ) -> None:
        """The feature the rewrite exists for. 89 test invocations rely on it."""
        result = CliRunner().invoke(
            cli_main,
            ["Explain quantum computing in one sentence", "--models", "gpt-5.5", "--no-stream"],
        )

        assert result.exit_code == 0, result.output
        assert len(fake_provider.calls) == 1

    def test_a_prompt_naming_a_real_file_can_still_be_forced(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        """The escape hatch the error message names, for the rare prompt that
        happens to match a path on disk.
        """
        collide = tmp_path / "README.md"
        collide.write_text("# hi\n", encoding="utf-8")

        result = CliRunner().invoke(
            cli_main, ["compare", str(collide), "--models", "gpt-5.5", "--no-stream"]
        )

        assert result.exit_code == 0, result.output
        assert len(fake_provider.calls) == 1
        assert fake_provider.calls[0]["prompt"] == str(collide)


class TestNoAssertionsConflictsWithGateFlags:
    """--no-assertions skips every assertion, so gating on the result is
    self-contradictory. It used to be accepted: failing assertions exited 0
    with no warning that the gate had been switched off.
    """

    @pytest.mark.parametrize(
        "gate", [["--min-pass-rate", "0.99"], ["--strict-assertions"]]
    )
    def test_rejected_before_any_call(
        self, fake_provider: _RecordingProvider, tmp_path: Path, gate: list[str]
    ) -> None:
        prompts = tmp_path / "p.json"
        prompts.write_text(
            json.dumps(
                [{"id": "p1", "prompt": "x", "assertions": [{"type": "contains", "value": "NOPE"}]}]
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(
            cli_main,
            ["batch", str(prompts), "--models", "gpt-5.5", "--no-assertions", *gate],
        )

        assert result.exit_code == 2, result.output
        assert "mutually exclusive" in result.output
        assert fake_provider.calls == []


class TestIncludeReasoningRejectedOnBatch:
    """The flag was accepted and never read, while --help advertised it.

    Rejected rather than wired: wiring it would put judge reasoning into
    markdown and CSV and falsify the privacy note in nine READMEs. Rejected
    rather than removed: a documented flag collapsing into "no such option"
    is the worse message.
    """

    def test_batch_rejects_it_before_any_call(
        self, fake_provider: _RecordingProvider, tmp_path: Path
    ) -> None:
        prompts = tmp_path / "p.json"
        _write_json(prompts, [{"id": "p1", "prompt": "x"}])

        result = CliRunner().invoke(
            cli_main,
            [
                "batch", str(prompts), "--models", "gpt-5.5",
                "--judge", "claude-opus-4-7", "--no-judge-tos",
                "--include-reasoning",
            ],
        )

        assert result.exit_code == 2, result.output
        assert "not supported on `batch`" in result.output
        assert "It works on `compare`" in result.output
        assert fake_provider.calls == []

    def test_the_flag_is_still_advertised_rather_than_unknown(self) -> None:
        result = CliRunner().invoke(cli_main, ["batch", "--help"])

        assert result.exit_code == 0
        assert "--include-reasoning" in result.output
