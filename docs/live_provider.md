# Optional Anthropic mode

Mock is the default and requires no key, SDK, or network. Choosing
`--provider anthropic` opts into sending each current message to Anthropic
and potentially paid generation. No live API call is part of default tests.

## Installation

From the repository root in PowerShell, install locked optional dependencies:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.venv312'
uv sync --locked --inexact --extra dev --extra anthropic --python 3.12
```

`--inexact` preserves unrelated installed packages. The earlier dependency setup
recreated `.venv` using Python 3.12; the documented environment is `.venv312`.
Neither environment should be committed. `.env.example` lists settings, but
the app does not automatically read `.env` files.

## Configuration

| Environment variable | Requirement |
| --- | --- |
| ANTHROPIC_API_KEY | Required only in live mode; load privately into your process environment |
| HOPE_ANTHROPIC_MODEL | Required model ID you have access to; no default |
| HOPE_MAX_TOKENS | Default 256; integer 1-4096 |
| HOPE_TIMEOUT_SECONDS | Default 30; total timeout greater than 0 and at most 120 seconds |
| HOPE_TURN_BUDGET_USD | Required positive per-turn estimated spend limit |
| HOPE_SESSION_BUDGET_USD | Required positive cumulative limit shared by one provider/process |
| HOPE_INPUT_USD_PER_MILLION | Required positive input price for your chosen model |
| HOPE_OUTPUT_USD_PER_MILLION | Required positive output price for your chosen model |

Use current rates applicable to your account and model. No example rate is
assumed to be a real price. After setting the key privately, this prompts for
model/prices and sets a one-cent estimated per-turn limit:

```powershell
$env:HOPE_ANTHROPIC_MODEL = Read-Host 'Model ID'
$env:HOPE_INPUT_USD_PER_MILLION = Read-Host 'Input USD per million tokens'
$env:HOPE_OUTPUT_USD_PER_MILLION = Read-Host 'Output USD per million tokens'
$env:HOPE_TURN_BUDGET_USD = '0.01'
$env:HOPE_SESSION_BUDGET_USD = '0.05'
$env:HOPE_MAX_TOKENS = '256'
$env:HOPE_TIMEOUT_SECONDS = '30'
& .\.venv312\Scripts\python.exe -m hope_brain.cli --provider anthropic
```

The preflight estimate is `(reserved_input * input_rate + max_tokens * output_rate)
/ 1,000,000`, with `reserved_input = ceil(count * 1.10) + 64`. Above-budget turns
emit fallback speech then `turn.failed` with `provider_budget_exceeded`. There is
no automatic retry. This is an estimate gate, not a billing guarantee: incorrect
rates, provider-side accounting and interrupted requests may still incur charges.
The cumulative ledger reserves the estimate before generation, reconciles complete
usage, retains estimates for unknown usage, and blocks later generation after an
observed estimate overrun. A process restart resets the allowance; concurrent
processes have separate allowances. Use provider account limits for account-wide control.

Input is limited to 16,384 UTF-8 bytes before even the token-count request. Both
counting and generation receive current text and the trusted system prompt.
An authorized workout snapshot is also sent when available, without identity,
receipt IDs or timestamps. No conversation history, session ID, saved personal
memory or tool call is sent. The model cannot mutate workout state.

## Verification

Full offline suite with SDK installed (uses in-memory HTTP MockTransport):

```powershell
& .\.venv312\Scripts\python.exe -m pytest -q
& .\.venv312\Scripts\ruff.exe check .
& .\.venv312\Scripts\python.exe -m mypy src/hope_brain
```

Without the optional SDK, provider-transport tests are explicitly skipped;
mock/configuration tests still run. For complete provider coverage install the
extra above. Mypy checks the real SDK types and also requires that extra.

The optional **paid** smoke test is a separate explicit CLI action. It sends
one fixed `Hi` turn, uses the same budget/timeout checks, and exits nonzero if
the turn fails or is cancelled. It is never run automatically:

```powershell
& .\.venv312\Scripts\python.exe -m hope_brain.cli --provider anthropic --live-smoke
```

Missing key or invalid configuration produces a redacted stderr error and exit
code 2 before any network call. Speech candidates become NDJSON only after the
entire response is complete and validated. Safe metrics go to stderr. Ctrl+C
requests cancellation while generation is active; an abrupt process termination
or second interrupt may prevent terminal delivery. Closing the SDK stream is
local cleanup and does not promise that a remote billable request was undone.

The response schema is a structural guard. The development safety policy does
not provide comprehensive semantic safety, and no live quality evaluation has
been performed. See ADR 0002 for decisions and verified SDK documentation.
See [the bounded terminal demo](live_demo.md) and [ADR 0004](adr/0004-bounded-terminal-demo.md)
for the cumulative budget, hidden key prompt and five-scenario pilot.
