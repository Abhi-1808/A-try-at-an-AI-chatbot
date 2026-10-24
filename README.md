# Project Hope brain

An original AI companion brain prototype with offline mode by default. Prompt 01 implements
validated versioned events, an async provider interface, a deterministic mock,
a development intake policy, and a multi-turn NDJSON CLI. Prompt 02 adds an optional Anthropic adapter.
Mock mode uses no API keys or network services.

## Setup (Windows PowerShell)

Python 3.12 or 3.13 and `uv` are needed. Python 3.12.8 was used here because
3.13 was not installed.

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv312'
uv sync --locked --inexact --extra dev --python 3.12
& .venv312/Scripts/python.exe -m hope_brain.cli --provider mock
```

Enter multiple messages, then `/quit`. Only event JSON goes to stdout. The
startup instruction goes to stderr. In PowerShell, a short automated demo is:

```powershell
"Hi`n/quit" | & .venv312/Scripts/python.exe -m hope_brain.cli --provider mock
```

Actual stdout from one `Hi` demo (IDs change on each run):

```jsonl
{"v":1,"turn_id":"7bbfe3dc-f759-41eb-a789-b6e86cd2066b","seq":1,"type":"turn.started"}
{"v":1,"turn_id":"7bbfe3dc-f759-41eb-a789-b6e86cd2066b","seq":2,"type":"speech.segment","segment":{"text":"Hey there! What shall we explore today?","emotion":"playful","intensity":0.6}}
{"v":1,"turn_id":"7bbfe3dc-f759-41eb-a789-b6e86cd2066b","seq":3,"type":"turn.completed"}
```

## Checks

```powershell
& .venv312/Scripts/python.exe -m pytest -q
& .venv312/Scripts/ruff.exe check .
```

The schemas and event contract are documented in [event protocol](docs/event_protocol_v1.md).
The original character baseline is [persona v1](docs/persona_v1.md). The
[architecture decision](docs/adr/0001-offline-modular-brain.md) and
[threat model](docs/threat_model_v1.md) describe current boundaries.

For live-provider installation, configuration, costs, and an explicitly opt-in
smoke test, see [live provider](docs/live_provider.md).

The CLI now supports [authoritative workout commands](docs/workout_commands.md)
and opt-in SQLite workout storage. General personal memory, API server, and
voice/avatar remain unimplemented. Its safety rules remain a development baseline only.

See [milestone review](docs/milestone_01_review.md) for verified results and remaining work.

Current progress and verification: [Prompt 02 review](docs/milestone_02_review.md).

[Workout review](docs/milestone_04_review.md) and [voice entry gates](docs/release_gates.md).
