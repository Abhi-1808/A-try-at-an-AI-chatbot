# Prompt 01 review - 24 October 2026

## Scope and existing work

Reviewed the supplied implementation prompt pack and repository AGENTS.md.
The repository already contains the offline modular brain: Pydantic contracts,
async provider interface, deterministic mock, intake policy, orchestrator,
NDJSON CLI, persona/protocol/threat-model documents, and 21 passing tests.
This review finishes the current Prompt 01 milestone; Prompts 02-08 remain pending.
The architecture_v2.md reference is absent. No substitute production plan was invented.
The PDF scenario definitions were not independently verified in this review.

## Findings and changes

- Confirmed: constructed or mutated SpeechSegment instances bypassed validation.
  Enable instance revalidation at the candidate schema boundary; invalid objects
  now produce valid fallback speech and one provider_invalid terminal event.
- Confirmed: explicit stop talking/chatting/responding requests reached the mock.
  Recognize these stop commands, preserving the existing preference exception.
- Verified: cancellation between segments works in the current orchestrator.
  Added a regression test; preserved its existing implementation.
- Coverage gap: the previous offline test did not actually block network access.
  Added a socket/DNS guard during brain execution, after Windows event-loop setup.
  Added malformed output shape and diagnostic privacy checks.
- Setup mismatch: README commands used .venv, which contains Python 3.14 here.
  Updated commands to the verified .venv312 environment (Python 3.12.8).

## Verification

Executed from the repository root:

```powershell
& .\.venv312\Scripts\python.exe -m pytest -q
& .\.venv312\Scripts\ruff.exe check .
"Hi`nStop talking`n/quit" | & .\.venv312\Scripts\python.exe -m hope_brain.cli --provider mock
```

Baseline: 21 tests passed. After regression tests and fixes: 33 passed;
Ruff reported All checks passed. The CLI demo emitted six JSON events:
a completed greeting turn and a cancelled stop turn, each with seq 1, 2, 3.
The automated CLI test separately validates stdout JSON and stderr separation.
No live model call, deployment, new dependency, or persistent memory was introduced.

## Limits and next task

Fresh installation and Python 3.13/3.14 compatibility were not verified in this
review. Existing rule-based safety remains a development baseline, with known
paraphrase and quotation limitations. Cancellation via an Event is checked at
boundaries; it does not interrupt a provider while generate is still awaiting.
No authentication or workout state exists, so ownership/tool tests belong to
later milestones. Files are untracked and the repository has no initial commit;
Git cannot supply a historical baseline diff. No commit was created.

Next small task: Prompt 02's configuration-gated real provider adapter, with
mocked transport tests and no live call without explicit opt-in. Persona evals,
authoritative workout state, opt-in memory, safety hardening, API transport,
and performance measurement remain subsequent milestones.
