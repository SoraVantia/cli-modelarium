"""What the 2026-09-06 pricing sweep established, pinned row by row.

Every figure here is the one the sweep read off the provider's own page. The
point is not that the arithmetic works - `test_pricing.py` covers that - it is
that a later edit which drifts a rate back has to fail here rather than ship a
confident wrong number. A wrong rate is invisible in normal use: the tool
prints a total and nothing in the output can tell.

The four corrections and their direction:

    gpt-5.6-sol        5.00 / 30.00 / 0.50  ->  4.00 / 20.00 / 0.40   DOWN
    deepseek-v4-pro    0.435 / 0.87         ->  1.32 / 3.96           UP
    deepseek-v4-flash  0.14 / 0.28          ->  0.44 / 1.32           UP
    qwen3.7-plus       unchanged - list price kept, discount documented

gpt-5.6-sol is the only one that moved DOWN, and the only one where the tool
was over-reporting. Everything else in this cycle under-reported.
"""

from __future__ import annotations

import re

import pytest

from cli_modelarium.exceptions import RetiredModelError, UnknownModelError
from cli_modelarium.models_registry import MODEL_GROUPS, get_provider_for_model
from cli_modelarium.pricing import (
    PRICING,
    PRICING_AS_OF,
    calculate_cost,
    pricing_freshness_note,
    rejects_sampling_params,
)

SWEEP_DATE = "2026-09-06"


class TestTheFourCorrectedRows:
    def test_gpt_5_6_sol_is_the_promotional_rate(self) -> None:
        # OpenAI's pricing table, read 2026-09-06. The promotion runs "at least
        # through November 21, 2026", so this row goes UP when it ends.
        row = PRICING["gpt-5.6-sol"]
        assert (row["input"], row["output"], row["cached_input"]) == (4.00, 20.00, 0.40)

    def test_gpt_5_6_sol_now_ranks_below_claude_opus_4_8(self) -> None:
        # The reason the direction matters for a comparison tool. At the old
        # 5.00 / 30.00 this model ranked above claude-opus-4-8 on both columns;
        # at the real rate it is below on both.
        sol, opus = PRICING["gpt-5.6-sol"], PRICING["claude-opus-4-8"]
        assert sol["input"] < opus["input"]
        assert sol["output"] < opus["output"]

    def test_deepseek_rows_are_the_peak_tier(self) -> None:
        # Peak is 01:00-04:00 and 06:00-10:00 UTC Mon-Fri; off-peak is exactly
        # half. Peak is stored because over-reporting off-peak is the safe
        # direction. The old values matched neither tier.
        pro, flash = PRICING["deepseek-v4-pro"], PRICING["deepseek-v4-flash"]
        assert (pro["input"], pro["output"], pro["cached_input"]) == (1.32, 3.96, 0.044)
        assert (flash["input"], flash["output"], flash["cached_input"]) == (0.44, 1.32, 0.014)

    @pytest.mark.parametrize("model", ["deepseek-v4-pro", "deepseek-v4-flash"])
    def test_off_peak_is_exactly_half_of_what_is_stored(self, model: str) -> None:
        # Documents the relationship the schema cannot express: one row, two
        # rates. If a later change decides to store off-peak instead, this is
        # the arithmetic it has to satisfy.
        off_peak = {"deepseek-v4-pro": 1.98, "deepseek-v4-flash": 0.66}[model]
        assert PRICING[model]["output"] / 2 == pytest.approx(off_peak)

    def test_qwen3_7_plus_stores_list_price_not_the_discounted_one(self) -> None:
        # Alibaba shows "List price $0.4 (Limited-time 20% off)". List is
        # stored, so a run today is billed 20% under what this row says - the
        # over-reporting direction, and the one the block rule already picks.
        row = PRICING["qwen3.7-plus"]
        assert (row["input"], row["output"]) == (0.40, 1.60)
        assert row["input"] * 0.8 == pytest.approx(0.32), "the effective rate, for the record"


class TestWithdrawnModels:
    """Mistral's reasoning family is gone and no replacement is named."""

    @pytest.mark.parametrize("model", ["magistral-medium-latest", "magistral-small-latest"])
    def test_raises_unknown_not_retired(self, model: str) -> None:
        # RETIRED_MODELS exists to name a replacement. Mistral names none, so
        # RetiredModelError would have to invent one. "Unknown model" is the
        # accurate answer, and this asserts the distinction rather than just
        # that something raised.
        assert model not in PRICING
        with pytest.raises(UnknownModelError):
            get_provider_for_model(model)
        try:
            get_provider_for_model(model)
        except RetiredModelError:  # pragma: no cover - the failure this pins
            pytest.fail(f"{model} must not resolve as retired: no replacement exists to name")
        except UnknownModelError:
            pass

    def test_no_static_group_still_lists_them(self) -> None:
        listed = {m for members in MODEL_GROUPS.values() for m in members}
        assert "magistral-medium-latest" not in listed
        assert "magistral-small-latest" not in listed


class TestMistralCachedRates:
    """Published at exactly 10% of input, and the registry carried none."""

    EXPECTED = {
        "mistral-medium-latest": (1.50, 0.15),
        "mistral-large-latest": (0.50, 0.05),
        "mistral-small-latest": (0.15, 0.015),
        "codestral-latest": (0.30, 0.03),
    }

    @pytest.mark.parametrize("model", sorted(EXPECTED))
    def test_rate_is_registered_and_is_a_tenth_of_input(self, model: str) -> None:
        expected_input, expected_cached = self.EXPECTED[model]
        row = PRICING[model]
        assert row["input"] == expected_input
        assert row["cached_input"] == pytest.approx(expected_cached)
        assert row["cached_input"] == pytest.approx(row["input"] / 10)

    def test_a_cached_hit_now_costs_a_tenth_of_what_it_did(self) -> None:
        # The path that actually changed. Before these rates existed,
        # `calculate_cost` fell through to the full input rate for cached
        # tokens, so every cache hit over-reported 10x. This is the fallback
        # arithmetic against the registered arithmetic, on the same input.
        cost = calculate_cost("mistral-medium-latest", input_tokens=1_000_000, output_tokens=0,
                              cached_tokens=1_000_000)
        assert cost == pytest.approx(0.15), "1M fully-cached input at the cache-read rate"
        fallback = 1.50
        assert cost == pytest.approx(fallback / 10)


class TestTheTwoNewRows:
    def test_gpt_6_astra_resolves_priced_and_rejects_temperature(self) -> None:
        # Verified by live call 2026-09-06: temperature=0.5 returned a 400
        # reading "Only the default (1) value is supported"; 1.0 was accepted.
        assert get_provider_for_model("gpt-6-astra") == "openai"
        row = PRICING["gpt-6-astra"]
        assert (row["input"], row["output"], row["cached_input"]) == (10.00, 50.00, 1.00)
        assert row["provider"] == "openai"
        assert rejects_sampling_params("gpt-6-astra") is True

    def test_gpt_6_astra_is_priced_where_the_sweep_put_it(self) -> None:
        # Level with claude-fable-5-1 on output and below o3-pro. Stated as a
        # relationship rather than a rank, so adding a row does not break it.
        assert PRICING["gpt-6-astra"]["output"] == PRICING["claude-fable-5-1"]["output"]
        assert PRICING["gpt-6-astra"]["output"] < PRICING["o3-pro"]["output"]

    def test_gemini_3_8_flash_resolves_and_is_priced(self) -> None:
        assert get_provider_for_model("gemini-3.8-flash") == "google"
        row = PRICING["gemini-3.8-flash"]
        assert (row["input"], row["output"], row["cached_input"]) == (0.75, 3.75, 0.075)
        assert row["provider"] == "google"

    def test_the_three_gemini_flash_rows_share_one_introductory_rate(self) -> None:
        # They expire together on 2027-01-01, doubling. If one is corrected
        # without the others, that is worth a failure rather than a silent split.
        rows = [PRICING[m] for m in ("gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash")]
        assert len({(r["input"], r["output"], r["cached_input"]) for r in rows}) == 1

    def test_gemini_3_8_flash_is_the_only_flagged_google_row(self) -> None:
        # Deliberately pinned as an oddity, not as a rule: no other Gemini entry
        # rejects a temperature. If a second one is ever flagged, read this test
        # before assuming the first was a mistake.
        flagged = {m for m, v in PRICING.items()
                   if v.get("provider") == "google" and v.get("rejects_sampling_params")}
        assert flagged == {"gemini-3.8-flash"}


class TestRegistryShape:
    def test_row_count(self) -> None:
        # Two added, two deleted, so the count is unchanged at 94 across the
        # sweep. A tripwire on deliberate edits, not a meaningful constant.
        assert len(PRICING) == 94

    def test_rejecting_count(self) -> None:
        # 17 -> 19. `test_temperature_predicate.py` owns the authoritative
        # tripwire and its reasoning; this asserts the sweep's own delta.
        assert sum(1 for v in PRICING.values() if v.get("rejects_sampling_params")) == 19


class TestTheDate:
    def test_constant(self) -> None:
        assert PRICING_AS_OF == SWEEP_DATE

    def test_freshness_note_renders_it(self) -> None:
        # The note is printed at five CLI sites, so this is the string a user
        # actually sees.
        note = pricing_freshness_note()
        assert SWEEP_DATE in note
        assert "Verify current pricing at provider websites" in note

    def test_every_readme_states_it(self) -> None:
        # Uses the parity suite's own date selector rather than a second one:
        # a fresh regex here would drift from the one that guards the nine
        # files, and the translations write the date six different ways.
        from tests.test_readme_parity import ALL_READMES, _read, _to_iso

        for name in ALL_READMES:
            found = {
                iso
                for raw in re.findall(r"\*\*([^*]*\d{4}[^*]*)\*\*", _read(name))
                if (iso := _to_iso(raw)) is not None
            }
            assert SWEEP_DATE in found, (
                f"{name} does not state {SWEEP_DATE}; states {sorted(found)}"
            )


class TestTheReadmesDoNotOverclaim:
    """The nine files say what was NOT verified, and where the two time bombs are.

    Matched on identifiers and brand names rather than prose, so one assertion
    covers all nine languages. A user planning a budget will not read the
    registry source, so these facts have to survive here too.
    """

    @pytest.mark.parametrize("provider", ["Groq", "Moonshot", "NVIDIA", "OpenRouter"])
    def test_every_readme_names_the_unverified_providers(self, provider: str) -> None:
        from tests.test_readme_parity import ALL_READMES, _read

        for name in ALL_READMES:
            assert provider in _read(name), f"{name} does not name {provider} as unverified"

    @pytest.mark.parametrize(
        "model,expiry",
        [("gemini-3.8-flash", "2027"), ("gpt-5.6-sol", "2026")],
    )
    def test_every_readme_states_both_expiries(self, model: str, expiry: str) -> None:
        # Both expire UPWARD, so a comparison run today reads cheaper than the
        # same run will later - uniformly, which is why nothing in the output
        # looks odd and why it has to be stated in prose.
        from tests.test_readme_parity import ALL_READMES, _read

        for name in ALL_READMES:
            text = _read(name)
            assert model in text, f"{name} does not name {model}"
            assert expiry in text, f"{name} does not state the {expiry} expiry"


class TestWhatTheSweepDidNotSettle:
    """Four providers are not covered by PRICING_AS_OF, and the file says so.

    Recorded as tests because the failure mode is a later sweep quietly
    absorbing them under a new date without anyone having checked.
    """

    @pytest.mark.parametrize(
        "provider,marker",
        [
            ("groq", "UNVERIFIED"),
            ("moonshot", "NOT FIRST-PARTY VERIFIED"),
            ("nvidia", "UNVERIFIABLE BY CONSTRUCTION"),
            ("openrouter", "NOT CHECKED"),
        ],
    )
    def test_block_carries_its_caveat(self, provider: str, marker: str) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "src" / "cli_modelarium" / "pricing.py"
        text = source.read_text(encoding="utf-8")
        assert marker in text, f"the {provider} block no longer states {marker!r}"

    def test_the_header_names_all_four(self) -> None:
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "src" / "cli_modelarium" / "pricing.py"
        header = source.read_text(encoding="utf-8").split("PRICING_AS_OF = ")[0]
        for provider in ("groq", "moonshot", "nvidia", "openrouter"):
            assert provider in header, f"{provider} is not listed as uncovered by PRICING_AS_OF"
