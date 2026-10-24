"""Authoritative workout, ownership, persistence and transaction regressions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from pydantic import ValidationError

from hope_brain.workout import (
    Actor,
    ConfirmTargetChange,
    EndWorkout,
    ProposeTarget,
    StartWorkout,
    ToolRequest,
    UpdateReps,
    WorkoutError,
)
from hope_brain.workout_store import SQLiteWorkoutRepository

OWNER = Actor(user_id="owner", session_id="session")


@pytest.fixture
def repo():
    store = SQLiteWorkoutRepository()
    store.register_session(OWNER)
    yield store
    store.close()


def request(store, action, *, actor=OWNER, **overrides):
    state = store.get(actor)
    return ToolRequest.model_validate(
        {
            "command_id": uuid4(),
            "submission_id": uuid4(),
            "set_id": None if isinstance(action, StartWorkout) or state is None else state.set_id,
            "expected_version": state.version if state else 0,
            "action": action,
            **overrides,
        }
    )


def apply(store, action, *, actor=OWNER, origin="user", **overrides):
    return store.apply(actor, request(store, action, actor=actor, **overrides), origin=origin)


def start(store, target=12):
    return apply(store, StartWorkout(exercise="pushups", target=target))


def change(store, target):
    proposal = apply(store, ProposeTarget(target=target)).pending_proposal
    return apply(store, ConfirmTargetChange(proposal_id=proposal.proposal_id))


def test_s1_ten_of_twelve_means_two(repo):
    start(repo)
    state = apply(repo, UpdateReps(increment=10))
    assert (state.reps_done, state.target, state.remaining) == (10, 12, 2)
    assert state.last_confirmed_update.total == 10
    assert state.last_confirmed_update.actor == OWNER.user_id


def test_proposal_never_changes_target_without_user_confirmation(repo):
    start(repo)
    state = apply(repo, ProposeTarget(target=15), origin="model")
    assert state.target == 12 and state.goal_history == ()
    pending = state.pending_proposal
    with pytest.raises(WorkoutError, match="action_not_authorized"):
        apply(repo, ConfirmTargetChange(proposal_id=pending.proposal_id), origin="model")
    confirmed = apply(repo, ConfirmTargetChange(proposal_id=pending.proposal_id))
    assert confirmed.target == 15
    history = confirmed.goal_history[-1]
    assert (history.old_target, history.new_target, history.actor) == (12, 15, "model")
    assert history.confirmed_by == OWNER.user_id
    assert history.confirmed_at >= history.proposed_at
    assert history.reason == "user_request"


@pytest.mark.parametrize(
    "action",
    [
        StartWorkout(exercise="squats", target=10),
        UpdateReps(increment=1),
        EndWorkout(),
    ],
)
def test_model_cannot_execute_mutations(repo, action):
    start(repo)
    before = repo.get(OWNER)
    with pytest.raises(WorkoutError, match="action_not_authorized"):
        apply(repo, action, origin="model")
    assert repo.get(OWNER) == before


def test_s4_two_increases_maximum_even_after_lowering(repo):
    start(repo)
    change(repo, 15)
    assert change(repo, 18).raises_used == 2
    assert change(repo, 17).raises_used == 2
    with pytest.raises(WorkoutError, match="target_cap"):
        apply(repo, ProposeTarget(target=20))
    assert repo.get(OWNER).target == 17


def test_increase_limited_to_three_and_lower_bound_is_confirmed_reps(repo):
    start(repo)
    with pytest.raises(WorkoutError, match="target_cap"):
        apply(repo, ProposeTarget(target=16))
    apply(repo, UpdateReps(increment=10))
    with pytest.raises(WorkoutError, match="invalid_target"):
        apply(repo, ProposeTarget(target=9))
    assert change(repo, 10).status == "completed"


@pytest.mark.parametrize("value", [-1, 0, 21, True, 1.5, "5"])
def test_rep_increment_rejects_invalid_boundaries(value):
    with pytest.raises(ValidationError):
        UpdateReps(increment=value)


@pytest.mark.parametrize("value", [-1, 0, 101, True, 1.5, "12"])
def test_target_rejects_invalid_boundaries(value):
    with pytest.raises(ValidationError):
        StartWorkout(exercise="pushups", target=value)


def test_duplicate_command_and_transcript_ids_do_not_double_count(repo):
    start(repo)
    original = request(repo, UpdateReps(increment=5))
    state = repo.apply(OWNER, original, origin="user")
    for duplicate in [
        original,
        original.model_copy(update={"command_id": uuid4()}),
        original.model_copy(update={"submission_id": uuid4()}),
    ]:
        with pytest.raises(WorkoutError, match="duplicate_submission"):
            repo.apply(OWNER, duplicate, origin="user")
        assert repo.get(OWNER) == state


def test_stale_versions_and_wrong_sets_cannot_change_state(repo):
    started = start(repo)
    stale = request(repo, UpdateReps(increment=1))
    current = apply(repo, UpdateReps(increment=2))
    with pytest.raises(WorkoutError, match="stale_version"):
        repo.apply(OWNER, stale, origin="user")
    with pytest.raises(WorkoutError, match="wrong_set"):
        apply(repo, UpdateReps(increment=1), set_id=uuid4())
    assert repo.get(OWNER) == current
    assert current.version > started.version


def test_rep_update_invalidates_pending_confirmation(repo):
    start(repo)
    pending = apply(repo, ProposeTarget(target=15)).pending_proposal
    apply(repo, UpdateReps(increment=1))
    with pytest.raises(WorkoutError, match="proposal_not_found"):
        apply(repo, ConfirmTargetChange(proposal_id=pending.proposal_id))
    assert repo.get(OWNER).target == 12


def test_owner_and_session_isolation(repo):
    state = start(repo)
    foreign = Actor(user_id="intruder", session_id=OWNER.session_id)
    unknown = Actor(user_id="owner", session_id="unregistered")
    for actor in [foreign, unknown]:
        with pytest.raises(WorkoutError, match="unauthorized"):
            repo.get(actor)
        with pytest.raises(WorkoutError, match="unauthorized"):
            repo.stop(actor)
        command = request(repo, UpdateReps(increment=1))
        with pytest.raises(WorkoutError, match="unauthorized"):
            repo.apply(actor, command, origin="user")
    with pytest.raises(WorkoutError, match="unauthorized"):
        repo.register_session(foreign)
    other_session = Actor(user_id="owner", session_id="other")
    repo.register_session(other_session)
    with pytest.raises(WorkoutError, match="unknown_state"):
        repo.get(other_session, state.set_id)
    with pytest.raises(WorkoutError, match="unknown_state"):
        apply(repo, UpdateReps(increment=1), actor=other_session, set_id=state.set_id)
    assert repo.get(OWNER) == state


def test_stop_discards_pending_proposals_and_is_idempotent(repo):
    start(repo)
    apply(repo, ProposeTarget(target=15))
    stopped = repo.stop(OWNER)
    assert stopped.status == "stopped" and stopped.pending_proposal is None
    assert repo.stop(OWNER) == stopped
    with pytest.raises(WorkoutError, match="set_closed"):
        apply(repo, UpdateReps(increment=1))


def test_new_set_keeps_old_history_and_increases_version(repo):
    first = start(repo)
    change(repo, 15)
    ended = apply(repo, EndWorkout())
    second = start(repo, 10)
    assert second.set_id != first.set_id
    assert second.version == ended.version + 1
    assert second.raises_used == 0
    assert repo.get(OWNER, first.set_id).goal_history[-1].new_target == 15


def test_state_and_receipts_survive_restart(tmp_path):
    path = str(tmp_path / "workout.db")
    first = SQLiteWorkoutRepository(path)
    first.register_session(OWNER)
    start(first)
    command = request(first, UpdateReps(increment=5))
    state = first.apply(OWNER, command, origin="user")
    first.close()
    second = SQLiteWorkoutRepository(path)
    try:
        assert second.get(OWNER) == state
        with pytest.raises(WorkoutError, match="duplicate_submission"):
            second.apply(OWNER, command, origin="user")
        assert second._db.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        second.close()


@pytest.mark.parametrize("duplicate", [False, True])
def test_concurrent_delivery_across_connections_commits_once(tmp_path, duplicate):
    path = str(tmp_path / "concurrent.db")
    first, second = SQLiteWorkoutRepository(path), SQLiteWorkoutRepository(path)
    try:
        first.register_session(OWNER)
        start(first)
        one = request(first, UpdateReps(increment=1))
        two = one if duplicate else request(second, UpdateReps(increment=1))
        barrier = Barrier(2)

        def execute(store, command):
            barrier.wait(timeout=3)
            try:
                store.apply(OWNER, command, origin="user")
                return "committed"
            except WorkoutError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(execute, store, command)
                for store, command in [(first, one), (second, two)]
            ]
            results = [future.result(timeout=5) for future in futures]
        assert sorted(results) == sorted(
            ["committed", "duplicate_submission" if duplicate else "stale_version"]
        )
        assert first.get(OWNER).reps_done == 1
    finally:
        first.close()
        second.close()


def test_failed_receipt_write_rolls_back_state(repo):
    import sqlite3

    before = start(repo)
    repo._db.execute("""CREATE TRIGGER reject_receipt BEFORE INSERT ON receipts
        BEGIN SELECT RAISE(ABORT, 'simulated storage failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        apply(repo, UpdateReps(increment=5))
    assert repo.get(OWNER) == before


def test_forged_model_instance_is_revalidated(repo):
    start(repo)
    command = request(repo, UpdateReps(increment=1))
    forged = command.model_copy(update={"action": UpdateReps.model_construct(increment=-1)})
    with pytest.raises(ValidationError):
        repo.apply(OWNER, forged, origin="user")
    assert repo.get(OWNER).reps_done == 0


def test_superseded_and_invalidated_proposals_remain_in_audit_history(repo):
    start(repo)
    first = apply(repo, ProposeTarget(target=14)).pending_proposal
    second = apply(repo, ProposeTarget(target=15)).pending_proposal
    state = apply(repo, UpdateReps(increment=1))
    assert state.pending_proposal is None
    assert state.target_proposals == (first, second)
    assert state.goal_history == () and state.target == 12
    for proposal in [first, second]:
        with pytest.raises(WorkoutError, match="proposal_not_found"):
            apply(repo, ConfirmTargetChange(proposal_id=proposal.proposal_id))
