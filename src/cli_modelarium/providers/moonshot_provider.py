"""Moonshot AI (Kimi) provider - uses the OpenAI SDK with a different base URL.

Four Kimi models route here. Registered from Moonshot's published documentation
(platform.kimi.ai, read 2026-08-31) and NOT exercised against the live API -
Moonshot requires a $1 minimum top-up and no key was purchased. Everything the
base class does - streaming, TTFT, `stream_options` usage on the final event,
error translation, redaction, retry - is inherited unchanged, so the shape risk
is the same as any other OpenAI-compatible subclass. What is unverified is the
data on the wire.

No `cached_input` is registered for any of the four, and the reason is a
property of the wire format rather than of this class. The `# ===== Moonshot
AI (Kimi) =====` block in `pricing.py` carries the full account, beside the
rows it justifies; `tests/test_moonshot_provider.py` pins what the client
extracts from each candidate `usage` shape.

One thing reading the documentation cannot settle: whether `completion_tokens`
includes reasoning tokens. These models always reason, so if it excludes them
every Kimi cost is understated - the failure `google_provider.py` documents for
Gemini, whose docstring names this as the open case.
"""

from __future__ import annotations

from cli_modelarium.providers.openai_provider import OpenAIProvider


class MoonshotProvider(OpenAIProvider):
    """Kimi models via Moonshot's OpenAI-compatible endpoint at api.moonshot.ai."""

    name: str = "moonshot"
    BASE_URL: str = "https://api.moonshot.ai/v1"

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key=api_key, base_url=self.BASE_URL)
