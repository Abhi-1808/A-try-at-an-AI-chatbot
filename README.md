# Project Hope brain

An original AI companion brain prototype with offline mode by default. Prompt 01 implements
validated versioned events, an async provider interface, a deterministic mock,
a development intake policy, and a multi-turn NDJSON CLI. Prompt 02 adds an optional Anthropic adapter.
Mock mode uses no API keys or network services.

The [revised architecture and milestone plan](docs/architecture_v2.md) makes Mira
a general assistant with a frontier cloud primary path and gym as a future skill.
The prepared paid launcher now selects Claude Sonnet 5.5; Qwen remains available
for offline development. Both real providers carry bounded recent conversation,
address preferences and `/clear`. Cloud mode sends this context to Anthropic.
Live cloud quality/latency remains unverified. Web/calculator/file tools, long-term
personal memory, routing and broader safety are planned, not implemented.

For open-ended answers and follow-up questions without a paid API key, use
[local chat with Ollama](docs/local_chat.md). After installing the runtime and
downloading a model, launch `& .\scripts\Start-Mira.ps1 -Local`. This mode retains
recent conversation in RAM and supports `/clear`. Mock mode remains scripted.
See the [local-chat review](docs/local_chat_review.md) for exact verification and limitations.

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

Without an API key, run `& .\scripts\Start-Mira.ps1 -Mock` for the free scripted
terminal demo. Workout state and safety/stop commands work; persona evaluation
still requires a real model.

With a paid key and credits, run `& .\scripts\Start-Mira.ps1 -Pilot` in PowerShell.
It prompts privately for a key and runs five real-model scenarios with a $0.05
cumulative estimate limit. See [terminal demo instructions](docs/live_demo.md)
for setup, human persona review, cost accounting and interactive chat.
The prepared demo has been tested offline; no paid pilot result is claimed.
See [demo review](docs/live_demo_review.md) for the earlier baseline and
[cloud-readiness review](docs/cloud_readiness_review.md) for this change.

The CLI now supports [authoritative workout commands](docs/workout_commands.md)
and opt-in SQLite workout storage. General personal memory, API server, and
voice/avatar remain unimplemented. Its safety rules remain a development baseline only.

See [milestone review](docs/milestone_01_review.md) for verified results and remaining work.

Current progress and verification: [Prompt 02 review](docs/milestone_02_review.md).

[Workout review](docs/milestone_04_review.md) and [voice entry gates](docs/release_gates.md).

Mira now uses a [versioned character bible](docs/character_bible_v1.md), session
address preferences and visible input queues. Run the free local
[eight-scenario character pilot](docs/character_eval.md) with:

```powershell
& .\.venv312\Scripts\python.exe -m hope_brain.character_eval --provider ollama --pilot --report local_data/character-pilot.json
```

Results and limitations: [character review](docs/character_review.md).
Current prompt and local comparison: [character refinement](docs/character_refinement_review.md).
