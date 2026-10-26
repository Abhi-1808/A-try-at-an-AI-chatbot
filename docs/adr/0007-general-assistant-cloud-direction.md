# ADR 0007: General assistant with an explicit cloud primary path

Accepted 26 October 2026. The user requested a frontier main model, offline Qwen,
tools, proper Prompt 05 memory, cost-aware routing, broader safety and gym as a skill.

Use the existing Anthropic adapter for the first prepared cloud candidate, Sonnet
5.5, instead of adding another provider or routing layer before a quality baseline.
The launcher selects it with explicitly documented prices, text-only configuration
and the existing small budget. Default CLI startup remains the deterministic mock;
cloud selection is explicit and local mode never falls back to a paid provider.

Extend the same bounded, authorized in-RAM history and address preferences to
Anthropic. Count and generate from identical dialogue/system context. Include
only validated delivered exchanges, preserve state on `/clear`, and disclose
that clearing local history cannot undo earlier provider transmission. Providers
never own session history or state authority. No durable personal-memory claims.

Expose only `disabled` and `between_tools` thinking settings, using locked SDK
types. Choose the latter for the no-tools Sonnet candidate. The response parser
continues to reject reasoning/tool blocks. Other modes and larger models need a
separate transport milestone before routing; no capability compatibility is inferred
from accepting an arbitrary model ID. Live compatibility remains unverified.

This supersedes ADR 0005's local-only history restriction. Both real providers now
use the same conversational context and character policy. The short paid pilot's
14-word checks remain, while requested detailed explanations may be longer during
normal chat. Prior local results remain historical evidence, not cloud evaluation.

The [revised architecture](../architecture_v2.md) orders the remaining work:
priority cancellation and general safety, consented memory, gym/tool boundaries,
then measured routing and performance. These are planned capabilities, not features
introduced by this change. No paid calls, new dependencies, infrastructure, voice
or public deployment are needed for cloud-readiness tests.
