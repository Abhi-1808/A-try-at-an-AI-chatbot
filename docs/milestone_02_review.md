# Progress review - 24 October 2026

## What we have now

Prompt 01 supplied the modular offline brain: typed requests and events,
a deterministic original Mira mock, a development intake policy, an async
orchestrator, and a multi-turn CLI. The previous review fixed model-instance
validation and conversation stop handling, reaching 33 passing tests.

Prompt 02 is now implemented and verified offline. It adds an optional pinned
Anthropic SDK adapter with private async streaming, a separate trusted context
builder, environment configuration, estimated budget preflight, timeouts,
cooperative in-flight cancellation, zero automatic retries, and redacted metrics.
The CLI defaults to mock and supports an explicitly opt-in paid one-turn smoke
command. Unicode stdout is explicitly UTF-8 even on hosts configured for ASCII.

The live provider was not called. Real-model availability, quality, latency,
and actual billing remain unverified. There is still no workout state, tool
execution, persistent memory, HTTP server, voice, avatar, or deployment.

## Changed files in this milestone

- src/hope_brain/settings.py: typed required live settings and safe errors.
- src/hope_brain/context.py: separate trusted instructions and user message;
  strict candidate envelope.
- src/hope_brain/anthropic_provider.py: bounded SDK stream, cost preflight,
  token/timing diagnostics, resource closure, and no raw-content logging.
- src/hope_brain/provider.py: shared budget-exceeded signal without SDK imports.
- src/hope_brain/orchestrator.py: in-flight cancellation and safe failure handling.
- src/hope_brain/contracts.py: additive timeout and budget failure reason codes.
- src/hope_brain/cli.py: provider selection, configuration errors, optional smoke,
  client lifecycle, and UTF-8 standard streams.
- tests/test_configuration.py and tests/test_anthropic_provider.py: configuration,
  context isolation, SDK transport, privacy, stream validity, cancellation,
  network blocking, Unicode CLI, and explicit opt-in coverage.
- pyproject.toml and uv.lock: optional anthropic==2.3.0, dev mypy, locked dependencies.
- .gitignore: ignore type-checker cache; .env.example: empty credential/model/rates.
- README.md, docs/live_provider.md, docs/event_protocol_v1.md,
  docs/threat_model_v1.md, docs/adr/0002-opt-in-live-provider.md, and this review.

## Exact verification and actual results

All commands ran from the repository root on Python 3.12.8:

```powershell
& .\.venv312\Scripts\python.exe -m pytest -q
# 82 passed in 6.88s
& .\.venv312\Scripts\ruff.exe check .
# All checks passed (after an explicit check=False lint correction in a test).
& .\.venv312\Scripts\python.exe -m mypy src/hope_brain
# Success: no issues found in 9 source files
uv lock --check --offline
# Resolved 29 packages; exit 0
```

Fresh mock-only installation from cached locked packages:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv-mock-check'
uv sync --locked --offline --extra dev --python .venv312/Scripts/python.exe
& .\.venv-mock-check\Scripts\python.exe -m pytest -q
# 51 passed, 1 skipped in 2.12s
```

Confirmed the fresh environment does not contain the Anthropic SDK. The skipped
module is the optional SDK transport suite. Full coverage uses .venv312 with
both dev and anthropic extras. No paid generation or remote token-count call ran.

```powershell
"Hi`nStop talking`n/quit" | & .\.venv312\Scripts\python.exe -m hope_brain.cli --provider mock
```

The demo emitted six JSON events with completed and cancelled terminal events;
sequences were 1,2,3 per turn. Automated subprocess checks validate stdout and
Unicode, and an in-process fake-SDK CLI check covers both success and failure.

## Review findings and limitations

- Server code retains event/ID/sequence authority. Model output cannot execute
  tools or mutate goals, because those capabilities do not exist yet.
- Malformed, incomplete, oversized, tool-containing, and non-text streams are
  rejected before provider speech is emitted. Schema validity is not semantic
  safety; development intake filters can miss or misclassify requests.
- Context separation and log redaction are tested. No content is persisted.
  Live selection would transmit current input for both counting and generation.
- Cost estimates use configured rates, an input margin, maximum output tokens,
  and no retries. They are not hard provider billing caps or session-wide limits.
- Cancellation closes cooperative SDK streams; it cannot guarantee remote
  computation or charges stop. Abandoned consumers cannot receive a terminal.
- A regression exposed UnicodeEncodeError under ASCII host output; the CLI now
  reconfigures standard streams to UTF-8, and that subprocess test passes.
- Python 3.13/3.14 and live quality remain untested. architecture_v2.md is absent.
- Dependency setup initially recreated .venv as Python 3.12. Corrected the target
  to .venv312 and restored its pre-existing pypdf==6.21.2 package after uv sync
  removed it. Documented --inexact setup preserves unrelated packages in future.
- The repository remains untracked with no historical Git baseline; no commit
  or deployment was created. Current sources were reviewed directly.

## Next small task

Prompt 03: versioned character bible and offline conversation evaluation
fixtures, including human-review criteria for subjective personality quality.
Do not add tools or memory in that milestone. Stop here until the next task.
