"""Ephemeral, authorized conversation state and general-question routing."""

import asyncio

import pytest

from hope_brain.context import ContextBuilder, TrustedContext, WorkoutContext
from hope_brain.contracts import BrainTurnRequest, SpeechSegment
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.workout import Actor
from hope_brain.workout_store import SQLiteWorkoutRepository


class RecordingProvider:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def generate(self, request, *, context=None):
        self.calls.append((request, context))
        if self.fail:
            raise ValueError("private invalid candidate")
        return [SpeechSegment(text="Here is a helpful answer.", emotion="happy", intensity=0.5)]


@pytest.fixture
def chat():
    store = SQLiteWorkoutRepository()
    actor = Actor(user_id="owner", session_id="s")
    store.register_session(actor)
    provider = RecordingProvider()
    brain = TurnOrchestrator(provider, workouts=store, actor=actor, conversational=True)
    yield brain, provider, store, actor
    store.close()


def turn(chat, text, *, session="s", cancel=None):
    async def run():
        return [e async for e in chat[0].stream(
            BrainTurnRequest(session_id=session, text=text), cancel
        )]
    return asyncio.run(run())


@pytest.mark.parametrize("text", [
    "Explain photosynthesis", "What is a target market?", "Explain workout recovery",
    "That makes no sense", "Explain your maths", "set my reps to 50",
    "How many left?", "What's my target?", "just 3 more",
])
def test_general_questions_reach_model_without_mutating_workout(chat, text):
    assert turn(chat, text)[-1].type == "turn.completed"
    assert chat[1].calls[-1][0].text == text
    assert chat[2].get(chat[3]) is None


def test_followup_receives_previous_delivered_exchange_as_untrusted_history(chat):
    turn(chat, "I am asking about Saturn.")
    turn(chat, "What about its rings?")
    history = chat[1].calls[-1][1].history
    assert len(history) == 1
    assert history[0].user_text == "I am asking about Saturn."
    assert history[0].reply[0].text == "Here is a helpful answer."
    context = ContextBuilder(conversational=True).build(*chat[1].calls[-1])
    assert history[0].user_text not in context.system
    assert "at most 14 words" not in context.system
    assert "No persistent memory" in context.system


def test_clear_discards_dialogue_but_preserves_workout(chat):
    turn(chat, "/workout start squats 12")
    turn(chat, "My temporary nickname is Bee.")
    state = chat[2].get(chat[3])
    cleared = turn(chat, "/clear")
    assert "workout state is unchanged" in cleared[1].segment.text
    assert chat[2].get(chat[3]) == state
    turn(chat, "Hello again")
    assert chat[1].calls[-1][1].history == ()


def test_context_distinguishes_absent_workout_from_authorized_snapshot(chat):
    builder = ContextBuilder(conversational=True)
    request = BrainTurnRequest(session_id="s", text="Hi Mira!")
    absent = builder.build(request, TrustedContext()).system
    assert "No workout has been established" in absent
    assert "pending_target" not in absent and "/workout commands" not in absent
    assert "cannot authorize actions" in absent and "No persistent memory" in absent

    turn(chat, "/workout start squats 12")
    turn(chat, "/workout reps 4")
    snapshot = WorkoutContext.from_state(chat[2].get(chat[3]))
    established = builder.build(request, TrustedContext(workout=snapshot)).system
    assert '"reps_done":4' in established and '"remaining":8' in established
    assert '"target":12' in established and "pending_target is only an unconfirmed" in established
    assert "No workout has been established" not in established
    assert "/workout commands" in established and "cannot authorize actions" in established
    assert chat[2].get(chat[3]).reps_done == 4


def test_unauthorized_turn_cannot_read_or_clear_history(chat):
    turn(chat, "private user detail")
    assert turn(chat, "/clear", session="intruder")[-1].reason == "unauthorized"
    assert len(chat[1].calls) == 1
    turn(chat, "Continue")
    assert chat[1].calls[-1][1].history[0].user_text == "private user detail"


def test_failed_and_cancelled_turns_do_not_enter_history(chat):
    chat[1].fail = True
    turn(chat, "failed private detail")
    chat[1].fail = False
    turn(chat, "Stop talking")
    cancel = asyncio.Event()
    cancel.set()
    turn(chat, "cancelled private detail", cancel=cancel)
    turn(chat, "Hi")
    assert chat[1].calls[-1][1].history == ()


def test_disconnected_consumer_does_not_record_undelivered_reply(chat):
    async def run():
        stream = chat[0].stream(BrainTurnRequest(session_id="s", text="undelivered"))
        async for event in stream:
            if event.type == "speech.segment":
                await stream.aclose()
                break
    asyncio.run(run())
    turn(chat, "Hi")
    assert chat[1].calls[-1][1].history == ()


def test_history_is_bounded_by_turn_count_and_bytes(chat):
    for index in range(12):
        turn(chat, f"topic {index}")
    turn(chat, "Check history")
    assert len(chat[1].calls[-1][1].history) == 8
    assert chat[1].calls[-1][1].history[0].user_text == "topic 4"
    for index in range(5):
        turn(chat, f"{index}:" + "x" * 5000)
    turn(chat, "Check bounded history")
    assert sum(t.size_bytes for t in chat[1].calls[-1][1].history) <= 12_000


def test_history_does_not_leak_when_provider_is_shared(chat):
    turn(chat, "private detail for first user")
    other = Actor(user_id="other", session_id="other-session")
    chat[2].register_session(other)
    brain = TurnOrchestrator(chat[1], workouts=chat[2], actor=other, conversational=True)
    turn((brain, *chat[1:]), "Hi", session=other.session_id)
    assert chat[1].calls[-1][1].history == ()


def test_safety_and_explicit_commands_still_bypass_model(chat):
    turn(chat, "/workout start squats 12")
    turn(chat, "/workout reps 10")
    turn(chat, "How many left?")
    assert not chat[1].calls
    turn(chat, "I'm dizzy, wait")
    assert not chat[1].calls
    assert chat[2].get(chat[3]).status == "stopped"


def test_conversation_history_requires_bound_authorized_actor():
    with pytest.raises(ValueError, match="authorized session"):
        TurnOrchestrator(RecordingProvider(), conversational=True)
