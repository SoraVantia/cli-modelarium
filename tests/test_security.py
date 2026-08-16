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
            ("openai", "sk-proj-abc123XYZ456DEF789ghi0jklmnop"),
            ("openai", "sk-abc123XYZ456DEF789ghi0jklmnop"),
            ("anthropic", "sk-ant-api03-abc123XYZ456DEF789ghi"),
            ("anthropic", "sk-ant-abc123XYZ456DEF789ghi"),
            ("xai", "xai-abc123XYZ456DEF789ghi"),
            ("groq", "gsk_abc123XYZ456DEF789ghi"),
            ("openrouter", "sk-or-abc123XYZ456DEF789ghi"),
            ("deepseek", "sk-abc123XYZ456DEF789ghi"),
            ("mistral", "abc123XYZ456DEF789ghi0"),
            ("dashscope", "sk-xxxxxxxxxxxxxxxxxxxx"),
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
        ],
    )
    def test_invalid_formats(self, provider: str, key: str) -> None:
        assert not security.validate_key(provider, key)

    def test_unknown_provider_returns_true(self) -> None:
        # Cannot validate what we don't have a pattern for; accept and let the
        # provider reject at API time.
        assert security.validate_key("brand-new-provider", "anything-goes-here-1234")


class TestRedactSecrets:
    @pytest.mark.parametrize(
        "secret",
        [
            "sk-proj-abc123XYZ456DEF789ghijklmnop",
            "sk-ant-api03-abc123XYZ456DEF789ghi",
            "sk-or-abc123XYZ456DEF789ghi",
            "xai-abc123XYZ456DEF789ghi",
            "gsk_abc123XYZ456DEF789ghi",
            "AIzaSyABC123def456GHI789jkl012MNO345pqr678",
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
        redacted = security.redact_secrets("x-api-key: sk-someValue1234567890")
        assert "someValue" not in redacted

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
        redacted = security.redact_secrets("sk-ant-api03-abc123XYZ456DEF789ghi")
        assert "sk-ant-***REDACTED***" in redacted

        redacted = security.redact_secrets("sk-or-abc123XYZ456DEF789ghi")
        assert "sk-or-***REDACTED***" in redacted

    def test_non_string_input(self) -> None:
        # Defensive: object that stringifies to something with a key.
        class Obj:
            def __str__(self) -> str:
                return "key=sk-proj-abc123XYZ456DEF789ghi"

        redacted = security.redact_secrets(Obj())  # type: ignore[arg-type]
        assert "abc123" not in redacted


class TestNvapiRedaction:
    """The `nvapi-` rule, added in 0.1.6.

    Before it existed only a fully echoed `Authorization: Bearer` header was
    caught. A bare token in a JSON error body survived and reached the `error`
    column of CSV and JSON output, which CI commonly uploads as an artifact.
    """

    NVAPI = "nvapi-abcdefghij1234567890ABCDEFGHIJ1234567890"

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
            ("sk-proj-abc123XYZ456DEF789ghi", "sk-proj-***REDACTED***"),
            ("sk-ant-api03-abc123XYZ456DEF789ghi", "sk-ant-***REDACTED***"),
            ("sk-or-abc123XYZ456DEF789ghi", "sk-or-***REDACTED***"),
            ("xai-abc123XYZ456DEF789ghi", "xai-***REDACTED***"),
            ("gsk_abc123XYZ456DEF789ghi", "gsk_***REDACTED***"),
            ("sk-abc123XYZ456DEF789ghi", "sk-***REDACTED***"),
            ("AIzaSyABC123def456GHI789jkl012MNO345pqr678", "AIza***REDACTED***"),
            ("nvapi-abc123XYZ456DEF789ghi", "nvapi-***REDACTED***"),
        ],
    )
    def test_prefix_rule_output_is_exact(self, secret: str, expected: str) -> None:
        assert security.redact_secrets(secret) == expected

    def test_header_and_query_rules_unchanged(self) -> None:
        assert (
            security.redact_secrets("Authorization: Bearer abc123XYZ456DEF789ghi")
            == "Authorization: Bearer ***REDACTED***"
        )
        assert security.redact_secrets("x-api-key: someValue1234567890") == (
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
            ("nvapi-abcdefghij1234567890abcd", True),
            ("nvapi-short", False),
            ("sk-proj-abcdefghij1234567890", False),
            ("abcdefghij1234567890abcdefgh", False),
        ],
    )
    def test_nvidia_key_format_validation(self, key: str, valid: bool) -> None:
        assert security.validate_key("nvidia", key) is valid


class TestKeyringIntegration:
    def test_save_and_load(self) -> None:
        security.save_key("openai", "sk-proj-test1234567890abcdefghi")
        assert security.load_key("openai") == "sk-proj-test1234567890abcdefghi"

    def test_save_strips_whitespace(self) -> None:
        security.save_key("openai", "  sk-proj-test1234567890abcdefghi  \n")
        assert security.load_key("openai") == "sk-proj-test1234567890abcdefghi"

    def test_save_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError):
            security.save_key("openai", "wrong-format-key")

    def test_load_returns_none_when_missing(self) -> None:
        assert security.load_key("openai") is None

    def test_delete_silent_when_missing(self) -> None:
        assert security.delete_key("openai") is False

    def test_delete_removes_existing(self) -> None:
        security.save_key("openai", "sk-proj-test1234567890abcdefghi")
        assert security.delete_key("openai") is True
        assert security.load_key("openai") is None

    def test_delete_local_url_returns_false_when_missing(self) -> None:
        assert security.delete_local_url() is False

    def test_delete_local_url_returns_true_when_existing(self) -> None:
        security.save_local_url("http://localhost:1234/v1")
        assert security.delete_local_url() is True
        assert security.load_local_url() is None

    def test_env_var_takes_precedence_over_keychain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        security.save_key("openai", "sk-proj-kerring1234567890abcdefghi")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-fromenv1234567890abcdefghi")
        assert security.load_key("openai") == "sk-proj-fromenv1234567890abcdefghi"

    def test_env_var_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fromenv1234567890abcdefghi")
        assert security.load_key("anthropic") == "sk-ant-fromenv1234567890abcdefghi"

    def test_env_var_is_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "  sk-proj-padded1234567890abcdefghi  ")
        assert security.load_key("openai") == "sk-proj-padded1234567890abcdefghi"

    def test_gemini_api_key_alias_for_google(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # GEMINI_API_KEY is accepted as a fallback for the google provider.
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaGemini1234567890abcdef1234567890")
        assert security.load_key("google") == "AIzaGemini1234567890abcdef1234567890"

    def test_google_api_key_takes_precedence_over_gemini(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "AIzaGoogle1234567890abcdef1234567890")
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaGemini1234567890abcdef1234567890")
        assert security.load_key("google") == "AIzaGoogle1234567890abcdef1234567890"

    def test_gemini_alias_does_not_leak_to_other_providers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The alias is google-only; GEMINI_API_KEY must not satisfy openai.
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaGemini1234567890abcdef1234567890")
        assert security.load_key("openai") is None

    def test_is_key_configured_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XAI_API_KEY", "xai-test1234567890abcdefghi")
        assert security.is_key_configured("xai")

    def test_is_key_configured_via_keychain(self) -> None:
        security.save_key("groq", "gsk_test1234567890abcdefghi")
        assert security.is_key_configured("groq")

    def test_is_key_configured_returns_false_when_missing(self) -> None:
        assert not security.is_key_configured("openrouter")
