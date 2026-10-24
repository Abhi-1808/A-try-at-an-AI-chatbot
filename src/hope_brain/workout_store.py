"""SQLite transactions, ownership and replay protection for workout state."""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from hope_brain.workout import (
    Actor,
    CountStatement,
    Origin,
    ToolRequest,
    WorkoutError,
    WorkoutState,
    reduce_workout,
    revise,
)


class SQLiteWorkoutRepository:
    def __init__(self, path: str = ":memory:") -> None:
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        try:
            with self._transaction() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in {0, 1}:
                    raise WorkoutError("unsupported_schema")
                if version == 0:
                    db.execute("""CREATE TABLE sessions (
                        session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, current_set TEXT)""")
                    db.execute("""CREATE TABLE workouts (
                        set_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions,
                        state_json TEXT NOT NULL)""")
                    db.execute("""CREATE TABLE receipts (
                        session_id TEXT NOT NULL REFERENCES sessions,
                        command_id TEXT NOT NULL, submission_id TEXT NOT NULL,
                        PRIMARY KEY(session_id, command_id), UNIQUE(session_id, submission_id))""")
                    db.execute("PRAGMA user_version = 1")
        except BaseException:
            self._db.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise

    def register_session(self, actor: Actor) -> None:
        """Trusted application registration; not a public authentication endpoint."""
        actor = Actor.model_validate(actor)
        with self._transaction() as db:
            row = db.execute(
                "SELECT user_id FROM sessions WHERE session_id = ?", (actor.session_id,)
            ).fetchone()
            if row is not None and row[0] != actor.user_id:
                raise WorkoutError("unauthorized")
            db.execute(
                "INSERT OR IGNORE INTO sessions(session_id, user_id) VALUES (?, ?)",
                (actor.session_id, actor.user_id),
            )

    def _authorize(self, db: sqlite3.Connection, actor: Actor) -> str | None:
        row = db.execute(
            "SELECT user_id, current_set FROM sessions WHERE session_id = ?", (actor.session_id,)
        ).fetchone()
        if row is None or row[0] != actor.user_id:
            raise WorkoutError("unauthorized")
        return row[1]

    def _get(self, db: sqlite3.Connection, actor: Actor, set_id: str | None) -> WorkoutState | None:
        if set_id is None:
            return None
        row = db.execute(
            "SELECT state_json FROM workouts WHERE session_id = ? AND set_id = ?",
            (actor.session_id, set_id),
        ).fetchone()
        if row is None:
            raise WorkoutError("unknown_state")
        return WorkoutState.model_validate_json(row[0])

    def get(self, actor: Actor, set_id: UUID | None = None) -> WorkoutState | None:
        with self._transaction() as db:
            current = self._authorize(db, actor)
            return self._get(db, actor, str(set_id) if set_id else current)

    def _save(self, db: sqlite3.Connection, actor: Actor, state: WorkoutState) -> None:
        db.execute(
            """INSERT INTO workouts(set_id, session_id, state_json) VALUES (?, ?, ?)
            ON CONFLICT(set_id) DO UPDATE SET state_json = excluded.state_json""",
            (str(state.set_id), actor.session_id, state.model_dump_json()),
        )
        db.execute(
            "UPDATE sessions SET current_set = ? WHERE session_id = ?",
            (str(state.set_id), actor.session_id),
        )

    def apply(self, actor: Actor, request: ToolRequest, *, origin: Origin) -> WorkoutState:
        # Revalidate even model_construct/model_copy instances at the service boundary.
        actor = Actor.model_validate(actor)
        request = ToolRequest.model_validate(request)
        with self._transaction() as db:
            current = self._authorize(db, actor)
            duplicate = db.execute(
                """SELECT 1 FROM receipts WHERE session_id = ?
                AND (command_id = ? OR submission_id = ?)""",
                (actor.session_id, str(request.command_id), str(request.submission_id)),
            ).fetchone()
            if duplicate:
                raise WorkoutError("duplicate_submission")
            state = reduce_workout(
                self._get(db, actor, current),
                request,
                actor,
                origin,
                now=datetime.now(UTC),
                new_id=uuid4(),
            )
            self._save(db, actor, state)
            db.execute(
                "INSERT INTO receipts VALUES (?, ?, ?)",
                (actor.session_id, str(request.command_id), str(request.submission_id)),
            )
            return state

    def record_statement(self, actor: Actor, state: WorkoutState) -> WorkoutState:
        with self._transaction() as db:
            current = self._get(db, actor, self._authorize(db, actor))
            if (
                current is None
                or current.set_id != state.set_id
                or current.version != state.version
            ):
                raise WorkoutError("stale_version")
            claim = CountStatement(
                reps_done=current.reps_done, target=current.target, at=datetime.now(UTC)
            )
            current = revise(current, statements=(*current.statements[-49:], claim))
            self._save(db, actor, current)
            return current

    def stop(self, actor: Actor) -> WorkoutState | None:
        """Safety stop takes the latest version atomically; stores no symptoms."""
        with self._transaction() as db:
            current = self._get(db, actor, self._authorize(db, actor))
            if current is None or current.status in {"ended", "stopped"}:
                return current
            current = revise(
                current,
                status="stopped",
                pending_proposal=None,
                version=current.version + 1,
                updated_at=datetime.now(UTC),
            )
            self._save(db, actor, current)
            return current
