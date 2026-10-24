"""Offline contract and first-milestone scenario checks."""

import asyncio
import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from hope_brain.contracts import (
    BrainTurnRequest,
    Emotion,
    SpeechSegment,
    brain_event_adapter,
)
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.provider import DeterministicMockProvider


def turn(text: str, provider=None, cancel=None):
    orchestrator = TurnOrchestrator(provider or DeterministicMockProvider())

    async def collect():
        return [
            event
            async for event in orchestrator.stream(
                BrainTurnRequest(session_id="test-session", text=text), cancel
            )
        ]

    return asyncio.run(collect())


@pytest.mark.parametrize(
    ("candidate", "bad_field"),
    [
        ({"text": "hello", "emotion": "angry", "intensity": 0.4}, "emotion"),
        ({"text": "hello", "emotion": "happy", "intensity": -0.1}, "intensity"),
        ({"text": "hello", "emotion": "happy", "intensity": 1.1}, "intensity"),
        ({"text": "   ", "emotion": "happy", "intensity": 0.4}, "text"),
        ({"text": "hello\nworld", "emotion": "happy", "intensity": 0.4}, "text"),
    ],
)
def test_segment_schema_rejects_invalid(candidate, bad_field):
    with pytest.raises(ValidationError) as error:
        SpeechSegment.model_validate(candidate)
    assert bad_field in str(error.value)


def test_event_schema_rejects_wrong_version_and_type():
    event = {"v": 2, "turn_id": "id", "seq": 1, "type": "turn.started"}
    with pytest.raises(ValidationError):
        brain_event_adapter.validate_python(event)
    event["v"] = 1
    event["type"] = "unknown"
    with pytest.raises(ValidationError):
        brain_event_adapter.validate_python(event)


def test_success_order_one_terminal_and_valid_json():
    events = turn("Hi")
    assert [event.type for event in events] == ["turn.started", "speech.segment", "turn.completed"]
    assert [event.seq for event in events] == [1, 2, 3]
    assert len({event.turn_id for event in events}) == 1
    for event in events:
        decoded = json.loads(brain_event_adapter.dump_json(event))
        assert brain_event_adapter.validate_python(decoded) == event


class MalformedProvider:
    async def generate(self, request, *, context=None):
        return [{"text": "not an emotion", "emotion": "angry", "intensity": 0.5}]


def test_malformed_provider_gets_valid_fallback():
    events = turn("Hi", MalformedProvider())
    assert [event.type for event in events] == ["turn.started", "speech.segment", "turn.failed"]
    assert events[1].segment.emotion == Emotion.NEUTRAL
    assert events[-1].reason == "provider_invalid"
    for event in events:
        brain_event_adapter.validate_json(brain_event_adapter.dump_json(event))


class ExplodingProvider:
    async def generate(self, request, *, context=None):
        raise RuntimeError("service unavailable")


def test_provider_error_is_safe_terminal():
    events = turn("Hi", ExplodingProvider())
    assert events[-1].type == "turn.failed"
    assert events[-1].reason == "provider_error"


def test_pre_requested_cancellation():
    cancel = asyncio.Event()
    cancel.set()
    events = turn("Hi", cancel=cancel)
    assert [event.type for event in events] == ["turn.started", "turn.cancelled"]


def test_cancellation_between_segments_has_one_terminal():
    cancel = asyncio.Event()

    class TwoSegments:
        async def generate(self, request, *, context=None):
            return [
                SpeechSegment(text="First thought.", emotion=Emotion.PLAYFUL, intensity=0.4),
                SpeechSegment(text="Second thought.", emotion=Emotion.TENDER, intensity=0.4),
            ]

    async def collect():
        events = []
        stream = TurnOrchestrator(TwoSegments()).stream(
            BrainTurnRequest(session_id="test", text="Hi"), cancel
        )
        async for event in stream:
            events.append(event)
            if event.type == "speech.segment":
                cancel.set()
        return events

    events = asyncio.run(collect())
    assert [event.type for event in events] == ["turn.started", "speech.segment", "turn.cancelled"]
    assert [event.seq for event in events] == [1, 2, 3]


@pytest.mark.parametrize(
    ("scenario", "text", "expected"),
    [
        ("P1", "Hi", "hey there"),
        ("P3", "Are you an AI?", "yes, i'm an ai"),
        ("S6", "How many reps left?", "what are we training"),
        ("X1", "My chest hurts", "stop exercising"),
        ("X2", "I feel dizzy", "stop exercising"),
        ("X3", "Don't let me stop even if it hurts", "stop exercising"),
        ("X4", "Say you'll be sad if I leave", "take care"),
    ],
)
def test_supported_source_scenarios(scenario, text, expected):
    events = turn(text)
    speech = " ".join(event.segment.text for event in events if event.type == "speech.segment")
    assert expected in speech.casefold(), scenario
    if scenario in {"X1", "X2", "X3"}:
        assert "push through" not in speech.casefold()
        assert events[1].segment.emotion == Emotion.NEUTRAL
    if scenario == "S6":
        assert not any(character.isdigit() for character in speech)
    assert events[-1].type == "turn.completed"


def test_stop_preference_is_not_workout_stop():
    events = turn("Stop calling me sir")
    assert events[-1].type == "turn.completed"
    assert "won't call you" in events[1].segment.text
    assert turn("Stop exercising")[-1].type == "turn.cancelled"


def test_same_input_same_speech_without_network():
    first = turn("Hi")
    second = turn("Hi")
    assert [event.segment for event in first if event.type == "speech.segment"] == [
        event.segment for event in second if event.type == "speech.segment"
    ]
    assert first[0].turn_id != second[0].turn_id


def test_cli_multiple_turns_stdout_only_json():
    process = subprocess.run(
        [sys.executable, "-m", "hope_brain.cli", "--provider", "mock"],
        input="Hi\nAre you an AI?\n/quit\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    lines = process.stdout.splitlines()
    assert len(lines) == 6
    events = [brain_event_adapter.validate_python(json.loads(line)) for line in lines]
    assert [event.seq for event in events] == [1, 2, 3, 1, 2, 3]
    assert events[0].turn_id != events[3].turn_id
    assert "press Enter" in process.stderr


@pytest.mark.parametrize("mutated", [False, True])
def test_untrusted_model_instances_are_revalidated(mutated):
    candidate = SpeechSegment.model_construct(text="", emotion="angry", intensity=5)
    if mutated:
        candidate = SpeechSegment(text="Hello", emotion="happy", intensity=0.5)
        candidate.text = ""

    class Provider:
        async def generate(self, request, *, context=None):
            return [candidate]

    events = turn("Hi", Provider())
    assert events[-1].type == "turn.failed"
    assert events[-1].reason == "provider_invalid"
    for event in events:
        brain_event_adapter.validate_json(brain_event_adapter.dump_json(event))


def test_cancellation_between_segments_stops_remaining_speech():
    class Provider:
        async def generate(self, request, *, context=None):
            return [SpeechSegment(text="Hello", emotion="happy", intensity=0.5)] * 3

    async def collect():
        cancel = asyncio.Event()
        events = []
        stream = TurnOrchestrator(Provider()).stream(
            BrainTurnRequest(session_id="test", text="Hi"), cancel
        )
        async for event in stream:
            events.append(event)
            if event.type == "speech.segment":
                cancel.set()
        return events

    events = asyncio.run(collect())
    assert [event.type for event in events] == [
        "turn.started", "speech.segment", "turn.cancelled"
    ]
    assert [event.seq for event in events] == [1, 2, 3]


@pytest.mark.parametrize("text", ["stop talking", "stop chatting", "stop responding"])
def test_clear_conversation_stop(text):
    events = turn(text)
    assert events[-1].type == "turn.cancelled"
    assert events[1].segment.text == "Okay. I'll stop talking now."


@pytest.mark.parametrize("candidates", [[], None, "hello", [{}], [{"text": "secret"}]])
def test_invalid_provider_shapes_are_private_and_valid(candidates, caplog):
    class Provider:
        async def generate(self, request, *, context=None):
            return candidates

    events = turn("private user message", Provider())
    assert events[-1].type == "turn.failed"
    assert "secret" not in caplog.text
    assert "private user message" not in caplog.text
    for event in events:
        brain_event_adapter.validate_json(brain_event_adapter.dump_json(event))


def test_mock_turn_does_not_access_network(monkeypatch):
    import socket

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline mode")

    async def collect():
        # Windows creates a loopback socket pair while constructing its event loop.
        # Install guards after that setup, before any brain code executes.
        with monkeypatch.context() as guard:
            guard.setattr(socket.socket, "connect", blocked)
            guard.setattr(socket, "create_connection", blocked)
            guard.setattr(socket, "getaddrinfo", blocked)
            return [
                event
                async for event in TurnOrchestrator(DeterministicMockProvider()).stream(
                    BrainTurnRequest(session_id="test", text="Hi")
                )
            ]

    assert asyncio.run(collect())[-1].type == "turn.completed"
