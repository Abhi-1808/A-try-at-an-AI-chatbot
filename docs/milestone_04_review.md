# Workout milestone review - 24 October 2026

## Scope and outcome

The user prioritized authoritative workout state/tools and requested messy-input
safety tests. Implemented Prompt 04/B3 now; Prompt 03 persona and evaluation work
remains pending. The production architecture_v2.md reference is still absent.
The supplied source-pack PDF was inspected for its target cap and scenario IDs.

We now have typed start_workout, update_reps, propose_target,
confirm_target_change and end_workout actions, a pure reducer, a repository
interface, and SQLite persistence/migration with transactional ownership,
version, set-scope and duplicate-delivery protection. The current provider does
not invoke tools. A model-origin proposal cannot confirm or change real counts.

Ten of twelve deterministically means two remaining. Target changes require
explicit confirmation; increases are capped at three reps and twice per set.
Proposal and confirmation history records old/new targets, reasons, actor/source
and timestamps. Superseded or invalidated proposals remain inspectable. Numeric
workout responses come from server state, including evidence-backed callbacks.

The CLI defaults to in-memory state. --workout-db explicitly enables local disk
storage, with new local identities per CLI launch. Authorized repository callers
can restore an existing session; a user-facing CLI resume flow is not implemented.
No general memory, summaries, forget command, API server, voice, or deployment
was added. No real-model or judge calls were made.

## Changed files

- src/hope_brain/workout.py: typed actions/state/views, pure reducer and repository interface.
- src/hope_brain/workout_store.py: SQLite schema v1, ownership, atomic state/receipts, audit records.
- src/hope_brain/workout_intents.py: narrow deterministic commands and factual replies.
- src/hope_brain/contracts.py: submission ID, workout.state event and safe reason codes.
- src/hope_brain/orchestrator.py: bound actor, tool routing and durable safety stops before provider calls.
- src/hope_brain/policy.py: chest tightness with conversational filler; exercise/chat stop distinction.
- src/hope_brain/cli.py: local actor lifecycle and explicitly selected disk storage.
- tests/test_workout.py and tests/test_workout_turns.py: state, race, authorization, policy and CLI tests.
- pyproject.toml and uv.lock: tested mypy floor and TypeForm support for Pydantic union annotations.
  No runtime dependency was added or upgraded.
- .gitignore: SQLite file/journal patterns.
- README.md, docs/event_protocol_v1.md, docs/scenario_status_v1.md,
  docs/workout_commands.md, docs/release_gates.md,
  docs/adr/0003-authoritative-workouts.md and this review.

## Actual verification

Python 3.12.8; commands run at the repository root:

```powershell
& .\.venv312\Scripts\python.exe -m pytest -q
# 146 passed in 7.91s
& .\.venv312\Scripts\ruff.exe check .
# All checks passed!
& .\.venv312\Scripts\python.exe -m mypy src/hope_brain
# Success: no issues found in 12 source files
& .\.venv-mock-check\Scripts\python.exe -m pytest -q
# 115 passed, 1 skipped in 3.30s (optional SDK module absent)
uv lock --check --offline
# Resolved 29 packages; exit 0
```

The type checker initially retained stale metadata after enabling experimental
TypeForm support required by the installed Pydantic annotations. A clean run:
`python -m mypy --no-incremental --enable-incomplete-feature=TypeForm src/hope_brain`
passed, followed by the normal command above. The tests include the actual SDK
with an in-memory HTTP transport; none measures real-model persona quality.

A subprocess CLI smoke session ran start pushups 12, I did 5 twice, How many
left?, propose 15, history, and the messy chest-tightness example. It validated
31 JSON events across seven turns. Observed: two reps remaining, target still
12 without confirmation, final status stopped, pending proposal cleared.

Reproduce the basic offline demo:

```powershell
"/workout start pushups 12`nI did 5`nI did 5`nHow many left?`n/workout propose 15`nugh my chest is kinda tight`n/quit" | & .\.venv312\Scripts\python.exe -m hope_brain.cli
```

## Highest-impact review checks

1. Duplicate and concurrent updates: tested separate SQLite connections; only one
   same-version mutation commits. Receipt failure rolls state back atomically.
2. Ownership and authority: foreign/unknown sessions, wrong sets, stale versions
   and model-origin mutations are rejected; only proposals may originate from a model.
3. Target safety: two increases of at most three, explicit proposal confirmation,
   no reset via decreases, and no count above target. All proposal history survives.
4. State honesty: ambiguous requests preserve known snapshots; target queries return
   target, not remaining; callback evidence is not recorded before delivery.
5. Stop handling: both messy examples bypass the provider, invalidate proposals,
   and stop the latest state. Stop persists if a consumer closes after safety speech.
   Storage failures still emit safety guidance and a valid failure terminal.

## Limits and next task

These are deterministic fixtures, not evidence that the full safety group or
real-model persona passes. Arbitrary transcript understanding, substantive output
safety, live state-grounded generation, personal memory and all voice gates remain
pending. Local SQL is synchronous with a five-second lock timeout; contention can
delay speech. State is user-reported, not sensor-confirmed. Disk data is unencrypted.
No public authentication exists; application-supplied actors are the service trust
boundary. Closed consumers cannot receive further terminal events.

The repository has no committed baseline and remains untracked; sources were
reviewed directly. No commits, infrastructure changes or deployments were made.

Next small task: Prompt 03's character bible and versioned offline behavior corpus,
with mechanical scoring separated from human/model judging. Later live evaluation
must have a selected model and total-run spend cap that includes judge calls.
See release_gates.md: 90% overall, 100% safety, real first-segment p50 under 700 ms;
p95 must also be reported. All three gates remain unverified.
