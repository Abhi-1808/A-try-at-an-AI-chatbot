# Character evaluation

Run from the repository root with the existing Python environment. Offline is the
default, and neither command supports a paid provider or a paid judge:

```powershell
& .\.venv312\Scripts\python.exe -m hope_brain.character_eval --pilot
& .\.venv312\Scripts\python.exe -m hope_brain.character_eval --provider ollama --pilot --report local_data/character-pilot.json
```

The second command explicitly uses the installed local model. It does not install
or download anything. Start Ollama and download the model using [local setup](local_chat.md)
first if necessary. An existing report is never overwritten; choose a fresh filename.
Omit `--pilot` to exercise all supported character fixtures. Mock results establish
the harness and deterministic paths only; they cannot establish personality quality.

`evals/character_v1.json` maps the source pack's P1-P6, C1-C5, E1-E4 and B1-B2
to original synthetic dialogue and review expectations. It adds X2 as a pre-model
safety regression. The eight pilot IDs are P1, P3, P5, P6, C1, E3, B2 and X2.
Each scenario gets a fresh authorized in-memory session. P6 is multi-turn; C1 and
X2 have authoritative state setup. B1 has twenty turns. Thus cases and model calls
are different quantities. C5 is explicitly unsupported because no silence/idle
transport event exists; it stays in the selected denominator, never a fake pass.
The other source-pack scenarios are outside this character milestone.

Automatic checks cover event schema, contiguous sequence and turn identity, exactly
one terminal event, successful completion, one to three validated segments, word
limits, common emoji ranges, selected exact state effects and pre-model safety.
AI disclosure is only a lexical heuristic; a contradictory sentence containing
“AI” could pass it. No-title checks also need subjective context. The emoji detector
is a narrow Unicode heuristic. These checks do not replace the separate review list.
Default maximum is 14 whitespace-separated words per segment; P4 and X2 allow 80,
and B2 allows 40. These exceptions are declared before running, not after failures.

Every report leaves human review `pending`. Review whether Mira actually answers,
sounds consistent, uses kind optional wit, respects boundaries, avoids fabricated
state and chooses appropriate emotion/intensity. Record an assistant review separately;
it is not a human verdict. The 90% overall and 100% full safety gates require the
larger repeated evaluation in [release gates](release_gates.md).

First-segment time starts when the orchestrator accepts a turn and ends when its
first validated `speech.segment` is consumed. It includes policy, state access,
model metadata check, inference and full-response validation. Ollama streaming is
off, so this is not first-token latency. Reports use median p50 and nearest-rank
p95, with sample count. Successful model calls (including any setup calls) are
separate from deterministic turns. Failed model calls remain failures and retain
their elapsed duration, but do not enter successful-response latency percentiles.
CLI metrics additionally expose queue wait and input-arrival-to-first-segment time.

Ollama already receives the candidate JSON schema via `format` and `think: false`.
Returned emotion/intensity/text still undergo Pydantic validation. Malformed,
truncated or tool-bearing output fails with a safe fallback; no automatic repair
or retry is implemented. Metrics record whether a nonempty thinking field appeared,
never its contents, plus load/prompt-evaluation/generation duration when supplied.
The official [structured output](https://docs.ollama.com/capabilities/structured-outputs)
and [thinking](https://docs.ollama.com/capabilities/thinking) documentation describe
those controls. Prompt compliance and semantic safety remain separate questions.

Only BrainEvent NDJSON goes to stdout; progress and summary go to stderr. Reports
explicitly save fixed synthetic prompts and replies for review, under ignored
`local_data/` in the example. Do not substitute real personal chat when preparing
shareable evaluation artifacts. Ordinary application metrics never log messages,
secrets or internal reasoning. Golden examples are authored illustrations, not
claims that any particular model produced or will reproduce them.
