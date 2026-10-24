# Voice entry gates and pending real-model evaluation

User targets recorded 24 October 2026; none is claimed achieved.

| Gate | Measurement | Current evidence |
| --- | --- | --- |
| At least 90% overall | Fixed versioned corpus, 3 runs per scenario; all required dimensions pass | Local pilot: 7/8 mechanical passes; human/full repeated evaluation pending |
| 100% safety group | Every X1-X7 case across all repetitions, with human review of failures | X2 local pilot passes without model; full group pending; memory/deletion blocks X7 |
| First segment p50 below 700 ms | Accepted user turn to first validated speech.segment consumed, over at least 30 real-model turns | Local diagnostic p50 11,441.531 ms, p95 25,912.149 ms, n=7; target not met and 30-turn sample pending |

Do not use turn.started or provider first-token timing as first-speech latency.
Include input policy, token-count preflight, generation, buffering, validation
and state work in the measurement. Report local deterministic and real-model
results separately. Buffered full-response validation plus a network preflight
may make the latency target challenging; the current local diagnostic exceeds it.

The source pack pages 9-11 contain 33 IDs: P1-P6, S1-S6, C1-C5, E1-E4,
B1-B2, X1-X7 and M1-M3. Port expectations into an independently versioned corpus
with source mapping and explicit deviations for user agency. Never fake a target
change or pressure exercise just to match a comic reference. Unknown abilities
are pending/failing, not silently excluded from the release denominator.

Scoring must separate automatic checks (schema, one terminal, emotion/intensity,
segment count/word limits, tool effects and exact authoritative state) from
persona/safety judgment against a character bible. A model judge is an assistive
reviewer, not proof; human review should cover safety failures and disagreements.
Safety and explicitly requested detail may have documented word-limit exceptions.
No real-model persona or 14-word compliance claim follows from unit-test results.

33 scenarios repeated three times gives 99 scenario executions, not necessarily
99 API calls. Several are multi-turn; B1 includes 20 prompts. Judge calls add
further spend. Count generation, judge, and retry attempts separately. There
are no generation retries in the current adapter.

The user prioritized a five-scenario pilot before the remaining milestones and
chose to run it personally. The [prepared pilot](live_demo.md) enforces a maximum
USD 0.05 cumulative estimate and USD 0.01 per turn. One provider instance shares
accounting across turns and retains uncertain reservations after failures.
It makes no judge calls. No paid pilot or full corpus run has been performed here.
For a later full evaluation, include every generation/judge attempt in one budget,
verify then-current pricing, and set an account-wide limit separately. Process
restarts currently reset local accounting; this is not an account-level spend cap.

Pricing checked against the official page on 24 October 2026. It lists standard
Claude Haiku 4.5 at USD 1 input / USD 5 output per million tokens, and Claude
Sonnet 4.6 at USD 3 / USD 15. These are reference examples, not a selected model
or an inferred account rate. Recheck before execution; pricing features and tiers
can change. Source: https://platform.claude.com/docs/en/about-claude/pricing

For successful calls, compute estimated actual usage cost from returned input
and output tokens at configured rates, and compare with the preflight estimate.
Record missing usage on cancellations/failures as unknown, not zero. Token usage
is not a billing invoice. Report call count, model, rates/date, budget consumed,
unknown-cost calls, p50/p95, workload, hardware and sample size.

The paid pilot is parked because the user has no paid key. The user installed a
local model; Prompt 03 now has a bible, versioned corpus and an observed eight-case
pilot. See [actual review](character_review.md). Next is targeted character refinement
and human review, not a voice milestone.
Opt-in memory/deletion and broader safety coverage still need their own milestones;
voice and avatar work stay gated.
