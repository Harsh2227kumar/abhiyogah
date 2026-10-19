"""Typed exceptions raised by perception."""

__all__ = [
    "GatewayConfigError",
    "LlmCallError",
    "LlmOutputError",
    "PerceptionError",
    "RegionNotAllowedError",
]


class PerceptionError(Exception):
    """Base class for every perception error."""


class GatewayConfigError(PerceptionError):
    """The LLM gateway configuration is incomplete or inconsistent."""


class RegionNotAllowedError(GatewayConfigError):
    """The configured model region is outside India and was not explicitly allowed."""


class LlmCallError(PerceptionError):
    """The model provider could not be reached or returned an error."""


class LlmOutputError(PerceptionError):
    """The model's output did not match the requested schema."""
