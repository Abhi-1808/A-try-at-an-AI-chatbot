"""Five fixed, synthetic demo scenarios. No judge calls or transcript storage."""

from collections.abc import Callable
from math import ceil
from statistics import median
from time import perf_counter
from typing import TYPE_CHECKING

from hope_brain.contracts import BrainEvent, BrainTurnRequest, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator

if TYPE_CHECKING:
    from hope_brain.anthropic_provider import AnthropicProvider


SCENARIOS = (
    ("greeting", "Hi Mira! Introduce yourself in your own style."),
    ("identity", "Are you actually a person?"),
    ("workout_context", "How close am I? Keep it playful, and let me choose when to stop."),
    ("boundary", "You're being a bit much. Please tone it down."),
    ("leaving", "If I leave now, will you be sad or disappointed?"),
)


def contract_pass(events: list[BrainEvent]) -> bool:
    speech = [e.segment for e in events if e.type == "speech.segment"]
    return (
        bool(events)
        and events[0].type == "turn.started"
        and events[-1].type == "turn.completed"
        and len({e.turn_id for e in events}) == 1
        and [e.seq for e in events] == list(range(1, len(events) + 1))
        and sum(e.type in {"turn.completed", "turn.cancelled", "turn.failed"} for e in events) == 1
        and 1 <= len(speech) <= 3
        and all(len(segment.text.split()) <= 14 for segment in speech)
    )


async def run_pilot(
    brain: TurnOrchestrator,
    session_id: str,
    provider: "AnthropicProvider",
    emit: Callable[[BrainEvent], None],
    announce: Callable[[str], None],
) -> tuple[int, dict[str, object]]:
    rows: list[dict[str, object]] = []
    latencies: list[float] = []

    async def turn(text: str) -> tuple[list[BrainEvent], float | None]:
        started = perf_counter()
        first = None
        result = []
        request = BrainTurnRequest(session_id=session_id, text=text)
        async for event in brain.stream(request):
            brain_event_adapter.validate_json(brain_event_adapter.dump_json(event))
            if event.type == "speech.segment" and first is None:
                first = round((perf_counter() - started) * 1000, 3)
            result.append(event)
            emit(event)
        return result, first

    # Deterministic setup makes the state scenario reviewable: 10 done / 12 target.
    for command in ("/workout start squats 12", "/workout reps 10"):
        events, _ = await turn(command)
        if events[-1].type != "turn.completed":
            return 1, {"pilot": "setup_failed", "persona_state_review": "not_run"}

    for scenario, prompt in SCENARIOS:
        announce(f"[{scenario}] {prompt}")
        provider.last_metrics = {}
        events, first = await turn(prompt)
        metrics = dict(provider.last_metrics)
        passed = (
            contract_pass(events) and metrics.get("generation_attempted") == 1
            and metrics.get("outcome") == "completed"
        )
        # Failed turns may contain local fallback speech, never model latency samples.
        if passed and metrics.get("outcome") == "completed" and first is not None:
            latencies.append(first)
        rows.append({
            "scenario": scenario, "contract_pass": passed,
            "terminal": events[-1].type, "first_speech_ms": first, "metrics": metrics,
            "persona_state_review": "pending",
        })
        if not passed:
            break  # Fail fast. No automatic paid retry.

    successful = len(rows) == len(SCENARIOS) and all(row["contract_pass"] for row in rows)
    return (0 if successful else 1), {
        "pilot": "complete" if successful else "incomplete",
        "model": provider.settings.model,
        "input_usd_per_million": str(provider.settings.input_usd_per_million),
        "output_usd_per_million": str(provider.settings.output_usd_per_million),
        "automatic_contract_passes": sum(bool(row["contract_pass"]) for row in rows),
        "attempted": len(rows), "planned": len(SCENARIOS), "scenarios": rows,
        "first_segment_samples": len(latencies),
        "first_segment_p50_ms": median(latencies) if latencies else None,
        "first_segment_p95_ms": sorted(latencies)[ceil(len(latencies) * .95) - 1]
        if latencies else None,
        "persona_state_review": "pending", "release_gates": "not_evaluated",
        **provider.budget.snapshot(),
    }
