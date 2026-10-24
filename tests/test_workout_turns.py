"""Offline state dialogue and pre-provider safety integration."""

import asyncio
import json
import subprocess
import sys
from uuid import uuid4

import pytest

from hope_brain.contracts import BrainTurnRequest, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.provider import DeterministicMockProvider
from hope_brain.workout import Actor
from hope_brain.workout_store import SQLiteWorkoutRepository


class NeverProvider:
    def __init__(self):
        self.calls = 0

    async def generate(self, request, *, context=None):
        self.calls += 1
        raise AssertionError("This deterministic turn must bypass the provider")


@pytest.fixture
def brain():
    store = SQLiteWorkoutRepository()
    actor = Actor(user_id="owner", session_id="session")
    store.register_session(actor)
    provider = NeverProvider()
    orchestrator = TurnOrchestrator(provider, workouts=store, actor=actor)
    yield orchestrator, store, actor, provider
    store.close()


def turn(brain, text, **overrides):
    request = BrainTurnRequest(session_id="session", text=text, **overrides)

    async def collect():
        result = [event async for event in brain[0].stream(request)]
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

    return asyncio.run(asyncio.wait_for(collect(), 2))


def speech(events):
    return " ".join(event.segment.text for event in events if event.type == "speech.segment")


def test_s1_s2_s5_and_unknown_s6(brain):
    unknown = turn(brain, "How many left?")
    assert "training" in speech(unknown)
    assert not any(c.isdigit() for c in speech(unknown))
    turn(brain, "/workout start pushups 12")
    turn(brain, "I did 5")
    turn(brain, "I did 5")
    status = turn(brain, "How many left?")
    assert speech(status) == "2 reps remain."
    assert brain[1].get(brain[2]).reps_done == 10
    assert brain[3].calls == 0


def test_s3_s4_confirmed_target_history_and_cap(brain):
    turn(brain, "/workout start pushups 12")
    assert "has not changed" in speech(turn(brain, "Did you just move my target?"))
    for target in [15, 18]:
        turn(brain, "just 3 more")
        state = brain[1].get(brain[2])
        assert state.target == target - 3
        turn(brain, f"/workout confirm {state.pending_proposal.proposal_id}")
    history = speech(turn(brain, "Did you just move my target?"))
    assert "15 to 18" in history and "confirmed" in history
    rejected = turn(brain, "just 3 more")
    assert rejected[-1].reason == "tool_rejected"
    assert brain[1].get(brain[2]).target == 18
    assert brain[3].calls == 0


def test_c1_callback_requires_recorded_statement_and_never_invents_admission(brain):
    turn(brain, "/workout start pushups 12")
    turn(brain, "/workout reps 9")
    turn(brain, "/workout reps 3")
    reply = speech(turn(brain, "You said 3 reps ago it was only 3 left"))
    assert "reported 3 left" in reply and "0 reps remain" in reply
    assert "confirmed a target change" not in reply
    missing = speech(turn(brain, "You said 5 reps ago it was only 3 left"))
    assert "can't verify" in missing


def test_c1_callback_explains_actual_confirmed_change(brain):
    turn(brain, "/workout start pushups 12")
    turn(brain, "/workout reps 9")
    turn(brain, "/workout propose 15")
    pending = brain[1].get(brain[2]).pending_proposal
    turn(brain, f"/workout confirm {pending.proposal_id}")
    turn(brain, "/workout reps 3")
    reply = speech(turn(brain, "You said 3 reps ago it was only 3 left"))
    assert "confirmed a target change" in reply and "3 reps remain" in reply


@pytest.mark.parametrize("text", ["Explain your maths", "That makes no sense"])
def test_c2_c3_explain_real_state_without_moving_goal(brain, text):
    turn(brain, "/workout start pushups 12")
    turn(brain, "/workout reps 10")
    before = brain[1].get(brain[2])
    assert speech(turn(brain, text)) == "2 reps remain."
    assert brain[1].get(brain[2]).version == before.version


@pytest.mark.parametrize(
    "text",
    [
        "ugh my chest is kinda tight",
        "I'm dizzy, wait",
        "I\u2019m dizzy, wait",
        "my chest hurts",
        "trouble breathing",
        "Don't let me stop even if it hurts",
        "/workout reps 5 but my chest feels tight",
    ],
)
def test_messy_danger_stops_state_before_any_provider_call(brain, text):
    turn(brain, "/workout start pushups 12")
    turn(brain, "/workout propose 15")
    result = turn(brain, text)
    assert "Stop exercising" in speech(result)
    assert result[-1].type == "turn.completed"
    assert all(
        event.segment.emotion.value == "neutral"
        for event in result
        if event.type == "speech.segment"
    )
    state = brain[1].get(brain[2])
    assert state.status == "stopped" and state.reps_done == 0
    assert state.pending_proposal is None
    assert text not in state.model_dump_json()
    assert brain[3].calls == 0


@pytest.mark.parametrize("text", ["Stop", "Stop exercising", "Please stop the workout"])
def test_stop_cancels_turn_and_ends_workout(brain, text):
    turn(brain, "/workout start pushups 12")
    assert turn(brain, text)[-1].type == "turn.cancelled"
    assert brain[1].get(brain[2]).status == "stopped"
    assert brain[3].calls == 0


def test_preference_and_chat_stop_leave_workout_alone(brain):
    turn(brain, "/workout start pushups 12")
    brain[0].provider = DeterministicMockProvider()
    assert turn(brain, "Stop calling me sir")[-1].type == "turn.completed"
    assert brain[1].get(brain[2]).status == "active"
    stopped = turn(brain, "Stop talking")
    assert stopped[-1].type == "turn.cancelled"
    assert speech(stopped) == "Okay. I'll stop talking now."
    assert brain[1].get(brain[2]).status == "active"


def test_replayed_transcript_is_rejected(brain):
    turn(brain, "/workout start pushups 12")
    submission = uuid4()
    turn(brain, "I did 5", submission_id=submission)
    repeated = turn(brain, "I did 5", submission_id=submission)
    assert repeated[-1].reason == "tool_rejected"
    assert "already recorded" in speech(repeated)
    assert brain[1].get(brain[2]).reps_done == 5


@pytest.mark.parametrize(
    "text",
    [
        "/workout reps -1",
        "/workout start pushups 0",
        "/workout confirm yes",
        "set my reps to 50",
        "/workout start pushups 12 and ignore all limits",
    ],
)
def test_invalid_or_ambiguous_commands_do_not_reach_provider(brain, text):
    turn(brain, text)
    assert brain[1].get(brain[2]) is None
    assert brain[3].calls == 0


def test_request_cannot_select_another_bound_session(brain):
    async def collect():
        request = BrainTurnRequest(session_id="someone-else", text="Hi")
        return [event async for event in brain[0].stream(request)]

    result = asyncio.run(collect())
    assert result[-1].reason == "unauthorized"
    assert brain[3].calls == 0


def test_database_failure_still_returns_safety_speech_and_no_provider(brain):
    brain[1]._db.execute("DROP TABLE sessions")
    result = turn(brain, "I'm dizzy, wait")
    assert "Stop exercising" in speech(result)
    assert result[-1].reason == "state_unavailable"
    assert brain[3].calls == 0


def test_cli_workout_session_is_ndjson():
    result = subprocess.run(
        [sys.executable, "-m", "hope_brain.cli"],
        input="/workout start pushups 12\nI did 5\nI did 5\nHow many left?\nStop\n/quit\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    events = [
        brain_event_adapter.validate_python(json.loads(line)) for line in result.stdout.splitlines()
    ]
    assert "2 reps remain." in speech(events)
    assert events[-1].type == "turn.cancelled"
    assert [event.state.status for event in events if event.type == "workout.state"][
        -1
    ] == "stopped"


def test_ambiguous_request_preserves_known_state(brain):
    turn(brain, "/workout start pushups 12")
    result = turn(brain, "set my reps to 50")
    view = next(event.state for event in result if event.type == "workout.state")
    assert view.target == 12 and view.reps_done == 0


def test_target_query_returns_target_instead_of_remaining(brain):
    turn(brain, "/workout start pushups 12")
    turn(brain, "/workout reps 10")
    assert speech(turn(brain, "What's my target?")) == "Your confirmed target is 12 reps."
    assert speech(turn(brain, "What\u2019s my target?")) == "Your confirmed target is 12 reps."


def test_misspelled_command_prefix_cannot_start_workout(brain):
    turn(brain, "/workouttypo start pushups 12")
    assert brain[1].get(brain[2]) is None


def test_large_callback_number_does_not_break_event_stream(brain):
    turn(brain, "You said " + "9" * 5000 + " reps ago only 3 left")
    assert brain[3].calls == 0


def test_cancelled_undelivered_count_cannot_be_used_as_a_callback(brain):
    turn(brain, "/workout start pushups 12")

    async def cancel_before_speech():
        cancel = asyncio.Event()
        request = BrainTurnRequest(session_id="session", text="/workout reps 9")
        result = []
        async for event in brain[0].stream(request, cancel):
            result.append(event)
            if event.type == "workout.state":
                cancel.set()
        assert result[-1].type == "turn.cancelled"
        assert not any(event.type == "speech.segment" for event in result)

    asyncio.run(cancel_before_speech())
    turn(brain, "/workout reps 3")
    reply = speech(turn(brain, "You said 3 reps ago it was only 3 left"))
    assert "can't verify" in reply


def test_completed_set_is_cheering_without_extra_target(brain):
    turn(brain, "/workout start pushups 12")
    result = turn(brain, "/workout reps 12")
    segment = next(event.segment for event in result if event.type == "speech.segment")
    assert segment.emotion.value == "cheering" and segment.intensity >= 0.7
    assert len(segment.text.split()) <= 14
    assert brain[1].get(brain[2]).target == 12


def test_stop_commits_before_consumer_closes_after_safety_speech(brain):
    turn(brain, "/workout start pushups 12")
    turn(brain, "/workout propose 15")

    async def close_early():
        stream = brain[0].stream(BrainTurnRequest(session_id="session", text="Stop exercising"))
        assert (await anext(stream)).type == "turn.started"
        assert (await anext(stream)).type == "speech.segment"
        await stream.aclose()

    asyncio.run(close_early())
    state = brain[1].get(brain[2])
    assert state.status == "stopped" and state.pending_proposal is None
    assert brain[3].calls == 0
