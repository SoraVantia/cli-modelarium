"""The first tests `configure` has ever had.

It shipped reporting success unconditionally - a green "Configuration
complete" panel and exit 0 whether eleven keys saved, ten were rejected, or
the machine had no keychain at all. Nothing in the suite touched the command,
which is why that survived.

Three conventions this file follows, each for a reason:

    Provider count is DERIVED from `all_known_providers()`, never written as
    11. The list comes from PRICING, so a twelfth provider would otherwise
    turn every piped-input test into an EOFError - failing as though the
    command regressed rather than as a stale fixture.

    Keys are placed BY PROVIDER NAME, never by index. Prompting is
    alphabetical (anthropic first, zai last); indexing by position bakes that
    order into every test.

    Border colour is asserted through SGR codes, which needs
    `force_terminal=True` on a Console with a pinned width. A plain
    `CliRunner(color=True)` emits no ANSI at all - the styling is decided by
    the Rich console the command writes to, not by Click.
"""

from __future__ import annotations

import io
import re

import keyring
import keyring.backend
import keyring.errors
import pytest
from click.testing import CliRunner
from rich.console import Console

from cli_modelarium import cli
from cli_modelarium.models_registry import all_known_providers
from tests.conftest import flatten_rendered

PROVIDERS = [p for p in all_known_providers() if p != "local"]

# Shape-valid keys, one per provider, so a test can configure any subset.
VALID_KEYS = {
    "anthropic": "sk-ant-api03-abcdefghij1234567890",
    "dashscope": "sk-abcdefghij1234567890",
    "deepseek": "sk-abcdefghij1234567890",
    "google": "AIzaSyD-1a2B3c4D5e6F7g8H9i0JkLmNoPqRsTu",
    "groq": "gsk_abcdefghij1234567890",
    "mistral": "abcdefghij1234567890abcd",
    "nvidia": "nvapi-abcdefghij1234567890abcd",
    "openai": "sk-proj-abcdefghij1234567890",
    "openrouter": "sk-or-abcdefghij1234567890",
    "xai": "xai-abcdefghij1234567890",
    "zai": "abcdefghij1234567890abcd",
}

# A key no provider's pattern accepts, for the "invalid format" path.
BAD_KEY = "nope"


def _input_for(answers: dict[str, str]) -> str:
    """Piped stdin for one full pass, padded to every prompt.

    Short input is not a neutral shortcut: the loop would hit EOFError and
    take the interrupt path, so a test meaning to check a summary would
    silently be checking cancellation instead.
    """
    return "\n".join(answers.get(p, "") for p in PROVIDERS) + "\n"


class RecordingKeyring(keyring.backend.KeyringBackend):
    """An in-memory backend that can be told to fail, and counts its calls.

    `conftest.InMemoryKeyring` always succeeds, so it cannot reach any of the
    failure branches. The call count is what proves the loop stopped rather
    than merely that the summary said it did.
    """

    priority = 1

    def __init__(self, error: Exception | None = None, fail_on: str | None = None) -> None:
        self._store: dict[tuple[str, str], str] = {}
        self.error = error
        self.fail_on = fail_on
        self.set_calls: list[str] = []

    def set_password(self, servicename: str, username: str, password: str) -> None:
        self.set_calls.append(username)
        if self.error is not None and (self.fail_on is None or self.fail_on == username):
            raise self.error
        self._store[(servicename, username)] = password

    def get_password(self, servicename: str, username: str) -> str | None:
        return self._store.get((servicename, username))

    def delete_password(self, servicename: str, username: str) -> None:
        raise keyring.errors.PasswordDeleteError("not found")


def _run(answers: dict[str, str], backend: keyring.backend.KeyringBackend | None = None):
    """Invoke `configure` against a chosen backend and return (result, backend)."""
    backend = backend or RecordingKeyring()
    keyring.set_keyring(backend)
    result = CliRunner().invoke(cli.main, ["configure"], input=_input_for(answers))
    return result, backend


class TestOutcomes:
    """Exit code and panel title for each way a run can end."""

    def test_all_skipped_is_not_an_error(self) -> None:
        # Someone running `configure` to read the prompts has done nothing
        # wrong. Guarding on `configured == 0` instead of `attempted > 0 and
        # configured == 0` would fail exactly this run.
        result, backend = _run({})
        assert result.exit_code == 0
        assert "No changes" in result.output
        assert backend.set_calls == []

    def test_some_configured_rest_skipped(self) -> None:
        result, backend = _run({p: VALID_KEYS[p] for p in ("anthropic", "openai", "groq")})
        assert result.exit_code == 0
        assert "Configuration complete" in result.output
        assert sorted(backend.set_calls) == ["anthropic", "groq", "openai"]

    def test_one_configured_one_invalid(self) -> None:
        result, _ = _run({"anthropic": VALID_KEYS["anthropic"], "openai": BAD_KEY})
        assert result.exit_code == 0
        assert "Configured with errors" in result.output

    def test_all_attempted_all_invalid_exits_two(self) -> None:
        result, _ = _run({p: BAD_KEY for p in PROVIDERS})
        assert result.exit_code == 2
        assert "Configuration failed" in result.output

    def test_partial_success_is_not_a_failure(self) -> None:
        # Configuring the two providers you own is complete success, not a
        # shortfall over the nine you do not.
        result, _ = _run({p: VALID_KEYS[p] for p in ("anthropic", "openai")})
        assert result.exit_code == 0

    def test_every_provider_configured(self) -> None:
        result, backend = _run(dict(VALID_KEYS))
        assert result.exit_code == 0
        assert "Configuration complete" in result.output
        assert sorted(backend.set_calls) == sorted(PROVIDERS)
        # Nothing was skipped, so the panel must not offer to add a skipped
        # provider - a line asserting what the counters deny is the defect
        # this whole command was rewritten to stop producing.
        assert "skipped" not in result.output


def _counters_from(output: str, total: int) -> dict[str, int]:
    """Recover the five counters from a rendered panel.

    Parsed back out of the user-visible text rather than read from the
    function's internals, so the invariant is asserted against what was
    actually shown.
    """
    flat = " ".join(flatten_rendered(output).split())
    found = {}
    for label in ("configured", "invalid", "not stored", "skipped", "not reached"):
        match = re.search(rf"(\d+) {label}\b", flat)
        found[label] = int(match.group(1)) if match else 0
    # "all N providers skipped" is the wording when nothing else happened.
    if not any(found.values()) and f"all {total} providers skipped" in flat:
        found["skipped"] = total
    return found


class TestCountsAreDistinguishable:
    """The defect that made the old summary useless."""

    def test_skipped_and_invalid_read_differently(self) -> None:
        # `saved` alone rendered these two runs byte-identically as
        # "1 of 11 providers configured." Every other assertion in this file
        # would pass with that regression reinstated; this one would not.
        skipped_run, _ = _run({"anthropic": VALID_KEYS["anthropic"]})
        invalid_run, _ = _run(
            {"anthropic": VALID_KEYS["anthropic"], **{p: BAD_KEY for p in PROVIDERS[1:]}}
        )
        assert skipped_run.output != invalid_run.output
        assert "invalid" in invalid_run.output
        assert "invalid" not in skipped_run.output

    def test_the_summary_names_each_category(self) -> None:
        result, _ = _run({"anthropic": VALID_KEYS["anthropic"], "openai": BAD_KEY})
        assert "1 configured" in result.output
        assert "1 invalid" in result.output
        assert "9 skipped" in result.output


class TestMissingBackend:
    """No keychain: stop asking for credentials that cannot be stored."""

    def test_stops_on_the_first_provider(self) -> None:
        backend = RecordingKeyring(error=keyring.errors.NoKeyringError("no backend"))
        result, backend = _run({p: VALID_KEYS[p] for p in PROVIDERS}, backend)
        assert backend.set_calls == ["anthropic"], "must not prompt the remaining providers"
        assert result.exit_code == 2
        assert "no OS keychain" in result.output
        assert result.output.count("no backend") == 1, "the reason belongs on screen once"

    def test_reports_what_was_not_reached(self) -> None:
        backend = RecordingKeyring(
            error=keyring.errors.NoKeyringError("no backend"), fail_on=PROVIDERS[5]
        )
        result, backend = _run({p: VALID_KEYS[p] for p in PROVIDERS}, backend)
        assert len(backend.set_calls) == 6
        assert "5 configured" in result.output
        assert f"{len(PROVIDERS) - 6} not reached" in result.output

    def test_earlier_saves_are_not_reported_as_total_failure(self) -> None:
        backend = RecordingKeyring(
            error=keyring.errors.NoKeyringError("no backend"), fail_on=PROVIDERS[5]
        )
        result, _ = _run({p: VALID_KEYS[p] for p in PROVIDERS}, backend)
        assert "Configured with errors" in result.output
        assert result.exit_code == 0

    def test_failing_on_the_last_provider_reaches_everything(self) -> None:
        # The break arithmetic is `len(providers) - index - 1`, which is zero
        # on the final provider. Reachable, and the only state where a break
        # leaves nothing unreached - so the summary must not mention any.
        backend = RecordingKeyring(
            error=keyring.errors.NoKeyringError("no backend"), fail_on=PROVIDERS[-1]
        )
        result, backend = _run({p: VALID_KEYS[p] for p in PROVIDERS}, backend)
        assert backend.set_calls == PROVIDERS
        assert "not reached" not in result.output
        assert f"{len(PROVIDERS) - 1} configured" in result.output


class TestRecoverableKeyringErrors:
    """Everything that is NOT NoKeyringError must keep going.

    `PasswordSetError` is what KWallet raises when a user dismisses one OS
    auth dialog. Breaking the loop there would abandon ten providers because
    somebody pressed Escape once.
    """

    @pytest.mark.parametrize(
        "error",
        [
            keyring.errors.KeyringLocked("locked"),
            keyring.errors.PasswordSetError("Cancelled by user"),
            keyring.errors.InitError("collection failed"),
            RuntimeError("a bare pywintypes.error stands in for Windows"),
        ],
        ids=["locked", "cancelled", "init", "non-keyring"],
    )
    def test_one_failure_does_not_abandon_the_run(self, error: Exception) -> None:
        backend = RecordingKeyring(error=error, fail_on="anthropic")
        result, backend = _run({p: VALID_KEYS[p] for p in PROVIDERS}, backend)
        assert backend.set_calls == PROVIDERS, "every provider must still be offered"
        assert "not reached" not in result.output
        assert "1 not stored" in result.output
        assert result.exit_code == 0

    def test_a_storage_failure_is_not_called_invalid(self) -> None:
        # A user with a locked keychain told their key was "invalid" goes and
        # checks the key, which is the wrong place to look.
        backend = RecordingKeyring(error=keyring.errors.KeyringLocked("locked"))
        result, _ = _run({p: VALID_KEYS[p] for p in PROVIDERS}, backend)
        assert "not stored" in result.output
        assert "invalid" not in result.output


class TestInterrupt:
    """Ctrl-C used to print nothing about what had already been stored."""

    def test_summary_is_printed_and_exit_is_two(self) -> None:
        keyring.set_keyring(RecordingKeyring())
        short = "\n".join(VALID_KEYS[p] for p in PROVIDERS[:3]) + "\n"
        result = CliRunner().invoke(cli.main, ["configure"], input=short)
        assert result.exit_code == 2
        assert "Setup cancelled" in result.output
        assert "3 configured" in result.output
        assert f"{len(PROVIDERS) - 3} not reached" in result.output

    def test_it_does_not_claim_completion(self) -> None:
        keyring.set_keyring(RecordingKeyring())
        result = CliRunner().invoke(cli.main, ["configure"], input="\n")
        assert "Configuration complete" not in result.output


class TestPanelColour:
    """The border style, which no text assertion can see."""

    @staticmethod
    def _styled_output(answers: dict[str, str], backend=None) -> str:
        keyring.set_keyring(backend or RecordingKeyring())
        buf = io.StringIO()
        original = cli.console
        # force_terminal=True is what makes Rich emit SGR codes at all; the
        # pinned width satisfies test_rendered_output_convention.
        cli.console = Console(
            file=buf, width=200, force_terminal=True, color_system="truecolor"
        )
        try:
            CliRunner().invoke(cli.main, ["configure"], input=_input_for(answers))
        finally:
            cli.console = original
        return buf.getvalue()

    def test_success_is_green(self) -> None:
        out = self._styled_output({"anthropic": VALID_KEYS["anthropic"]})
        assert "\x1b[32m" in out

    def test_partial_failure_is_yellow(self) -> None:
        out = self._styled_output(
            {"anthropic": VALID_KEYS["anthropic"], "openai": BAD_KEY}
        )
        assert "\x1b[33m" in out

    def test_total_failure_is_red(self) -> None:
        out = self._styled_output({p: BAD_KEY for p in PROVIDERS})
        assert "\x1b[31m" in out


class TestPartitionInvariant:
    """Every provider lands in exactly one bucket, in every reachable state.

    configured + skipped + invalid + not_stored + not_reached == len(providers)

    One assertion covering a whole class of bookkeeping error: a counter
    incremented in the wrong arm, a `continue` that skips a tally, or break
    arithmetic off by one all show up here as a sum that misses the total.
    """

    NO_BACKEND = keyring.errors.NoKeyringError("no backend")

    @pytest.mark.parametrize(
        "label, answers, backend",
        [
            ("all skipped", {}, None),
            ("every provider configured", dict(VALID_KEYS), None),
            (
                "some configured, rest skipped",
                {p: VALID_KEYS[p] for p in ("anthropic", "openai", "groq")},
                None,
            ),
            (
                "one configured, one invalid",
                {"anthropic": VALID_KEYS["anthropic"], "openai": BAD_KEY},
                None,
            ),
            ("all attempted, all invalid", {p: BAD_KEY for p in PROVIDERS}, None),
            (
                "locked on one provider",
                dict(VALID_KEYS),
                lambda: RecordingKeyring(
                    error=keyring.errors.KeyringLocked("locked"), fail_on="google"
                ),
            ),
            (
                "dialog dismissed on one provider",
                dict(VALID_KEYS),
                lambda: RecordingKeyring(
                    error=keyring.errors.PasswordSetError("Cancelled by user"),
                    fail_on="google",
                ),
            ),
            (
                "no backend, first provider",
                dict(VALID_KEYS),
                lambda: RecordingKeyring(error=TestPartitionInvariant.NO_BACKEND),
            ),
            (
                "no backend, provider six",
                dict(VALID_KEYS),
                lambda: RecordingKeyring(
                    error=TestPartitionInvariant.NO_BACKEND, fail_on=PROVIDERS[5]
                ),
            ),
            (
                "no backend, last provider",
                dict(VALID_KEYS),
                lambda: RecordingKeyring(
                    error=TestPartitionInvariant.NO_BACKEND, fail_on=PROVIDERS[-1]
                ),
            ),
        ],
    )
    def test_counters_partition_the_providers(self, label, answers, backend) -> None:
        result, _ = _run(answers, backend() if backend else None)
        counters = _counters_from(result.output, len(PROVIDERS))
        assert sum(counters.values()) == len(PROVIDERS), f"{label}: {counters}"

    @pytest.mark.parametrize("saves", [0, 3])
    def test_the_invariant_holds_on_the_interrupt_path(self, saves: int) -> None:
        # Ctrl-C during a prompt means that provider was neither attempted nor
        # skipped, so it belongs to not_reached along with the ones behind it.
        keyring.set_keyring(RecordingKeyring())
        short = "\n".join(VALID_KEYS[p] for p in PROVIDERS[:saves]) + "\n"
        result = CliRunner().invoke(cli.main, ["configure"], input=short)
        counters = _counters_from(result.output, len(PROVIDERS))
        assert sum(counters.values()) == len(PROVIDERS), counters


class TestRedaction:
    """cli.py's ValueError arm printed whatever the exception carried."""

    def test_the_invalid_format_line_is_redacted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        canary = "sk-ant-api03-CANARYabcdefghij1234567890"

        def fake_save(provider: str, key: str) -> None:
            raise ValueError(f"Invalid API key format for {provider}: {canary}")

        monkeypatch.setattr(cli, "save_key", fake_save)
        result, _ = _run({"anthropic": VALID_KEYS["anthropic"]})
        assert canary not in result.output
        assert "REDACTED" in result.output
