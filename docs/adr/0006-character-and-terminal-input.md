# ADR 0006: Versioned character and visible terminal input

Status: accepted, 2026-10-25. Scope: requested Prompt 03 character work and local
terminal diagnostics. No voice, persistent personal memory, paid run or new service.

Keep one versioned runtime character module separate from policy and state.
Both real providers use it. Local general conversation remains available; ordinary
answers become compact, with explicit-detail exceptions. Narrow address requests
update application-owned per-session preferences, independent of truncated history.
They are never parsed from model output and are reset with `/clear`.

Read stdin in one daemon thread while async inference runs. Accepted lines receive
numbered stderr receipts and enter a FIFO with 32 waiting slots. Excess lines are
visibly rejected; EOF drains accepted inputs, including a final line without newline.
`/quit` closes the chat and announces pending cancellations. Commands matching the
narrow PowerShell/launcher detector receive an `input_rejected` terminal event and
do not reach the model or history. This is a usability rule, not a shell sandbox.
The application never executes chat text. Explanation questions still reach Mira.

Queue waiting is measured separately from generation. Input is processed in FIFO
order, so a typed stop/symptom line does not interrupt an already running previous
turn. Its safety gate runs before its own model call; Ctrl+C interrupts current
waiting. Priority interruption needs a deliberate later transport decision.

The evaluator defaults to mock and offers an explicitly selected local provider.
Fixtures, exceptions and pilot selection are versioned. Automatic checks and pending
human review remain separate. Unsupported silence behavior remains visible. No
automatic repair is added: invalid generations retain their failed outcome.

Keep JSON-schema-constrained generation and `think: false`, which were already
present. Record redacted timing/token metrics and whether thinking output appeared.
Buffered validation means first validated segment waits for the entire model reply;
measure this honestly before considering a streaming change.

26 October refinement: version the prompt as `mira-v1.3`; use structured original
demonstrations without the copied readiness line, explicit restrained intensity,
and direct identity wording. Keep provider settings, event validation and the
eight-case corpus unchanged for comparison. Add a separate small regression corpus
and opt-in lexical/repetition checks. Preserve failures; no output cleanup or
automatic generation retry is introduced.
Show detailed workout instructions only when the authorized context contains a
workout. Otherwise explicitly say none is established and avoid assuming exercise
is planned. This reduces irrelevant workout steering while retaining the same
state ownership and safety policy. Intermediate prompt revisions and observed
regressions remain in the comparison evidence.
