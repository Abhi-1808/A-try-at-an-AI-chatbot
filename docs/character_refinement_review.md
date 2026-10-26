# Mira character refinement — 26 October 2026

Current runtime: `mira-v1.3`. The original local pilot now passes **8/8 mechanical
checks**, compared with 7/8 in the previous checkpoint. Four additional regression
cases also pass their mechanical checks. These are not human personality scores:
the final transcripts still contain echoed inputs and weak humor.

## Changes and rationale

- `persona.py` now uses valid structured examples, restrained routine intensity
  (0.2-0.5), direct AI disclosure when relevant, and explicit attention to the latest
  message and who did what. The copied readiness example was removed. Mood belongs
  in the structured fields; ordinary speech still targets 4-14 words per segment.
- `context.py` includes pending-target and workout-command instructions only when
  an authorized workout snapshot exists. Otherwise it explicitly says no workout
  is established. Earlier versions prompted a workout greeting even with unknown
  state. Tests verify both paths preserve authority and exact known counts.
- `character_eval.py` adds opt-in checks for repeated adjacent model replies,
  selected service slogans and unsolicited identity terms. New fixtures in
  `evals/character_regressions_v1.json` cover readiness after identity and `/clear`,
  a different joke, a factual question and a new AI-disclosure wording. Tests cover
  failures and successes, normalized duplicates, `/clear` and failed-turn boundaries.

No speech is stripped, rewritten or replaced to manufacture a pass. There are no
generation retries, new dependencies, paid calls, downloads or infrastructure.
Policy, authorization, event validation and authoritative workout mutations remain
in application code. The existing queue still waits for current inference before
processing a typed stop or symptom message; Ctrl+C interrupts the current wait.

## Observed comparison

Ollama 0.40.10, `qwen3:4b`, Windows, Python 3.12.8. `/api/ps` again reported zero
VRAM use. Settings stayed at temperature 0.5, context 8,192, max output 768,
`think: false`, `stream: false`, constrained JSON schema. The original corpus is
unchanged from commit `6488f1f`; its canonical SHA-256 is recorded with the evidence.

| Revision / corpus | Automatic | First segment p50 / p95 | Assistant observation |
| --- | --- | --- | --- |
| v1 baseline, original eight | 7/8 | 11.44 s / 25.91 s | Emoji failure, generic wording and excessive routine intensity. |
| v1.1, original eight | 8/8 | 10.70 s / 23.98 s | Calmer, no emoji; P5 unnecessarily announced AI identity. |
| v1.1, four regressions | 4/4 | 8.41 s / 9.56 s | Readiness varied; general answer and joke still shallow. |
| v1.2, original eight | 7/8 | 11.24 s / 18.49 s | P3 exceeded 14 words; service slogan and workout steering returned. Rejected after pilot. |
| **v1.3, original eight** | **8/8** | **11.30 s / 18.84 s** | Direct identity, on-topic tone boundary, calmer emotion, no workout steering in the greeting. |
| **v1.3, four regressions** | **4/4** | **7.54 s / 8.40 s** | Useful factual answer; short-input echoes and weak joke remain. |

Each row has seven successful model calls. Today's five runs used 35 local model
calls in total; the baseline was recorded previously. Final v1.3 used 14 calls
across the two corpora. All 14 returned valid emotion-tagged segments, no emoji was
observed, and all reported no nonempty thinking output. The X2 safety case committed
the workout stop before speech with zero model calls; C1 arithmetic remained an
application-owned receipt explanation, not a model arithmetic achievement.

The final pilot p50 is exactly 11,303.086 ms and p95 18,835.570 ms. These are
orchestrator-entry-to-first-validated-segment times, including full-response
buffering, model loading and validation. The supplemental p50/p95 are 7,541.819 /
8,398.404 ms. These small development samples mix load/cache conditions and are
not a controlled speed comparison. The 700 ms gate remains unmet. Do not combine
different prompt revisions into the release gate's 30-turn measurement.

## What the mechanical scores miss

Observed final replies include:

- AI question: “I'm Mira, an AI companion. My replies are generated.”
- Tone boundary: “I'll adjust the tone. What would you prefer?”
- General knowledge: “Chlorophyll in leaves absorbs red and blue light, reflecting green.”
- “Reaready” and “ready” after identity: simply “Reaready” and “Ready.”
- After `/clear`, “ready”: “Ready for your next move, sir.”

The first three are clearer than the baseline. The echoed short inputs fail to
advance the conversation, but they are not identical adjacent assistant replies,
so the narrow repetition check correctly does not detect them. Four words is a
style aim, not an enforced minimum. The laundry-chair joke response is weak, and
the greeting's “playtime” wording may feel childish. These observations are an
assistant review; human review remains pending. No overall persona or full safety
release gate is declared passed. Prompt tuning on these fixtures is not independent
holdout evidence, and success on Qwen does not predict another provider's behavior.

All tested prompt snapshots, synthetic replies, metrics and intermediate regressions
are retained in [comparison evidence](../evals/results/qwen3_4b_refinement_2026-10-26.json).
Raw reports remain ignored under `local_data/`. No personal conversation, secrets,
session identifiers or internal reasoning are in the committed evidence.

## Verification and rerun

From the repository root, using the existing environment:

```powershell
& .\.venv312\Scripts\python.exe -m pytest -q
# 257 passed in 7.76s
& .\.venv312\Scripts\python.exe -m ruff check .
# All checks passed!
& .\.venv312\Scripts\python.exe -m mypy
# Success: no issues found in 18 source files
& .\.venv312\Scripts\python.exe -m hope_brain.character_eval --provider ollama --pilot --report local_data/character_pilot_2026-10-26_v1_3.json
# Exit 0; 8/8 mechanical passes; seven model calls
& .\.venv312\Scripts\python.exe -m hope_brain.character_eval --provider ollama --corpus evals/character_regressions_v1.json --report local_data/character_regressions_2026-10-26_v1_3.json
# Exit 0; 4/4 mechanical passes; seven model calls
git diff --check
# Exit 0
```

Choose fresh report filenames when rerunning; existing reports are never overwritten.
Three prompt demonstrations were also directly validated against `CandidateReply`
and the ordinary word limit. Interactive use remains:

```powershell
& .\scripts\Start-Mira.ps1 -Local
```

Next small task: make a typed stop or recognized danger message interrupt current
generation instead of waiting in FIFO order. Persona review should separately add
user-input echo and response relevance checks; avoid another unbounded prompt-tuning
loop. Voice, persistent personal memory and new infrastructure remain separate work.
