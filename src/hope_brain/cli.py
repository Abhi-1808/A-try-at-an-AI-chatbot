"""NDJSON CLI; live generation requires explicit provider selection."""

import argparse
import asyncio
import io
import logging
import sqlite3
import sys
from typing import TYPE_CHECKING
from uuid import uuid4

from hope_brain.contracts import BrainTurnRequest, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.provider import DeterministicMockProvider, ModelProvider
from hope_brain.settings import AnthropicSettings, ConfigurationError
from hope_brain.workout import Actor, WorkoutError
from hope_brain.workout_store import SQLiteWorkoutRepository

if TYPE_CHECKING:
    from hope_brain.anthropic_provider import AnthropicProvider as LiveProvider


async def run() -> int:
    parser = argparse.ArgumentParser(description="Project Hope brain")
    parser.add_argument("--provider", choices=["mock", "anthropic"], default="mock")
    parser.add_argument(
        "--live-smoke", action="store_true", help="Explicitly run one paid test turn"
    )
    parser.add_argument("--workout-db", help="Opt in to saving workout state in this SQLite file")
    args = parser.parse_args()
    if args.live_smoke and args.provider != "anthropic":
        parser.error("--live-smoke requires --provider anthropic")

    live: LiveProvider | None = None
    provider: ModelProvider = DeterministicMockProvider()
    if args.provider == "anthropic":
        try:
            settings = AnthropicSettings.from_env()
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

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    session_id = str(uuid4())
    actor = Actor(user_id=str(uuid4()), session_id=session_id)
    try:
        workouts = SQLiteWorkoutRepository(args.workout_db or ":memory:")
        workouts.register_session(actor)
    except (sqlite3.Error, WorkoutError):
        if live is not None:
            await live.aclose()
        parser.error("Could not open workout storage. Check the path and permissions.")
    orchestrator = TurnOrchestrator(provider, workouts=workouts, actor=actor)
    print("Enter a sentence, or /quit to exit.", file=sys.stderr)
    exit_code = 0
    try:
        lines = ["Hi"] if args.live_smoke else sys.stdin
        for raw in lines:
            text = raw.strip()
            if text.casefold() == "/quit":
                break
            if not text:
                continue
            request = BrainTurnRequest(session_id=session_id, text=text)
            async for event in orchestrator.stream(request):
                print(brain_event_adapter.dump_json(event).decode("utf-8"), flush=True)
                if args.live_smoke and event.type in {"turn.failed", "turn.cancelled"}:
                    exit_code = 1
    finally:
        workouts.close()
        if live is not None:
            await live.aclose()
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
