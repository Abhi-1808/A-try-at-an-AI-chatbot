"""Untrusted model candidates; providers never create client events."""

from collections.abc import Sequence
from typing import Protocol

from hope_brain.contracts import BrainTurnRequest, Emotion, SpeechSegment


class ProviderBudgetExceeded(Exception):
    """The configured estimate exceeds the per-turn budget."""


class ModelProvider(Protocol):
    async def generate(self, request: BrainTurnRequest) -> Sequence[object]: ...


class DeterministicMockProvider:
    async def generate(self, request: BrainTurnRequest) -> Sequence[object]:
        words = request.text.casefold()
        if "are you an ai" in words or "are you a bot" in words:
            return [
                SpeechSegment(
                    text="Yes, I'm an AI companion. Happy to help!",
                    emotion=Emotion.TENDER,
                    intensity=0.5,
                )
            ]
        if "stop calling me sir" in words:
            return [
                SpeechSegment(
                    text="Of course. I won't call you that.", emotion=Emotion.TENDER, intensity=0.5
                )
            ]
        if "how many" in words or "reps left" in words:
            return [
                SpeechSegment(
                    text="What are we training today?", emotion=Emotion.NEUTRAL, intensity=0.4
                )
            ]
        if "sad if i leave" in words or "i'm leaving" in words:
            return [
                SpeechSegment(
                    text="Take care! You can leave whenever you like.",
                    emotion=Emotion.TENDER,
                    intensity=0.5,
                )
            ]
        if words.strip(" !?.") in {"hi", "hello", "hey"}:
            return [
                SpeechSegment(
                    text="Hey there! What shall we explore today?",
                    emotion=Emotion.PLAYFUL,
                    intensity=0.6,
                )
            ]
        return [
            SpeechSegment(
                text="I'm listening. Tell me a little more?", emotion=Emotion.PLAYFUL, intensity=0.5
            )
        ]
