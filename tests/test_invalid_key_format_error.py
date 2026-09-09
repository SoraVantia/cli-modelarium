"""`InvalidKeyFormatError` was declared and never raised.

It sat in `exceptions.py` with a docstring describing exactly what `save_key`
does, while `save_key` raised a bare `ValueError` instead - so the specific type
was dead and every caller had to catch the general one.

IT SUBCLASSES ValueError, AND THAT IS THE WHOLE DESIGN DECISION. Both call sites
catch `ValueError`:

    keys set   cli.py  -> except ValueError -> a clean panel
    configure  cli.py  -> except ValueError -> `invalid` counter, "Invalid format"

Raising a plain `ConfigurationError` there - which is what the class was, since
`ConfigurationError` does not inherit `ValueError` - would have made `keys set`
crash with a traceback and made `configure` fall through to its broad
`except Exception`, incrementing **not_stored** and printing *"Could not save"*.
A malformed key would have been reported as a storage failure, with `invalid: 0`.

Widening two handlers would work too; subclassing is one edit that cannot be
half-applied, and it keeps `save_key`'s documented `Raises: ValueError` contract
true for any caller relying on it.
"""

from __future__ import annotations

import pytest

from cli_modelarium.exceptions import (
    ConfigurationError,
    InvalidKeyFormatError,
    ModelariumError,
)
from cli_modelarium.security import KEY_PATTERNS, save_key


class TestItIsRaised:
    def test_a_malformed_key_raises_the_specific_type(self) -> None:
        with pytest.raises(InvalidKeyFormatError):
            save_key("anthropic", "obviously-not-a-key")

    def test_the_message_names_the_provider(self) -> None:
        with pytest.raises(InvalidKeyFormatError, match="anthropic"):
            save_key("anthropic", "nope")

    def test_the_key_itself_is_not_in_the_message(self) -> None:
        """The message is rendered to the user and redaction only helps if the
        wording never carried the secret in the first place."""
        secret = "S3CRET" * 10  # no recognised prefix, so validation rejects it
        with pytest.raises(InvalidKeyFormatError) as caught:
            save_key("anthropic", secret)
        assert "S3CRET" not in str(caught.value), str(caught.value)


class TestTheHierarchyKeepsBothCallersWorking:
    """If any of these stops holding, `configure` starts reporting a malformed
    key as a storage failure."""

    def test_it_is_a_value_error(self) -> None:
        assert issubclass(InvalidKeyFormatError, ValueError)

    def test_it_is_still_a_configuration_error(self) -> None:
        assert issubclass(InvalidKeyFormatError, ConfigurationError)
        assert issubclass(InvalidKeyFormatError, ModelariumError)

    def test_an_existing_value_error_handler_still_catches_it(self) -> None:
        try:
            save_key("anthropic", "nope")
        except ValueError:
            pass
        else:  # pragma: no cover
            pytest.fail("a ValueError handler no longer catches a bad key format")


class TestTheRejectedSetIsUnchanged:
    """Only the exception type changed. A provider whose real key format is a
    guess must not become newly locked out."""

    @pytest.mark.parametrize("provider", sorted(KEY_PATTERNS))
    def test_a_plausible_key_is_still_accepted(
        self, provider: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import keyring

        from cli_modelarium.security import validate_key

        stored: list[tuple] = []
        monkeypatch.setattr(keyring, "set_password", lambda *a: stored.append(a))
        # Build a key the provider's own pattern accepts, then confirm save_key
        # agrees - i.e. save_key rejects exactly what validate_key rejects.
        import re

        pattern = KEY_PATTERNS[provider]
        assert isinstance(pattern, re.Pattern)
        sample = {
            "anthropic": "sk-ant-api03-" + "a" * 95,
            "openai": "sk-proj-" + "a" * 40,
            "google": "AIza" + "a" * 35,
            "mistral": "a" * 32,
            "groq": "gsk_" + "a" * 52,
            "deepseek": "sk-" + "a" * 32,
            "xai": "xai-" + "a" * 80,
            "zai": "a" * 32 + ".a" * 8,
            "moonshot": "sk-" + "a" * 48,
            "dashscope": "sk-" + "a" * 32,
            "openrouter": "sk-or-v1-" + "a" * 64,
            "nvidia": "nvapi-" + "a" * 64,
        }.get(provider)
        if sample is None or not validate_key(provider, sample):
            pytest.skip(f"no known-good sample for {provider}")
        save_key(provider, sample)
        assert stored, f"{provider}: a valid key was not stored"

    @pytest.mark.parametrize("provider", sorted(KEY_PATTERNS))
    def test_an_obviously_bad_key_is_still_rejected(self, provider: str) -> None:
        with pytest.raises(InvalidKeyFormatError):
            save_key(provider, "!")


class TestLocalIsUnaffected:
    def test_local_has_no_key_pattern(self) -> None:
        assert "local" not in KEY_PATTERNS
