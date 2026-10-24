"""Local adapter exercised against HTTP fixtures; never downloads or runs a model."""

import asyncio
import json
import logging

import pytest

httpx = pytest.importorskip("httpx2")

from hope_brain.context import ConversationExchange, TrustedContext
from hope_brain.contracts import BrainTurnRequest, SpeechSegment
from hope_brain.ollama_provider import OllamaProvider
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.settings import ConfigurationError, OllamaSettings

REQUEST = BrainTurnRequest(session_id="private-session", text="Explain photosynthesis")
SHOW = {"model_info": {"general.architecture": "qwen3"}, "capabilities": ["completion"]}
REPLY = {"segments": [{"text": "Plants use sunlight to make food.",
                       "emotion": "neutral", "intensity": 0.4}]}


@pytest.fixture(autouse=True)
def prevent_network(monkeypatch):
    original = httpx.AsyncClient.send

    async def guarded(client, *args, **kwargs):
        assert isinstance(client._transport, httpx.MockTransport), "Real HTTP forbidden in tests"
        return await original(client, *args, **kwargs)
    monkeypatch.setattr(httpx.AsyncClient, "send", guarded)


class Body(httpx.AsyncByteStream):
    def __init__(self, payload, hang=False):
        self.payload = payload
        self.hang = hang
        self.entered = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        self.entered.set()
        yield self.payload
        if self.hang:
            await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


def provider(*, reply=None, show=None, status=200, hang=False, timeout=1, raw=None):
    calls = []
    payload = {"done": True, "done_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(REPLY), "thinking": "private reasoning",
    }, "prompt_eval_count": 100, "eval_count": 30} if reply is None else reply
    stream = Body(json.dumps(payload).encode() if raw is None else raw, hang)

    async def handle(request):
        calls.append(request)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW if show is None else show)
        if status != 200:
            return httpx.Response(status, json={"error": "private server details"},
                                  headers={"location": "https://example.com/private"})
        return httpx.Response(200, stream=stream)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle), trust_env=False,
                               follow_redirects=False)
    return OllamaProvider(OllamaSettings(timeout_seconds=timeout), client=client), calls, stream


async def collect(local, request=REQUEST, cancel=None):
    try:
        return [e async for e in TurnOrchestrator(local).stream(request, cancel)]
    finally:
        await local.aclose()


def test_general_reply_uses_schema_loopback_history_and_redacted_logs(caplog):
    caplog.set_level(logging.INFO, logger="hope_brain")
    local, calls, stream = provider()
    history = ConversationExchange("private prior message", (
        SpeechSegment(text="Earlier answer.", emotion="happy", intensity=0.5),
    ))

    async def exercise():
        try:
            return await local.generate(REQUEST, context=TrustedContext(history=(history,)))
        finally:
            await local.aclose()
    result = asyncio.run(exercise())
    assert result[0].text == "Plants use sunlight to make food."
    assert stream.closed and local.client.is_closed
    assert [call.url.path for call in calls] == ["/api/show", "/api/chat"]
    assert all(call.url.host == "127.0.0.1" for call in calls)
    body = json.loads(calls[-1].content)
    assert body["format"]["type"] == "object" and body["stream"] is False
    assert body["think"] is False and "tools" not in body
    assert body["messages"][1] == {"role": "user", "content": "private prior message"}
    assert body["messages"][-1]["content"] == REQUEST.text
    assert "private prior message" not in body["messages"][0]["content"]
    assert "private-session" not in calls[-1].content.decode()
    for text in [REQUEST.text, "private prior", "private reasoning", "Earlier answer", result[0].text]:
        assert text not in caplog.text
    assert '"eval_count":30' in caplog.text
    assert local.last_metrics["thinking_requested"] == 0
    assert local.last_metrics["thinking_output_seen"] == 1
    assert "private reasoning" not in json.dumps(local.last_metrics)


@pytest.mark.parametrize("reply", [
    {"done": False}, {"done": True, "done_reason": "length"},
    {"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": "bad"}},
    {"done": True, "done_reason": "stop", "message": {
        "role": "assistant", "content": json.dumps(REPLY), "tool_calls": [{"name": "set_reps"}],
    }},
    {"done": True, "done_reason": "stop", "remote_host": "private-cloud",
     "message": {"role": "assistant", "content": json.dumps(REPLY)}},
    {"error": "private-error"},
])
def test_bad_responses_are_rejected_without_leaking_content(reply, caplog):
    local, _, stream = provider(reply=reply)
    result = asyncio.run(collect(local))
    assert result[-1].reason == "provider_invalid"
    assert stream.closed
    assert "private-error" not in caplog.text
    assert not any("Plants" in e.segment.text for e in result if e.type == "speech.segment")


@pytest.mark.parametrize("status", [302, 401, 404, 500])
def test_http_failures_do_not_retry_or_follow_redirects(status, caplog):
    local, calls, _ = provider(status=status)
    assert asyncio.run(collect(local))[-1].reason == "provider_error"
    assert len(calls) == 2
    assert "private server details" not in caplog.text


@pytest.mark.parametrize("details", [
    SHOW | {"remote_host": "https://ollama.com"}, SHOW | {"remote_model": "cloud-alias"},
    {"model_info": {}, "capabilities": ["completion"]},
    {"model_info": {"a": 1}, "capabilities": ["embedding"]},
])
def test_model_inspection_rejects_cloud_or_incompatible_model_before_prompt(details):
    local, calls, _ = provider(show=details)
    assert asyncio.run(collect(local))[-1].reason == "provider_invalid"
    assert len(calls) == 1
    assert REQUEST.text not in calls[0].content.decode()


def test_timeout_closes_http_body():
    local, _, stream = provider(hang=True, timeout=0.05)
    assert asyncio.run(collect(local))[-1].reason == "provider_timeout"
    assert stream.closed


def test_cancellation_closes_http_body_and_emits_one_terminal():
    local, _, stream = provider(hang=True)

    async def exercise():
        cancel = asyncio.Event()
        task = asyncio.create_task(collect(local, cancel=cancel))
        await stream.entered.wait()
        cancel.set()
        return await task
    result = asyncio.run(exercise())
    assert [e.type for e in result] == ["turn.started", "turn.cancelled"]
    assert stream.closed


def test_input_and_response_size_limits():
    local, calls, _ = provider()
    result = asyncio.run(collect(local, BrainTurnRequest(session_id="s", text="x" * 8193)))
    assert result[-1].reason == "provider_invalid" and not calls
    local, _, stream = provider(raw=b"x" * 262_145)
    assert asyncio.run(collect(local))[-1].reason == "provider_invalid"
    assert stream.closed


def test_safety_never_contacts_ollama():
    local, calls, _ = provider()
    result = asyncio.run(collect(local, BrainTurnRequest(session_id="s", text="I'm dizzy, wait")))
    assert result[-1].type == "turn.completed" and not calls


@pytest.mark.parametrize(("name", "value"), [
    ("HOPE_OLLAMA_PORT", "0"), ("HOPE_OLLAMA_PORT", "65536"),
    ("HOPE_OLLAMA_TIMEOUT_SECONDS", "nan"), ("HOPE_OLLAMA_MAX_TOKENS", "0"),
    ("HOPE_OLLAMA_MODEL", "secret invalid"), ("HOPE_OLLAMA_MODEL", "test-cloud"),
])
def test_invalid_local_settings_are_redacted(name, value):
    with pytest.raises(ConfigurationError) as error:
        OllamaSettings.from_env({name: value})
    assert name in str(error.value)
    assert "secret invalid" not in str(error.value)


def test_cli_local_chat_has_followups_clear_and_no_paid_key(monkeypatch, capsys):
    import io
    import sys

    from hope_brain import cli, ollama_provider
    from hope_brain.contracts import brain_event_adapter

    local, calls, _ = provider()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ollama_provider, "OllamaProvider", lambda settings: local)
    monkeypatch.setattr(sys, "argv", ["hope", "--provider", "ollama", "--chat"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        "Explain photosynthesis\nWhat about at night?\n/clear\nExplain a target market\n/quit\n"
    ))
    assert asyncio.run(cli.run()) == 0
    output = capsys.readouterr()
    events = [brain_event_adapter.validate_json(line) for line in output.out.splitlines()]
    assert sum(e.type == "turn.completed" for e in events) == 4
    bodies = [json.loads(call.content) for call in calls if call.url.path == "/api/chat"]
    assert len(bodies) == 3
    assert len(bodies[1]["messages"]) == 4
    assert bodies[1]["messages"][1]["content"] == "Explain photosynthesis"
    assert len(bodies[2]["messages"]) == 2
    assert local.client.is_closed
    assert "Mira: Plants use sunlight" in output.err
    assert "API key" not in output.err


@pytest.mark.parametrize("failure", ["connection", "missing_model", "cloud"])
def test_startup_failures_have_safe_actionable_errors(failure):
    async def handle(request):
        if failure == "connection":
            raise httpx.ConnectError("private-server-detail")
        if failure == "missing_model":
            return httpx.Response(404, json={"error": "private-server-detail"})
        return httpx.Response(200, json=SHOW | {"remote_host": "private-server-detail"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    local = OllamaProvider(OllamaSettings(), client=client)

    async def exercise():
        try:
            with pytest.raises(ConfigurationError) as error:
                await local.check_ready()
            return str(error.value)
        finally:
            await local.aclose()
    message = asyncio.run(exercise())
    assert "private-server-detail" not in message
    assert {"connection": "Start Ollama", "missing_model": "ollama pull", "cloud": "disabled"}[
        failure
    ] in message


def test_default_client_ignores_proxy_environment(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://private-proxy:9999")
    monkeypatch.setenv("OLLAMA_HOST", "https://private-remote")
    local = OllamaProvider(OllamaSettings())
    assert local.url == "http://127.0.0.1:11434"
    assert local.client.trust_env is False
    assert local.client.follow_redirects is False
    asyncio.run(local.aclose())


def test_late_transport_loggers_cannot_expose_request_text(caplog):
    caplog.set_level(logging.DEBUG)
    local, _, _ = provider()
    logging.getLogger("httpx2.new_local_connection").warning("private request canary")
    assert "private request canary" not in caplog.text
    asyncio.run(local.aclose())


def test_cli_failed_model_check_closes_client_without_emitting_events(monkeypatch, capsys):
    import sys

    from hope_brain import cli, ollama_provider

    local, calls, _ = provider(show=SHOW | {"remote_host": "private-remote"})
    monkeypatch.setattr(ollama_provider, "OllamaProvider", lambda settings: local)
    monkeypatch.setattr(sys, "argv", ["hope", "--provider", "ollama"])
    with pytest.raises(SystemExit) as error:
        asyncio.run(cli.run())
    assert error.value.code == 2 and local.client.is_closed
    captured = capsys.readouterr()
    assert captured.out == "" and "Cloud-backed" in captured.err
    assert "private-remote" not in captured.err
    assert len(calls) == 1
