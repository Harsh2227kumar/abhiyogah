"""The LLM gateway: one interface over every model provider perception may call.

Perception never talks to a provider directly. It builds an ``LlmRequest`` (prompt ID, prompt
version, masked text, the JSON schema the answer must follow) and hands it to an ``LlmGateway``.
The answer comes back with the model identifier and prompt version, so every fact derived from it
carries its provenance (CLAUDE.md hard rule 4).

Adapters (``perception.adapters``):

- ``FakeModel``: deterministic, no network; the default in tests.
- ``AnthropicAdapter``: the Anthropic SDK client (loaded lazily, never a hard dependency).
- ``BedrockAdapter``: an AWS Bedrock runtime client, normally in ``ap-south-1`` (Mumbai).
- ``OpenAICompatibleAdapter``: any ``/chat/completions`` endpoint, for example self-hosted vLLM,
  Ollama or Sarvam AI (``Provider.SARVAM`` fills in Sarvam's endpoint and key header).

Provider, model and region come from configuration (``GatewayConfig.from_env``). A region outside
India is refused unless ``allow_non_india_region`` is set explicitly. ``in-attested`` is for a
hosted provider (e.g. Sarvam AI) that has confirmed to the owner that it processes data only in
India; setting it is the owner's call, never a default. Model identifiers are never
written into code: they come only from configuration.
"""

import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from abhiyogah.perception.errors import GatewayConfigError, RegionNotAllowedError

__all__ = [
    "INDIA_REGIONS",
    "GatewayConfig",
    "LlmGateway",
    "LlmRequest",
    "LlmResponse",
    "Provider",
    "check_region",
]

INDIA_REGIONS: frozenset[str] = frozenset(
    {
        "ap-south-1",  # AWS Mumbai
        "ap-south-2",  # AWS Hyderabad
        "centralindia",  # Azure Pune
        "southindia",  # Azure Chennai
        "westindia",  # Azure Mumbai
        "jioindiawest",  # Azure Jamnagar
        "jioindiacentral",  # Azure Nagpur
        "asia-south1",  # Google Cloud Mumbai
        "asia-south2",  # Google Cloud Delhi
        "on-prem",  # the bank's own data centre (self-hosted model)
        "in-attested",  # a hosted provider the owner has confirmed processes data only in India
    }
)
"""Regions whose data stays in India. Anything else needs ``allow_non_india_region``."""


class Provider(StrEnum):
    """Which adapter the gateway uses. ``NONE`` means rules-only: no model is called."""

    NONE = "NONE"
    FAKE = "FAKE"
    ANTHROPIC = "ANTHROPIC"
    BEDROCK = "BEDROCK"
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"
    SARVAM = "SARVAM"
    """Sarvam AI's OpenAI-style API; endpoint defaults to ``https://api.sarvam.ai/v1``."""


class GatewayConfig(BaseModel):
    """Which provider, model and region to use. Read once at start-up."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider = Provider.NONE
    model: str | None = Field(default=None, description="Model identifier, from configuration.")
    region: str | None = None
    allow_non_india_region: bool = False
    endpoint: str | None = Field(default=None, description="Base URL (OpenAI-compatible only).")
    api_key: str | None = Field(default=None, repr=False)
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_output_tokens: int = Field(default=2048, gt=0)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "GatewayConfig":
        """Read ``LLM_PROVIDER``, ``LLM_MODEL``, ``LLM_REGION``, ``LLM_ENDPOINT``, ``LLM_API_KEY``.

        ``LLM_ALLOW_NON_INDIA_REGION=true`` lifts the India-only check. An empty provider means
        rules-only (``Provider.NONE``).
        """
        raw = env.get("LLM_PROVIDER", "").strip().upper() or Provider.NONE.value
        try:
            provider = Provider(raw)
        except ValueError as exc:
            raise GatewayConfigError(f"unknown LLM_PROVIDER {raw!r}") from exc
        return cls(
            provider=provider,
            model=env.get("LLM_MODEL") or None,
            region=env.get("LLM_REGION") or None,
            allow_non_india_region=env.get("LLM_ALLOW_NON_INDIA_REGION", "").lower()
            in {"1", "true", "yes"},
            endpoint=env.get("LLM_ENDPOINT") or None,
            api_key=env.get("LLM_API_KEY") or None,
        )


def check_region(config: GatewayConfig) -> None:
    """Refuse a provider whose region is unknown or outside India, unless explicitly allowed."""
    if config.provider in {Provider.NONE, Provider.FAKE}:
        return
    if not config.model:
        raise GatewayConfigError(f"{config.provider} needs LLM_MODEL")
    if config.allow_non_india_region:
        return
    if config.region is None:
        raise RegionNotAllowedError(
            f"{config.provider} has no LLM_REGION; set an India region or allow non-India regions"
        )
    if config.region not in INDIA_REGIONS:
        raise RegionNotAllowedError(
            f"region {config.region!r} is outside India; set LLM_ALLOW_NON_INDIA_REGION to allow it"
        )


class LlmRequest(BaseModel):
    """One model call. ``text`` must already be PII-masked (``perception.pii``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_id: str = Field(min_length=1, description="Which prompt, e.g. 'triage'.")
    prompt_version: str = Field(min_length=1, description="Version of the prompt text.")
    system: str = Field(description="Instructions for the model.")
    text: str = Field(description="The masked input text.")
    output_schema: dict[str, JsonValue] = Field(description="JSON schema the answer must match.")


class LlmResponse(BaseModel):
    """A model's answer, with what is needed for provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(min_length=1)
    prompt_id: str
    prompt_version: str
    output: dict[str, JsonValue]


@runtime_checkable
class LlmGateway(Protocol):
    """Anything that answers an ``LlmRequest`` with schema-shaped JSON."""

    @property
    def model(self) -> str:
        """The model identifier recorded in provenance."""
        ...

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Send the request and return the parsed JSON answer."""
        ...
