# ADR 0003: Authoritative workout state and explicit tools

Status: implemented for Prompt 04/B3, prioritized by the user on 24 October 2026.
Prompt 03 persona evaluations remain pending; this is an intentional ordering
change based on the user's request to build state and tools next.

Use typed immutable state, a pure reducer, a repository Protocol, and SQLite
with schema user_version=1. SQLite is in the standard library; no new runtime
dependency or external infrastructure is needed. Typed state is serialized as
JSON in owner-scoped set records; old sets remain available to authorized callers.
BEGIN IMMEDIATE transactions serialize mutations and commit state together with
command/submission receipts. Both are rolled back on failure. Read access also
uses the repository lock/transaction; this is local CLI infrastructure, not a
high-concurrency production transport.

Trusted application code supplies Actor(user_id, session_id) and an origin
separate from request data. It registers the session once. Every service operation
checks the registered owner. These are interface authorization checks, not public
identity authentication. A future transport must authenticate users before
constructing Actor. The CLI creates new random local IDs each invocation and
does not offer cross-process session resumption yet.

Commands carry a set ID, expected version, command ID and transcript submission
ID. Reusing either delivery ID rejects the mutation. The same text deliberately
submitted again with a new source ID is a new action; text similarity cannot
reliably distinguish another five reps from a retransmission. Upstream clients
must preserve submission IDs when retrying. Versions remain monotonic across
sets in a session. No automatic retry of a mutation is implemented.

The source pack (pages 7-8) specifies at most two target increases per set, each
at most three reps. Both proposal and confirmation enforce this cap. Decreasing
the target never resets it. Every target change, including a decrease, needs an
explicit confirmation referencing the pending proposal ID. Pending proposals
are invalidated by rep updates, end, or safety stop. All proposals and confirmed
changes retain old/new values, reason codes, actor/source and timestamps. Model
origin may propose but cannot start, count, confirm, or end a workout. Model
output has no dispatch path; the current provider continues to return speech only.

Engineering bounds are target 1-100 and rep increment 1-20, with no overshoot.
These are input plausibility limits, not medical recommendations or proof that
a particular workout is suitable. Counters are user-reported, not sensor-verified.

Workout commands and recognized count/history questions use deterministic speech
from validated state, so the model cannot invent these answers. A bounded record
of 50 delivered count statements supports factual callbacks. It is written after
the relevant speech has been yielded and consumption resumes; abrupt consumer
closure can leave a missing receipt, so callbacks then decline to verify it.
Persona flourishes and unrecognized natural-language abilities are deferred.

Intake policy remains before both tool dispatch and provider invocation. Danger
symptoms stop the latest stored workout and invalidate proposals before yielding
safety speech, so early stream closure cannot leave an active set behind. No symptom text is saved. A storage failure still
returns safety speech, emits state_unavailable, and never invokes the provider.
A conversation-only stop leaves workout counts unchanged. Preference requests
such as stop calling me sir remain separate from stopping exercise.

Storage defaults to SQLite :memory:. --workout-db explicitly opts into disk
workout storage. This is operational workout state, not general personal memory.
Raw transcripts, symptom descriptions, keys and model reasoning are not stored.
Local disk access is governed by OS permissions; encryption and backup/deletion
policies for a public product have not been implemented.

The v1 protocol gains workout.state snapshots and fixed tool/state error codes.
Committed state is emitted before workout speech. Cancellation after commit
cannot undo it; the receipt protects retries. Existing clients must update their
event-union reader for the additive event type.

SQLite work is synchronous with a five-second lock timeout. Database contention
can delay safety speech, although a model outage cannot. The future transport
and performance milestones must measure and address this local limitation.
