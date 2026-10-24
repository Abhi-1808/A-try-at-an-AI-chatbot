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

_SHELL_COMMAND = re.compile(
    r"^\s*(?:&\s|\$env:|PS\s+[A-Z]:\\|\.\\[^\s]+\.ps1\b|"
    r"(?:ollama\s+(?:serve|pull|run|list|ls|ps)|uv\s+(?:sync|run)|"
    r"(?:python|python3|python\.exe)\s+-(?:m|c)\b|Set-Location\b|pip\s+install\b))",
    re.IGNORECASE,
)


def looks_like_shell_command(text: str) -> bool:
    return bool(_SHELL_COMMAND.search(text))


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
        conversation_stop = bool(re.search(r"\b(talking|chatting|responding)\b", text, re.IGNORECASE))
        return PolicyDecision(
            segment=SpeechSegment(
                text=(
                    "Okay. I'll stop talking now."
                    if conversation_stop else "Okay. We'll stop this activity now."
                ),
                emotion=Emotion.TENDER,
                intensity=0.3,
            ),
            terminal="cancelled",
            reason="user_stop",
            stop_workout=not conversation_stop,
        )
    return None
