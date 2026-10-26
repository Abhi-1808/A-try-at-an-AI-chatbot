# Cloud-readiness review

Reviewed 26 October 2026. This change prepares, but does not validate, the
frontier-cloud path for Mira.

## What is prepared

- The existing Anthropic adapter accepts explicit `disabled` and `between_tools`
  text-only modes.
- The launcher selects Claude Sonnet 5.5, explicit rates, a 0.01 USD per-turn
  estimate limit, and a 0.05 USD process-session limit.
- Anthropic token counting and generation receive the same trusted system prompt,
  bounded recent dialogue, address preference, and authorized workout snapshot.
- Conversation history is limited to eight completed exchanges or 12,000 UTF-8
  bytes, failed and cancelled turns are excluded, and `/clear` resets local
  dialogue/address state without changing workout state or making a provider call.
- The default CLI remains deterministic mock mode; local Ollama mode does not
  fall back to a paid provider.

## Verification

Offline verification completed with the optional SDK installed:

```text
265 passed
ruff check .
mypy src/hope_brain
```

The provider tests use an in-memory HTTP transport and explicitly reject real
network requests. They cover request parity, history/session boundaries, clear
behavior, budget rejection, timeout/cancellation, malformed responses, and
redacted diagnostics.

## Not validated

- Anthropic account access, model availability, or live API compatibility.
- Cloud response quality, persona fidelity, or latency.
- Provider billing or account-wide spend limits; local process budgets reset on
  restart and are not an invoice.
- Thinking/tool blocks, web/calculator/file tools, routing, durable personal
  memory, or broader semantic safety.

The next cloud milestone should use an explicitly approved live smoke test and
then a measured persona/safety evaluation. Recheck model identifiers, pricing,
and account limits immediately before any paid run.
