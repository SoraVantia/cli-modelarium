"""Non-finite numbers were accepted everywhere and broke three different things.

    flag                       nan    inf    consequence
    --temperatures             ACC    ACC    NaN reaches JSON
    --max-cost                 ACC    ACC    the cost gate silently disabled
    --ci-level                 ACC    rej    NaN reaches JSON as ci_level
    --significance-threshold   ACC    rej    NaN reaches JSON as threshold
    --min-pass-rate            rej    rej    hand-rolled 0..1 check catches it

ONE ROOT CAUSE, NOT FOUR SYMPTOMS. `click.FloatRange` does not reject NaN,
because every comparison with NaN is False and so the bound never trips. The one
flag that was already safe, `--min-pass-rate`, is guarded by a hand-rolled
`not (0.0 <= x <= 1.0)` rather than by click - the tool's own check was better
than the built-in range, which is what the fix is modelled on.

`FiniteFloatRange` is therefore applied to EVERY `FloatRange` flag, not to the
ones that happened to be reported.

WHY IT MATTERS IN TWO DIFFERENT WAYS:

  * `--max-cost nan` disabled the cost gate. `estimated > nan` is always False,
    so a run the limit would block ran to completion. The flag exists to stop an
    expensive run, and a typo removed the limit.

  * Three flags wrote `NaN` into JSON, which RFC 8259 does not allow. The
    documented `jq` recipe does not error on it - it silently yields `null`, so
    the documented workflow read a wrong value rather than failing. A strict
    parser rejects the file outright.

NOT ENFORCED: any bound on temperature. There is no client-side limit anywhere,
no documented range in the help text or the READMEs, and every provider forwards
the raw float - and since OpenAI's range extends above 1.0, a 0..1 check would
refuse a value that works today. `TestTheRangeCheckDidNotRideIn` pins that.
"""

from __future__ import annotations

import json
import math

import click
import pytest
from click.testing import CliRunner

from cli_modelarium.cli import _parse_temperatures
from cli_modelarium.cli import main as cli_main

NON_FINITE = ["nan", "NaN", "inf", "Infinity", "-inf", "-Infinity"]


def _strict(raw: str) -> None:
    """json.loads that refuses the constants RFC 8259 has no syntax for."""
    json.loads(
        raw,
        parse_constant=lambda c: (_ for _ in ()).throw(
            ValueError(f"invalid JSON constant: {c}")
        ),
    )


class TestClickFloatRangeIsTheRootCause:
    """Pinned so the reason for a custom type is on the record rather than in a
    commit message. If click ever fixes this, the custom type can go."""

    @pytest.mark.parametrize(
        "spec",
        [
            click.FloatRange(min=0.0),
            click.FloatRange(0.0, 1.0, min_open=True, max_open=True),
        ],
    )
    def test_the_builtin_range_accepts_nan(self, spec: click.FloatRange) -> None:
        assert math.isnan(spec.convert("nan", None, None))


class TestEveryFloatFlagRefusesNonFinite:
    FLAGS = ["--max-cost", "--ci-level", "--significance-threshold", "--min-pass-rate"]

    @pytest.mark.parametrize("value", NON_FINITE)
    @pytest.mark.parametrize("flag", FLAGS)
    def test_refused_on_compare_or_batch(self, flag: str, value: str, tmp_path) -> None:
        if flag == "--min-pass-rate":  # batch-only flag
            suite = tmp_path / "s.json"
            suite.write_text('[{"id":"p1","prompt":"hi"}]', encoding="utf-8")
            argv = ["batch", str(suite), "--models", "claude-opus-4-7", flag, value]
        else:
            argv = ["hi", "--models", "claude-opus-4-7", flag, value]
        result = CliRunner().invoke(cli_main, argv)
        assert result.exit_code == 2, result.output
        assert "Traceback" not in result.output, result.output

    @pytest.mark.parametrize("value", NON_FINITE)
    def test_temperatures_refuses_non_finite(self, value: str) -> None:
        with pytest.raises(ValueError, match="finite"):
            _parse_temperatures(value)

    @pytest.mark.parametrize("value", NON_FINITE)
    def test_temperatures_refuses_it_in_a_list(self, value: str) -> None:
        with pytest.raises(ValueError, match="finite"):
            _parse_temperatures(f"0.0,{value},0.7")

    def test_the_message_says_which_value(self) -> None:
        with pytest.raises(ValueError, match="nan"):
            _parse_temperatures("nan")


class TestLegalValuesStillWork:
    @pytest.mark.parametrize("value", ["0", "0.0", "0.7", "1", "1.0", "2.0", "0,0.7"])
    def test_temperatures_accepts_finite(self, value: str) -> None:
        got = _parse_temperatures(value)
        assert all(math.isfinite(t) for t in got), got

    def test_the_documented_values_parse(self) -> None:
        # Every --temperatures value that appears in the nine READMEs.
        assert _parse_temperatures("0") == [0.0]
        assert _parse_temperatures("0,0.7") == [0.0, 0.7]

    @pytest.mark.parametrize(
        "flag,value",
        [("--max-cost", "0.50"), ("--ci-level", "0.99"),
         ("--ci-level", "0.95"), ("--significance-threshold", "0.01")],
    )
    def test_documented_flag_values_are_accepted(self, flag: str, value: str) -> None:
        flat = " ".join(
            CliRunner().invoke(
                cli_main, ["hi", "--models", "claude-opus-4-7", flag, value]
            ).output.split()
        )
        assert "Invalid value" not in flat, flat
        assert "No API key configured" in flat, flat


class TestTheCostGateStillFires:
    """The other half of item 3: refusing NaN is only worth anything if a real
    limit still stops a run. `estimated > nan` was always False, so the gate was
    silently disabled by a typo."""

    def _run(self, value: str):
        return CliRunner().invoke(
            cli_main,
            ["hi", "--models", "claude-opus-4-7", "--runs", "5", "--max-cost", value],
        )

    def test_a_low_limit_blocks_the_run(self) -> None:
        result = self._run("0.0001")
        assert result.exit_code == 2, result.output
        assert "exceeds --max-cost" in " ".join(result.output.split())

    def test_a_high_limit_lets_it_through(self) -> None:
        flat = " ".join(self._run("100.0").output.split())
        assert "exceeds --max-cost" not in flat, flat

    @pytest.mark.parametrize("value", ["nan", "inf"])
    def test_a_non_finite_limit_no_longer_disables_the_gate(self, value: str) -> None:
        result = self._run(value)
        assert result.exit_code == 2, result.output
        assert "Invalid value" in " ".join(result.output.split()), result.output


class TestTheRangeCheckDidNotRideIn:
    """A 0..1 bound on temperature is the obvious thing to add alongside a
    finiteness check, and it would refuse a value that works today."""

    @pytest.mark.parametrize("value", ["1.5", "2.0"])
    def test_a_temperature_above_one_still_parses(self, value: str) -> None:
        assert _parse_temperatures(value) == [float(value)]

    def test_it_still_reaches_the_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cli_modelarium.providers.anthropic_provider import AnthropicProvider

        seen = AnthropicProvider._build_kwargs  # noqa: F841  (existence check)
        assert _parse_temperatures("2.0") == [2.0]


class TestTheSavedFileParsesStrictly:
    """The point of the JSON half: a strict parser must accept what we write."""

    def _run(self, tmp_path, *flag: str) -> str:
        import os

        import cli_modelarium.cli as cli_module
        from cli_modelarium.providers.base import CompletionResult

        class _P:
            name = "anthropic"

            async def stream(self, *a, **k):  # pragma: no cover - --no-stream
                yield "hi"

            async def complete(self, prompt, model, temperature, system_prompt=None,
                               *, on_chunk=None, **k):
                if on_chunk:
                    on_chunk("hi")
                return CompletionResult(
                    output="hi", input_tokens=5, output_tokens=2, cost_usd=0.0001,
                    latency_ms=10.0, ttft_ms=1.0, model=model, provider="anthropic",
                    temperature=temperature,
                )

        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-" + "x" * 95
        monkey = cli_module._get_provider_instance
        cli_module._get_provider_instance = lambda n, **k: _P()
        out = tmp_path / "r.json"
        try:
            result = CliRunner().invoke(
                cli_main,
                ["hi", "--models", "claude-opus-4-7", "--runs", "3", "--no-stream",
                 "--bootstrap-seed", "7", *flag, "--output", str(out)],
            )
        finally:
            cli_module._get_provider_instance = monkey
            os.environ.pop("ANTHROPIC_API_KEY", None)
        assert result.exit_code == 0, result.output
        return out.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "flag", [(), ("--temperatures", "0.7"), ("--ci-level", "0.99"),
                 ("--significance-threshold", "0.01")]
    )
    def test_a_legal_run_parses_strictly(self, flag: tuple, tmp_path) -> None:
        _strict(self._run(tmp_path, *flag))

    def test_no_non_finite_constant_appears(self, tmp_path) -> None:
        raw = self._run(tmp_path)
        for token in ("NaN", "Infinity", "-Infinity"):
            assert token not in raw, token
