"""Evaluation scores contracts without pretending to judge personality."""

import asyncio
import json
import sys

import pytest
from pydantic import ValidationError

from hope_brain import character_eval as evaluation
from hope_brain.contracts import SpeechEvent, SpeechSegment, TurnCompleted, TurnStarted
from hope_brain.provider import DeterministicMockProvider


def events(text="A short helpful answer."):
    return [
        TurnStarted(turn_id="t", seq=1),
        SpeechEvent(turn_id="t", seq=2, segment=SpeechSegment(
            text=text, emotion="playful", intensity=0.5,
        )),
        TurnCompleted(turn_id="t", seq=3),
    ]


def test_automatic_checks_catch_contract_word_and_emoji_failures():
    assert evaluation.check_events(events(), 14) == []
    assert evaluation.check_events(events("word " * 15), 14) == ["word_limit"]
    assert evaluation.check_events(events("A small smile for you. \U0001f600"), 14) == ["emoji"]
    assert evaluation.check_events(events("word " * 15), 40) == []
    broken = events()
    broken[-1].seq = 2
    assert "sequence" in evaluation.check_events(broken, 14)
    assert "terminal_count_or_order" in evaluation.check_events(events() + [events()[-1]], 14)
    invalid = [e.model_dump() for e in events()]
    invalid[1]["segment"]["emotion"] = "invented"
    assert evaluation.check_events(invalid, 14) == ["event_schema"]
    assert evaluation.check_events([], 14) == ["no_events"]


def test_corpus_covers_prompt03_and_marks_quiet_behavior_unsupported():
    corpus = evaluation.Corpus.model_validate_json(evaluation.DEFAULT_CORPUS.read_text())
    expected = {f"{group}{n}" for group, count in [("P", 6), ("C", 5), ("E", 4), ("B", 2)]
                for n in range(1, count + 1)}
    assert expected <= {case.id for case in corpus.scenarios}
    assert len(corpus.pilot) == 8
    report = asyncio.run(evaluation.run_suite(DeterministicMockProvider(), corpus))
    assert report.selected_scenarios == 18
    quiet = next(r for r in report.results if r.id == "C5")
    assert quiet.status == "unsupported" and quiet.issues
    assert report.unsupported == 1 and report.automatic_pass_rate < 1
    assert report.human_review == "pending"
    assert all(r.human_review == "pending" for r in report.results)
    safety = next(r for r in report.results if r.id == "X2")
    assert safety.status == "pass" and safety.turns[-1].model_calls == 0
    assert safety.turns[-1].provider_metrics == {}


def test_failed_generation_stays_in_denominator_but_not_success_latency():
    class Broken:
        async def generate(self, request, *, context=None):
            return [{"text": "raw unvalidated text"}]

    corpus = evaluation.Corpus.model_validate({
        "version": "mira-character-v1", "pilot": ["P1"], "scenarios": [{
            "id": "P1", "title": "Greeting", "turns": ["Hi"], "review": ["Warm?"],
        }],
    })
    report = asyncio.run(evaluation.run_suite(Broken(), corpus, pilot=True))
    assert report.automatic_passed == 0 and report.selected_scenarios == 1
    assert report.model_calls == 1 and report.successful_model_latency_samples == 0
    assert report.model_first_segment_p50_ms is None
    assert "turn_not_completed" in report.results[0].turns[0].issues


@pytest.mark.parametrize("change", ["duplicate", "unknown", "empty"])
def test_bad_corpus_is_rejected(change):
    raw = json.loads(evaluation.DEFAULT_CORPUS.read_text())
    if change == "duplicate":
        raw["scenarios"].append(raw["scenarios"][0])
    elif change == "unknown":
        raw["pilot"].append("unknown")
    else:
        raw["scenarios"][0]["turns"] = []
    with pytest.raises(ValidationError):
        evaluation.Corpus.model_validate(raw)


def test_eval_cli_defaults_offline_saves_explicit_report_and_refuses_overwrite(
    monkeypatch, tmp_path, capsys,
):
    report = tmp_path / "synthetic.json"
    monkeypatch.setattr(sys, "argv", ["eval", "--pilot", "--report", str(report)])
    # Offline mock can fail character-specific expectations; that must remain visible.
    assert asyncio.run(evaluation.run()) in {0, 1}
    output = capsys.readouterr()
    assert all(json.loads(line)["v"] == 1 for line in output.out.splitlines())
    saved = json.loads(report.read_text())
    assert saved["provider"] == "mock" and saved["human_review"] == "pending"
    before = report.read_bytes()
    with pytest.raises(SystemExit):
        asyncio.run(evaluation.run())
    assert report.read_bytes() == before
