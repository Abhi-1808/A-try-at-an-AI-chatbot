"""Persona preferences, command separation and input arriving during generation."""

import asyncio
import io
import json
import queue
import sys

import pytest

from hope_brain import cli
from hope_brain.context import ContextBuilder, TrustedContext
from hope_brain.contracts import BrainTurnRequest, SpeechSegment, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.persona import PERSONA_RULES, PERSONA_VERSION, StylePreferences
from hope_brain.terminal_input import TerminalInput
from hope_brain.workout import Actor
from hope_brain.workout_store import SQLiteWorkoutRepository


class Recorder:
    def __init__(self):
        self.calls = []

    async def generate(self, request, *, context=None):
        self.calls.append((request, context))
        return [SpeechSegment(text="Ready for the next idea.", emotion="playful", intensity=0.5)]


def test_versioned_persona_is_in_both_model_prompts():
    for conversational in (False, True):
        built = ContextBuilder(conversational=conversational).build(
            BrainTurnRequest(session_id="s", text="private prompt"),
            TrustedContext(preferences=StylePreferences("boss")),
        )
        assert PERSONA_RULES in built.system and PERSONA_VERSION in built.system
        assert '"address": "boss"' in built.system
        assert "private prompt" not in built.system
        assert "Runtime policy" in built.system


def test_session_preferences_survive_history_eviction_and_clear_and_respect_auth():
    store = SQLiteWorkoutRepository()
    actor = Actor(user_id="owner", session_id="s")
    store.register_session(actor)
    provider = Recorder()
    brain = TurnOrchestrator(provider, workouts=store, actor=actor, conversational=True)

    async def turn(text, session="s"):
        return [e async for e in brain.stream(BrainTurnRequest(session_id=session, text=text))]

    async def exercise():
        await turn("Call me boss")
        assert not provider.calls
        for index in range(10):
            await turn(f"Topic {index}")
        assert provider.calls[-1][1].preferences.address == "boss"
        rejected = await turn("Call me intruder", "wrong-session")
        assert rejected[-1].reason == "unauthorized"
        await turn("Stop calling me boss")
        await turn("ready")
        assert provider.calls[-1][1].preferences.address is None
        cleared = await turn("/clear")
        assert "address reset to sir" in cleared[1].segment.text
        await turn("ready")
        assert provider.calls[-1][1].preferences.address == "sir"
        assert provider.calls[-1][1].history == ()
    try:
        asyncio.run(exercise())
    finally:
        store.close()


@pytest.mark.parametrize("text", [
    r"& .\scripts\Start-Mira.ps1 -Local", "$env:HOPE_OLLAMA_MODEL='qwen3:4b'",
    "ollama pull qwen3:4b", "uv sync --extra local", "python -m hope_brain.cli",
])
def test_shell_commands_are_rejected_before_model_and_never_enter_history(text):
    store = SQLiteWorkoutRepository()
    actor = Actor(user_id="owner", session_id="s")
    store.register_session(actor)
    provider = Recorder()
    brain = TurnOrchestrator(provider, workouts=store, actor=actor, conversational=True)

    async def exercise():
        rejected = [e async for e in brain.stream(BrainTurnRequest(session_id="s", text=text))]
        assert rejected[-1].reason == "input_rejected"
        assert not provider.calls
        result = [e async for e in brain.stream(BrainTurnRequest(
            session_id="s", text="Explain this command: ollama pull qwen3:4b"
        ))]
        assert result[-1].type == "turn.completed"
        assert provider.calls[-1][1].history == ()
    try:
        asyncio.run(exercise())
    finally:
        store.close()


def test_four_inputs_arriving_during_first_generation_receive_four_replies(monkeypatch, capsys):
    source = queue.Queue()
    calls = []

    def lines():
        while (item := source.get()) is not None:
            yield item

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        class SlowProvider:
            async def generate(self, request, *, context=None):
                calls.append(request.text)
                if len(calls) == 1:
                    entered.set()
                    await release.wait()
                return [SpeechSegment(text="A short test reply.", emotion="neutral", intensity=0.3)]

        monkeypatch.setattr(cli, "DeterministicMockProvider", SlowProvider)
        monkeypatch.setattr(sys, "argv", ["hope", "--chat"])
        monkeypatch.setattr(sys, "stdin", lines())
        source.put("Hi\n")
        task = asyncio.create_task(cli.run())
        await asyncio.wait_for(entered.wait(), 1)
        for line in ["Reaready\n", "ready\n", "Explain rain\n"]:
            source.put(line)
        source.put(None)
        await asyncio.sleep(0.05)
        assert calls == ["Hi"]
        release.set()
        assert await asyncio.wait_for(task, 2) == 0
    asyncio.run(exercise())
    assert calls == ["Hi", "Reaready", "ready", "Explain rain"]
    output = capsys.readouterr()
    events = [brain_event_adapter.validate_json(line) for line in output.out.splitlines()]
    assert sum(e.type == "turn.completed" for e in events) == 4
    for number in range(1, 5):
        assert f"Input #{number} accepted" in output.err
        assert f"Reply #{number}: completed" in output.err


def test_queue_overflow_is_visible_and_eof_drains_accepted_inputs():
    async def exercise():
        notices = []
        offered = asyncio.Event()

        def notice(message):
            notices.append(message)
            if len(notices) == 4:
                offered.set()
        reader = TerminalInput(io.StringIO("one\ntwo\nthree\nfour"), notice, capacity=2)
        try:
            await asyncio.wait_for(offered.wait(), 1)
            received = [item.text async for item in reader]
            assert received == ["one", "two"]
            assert sum("rejected: queue full" in n for n in notices) == 2
        finally:
            reader.close()
    asyncio.run(exercise())


def test_cli_delivers_last_line_without_newline_at_eof(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hope"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("Hi\nready"))
    assert asyncio.run(cli.run()) == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert sum(e["type"] == "turn.completed" for e in events) == 2
