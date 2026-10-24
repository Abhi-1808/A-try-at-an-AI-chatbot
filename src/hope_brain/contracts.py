"""Trusted, versioned client protocol and provider candidate schemas."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator

from hope_brain.workout import WorkoutView


class Emotion(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    PLAYFUL = "playful"
    SMUG = "smug"
    POUTY = "pouty"
    SAD = "sad"
    SHY = "shy"
    CHEERING = "cheering"
    TENDER = "tender"


NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class BrainTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: NonBlank
    text: NonBlank
    submission_id: UUID = Field(default_factory=uuid4)


class SpeechSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")

    text: NonBlank
    emotion: Emotion
    intensity: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("text")
    @classmethod
    def speakable_text(cls, value: str) -> str:
        if any(ord(char) < 32 for char in value):
            raise ValueError("speech cannot contain control characters")
        return value


class EventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: Literal[1] = 1
    turn_id: NonBlank
    seq: int = Field(ge=1)


class TurnStarted(EventBase):
    type: Literal["turn.started"] = "turn.started"


class SpeechEvent(EventBase):
    type: Literal["speech.segment"] = "speech.segment"
    segment: SpeechSegment


class TurnCompleted(EventBase):
    type: Literal["turn.completed"] = "turn.completed"


type FailureReason = Literal[
    "provider_invalid",
    "provider_error",
    "provider_timeout",
    "provider_budget_exceeded",
    "tool_rejected",
    "unauthorized",
    "state_unavailable",
]


class TurnFailed(EventBase):
    type: Literal["turn.failed"] = "turn.failed"
    reason: FailureReason


class TurnCancelled(EventBase):
    type: Literal["turn.cancelled"] = "turn.cancelled"
    reason: Literal["user_stop", "request_cancelled"]


class WorkoutStateEvent(EventBase):
    type: Literal["workout.state"] = "workout.state"
    state: WorkoutView | None


type BrainEvent = Annotated[
    TurnStarted | SpeechEvent | WorkoutStateEvent | TurnCompleted | TurnFailed | TurnCancelled,
    Field(discriminator="type"),
]
brain_event_adapter: TypeAdapter[BrainEvent] = TypeAdapter(BrainEvent)
