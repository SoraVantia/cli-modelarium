"""Tests for cli_modelarium.pricing."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.exceptions import (
    ModelariumError,
    RetiredModelError,
    UnknownModelError,
)
from cli_modelarium.models_registry import get_provider_for_model
from cli_modelarium.pricing import (
    PRICING,
    PRICING_AS_OF,
    RETIRED_MODELS,
    calculate_cost,
    is_local_model,
    pricing_freshness_note,
)


class TestPricingAsOf:
    def test_constant_format(self) -> None:
        assert PRICING_AS_OF == "2026-07-29"

    def test_freshness_note_includes_date(self) -> None:
        assert PRICING_AS_OF in pricing_freshness_note()


class TestIsLocalModel:
    def test_local_prefix(self) -> None:
        assert is_local_model("local/llama-3.3-70b")

    def test_no_prefix(self) -> None:
        assert not is_local_model("gpt-5.5")

    def test_local_anywhere_else(self) -> None:
        assert not is_local_model("not-local/anything")


class TestPricingLookup:
    """The pricing-lookup contract, asserted against PRICING directly.

    These covered get_pricing() until it was removed in 0.1.5; the contract they
    pin belongs to the registry, not to that wrapper, so they survive it.
    """

    def test_known_cloud_model(self) -> None:
        entry = PRICING.get("claude-opus-4-7")
        assert entry is not None
        assert entry["provider"] == "anthropic"

    def test_local_resolves_to_wildcard(self) -> None:
        # get_pricing() used to map any `local/...` name onto this entry. Nothing
        # does that mapping now, so assert the two halves that remain: the
        # wildcard entry exists and is flagged local, and an arbitrary local name
        # is still recognised as local. A bare PRICING.get("local/anything") is
        # None by design - the prefix, not the registry, is what routes it.
        entry = PRICING["local/*"]
        assert entry is not None
        assert entry.get("is_local") is True
        assert is_local_model("local/anything-goes")
        assert PRICING.get("local/anything-goes") is None

    def test_unknown_returns_none(self) -> None:
        assert PRICING.get("nonexistent-model-xyz") is None


class TestCalculateCost:
    def test_input_only(self) -> None:
        # claude-opus-4-7: $5.00 input / $25.00 output per 1M tokens
        cost = calculate_cost("claude-opus-4-7", input_tokens=1_000_000, output_tokens=0)
        assert cost == pytest.approx(5.00)

    def test_output_only(self) -> None:
        cost = calculate_cost("claude-opus-4-7", input_tokens=0, output_tokens=1_000_000)
        assert cost == pytest.approx(25.00)

    def test_input_plus_output(self) -> None:
        # Sonnet 4.6: $3.00 input / $15.00 output
        cost = calculate_cost("claude-sonnet-4-6", input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == pytest.approx(18.00)

    def test_haiku_4_5_user_specified_pricing(self) -> None:
        # User-corrected: $1.00 / $5.00 per 1M.
        cost = calculate_cost("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == pytest.approx(6.00)

    def test_cached_tokens_apply_cached_rate(self) -> None:
        # claude-opus-4-7 cached_input = $0.50/M.
        cost = calculate_cost(
            "claude-opus-4-7",
            input_tokens=1_000_000,
            output_tokens=0,
            cached_tokens=1_000_000,
        )
        assert cost == pytest.approx(0.50)

    def test_partially_cached_input(self) -> None:
        # 500k regular @ $5/M + 500k cached @ $0.50/M = $2.50 + $0.25 = $2.75
        cost = calculate_cost(
            "claude-opus-4-7",
            input_tokens=1_000_000,
            output_tokens=0,
            cached_tokens=500_000,
        )
        assert cost == pytest.approx(2.75)

    def test_cached_without_cached_rate_falls_back_to_input(self) -> None:
        # o3-pro doesn't have cached_input; cached tokens should bill at input rate.
        # o3-pro input = $20/M
        cost = calculate_cost(
            "o3-pro",
            input_tokens=1_000_000,
            output_tokens=0,
            cached_tokens=1_000_000,
        )
        assert cost == pytest.approx(20.00)

    def test_cached_clamped_to_input(self) -> None:
        # Caller passing cached > input should be clamped (defensive).
        cost = calculate_cost(
            "claude-opus-4-7",
            input_tokens=1_000,
            output_tokens=0,
            cached_tokens=10_000_000,
        )
        # All 1000 input tokens billed at cached rate.
        assert cost == pytest.approx(0.50 * 1_000 / 1_000_000)

    def test_local_model_is_free(self) -> None:
        assert calculate_cost("local/llama-3.3-70b", 100_000, 100_000) == 0.0
        assert calculate_cost("local/anything", 1_000_000, 1_000_000, cached_tokens=999) == 0.0

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(UnknownModelError):
            calculate_cost("totally-fake-model", 100, 100)

    def test_zero_tokens(self) -> None:
        assert calculate_cost("claude-opus-4-7", 0, 0) == 0.0


class TestPricingTableCoverage:
    """Smoke checks across the registry so adding a model later isn't silently broken."""

    @pytest.mark.parametrize(
        "model",
        [
            "gpt-5.5",
            "gpt-5.4-mini",
            "o3",
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
            "gemini-3.5-flash",
            "gemini-3.1-pro-preview",
            "grok-4.3",
            "deepseek-v4-pro",
            "mistral-large-latest",
            "llama-3.3-70b-versatile",
        ],
    )
    def test_every_headline_model_has_provider(self, model: str) -> None:
        entry = PRICING[model]
        assert "provider" in entry
        assert "input" in entry
        assert "output" in entry

    def test_anthropic_opus_47_pricing_user_corrected(self) -> None:
        entry = PRICING["claude-opus-4-7"]
        assert entry["input"] == 5.00
        assert entry["output"] == 25.00

    def test_anthropic_haiku_45_pricing_user_corrected(self) -> None:
        entry = PRICING["claude-haiku-4-5"]
        assert entry["input"] == 1.00
        assert entry["output"] == 5.00


class TestRetiredModels:
    """The retirement guard: error clearly, never substitute."""

    def test_retired_model_error_subclasses_modelarium_error(self) -> None:
        # THE load-bearing assertion. cli.py's compare and batch commands catch
        # ModelariumError, not Exception. If this is ever reparented directly to
        # Exception, every retired-ID path becomes an unhandled traceback and
        # nothing else in the suite would notice.
        assert issubclass(RetiredModelError, ModelariumError)

    def test_retired_is_distinct_from_unknown(self) -> None:
        # "Unknown" reads as a typo; these IDs were deliberately retired.
        assert not issubclass(RetiredModelError, UnknownModelError)
        assert not issubclass(UnknownModelError, RetiredModelError)

    @pytest.mark.parametrize("model", sorted(RETIRED_MODELS))
    def test_retired_id_raises_retired_not_unknown(self, model: str) -> None:
        with pytest.raises(RetiredModelError):
            get_provider_for_model(model)

    @pytest.mark.parametrize("model", sorted(RETIRED_MODELS))
    def test_message_names_replacement_and_date(self, model: str) -> None:
        replacement, retired_on = RETIRED_MODELS[model]
        with pytest.raises(RetiredModelError) as exc:
            get_provider_for_model(model)
        message = str(exc.value)
        assert replacement in message
        assert retired_on in message
        assert model in message

    @pytest.mark.parametrize("model", sorted(RETIRED_MODELS))
    def test_retired_id_is_never_silently_resolved(self, model: str) -> None:
        # No substitution, no aliasing, no fallback: resolution must not return.
        replacement, _ = RETIRED_MODELS[model]
        with pytest.raises(RetiredModelError):
            get_provider_for_model(model)
        # And the replacement it names must itself be live.
        assert replacement in PRICING

    @pytest.mark.parametrize("model", sorted(RETIRED_MODELS))
    def test_retired_id_removed_from_pricing(self, model: str) -> None:
        assert model not in PRICING

    @pytest.mark.parametrize("model", sorted(RETIRED_MODELS))
    def test_compare_with_retired_id_exits_2(self, model: str) -> None:
        # CI consumers gate on exit status, so the code matters as much as the
        # message. EXIT_CALL_FAILED == 2, matching other ConfigurationErrors.
        result = CliRunner().invoke(cli_main, ["compare", "--models", model, "hi"])
        assert result.exit_code == 2, result.output
        assert "was retired by its provider" in result.output
        assert "Unknown model" not in result.output

    @pytest.mark.parametrize("model", sorted(RETIRED_MODELS))
    def test_pricing_command_reports_retirement(self, model: str) -> None:
        result = CliRunner().invoke(cli_main, ["pricing", model])
        assert result.exit_code == 2, result.output
        assert "was retired by its provider" in result.output
        assert "Unknown model" not in result.output

    def test_retired_ids_absent_from_resolve_all_cloud(self) -> None:
        # _resolve_all_cloud() reads PRICING directly and bypasses the guard
        # entirely, so this is enforced only by removal from PRICING. Pin it.
        from cli_modelarium.cli import _resolve_all_cloud

        resolved = set(_resolve_all_cloud())
        assert resolved.isdisjoint(RETIRED_MODELS)

    def test_no_id_is_both_live_and_retired(self) -> None:
        assert set(PRICING).isdisjoint(RETIRED_MODELS)

    def test_genuine_typo_still_raises_unknown(self) -> None:
        with pytest.raises(UnknownModelError):
            get_provider_for_model("not-a-real-model")

    @pytest.mark.parametrize("model", ["mistral-medium-3.5", "gemini-3-flash"])
    def test_never_retired_ids_are_unknown_not_retired(self, model: str) -> None:
        # Neither was retired by its provider: one was a duplicate this registry
        # invented, the other was simply the wrong ID. "Unknown" is accurate.
        assert model not in RETIRED_MODELS
        with pytest.raises(UnknownModelError):
            get_provider_for_model(model)
