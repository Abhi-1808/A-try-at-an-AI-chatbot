"""NDJSON CLI; live generation requires explicit provider selection."""

import argparse
import asyncio
import io
import json
import logging
import sqlite3
import sys
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from hope_brain.contracts import BrainEvent, BrainTurnRequest, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.provider import DeterministicMockProvider, ModelProvider
from hope_brain.settings import AnthropicSettings, ConfigurationError, OllamaSettings
from hope_brain.workout import Actor, WorkoutError
from hope_brain.workout_store import SQLiteWorkoutRepository

if TYPE_CHECKING:
    from hope_brain.anthropic_provider import AnthropicProvider as LiveProvider
    from hope_brain.ollama_provider import OllamaProvider as LocalProvider


async def run() -> int:
    parser = argparse.ArgumentParser(description="Project Hope brain")
    parser.add_argument("--provider", choices=["mock", "anthropic", "ollama"], default="mock")
    parser.add_argument(
        "--live-smoke", action="store_true", help="Explicitly run one paid test turn"
    )
    parser.add_argument("--workout-db", help="Opt in to saving workout state in this SQLite file")
    parser.add_argument("--chat", action="store_true", help="Display Mira's speech on stderr")
    parser.add_argument("--live-pilot", action="store_true", help="Run five paid demo scenarios")
    args = parser.parse_args()
    if args.live_smoke and args.provider != "anthropic":
        parser.error("--live-smoke requires --provider anthropic")
    if args.live_pilot and (args.provider != "anthropic" or args.live_smoke):
        parser.error("--live-pilot requires --provider anthropic and excludes --live-smoke")

    live: LiveProvider | None = None
    local: LocalProvider | None = None
    provider: ModelProvider = DeterministicMockProvider()
    if args.provider == "anthropic":
        try:
            settings = AnthropicSettings.from_env()
            if args.live_pilot and (
                settings.session_budget_usd > Decimal("0.05")
                or settings.turn_budget_usd > Decimal("0.01")
            ):
                parser.error("Pilot limits: HOPE_SESSION_BUDGET_USD <= 0.05; "
                             "HOPE_TURN_BUDGET_USD <= 0.01")
            # Keep the optional SDK out of offline startup and imports.
            from hope_brain.anthropic_provider import AnthropicProvider

            live = AnthropicProvider(settings)
            provider = live
        except ConfigurationError as error:
            parser.error(str(error))
        except ImportError:
            parser.error("Install the anthropic extra to use --provider anthropic.")
        except Exception:  # noqa: BLE001 - never expose SDK configuration or credentials
            parser.error("Could not initialize the live provider. Check your configuration.")

    if args.provider == "ollama":
        try:
            local_settings = OllamaSettings.from_env()
            from hope_brain.ollama_provider import OllamaProvider

            local = OllamaProvider(local_settings)
            await local.check_ready()
            provider = local
        except ImportError:
            if local is not None:
                await local.aclose()
            parser.error("Install the local extra to use --provider ollama; see docs/local_chat.md.")
        except ConfigurationError as error:
            if local is not None:
                await local.aclose()
            parser.error(str(error))
        except Exception:  # noqa: BLE001 - do not print server error bodies
            if local is not None:
                await local.aclose()
            parser.error("Could not initialize local chat. See docs/local_chat.md.")

    logging.basicConfig(
        level=logging.WARNING if args.chat else logging.INFO,
        stream=sys.stderr, format="%(message)s",
    )
    session_id = str(uuid4())
    actor = Actor(user_id=str(uuid4()), session_id=session_id)
    try:
        workouts = SQLiteWorkoutRepository(args.workout_db or ":memory:")
        workouts.register_session(actor)
    except (sqlite3.Error, WorkoutError):
        if live is not None:
            await live.aclose()
        if local is not None:
            await local.aclose()
        parser.error("Could not open workout storage. Check the path and permissions.")
    orchestrator = TurnOrchestrator(
        provider, workouts=workouts, actor=actor, conversational=args.provider == "ollama"
    )
    print("Enter a sentence, or /quit to exit.", file=sys.stderr)
    if local is not None:
        print("Local chat remembers recent turns in memory. /clear clears the conversation.",
              file=sys.stderr)
    exit_code = 0

    def emit(event: BrainEvent) -> None:
        print(brain_event_adapter.dump_json(event).decode("utf-8"), flush=True)
        if args.chat and event.type == "speech.segment":
            print(f"Mira: {event.segment.text}", file=sys.stderr, flush=True)
        if args.chat and event.type == "workout.state" and event.state is not None:
            proposal = event.state.pending_proposal
            if proposal is not None:
                print(
                    f"To approve target {proposal.new_target}, enter: "
                    f"/workout confirm {proposal.proposal_id}",
                    file=sys.stderr, flush=True,
                )
        if args.chat and event.type == "turn.failed":
            print(f"Turn failed: {event.reason}", file=sys.stderr, flush=True)

    try:
        if args.live_pilot:
            from hope_brain.pilot import run_pilot

            assert live is not None
            exit_code, report = await run_pilot(
                orchestrator, session_id, live, emit,
                lambda text: print(text, file=sys.stderr, flush=True),
            )
            print(json.dumps(report, indent=2), file=sys.stderr, flush=True)
            return exit_code
        lines = ["Hi"] if args.live_smoke else sys.stdin
        for raw in lines:
            text = raw.strip()
            if text.casefold() == "/quit":
                break
            if not text:
                continue
            request = BrainTurnRequest(session_id=session_id, text=text)
            async for event in orchestrator.stream(request):
                emit(event)
                if args.live_smoke and event.type in {"turn.failed", "turn.cancelled"}:
                    exit_code = 1
    finally:
        workouts.close()
        if live is not None:
            await live.aclose()
        if local is not None:
            await local.aclose()
    return exit_code


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(asyncio.run(run()))
    except KeyboardInterrupt:
        # A second interrupt may abort output; no private traceback is printed.
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
