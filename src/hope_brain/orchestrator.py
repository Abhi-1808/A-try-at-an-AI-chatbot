"""Server-owned turn lifecycle, validation, and sequence numbering."""

import asyncio
import logging
import sqlite3
from collections import deque
from collections.abc import AsyncIterator, Sequence
from uuid import uuid4

from pydantic import ValidationError

from hope_brain.context import ConversationExchange, TrustedContext, WorkoutContext
from hope_brain.contracts import (
    BrainEvent,
    BrainTurnRequest,
    Emotion,
    FailureReason,
    SpeechEvent,
    SpeechSegment,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
    WorkoutStateEvent,
)
from hope_brain.persona import StylePreferences, address_request
from hope_brain.policy import intake_policy, looks_like_shell_command
from hope_brain.provider import ModelProvider, ProviderBudgetExceeded
from hope_brain.workout import Actor, WorkoutError, WorkoutRepository, WorkoutView
from hope_brain.workout_intents import ERROR_MESSAGES, WorkoutController, say

logger = logging.getLogger(__name__)


class TurnOrchestrator:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        workouts: WorkoutRepository | None = None,
        actor: Actor | None = None,
        conversational: bool = False,
    ) -> None:
        if (workouts is None) != (actor is None):
            raise ValueError("workout repository and trusted actor must be supplied together")
        if conversational and actor is None:
            raise ValueError("conversation history requires an authorized session")
        self.conversational = conversational
        self._history: deque[ConversationExchange] = deque()
        self._preferences = StylePreferences()
        self.provider = provider
        self.workout = (
            WorkoutController(workouts, actor, general_chat=conversational)
            if workouts is not None and actor else None
        )

    async def stream(
        self, request: BrainTurnRequest, cancel: asyncio.Event | None = None
    ) -> AsyncIterator[BrainEvent]:
        delivered: list[SpeechSegment] = []
        async for event in self._stream(request, cancel):
            if event.type == "speech.segment":
                delivered.append(event.segment.model_copy(deep=True))
            if (
                self.conversational and event.type == "turn.completed"
                and request.text.strip().casefold() != "/clear"
            ):
                self._history.append(ConversationExchange(request.text, tuple(delivered)))
                while len(self._history) > 8 or sum(t.size_bytes for t in self._history) > 12_000:
                    self._history.popleft()
            yield event

    async def _stream(
        self, request: BrainTurnRequest, cancel: asyncio.Event | None = None
    ) -> AsyncIterator[BrainEvent]:
        turn_id = str(uuid4())
        seq = 1
        yield TurnStarted(turn_id=turn_id, seq=seq)

        if cancel is not None and cancel.is_set():
            yield TurnCancelled(turn_id=turn_id, seq=seq + 1, reason="request_cancelled")
            return

        if self.workout is not None and request.session_id != self.workout.actor.session_id:
            yield TurnFailed(turn_id=turn_id, seq=seq + 1, reason="unauthorized")
            return

        decision = intake_policy(request.text)
        if decision is not None:
            stopped_view = None
            state_failed = False
            if self.workout is not None:
                try:
                    if decision.stop_workout:
                        state = self.workout.repository.stop(self.workout.actor)
                        stopped_view = WorkoutView.from_state(state) if state else None
                    else:
                        self.workout.repository.get(self.workout.actor)
                except (WorkoutError, sqlite3.Error, ValidationError):
                    logger.warning("workout safety state unavailable")
                    state_failed = True
            # Commit the stop before yielding: a disconnected consumer must not
            # leave a pending target proposal or active set behind.
            seq += 1
            yield SpeechEvent(turn_id=turn_id, seq=seq, segment=decision.segment)
            if state_failed:
                yield TurnFailed(turn_id=turn_id, seq=seq + 1, reason="state_unavailable")
                return
            if self.workout is not None and decision.stop_workout:
                seq += 1
                yield WorkoutStateEvent(turn_id=turn_id, seq=seq, state=stopped_view)
            seq += 1
            if cancel is not None and cancel.is_set():
                yield TurnCancelled(turn_id=turn_id, seq=seq, reason="request_cancelled")
                return
            if decision.terminal == "cancelled":
                yield TurnCancelled(turn_id=turn_id, seq=seq, reason="user_stop")
            else:
                yield TurnCompleted(turn_id=turn_id, seq=seq)
            return

        context = TrustedContext()
        if self.workout is not None:
            try:
                # Authenticate the bound scope even for a non-workout conversation turn.
                state = self.workout.repository.get(self.workout.actor)
                context = TrustedContext(
                    WorkoutContext.from_state(state) if state else None, tuple(self._history),
                    self._preferences,
                )
                if self.conversational and request.text.strip().casefold() == "/clear":
                    self._history.clear()
                    self._preferences = StylePreferences()
                    yield SpeechEvent(
                        turn_id=turn_id, seq=seq + 1,
                        segment=say(
                            "History cleared; address reset to sir. Your workout state is unchanged."
                        ),
                    )
                    yield TurnCompleted(turn_id=turn_id, seq=seq + 2)
                    return
                if looks_like_shell_command(request.text):
                    yield SpeechEvent(
                        turn_id=turn_id, seq=seq + 1,
                        segment=say("That looks like a PowerShell command. Run it outside Mira after /quit."),
                    )
                    yield TurnFailed(turn_id=turn_id, seq=seq + 2, reason="input_rejected")
                    return
                preference = address_request(request.text, self._preferences)
                if preference is not None:
                    self._preferences = preference
                    yield SpeechEvent(
                        turn_id=turn_id, seq=seq + 1,
                        segment=say(
                            f"Got it. I'll call you {preference.address}."
                            if preference.address is not None else "Of course. I'll drop that title."
                        ),
                    )
                    yield TurnCompleted(turn_id=turn_id, seq=seq + 2)
                    return
                reply = self.workout.handle(request.text, request.submission_id)
            except WorkoutError as error:
                seq += 1
                yield SpeechEvent(
                    turn_id=turn_id,
                    seq=seq,
                    segment=say(ERROR_MESSAGES.get(error.code, "Workout action rejected.")),
                )
                yield TurnFailed(
                    turn_id=turn_id,
                    seq=seq + 1,
                    reason="unauthorized" if error.code == "unauthorized" else "tool_rejected",
                )
                return
            except (sqlite3.Error, ValidationError):
                logger.warning("workout state unavailable")
                async for event in self._fallback(turn_id, seq, "state_unavailable", cancel):
                    yield event
                return
            if reply is not None:
                # Emit committed state even if the consumer cancels after mutation.
                seq += 1
                yield WorkoutStateEvent(turn_id=turn_id, seq=seq, state=reply.state)
                for segment in reply.segments:
                    if cancel is not None and cancel.is_set():
                        yield TurnCancelled(
                            turn_id=turn_id, seq=seq + 1, reason="request_cancelled"
                        )
                        return
                    seq += 1
                    yield SpeechEvent(turn_id=turn_id, seq=seq, segment=segment)
                if reply.record_count is not None:
                    try:
                        self.workout.repository.record_statement(
                            self.workout.actor, reply.record_count
                        )
                    except (WorkoutError, sqlite3.Error, ValidationError):
                        logger.warning("workout count receipt unavailable")
                        yield TurnFailed(turn_id=turn_id, seq=seq + 1, reason="state_unavailable")
                        return
                if cancel is not None and cancel.is_set():
                    yield TurnCancelled(turn_id=turn_id, seq=seq + 1, reason="request_cancelled")
                else:
                    yield TurnCompleted(turn_id=turn_id, seq=seq + 1)
                return

        try:
            candidates = await self._generate(request, cancel, context)
            if cancel is not None and cancel.is_set():
                yield TurnCancelled(turn_id=turn_id, seq=seq + 1, reason="request_cancelled")
                return
            if not isinstance(candidates, (list, tuple)) or not 1 <= len(candidates) <= 3:
                raise ValueError("invalid segment count")
            # Validate the entire reply before emitting any untrusted candidate.
            segments = [SpeechSegment.model_validate(candidate) for candidate in candidates]
        except asyncio.CancelledError:
            # This covers cancellation delivered while awaiting a cooperative provider.
            yield TurnCancelled(turn_id=turn_id, seq=seq + 1, reason="request_cancelled")
            return
        except TimeoutError:
            logger.warning("provider timeout")
            async for event in self._fallback(turn_id, seq, "provider_timeout", cancel):
                yield event
            return
        except ProviderBudgetExceeded:
            logger.warning("provider budget exceeded")
            async for event in self._fallback(turn_id, seq, "provider_budget_exceeded", cancel):
                yield event
            return
        except (ValidationError, ValueError, TypeError):
            logger.warning("provider candidate rejected", extra={"reason_code": "provider_invalid"})
            async for event in self._fallback(turn_id, seq, "provider_invalid", cancel):
                yield event
            return
        except Exception:  # noqa: BLE001 - providers are an untrusted failure boundary
            logger.error("provider failed", extra={"reason_code": "provider_error"})
            async for event in self._fallback(turn_id, seq, "provider_error", cancel):
                yield event
            return

        for segment in segments:
            if cancel is not None and cancel.is_set():
                yield TurnCancelled(turn_id=turn_id, seq=seq + 1, reason="request_cancelled")
                return
            seq += 1
            yield SpeechEvent(turn_id=turn_id, seq=seq, segment=segment)
        if cancel is not None and cancel.is_set():
            yield TurnCancelled(turn_id=turn_id, seq=seq + 1, reason="request_cancelled")
            return
        yield TurnCompleted(turn_id=turn_id, seq=seq + 1)

    async def _generate(
        self, request: BrainTurnRequest, cancel: asyncio.Event | None, context: TrustedContext
    ) -> Sequence[object]:
        generation = asyncio.create_task(self.provider.generate(request, context=context))
        cancellation = asyncio.create_task(cancel.wait()) if cancel is not None else None
        tasks = [generation] if cancellation is None else [generation, cancellation]
        try:
            if cancellation is not None:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if cancellation in done:
                    raise asyncio.CancelledError
            return await generation
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _fallback(
        self, turn_id: str, seq: int, reason: FailureReason, cancel: asyncio.Event | None
    ) -> AsyncIterator[BrainEvent]:
        if cancel is not None and cancel.is_set():
            yield TurnCancelled(turn_id=turn_id, seq=seq + 1, reason="request_cancelled")
            return
        yield SpeechEvent(
            turn_id=turn_id,
            seq=seq + 1,
            segment=SpeechSegment(
                text=(
                    "The spending limit blocks this reply. Please review the budget settings."
                    if reason == "provider_budget_exceeded"
                    else "Sorry, I missed that. Please say it again."
                ),
                emotion=Emotion.NEUTRAL,
                intensity=0.3,
            ),
        )
        if cancel is not None and cancel.is_set():
            yield TurnCancelled(turn_id=turn_id, seq=seq + 2, reason="request_cancelled")
            return
        yield TurnFailed(turn_id=turn_id, seq=seq + 2, reason=reason)
