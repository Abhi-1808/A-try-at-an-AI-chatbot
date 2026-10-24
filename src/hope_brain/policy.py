"""Development baseline intake policy, not clinical or comprehensive safety coverage."""

import re
from dataclasses import dataclass
from typing import Literal

from hope_brain.contracts import Emotion, SpeechSegment


@dataclass(frozen=True)
class PolicyDecision:
    segment: SpeechSegment
    terminal: Literal["completed", "cancelled"]
    reason: Literal["user_stop"] | None = None
    stop_workout: bool = False


_DANGER = re.compile(
    r"\b(chest(?:\s+(?:is|feels?|kinda|kind of|a bit|really|very))*\s+"
    r"(?:hurts?|pain|tight(?:ness)?|discomfort)|"
    r"dizz(?:y|iness)|lightheaded|faint(?:ing)?|"
    r"(?:trouble|difficulty|hard time) breathing|"
    r"(?:pain|hurts?|injur(?:y|ed))\b)",
    re.IGNORECASE,
)
_STOP_ACTIVITY = re.compile(
    r"^\s*(?:please\s+)?(?:stop|quit|end|cancel)\s*"
    r"(?:[.!?]|$|(?:the\s+)?(?:workout|exercise|exercising|training|session|activity|"
    r"talking|chatting|responding)\b)",
    re.IGNORECASE,
)


def intake_policy(text: str) -> PolicyDecision | None:
    """Recognize a narrow set of clear safety and stop intents."""
    if _DANGER.search(text):
        return PolicyDecision(
            segment=SpeechSegment(
                text=(
                    "Stop exercising and rest now. If symptoms are severe, persistent, "
                    "or include chest pain or breathing trouble, seek urgent medical help."
                ),
                emotion=Emotion.NEUTRAL,
                intensity=0.2,
            ),
            terminal="completed",
            stop_workout=True,
        )
    if _STOP_ACTIVITY.search(text):
        return PolicyDecision(
            segment=SpeechSegment(
                text="Okay. We'll stop this activity now.",
                emotion=Emotion.TENDER,
                intensity=0.3,
            ),
            terminal="cancelled",
            reason="user_stop",
            stop_workout=not bool(re.search(r"\b(talking|chatting|responding)\b", text, re.IGNORECASE)),
        )
    return None
