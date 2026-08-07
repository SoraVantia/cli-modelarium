"""Pricing data and cost calculation for all supported models.

Pricing is per 1M tokens, in USD. Verified July 29, 2026 from each provider's
official documentation. LLM pricing changes frequently - re-verify against
the provider's pricing page before relying on these values for production
budgeting.

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
# For models tiered by input size (OpenAI, Gemini, and Qwen flagships), the entry /
# short-context tier is stored. `cached_input` = the provider's cache-read / implicit-cache
# rate (not cache-write/creation). DeepSeek rates are standard-hours (not off-peak).
# Qwen flagship rates are list price (the time-limited promo is NOT used).
# Verified against first-party provider pages on the PRICING_AS_OF date.
PRICING_AS_OF = "2026-07-29"

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
    # Verified 2026-07-29.
    # The gpt-5.6 line is the exception: prices, chat-completions reachability
    # and the temperature rejection were verified 2026-08-07 by live call, one
    # day after the block date above. gpt-5.6-terra is OpenAI's named
    # replacement for o4-mini, which shuts down 2026-10-23.
    "gpt-5.6-sol": {
        "input": 5.00,
        "output": 30.00,
        "cached_input": 0.50,
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
    # Verified 2026-07-29.
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
    # List price, per this registry's store-list-not-promo policy. Anthropic is
    # running introductory pricing of 2.00 / 10.00 (cached 0.20) through
    # 2026-08-31; list pricing below takes effect 2026-09-01.
    "claude-sonnet-5": {
        "input": 3.00,
        "output": 15.00,
        "cached_input": 0.30,
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
    # Verified 2026-07-29.
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
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50, "cached_input": 0.15, "provider": "google"},
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
    # Verified 2026-07-29.
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
    # Verified 2026-07-29.
    "deepseek-v4-pro": {
        "input": 0.435,
        "output": 0.87,
        "cached_input": 0.003625,
        "provider": "deepseek",
    },
    "deepseek-v4-flash": {
        "input": 0.14,
        "output": 0.28,
        "cached_input": 0.0028,
        "provider": "deepseek",
    },
    # ===== Mistral =====
    # Verified 2026-07-29.
    "mistral-medium-latest": {"input": 1.50, "output": 7.50, "provider": "mistral"},
    "mistral-large-latest": {"input": 0.50, "output": 1.50, "provider": "mistral"},
    "mistral-small-latest": {"input": 0.15, "output": 0.60, "provider": "mistral"},
    "codestral-latest": {"input": 0.30, "output": 0.90, "provider": "mistral"},
    "magistral-medium-latest": {"input": 2.00, "output": 5.00, "provider": "mistral"},
    "magistral-small-latest": {"input": 0.50, "output": 1.50, "provider": "mistral"},
    # ===== Groq =====
    # Verified 2026-07-29.
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
    # Verified 2026-07-29.
    "qwen3.7-max": {"input": 2.50, "output": 7.50, "cached_input": 0.50, "provider": "dashscope"},
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
    # Verified against Z.AI's pricing page (docs.z.ai), 2026-06-22.
    # That date is older than PRICING_AS_OF deliberately: this block was NOT re-checked
    # in the 2026-07-29 pass, and its 14 entries have not changed since the date above.
    # The mismatch records what was actually checked and when - it is accurate, not a
    # comment someone forgot to update.
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
