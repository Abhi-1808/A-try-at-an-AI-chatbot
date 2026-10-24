# General conversation with a local model

Mock mode answers from a few fixed rules. Local chat instead asks a real language
model to generate answers about study, ideas, coding, everyday questions and other
topics. It supports follow-up questions using recent conversation. A small local
model will not match every capability or answer quality of ChatGPT or Gemini.

No paid API key is needed. The code is implemented and tested with HTTP fixtures;
real inference needs Ollama plus a downloaded model. Neither has been installed
by this change. The CLI never downloads a model or falls back to paid/cloud inference.

## Setup on this Windows PC

Hardware checks reported 15.3 GB RAM and AMD Radeon (TM) Graphics. GPU acceleration
and response speed are unverified. `qwen3:4b` is the starting configuration, not a
performance guarantee. Its official [model listing](https://ollama.com/library/qwen3:4b)
reports a 2.5 GB download and Apache 2.0 licensing (checked 2026-10-24). Runtime and
context memory need additional space. Ollama's [Windows documentation](https://docs.ollama.com/windows)
lists at least 4 GB for the runtime installation plus model storage.

1. Install Ollama from its [official Windows download](https://ollama.com/download/windows).
2. Quit an existing Ollama tray instance before starting the local-only server below.
3. In a PowerShell window, run these commands and leave the server window open:

```powershell
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
ollama serve
```

In a second PowerShell window, download the model once:

```powershell
ollama pull qwen3:4b
```

From the Project Hope folder, install the optional HTTP client and launch Mira:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv312'
uv sync --locked --inexact --extra dev --extra local --python 3.12
& .\scripts\Start-Mira.ps1 -Local
```

The runtime serves only this PC. No sign-in or key is required for the
[local API](https://docs.ollama.com/api/authentication); `OLLAMA_NO_CLOUD=1`
[disables cloud features](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).
The app ignores proxy/host environment overrides, rejects redirects, inspects the
model before each prompt, and rejects reported remote/cloud aliases.

Try unrelated questions and follow-ups:

```text
Explain why the sky is blue.
Can you explain that more simply?
Help me plan a 30-minute study session.
What is a target market?
Tell me a short story about a robot gardener.
/clear
/quit
```

`-Local` cannot be combined with `-Mock` or the paid `-Pilot`. To use another
downloaded local model: `& .\scripts\Start-Mira.ps1 -Local -Model 'MODEL:TAG'`.
Direct CLI use is `python -m hope_brain.cli --provider ollama --chat`.

## Conversation and workout behavior

- The app retains at most eight completed exchanges and 12,000 UTF-8 bytes of
  conversation in RAM. Oldest exchanges drop out first. Failed, cancelled and
  incompletely consumed turns are not retained. History is private to the bound
  authorized session, even when a model provider is shared.
- `/clear` deletes that conversation history. It does not change workout state.
  Exiting discards history; it is never written to SQLite or diagnostic logs.
- General questions containing "workout", "reps" or "target" can now reach the
  model in local chat. Commands such as `/workout reps 5` remain authoritative;
  the model itself cannot record reps or change a target. Ambiguous natural-language
  action requests should result in guidance to use a command, not a state mutation.
- Local chat allows fuller answers, up to three speech paragraphs, instead of
  prompting for at most 14 words. Each segment remains a validated single line of
  text. The original compact persona/pilot configuration remains unchanged.
- Earlier dialogue is untrusted context. The current app-owned workout snapshot
  overrides earlier numeric claims. Generated numeric claims are not semantically
  verified and do not become count receipts; that limitation remains.
- Safety and stop rules still run before generation. Their keyword matching remains
  a development baseline and can misclassify figurative or quoted discussion.

The model has no web browsing, file access, code execution, long-term personal
memory, voice or avatar. It can make factual mistakes, and it may be slow on this PC.
First-run loading can take longer; the 180-second total request timeout is not a
latency target or benchmark. Ctrl+C cancels local waiting and closes the connection;
it does not promise immediate model unloading or that computation stops instantly.

## Local settings

| Variable | Default / limit |
| --- | --- |
| `HOPE_OLLAMA_MODEL` | `qwen3:4b`, must already be downloaded |
| `HOPE_OLLAMA_PORT` | `11434`, always connects to `127.0.0.1` |
| `HOPE_OLLAMA_MAX_TOKENS` | `768`, allowed 64-2048 |
| `HOPE_OLLAMA_TIMEOUT_SECONDS` | `180`, maximum 300 seconds |

Input is bounded to 8,192 UTF-8 bytes and each HTTP response to 262,144 bytes.
The model receives an 8,192-token context option; byte limits are not exact token
counts. The adapter requests no thinking output, no tools, a JSON schema and no
streamed model output, then validates the full response before emitting events.
Only timing/outcome and valid token-count metrics are logged. `--chat` itself
intentionally displays replies on stderr; capturing that stream saves dialogue.

Sources: Ollama [chat API](https://docs.ollama.com/api/chat),
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs), and
[model metadata definitions](https://github.com/ollama/ollama/blob/main/api/types.go).
