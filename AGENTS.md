# Project Hope — Codex repository instructions

## Product
Build an original, expressive AI companion **brain first**. No voice, STT, TTS, avatar, scraped private data, real-person voice cloning, or pretrained-model training in the initial milestones. The reference video is inspiration for behaviors, not proof of proprietary implementation. See `docs/architecture_v2.md` for architectural details.

## Engineering principles
- Keep a modular monolith. Prefer small, tested changes over frameworks and speculative abstractions.
- Application code owns user/session IDs, authorization, counters, goal changes, consent, and outbound event schemas. The LLM provides language and candidate actions, never authority.
- Use a swappable async ModelProvider interface; deterministic local mock by default. No paid API call in tests or without explicit opt-in.
- Client output consists exclusively of validated, versioned BrainEvent records. NDJSON stdout for CLI; diagnostics go to stderr. Exactly one terminal event per turn and monotonically increasing `seq`.
- Respect user agency and safety: stop means stop, no guilt, no surprise exercise goal changes, no invented numeric state, no manipulative attachment. Danger symptoms override teasing. Identify basic rule-based filters as development-only, not comprehensive safety.
- Persistent personal memory is opt-in, private to the authorized user, inspectable and deletable. Never write sensitive facts without explicit permissions and appropriate policy.
- Avoid logging personal messages, secrets, or internal model reasoning. Load keys from environment; never commit `.env`.
- Build tests with every behavioral change. Include success/failure and authorization/boundary cases.
- No externally accessible deployment or new infrastructure until specifically requested.

## Implementation expectations
- Prefer Python 3.13 when supported in the environment, otherwise record use of 3.12 and keep compatibility explicit.
- Use typed Pydantic models for incoming requests, segments, and client events; pytest for tests; Ruff for lint.
- Keep CLI, provider, orchestration, state, policy, memory, and transport responsibilities separate without generating empty modules.
- Make decisions explicit in small ADR docs. Distinguish model-generated content from trusted state/data.
- Reuse existing code and preserve unrelated user changes.

## Task workflow
1. Inspect repository, docs, relevant files, and tests before editing.
2. Implement only the current milestone from `Project_Hope_Codex_Brain_Build_Prompts_v1.md` (if present) or the current user prompt.
3. Add/update tests, then run `pytest -q` and `ruff check .` using available environment setup. Run more checks when applicable.
4. Review diff for privacy, tool authority, malformed output, undesired dependencies, and scope creep.
5. Report files changed, exact commands, ACTUAL results, limitations, and the next recommended small task. Do not claim tests passed when not executed and never continue automatically into the next milestone.
