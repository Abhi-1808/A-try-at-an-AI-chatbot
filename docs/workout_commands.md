# Workout state: local development commands

Start the offline CLI:

```powershell
& .\.venv312\Scripts\python.exe -m hope_brain.cli
```

| Input | Result |
| --- | --- |
| /workout start pushups 12 | Create a new set with target 12 |
| /workout reps 5 | Add five user-confirmed reps |
| I did 5 | Same narrow, deterministic update |
| /workout status or How many left? | Report calculated remaining reps |
| What's my target? | Report the confirmed target |
| /workout propose 15 | Propose a new target without changing the current one |
| /workout confirm PROPOSAL_ID | Confirm exactly the pending proposal |
| /workout history | Explain the most recent confirmed target change |
| /workout end | End the current set |
| Stop exercising | Stop the workout and cancel the turn |
| Stop talking | Cancel conversation without changing workout state |

Supported exercise names: pushups, squats, situps, pullups. Copy PROPOSAL_ID
from workout.state.state.pending_proposal.proposal_id. With `--chat` (including
the PowerShell launcher), the terminal shows the complete confirmation command
beside each pending proposal; copy that command to approve it. An unqualified yes does
not change a goal. Neither does a model suggestion. Just 3 more creates a
proposal only, within the two-increase/three-rep cap.

With nine of twelve reps recorded, Mira can report three remaining. After three
more reps, a callback about that earlier statement reports zero remaining. If
you explicitly approved a target increase between those statements, the reply
explains that change. Missing statement evidence produces clarification, never
a fabricated admission. The mathematical explanation is deterministic; subjective
persona quality remains unevaluated.

All stdout lines remain validated BrainEvents. workout.state contains set ID,
exercise, reps_done, target, server-calculated remaining, status, version,
raises_used and the pending proposal. It excludes user/session identities.
A rejected mutation produces turn.failed with tool_rejected; current state is
unchanged. Retries must keep their submission ID at the service boundary.

By default everything disappears when the CLI exits. Explicitly save workout
records in a local SQLite file with:

```powershell
& .\.venv312\Scripts\python.exe -m hope_brain.cli --workout-db .\workouts.db
```

The parent directory must already exist. This saves state/audit receipts but
still starts a fresh CLI identity/session each launch. Authorized service callers
can reopen the same database using their verified Actor to recover a prior
session; CLI resumption is not yet provided. Stored records are not encrypted.
Use your private local directory. General memory, summaries, recall and forget
commands remain unimplemented. Nothing is deployed and no paid calls are needed.

The precise command grammar deliberately refuses ambiguous action requests.
It does not understand arbitrary exercise language or observe your real reps.
The safety matcher handles the tested examples but remains a development baseline.
