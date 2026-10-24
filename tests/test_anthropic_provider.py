"""Real SDK against an in-memory HTTP transport. No paid calls."""

import asyncio
import json
import logging

import pytest

httpx = pytest.importorskip("httpx2")
anthropic = pytest.importorskip("anthropic")

from hope_brain.anthropic_provider import AnthropicProvider
from hope_brain.contracts import BrainTurnRequest, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.settings import AnthropicSettings

REQUEST = BrainTurnRequest(session_id="private-session", text="private-input")
REPLY = '{"segments":[{"text":"Hello there!","emotion":"happy","intensity":0.5}]}'


@pytest.fixture(autouse=True)
def prevent_real_http(monkeypatch):
    send = httpx.AsyncClient.send

    async def guarded(client, *args, **kwargs):
        assert isinstance(client._transport, httpx.MockTransport), "Real HTTP forbidden in tests"
        return await send(client, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", guarded)


def settings(**overrides):
    return AnthropicSettings.model_validate(
        {
            "api_key": "test-secret",
            "model": "test-model",
            "turn_budget_usd": "0.01",
            "input_usd_per_million": "1",
            "output_usd_per_million": "2",
            **overrides,
        }
    )


def events(text=REPLY, stop_reason="end_turn"):
    return [
        {
            "type": "message_start",
            "message": {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "test-model",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 1},
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        *[
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": part},
            }
            for part in [text[:15], text[15:]]
        ],
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 35},
        },
        {"type": "message_stop"},
    ]


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, payload, hang=False, disconnect=False):
        self.payload = payload
        self.hang = hang
        self.disconnect = disconnect
        self.entered = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        self.entered.set()
        for event in self.payload:
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
            await asyncio.sleep(0)
        if self.disconnect:
            raise httpx.ReadError("private transport error test-secret")
        if self.hang:
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


def provider_with_transport(
    payload=None,
    *,
    config=None,
    status=200,
    hang=False,
    disconnect=False,
    input_tokens=100,
    count_hang=False,
):
    requests = []
    response_stream = ResponseStream(events() if payload is None else payload, hang, disconnect)
    count_entered = asyncio.Event()

    async def handle(request):
        requests.append(request)
        if request.url.path.endswith("count_tokens"):
            count_entered.set()
            if count_hang:
                await asyncio.Event().wait()
            return httpx.Response(200, json={"input_tokens": input_tokens})
        if status != 200:
            return httpx.Response(
                status,
                json={
                    "type": "error",
                    "error": {
                        "type": "overloaded_error",
                        "message": "private-input test-secret",
                    },
                },
            )
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=response_stream
        )

    client = anthropic.AsyncAnthropic(
        api_key="test-secret",
        max_retries=0,
        open_telemetry=False,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    return (
        AnthropicProvider(config or settings(), client=client),
        requests,
        response_stream,
        count_entered,
    )


async def collect(provider, cancel=None, request=REQUEST):
    try:
        result = [event async for event in TurnOrchestrator(provider).stream(request, cancel)]
        for event in result:
            brain_event_adapter.validate_json(brain_event_adapter.dump_json(event))
        assert [event.seq for event in result] == list(range(1, len(result) + 1))
        assert len({event.turn_id for event in result}) == 1
        assert (
            sum(
                event.type in {"turn.completed", "turn.failed", "turn.cancelled"}
                for event in result
            )
            == 1
        )
        return result
    finally:
        await provider.aclose()


def test_stream_success_and_context_boundary(caplog):
    caplog.set_level(logging.INFO, logger="hope_brain")
    provider, requests, stream, _ = provider_with_transport()
    result = asyncio.run(collect(provider))
    assert result[-1].type == "turn.completed"
    assert result[1].segment.text == "Hello there!"
    assert stream.closed
    assert len(requests) == 2
    body = json.loads(requests[1].content)
    assert body["stream"] is True
    assert body["messages"] == [{"role": "user", "content": "private-input"}]
    assert "private-input" not in body["system"]
    assert "private-session" not in requests[1].content.decode()
    assert body["max_tokens"] == 256
    assert "tools" not in body
    assert "private-input" not in caplog.text
    assert "Hello there!" not in caplog.text
    assert "test-secret" not in caplog.text
    assert '"input_tokens":100' in caplog.text
    assert '"output_tokens":35' in caplog.text
    assert '"first_text_ms"' in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        events("not-json private-input"),
        events('{"segments":[]}'),
        events(REPLY.replace('"happy"', '"angry"')),
        events(REPLY[:-1]),
        events(stop_reason="max_tokens"),
        events()[:-1],
        events(REPLY.replace('"segments":', '"seq":99,"segments":')),
        events("x" * 65_537),
        [],
    ],
)
def test_invalid_or_incomplete_stream_never_leaks_candidates(payload, caplog):
    provider, _, stream, _ = provider_with_transport(payload)
    result = asyncio.run(collect(provider))
    assert result[-1].reason == "provider_invalid"
    assert result[1].segment.text != "Hello there!"
    assert "private-input" not in caplog.text
    assert stream.closed


@pytest.mark.parametrize("status", [401, 429, 500, 529])
def test_provider_errors_are_not_retried_or_logged(status, caplog):
    provider, requests, _, _ = provider_with_transport(status=status)
    result = asyncio.run(collect(provider))
    assert result[-1].reason == "provider_error"
    assert len(requests) == 2
    assert "private-input" not in caplog.text
    assert "test-secret" not in caplog.text


def test_disconnect_closes_stream_and_fails_once():
    provider, requests, stream, _ = provider_with_transport(events()[:4], disconnect=True)
    result = asyncio.run(collect(provider))
    assert result[-1].reason == "provider_error"
    assert len(requests) == 2
    assert stream.closed


def test_budget_blocks_generation():
    provider, requests, _, _ = provider_with_transport(config=settings(turn_budget_usd="0.000001"))
    result = asyncio.run(collect(provider))
    assert result[-1].reason == "provider_budget_exceeded"
    assert len(requests) == 1
    assert requests[0].url.path.endswith("count_tokens")


def test_input_limit_prevents_even_token_count_request():
    provider, requests, _, _ = provider_with_transport()
    result = asyncio.run(
        collect(provider, request=BrainTurnRequest(session_id="test", text="x" * 16_385))
    )
    assert result[-1].reason == "provider_invalid"
    assert not requests


@pytest.mark.parametrize("during_count", [False, True])
def test_total_timeout_bounds_stream_and_preflight(during_count):
    provider, _, stream, _ = provider_with_transport(
        events()[:4], config=settings(timeout_seconds=0.1), hang=True, count_hang=during_count
    )
    result = asyncio.run(asyncio.wait_for(collect(provider), timeout=2))
    assert result[-1].reason == "provider_timeout"
    if not during_count:
        assert stream.closed


@pytest.mark.parametrize("during_count", [False, True])
def test_in_flight_cancellation_closes_request(during_count):
    async def run():
        provider, _, stream, count_entered = provider_with_transport(
            events()[:4], hang=True, count_hang=during_count
        )
        cancel = asyncio.Event()
        task = asyncio.create_task(collect(provider, cancel))
        await asyncio.wait_for((count_entered if during_count else stream.entered).wait(), 2)
        cancel.set()
        result = await asyncio.wait_for(task, 2)
        assert [event.type for event in result] == ["turn.started", "turn.cancelled"]
        if not during_count:
            assert stream.closed
        assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    asyncio.run(run())


def test_safety_policy_bypasses_all_provider_requests():
    provider, requests, _, _ = provider_with_transport()
    result = asyncio.run(
        collect(provider, request=BrainTurnRequest(session_id="test", text="I feel dizzy"))
    )
    assert result[-1].type == "turn.completed"
    assert not requests


def test_factory_disables_retries_and_untrusted_base_url(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://untrusted.invalid")
    provider = AnthropicProvider(settings())
    assert str(provider.client.base_url) == "https://api.anthropic.com"
    assert provider.client.max_retries == 0
    assert provider.client.timeout == 30
    assert logging.getLogger("anthropic").disabled
    asyncio.run(provider.aclose())


def test_unexpected_tool_content_is_rejected():
    payload = events()
    payload[1]["content_block"] = {
        "type": "tool_use",
        "id": "tool_test",
        "name": "change_goal",
        "input": {},
    }
    provider, _, stream, _ = provider_with_transport(payload)
    result = asyncio.run(collect(provider))
    assert result[-1].reason == "provider_invalid"
    assert stream.closed


@pytest.mark.parametrize("input_tokens", [-1, "private token count"])
def test_invalid_preflight_usage_cannot_reach_generation(input_tokens, caplog):
    provider, requests, _, _ = provider_with_transport(input_tokens=input_tokens)
    result = asyncio.run(collect(provider))
    assert result[-1].reason == "provider_invalid"
    assert len(requests) == 1
    assert "private token count" not in caplog.text


def test_sdk_read_timeout_has_timeout_reason():
    async def handle(request):
        raise httpx.ReadTimeout("private-input test-secret")

    client = anthropic.AsyncAnthropic(
        api_key="test-secret",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    provider = AnthropicProvider(settings(), client=client)
    result = asyncio.run(collect(provider))
    assert result[-1].reason == "provider_timeout"


@pytest.mark.parametrize(("payload", "expected_exit"), [(events(), 0), (events()[:-1], 1)])
def test_cli_live_smoke_uses_validated_ndjson_and_closes_client(
    payload, expected_exit, monkeypatch, capsys
):
    import sys

    from hope_brain import anthropic_provider, cli

    provider, requests, stream, _ = provider_with_transport(payload)
    monkeypatch.setattr(anthropic_provider, "AnthropicProvider", lambda settings: provider)
    monkeypatch.setattr(AnthropicSettings, "from_env", classmethod(lambda cls: settings()))
    monkeypatch.setattr(sys, "argv", ["hope", "--provider", "anthropic", "--live-smoke"])
    assert asyncio.run(cli.run()) == expected_exit
    captured = capsys.readouterr()
    result = [brain_event_adapter.validate_json(line) for line in captured.out.splitlines()]
    assert result[-1].type == ("turn.completed" if expected_exit == 0 else "turn.failed")
    assert [event.seq for event in result] == [1, 2, 3]
    assert stream.closed
    assert provider.client.is_closed()
    assert len(requests) == 2
    assert "test-secret" not in captured.err


def test_cancellation_after_fallback_suppresses_failure_terminal():
    async def run():
        provider, _, _, _ = provider_with_transport(events("invalid"))
        cancel = asyncio.Event()
        result = []
        try:
            async for event in TurnOrchestrator(provider).stream(REQUEST, cancel):
                result.append(event)
                if event.type == "speech.segment":
                    cancel.set()
        finally:
            await provider.aclose()
        assert [event.type for event in result] == [
            "turn.started",
            "speech.segment",
            "turn.cancelled",
        ]

    asyncio.run(run())


def test_task_cancellation_closes_sdk_stream():
    async def run():
        provider, _, stream, _ = provider_with_transport(events()[:4], hang=True)
        task = asyncio.create_task(collect(provider))
        await asyncio.wait_for(stream.entered.wait(), 2)
        task.cancel()
        result = await asyncio.wait_for(task, 2)
        assert [event.type for event in result] == ["turn.started", "turn.cancelled"]
        assert stream.closed

    asyncio.run(run())
