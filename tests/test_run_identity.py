"""Run identity: started_at, run_id, experiment_key, invocation.

WHAT THESE PIN, AND WHY IT NEEDED PINNING. A probe against the published 0.1.9
ran one command twice, 93 seconds apart, and the whole JSON diff was two
fields - `latency_ms` and `ttft_ms`. Everything else, `cost_usd` and the output
string included, was byte-identical. The second run was the FASTER one, so
latency orders that pair backwards; filesystem mtime was the only remaining
signal and it does not survive `git add`, a copy or a tar extract.

So the tests below are not about the fields existing. They are about the four
properties a drift monitor actually needs:

    two runs of one command are DISTINGUISHABLE          (run_id, started_at)
    two runs of one command are RECOGNISABLY THE SAME    (experiment_key)
    two runs of different inputs are RECOGNISABLY NOT    (experiment_key)
    the flags recorded are the RESOLVED ones             (invocation)

`experiment_key` stability is proved by computing it twice from the same inputs
and asserting equality - never against a hardcoded digest, which would break the
day someone reorders a dict and would prove nothing about stability anyway.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import datetime

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk
from cli_modelarium.run_identity import build_run_identity, utc_now_iso


class _FixedProvider(BaseProvider):
    """Deterministic result with fixed timings, so only identity varies."""

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
            on_chunk("an answer")
        return CompletionResult(
            output="an answer",
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
    monkeypatch.setattr("cli_modelarium.cli._get_provider_instance", lambda name, **_k: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_test_fixture_00")
    return fake


def _compare(*extra: str) -> dict:
    result = CliRunner().invoke(
        cli_main,
        ["compare", "--models", "gpt-5.5", "--output-format", "json", *extra, "a prompt"],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _kwargs(**over):
    base = dict(
        command="compare",
        started_at="2026-09-06T12:00:00Z",
        prompts=["a prompt"],
        models=["gpt-5.5"],
        temperatures=[0.0],
        system_prompts=[None],
        judges=None,
        runs=1,
    )
    base.update(over)
    return base


class TestAllFourArePresent:
    def test_compare_json_carries_them(self, fixed_provider: _FixedProvider) -> None:
        payload = _compare()
        for field in ("started_at", "run_id", "experiment_key", "invocation"):
            assert field in payload, f"{field} missing from compare JSON"

    def test_batch_json_carries_them_too(
        self, fixed_provider: _FixedProvider, tmp_path
    ) -> None:
        # Identity is as absent from batch as from compare, and nothing about
        # `started_at` is false in a batch run - unlike `methodology`, which is
        # compare-only because `scipy_version` would name a library batch
        # never loads.
        suite = tmp_path / "p.json"
        suite.write_text(json.dumps([{"id": "one", "prompt": "a prompt"}]), encoding="utf-8")
        result = CliRunner().invoke(
            cli_main, ["batch", str(suite), "--models", "gpt-5.5", "--output-format", "json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        for field in ("started_at", "run_id", "experiment_key", "invocation"):
            assert field in payload
        assert payload["invocation"]["command"] == "batch"

    def test_nothing_that_had_content_lost_it(self, fixed_provider: _FixedProvider) -> None:
        # These are additive. Every key a 0.2.0 consumer read must still be
        # there, with the same meaning.
        payload = _compare()
        for field in (
            "version",
            "pricing_as_of",
            "total_cost_usd",
            "total_results",
            "failed_results",
            "models_without_temperature",
            "significance_temperature_mixed",
            "results",
            "total_runs",
            "methodology",
        ):
            assert field in payload, f"{field} disappeared - these fields are additive"
        assert payload["total_results"] == 1
        assert payload["results"][0]["model"] == "gpt-5.5"


class TestStartedAt:
    def test_parses_as_iso_8601_and_is_utc(self, fixed_provider: _FixedProvider) -> None:
        raw = _compare()["started_at"]
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None, "must carry an offset, not be naive"
        assert parsed.utcoffset().total_seconds() == 0, "must be UTC"

    def test_spelled_with_z_and_second_precision(self) -> None:
        # Not cosmetic: jq's `fromdateiso8601` - the first thing a shell drift
        # monitor reaches for - rejects fractional seconds and rejects the
        # `+00:00` spelling. Two runs inside one second are separated by
        # `run_id`, which is the collision it exists to prevent.
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now_iso())

    def test_is_the_run_start_not_the_write_time(self, fixed_provider: _FixedProvider) -> None:
        # Bounds it from the outside: the recorded time must not be later than
        # the moment the command returned. A timestamp taken in `_format_json`
        # would be, on any run slower than a second.
        before = utc_now_iso()
        payload = _compare()
        after = utc_now_iso()
        assert before <= payload["started_at"] <= after


class TestRunId:
    def test_two_runs_in_one_process_differ(self, fixed_provider: _FixedProvider) -> None:
        # The property the whole feature exists for: the probe's two runs were
        # indistinguishable, and the faster one ran second.
        assert _compare()["run_id"] != _compare()["run_id"]

    def test_is_a_uuid(self, fixed_provider: _FixedProvider) -> None:
        import uuid

        uuid.UUID(_compare()["run_id"])  # raises if malformed

    def test_not_derived_from_the_timestamp(self) -> None:
        # Deriving it from the clock would reintroduce the same-second
        # collision it exists to prevent.
        a = build_run_identity(**_kwargs())
        b = build_run_identity(**_kwargs())
        assert a["started_at"] == b["started_at"]
        assert a["run_id"] != b["run_id"]


class TestExperimentKeyIsStable:
    def test_identical_inputs_give_the_same_key(self) -> None:
        # Computed twice, compared - never against a hardcoded digest, which
        # would break on a dict reordering and would prove nothing anyway.
        assert build_run_identity(**_kwargs())["experiment_key"] == (
            build_run_identity(**_kwargs())["experiment_key"]
        )

    def test_stable_across_two_real_runs(self, fixed_provider: _FixedProvider) -> None:
        first, second = _compare(), _compare()
        assert first["experiment_key"] == second["experiment_key"]
        assert first["run_id"] != second["run_id"], "same experiment, different runs"

    def test_started_at_does_not_enter_the_key(self) -> None:
        a = build_run_identity(**_kwargs(started_at="2026-01-01T00:00:00Z"))
        b = build_run_identity(**_kwargs(started_at="2026-12-31T23:59:59Z"))
        assert a["experiment_key"] == b["experiment_key"], "when is not what"


class TestExperimentKeyMoves:
    """One test per hashed input. Each must change the key on its own."""

    BASE = None

    def _key(self, **over) -> str:
        return build_run_identity(**_kwargs(**over))["experiment_key"]

    def test_prompt(self) -> None:
        assert self._key() != self._key(prompts=["a different prompt"])

    def test_models(self) -> None:
        assert self._key() != self._key(models=["gpt-5.5", "claude-opus-5"])

    def test_temperature(self) -> None:
        # THE CASE THE PROBE EXPOSED. One prompt at two temperatures produced
        # `p1` and `p2`, so a monitor grouping by `prompt_id` would read one
        # experiment as two. The same prompt at a different temperature IS a
        # different experiment, and the key has to say so.
        assert self._key() != self._key(temperatures=[0.7])

    def test_temperature_set_size(self) -> None:
        assert self._key() != self._key(temperatures=[0.0, 0.7])

    def test_system_prompt(self) -> None:
        assert self._key() != self._key(system_prompts=["You are terse."])

    def test_judges(self) -> None:
        assert self._key() != self._key(judges=["gpt-5.5"])

    def test_runs(self) -> None:
        # n=1 and n=10 over the same cells are not the same experiment: the
        # second answers a question about variance the first cannot, and a
        # monitor pooling them compares a point estimate to a distribution.
        assert self._key() != self._key(runs=10)

    def test_command(self) -> None:
        # compare and batch must never collide even on identical inputs -
        # `prompt_id` means different things in each.
        assert self._key() != self._key(command="batch")

    def test_model_order_is_not_canonicalised(self) -> None:
        # DELIBERATE. Sorting would make `--models a,b` and `--models b,a`
        # share a key, but compare's `prompt_id` is a positional row ordinal,
        # so `p1` is a different model in each. A consumer joining on
        # (experiment_key, prompt_id) would mis-align every row while both
        # keys agreed. A false "different" costs one skipped comparison; a
        # false "same" silently corrupts one.
        assert self._key(models=["a", "b"]) != self._key(models=["b", "a"])

    def test_key_is_short_enough_to_read(self) -> None:
        assert re.fullmatch(r"[0-9a-f]{16}", self._key())


class TestInvocationRecordsResolvedValues:
    def test_group_is_expanded(self, fixed_provider: _FixedProvider) -> None:
        # `all-flagship` is registry state that moves between versions, so the
        # group name alone would not let anyone reproduce the run.
        from cli_modelarium.models_registry import MODEL_GROUPS

        result = CliRunner().invoke(
            cli_main,
            ["compare", "--models", "all-flagship", "--output-format", "json", "a prompt"],
        )
        assert result.exit_code == 0, result.output
        recorded = json.loads(result.stdout)["invocation"]["models"]
        assert recorded == MODEL_GROUPS["all-flagship"], (
            "invocation must carry the expanded member list, not the group token"
        )
        assert "all-flagship" not in recorded
        assert len(recorded) > 1

    def test_temperatures_are_parsed_floats(self, fixed_provider: _FixedProvider) -> None:
        payload = _compare("--temperatures", "0,0.7")
        assert payload["invocation"]["temperatures"] == [0.0, 0.7]

    def test_command_is_named(self, fixed_provider: _FixedProvider) -> None:
        assert _compare()["invocation"]["command"] == "compare"

    def test_runs_is_not_duplicated_here(self, fixed_provider: _FixedProvider) -> None:
        # `total_runs` is already top-level and unconditional. A third copy of
        # one number is a third thing that can disagree.
        payload = _compare("--runs", "2")
        assert "runs" not in payload["invocation"]
        assert payload["total_runs"] == 2


class TestNoSecretReachesInvocation:
    """Asserted against the redaction path, not by reading the output.

    `invocation` is a hand-written allowlist rather than a redaction pass,
    because the highest-risk value has no pattern to match: `--local-url` can
    carry credentials in the userinfo position and `redact_secrets` covers the
    `AQ.Ab`, `AIza`, `x-goog-api-key` and `?key=` forms, not a `user:pass`
    pair. This proves both halves - that the pattern matcher would indeed miss
    it, and that the allowlist means it never gets the chance.
    """

    CANARY_URL = "http://canary_user:canary_pass_NOT_REAL@localhost:11434/v1"

    def test_redact_secrets_would_not_have_caught_it(self) -> None:
        # The premise. If this ever starts passing, the allowlist is still
        # correct but this test's reasoning needs rewriting.
        from cli_modelarium.security import redact_secrets

        assert "canary_pass_NOT_REAL" in redact_secrets(self.CANARY_URL), (
            "redact_secrets now matches URL userinfo - update this test's reasoning"
        )

    def test_local_url_never_reaches_the_payload(
        self, fixed_provider: _FixedProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = CliRunner().invoke(
            cli_main,
            [
                "compare",
                "--models",
                "gpt-5.5",
                "--local-url",
                self.CANARY_URL,
                "--output-format",
                "json",
                "a prompt",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "canary_pass_NOT_REAL" not in result.stdout
        assert "canary_user" not in result.stdout
        assert "local_url" not in json.loads(result.stdout)["invocation"]

    def test_file_paths_are_not_recorded(
        self, fixed_provider: _FixedProvider, tmp_path
    ) -> None:
        # A path leaks a home directory and a username, and the CONTENT that
        # matters is already recorded - the resolved system prompt is in
        # `invocation` and on every result row.
        sp = tmp_path / "secret_dir_name" / "sp.txt"
        sp.parent.mkdir()
        sp.write_text("You are terse.", encoding="utf-8")
        payload = _compare("--system-prompt-file", str(sp))
        assert "secret_dir_name" not in json.dumps(payload)
        assert payload["invocation"]["system_prompts"] == ["You are terse."]

    def test_invocation_keys_are_a_closed_set(self, fixed_provider: _FixedProvider) -> None:
        # The allowlist is the security boundary: anything not named here
        # cannot reach the payload, so a new flag cannot leak by default.
        allowed = {"command", "models", "temperatures", "system_prompts", "judges"}
        assert set(_compare()["invocation"]) <= allowed

    def test_output_destination_is_not_recorded(
        self, fixed_provider: _FixedProvider, tmp_path
    ) -> None:
        # Where a payload was written does not define the experiment - and the
        # stdout-versus-file parity test in test_stdout_machine_output.py runs
        # exactly that pair and compares the bytes.
        target = tmp_path / "out.json"
        result = CliRunner().invoke(
            cli_main, ["compare", "--models", "gpt-5.5", "--output", str(target), "a prompt"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert "output" not in payload["invocation"]
        assert str(tmp_path) not in json.dumps(payload["invocation"])


class TestMarkdownCarriesIdentity:
    def test_started_at_and_run_id_appear(
        self, fixed_provider: _FixedProvider, tmp_path
    ) -> None:
        target = tmp_path / "out.md"
        result = CliRunner().invoke(
            cli_main, ["compare", "--models", "gpt-5.5", "--output", str(target), "a prompt"]
        )
        assert result.exit_code == 0, result.output
        text = target.read_text(encoding="utf-8")
        assert "- Started at: " in text
        assert "- Run ID: " in text
        # Beside the two run-level facts the header already carried.
        assert "- Pricing data as of: " in text
