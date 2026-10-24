# ADR 0001: Offline modular brain first

Status: accepted for Prompt 01.

Use a Python modular monolith with a swappable async provider. The provider
returns only untrusted speech candidates. The orchestrator validates candidates
and creates all client events. A deterministic mock enables a useful local demo
and repeatable tests without credentials, networking, or infrastructure.

The separate `Project_Hope_AI_Brain_Production_Plan_v2.md` was not supplied.
The provided Prompt 01 pack, repository instructions, and source-pack PDF are
the milestone references. Python 3.13 was unavailable locally; development
and checks use Python 3.12.8. The source-pack PDF remains outside the repo
because redistribution rights were not established.

No database, persistent memory, workout state, live model, HTTP transport,
voice, or avatar is implemented at this milestone.

