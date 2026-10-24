# ADR 0002: Explicit live mode with buffered, validated streaming

Status: implemented for Prompt 02, 24 October 2026.

Keep the async ModelProvider.generate interface and existing event authority.
The optional Anthropic adapter uses SDK 2.3.0, pinned in pyproject.toml and uv.lock.
The package version was checked through PyPI and its installed signatures were
inspected. Python 3.12.8 is the tested runtime; no broader runtime certification
is claimed. The architecture_v2.md reference is still absent.

ContextBuilder supplies server policy, persona v1, and the explicit absence of
workout state and memory as a system message. Only current user text is placed
in the user message. Session IDs are not sent. This role separation helps keep
instructions distinct; it is not a guarantee against prompt injection.

Use the official async SSE client internally, buffering at most 65,536 response
characters. Accept one text block, a successful end_turn, and message_stop.
Reject tool/thinking blocks, incomplete streams, invalid JSON/schema, and extra
metadata. Validate all segments before releasing any provider speech. This costs
first-speech latency but prevents partial JSON or incomplete replies reaching
clients. The server still creates every event ID, sequence number, and terminal.

Live mode requires explicit provider selection, API key, model, per-turn USD
budget, and configured input/output prices. A token-count preflight reserves
10% plus 64 input tokens and the configured maximum output. Reject estimates
above budget before generation. Rates and token counts are estimates, not an
account billing cap. No pricing or model identifier is hardcoded. Retries are
zero, avoiding unexpected repeated generation charges. Count requests still
send the current input to Anthropic even when generation is budget-rejected.

A total timeout wraps preflight plus generation. The orchestrator races a
cooperative generation task against cancellation and awaits cleanup. Closing a
client connection cannot undo provider charges or guarantee remote computation
has stopped. Consumers must continue reading to receive the terminal event.

Routine diagnostics contain stage durations, token counts when returned, and
fixed outcome/reason codes. SDK debug logs and SDK OpenTelemetry are disabled;
raw prompts, replies, credentials, and exception text are not logged.

No tools, state mutation, persistence, memory, API server, or deployment is added.
The development intake safety baseline and absence of a semantic output guard
remain known limits. A real model's persona and safety quality are unverified.

Sources consulted:
- https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python
- https://platform.claude.com/docs/en/build-with-claude/streaming
- https://platform.claude.com/docs/en/build-with-claude/token-counting
- https://pypi.org/pypi/anthropic/2.3.0/json
