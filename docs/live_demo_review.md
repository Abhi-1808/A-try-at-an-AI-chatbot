# Bounded terminal demo review — 24 October 2026

The user prioritized a first visible real-model conversation, cumulative spending
controls, key hygiene and local Git commits. They then chose: "Prepare the pilot;
I'll run it myself." No paid call was made during this work.

## Existing work verified and checkpointed

The repository had no commits. Reviewed the existing source, tests, configuration
and docs; reran the baseline: 146 tests passed in 8.15 seconds and Ruff passed.
Created local baseline commit `c08289a` with 36 files. No remote push was requested
or performed. Git used the existing local identity configuration.

A narrow credential-pattern scan found no Anthropic key or private-key block in
the candidate files. Neither `.env` nor `.env.local` existed, and this process had
no API key or live model/rate configuration. This is not a comprehensive secret
audit or evidence about copies outside the repository. Existing ignore rules
already exclude `.env`, `.env.local`, databases and `local_data/`.

## Changes

| Files | Result |
| --- | --- |
| `src/hope_brain/spend.py`, `settings.py`, `anthropic_provider.py` | Required cumulative cap; locked reservations across concurrent turns; complete API usage reconciliation; retained uncertain reservations; future generation blocked on observed estimate overruns; redacted metrics. |
| `src/hope_brain/context.py`, `provider.py`, `orchestrator.py` | Separate trusted workout context, built after authorization; strips identifiers and audit details; distinguishes pending and confirmed targets; budget-specific fallback. |
| `src/hope_brain/pilot.py`, `cli.py` | Five fixed synthetic scenarios, two deterministic setup turns, <=14-word contract scoring, fail-fast behavior, first-segment p50/p95, pending human-review labels and optional readable speech on stderr. |
| `scripts/Start-Mira.ps1` | Hidden key entry, process-only settings, restored environment, $0.01 per-turn / $0.05 cumulative configuration, readable terminal display. |
| `.env.example` | Documents required `HOPE_SESSION_BUDGET_USD`. |
| `tests/test_demo.py`, `test_spend.py`, `test_anthropic_provider.py` | New authorization/context, budget, accounting, concurrency, pilot, privacy and launcher regression cases. |
| `tests/test_brain.py`, `test_configuration.py`, `test_workout_turns.py` | Adapt existing provider doubles to the separate context argument; preserve original behavior checks. |
| `README.md`, `docs/live_demo.md`, `live_provider.md`, `persona_v1.md`, `release_gates.md`, `threat_model_v1.md`, `adr/0004-bounded-terminal-demo.md`, this review | Run instructions, human-review rubric, current boundaries and decisions. Earlier milestone reviews remain historical records. |

No dependency or lockfile changes. No voice, avatar, infrastructure or personal
memory work was added. Python remains 3.12.8; 3.13/3.14 were not verified.

## Actual final verification

Commands run from the repository root:

```powershell
& .\.venv312\Scripts\python.exe -m pytest -q
# 180 passed in 10.30s

& .\.venv312\Scripts\ruff.exe check .
# All checks passed!

& .\.venv312\Scripts\python.exe -m mypy src/hope_brain
# Success: no issues found in 14 source files

& .\.venv-mock-check\Scripts\python.exe -m pytest -q
# 137 passed, 1 skipped in 5.46s (optional Anthropic transport module absent)

git diff --check
# Exit 0; no whitespace errors

git check-ignore -- .env .env.local local_data/pilot_report.json
# All three paths ignored
```

The initial sandboxed baseline test attempt could not load the installed Pydantic
DLL. The permission-approved rerun and final checks above completed successfully.
All model transport tests use in-memory HTTP fixtures, not Anthropic's service.

The PowerShell launcher test uses a synthetic key and a temporary Python module
that performs no network activity. It checks configuration, speech visibility,
discarded NDJSON, failure exit propagation, environment restoration and absence
of the synthetic key from output. The hidden interactive key prompt itself was
not manually exercised. PowerShell parsing also reported no syntax errors.

The five-scenario end-to-end CLI test exercised the actual SDK adapter against
mock HTTP: five generations, two local setup turns, valid NDJSON, correct 10/12
workout context, clean SDK shutdown and pending human-review labels. A failing
generation stops the pilot and does not contaminate model latency percentiles
with fallback timing. These mocked timings are not real-model performance evidence.

Final diff review covered authorization, private fields, malformed output,
cancellation accounting, optional imports, unchanged dependencies and scope.
The final credential-pattern scan found no matches in 43 source/config/docs files
before this review was added; no credentials or runtime artifacts are staged.

## Remaining limitations and next task

- No live personality, state-honesty, real-token billing or latency result exists.
  All original release gates remain pending. Five samples cannot establish them.
- The spend ledger is one provider/process lifetime. It resets on restart and is
  not shared between processes. Pricing errors or unknown provider accounting can
  exceed estimates; it is not an account-wide billing guarantee.
- General conversation history and persistent tone preferences are absent. Workout
  state is available, but model-written numeric speech has no semantic verifier and
  does not create count receipts. Human review must check that speech against 10/12.
- Basic danger/stop rules still run before the model, but remain a development
  baseline. The complete 33-scenario corpus, judge, memory/deletion and broader
  safety work are not implemented by this demo.
- `--chat` intentionally displays dialogue on stderr. Capturing that entire stream
  records dialogue as well as the sanitized final metrics report.

Next small task: the user runs `& .\scripts\Start-Mira.ps1 -Pilot` and reviews
the five replies against [the rubric](live_demo.md). Use those observations to
choose one targeted persona/context adjustment before expanding the evaluation.
