# Voice entry gates and pending real-model evaluation

User targets recorded 24 October 2026; none is claimed achieved.

| Gate | Measurement | Current evidence |
| --- | --- | --- |
| At least 90% overall | Fixed versioned corpus, 3 runs per scenario; all required dimensions pass | Pending real-model evaluation |
| 100% safety group | Every X1-X7 case across all repetitions, with human review of failures | Pending; missing memory/deletion behavior blocks X7 |
| First segment p50 below 700 ms | Accepted user turn to first validated speech.segment consumed, over at least 30 real-model turns | Pending; also report p95 |

Do not use turn.started or provider first-token timing as first-speech latency.
Include input policy, token-count preflight, generation, buffering, validation
and state work in the measurement. Report local deterministic and real-model
results separately. Buffered full-response validation plus a network preflight
may make the latency target challenging; no measurement currently establishes it.

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

Before running live: select a model, verify its current pricing and availability,
set a small account/workspace limit, and implement a total-run budget that includes
judge calls and unsuccessful attempts. Suggested initial experiment ceiling:
USD 0.25 total, with the existing per-turn cap kept low. This is a proposed
ceiling, not authorization or a promise that all 99 executions fit within it.
The current adapter only enforces an estimated per-turn preflight; no batch run
has been started and there is no aggregate-run cap yet.

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

Next: Prompt 03 character bible and offline versioned evaluation corpus. Then
opt-in memory/deletion and safety coverage can fill their specific missing cases.
Live evaluation and latency/cost measurement remain explicit subsequent work;
voice and avatar work stay gated.
