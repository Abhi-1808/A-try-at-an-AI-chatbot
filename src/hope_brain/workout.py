"""Typed workout commands and pure state transitions. No model authority."""

from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Target = Annotated[int, Field(strict=True, ge=1, le=100)]
Origin = Literal["user", "model"]
Exercise = Literal["pushups", "squats", "situps", "pullups"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class Actor(Record):
    """Identity supplied by trusted application code, never by model output."""

    user_id: Identifier
    session_id: Identifier


class StartWorkout(Record):
    type: Literal["start_workout"] = "start_workout"
    exercise: Exercise
    target: Target


class UpdateReps(Record):
    type: Literal["update_reps"] = "update_reps"
    increment: int = Field(strict=True, ge=1, le=20)


class ProposeTarget(Record):
    type: Literal["propose_target"] = "propose_target"
    target: Target
    reason: Literal["user_request", "optional_extension", "correction"] = "user_request"


class ConfirmTargetChange(Record):
    type: Literal["confirm_target_change"] = "confirm_target_change"
    proposal_id: UUID


class EndWorkout(Record):
    type: Literal["end_workout"] = "end_workout"


WorkoutAction = Annotated[
    StartWorkout | UpdateReps | ProposeTarget | ConfirmTargetChange | EndWorkout,
    Field(discriminator="type"),
]


class ToolRequest(Record):
    command_id: UUID
    submission_id: UUID
    set_id: UUID | None
    expected_version: int = Field(strict=True, ge=0)
    action: WorkoutAction


class TargetProposal(Record):
    proposal_id: UUID
    old_target: Target
    new_target: Target
    reason: Literal["user_request", "optional_extension", "correction"]
    actor: Origin
    proposed_at: datetime
    reps_at_proposal: int = Field(ge=0)


class GoalChange(TargetProposal):
    confirmed_by: Identifier
    confirmed_at: datetime
    reps_at_confirmation: int = Field(ge=0)


class RepUpdate(Record):
    increment: int = Field(ge=1, le=20)
    total: int = Field(ge=1, le=100)
    actor: Identifier
    at: datetime


class CountStatement(Record):
    reps_done: int = Field(ge=0, le=100)
    target: Target
    at: datetime

    @property
    def remaining(self) -> int:
        return self.target - self.reps_done


class WorkoutState(Record):
    set_id: UUID
    exercise: Exercise
    reps_done: int = Field(strict=True, ge=0, le=100)
    target: Target
    status: Literal["active", "completed", "ended", "stopped"]
    version: int = Field(strict=True, ge=1)
    updated_at: datetime
    last_confirmed_update: RepUpdate | None = None
    updates: tuple[RepUpdate, ...] = ()
    pending_proposal: TargetProposal | None = None
    goal_history: tuple[GoalChange, ...] = ()
    target_proposals: tuple[TargetProposal, ...] = ()
    statements: tuple[CountStatement, ...] = ()

    @property
    def remaining(self) -> int:
        return self.target - self.reps_done

    @property
    def raises_used(self) -> int:
        return sum(change.new_target > change.old_target for change in self.goal_history)

    @model_validator(mode="after")
    def check_invariants(self) -> "WorkoutState":
        if self.reps_done > self.target:
            raise ValueError("reps exceed target")
        if self.status == "active" and self.remaining == 0:
            raise ValueError("completed set cannot be active")
        if self.status == "completed" and self.remaining != 0:
            raise ValueError("incomplete set cannot be completed")
        if self.raises_used > 2 or any(c.new_target - c.old_target > 3 for c in self.goal_history):
            raise ValueError("target increase cap exceeded")
        return self


class WorkoutView(Record):
    """Client-safe snapshot; excludes identity and audit actor details."""

    set_id: UUID
    exercise: Exercise
    reps_done: int = Field(strict=True, ge=0, le=100)
    target: Target
    remaining: int = Field(strict=True, ge=0, le=100)
    status: Literal["active", "completed", "ended", "stopped"]
    version: int = Field(strict=True, ge=1)
    raises_used: int = Field(strict=True, ge=0, le=2)
    pending_proposal: TargetProposal | None

    @model_validator(mode="after")
    def check_remaining(self) -> "WorkoutView":
        if self.remaining != self.target - self.reps_done:
            raise ValueError("remaining does not match authoritative counts")
        return self

    @classmethod
    def from_state(cls, state: WorkoutState) -> "WorkoutView":
        return cls(
            set_id=state.set_id,
            exercise=state.exercise,
            reps_done=state.reps_done,
            target=state.target,
            remaining=state.remaining,
            status=state.status,
            version=state.version,
            raises_used=state.raises_used,
            pending_proposal=state.pending_proposal,
        )


class WorkoutError(Exception):
    """Fixed, non-sensitive reason codes only."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def revise(state: WorkoutState, **changes: object) -> WorkoutState:
    return WorkoutState.model_validate(state.model_dump() | changes)


def validate_target(state: WorkoutState, target: int) -> None:
    if target < state.reps_done or target == state.target:
        raise WorkoutError("invalid_target")
    if target > state.target and (target - state.target > 3 or state.raises_used >= 2):
        raise WorkoutError("target_cap")


def reduce_workout(
    state: WorkoutState | None,
    request: ToolRequest,
    actor: Actor,
    origin: Origin,
    *,
    now: datetime,
    new_id: UUID,
) -> WorkoutState:
    """Pure transition; caller supplies trusted time, ID and authenticated actor."""
    action = request.action
    if origin not in {"user", "model"} or (
        origin == "model" and not isinstance(action, ProposeTarget)
    ):
        raise WorkoutError("action_not_authorized")
    if request.expected_version != (state.version if state else 0):
        raise WorkoutError("stale_version")
    if isinstance(action, StartWorkout):
        if request.set_id is not None:
            raise WorkoutError("wrong_set")
        if state is not None and state.status == "active":
            raise WorkoutError("already_active")
        return WorkoutState(
            set_id=new_id,
            exercise=action.exercise,
            reps_done=0,
            target=action.target,
            status="active",
            version=request.expected_version + 1,
            updated_at=now,
        )
    if state is None:
        raise WorkoutError("unknown_state")
    if request.set_id != state.set_id:
        raise WorkoutError("wrong_set")
    if state.status in {"ended", "stopped"}:
        raise WorkoutError("set_closed")
    changes: dict[str, object] = {"version": state.version + 1, "updated_at": now}
    if isinstance(action, UpdateReps):
        if state.status != "active" or state.reps_done + action.increment > state.target:
            raise WorkoutError("invalid_increment")
        update = RepUpdate(
            increment=action.increment,
            total=state.reps_done + action.increment,
            actor=actor.user_id,
            at=now,
        )
        changes.update(
            reps_done=update.total,
            last_confirmed_update=update,
            updates=(*state.updates, update),
            pending_proposal=None,
            status="completed" if update.total == state.target else "active",
        )
    elif isinstance(action, ProposeTarget):
        validate_target(state, action.target)
        proposal = TargetProposal(
            proposal_id=new_id,
            old_target=state.target,
            new_target=action.target,
            reason=action.reason,
            actor=origin,
            proposed_at=now,
            reps_at_proposal=state.reps_done,
        )
        changes.update(
            pending_proposal=proposal, target_proposals=(*state.target_proposals, proposal)
        )
    elif isinstance(action, ConfirmTargetChange):
        pending = state.pending_proposal
        if pending is None or action.proposal_id != pending.proposal_id:
            raise WorkoutError("proposal_not_found")
        validate_target(state, pending.new_target)
        change = GoalChange(
            **pending.model_dump(),
            confirmed_by=actor.user_id,
            confirmed_at=now,
            reps_at_confirmation=state.reps_done,
        )
        changes.update(
            target=change.new_target,
            goal_history=(*state.goal_history, change),
            pending_proposal=None,
            status="completed" if state.reps_done == change.new_target else "active",
        )
    else:
        changes.update(status="ended", pending_proposal=None)
    return revise(state, **changes)


class WorkoutRepository(Protocol):
    def get(self, actor: Actor, set_id: UUID | None = None) -> WorkoutState | None: ...
    def apply(self, actor: Actor, request: ToolRequest, *, origin: Origin) -> WorkoutState: ...
    def record_statement(self, actor: Actor, state: WorkoutState) -> WorkoutState: ...
    def stop(self, actor: Actor) -> WorkoutState | None: ...
