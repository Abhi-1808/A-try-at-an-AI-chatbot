# ADR 0004: Bounded terminal demo before further milestones

Accepted 2026-10-24 following the user's request to test Mira's personality next.
The user chose to run paid calls themselves; implementation and verification here
use offline mock HTTP only.

- Keep the current modular monolith and optional Anthropic adapter. No new dependency,
  hosted service, judge model, voice, avatar, or general personal-memory implementation.
- Pass an immutable, minimal workout snapshot through a separate trusted provider
  argument. Construct it only after authorization. Omit user/session/set/proposal IDs,
  timestamps, receipt history and raw private messages. Current user text stays in
  the user message; an incoming request cannot supply this trusted argument.
- The model still produces speech only. Existing deterministic workout commands,
  count receipts, confirmation rules, caps and pre-model safety stay authoritative.
- Require both per-turn and cumulative estimated spend limits. One provider instance
  shares a synchronous locked ledger across turns. Reserve before generation, reconcile
  only with complete usage, retain the entire estimate for uncertain requests, and
  block future generations after any observed estimate overrun. No automatic retries.
- Ledger scope is one provider/process lifetime, including pilot setup and turns.
  Restarting creates a new allowance; this is not an account-wide billing limit.
  Current rates and provider billing still govern actual charges.
- Add `--chat` speech display on stderr. Stdout remains validated BrainEvent NDJSON.
  The PowerShell launcher discards that stdout for a readable terminal conversation.
  Speech display is deliberately requested UI output, not a diagnostic log.
- Use a hidden key prompt with process-only environment variables and cleanup. Do not
  automatically load dotenv files, save keys, change Windows user settings, or log SDK
  bodies. Secrets necessarily exist transiently in process memory/environment.
- Five fixed synthetic prompts use one model instance and a maximum $0.05 cumulative
  allowance ($0.01 per turn). Two deterministic commands first establish 10/12 squats.
  Contract scoring includes <=14 whitespace-delimited words per segment. Persona and
  state correctness require human review; no automated judge verdict is invented.
- First-speech latency starts before orchestration and ends at the first validated
  speech event consumed. Failed/fallback turns are excluded from model latency
  samples. Five observations cannot establish the 30-turn latency release gate.

No conversation-history buffer is added in this milestone. Short-term preferences
and earlier dialogue are not remembered by general model turns. Workout state persists
within the CLI session; personal memory and cross-session identity remain separate work.
