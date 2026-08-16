"""NVIDIA NIM provider - uses the OpenAI SDK with a different base URL.

Nine NIM models route here, all registered in `PRICING` at `0.0` because NVIDIA
publishes no per-token rate for the hosted endpoint. The zeros are not prices,
and `--max-cost` and `cost_under` give no protection on this provider; the
`PRICING` block for those rows carries the full explanation.

NVIDIA's hosted endpoint is OpenAI-compatible - streaming, `stream_options`
usage on the final event, and `temperature` all behave as the base class
expects, so there is no `_extra_create_kwargs()` override. A
thinking-suppression parameter exists for some NIM models and is ignored by
others, which makes it per-model rather than per-provider; it does not belong
on the class.
"""

from __future__ import annotations

from cli_modelarium.providers.openai_provider import OpenAIProvider


class NVIDIAProvider(OpenAIProvider):
    """NVIDIA NIM models via the OpenAI-compatible endpoint at integrate.api.nvidia.com."""

    name: str = "nvidia"
    BASE_URL: str = "https://integrate.api.nvidia.com/v1"

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key=api_key, base_url=self.BASE_URL)
