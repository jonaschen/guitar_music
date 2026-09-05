import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..models.score import SongScore


class RevisionStore:
    """SQLite persistence for score revisions; no external database dependency."""

    def __init__(self, root_dir: Path):
        root_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = root_dir / "guitarscribe.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scores (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY,
                    score_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (score_id) REFERENCES scores(id)
                );
                CREATE INDEX IF NOT EXISTS revisions_score_id_idx ON revisions(score_id);
                """
            )

    def save(self, score: SongScore, revision_id: str | None = None) -> str:
        resolved_id = revision_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload = score.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO scores(id, payload, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (resolved_id, payload, now),
            )
            connection.execute(
                "INSERT INTO revisions(id, score_id, payload, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, created_at=excluded.created_at",
                (resolved_id, resolved_id, payload, now),
            )
        return resolved_id

    def load(self, revision_id: str) -> SongScore:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM revisions WHERE id = ?", (revision_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Revision not found: {revision_id}")
        return SongScore.model_validate_json(row["payload"])
