"""Narrow local command grammar and server-authored workout replies."""

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import TypeAdapter, ValidationError

from hope_brain.contracts import Emotion, SpeechSegment
from hope_brain.workout import (
    Actor,
    ConfirmTargetChange,
    ProposeTarget,
    ToolRequest,
    WorkoutAction,
    WorkoutError,
    WorkoutRepository,
    WorkoutState,
    WorkoutView,
)

_ACTION: TypeAdapter[WorkoutAction] = TypeAdapter(WorkoutAction)


@dataclass(frozen=True)
class WorkoutReply:
    segments: tuple[SpeechSegment, ...]
    state: WorkoutView | None
    record_count: WorkoutState | None = None


def say(text: str, emotion: Emotion = Emotion.NEUTRAL) -> SpeechSegment:
    return SpeechSegment(
        text=text, emotion=emotion, intensity=0.8 if emotion == Emotion.CHEERING else 0.4
    )


ERROR_MESSAGES = {
    "unauthorized": "This workout session is not authorized.",
    "duplicate_submission": "That submission was already recorded. Nothing was counted again.",
    "stale_version": "The workout changed. Check its current status before retrying.",
    "wrong_set": "That request belongs to a different set.",
    "unknown_state": "What are we training today? Start a workout first.",
    "set_closed": "This set is closed. Start a new set when ready.",
    "already_active": "A set is already active. End it before starting another.",
    "invalid_increment": "That update exceeds the agreed target or the set is complete.",
    "invalid_target": "Choose a different target, no lower than your completed reps.",
    "target_cap": "Each increase is limited to three reps, twice per set.",
    "proposal_not_found": "That proposal is no longer pending. Request a new proposal.",
    "action_not_authorized": "Only you can confirm a target change or record reps.",
    "invalid_command": "Use the documented workout commands; I won't guess an action.",
}


class WorkoutController:
    def __init__(self, repository: WorkoutRepository, actor: Actor) -> None:
        self.repository = repository
        self.actor = actor

    def _reply(
        self, state: WorkoutState | None, *segments: SpeechSegment, record_count: bool = False
    ) -> WorkoutReply:
        return WorkoutReply(
            tuple(segments),
            WorkoutView.from_state(state) if state else None,
            state if record_count else None,
        )

    def _status(self, state: WorkoutState | None) -> WorkoutReply:
        if state is None:
            return self._reply(None, say("What are we training today?"))
        if state.status in {"ended", "stopped"}:
            return self._reply(
                state, say("This set is closed. Start another only when you're ready.")
            )
        return self._reply(
            state,
            say(
                f"{state.remaining} reps remain.",
                Emotion.CHEERING if state.status == "completed" else Emotion.NEUTRAL,
            ),
            record_count=True,
        )

    def handle(self, text: str, submission_id: UUID) -> WorkoutReply | None:
        words = text.casefold().strip(" .!?").replace("\u2019", "'")
        status = words in {
            "/workout status",
            "how many left",
            "how many reps left",
            "reps left",
            "explain your maths",
            "that makes no sense",
        }
        target_query = words == "what's my target"
        history = words in {"/workout history", "did you just move my target"}
        callback = re.fullmatch(
            r"you said (\d{1,3}) reps ago (?:it was )?only (\d{1,3}) (?:reps )?left", words
        )
        increment = re.fullmatch(r"i did (\d+)(?: reps)?", words)
        extension = words == "just 3 more"
        command = words == "/workout" or words.startswith("/workout ")
        if not (status or target_query or history or callback or increment or extension or command):
            if re.search(r"\b(reps?|workout|target)\b", words):
                return self._reply(
                    self.repository.get(self.actor),
                    say("Please use a workout command so I don't guess your intent."),
                )
            return None
        state = self.repository.get(self.actor)
        if target_query:
            if state is None:
                return self._status(None)
            return self._reply(state, say(f"Your confirmed target is {state.target} reps."))
        if status:
            return self._status(state)
        if history:
            if state is None:
                return self._status(None)
            if not state.goal_history:
                return self._reply(state, say("Your target has not changed during this set."))
            change = state.goal_history[-1]
            return self._reply(
                state,
                say(f"The target changed from {change.old_target} to {change.new_target}."),
                say("You explicitly confirmed that change."),
            )
        if callback:
            if state is None:
                return self._status(None)
            ago, remaining = map(int, callback.groups())
            match = next(
                (
                    s
                    for s in reversed(state.statements)
                    if state.reps_done - s.reps_done == ago and s.remaining == remaining
                ),
                None,
            )
            if match is None:
                return self._reply(
                    state, say("I can't verify that earlier count from the recorded statements.")
                )
            first = say(f"I reported {remaining} left; you've recorded {ago} reps since.")
            current = say(f"{state.remaining} reps remain against your confirmed target.")
            if match.target != state.target:
                return self._reply(
                    state, first, say("You confirmed a target change after that count."), current
                )
            return self._reply(state, first, current)
        try:
            if increment:
                raw = {"type": "update_reps", "increment": int(increment.group(1))}
            elif extension:
                if state is None:
                    return self._status(None)
                raw = {"type": "propose_target", "target": state.target + 3}
            else:
                parts = words.split()
                if len(parts) == 4 and parts[1] == "start":
                    raw = {"type": "start_workout", "exercise": parts[2], "target": int(parts[3])}
                elif len(parts) == 3 and parts[1] in {"reps", "propose", "confirm"}:
                    if parts[1] == "reps":
                        raw = {"type": "update_reps", "increment": int(parts[2])}
                    elif parts[1] == "propose":
                        raw = {"type": "propose_target", "target": int(parts[2])}
                    else:
                        raw = {"type": "confirm_target_change", "proposal_id": parts[2]}
                elif parts == ["/workout", "end"]:
                    raw = {"type": "end_workout"}
                else:
                    raise WorkoutError("invalid_command")
            action = _ACTION.validate_python(raw)
        except (ValueError, ValidationError):
            raise WorkoutError("invalid_command") from None
        request = ToolRequest(
            command_id=uuid4(),
            submission_id=submission_id,
            set_id=None if action.type == "start_workout" else state.set_id if state else None,
            expected_version=state.version if state else 0,
            action=action,
        )
        result = self.repository.apply(self.actor, request, origin="user")
        if isinstance(action, ProposeTarget):
            return self._reply(
                result,
                say(
                    f"Proposed target: {action.target}. Your current target stays {result.target}."
                ),
                say("Confirm the proposal ID to approve that change."),
            )
        if isinstance(action, ConfirmTargetChange):
            return self._reply(result, say(f"Confirmed. Your target is now {result.target} reps."))
        if action.type == "start_workout":
            return self._reply(
                result, say(f"Started {result.exercise} with your target of {result.target} reps.")
            )
        if action.type == "end_workout":
            return self._reply(result, say("Set ended. Thanks for telling me.", Emotion.TENDER))
        if result.status == "completed":
            return self._reply(
                result, say("Set complete. You reached your agreed target!", Emotion.CHEERING)
            )
        return self._reply(
            result,
            say(f"Recorded {action.increment} reps."),
            say(f"{result.remaining} reps remain."),
            record_count=True,
        )
