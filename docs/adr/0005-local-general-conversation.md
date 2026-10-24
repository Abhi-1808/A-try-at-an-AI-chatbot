# ADR 0005: Local general conversation

Accepted 2026-10-24 in response to the user's request for chatbot-style answers
beyond fixed mock replies, after reporting that they have no paid API key.

Use an optional Ollama adapter against loopback HTTP. Reuse the already locked
HTTPX2 package through a `local` extra without requiring Anthropic or adding a
second HTTP client dependency. Runtime installation/model download are separate
from app startup; no automatic paid fallback or model pull.

Keep the ModelProvider interface and BrainEvent protocol. Ask for a JSON schema,
buffer bounded responses, validate every speech candidate, reject tool calls and
incomplete generations, and close the HTTP body on cancellation and timeout.
Do not print server errors or model reasoning. Inspect local model metadata before
sending conversation text and reject cloud aliases and HTTP redirects. Loopback
is a transport boundary, not proof against a malicious local server; configure
Ollama with cloud features disabled as well.

Enable general-question routing and ephemeral history only in local-chat mode.
The app retains up to eight completed exchanges / 12,000 UTF-8 bytes, scoped to
an authorized actor/session. `/clear` erases dialogue but preserves workout state.
Completed turns enter history only after all speech is consumed. Do not persist
dialogue or silently introduce general personal memory. CLI turns are sequential;
history for other callers is ordered by completion.

Send history as ordinary user/assistant messages, never as trusted system text.
The current authorized workout snapshot remains the source of numeric state.
Explicit workout actions retain application authority and confirmation rules;
general questions about workouts no longer get trapped by the command parser.

The current user request overrides the compact response goal for local chat:
permit fuller explanations in up to three speech segments. The existing Anthropic
persona pilot and its <=14-word scoring stay unchanged. A local model supports
open-ended language generation, not guaranteed parity with commercial chatbots,
web browsing, tool execution or reliable factual reasoning.
