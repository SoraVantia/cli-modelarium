"""Tests for cli_modelarium.security."""

from __future__ import annotations

import pytest

from cli_modelarium import security


class TestNormalizeKey:
    def test_strips_whitespace(self) -> None:
        assert security.normalize_key("  sk-test123  ") == "sk-test123"

    def test_strips_double_quotes(self) -> None:
        assert security.normalize_key('"sk-test123"') == "sk-test123"

    def test_strips_single_quotes(self) -> None:
        assert security.normalize_key("'sk-test123'") == "sk-test123"

    def test_strips_whitespace_then_quotes(self) -> None:
        assert security.normalize_key('  "sk-test123"\n') == "sk-test123"


class TestValidateKey:
    @pytest.mark.parametrize(
        "provider, key",
        [
            ("openai", "sk-proj-NOT_A_REAL_KEY_test_fixture_00"),
            ("openai", "sk-NOT_A_REAL_KEY_test_fixture_0000"),
            ("anthropic", "sk-ant-api03-NOT_A_REAL_KEY_test_fixture"),
            ("anthropic", "sk-ant-NOT_A_REAL_KEY_test_fixture_0"),
            ("xai", "xai-NOT_A_REAL_KEY_test_fixture_00"),
            ("groq", "gsk_NOT_A_REAL_KEY_test_fixture_00"),
            ("openrouter", "sk-or-NOT_A_REAL_KEY_test_fixture_0"),
            ("deepseek", "sk-NOT_A_REAL_KEY_test_fixture_0000"),
            ("mistral", "NOTAREALKEYtestfixture00"),
            ("dashscope", "sk-xxxxxxxxxxxxxxxxxxxx"),
            # Google issues two shapes and both must pass. The Auth fixture
            # carries a hyphen as well as the dot: the hyphen was already in the
            # class and is not what the widening turned on, but it is what a
            # future rewrite to an `AIza|AQ\.Ab` alternation would break on.
            ("google", "AIzaSyNOT_A_REAL_KEY-test_fixture_000000"),
            ("google", "AQ.AbSyntheticTestKey-not_a_real_credential01"),
        ],
    )
    def test_valid_formats(self, provider: str, key: str) -> None:
        assert security.validate_key(provider, key)

    @pytest.mark.parametrize(
        "provider, key",
        [
            ("openai", "wrong-prefix-1234567890abc"),
            ("openai", "sk-tiny"),
            ("anthropic", "sk-not-ant-1234567890abc"),
            ("xai", "no-prefix-1234567890abc"),
            ("groq", "gsk-not-underscore-1234567890abc"),
            ("openrouter", "sk-not-or-1234567890abc"),
            # Google's is a shape floor, not a prefix rule, so the things that
            # must still fail are length and out-of-class characters.
            ("google", "a" * 29),
            ("google", "AQ.Ab has a space in the middle of it 012345"),
            ("google", "AQ.Ab+slash/and+plus+are+not+base64url+chars0"),
        ],
    )
    def test_invalid_formats(self, provider: str, key: str) -> None:
        assert not security.validate_key(provider, key)

    def test_unknown_provider_returns_true(self) -> None:
        # Cannot validate what we don't have a pattern for; accept and let the
        # provider reject at API time.
        assert security.validate_key("brand-new-provider", "anything-goes-here-1234")


class TestGoogleKeyFormat:
    """Both Gemini key shapes, and the floor that is the only real constraint.

    This pattern had no coverage in either direction before the `AQ.` widening,
    which is how it came to reject every key Google now issues without a test
    noticing. `AIza` keys keep working until Google stops accepting them in
    September 2026, so the point of these is that BOTH shapes pass, not that
    the new one does.
    """

    AIZA = "AIzaSyNOT_A_REAL_KEY-test_fixture_000000"
    AUTH = "AQ.AbSyntheticTestKey-not_a_real_credential01"

    def test_both_shapes_are_accepted(self) -> None:
        assert security.validate_key("google", self.AIZA)
        assert security.validate_key("google", self.AUTH)

    def test_the_auth_fixture_carries_a_dot_and_a_hyphen(self) -> None:
        # The dot is the character the widening turns on; the hyphen was always
        # in the class. The fixture carries both anyway, because a rewrite to an
        # `AIza|AQ\.Ab` alternation would admit the dot and could still stop at
        # the hyphen, and nothing else here would catch that.
        assert "." in self.AUTH and "-" in self.AUTH

    def test_length_floor_is_thirty(self) -> None:
        assert not security.validate_key("google", "a" * 29)
        assert security.validate_key("google", "a" * 30)

    def test_widening_did_not_relax_the_character_class(self) -> None:
        # Only `.` was added. Anything outside base64url-plus-dot still fails,
        # so the slot did not become "accept any string of length 30".
        for bad in ("+", "/", "=", " ", "$", "\t"):
            assert not security.validate_key("google", "a" * 20 + bad + "a" * 20), bad

    def test_class_matches_zai_with_a_stricter_floor(self) -> None:
        # The widened class is one already shipped for `zai`; only the floor
        # differs. Pinned so a future edit to either notices it is copying the
        # other rather than inventing a shape.
        def accepted_chars(provider: str) -> set[str]:
            pattern = security.KEY_PATTERNS[provider]
            return {
                chr(c) for c in range(32, 127) if pattern.match("a" * 20 + chr(c) + "a" * 20)
            }

        assert accepted_chars("google") == accepted_chars("zai")
        assert not security.validate_key("google", "a" * 29)
        assert security.validate_key("zai", "a" * 29)


class TestRedactSecrets:
    @pytest.mark.parametrize(
        "secret",
        [
            "sk-proj-NOT_A_REAL_KEY_test_fixture_00",
            "sk-ant-api03-NOT_A_REAL_KEY_test_fixture",
            "sk-or-NOT_A_REAL_KEY_test_fixture_0",
            "xai-NOT_A_REAL_KEY_test_fixture_00",
            "gsk_NOT_A_REAL_KEY_test_fixture_00",
            "AIzaSyNOT_A_REAL_KEY_test_fixture_0000000",
        ],
    )
    def test_each_provider_key_redacted(self, secret: str) -> None:
        message = f"Request failed with key {secret} in body"
        redacted = security.redact_secrets(message)
        assert secret not in redacted
        assert "REDACTED" in redacted

    def test_authorization_header(self) -> None:
        redacted = security.redact_secrets("Authorization: Bearer abc123XYZ456DEF789ghi")
        assert "abc123" not in redacted
        assert "REDACTED" in redacted

    def test_x_api_key_header(self) -> None:
        redacted = security.redact_secrets("x-api-key: sk-NOT_A_REAL_KEY_header_00000")
        assert "NOT_A_REAL" not in redacted

    def test_api_key_in_query_string(self) -> None:
        redacted = security.redact_secrets(
            "GET https://api.example.com/v1?api_key=abc123XYZ&other=val"
        )
        assert "abc123XYZ" not in redacted
        assert "REDACTED" in redacted

    def test_multiple_secrets_in_one_string(self) -> None:
        message = "Error: sk-proj-aaaaaaaaaaaaaaaaaaaa and sk-ant-bbbbbbbbbbbbbbbbbbbb both failed"
        redacted = security.redact_secrets(message)
        assert "aaaa" not in redacted
        assert "bbbb" not in redacted

    def test_no_secret_passes_through_unchanged(self) -> None:
        assert security.redact_secrets("Hello world") == "Hello world"

    def test_specific_prefixes_not_swallowed_by_generic_sk(self) -> None:
        # sk-ant-* should land on the anthropic placeholder, not the generic one.
        redacted = security.redact_secrets("sk-ant-api03-NOT_A_REAL_KEY_test_fixture")
        assert "sk-ant-***REDACTED***" in redacted

        redacted = security.redact_secrets("sk-or-NOT_A_REAL_KEY_test_fixture_0")
        assert "sk-or-***REDACTED***" in redacted

    def test_non_string_input(self) -> None:
        # Defensive: object that stringifies to something with a key.
        class Obj:
            def __str__(self) -> str:
                return "key=sk-proj-NOT_A_REAL_KEY_test_fixture_00"

        redacted = security.redact_secrets(Obj())  # type: ignore[arg-type]
        assert "abc123" not in redacted


class TestNvapiRedaction:
    """The `nvapi-` rule, added in 0.1.6.

    Before it existed only a fully echoed `Authorization: Bearer` header was
    caught. A bare token in a JSON error body survived and reached the `error`
    column of CSV and JSON output, which CI commonly uploads as an artifact.
    """

    NVAPI = "nvapi-NOT_A_REAL_KEY_test_fixture_00000000"

    def test_bare_token_in_json_body(self) -> None:
        redacted = security.redact_secrets(f'{{"error":"invalid key {self.NVAPI}"}}')
        assert self.NVAPI not in redacted
        assert "nvapi-***REDACTED***" in redacted

    def test_token_in_url_query_string(self) -> None:
        redacted = security.redact_secrets(f"https://integrate.api.nvidia.com/v1?k={self.NVAPI}")
        assert self.NVAPI not in redacted
        assert "nvapi-***REDACTED***" in redacted

    def test_authorization_header_form_still_caught(self) -> None:
        redacted = security.redact_secrets(f"Authorization: Bearer {self.NVAPI}")
        assert self.NVAPI not in redacted

    @pytest.mark.parametrize(
        "benign",
        [
            "the nvapi-style endpoint is documented",
            "nvapi-abc",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "meta/llama-3.1-8b-instruct",
        ],
    )
    def test_does_not_over_match(self, benign: str) -> None:
        assert security.redact_secrets(benign) == benign


class TestRedactionRegressionPins:
    """Byte-identical pins for every pre-existing rule.

    A future pattern addition placed above one of these could silently swallow
    it into the wrong placeholder. These assert the exact output, not just that
    something was redacted.
    """

    @pytest.mark.parametrize(
        "secret,expected",
        [
            ("sk-proj-NOT_A_REAL_KEY_test_fixture_00", "sk-proj-***REDACTED***"),
            ("sk-ant-api03-NOT_A_REAL_KEY_test_fixture", "sk-ant-***REDACTED***"),
            ("sk-or-NOT_A_REAL_KEY_test_fixture_0", "sk-or-***REDACTED***"),
            ("xai-NOT_A_REAL_KEY_test_fixture_00", "xai-***REDACTED***"),
            ("gsk_NOT_A_REAL_KEY_test_fixture_00", "gsk_***REDACTED***"),
            ("sk-NOT_A_REAL_KEY_test_fixture_0000", "sk-***REDACTED***"),
            ("AIzaSyNOT_A_REAL_KEY_test_fixture_0000000", "AIza***REDACTED***"),
            ("nvapi-NOT_A_REAL_KEY_test_fixture_0", "nvapi-***REDACTED***"),
        ],
    )
    def test_prefix_rule_output_is_exact(self, secret: str, expected: str) -> None:
        assert security.redact_secrets(secret) == expected

    def test_header_and_query_rules_unchanged(self) -> None:
        assert (
            security.redact_secrets("Authorization: Bearer abc123XYZ456DEF789ghi")
            == "Authorization: Bearer ***REDACTED***"
        )
        assert security.redact_secrets("x-api-key: NOT_A_REAL_KEY_header_0") == (
            "x-api-key: ***REDACTED***"
        )
        assert security.redact_secrets("api_key=abc123XYZdef") == "api_key=***REDACTED***"


class TestKeyPatternsCoverage:
    """Every provider `configure` prompts for must have a KEY_PATTERNS entry.

    `configure` iterates `all_known_providers()` (derived from PRICING) with no
    membership gate, and `validate_key` returns True when no pattern exists -
    but `keys set` and `keys delete` both gate on KEY_PATTERNS membership. A
    provider present in PRICING and absent from KEY_PATTERNS would therefore let
    `configure` write a credential that `keys delete` then refuses to remove.

    Deliberately a subset, not an equality: a provider may be wired in
    PROVIDER_REGISTRY and KEY_PATTERNS before any model is registered. `nvidia`
    was in that state when the provider landed and left it when its rows did.
    """

    def test_every_priced_provider_has_a_key_pattern(self) -> None:
        from cli_modelarium.models_registry import all_known_providers

        needs_key = set(all_known_providers()) - {"local"}
        missing = needs_key - set(security.KEY_PATTERNS)
        assert missing == set(), f"providers in PRICING with no KEY_PATTERNS entry: {missing}"

    def test_nvidia_has_a_pattern_and_is_now_registered(self) -> None:
        from cli_modelarium.models_registry import all_known_providers

        assert "nvidia" in security.KEY_PATTERNS
        assert "nvidia" in all_known_providers()

    @pytest.mark.parametrize(
        "key,valid",
        [
            ("nvapi-NOT_A_REAL_KEY_test_fixture_1", True),
            ("nvapi-short", False),
            ("sk-proj-NOT_A_REAL_KEY_test_fixture_00", False),
            ("abcdefghij1234567890abcdefgh", False),
        ],
    )
    def test_nvidia_key_format_validation(self, key: str, valid: bool) -> None:
        assert security.validate_key("nvidia", key) is valid


class TestKeyringIntegration:
    def test_save_and_load(self) -> None:
        security.save_key("openai", "sk-proj-NOT_A_REAL_KEY_test_fixture_00")
        assert security.load_key("openai") == "sk-proj-NOT_A_REAL_KEY_test_fixture_00"

    def test_save_strips_whitespace(self) -> None:
        security.save_key("openai", "  sk-proj-NOT_A_REAL_KEY_test_fixture_00  \n")
        assert security.load_key("openai") == "sk-proj-NOT_A_REAL_KEY_test_fixture_00"

    def test_save_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError):
            security.save_key("openai", "wrong-format-key")

    def test_load_returns_none_when_missing(self) -> None:
        assert security.load_key("openai") is None

    def test_delete_silent_when_missing(self) -> None:
        assert security.delete_key("openai") is False

    def test_delete_removes_existing(self) -> None:
        security.save_key("openai", "sk-proj-NOT_A_REAL_KEY_test_fixture_00")
        assert security.delete_key("openai") is True
        assert security.load_key("openai") is None

    def test_delete_local_url_returns_false_when_missing(self) -> None:
        assert security.delete_local_url() is False

    def test_delete_local_url_returns_true_when_existing(self) -> None:
        security.save_local_url("http://localhost:1234/v1")
        assert security.delete_local_url() is True
        assert security.load_local_url() is None

    def test_env_var_takes_precedence_over_keychain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        security.save_key("openai", "sk-proj-NOT_A_REAL_KEY_from_keyring_0")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_from_env_0000")
        assert security.load_key("openai") == "sk-proj-NOT_A_REAL_KEY_from_env_0000"

    def test_env_var_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-NOT_A_REAL_KEY_from_env_0000")
        assert security.load_key("anthropic") == "sk-ant-NOT_A_REAL_KEY_from_env_0000"

    def test_env_var_is_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "  sk-proj-NOT_A_REAL_KEY_padded_00000  ")
        assert security.load_key("openai") == "sk-proj-NOT_A_REAL_KEY_padded_00000"

    def test_gemini_api_key_alias_for_google(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # GEMINI_API_KEY is accepted as a fallback for the google provider.
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaGemini_NOT_A_REAL_KEY_test_fixture_0")
        assert security.load_key("google") == "AIzaGemini_NOT_A_REAL_KEY_test_fixture_0"

    def test_google_api_key_takes_precedence_over_gemini(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "AIzaGoogle_NOT_A_REAL_KEY_test_fixture_0")
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaGemini_NOT_A_REAL_KEY_test_fixture_0")
        assert security.load_key("google") == "AIzaGoogle_NOT_A_REAL_KEY_test_fixture_0"

    def test_gemini_alias_does_not_leak_to_other_providers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The alias is google-only; GEMINI_API_KEY must not satisfy openai.
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaGemini_NOT_A_REAL_KEY_test_fixture_0")
        assert security.load_key("openai") is None

    def test_is_key_configured_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XAI_API_KEY", "xai-NOT_A_REAL_KEY_test_fixture_00")
        assert security.is_key_configured("xai")

    def test_is_key_configured_via_keychain(self) -> None:
        security.save_key("groq", "gsk_NOT_A_REAL_KEY_test_fixture_00")
        assert security.is_key_configured("groq")

    def test_is_key_configured_returns_false_when_missing(self) -> None:
        assert not security.is_key_configured("openrouter")
