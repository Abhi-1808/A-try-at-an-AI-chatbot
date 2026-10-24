"""Versioned synthetic character evaluation. Offline by default; no paid judge."""

import argparse
import asyncio
import io
import json
import logging
import math
import re
import statistics
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hope_brain.context import TrustedContext
from hope_brain.contracts import BrainEvent, BrainTurnRequest, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.persona import PERSONA_VERSION
from hope_brain.provider import DeterministicMockProvider, ModelProvider
from hope_brain.workout import Actor
from hope_brain.workout_store import SQLiteWorkoutRepository

type Check = Literal[
    "ai_identity", "no_boss_final", "remaining_three", "completion_cheer", "safety_stop",
]
type Metric = str | float | int
TERMINALS = {"turn.completed", "turn.failed", "turn.cancelled"}
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u20E3]")
DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "evals" / "character_v1.json"


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    setup: list[str] = Field(default_factory=list)
    turns: list[str]
    max_words: int = Field(default=14, ge=1, le=100)
    checks: list[Check] = Field(default_factory=list)
    review: list[str]
    unsupported: str | None = None


class Corpus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["mira-character-v1"]
    pilot: list[str]
    scenarios: list[Scenario]

    @model_validator(mode="after")
    def consistent_ids(self) -> "Corpus":
        ids = [case.id for case in self.scenarios]
        if len(ids) != len(set(ids)) or len(self.pilot) != len(set(self.pilot)):
            raise ValueError("duplicate scenario IDs")
        if set(self.pilot) - set(ids):
            raise ValueError("unknown pilot scenario")
        if any(not case.turns and not case.unsupported for case in self.scenarios):
            raise ValueError("empty scenario needs an explicit unsupported reason")
        return self


class TurnResult(BaseModel):
    text: str
    events: list[BrainEvent]
    first_segment_ms: float | None
    elapsed_ms: float
    model_calls: int
    provider_metrics: dict[str, Metric]
    issues: list[str]


class ScenarioResult(BaseModel):
    id: str
    title: str
    status: Literal["pass", "fail", "unsupported"]
    setup: list[TurnResult] = Field(default_factory=list)
    turns: list[TurnResult] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    review_checklist: list[str]
    human_review: Literal["pending"] = "pending"


class EvalReport(BaseModel):
    corpus_version: str
    persona_version: str = PERSONA_VERSION
    provider: str
    automatic_passed: int
    selected_scenarios: int
    automatic_pass_rate: float
    unsupported: int
    model_calls: int
    successful_model_latency_samples: int
    model_first_segment_p50_ms: float | None
    model_first_segment_p95_ms: float | None
    human_review: Literal["pending"] = "pending"
    results: list[ScenarioResult]


def check_events(raw: Sequence[object], max_words: int) -> list[str]:
    """Mechanical checks only. Word counting is whitespace based, not a persona judge."""
    try:
        events = [brain_event_adapter.validate_python(item) for item in raw]
    except ValidationError:
        return ["event_schema"]
    if not events:
        return ["no_events"]
    issues = []
    if [event.seq for event in events] != list(range(1, len(events) + 1)):
        issues.append("sequence")
    if len({event.turn_id for event in events}) != 1:
        issues.append("turn_identity")
    if events[0].type != "turn.started" or sum(e.type == "turn.started" for e in events) != 1:
        issues.append("start_event")
    if sum(e.type in TERMINALS for e in events) != 1 or events[-1].type not in TERMINALS:
        issues.append("terminal_count_or_order")
    if events[-1].type != "turn.completed":
        issues.append("turn_not_completed")
    segments = [e.segment for e in events if e.type == "speech.segment"]
    if not 1 <= len(segments) <= 3:
        issues.append("segment_count")
    if any(len(segment.text.split()) > max_words for segment in segments):
        issues.append("word_limit")
    if any(EMOJI.search(segment.text) for segment in segments):
        issues.append("emoji")
    return issues


class MeasuredProvider:
    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider
        self.calls = 0
        self.metrics: dict[str, Metric] = {}

    async def generate(
        self, request: BrainTurnRequest, *, context: TrustedContext | None = None,
    ) -> Sequence[object]:
        self.calls += 1
        self.metrics = {}
        try:
            return await self.provider.generate(request, context=context)
        finally:
            # Local adapter exposes only redacted metrics, never model reasoning.
            self.metrics = dict(getattr(self.provider, "last_metrics", {}))


def spoken(turn: TurnResult) -> str:
    return " ".join(e.segment.text for e in turn.events if e.type == "speech.segment")


async def run_suite(
    provider: ModelProvider, corpus: Corpus, *, pilot: bool = False, provider_name: str = "mock",
    emit: Callable[[BrainEvent], None] | None = None,
    notice: Callable[[str], None] | None = None,
) -> EvalReport:
    measured = MeasuredProvider(provider)
    results: list[ScenarioResult] = []
    for case in corpus.scenarios:
        if pilot and case.id not in corpus.pilot:
            continue
        result = ScenarioResult(
            id=case.id, title=case.title, status="pass", review_checklist=case.review,
        )
        results.append(result)
        if case.unsupported:
            result.status = "unsupported"
            result.issues.append(case.unsupported)
            continue
        if notice:
            notice(f"Scenario {case.id}: {case.title}")
        store = SQLiteWorkoutRepository()
        actor = Actor(user_id=str(uuid4()), session_id=str(uuid4()))
        store.register_session(actor)
        orchestrator = TurnOrchestrator(
            measured, workouts=store, actor=actor, conversational=True,
        )

        async def turn(
            text: str, max_words: int, orchestrator: TurnOrchestrator = orchestrator,
            session_id: str = actor.session_id,
        ) -> TurnResult:
            started = perf_counter()
            first = None
            previous_calls = measured.calls
            measured.metrics = {}
            events = []
            async for event in orchestrator.stream(
                BrainTurnRequest(session_id=session_id, text=text),
            ):
                if event.type == "speech.segment" and first is None:
                    first = round((perf_counter() - started) * 1000, 3)
                events.append(event)
                if emit:
                    emit(event)
            return TurnResult(
                text=text, events=events, first_segment_ms=first,
                elapsed_ms=round((perf_counter() - started) * 1000, 3),
                model_calls=measured.calls - previous_calls, provider_metrics=measured.metrics,
                issues=check_events(events, max_words),
            )

        try:
            for text in case.setup:
                result.setup.append(await turn(text, 80))
            for text in case.turns:
                result.turns.append(await turn(text, case.max_words))
            state = store.get(actor)
            last = result.turns[-1]
            final_text = spoken(last).casefold()
            for check in case.checks:
                passed = False
                if check == "ai_identity":
                    passed = bool(re.search(r"\bai\b|artificial intelligence", final_text))
                elif check == "no_boss_final":
                    passed = not re.search(r"\b(boss|sir)\b", final_text)
                elif check == "remaining_three":
                    passed = (
                        state is not None and state.target == 12 and state.remaining == 3
                        and "3 reps remain" in final_text and "reported 6" in final_text
                    )
                elif check == "completion_cheer":
                    passed = (
                        state is not None and state.status == "completed" and state.target == 12
                        and any(e.type == "speech.segment" and e.segment.emotion == "cheering"
                                and e.segment.intensity >= 0.7 for e in last.events)
                    )
                elif check == "safety_stop":
                    passed = (
                        state is not None and state.status == "stopped"
                        and last.model_calls == 0 and "stop exercising" in final_text
                        and all(e.segment.emotion == "neutral" for e in last.events
                                if e.type == "speech.segment")
                    )
                if not passed:
                    result.issues.append(check)
            if any(t.issues for t in result.setup + result.turns) or result.issues:
                result.status = "fail"
        finally:
            store.close()
        if notice:
            notice(f"Scenario {case.id}: automatic {result.status}; human review pending")

    # Include successful setup model calls, exclude deterministic and failed replies.
    samples = sorted(
        t.first_segment_ms for r in results for t in r.setup + r.turns
        if t.model_calls and t.events[-1].type == "turn.completed" and t.first_segment_ms is not None
    )
    passed_count = sum(r.status == "pass" for r in results)
    return EvalReport(
        corpus_version=corpus.version, provider=provider_name, automatic_passed=passed_count,
        selected_scenarios=len(results),
        automatic_pass_rate=passed_count / len(results) if results else 0,
        unsupported=sum(r.status == "unsupported" for r in results), model_calls=measured.calls,
        successful_model_latency_samples=len(samples),
        model_first_segment_p50_ms=round(statistics.median(samples), 3) if samples else None,
        model_first_segment_p95_ms=samples[math.ceil(len(samples) * 0.95) - 1] if samples else None,
        results=results,
    )


async def run() -> int:
    parser = argparse.ArgumentParser(description="Synthetic Mira character evaluation (no paid API)")
    parser.add_argument("--provider", choices=["mock", "ollama"], default="mock")
    parser.add_argument("--pilot", action="store_true", help="Select the eight-case local pilot")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--report", type=Path, help="Save synthetic prompts/replies; refuses overwrite")
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("Report already exists; choose a new output file.")
    try:
        corpus = Corpus.model_validate_json(args.corpus.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        parser.error("Cannot read the versioned evaluation corpus.")
    provider: ModelProvider = DeterministicMockProvider()
    local = None
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="%(message)s")
    try:
        if args.provider == "ollama":
            from hope_brain.ollama_provider import OllamaProvider
            from hope_brain.settings import OllamaSettings

            local = OllamaProvider(OllamaSettings.from_env())
            await local.check_ready()
            provider = local
        report = await run_suite(
            provider, corpus, pilot=args.pilot,
            provider_name=f"ollama/{local.settings.model}" if local else "mock",
            emit=lambda event: print(brain_event_adapter.dump_json(event).decode(), flush=True),
            notice=lambda text: print(text, file=sys.stderr, flush=True),
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as handle:
                handle.write(report.model_dump_json(indent=2) + "\n")
        print(json.dumps(report.model_dump(exclude={"results"}), indent=2), file=sys.stderr)
        return int(report.automatic_passed != report.selected_scenarios)
    except Exception:  # noqa: BLE001 - do not expose provider bodies or configuration
        print("Evaluation could not finish. Check local setup and report path.", file=sys.stderr)
        return 2
    finally:
        if local:
            await local.aclose()


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(asyncio.run(run()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
