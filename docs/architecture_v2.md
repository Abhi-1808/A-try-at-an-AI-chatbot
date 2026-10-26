# Project Hope: general-assistant direction

Revised 26 October 2026 from the user's six requested changes. This is a new
architecture record, not a recovered copy of the absent original production plan.
The supplied build-prompt pack remains milestone guidance; the user's current
request changes the product direction. Implement one reviewed milestone at a time.

## Product and model choice

Mira is an original, expressive general assistant. A frontier cloud model is the
intended main brain; gym coaching becomes one optional capability. Keep Qwen for
offline conversation development and contract tests, and the deterministic mock
as the no-network development default. Choosing cloud mode must remain explicit.
No voice, avatar, model training, public deployment or new service in this slice.

Start with one capable cloud model before adding routing. The prepared launcher
selects Claude Sonnet 5.5 as an interactive baseline candidate: this is a project
choice based on the existing adapter and expected speed/quality balance, not an
observed Mira benchmark. The official comparison lists Sonnet as fast and Opus
as moderate latency; Opus is a candidate for difficult questions after adapter
compatibility and evaluation. Haiku is a future fast-lane candidate.
Source, checked 2026-10-26: [Anthropic model comparison](https://platform.claude.com/docs/en/models/overview).

The current adapter supports text-only output. Sonnet 5.5 requires
`thinking.type=between_tools` to suppress up-front thinking; with no tools the
documented response is text only. The installed locked SDK supports this option.
This is configuration preparation plus offline transport testing, not a successful
live call. Adaptive/always-on thinking and tool blocks remain unsupported.
Source: [Sonnet migration changes](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5).

## Actual implementation boundary

| Area | Present now | Still to build or prove |
| --- | --- | --- |
| Cloud | Explicit opt-in Anthropic adapter, count preflight, timeouts, cumulative estimates, bounded history and `/clear` | Funded real-model quality/cost/latency pilot; thinking/tool block transport |
| Offline | Deterministic mock and local Qwen, schema validation, character pilot | Local results do not establish cloud quality or final safety |
| Conversation | Shared Mira v1.3 prompt; up to 8 completed exchanges / 12,000 UTF-8 bytes; session address preference | Long-chat summaries; persistent consented facts |
| Gym | Application-owned counts, target proposals/confirmations, receipts, SQLite ownership/version checks | Still coupled to orchestrator/context; no generic skill registry yet |
| Tools | Explicit deterministic workout commands | Web search, calculator, file reading; no host code execution |
| Safety | Development stop/danger intake rules and structural output checks | General-assistant intake/action/output policy and priority interruption |
| Evaluation | Unit/transport tests and narrow local character evidence | Full repeated corpus, general-assistant scenarios, human safety/persona review |

Only validated completed speech enters recent history; failures and cancellations
do not. History is ordinary user/assistant data, never trusted instructions.
Current authorized state overrides historical language. A shared provider must
not share users' conversation histories. Cloud token counting and generation both
receive the same current message, history, preference and authorized snapshot.
`/clear` resets local dialogue/address, preserves workouts and does not promise
deletion of data already sent to the provider. There is no durable personal memory.

## Target boundaries (planned)

Keep the modular monolith and swappable async providers. The turn coordinator
owns identity, cancellation, authorization, budgets and the versioned event stream.
Providers return untrusted speech/action candidates. Application code validates
and authorizes each action before execution, then supplies bounded tool results
as data. A model's statement that an action succeeded is never a receipt.

Introduce a small typed capability dispatcher when the first tool is implemented.
Extract gym commands behind it while preserving the existing tests, receipts,
ownership, confirmation and stale-update checks. Gym state is present only when
relevant and authorized; unrelated questions continue through general chat.
No plugin framework or empty abstraction modules in advance of this work.

Use separate intake, action and outgoing-content policies. They must cover
self-harm, medical questions, minors/age-appropriate content, privacy, emotional
pressure and exercise danger. Distress overrides teasing; support and appropriate
human help take priority over persona. Crisis resources must be verified for the
user's location when supplied. Avoid diagnostic certainty and unsupported safety
guarantees. Model refusals must be handled without fabricating a successful answer.
External text and retrieved facts cannot grant permissions or reveal other users' data.

## Milestones and acceptance evidence

1. **Cloud conversation readiness (this change) and then a separate live pilot.**
   Give Anthropic history/preferences and `/clear` parity, explicit text-only mode,
   disclosure, counted context and offline regression coverage. Prepare Sonnet in
   the launcher without making paid calls. The live pilot requires credentials,
   credits, verified applicable rates and explicit execution; keep USD 0.01/turn
   and USD 0.05/process limits. Judge Mira's identity, wit, follow-ups, factual
   uncertainty, boundaries and honest state; record failures, not just schema passes.
2. **General safety before external tools.** First allow a new stop/danger input
   to cancel an active generation instead of waiting behind it in the FIFO.
   Preserve one terminal event and state-stop semantics. Then add bounded intake,
   action and outgoing guards plus at least 30 adversarial fixtures spanning the
   broader topics above. Use human-reviewed criteria for semantic cases. A passing
   fixture set is evidence about that set, not universal safety.
3. **Prompt 05 memory, in small reviewed slices.** Introduce an explicit local
   profile/owner boundary first: random fresh CLI identities cannot support honest
   cross-session recall. Default persistent memory OFF. Provide enable/disable,
   inspect, correct, export and delete controls. Store SQL facts and neutral episode
   summaries with owner, source turn, category, timestamps, consent and retention.
   Pipeline: candidate, policy, permission, deduplicate/supersede, save, acknowledge.
   Reject sensitive health/financial facts in this milestone. Ownership and active
   consent filter before bounded keyword/recency retrieval. Retrieved material is
   data, and quotations about third parties must not become personal facts.
   Long-chat summaries must preserve uncertainty and provenance; in-RAM compression
   must not silently become persistence. Any cloud summarization counts against the
   same spend allowance. Resolve "forget that" when clear, clarify ambiguity, and
   delete linked active facts, summaries and caches for "forget everything about me".
   Explain backup/provider-retention limits honestly. Prove isolation, correction,
   disabled-mode behavior, injection resistance and M1-M3/X7 deletion regressions.
4. **Gym extraction and bounded tools.** Introduce the dispatcher with gym plus a
   calculator using a restricted arithmetic parser and resource bounds, not `eval`
   or host shell execution. Then add file reading only for explicitly allowed files
   or roots, with path/size/type limits and escape/secret protections. Finally add
   search with cited sources, bounded requests/results, provider cost accounting,
   network destination controls and prompt-injection tests. Reading a file/search
   result does not authorize its upload, execution or instructions. Choose a
   calculator first; an isolated code runner is a separate later proposal.
5. **Measured routing.** After the single-model baseline, use application-owned
   rules to route eligible simple chat to a small model and hard questions to a
   larger compatible model. Allow an explicit stronger-model choice. Compare
   quality and cost on the same versioned corpus; don't trust model confidence as
   proof. Share one budget ledger across routes, retries, tools, summaries and
   judges. Never silently fall back from local to paid inference. Preserve persona,
   consent and authoritative state across routes without replaying incompatible
   reasoning blocks.
6. **Latency and readiness.** Expand the original 33-scenario evaluation with
   general-chat, tool, memory, routing and safety cases. Score contracts separately
   from human/judge assessments. Keep the existing voice entry gates: >=90% overall,
   100% of the defined safety group, and first useful validated segment p50 <700 ms
   over at least 30 real-model turns; report p95, failures, costs and sample sizes.

Each numbered item can require several small milestones; stop after the current
one and report checks. A missing paid key does not prevent offline safety/memory
work, but it does prevent claiming a cloud quality result.

## Latency, cost and privacy limits

A cloud model makes a faster interaction plausible; it does not make 700 ms a
guarantee. Today token-count preflight plus the entire model reply must finish
before the first validated segment is emitted. Measure accepted-turn-to-segment
and queue delay separately, plus provider first-text time. Do not substitute a
canned acknowledgment or first token for useful validated speech. A future
incremental-validation change needs its own correctness and cancellation tests.

The ledger is process-local and reconciles returned usage at configured rates;
unknown requests retain estimates. It does not enforce billing or survive restarts.
Before routing, account for every model/search attempt under one shared allowance.
Ordinary logs contain timings and numeric usage, not dialogue, file contents,
secrets or internal reasoning. Persistent memory needs explicit permission, and
cloud use needs a clear account of what context leaves the machine.

See [ADR 0007](adr/0007-general-assistant-cloud-direction.md),
[cloud configuration](live_provider.md) and [release gates](release_gates.md).
