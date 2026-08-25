"""Model registry: maps model IDs to providers and defines group shortcuts."""

from __future__ import annotations

from cli_modelarium.exceptions import RetiredModelError, UnknownModelError
from cli_modelarium.pricing import PRICING, RETIRED_MODELS, is_local_model

# Group shortcuts let users write `--models all-premium` instead of listing
# eight model IDs. Static groups expand unconditionally, so a group spanning N
# providers needs all N keys and aborts on the first one missing. `all` and
# `all-local` are the exception; `_resolve_dynamic_groups` resolves those.
MODEL_GROUPS: dict[str, list[str]] = {
    "all-flagship": [
        "gpt-5.6-sol",
        "claude-opus-5",
        "gemini-3.1-pro-preview",
        "grok-4.6",
        "deepseek-v4-pro",
        "mistral-large-latest",
        "qwen3.8-max",
        "glm-5.2",
    ],
    "all-budget": [
        "gpt-5.4-nano",
        "claude-haiku-4-5",
        "gemini-3.1-flash-lite",
        "grok-4.20-0309-non-reasoning",
        "deepseek-v4-flash",
        "mistral-small-latest",
        "qwen3.7-plus",
        "glm-4.5-air",
    ],
    "all-reasoning": [
        "o3",
        "o4-mini",
        "deepseek-v4-pro",
        "magistral-medium-latest",
        "magistral-small-latest",
        "glm-5.2",
    ],
    "all-cheap": [
        "gpt-4o-mini",
        "claude-haiku-4-5",
        "gemini-2.5-flash-lite",
        "deepseek-v4-flash",
        "mistral-small-latest",
        "qwen-flash",
        "glm-4.7-flashx",
    ],
    # The gpt-oss models are served here by Groq, not OpenAI: the openai-provider
    # entries were removed in 0.1.5 (not callable on chat-completions), and these
    # Groq-served equivalents are the working route. Note this group now needs
    # GROQ_API_KEY for those two slots, where it previously used OPENAI_API_KEY.
    "all-open-weight": [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-safeguard-20b",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ],
    # Resolved dynamically at call time against the user's configured providers
    # and local models. Listed here so `is_group_name()` recognizes them.
    "all-local": [],
    "all": [],
}

# `all-premium` is the SAME list object as `all-flagship`, not a copy of it.
# They were two independent literals with identical contents, so every
# membership edit had to be made twice and nothing caught a miss.
#
# `all-flagship` is the canonical name: the group means each provider's top
# model, not a price tier - deepseek-v4-pro is DeepSeek's flagship at 0.435
# input, which nobody would call premium. `all-premium` keeps working for
# anyone who types it.
#
# The value must be the list, never the string "all-flagship". `expand_group`
# does `list(MODEL_GROUPS.get(group, []))`, and `list()` on a string iterates
# characters - an alias by string yields twelve one-character model ids and
# fails with "Unknown model: a", which points nowhere near the cause.
MODEL_GROUPS["all-premium"] = MODEL_GROUPS["all-flagship"]

# Group names that need dynamic resolution by the caller (not just lookup).
DYNAMIC_GROUPS = frozenset({"all-local", "all"})


def get_provider_for_model(model: str) -> str:
    """Return the provider name for a model ID.

    Raises RetiredModelError if the provider retired the model, and
    UnknownModelError if it is not in the registry at all.

    This is the single chokepoint for model resolution - every call site
    (streaming, batch, judge validation) routes through it before any request
    is constructed, so the retirement check here covers every path that would
    otherwise reach a provider. It errors; it never substitutes the
    replacement.
    """
    if is_local_model(model):
        return "local"
    retired = RETIRED_MODELS.get(model)
    if retired is not None:
        replacement, retired_on = retired
        raise RetiredModelError(model, replacement, retired_on)
    pricing = PRICING.get(model)
    if pricing is None:
        raise UnknownModelError(
            f"Unknown model: {model}. Run `cli-modelarium list-models` to see supported models."
        )
    return str(pricing["provider"])


def list_models_for_provider(provider: str) -> list[str]:
    """Return all concrete model IDs registered for a provider, sorted alphabetically."""
    return sorted(
        model
        for model, p in PRICING.items()
        if p.get("provider") == provider and not model.endswith("/*")
    )


def all_known_providers() -> list[str]:
    """Return all unique provider names present in the pricing registry, sorted."""
    providers = {str(p["provider"]) for p in PRICING.values()}
    return sorted(providers)


def is_group_name(name: str) -> bool:
    """Return True if `name` is a registered model group shortcut."""
    return name in MODEL_GROUPS


def expand_group(group: str) -> list[str]:
    """Expand a group name to its constituent model IDs.

    Dynamic groups (`all-local`, `all`) return an empty list - the caller is
    expected to populate them with configured models.
    """
    return list(MODEL_GROUPS.get(group, []))


def parse_models_arg(models_arg: str) -> list[str]:
    """Parse a `--models` CLI value into a flat list of model IDs.

    Accepts a comma-separated string mixing concrete model IDs and group names.
    Groups are expanded in place. Dynamic groups are returned as-is for the
    caller to resolve against runtime context.
    """
    result: list[str] = []
    for token in (t.strip() for t in models_arg.split(",")):
        if not token:
            continue
        if is_group_name(token):
            expanded = expand_group(token)
            if not expanded and token in DYNAMIC_GROUPS:
                result.append(token)
            else:
                result.extend(expanded)
        else:
            result.append(token)
    return result
