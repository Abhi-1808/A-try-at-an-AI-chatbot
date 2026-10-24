# Threat model v1 (development baseline)

Untrusted sources: user text and all model output. Trust boundary:
neither may assign event metadata, change authoritative state, or authorize
actions. This milestone has no tools or persistent state. The provider output
is fully validated before emission; malformed output yields a safe fallback.

Risks still open: rule-based intake misses paraphrases, quoted or adversarial
text may trigger false positives, and there is no public authentication, output
policy layer, privacy review, or clinical validation. Do not deploy this policy
as a comprehensive safety system. Do not connect it to a real workout device.

Routine diagnostics record reason codes, not prompts or candidate text. The
CLI emits protocol JSON on stdout and human guidance on stderr.


Prompt 02 adds optional remote disclosure of the current user text to Anthropic,
both in token counting and generation. SDK telemetry and debug logs are disabled.
Budget estimates depend on configured rates and do not guarantee billed spend.
The mock remains fully local. Structured validation does not detect all unsafe
or fabricated content in otherwise valid speech; live output quality and the
future semantic output guard remain unverified.
