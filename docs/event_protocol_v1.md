# Brain event protocol v1

Each CLI stdout line is one UTF-8 JSON object. All events have `v: 1`, a
server-generated `turn_id`, a per-turn `seq` beginning at 1, and `type`.
The first event is `turn.started`. Every turn ends with exactly one of
`turn.completed`, `turn.failed`, or `turn.cancelled` when the stream is consumed.
Sequence numbers increase by one. A `speech.segment` carries a validated
`segment` with speakable `text`, an allowed `emotion`, and `intensity` from 0 to 1.

`turn.failed` has a non-sensitive reason code `provider_invalid` or
`provider_error`, plus the additive Prompt 02 codes `provider_timeout` and
`provider_budget_exceeded`. `turn.cancelled` uses `user_stop` or `request_cancelled`.
The server may emit safe fallback speech before `turn.failed`. A failed turn
must not be mistaken for a successful reply.

The Pydantic discriminated union in `hope_brain.contracts` is authoritative.
Provider candidates have no `v`, IDs, sequence numbers, or event types.


Provider streams are buffered until complete validation. An asyncio cancellation
Event interrupts cooperative generation and produces turn.cancelled. Closing a
stream consumer without reading further cannot guarantee terminal delivery.

## Workout extension (Prompt 04)

The event union additionally accepts workout.state with state: null for unknown
state, or an authorized snapshot containing set_id, exercise, reps_done, target,
remaining, status, version, raises_used, and pending_proposal. State snapshots
come from server code only. Update clients to recognize this additive v1 event.
Tool failures use tool_rejected, unauthorized, or state_unavailable. A rejected
mutation does not change counts. A committed mutation may precede a cancellation;
consume its state event and preserve submission IDs on any transport retry.

BrainTurnRequest now carries an application-generated submission_id UUID. Preserve
it across redelivery; a new line typed in the CLI is a new submission. Authorization
comes from the orchestrator's bound Actor, not from model output or this ID.
