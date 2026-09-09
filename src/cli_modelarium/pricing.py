"""Pricing data and cost calculation for all supported models.

Pricing is per 1M tokens, in USD. Verified September 6, 2026 from each
provider's official documentation, with four providers excepted - see
PRICING_AS_OF below, which names them. LLM pricing changes frequently -
re-verify against the provider's pricing page before relying on these values
for production budgeting.

Schema per entry:
    input                    - cost per 1M input tokens (required)
    output                   - cost per 1M output tokens (required)
    cached_input             - cost per 1M cached input tokens (optional; typically ~90% off)
    provider                 - provider name matching BaseProvider.name (required)
    is_local                 - True for local models (optional; always free)
    rejects_sampling_params  - True when the provider 400s if `temperature` is sent at a
                               non-default value (optional; absent means SEND). Only the
                               models measured to reject it carry this flag; see
                               `rejects_sampling_params()` below.
"""

from __future__ import annotations

from cli_modelarium.exceptions import UnknownModelError

# Prices are each provider's STANDARD / LIST public pay-as-you-go rate per 1M tokens -
# NOT batch, priority/flex, off-peak, or promotional pricing.
#
# ONE ROW BREAKS THAT RULE ON PURPOSE: gpt-5.6-sol. OpenAI publishes 4.00 / 20.00 as
# THE price with a promotional footnote and shows no concurrent list price, so the
# promotional figure is what a caller is charged today and storing anything else
# would be storing a number nobody pays. qwen3.7-plus is the contrasting case and
# goes the other way: Alibaba prints a list price AND a "20% off" beside it, so the
# list price is a real published figure and is what this file stores. The rule is
# therefore "store what the provider says you will be charged, and prefer the
# higher figure when the page states two" - both rows are annotated at their entry.
# For models tiered by input size (OpenAI, Gemini, and Qwen flagships), the entry /
# short-context tier is stored. `cached_input` = the provider's cache-read / implicit-cache
# rate (not cache-write/creation). DeepSeek rates are PEAK, the higher of its two
# tiers - see the DeepSeek block. Qwen flagship rates are list price (the
# time-limited promo is NOT used).
#
# WHAT PRICING_AS_OF MEANS. On that date ten providers were read against their own
# published pricing pages and 81 rows were compared, several exercised by live call
# the same day. Four rows were wrong and are corrected here, two withdrawn models
# were deleted, and four published cached rates that the registry was missing were
# added. A wrong rate is invisible - the tool reports a confident number and nothing
# in the output can tell - so the sweep is the only thing standing between a stale
# constant and a budget built on it.
#
# FOUR PROVIDERS ARE NOT COVERED BY THAT DATE. They are recorded at their own blocks
# below rather than swept under it:
#   groq        UNVERIFIED. Rates match every third-party source, but two sources
#               report that on 2026-08-26 llama-3.1-8b-instant and
#               llama-3.3-70b-versatile moved from self-serve to sales-led
#               enterprise. A pricing page cannot answer that; a catalogue call can.
#   moonshot    Corroborated only through Alibaba's resale listing. That is
#               corroboration, not first-party verification.
#   nvidia      Unverifiable by construction - NVIDIA publishes no per-token rate
#               anywhere - and 3 of the 9 rows are dead.
#   openrouter  Not checked in this sweep. It is the one provider that serves prices
#               through its API: /api/v1/models returns pricing.prompt and
#               pricing.completion with no key required, so this block can be
#               verified automatically rather than by hand.
PRICING_AS_OF = "2026-09-06"

# HOW EACH PROVIDER'S RATES WERE ESTABLISHED, as of PRICING_AS_OF. The prose above
# says this in sentences; this says it in a form a test can read. That difference is
# the point: the nine READMEs state the same fact, and the only thing that stops a
# documented claim drifting from the code is a constant something can assert on.
#
# NOT A BOOLEAN. "Not first-party verified" covers four materially different
# situations and collapsing them loses the part a reader needs:
#
#   FIRST_PARTY   Read against the provider's own published pricing page on
#                 PRICING_AS_OF. The default, and what the date means.
#   THIRD_PARTY   Rates agree with every third-party source checked, but no
#                 first-party read was made. Weaker than it sounds for groq, whose
#                 CATALOGUE rather than whose rates is in question - a pricing page
#                 cannot show that a model moved to sales-led access.
#   RESELLER      Corroborated only through a reseller's listing. The figures
#                 matched, but a reseller is not the vendor.
#   UNPUBLISHED   There is no per-token rate to verify. This is unverifiABLE, not
#                 unverifiED, and no future sweep will change it.
#   UNCHECKED     Not looked at in this pass. Says nothing about the rates either
#                 way, which is exactly why it is its own value.
#   NOT_PRICED    Nothing to verify: the rows are $0 by construction.
FIRST_PARTY = "first-party"
THIRD_PARTY = "third-party"
RESELLER = "reseller"
UNPUBLISHED = "unpublished"
UNCHECKED = "unchecked"
NOT_PRICED = "not-priced"

# Every provider in the registry carries a status. A provider added without one
# fails `test_pricing_verification.py`, which is deliberate: an unstated status
# would silently read as verified in the READMEs' table.
PRICING_VERIFICATION: dict[str, str] = {
    "anthropic": FIRST_PARTY,
    "dashscope": FIRST_PARTY,
    "deepseek": FIRST_PARTY,
    "google": FIRST_PARTY,
    "mistral": FIRST_PARTY,
    "openai": FIRST_PARTY,
    "xai": FIRST_PARTY,
    "zai": FIRST_PARTY,
    # Rates match every third-party source checked. What is open is the catalogue:
    # two sources report that on 2026-08-26 llama-3.1-8b-instant and
    # llama-3.3-70b-versatile moved from self-serve to sales-led enterprise access.
    # A pricing page cannot answer that; a catalogue call can, and none was made.
    "groq": THIRD_PARTY,
    # Corroborated through Alibaba's resale listing, which showed kimi-k3 at 3.00 /
    # 15.00 and kimi-k2.7-code at 0.95 / 4.00 - both matching. Corroboration through
    # a reseller, not verification against Moonshot.
    "moonshot": RESELLER,
    # NVIDIA publishes no per-token rate anywhere, so the zeros cannot be checked
    # against anything. Three of the nine rows are also dead: 410 Gone, EOL
    # 2026-08-26T09:00:00Z, no successor named.
    "nvidia": UNPUBLISHED,
    # The one provider that serves prices through its API - GET /api/v1/models
    # returns pricing.prompt and pricing.completion with no key required - so this
    # block can be verified by a script rather than by hand. Worth doing before the
    # next sweep; until then it is unchecked, not verified.
    "openrouter": UNCHECKED,
    "local": NOT_PRICED,
}


def pricing_verification_coverage() -> tuple[int, int]:
    """Return (rows read against a first-party page, priced rows in the registry).

    Derived from PRICING and PRICING_VERIFICATION rather than stated, so the
    numbers move when a provider is re-verified or a row is added. Local rows are
    excluded from both halves: they are free by construction and counting them
    would inflate the coverage figure with rows nobody prices.
    """
    priced = [v for v in PRICING.values() if not v.get("is_local")]
    verified = [
        v
        for v in priced
        if PRICING_VERIFICATION.get(str(v["provider"])) == FIRST_PARTY
    ]
    return len(verified), len(priced)


def providers_not_first_party() -> list[str]:
    """Providers whose rates were not read against the vendor's own page, sorted."""
    return sorted(
        p
        for p, status in PRICING_VERIFICATION.items()
        if status not in (FIRST_PARTY, NOT_PRICED)
    )


# Model IDs the PROVIDER has retired. Not a compatibility shim: resolution
# raises RetiredModelError naming the replacement, and never substitutes it.
# Silent substitution is the failure mode this exists to prevent - xAI, for
# example, redirects retired slugs to grok-4.3 and bills at grok-4.3 rates, so
# a request appears to succeed while the reported cost is wrong by ~6x.
# Entries stay here after removal from PRICING so the error can stay specific.
# IDs that were never provider-retired (a duplicate this registry invented, or
# a simply-wrong ID) do NOT belong here - "Unknown model" is accurate for those.
RETIRED_MODELS: dict[str, tuple[str, str]] = {
    # retired id       -> (suggested replacement, retirement date)
    "deepseek-chat": ("deepseek-v4-flash", "2026-07-24"),
    "deepseek-reasoner": ("deepseek-v4-pro", "2026-07-24"),
    "grok-4.1-fast": ("grok-4.3", "2026-05-15"),
}

PRICING: dict[str, dict[str, float | str | bool]] = {
    # ===== OpenAI =====
    # gpt-5.6-terra is OpenAI's named replacement for o4-mini, which shuts down
    # 2026-10-23.
    #
    # Verified by live call 2026-09-06: reachable on chat-completions, answers, and
    # rejects temperature=0.5 with a 400 reading "Only the default (1) value is
    # supported" while accepting 1.0. The most expensive output rate in the
    # registry, level with claude-fable-5-1 and below o3-pro.
    "gpt-6-astra": {
        "input": 10.00,
        "output": 50.00,
        "cached_input": 1.00,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    # PROMOTIONAL RATE, so this row goes UP when it ends, not down. OpenAI's pricing
    # table on 2026-09-06 reads 4.00 / 20.00 / 0.40 with the footnote "GPT-5.6 Sol's
    # promotional pricing is available at least through November 21, 2026". Re-check
    # around 2026-11-21. Same shape as the gemini-3.8/3.7/3.6-flash rows below, which
    # expire upward on 2027-01-01, and the opposite of claude-sonnet-5, whose
    # introductory rate became permanent.
    #
    # This row previously carried 5.00 / 30.00 / 0.50 and OVER-reported. Nothing in
    # it looked wrong, because the stale figures were internally consistent: 0.50 is
    # 10% of 5.00 exactly as 0.40 is 10% of 4.00, so the cached rate corroborated a
    # baseline that is no longer charged. The direction matters for a comparison
    # tool - at 4.00 / 20.00 this model sits BELOW claude-opus-4-8 at 5.00 / 25.00,
    # and the registry ranked it above.
    "gpt-5.6-sol": {
        "input": 4.00,
        "output": 20.00,
        "cached_input": 0.40,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    "gpt-5.6-terra": {
        "input": 2.00,
        "output": 12.00,
        "cached_input": 0.20,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    "gpt-5.6-luna": {
        "input": 0.20,
        "output": 1.20,
        "cached_input": 0.02,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    "gpt-5.5": {
        "input": 5.00,
        "output": 30.00,
        "cached_input": 0.50,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    "gpt-5.4": {"input": 2.50, "output": 15.00, "cached_input": 0.25, "provider": "openai"},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50, "cached_input": 0.075, "provider": "openai"},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25, "cached_input": 0.02, "provider": "openai"},
    # o3-2025-04-16 is removed from the API 2026-12-11; whether the bare `o3`
    # alias survives is unconfirmed. In all-reasoning.
    "o3": {
        "input": 2.00,
        "output": 8.00,
        "cached_input": 0.50,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    # o3-pro-2025-06-10 removed 2026-12-11; bare alias status unconfirmed.
    #
    # GATED, NOT RETIRED - AND THIS SCHEMA CANNOT SAY SO. On 2026-09-06 the model
    # returned "Your organization must be verified to use the model o3-pro" on the
    # unverified key used for the sweep. It is listed, priced and current; it refuses
    # callers whose organization is unverified. That is a third state beside "present"
    # and "retired" with no field to hold it, and because the row is in `--models all`
    # that command fails outright for anyone unverified. Left in place deliberately:
    # deleting a live model because one key cannot reach it would turn it into an
    # "Unknown model" for every organization that can.
    "o3-pro": {"input": 20.00, "output": 80.00, "provider": "openai"},
    # Shuts down 2026-10-23 (documented alias of o4-mini-2025-04-16).
    # Replacement: gpt-5.6-terra. In all-reasoning.
    "o4-mini": {
        "input": 1.10,
        "output": 4.40,
        "cached_input": 0.275,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    "gpt-5": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "provider": "openai",
        "rejects_sampling_params": True,
    },
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60, "cached_input": 0.10, "provider": "openai"},
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached_input": 1.25, "provider": "openai"},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached_input": 0.075, "provider": "openai"},
    # ===== Anthropic =====
    "claude-opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cached_input": 0.50,
        "provider": "anthropic",
        "rejects_sampling_params": True,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cached_input": 0.30,
        "provider": "anthropic",
    },
    # Anthropic lists retirement not sooner than 2026-10-15; no deprecation
    # announced. In all-budget and all-cheap.
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cached_input": 0.10,
        "provider": "anthropic",
    },
    "claude-opus-5": {
        "input": 5.00,
        "output": 25.00,
        "cached_input": 0.50,
        "provider": "anthropic",
        "rejects_sampling_params": True,
    },
    # Anthropic states the introductory 2/10 rate is now permanent and the
    # planned 2026-09-01 increase is cancelled. That date has now passed and the
    # 2026-09-06 sweep found the rate unchanged, so this is settled rather than
    # pending - the entry that follows is what Anthropic charges today.
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cached_input": 0.20,
        "provider": "anthropic",
        "rejects_sampling_params": True,
    },
    "claude-opus-4-6": {
        "input": 5.00,
        "output": 25.00,
        "cached_input": 0.50,
        "provider": "anthropic",
    },
    "claude-fable-5": {
        "input": 10.00,
        "output": 50.00,
        "cached_input": 1.00,
        "provider": "anthropic",
        "rejects_sampling_params": True,
    },
    # The 0.25 cache rate is 2.5% of input, where every other Claude row is
    # 10%, and reads as a dropped digit. It is not: Anthropic's pricing page
    # footnotes cache hits on Fable 5.1 and Mythos 5.1 at 0.025x base input,
    # every other model at 0.1x.
    "claude-fable-5-1": {
        "input": 10.00,
        "output": 50.00,
        "cached_input": 0.25,
        "provider": "anthropic",
        "rejects_sampling_params": True,
    },
    "claude-opus-4-8": {
        "input": 5.00,
        "output": 25.00,
        "cached_input": 0.50,
        "provider": "anthropic",
        "rejects_sampling_params": True,
    },
    "claude-opus-4-5": {
        "input": 5.00,
        "output": 25.00,
        "cached_input": 0.50,
        "provider": "anthropic",
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "cached_input": 0.30,
        "provider": "anthropic",
    },
    # ===== Google Gemini (Google uses dots in model IDs) =====
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "cached_input": 0.15, "provider": "google"},
    "gemini-3.1-pro-preview": {
        "input": 2.00,
        "output": 12.00,
        "cached_input": 0.20,
        "provider": "google",
    },
    "gemini-3.1-flash-lite": {
        "input": 0.25,
        "output": 1.50,
        "cached_input": 0.025,
        "provider": "google",
    },
    # INTRODUCTORY RATE. Google's published schedule shows this entry doubling to
    # 1.50 / 7.50 on 2027-01-01; re-check before then. That records what the page
    # says today, not a rate predicted to start on a date.
    "gemini-3.7-flash": {
        "input": 0.75,
        "output": 3.75,
        "cached_input": 0.075,
        "provider": "google",
    },
    # INTRODUCTORY RATE, on the same schedule as gemini-3.7-flash above: 0.75 /
    # 3.75 / 0.075 through 2026-12-31, then 1.50 / 7.50 / 0.15 from 2027-01-01.
    # Re-check before that date. This row carried the 2027 figures until
    # 2026-08-23 - a future rate written into a field that means "current", which
    # is how every Sonnet 5 figure came to print high in the other direction.
    # Identical to gemini-3.7-flash, which is how Google prices the two.
    "gemini-3.6-flash": {
        "input": 0.75,
        "output": 3.75,
        "cached_input": 0.075,
        "provider": "google",
    },
    # INTRODUCTORY RATE, same schedule again - doubles to 1.50 / 7.50 / 0.15 on
    # 2027-01-01. Three Gemini rows now expire together on that date.
    "gemini-3.8-flash": {
        "input": 0.75,
        "output": 3.75,
        "cached_input": 0.075,
        "provider": "google",
        "rejects_sampling_params": True,
    },
    # No shutdown date announced, and Google names no replacement. Checked
    # 2026-08-07 against ai.google.dev/gemini-api/docs/deprecations.
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50, "cached_input": 0.03, "provider": "google"},
    # No shutdown date announced, and Google names no replacement. Checked
    # 2026-08-07 against the same page. In all-cheap.
    "gemini-2.5-flash-lite": {
        "input": 0.10,
        "output": 0.40,
        "cached_input": 0.01,
        "provider": "google",
    },
    # ===== xAI Grok (xAI uses dots in model IDs) =====
    # Entry tier: xAI bills grok-4.6 at this rate up to a 200k-token request. Past 200k
    # EVERY token in the request bills at the higher tier, not just the excess,
    # so a single long request costs more than this row implies.
    "grok-4.6": {"input": 2.00, "output": 6.00, "cached_input": 0.50, "provider": "xai"},
    "grok-4.3": {"input": 1.25, "output": 2.50, "cached_input": 0.20, "provider": "xai"},
    "grok-4.20-0309-non-reasoning": {
        "input": 1.25,
        "output": 2.50,
        "cached_input": 0.20,
        "provider": "xai",
    },
    "grok-4.20-multi-agent-0309": {
        "input": 1.25,
        "output": 2.50,
        "cached_input": 0.20,
        "provider": "xai",
    },
    "grok-build-0.1": {"input": 1.00, "output": 2.00, "cached_input": 0.20, "provider": "xai"},
    # ===== DeepSeek =====
    # PEAK RATES, and the choice is deliberate. DeepSeek charges two rates a day:
    # peak is 01:00-04:00 and 06:00-10:00 UTC, Monday to Friday; off-peak is
    # everything else, at exactly half. Peak is stored because it is the
    # conservative direction - the tool over-reports an off-peak run rather than
    # under-reporting a peak one - the same way the NVIDIA zeros below take the
    # safe reading and say so.
    #
    # THE SCHEMA CANNOT EXPRESS WHAT DEEPSEEK DOES, and no caveat fixes that. One
    # row holds one rate, so a `--runs 5` comparison started at 03:55 UTC crosses a
    # price change mid-run and every cell is priced at the single stored rate.
    #
    # Both rows were 3x to 6x LOW before 2026-09-06, matching neither tier - peak
    # is 1.32 / 3.96 and 0.44 / 1.32, off-peak exactly half of each, and the stored
    # 0.435 / 0.87 and 0.14 / 0.28 were neither. They read like rates from a
    # pricing structure DeepSeek has since revised. The comment that stood here
    # said "standard-hours (not off-peak)", which was wrong twice over: standard
    # hours ARE peak, and the figures were not peak either.
    "deepseek-v4-pro": {
        "input": 1.32,
        "output": 3.96,
        "cached_input": 0.044,
        "provider": "deepseek",
    },
    "deepseek-v4-flash": {
        "input": 0.44,
        "output": 1.32,
        "cached_input": 0.014,
        "provider": "deepseek",
    },
    # ===== Mistral =====
    # cached_input is now carried on every row. Mistral publishes a cache-read rate
    # for every text model at exactly 10% of input, and this registry had none - so
    # cached tokens fell through `calculate_cost`'s full-input-rate fallback and
    # over-reported every cache hit by 10x. That fallback was the right default
    # while the rates were unknown; it is not a reason to keep ignoring published
    # ones.
    #
    # magistral-medium-latest and magistral-small-latest were deleted 2026-09-06:
    # absent from Mistral's pricing page entirely - not in Standard, not Batch, not
    # Priority. The reasoning family is gone and Mistral Medium 3.5 now carries the
    # Reasoning tag itself. They are deliberately NOT in RETIRED_MODELS: that map
    # exists to name a replacement and raise RetiredModelError pointing at it, and
    # Mistral names none. With no replacement to name, "Unknown model" is the
    # accurate answer.
    "mistral-medium-latest": {
        "input": 1.50,
        "output": 7.50,
        "cached_input": 0.15,
        "provider": "mistral",
    },
    "mistral-large-latest": {
        "input": 0.50,
        "output": 1.50,
        "cached_input": 0.05,
        "provider": "mistral",
    },
    "mistral-small-latest": {
        "input": 0.15,
        "output": 0.60,
        "cached_input": 0.015,
        "provider": "mistral",
    },
    "codestral-latest": {
        "input": 0.30,
        "output": 0.90,
        "cached_input": 0.03,
        "provider": "mistral",
    },
    # ===== Groq =====
    # UNVERIFIED as of 2026-09-06, and not covered by PRICING_AS_OF. These rates
    # match every third-party source checked, but two of those sources report that
    # on 2026-08-26 llama-3.1-8b-instant and llama-3.3-70b-versatile moved from
    # self-serve to sales-led enterprise access. A price is not the question; a
    # model you can no longer call at any price is. A pricing page cannot answer
    # that - a catalogue call can, and none was made.
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79, "provider": "groq"},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60, "provider": "groq"},
    "openai/gpt-oss-safeguard-20b": {"input": 0.075, "output": 0.30, "provider": "groq"},
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "input": 0.11,
        "output": 0.34,
        "provider": "groq",
    },
    # ===== OpenRouter =====
    # OpenRouter aggregates 315+ models behind one API; these eight are the
    # ones this registry knows. Resolution is an exact PRICING lookup, so any
    # other OpenRouter ID is an unknown model rather than a passthrough - it
    # is rejected before it can reach a provider or a cost calculation.
    #
    # NOT CHECKED in the 2026-09-06 sweep, and not covered by PRICING_AS_OF. This is
    # the one provider in the registry that serves its prices through its API:
    # GET /api/v1/models returns pricing.prompt and pricing.completion per model with
    # no key required. This block should be verified by a script rather than by hand,
    # and until it is, these eight rows carry no verification date at all.
    "qwen/qwen3.7-max": {"input": 2.50, "output": 7.50, "provider": "openrouter"},
    "qwen/qwen3.5-plus": {"input": 0.30, "output": 1.80, "provider": "openrouter"},
    "qwen/qwen3.6-flash": {"input": 0.19, "output": 1.13, "provider": "openrouter"},
    "qwen/qwen3-coder:free": {"input": 0.0, "output": 0.0, "provider": "openrouter"},
    "deepseek/deepseek-r1:free": {"input": 0.0, "output": 0.0, "provider": "openrouter"},
    "meta-llama/llama-3-3-70b-instruct:free": {
        "input": 0.0,
        "output": 0.0,
        "provider": "openrouter",
    },
    "openai/gpt-oss-120b:free": {"input": 0.0, "output": 0.0, "provider": "openrouter"},
    "zhipuai/glm-4.7-flash:free": {"input": 0.0, "output": 0.0, "provider": "openrouter"},
    # ===== DashScope (Alibaba Model Studio, International/Singapore endpoint) =====
    # Single rate per entry = entry input-tier, non-thinking output (we send
    # enable_thinking=false). cached_input = Implicit-Cache read rate where offered.
    # Read from the Singapore column - the region this endpoint serves. Global is
    # roughly 18% cheaper and belongs to a different host.
    #
    # qwen3.8-max and qwen3.7-flash carry a cached_input that is a smaller fraction
    # of input (8.5% and 10%) than every older row here (20% without exception).
    # Whether Alibaba changed the cache rate class for those models or the older
    # rows use a different one is still NOT settled.
    "qwen3.8-max": {"input": 2.00, "output": 6.00, "cached_input": 0.17, "provider": "dashscope"},
    # Entry input tier, to 32k. Above 32k this bills 0.10 / 0.40, above 256k
    # 0.20 / 0.80 - so a long-context run costs well over this row.
    "qwen3.7-flash": {
        "input": 0.03,
        "output": 0.13,
        "cached_input": 0.003,
        "provider": "dashscope",
    },
    "qwen3.7-max": {"input": 2.50, "output": 7.50, "cached_input": 0.50, "provider": "dashscope"},
    # ON A 20% DISCOUNT, and this row stores the LIST price, not the effective one.
    # Alibaba's Singapore table on 2026-09-06 reads "List price $0.4 (Limited-time
    # 20% off)" on input and the same on output, so a run today is billed 0.32 /
    # 1.28 while this row says 0.40 / 1.60. List is stored for three reasons: it is
    # what the block rule at the top of this file already says for Qwen flagships,
    # it over-reports rather than under-reports when the promotion ends without
    # notice, and the table does not say whether the cached rate is discounted too -
    # so an "effective" row would be part measured and part guessed. The number
    # alone cannot tell a reader any of this, which is why it is written here.
    "qwen3.7-plus": {"input": 0.40, "output": 1.60, "cached_input": 0.08, "provider": "dashscope"},
    "qwen3.6-flash": {"input": 0.25, "output": 1.50, "provider": "dashscope"},
    "qwen3.6-plus": {"input": 0.50, "output": 3.00, "provider": "dashscope"},
    "qwen-flash": {"input": 0.05, "output": 0.40, "cached_input": 0.01, "provider": "dashscope"},
    "qwen3-coder-plus": {
        "input": 1.00,
        "output": 5.00,
        "cached_input": 0.20,
        "provider": "dashscope",
    },
    # ===== Z.AI / GLM (Zhipu AI, OpenAI-compatible overseas endpoint) =====
    # cached_input = Z.AI's "Cached Input" (cache-read) rate; "Cached Input Storage"
    # (limited-time free) has no field. Text models only (vision glm-5v-turbo excluded).
    # Read against Z.AI's pricing page (docs.z.ai). No count is stated here on
    # purpose: a number in prose goes stale the moment a row is added, and nothing
    # in the suite would catch it.
    "glm-5.3": {"input": 1.40, "output": 4.40, "cached_input": 0.26, "provider": "zai"},
    "glm-5.2": {"input": 1.40, "output": 4.40, "cached_input": 0.26, "provider": "zai"},
    "glm-5.1": {"input": 1.40, "output": 4.40, "cached_input": 0.26, "provider": "zai"},
    "glm-5": {"input": 1.00, "output": 3.20, "cached_input": 0.20, "provider": "zai"},
    "glm-5-turbo": {"input": 1.20, "output": 4.00, "cached_input": 0.24, "provider": "zai"},
    "glm-4.7": {"input": 0.60, "output": 2.20, "cached_input": 0.11, "provider": "zai"},
    "glm-4.7-flash": {"input": 0.00, "output": 0.00, "cached_input": 0.00, "provider": "zai"},
    "glm-4.7-flashx": {"input": 0.07, "output": 0.40, "cached_input": 0.01, "provider": "zai"},
    "glm-4.6": {"input": 0.60, "output": 2.20, "cached_input": 0.11, "provider": "zai"},
    "glm-4.5": {"input": 0.60, "output": 2.20, "cached_input": 0.11, "provider": "zai"},
    "glm-4.5-air": {"input": 0.20, "output": 1.10, "cached_input": 0.03, "provider": "zai"},
    "glm-4.5-x": {"input": 2.20, "output": 8.90, "cached_input": 0.45, "provider": "zai"},
    "glm-4.5-airx": {"input": 1.10, "output": 4.50, "cached_input": 0.22, "provider": "zai"},
    "glm-4.5-flash": {"input": 0.00, "output": 0.00, "cached_input": 0.00, "provider": "zai"},
    "glm-4-32b-0414-128k": {"input": 0.10, "output": 0.10, "provider": "zai"},
    # ===== NVIDIA NIM =====
    # UNVERIFIABLE BY CONSTRUCTION, and not covered by PRICING_AS_OF - see the zeros
    # note below.
    #
    # Reachability was verified 2026-08-15 by live call: each row was reachable on
    # chat-completions, answered in `content` rather than `reasoning_content`,
    # accepted a temperature, and streamed with usage. That date is kept rather than
    # replaced, because the 2026-09-06 sweep did not repeat the calls - and because
    # of what happened next. THREE OF THESE NINE ROWS ARE DEAD: they return 410 Gone,
    # EOL 2026-08-26, eleven days after the verification above, and nothing surfaced
    # it until a catalogue diff. The three are not named here because the sweep that
    # found them did not record which; naming the wrong three would be worse than
    # naming none. A catalogue call resolves it in one request and should be run
    # before the next release.
    #
    # THESE ZEROS ARE NOT A PRICE. NVIDIA publishes no per-token rate for hosted
    # NIM anywhere - not in the API, the featured-models feed or the catalog -
    # so 0.0 is what this schema forces, not what the models cost. Access is
    # credit-metered rather than per-token, so a user exhausts credits instead of
    # receiving a bill. Do NOT read these as equivalent to the genuinely-free
    # rows above (the OpenRouter `:free` entries and the two GLM flash models),
    # which are published at zero. `--max-cost` and the `cost_under` assertion
    # therefore provide no protection on this provider; a caveat panel says so at
    # the point of use. No `cached_input` - there is no cache-read rate either.
    "google/gemma-4-31b-it": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    "google/diffusiongemma-26b-a4b-it": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    "nvidia/nemotron-3-ultra-550b-a55b": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    "nvidia/llama-3.3-nemotron-super-49b-v1": {
        "input": 0.0,
        "output": 0.0,
        "provider": "nvidia",
    },
    "nvidia/nemotron-mini-4b-instruct": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    "mistralai/mistral-nemotron": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    "minimaxai/minimax-m3": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    "poolside/laguna-xs-2.1": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    "meta/llama-3.1-8b-instruct": {"input": 0.0, "output": 0.0, "provider": "nvidia"},
    # ===== Moonshot AI (Kimi) =====
    # NOT FIRST-PARTY VERIFIED, and not covered by PRICING_AS_OF. Read from
    # platform.kimi.ai/docs/models.md on 2026-08-31 and never exercised: Moonshot
    # requires a $1 minimum top-up and no key was purchased, so every figure here is
    # read rather than called. The 2026-09-06 sweep corroborated two of the four
    # through Alibaba's resale listing - kimi-k3 at 3.00 / 15.00 and kimi-k2.7-code
    # at 0.95 / 4.00, both matching - which is corroboration through a reseller, not
    # verification against Moonshot.
    #
    # NO `cached_input` ON ANY ROW, deliberately - and not because Moonshot has
    # no cache rate. It publishes one per model. The chat API documents `usage`
    # as four FLAT fields (prompt_tokens, completion_tokens, total_tokens,
    # cached_tokens) with no `prompt_tokens_details`, and
    # `OpenAIProvider.complete()` reads cached_tokens ONLY from inside
    # `prompt_tokens_details`. Against the documented shape a registered rate
    # could never fire, so these would be four dead constants. Cached tokens
    # therefore bill at the full input rate via the `calculate_cost` fallback -
    # an over-report against a real cache hit, which is the safe direction and
    # matches the Groq and OpenRouter rows. It no longer matches Mistral: those four
    # rows carried no cached rate for the same reason until 2026-09-06, when the
    # published rates were added. Add the rates only once a
    # live call shows a nested shape; `tests/test_moonshot_provider.py` pins
    # what the client extracts from each shape, so a wrong assumption fails
    # loudly there rather than as a wrong cost figure.
    #
    # All four fix temperature (and top_p, n, presence_penalty,
    # frequency_penalty); passing another value errors. Flagged from the
    # parameter reference, not from a measured 400 - see
    # `test_temperature_predicate.py`.
    #
    # kimi-k3 always reasons: reasoning_effort defaults to "max" and
    # max_completion_tokens to 131072, and it cannot be turned off. The output
    # rate below is what that default is priced against.
    "kimi-k3": {
        "input": 3.00,
        "output": 15.00,
        "provider": "moonshot",
        "rejects_sampling_params": True,
    },
    "kimi-k2.7-code": {
        "input": 0.95,
        "output": 4.00,
        "provider": "moonshot",
        "rejects_sampling_params": True,
    },
    # Exactly double kimi-k2.7-code on both columns. That is Moonshot's
    # published relationship - the same model on a faster serving route - not a
    # copied row or a typo.
    "kimi-k2.7-code-highspeed": {
        "input": 1.90,
        "output": 8.00,
        "provider": "moonshot",
        "rejects_sampling_params": True,
    },
    # Shares kimi-k2.7-code's input and output exactly; the two differ only in
    # the cache-hit rate, which is not registered here. Thinking can be disabled
    # through `extra_body`, which also changes the fixed temperature - not taken:
    # the rate stored is the thinking rate, as the DashScope rows do.
    "kimi-k2.6": {
        "input": 0.95,
        "output": 4.00,
        "provider": "moonshot",
        "rejects_sampling_params": True,
    },
    # ===== Local =====
    # Wildcard entry. Any model with `local/` prefix resolves here and costs $0.
    "local/*": {"input": 0.0, "output": 0.0, "provider": "local", "is_local": True},
}


def is_local_model(model: str) -> bool:
    """Return True for any model with the `local/` prefix."""
    return model.startswith("local/")


def rejects_sampling_params(model: str) -> bool:
    """True if this model 400s when temperature is sent at a non-default value.

    Callers must pass the ROUTING id (e.g. `local/gpt-5`), not the wire id a
    provider derives from it. The local short-circuit below is the structural
    backstop for that: local servers (Ollama, LM Studio, vLLM, llama.cpp) all
    accept temperature, and stripping it would remove real user control.

    Absent means SEND. Only models measured to reject the parameter carry the
    flag; anything not in PRICING - local ids and unregistered ids -
    falls through to False and keeps receiving temperature.
    """
    if is_local_model(model):
        return False
    return bool(PRICING.get(model, {}).get("rejects_sampling_params", False))


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """Return the USD cost for a single completion.

    Cached input tokens use the discounted `cached_input` rate if the model's
    pricing entry includes one; otherwise they fall back to the normal input
    rate. Local models always cost $0.
    """
    if is_local_model(model):
        return 0.0

    pricing = PRICING.get(model)
    if pricing is None:
        raise UnknownModelError(
            f"Unknown model: {model}. Run `cli-modelarium list-models` to see supported models."
        )

    cached_tokens = max(0, min(cached_tokens, input_tokens))
    non_cached = input_tokens - cached_tokens

    cost = (non_cached / 1_000_000) * float(pricing["input"])

    if cached_tokens > 0:
        cached_rate = pricing.get("cached_input", pricing["input"])
        cost += (cached_tokens / 1_000_000) * float(cached_rate)

    cost += (output_tokens / 1_000_000) * float(pricing["output"])

    return cost


def pricing_freshness_note() -> str:
    """Return the standard pricing-freshness disclaimer for user-facing output."""
    return f"Note: Pricing data as of {PRICING_AS_OF}. Verify current pricing at provider websites."
