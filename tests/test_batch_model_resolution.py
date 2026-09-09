"""`batch --models <typo>` crashed where `compare` printed a panel.

    input                     compare   batch
    --models <typo>           exit 2    exit 1  TRACEBACK
    --models <RETIRED>        exit 2    exit 1  TRACEBACK

`--models` is the whole divergence. Every other malformed input - a bad
temperature, an unknown judge, a bogus output format or CI method, a malformed
or missing suite file - already exits 2 in both commands.

WHY IT DIVERGED. Both commands resolve models through `get_provider_for_model`,
but `compare` reaches it inside a block ending in `except ModelariumError`,
while batch's `build_batch_states` sat between that guard and the run - after
the size check and the cost ceiling, and inside no handler at all.

TWO EXCEPTIONS, NOT ONE. `RetiredModelError` is NOT a subclass of
`UnknownModelError`; they are siblings under `ConfigurationError`. Catching only
the one the traceback happened to show would have fixed the typo and left the
three retired ids still crashing.

WHY IT IS WRAPPED IN PLACE rather than moved into the earlier guard: the size
check (`--force-large`) and the cost ceiling (`--max-cost`) sit between them, so
hoisting state-building above those would allocate one `StreamState` per call
for a batch those gates were about to refuse.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.pricing import RETIRED_MODELS

RETIRED = sorted(RETIRED_MODELS)


@pytest.fixture
def suite(tmp_path) -> str:
    path = tmp_path / "suite.json"
    path.write_text('[{"id": "p1", "prompt": "hi"}]', encoding="utf-8")
    return str(path)


def _batch(suite: str, model: str):
    return CliRunner().invoke(cli_main, ["batch", suite, "--models", model])


def _compare(model: str):
    return CliRunner().invoke(cli_main, ["hi", "--models", model])


class TestAnUnknownModel:
    def test_batch_exits_2_with_a_panel(self, suite: str) -> None:
        result = _batch(suite, "vendor/nope")
        assert result.exit_code == 2, result.output
        assert "Traceback" not in result.output, result.output
        assert "Unknown model: vendor/nope" in " ".join(result.output.split())

    def test_both_commands_agree(self, suite: str) -> None:
        assert _batch(suite, "vendor/nope").exit_code == _compare("vendor/nope").exit_code


class TestARetiredModel:
    """The half a fix that caught only `UnknownModelError` would have missed."""

    @pytest.mark.parametrize("model", RETIRED)
    def test_batch_exits_2_with_a_panel(self, model: str, suite: str) -> None:
        result = _batch(suite, model)
        assert result.exit_code == 2, result.output
        assert "Traceback" not in result.output, result.output

    @pytest.mark.parametrize("model", RETIRED)
    def test_the_replacement_name_is_shown(self, model: str, suite: str) -> None:
        replacement = RETIRED_MODELS[model][0]
        flat = " ".join(_batch(suite, model).output.split())
        assert "was retired by its provider" in flat, flat
        assert replacement in flat, flat

    @pytest.mark.parametrize("model", RETIRED)
    def test_both_commands_agree(self, model: str, suite: str) -> None:
        assert _batch(suite, model).exit_code == _compare(model).exit_code

    def test_the_two_exceptions_are_siblings_not_parent_and_child(self) -> None:
        """If this ever becomes a subclass relationship, one entry in the guard
        would be enough and the second could be dropped. Today it is not."""
        from cli_modelarium.exceptions import RetiredModelError, UnknownModelError

        assert not issubclass(RetiredModelError, UnknownModelError)
        assert not issubclass(UnknownModelError, RetiredModelError)


class TestTheOtherInputsWereAlreadyFine:
    """Pinned so the enumeration is on the record: `--models` was the only
    divergence, and nothing here regressed."""

    @pytest.mark.parametrize(
        "flag,value",
        [
            ("--temperatures", "abc"),
            ("--judge", "bogus-judge"),
            ("--ci-method", "bogus"),
        ],
    )
    def test_both_commands_exit_2(self, flag: str, value: str, suite: str) -> None:
        b = CliRunner().invoke(
            cli_main, ["batch", suite, "--models", "claude-opus-4-7", flag, value]
        )
        c = CliRunner().invoke(cli_main, ["hi", "--models", "claude-opus-4-7", flag, value])
        assert b.exit_code == 2, b.output
        assert c.exit_code == 2, c.output

    def test_a_malformed_suite_is_still_clean(self, tmp_path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all", encoding="utf-8")
        result = CliRunner().invoke(cli_main, ["batch", str(bad), "--models", "claude-opus-4-7"])
        assert result.exit_code == 2, result.output
        assert "Traceback" not in result.output


class TestValidRunsAreUnaffected:
    def test_a_known_model_still_reaches_the_key_check(self, suite: str) -> None:
        flat = " ".join(_batch(suite, "claude-opus-4-7").output.split())
        assert "No API key configured" in flat, flat
