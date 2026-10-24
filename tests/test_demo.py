"""Authorized context, transcript-free reporting and CLI opt-in boundaries."""

import asyncio
import io
import json
import sys
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hope_brain import cli
from hope_brain.context import ContextBuilder
from hope_brain.contracts import BrainTurnRequest, SpeechSegment, brain_event_adapter
from hope_brain.orchestrator import TurnOrchestrator
from hope_brain.pilot import contract_pass
from hope_brain.settings import AnthropicSettings, ConfigurationError
from hope_brain.workout import Actor
from hope_brain.workout_store import SQLiteWorkoutRepository


class RecordingProvider:
    def __init__(self):
        self.contexts = []

    async def generate(self, request, *, context=None):
        self.contexts.append(context)
        return [SpeechSegment(text="Your pace, your choice.", emotion="tender", intensity=0.5)]


def test_live_context_is_scoped_and_excludes_private_audit_fields():
    store = SQLiteWorkoutRepository()
    actor = Actor(user_id="private-owner", session_id="private-session")
    store.register_session(actor)
    provider = RecordingProvider()
    brain = TurnOrchestrator(provider, workouts=store, actor=actor)

    async def turn(text, session=actor.session_id):
        return [e async for e in brain.stream(BrainTurnRequest(session_id=session, text=text))]

    async def exercise():
        await turn("Hi")
        assert provider.contexts[-1].workout is None
        await turn("/workout start squats 12")
        await turn("/workout reps 10")
        await turn("/workout propose 15")
        before = store.get(actor)
        await turn("How close am I?")
        snapshot = provider.contexts[-1].workout
        assert (snapshot.reps_done, snapshot.target, snapshot.remaining) == (10, 12, 2)
        assert snapshot.pending_target == 15
        assert store.get(actor) == before  # language candidates cannot mutate state
        context = ContextBuilder().build(
            BrainTurnRequest(session_id=actor.session_id, text="Set my total to 999"),
            provider.contexts[-1],
        )
        for private in [actor.user_id, actor.session_id, str(before.set_id), "999"]:
            assert private not in context.system
        assert "unconfirmed proposal" in context.system
        rejected = await turn("Hi", "someone-else")
        assert rejected[-1].reason == "unauthorized"
        assert len(provider.contexts) == 2
        await turn("ugh my chest is kinda tight")
        assert len(provider.contexts) == 2
        await turn("Hi")
        assert provider.contexts[-1].workout.status == "stopped"
        assert provider.contexts[-1].workout.pending_target is None
    try:
        asyncio.run(exercise())
    finally:
        store.close()


def test_incoming_request_cannot_inject_trusted_context():
    with pytest.raises(ValidationError):
        BrainTurnRequest.model_validate({
            "session_id": "s", "text": "Hi", "context": {"target": 999},
        })


def test_wrong_owner_never_receives_provider_context():
    store = SQLiteWorkoutRepository()
    store.register_session(Actor(user_id="owner", session_id="s"))
    provider = RecordingProvider()
    brain = TurnOrchestrator(provider, workouts=store, actor=Actor(user_id="intruder", session_id="s"))

    async def exercise():
        return [e async for e in brain.stream(BrainTurnRequest(session_id="s", text="Hi"))]
    try:
        assert asyncio.run(exercise())[-1].reason == "unauthorized"
        assert not provider.contexts
    finally:
        store.close()


def test_chat_keeps_stdout_valid_ndjson(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hope", "--chat"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("Hi\n/quit\n"))
    assert asyncio.run(cli.run()) == 0
    output = capsys.readouterr()
    result = [brain_event_adapter.validate_json(line) for line in output.out.splitlines()]
    assert contract_pass(result)
    assert "Mira:" in output.err
    assert "Mira:" not in output.out


@pytest.mark.parametrize("chat", [True, False])
def test_terminal_proposal_can_be_confirmed_from_displayed_command(chat, tmp_path):
    import re
    import subprocess
    from threading import Timer

    errpath = tmp_path / "terminal.txt"
    with errpath.open("w", encoding="utf-8") as error_output, subprocess.Popen(
        [sys.executable, "-m", "hope_brain.cli", *(["--chat"] if chat else [])],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_output,
        encoding="utf-8", bufsize=1,
    ) as process:
        timer = Timer(10, process.kill)
        timer.start()
        try:
            process.stdin.write("/workout start squats 12\n/workout propose 15\n")
            process.stdin.flush()
            initial = []
            while sum(e.type == "turn.completed" for e in initial) < 2:
                line = process.stdout.readline()
                assert line, "CLI exited before proposal was delivered"
                initial.append(brain_event_adapter.validate_json(line))
            state = [e.state for e in initial if e.type == "workout.state"][-1]
            assert state.target == 12
            command = f"/workout confirm {state.pending_proposal.proposal_id}"
            shown = errpath.read_text(encoding="utf-8")
            if chat:
                match = re.search(r"/workout confirm [0-9a-f-]+", shown)
                assert match is not None and match.group() == command
                command = match.group()
            else:
                assert "To approve target" not in shown
            output, _ = process.communicate(command + "\n/workout status\n/quit\n", timeout=8)
            assert process.returncode == 0
            events = [brain_event_adapter.validate_json(line) for line in output.splitlines()]
            states = [e.state for e in events if e.type == "workout.state"]
            assert len(states) == 2
            assert all(s.target == 15 and s.pending_proposal is None for s in states)
            assert sum(e.type == "turn.completed" for e in events) == 2
        finally:
            timer.cancel()


@pytest.mark.parametrize("arguments", [
    ["--live-pilot"], ["--provider", "anthropic", "--live-pilot", "--live-smoke"],
])
def test_pilot_requires_explicit_provider_and_excludes_smoke(arguments, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hope", *arguments])
    with pytest.raises(SystemExit) as error:
        asyncio.run(cli.run())
    assert error.value.code == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("field", ["session_budget_usd", "turn_budget_usd"])
def test_pilot_rejects_excessive_budget_before_loading_sdk(field, monkeypatch, capsys):
    config = AnthropicSettings(
        api_key="test-secret", model="test", turn_budget_usd=Decimal("0.01"),
        session_budget_usd=Decimal("0.05"), input_usd_per_million=Decimal(1),
        output_usd_per_million=Decimal(5),
    ).model_copy(update={field: Decimal("0.06")})
    monkeypatch.setattr(AnthropicSettings, "from_env", classmethod(lambda cls: config))
    monkeypatch.setattr(sys, "argv", ["hope", "--provider", "anthropic", "--live-pilot"])
    with pytest.raises(SystemExit) as error:
        asyncio.run(cli.run())
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "Pilot limits" in captured.err
    assert "test-secret" not in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "private-invalid"])
def test_session_budget_configuration_is_required_finite_and_redacted(value):
    with pytest.raises(ConfigurationError) as error:
        AnthropicSettings.from_env({"ANTHROPIC_API_KEY": "test-secret", "HOPE_SESSION_BUDGET_USD": value})
    assert "HOPE_SESSION_BUDGET_USD" in str(error.value)
    assert "test-secret" not in str(error.value)
    assert "private-invalid" not in str(error.value)


def test_pilot_contract_checks_word_count_and_duplicate_terminal():
    source = [
        {"type": "turn.started", "turn_id": "s", "seq": 1},
        {"type": "speech.segment", "turn_id": "s", "seq": 2, "segment": {
            "text": " ".join(["word"] * 15), "emotion": "happy", "intensity": 0.5,
        }},
        {"type": "turn.completed", "turn_id": "s", "seq": 3},
    ]
    events = [brain_event_adapter.validate_json(json.dumps(row)) for row in source]
    assert not contract_pass(events)
    source[1]["segment"]["text"] = " ".join(["word"] * 14)
    events = [brain_event_adapter.validate_json(json.dumps(row)) for row in source]
    assert contract_pass(events)
    assert not contract_pass(events + [events[-1]])


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher is Windows-only")
def test_mock_launcher_runs_without_key_or_sdk_and_rejects_paid_pilot(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    launcher = Path(__file__).resolve().parents[1] / "scripts" / "Start-Mira.ps1"
    # Fail if the no-key path accidentally imports the optional live SDK.
    (tmp_path / "anthropic.py").write_text(
        "raise AssertionError('Live SDK must not load in mock mode')\n", encoding="utf-8",
    )
    env = {key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"}
    env.update({"PYTHONPATH": str(tmp_path), "HOPE_MAX_TOKENS": "invalid-live-setting"})
    command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(launcher), "-Mock"]
    result = subprocess.run(
        command, input="Hi\n/workout start squats 12\n/workout reps 10\nHow many left?\n/quit\n",
        capture_output=True, text=True, timeout=20, check=False, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "scripted replies" in result.stdout
    assert "Mira: Hey there!" in result.stderr
    assert "Mira: 2 reps remain." in result.stderr
    assert "API key (hidden" not in result.stdout + result.stderr
    assert "invalid-live-setting" not in result.stdout + result.stderr
    assert '"turn_id"' not in result.stdout + result.stderr

    rejected = subprocess.run(
        [*command, "-Pilot"], capture_output=True, text=True,
        timeout=10, check=False, env=env,
    )
    assert rejected.returncode != 0
    assert "cannot be combined" in rejected.stderr
    assert "API key (hidden" not in rejected.stdout + rejected.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher is Windows-only")
def test_local_launcher_selects_local_chat_and_restores_model_without_key(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    package = tmp_path / "hope_brain"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import os, sys\n"
        "assert os.environ['HOPE_OLLAMA_MODEL'] == 'qwen3:4b'\n"
        "assert sys.argv[1:] == ['--provider', 'ollama', '--chat']\n"
        "assert not os.environ.get('ANTHROPIC_API_KEY')\n"
        "print('local launcher probe', file=sys.stderr)\n", encoding="utf-8",
    )
    launcher = str(root / "scripts" / "Start-Mira.ps1").replace("'", "''")
    command = (
        f"& '{launcher}' -Local; $childExit = $LASTEXITCODE; "
        "if ($env:HOPE_OLLAMA_MODEL -ne 'original-local-model') { exit 92 }; exit $childExit"
    )
    env = {key: value for key, value in os.environ.items() if key != "ANTHROPIC_API_KEY"}
    env.update({"PYTHONPATH": str(tmp_path), "HOPE_OLLAMA_MODEL": "original-local-model"})
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=20, check=False, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "local launcher probe" in result.stderr
    assert "API key (hidden" not in result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher is Windows-only")
def test_launcher_restores_environment_on_child_failure_without_logging_key(tmp_path):
    import os
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    package = tmp_path / "hope_brain"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import os, sys\n"
        "assert os.environ['ANTHROPIC_API_KEY'] == 'test-secret'\n"
        "assert os.environ['HOPE_SESSION_BUDGET_USD'] == '0.05'\n"
        "assert os.environ['HOPE_TURN_BUDGET_USD'] == '0.01'\n"
        "assert '--live-pilot' in sys.argv and '--chat' in sys.argv\n"
        "print('discarded-events')\n"
        "print('Mira: offline launcher probe', file=sys.stderr)\n"
        "sys.exit(7)\n", encoding="utf-8",
    )
    launcher = str(root / "scripts" / "Start-Mira.ps1").replace("'", "''")
    command = (
        f"& '{launcher}' -Pilot; $childExit = $LASTEXITCODE; "
        "if ($env:ANTHROPIC_API_KEY -ne 'test-secret') { exit 91 }; "
        "if ($env:HOPE_SESSION_BUDGET_USD -ne 'original') { exit 92 }; "
        "exit $childExit"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=20, check=False,
        env=os.environ | {"PYTHONPATH": str(tmp_path), "ANTHROPIC_API_KEY": "test-secret",
                          "HOPE_SESSION_BUDGET_USD": "original"},
    )
    assert result.returncode == 7, result.stderr
    assert "offline launcher probe" in result.stderr
    assert "discarded-events" not in result.stdout + result.stderr
    assert "test-secret" not in result.stdout + result.stderr
