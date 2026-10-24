# Local general-chat review — 24 October 2026

The user reported that fixed mock replies were too limited and requested general
chatbot-style answers without having a paid API key. This change implements the
local-model path, broader question routing and temporary conversation context.

## Changed files

| Files | Change |
| --- | --- |
| `src/hope_brain/ollama_provider.py` | Optional asynchronous Ollama adapter, local model preflight, schema validation, bounded HTTP bodies, timeouts, cancellation and redacted metrics. |
| `src/hope_brain/settings.py`, `.env.example` | Local model, port, output limit and timeout configuration; no API key. |
| `src/hope_brain/context.py` | Conversation exchanges and a general-chat prompt that permits fuller explanations. |
| `src/hope_brain/orchestrator.py` | Session-scoped RAM history of at most eight completed exchanges / 12,000 UTF-8 bytes, plus `/clear`. |
| `src/hope_brain/workout_intents.py` | General questions no longer get intercepted just for containing workout words in local-chat mode. Generic follow-ups reach the model when there is no workout. Explicit state changes stay in application code. |
| `src/hope_brain/cli.py`, `scripts/Start-Mira.ps1` | `--provider ollama` and `-Local` modes, startup readiness checks, readable errors and cleanup. |
| `pyproject.toml`, `uv.lock` | `local` extra reuses already locked HTTPX2 2.16.0; package resolution stays at 29 packages. |
| `tests/test_conversation.py`, `test_ollama_provider.py`, `test_demo.py` | General routing, follow-ups, history limits/isolation/deletion, malformed responses, cloud rejection, timeout/cancellation, privacy, CLI and launcher tests. |
| `README.md`, `docs/live_demo.md`, `local_chat.md`, `adr/0005-local-general-conversation.md`, this review | Usage, setup, architecture choices, actual verification and limitations. |

## Actual verification

Using Python 3.12.8 from the repository root:

```powershell
& .\.venv312\Scripts\python.exe -m pytest -q
# 234 passed in 6.62s
& .\.venv312\Scripts\ruff.exe check .
# All checks passed!
& .\.venv312\Scripts\python.exe -m mypy src/hope_brain
# Success: no issues found in 15 source files
uv lock --check --offline
# Resolved 29 packages; exit 0
git diff --check
# Exit 0
```

The mock-only environment also ran successfully: `& .\.venv-mock-check\Scripts\python.exe
-m pytest -q` reported 156 passed, 2 skipped in 4.61 seconds before three additional
general-routing parameter cases were added. The two skipped modules require the
optional Anthropic/local HTTP adapters. No paid or real inference calls are made
by tests. An incremental Mypy cache initially produced a TypeForm error in the
existing workout union; the full `--no-incremental` check and subsequent normal
check both passed without changing that type definition.

The local adapter tests use the actual HTTP client against an in-memory transport.
They check successful replies, message roles, prior context, clear-history behavior,
private fields, input/body bounds, malformed JSON, unfinished generation, tool calls,
HTTP errors, no retry/redirect, cloud aliases, timeout, cancellation and HTTP cleanup.
The real PowerShell launcher is exercised with a temporary offline Python stub to
verify provider selection and environment restoration without an API key.

Diff review covered state authority, actor/session isolation, no history persistence,
model-data boundaries, no paid fallback, loopback requests, redacted error/log output
and dependency scope. A narrow scan of 49 source/config/docs files before this review
was added found no Anthropic key or private-key block. This is not a comprehensive
secret audit of the user's machine.

## Runtime status and next step

No Ollama service was reachable on `127.0.0.1:11434`. Runtime/model installation
has not been performed as part of the code changes. Therefore real response quality,
speed, GPU acceleration and the original persona/safety/latency release gates remain
unverified. The prepared [setup](local_chat.md) uses Qwen3 4B, whose model download
is about 2.5 GB, plus Ollama's runtime storage requirements.

General-chat mode is not full ChatGPT/Gemini feature parity: no browsing, file tools,
code execution, long-term personal memory, voice or avatar. It permits fuller answers
in up to three speech paragraphs, while the compact Anthropic pilot remains unchanged.
Generated claims can still be wrong. The development keyword safety matcher may
misclassify figurative/quoted content, and numeric model claims have no semantic guard.

Next: authorize/install the local runtime and model, then run actual multi-turn
conversations about unrelated topics and measure their behavior and response time.
