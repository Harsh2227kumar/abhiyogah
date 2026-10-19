"""LLM gateway: config, India-region check and every adapter, with no network calls."""

import json
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import JsonValue

from abhiyogah.perception.adapters import (
    AnthropicAdapter,
    BedrockAdapter,
    FakeModel,
    OpenAICompatibleAdapter,
    build_gateway,
    parse_json_object,
)
from abhiyogah.perception.errors import (
    GatewayConfigError,
    LlmCallError,
    LlmOutputError,
    RegionNotAllowedError,
)
from abhiyogah.perception.gateway import (
    GatewayConfig,
    LlmGateway,
    LlmRequest,
    Provider,
    check_region,
)

SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {"label": {"type": "string"}},
    "required": ["label"],
    "additionalProperties": False,
}
REQUEST = LlmRequest(
    prompt_id="triage",
    prompt_version="v1",
    system="Classify.",
    text="Synthetic text about <AMOUNT_1>.",
    output_schema=SCHEMA,
)


def test_config_from_env_defaults_to_rules_only() -> None:
    assert GatewayConfig.from_env({}).provider is Provider.NONE


def test_config_from_env_reads_every_setting() -> None:
    config = GatewayConfig.from_env(
        {
            "LLM_PROVIDER": "bedrock",
            "LLM_MODEL": "test-model",
            "LLM_REGION": "ap-south-1",
            "LLM_ALLOW_NON_INDIA_REGION": "true",
        }
    )
    assert config.provider is Provider.BEDROCK
    assert config.model == "test-model"
    assert config.region == "ap-south-1"
    assert config.allow_non_india_region


def test_config_from_env_rejects_unknown_provider() -> None:
    with pytest.raises(GatewayConfigError):
        GatewayConfig.from_env({"LLM_PROVIDER": "mystery"})


def test_api_key_is_not_in_repr() -> None:
    config = GatewayConfig(provider=Provider.ANTHROPIC, api_key="placeholder-key")
    assert "placeholder-key" not in repr(config)


@pytest.mark.parametrize("region", ["ap-south-1", "ap-south-2", "centralindia", "on-prem"])
def test_india_regions_pass(region: str) -> None:
    check_region(GatewayConfig(provider=Provider.BEDROCK, model="m", region=region))


@pytest.mark.parametrize("region", ["us-east-1", "eu-west-1", None])
def test_non_india_or_missing_region_is_refused(region: str | None) -> None:
    with pytest.raises(RegionNotAllowedError):
        check_region(GatewayConfig(provider=Provider.BEDROCK, model="m", region=region))


def test_non_india_region_passes_when_explicitly_allowed() -> None:
    check_region(
        GatewayConfig(
            provider=Provider.ANTHROPIC, model="m", region="us", allow_non_india_region=True
        )
    )


def test_real_provider_needs_a_model() -> None:
    with pytest.raises(GatewayConfigError):
        check_region(GatewayConfig(provider=Provider.BEDROCK, region="ap-south-1"))


def test_build_gateway_none_is_rules_only() -> None:
    assert build_gateway(GatewayConfig()) is None


def test_build_gateway_refuses_non_india_before_building_a_client() -> None:
    with pytest.raises(RegionNotAllowedError):
        build_gateway(GatewayConfig(provider=Provider.ANTHROPIC, model="m"))


def test_fake_model_is_deterministic_and_records_calls() -> None:
    fake = FakeModel({"triage": lambda r: {"label": r.text[:9]}})
    first = fake.complete(REQUEST)
    assert first == fake.complete(REQUEST)
    assert first.output == {"label": "Synthetic"}
    assert first.model == fake.model
    assert first.prompt_version == "v1"
    assert fake.calls == [REQUEST, REQUEST]
    assert isinstance(fake, LlmGateway)


def test_fake_model_without_responder_fails() -> None:
    with pytest.raises(LlmCallError):
        FakeModel().complete(REQUEST)


def test_build_gateway_fake() -> None:
    gateway = build_gateway(
        GatewayConfig(provider=Provider.FAKE), fake_responders={"triage": lambda r: {"label": "x"}}
    )
    assert gateway is not None
    assert gateway.complete(REQUEST).output == {"label": "x"}


class _FakeAnthropicMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _FakeAnthropic:
    def __init__(self, response: Any) -> None:
        self.messages = _FakeAnthropicMessages(response)


def _anthropic_response(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        model="served-model",
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
    )


def test_anthropic_adapter_sends_schema_and_parses_answer() -> None:
    client = _FakeAnthropic(_anthropic_response('{"label": "complaint"}'))
    gateway = build_gateway(
        GatewayConfig(
            provider=Provider.ANTHROPIC, model="configured-model", allow_non_india_region=True
        ),
        anthropic_client=client,
    )
    assert gateway is not None
    response = gateway.complete(REQUEST)
    assert response.output == {"label": "complaint"}
    assert response.model == "served-model"
    sent = client.messages.kwargs
    assert sent["model"] == "configured-model"
    assert sent["messages"] == [{"role": "user", "content": REQUEST.text}]
    assert sent["output_config"]["format"]["schema"] == SCHEMA


def test_anthropic_adapter_refusal_and_errors() -> None:
    with pytest.raises(LlmCallError):
        AnthropicAdapter(_FakeAnthropic(_anthropic_response("", "refusal")), "m").complete(REQUEST)
    with pytest.raises(LlmCallError):
        AnthropicAdapter(_FakeAnthropic(RuntimeError("down")), "m").complete(REQUEST)
    with pytest.raises(LlmOutputError):
        AnthropicAdapter(_FakeAnthropic(_anthropic_response("not json")), "m").complete(REQUEST)


class _FakeBedrock:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def converse(self, **kwargs: Any) -> Mapping[str, Any]:
        self.kwargs = kwargs
        return self.response


def test_bedrock_adapter() -> None:
    client = _FakeBedrock({"output": {"message": {"content": [{"text": '{"label": "q"}'}]}}})
    gateway = build_gateway(
        GatewayConfig(provider=Provider.BEDROCK, model="bedrock-model", region="ap-south-1"),
        bedrock_client=client,
    )
    assert gateway is not None
    response = gateway.complete(REQUEST)
    assert response.output == {"label": "q"}
    assert response.model == "bedrock-model"
    assert client.kwargs["modelId"] == "bedrock-model"
    assert json.dumps(SCHEMA, sort_keys=True) in client.kwargs["system"][0]["text"]


def test_bedrock_adapter_bad_shape() -> None:
    with pytest.raises(LlmOutputError):
        BedrockAdapter(_FakeBedrock({"output": {}}), "m").complete(REQUEST)


def test_openai_compatible_adapter() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"model": "vllm-model", "choices": [{"message": {"content": '{"label": "c"}'}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = build_gateway(
        GatewayConfig(
            provider=Provider.OPENAI_COMPATIBLE,
            model="vllm-model",
            region="on-prem",
            endpoint="http://llm.internal.test/v1/",
            api_key="placeholder",
        ),
        http_client=client,
    )
    assert gateway is not None
    assert gateway.complete(REQUEST).output == {"label": "c"}
    assert str(seen[0].url) == "http://llm.internal.test/v1/chat/completions"
    assert seen[0].headers["Authorization"] == "Bearer placeholder"
    body = json.loads(seen[0].content)
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA


def test_openai_compatible_adapter_http_error() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    adapter = OpenAICompatibleAdapter(client, "http://llm.internal.test", "m")
    with pytest.raises(LlmCallError):
        adapter.complete(REQUEST)


def test_openai_compatible_needs_endpoint() -> None:
    with pytest.raises(GatewayConfigError):
        build_gateway(
            GatewayConfig(provider=Provider.OPENAI_COMPATIBLE, model="m", region="on-prem")
        )


@pytest.mark.parametrize("text", ["[1]", "nope", '"s"'])
def test_parse_json_object_rejects_non_objects(text: str) -> None:
    with pytest.raises(LlmOutputError):
        parse_json_object(text)
