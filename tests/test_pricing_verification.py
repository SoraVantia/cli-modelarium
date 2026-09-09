"""`PRICING_VERIFICATION` - how each provider's rates were established.

This constant exists so that a documented claim about verification can be
pinned. Before it, the status lived only in prose comments: `grep UNVERIFIED
src/` outside comments returned nothing, so no test could assert on it, and the
nine READMEs stated the same fact with nothing checking they agreed.

That gap is not hypothetical. A README audit on 2026-09-06 found a sentence
claiming the pricing date was absent from Markdown output when
`_format_markdown` has emitted it since 2026-06-04. The false sentence was
introduced by `1d3ea74`, a commit titled "correct four false README claims",
and survived a month because nothing pinned it.
"""

from __future__ import annotations

import pytest

from cli_modelarium.pricing import (
    FIRST_PARTY,
    NOT_PRICED,
    PRICING,
    PRICING_VERIFICATION,
    RESELLER,
    THIRD_PARTY,
    UNCHECKED,
    UNPUBLISHED,
    pricing_verification_coverage,
    providers_not_first_party,
)

STATUSES = frozenset(
    {FIRST_PARTY, THIRD_PARTY, RESELLER, UNPUBLISHED, UNCHECKED, NOT_PRICED}
)


class TestEveryProviderHasAStatus:
    def test_no_provider_is_missing(self) -> None:
        # The failure this exists to prevent: a provider added to PRICING with no
        # verification status reads as verified in the READMEs' table, because a
        # blank cell looks like a clean one.
        in_registry = {str(v["provider"]) for v in PRICING.values()}
        missing = in_registry - set(PRICING_VERIFICATION)
        assert not missing, (
            f"{sorted(missing)} appear in PRICING with no PRICING_VERIFICATION entry. "
            f"Add one - an unstated status is read as verified by everything downstream."
        )

    def test_no_status_is_orphaned(self) -> None:
        # The other direction: a provider removed from the registry should not
        # leave a status behind claiming something about rows that no longer exist.
        in_registry = {str(v["provider"]) for v in PRICING.values()}
        orphans = set(PRICING_VERIFICATION) - in_registry
        assert not orphans, f"{sorted(orphans)} have a status but no rows in PRICING"

    def test_all_thirteen_are_covered(self) -> None:
        from cli_modelarium.models_registry import all_known_providers

        assert set(PRICING_VERIFICATION) == set(all_known_providers())
        assert len(PRICING_VERIFICATION) == 13

    @pytest.mark.parametrize("provider", sorted(PRICING_VERIFICATION))
    def test_status_is_from_the_closed_set(self, provider: str) -> None:
        assert PRICING_VERIFICATION[provider] in STATUSES


class TestTheFourAreDistinct:
    """The 2026-09-06 sweep left four providers uncovered, for four reasons.

    Flattening them to a boolean would lose the distinction a reader acts on:
    nvidia can never be verified, openrouter simply was not looked at, groq's
    rates are corroborated but its catalogue is in doubt, and moonshot's figures
    came from a reseller.
    """

    EXPECTED = {
        "groq": THIRD_PARTY,
        "moonshot": RESELLER,
        "nvidia": UNPUBLISHED,
        "openrouter": UNCHECKED,
    }

    @pytest.mark.parametrize("provider", sorted(EXPECTED))
    def test_each_carries_its_own_status(self, provider: str) -> None:
        assert PRICING_VERIFICATION[provider] == self.EXPECTED[provider]

    def test_the_four_statuses_are_four_different_values(self) -> None:
        assert len(set(self.EXPECTED.values())) == 4, "the distinction is the point"

    def test_providers_not_first_party_is_exactly_those_four(self) -> None:
        # local is excluded on purpose: its rows are $0 by construction, so
        # "not verified" would be a category error rather than a caveat.
        assert providers_not_first_party() == ["groq", "moonshot", "nvidia", "openrouter"]

    def test_local_is_not_priced_rather_than_unverified(self) -> None:
        assert PRICING_VERIFICATION["local"] == NOT_PRICED


class TestCoverageIsDerived:
    """The counts come from the registry, not from a number someone typed."""

    def test_matches_the_measured_figures(self) -> None:
        # 2026-09-06: 93 priced rows, 25 behind the four uncovered providers
        # (nvidia 9, openrouter 8, groq 4, moonshot 4), so 68 verified.
        verified, priced = pricing_verification_coverage()
        assert (verified, priced) == (68, 93)

    def test_local_rows_are_in_neither_half(self) -> None:
        _, priced = pricing_verification_coverage()
        assert priced == len([v for v in PRICING.values() if not v.get("is_local")])
        assert priced == len(PRICING) - 1, "one local wildcard row"

    def test_the_arithmetic_closes(self) -> None:
        verified, priced = pricing_verification_coverage()
        uncovered = sum(
            1
            for v in PRICING.values()
            if not v.get("is_local")
            and PRICING_VERIFICATION[str(v["provider"])] != FIRST_PARTY
        )
        assert verified + uncovered == priced

    def test_it_would_move_if_a_provider_were_re_verified(self) -> None:
        # Guards against a hardcoded 68 hiding behind a derived-looking call. If
        # openrouter's eight rows are verified by the script its comment
        # describes, coverage must become 76 without anyone editing a number.
        patched = dict(PRICING_VERIFICATION)
        patched["openrouter"] = FIRST_PARTY
        recomputed = sum(
            1
            for v in PRICING.values()
            if not v.get("is_local") and patched[str(v["provider"])] == FIRST_PARTY
        )
        assert recomputed == 76, "eight openrouter rows should join the verified half"
