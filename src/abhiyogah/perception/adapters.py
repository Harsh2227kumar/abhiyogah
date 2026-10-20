"""LLM gateway adapters: a deterministic fake, Anthropic, AWS Bedrock and OpenAI-compatible.

Provider SDKs are optional. Adapters take an already-built client that matches a small protocol,
so tests inject fakes and the package never imports an SDK at module load. ``build_gateway`` builds
the real client lazily from ``GatewayConfig`` after the India-region check.
"""

import importlib
import json
import re
from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast

import httpx
from pydantic import JsonValue

from abhiyogah.perception.errors import GatewayConfigError, LlmCallError, LlmOutputError
from abhiyogah.perception.gateway import (
    GatewayConfig,
    LlmGateway,
    LlmRequest,
    LlmResponse,
    Provider,
    check_region,
)

__all__ = [
    "AnthropicAdapter",
    "AnthropicClient",
    "BedrockAdapter",
    "BedrockClient",
    "FakeModel",
    "OpenAICompatibleAdapter",
    "Responder",
    "build_gateway",
    "parse_json_object",
]

Responder = Callable[[LlmRequest], Mapping[str, JsonValue]]
"""Produces the fake model's answer for one request."""

FAKE_MODEL_ID = "fake-deterministic"
SARVAM_ENDPOINT = "https://api.sarvam.ai/v1"
SARVAM_REASONING_EFFORT = "low"
"""Sarvam reasons at ``medium`` by default, and reasoning tokens count against ``max_tokens``;
triage and extraction need little reasoning, so the answer is not crowded out."""


_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_json_object(text: str) -> dict[str, JsonValue]:
    """Parse a model's text answer as one JSON object, or raise ``LlmOutputError``.

    Without native schema-constrained output, some models wrap the object in a code fence or put
    ``<think>`` reasoning before it; both are stripped. The object is still schema-validated by
    the caller, so this only finds it, never repairs it.
    """
    cleaned = _FENCE.sub("", _THINKING.sub("", text).strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LlmOutputError(f"model answer is not JSON: {exc.msg}") from exc
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as inner:
            raise LlmOutputError(f"model answer is not JSON: {inner.msg}") from inner
    if not isinstance(value, dict):
        raise LlmOutputError("model answer is not a JSON object")
    return cast(dict[str, JsonValue], value)


def _json_instructions(request: LlmRequest) -> str:
    """System text plus the schema, for providers without native schema-constrained output."""
    schema = json.dumps(request.output_schema, sort_keys=True)
    return (
        f"{request.system}\n\nAnswer with one JSON object and nothing else. "
        f"It must match this JSON schema:\n{schema}"
    )


class FakeModel:
    """Deterministic model for tests and demos: answers each prompt ID with a fixed function."""

    def __init__(
        self, responders: Mapping[str, Responder] | None = None, model: str = FAKE_MODEL_ID
    ) -> None:
        """Answer requests for each prompt ID with its responder; unknown prompt IDs fail."""
        self._responders = dict(responders or {})
        self._model = model
        self.calls: list[LlmRequest] = []

    @property
    def model(self) -> str:
        """The fake model's identifier."""
        return self._model

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Record the request and answer it with the prompt's responder."""
        self.calls.append(request)
        responder = self._responders.get(request.prompt_id)
        if responder is None:
            raise LlmCallError(f"fake model has no responder for prompt {request.prompt_id!r}")
        return LlmResponse(
            model=self._model,
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            output=dict(responder(request)),
        )


class _AnthropicMessages(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """Create a message (``anthropic.Anthropic().messages.create``)."""
        ...


class AnthropicClient(Protocol):
    """The part of the Anthropic SDK client the adapter uses."""

    @property
    def messages(self) -> _AnthropicMessages:
        """The Messages resource."""
        ...


class AnthropicAdapter:
    """Calls the Anthropic Messages API with structured (JSON-schema) output."""

    def __init__(self, client: AnthropicClient, model: str, max_output_tokens: int = 2048) -> None:
        """Use ``client`` (an ``anthropic.Anthropic`` instance) with the configured model."""
        self._client = client
        self._model = model
        self._max_tokens = max_output_tokens

    @property
    def model(self) -> str:
        """The configured model identifier."""
        return self._model

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Send one message whose answer is constrained to ``request.output_schema``."""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.text}],
                output_config={"format": {"type": "json_schema", "schema": request.output_schema}},
            )
        except Exception as exc:  # SDK error classes are not importable here
            raise LlmCallError(f"Anthropic call failed: {type(exc).__name__}") from exc
        if getattr(response, "stop_reason", None) == "refusal":
            raise LlmCallError("model declined the request")
        texts = [b.text for b in getattr(response, "content", []) if b.type == "text"]
        if not texts:
            raise LlmOutputError("model answer has no text block")
        return LlmResponse(
            model=str(getattr(response, "model", None) or self._model),
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            output=parse_json_object("".join(texts)),
        )


class BedrockClient(Protocol):
    """The part of a boto3 ``bedrock-runtime`` client the adapter uses."""

    def converse(self, **kwargs: Any) -> Mapping[str, Any]:
        """Call the Bedrock Converse API."""
        ...


class BedrockAdapter:
    """Calls a model on AWS Bedrock through the Converse API."""

    def __init__(self, client: BedrockClient, model: str, max_output_tokens: int = 2048) -> None:
        """Use ``client`` (a boto3 ``bedrock-runtime`` client) with the configured model ID."""
        self._client = client
        self._model = model
        self._max_tokens = max_output_tokens

    @property
    def model(self) -> str:
        """The configured Bedrock model ID."""
        return self._model

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Send one Converse request and parse the JSON answer."""
        try:
            response = self._client.converse(
                modelId=self._model,
                system=[{"text": _json_instructions(request)}],
                messages=[{"role": "user", "content": [{"text": request.text}]}],
                inferenceConfig={"maxTokens": self._max_tokens},
            )
        except Exception as exc:  # botocore error classes are not importable here
            raise LlmCallError(f"Bedrock call failed: {type(exc).__name__}") from exc
        try:
            blocks = response["output"]["message"]["content"]
            text = "".join(b["text"] for b in blocks if "text" in b)
        except (KeyError, TypeError) as exc:
            raise LlmOutputError("unexpected Bedrock response shape") from exc
        return LlmResponse(
            model=self._model,
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            output=parse_json_object(text),
        )


class OpenAICompatibleAdapter:
    """Calls an OpenAI-compatible ``/chat/completions`` endpoint (vLLM, Ollama, Sarvam, ...).

    It asks for a JSON-schema ``response_format``. If the endpoint rejects that with HTTP 400 or
    422, the adapter retries once without it and keeps doing so: the schema is also in the system
    prompt, and the answer is schema-validated either way. ``reasoning_effort``, when given, is
    sent as is; ``"none"`` sends null, which turns reasoning off on endpoints that support it.
    """

    def __init__(
        self,
        client: httpx.Client,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        max_output_tokens: int = 2048,
        key_headers: tuple[str, ...] = ("Authorization",),
        reasoning_effort: str | None = None,
    ) -> None:
        """POST to ``<endpoint>/chat/completions``, sending ``api_key`` in each of ``key_headers``.

        ``Authorization`` carries ``Bearer <key>``; any other header carries the bare key.
        """
        self._client = client
        self._url = endpoint.rstrip("/") + "/chat/completions"
        self._model = model
        self._max_tokens = max_output_tokens
        self._headers = {
            h: (f"Bearer {api_key}" if h == "Authorization" else api_key)
            for h in key_headers
            if api_key
        }
        self._reasoning_effort = reasoning_effort
        self._native_schema = True

    @property
    def model(self) -> str:
        """The configured model identifier."""
        return self._model

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        try:
            return self._client.post(self._url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise LlmCallError(f"OpenAI-compatible call failed: {type(exc).__name__}") from exc

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Send one chat completion and parse the JSON answer."""
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": "system", "content": _json_instructions(request)},
                {"role": "user", "content": request.text},
            ],
        }
        if self._reasoning_effort is not None:
            effort = None if self._reasoning_effort == "none" else self._reasoning_effort
            body["reasoning_effort"] = effort
        reply = None
        if self._native_schema:
            schema_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.prompt_id,
                    "schema": request.output_schema,
                    "strict": True,
                },
            }
            reply = self._post({**body, "response_format": schema_format})
            if reply.status_code in {400, 422}:
                self._native_schema = False
                reply = None
        if reply is None:
            reply = self._post(body)
        try:
            reply.raise_for_status()
            data = reply.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LlmCallError(f"OpenAI-compatible call failed: {type(exc).__name__}") from exc
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmOutputError("unexpected chat-completions response shape") from exc
        if not isinstance(text, str):
            if choice.get("finish_reason") == "length":
                raise LlmOutputError(
                    "answer cut off at max_tokens before any content; raise "
                    "LLM_MAX_OUTPUT_TOKENS or lower LLM_REASONING_EFFORT"
                )
            raise LlmOutputError("chat-completions content is not text")
        return LlmResponse(
            model=str(data.get("model") or self._model),
            prompt_id=request.prompt_id,
            prompt_version=request.prompt_version,
            output=parse_json_object(text),
        )


def _model(config: GatewayConfig) -> str:
    """The configured model identifier; ``check_region`` already refused a missing one."""
    if not config.model:
        raise GatewayConfigError(f"{config.provider} needs LLM_MODEL")
    return config.model


def build_gateway(
    config: GatewayConfig,
    *,
    fake_responders: Mapping[str, Responder] | None = None,
    anthropic_client: AnthropicClient | None = None,
    bedrock_client: BedrockClient | None = None,
    http_client: httpx.Client | None = None,
) -> LlmGateway | None:
    """Build the configured gateway, or ``None`` for rules-only. Checks the region first."""
    check_region(config)
    if config.reasoning_effort is not None and config.provider not in {
        Provider.OPENAI_COMPATIBLE,
        Provider.SARVAM,
    }:
        raise GatewayConfigError(
            "LLM_REASONING_EFFORT is only sent by OpenAI-compatible providers, "
            f"not {config.provider}"
        )
    match config.provider:
        case Provider.NONE:
            return None
        case Provider.FAKE:
            return FakeModel(fake_responders, model=config.model or FAKE_MODEL_ID)
        case Provider.ANTHROPIC:
            if anthropic_client is None:
                sdk = importlib.import_module("anthropic")
                anthropic_client = cast(
                    AnthropicClient,
                    sdk.Anthropic(api_key=config.api_key, timeout=config.timeout_seconds),
                )
            return AnthropicAdapter(anthropic_client, _model(config), config.max_output_tokens)
        case Provider.BEDROCK:
            if bedrock_client is None:
                boto3 = importlib.import_module("boto3")
                bedrock_client = cast(
                    BedrockClient, boto3.client("bedrock-runtime", region_name=config.region)
                )
            return BedrockAdapter(bedrock_client, _model(config), config.max_output_tokens)
        case Provider.OPENAI_COMPATIBLE:
            if not config.endpoint:
                raise GatewayConfigError("OPENAI_COMPATIBLE needs LLM_ENDPOINT")
            client = http_client or httpx.Client(timeout=config.timeout_seconds)
            return OpenAICompatibleAdapter(
                client,
                config.endpoint,
                _model(config),
                config.api_key,
                config.max_output_tokens,
                reasoning_effort=config.reasoning_effort,
            )
        case Provider.SARVAM:
            client = http_client or httpx.Client(timeout=config.timeout_seconds)
            return OpenAICompatibleAdapter(
                client,
                config.endpoint or SARVAM_ENDPOINT,
                _model(config),
                config.api_key,
                config.max_output_tokens,
                # Sarvam's SDK sends api-subscription-key; its examples also use a Bearer token.
                key_headers=("api-subscription-key", "Authorization"),
                reasoning_effort=config.reasoning_effort or SARVAM_REASONING_EFFORT,
            )
