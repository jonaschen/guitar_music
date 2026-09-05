import asyncio
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ..core.pipeline import AnalysisPipeline
from ..models.audio import SourceRequest, SourceType
from ..models.jobs import ACTIVE_JOB_STATUSES, AnalysisJob, JobStatus


STAGE_DETAILS: dict[str, tuple[JobStatus, int, str]] = {
    "resolving": (JobStatus.RESOLVING, 5, "Preparing audio"),
    "preprocessing": (JobStatus.PREPROCESSING, 15, "Normalizing audio"),
    "beat_analysis": (JobStatus.BEAT_ANALYSIS, 35, "Finding beats and bars"),
    "chord_analysis": (JobStatus.CHORD_ANALYSIS, 55, "Recognizing chords"),
    "melody_analysis": (JobStatus.MELODY_ANALYSIS, 75, "Extracting melody"),
    "postprocessing": (JobStatus.POSTPROCESSING, 90, "Preparing guitar chart"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """SQLite-backed metadata store; job input artifacts remain under ``root``."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "jobs.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_updated_at_idx ON jobs(updated_at)")

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def save(self, job: AnalysisJob) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs(id, payload, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (job.id, job.model_dump_json(), job.updated_at),
            )

    def load(self, job_id: str) -> AnalysisJob:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(job_id)
        return AnalysisJob.model_validate_json(row["payload"])

    def cleanup_expired(self, ttl_seconds: int) -> int:
        cutoff = time.time() - ttl_seconds
        cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
        with self._connect() as connection:
            job_ids = [row["id"] for row in connection.execute("SELECT id FROM jobs WHERE updated_at < ?", (cutoff_iso,))]
            connection.execute("DELETE FROM jobs WHERE updated_at < ?", (cutoff_iso,))
        removed = 0
        for job_id in job_ids:
            directory = self.job_dir(job_id)
            if directory.exists():
                shutil.rmtree(directory)
            removed += 1
        for directory in self.root.iterdir():
            if directory.is_dir() and directory.stat().st_mtime < cutoff:
                shutil.rmtree(directory)
                removed += 1
        return removed

    def mark_interrupted_jobs_failed(self) -> None:
        with self._connect() as connection:
            payloads = [row["payload"] for row in connection.execute("SELECT payload FROM jobs")]
        for payload in payloads:
            job = AnalysisJob.model_validate_json(payload)
            if job.status in ACTIVE_JOB_STATUSES:
                job.status = JobStatus.FAILED
                job.error = "The server restarted before this analysis completed."
                job.message = "Analysis interrupted by server restart"
                job.updated_at = _now()
                self.save(job)


class AnalysisJobService:
    def __init__(
        self,
        store: JobStore,
        pipeline_factory: Callable[[], AnalysisPipeline],
        max_concurrent_jobs: int = 1,
        job_ttl_seconds: int = 24 * 60 * 60,
    ):
        self.store = store
        self.pipeline_factory = pipeline_factory
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.store.cleanup_expired(job_ttl_seconds)
        self.store.mark_interrupted_jobs_failed()

    async def submit(self, filename: str, content: bytes, melody_mode: str, chord_complexity: str) -> AnalysisJob:
        job_id = uuid4().hex
        now = _now()
        job = AnalysisJob(
            id=job_id,
            melody_mode=melody_mode,
            chord_complexity=chord_complexity,
            created_at=now,
            updated_at=now,
        )
        directory = self.store.job_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix or ".wav"
        (directory / f"input{suffix}").write_bytes(content)
        self.store.save(job)
        self.tasks[job_id] = asyncio.create_task(self._run(job_id))
        return job

    def get(self, job_id: str) -> AnalysisJob:
        return self.store.load(job_id)

    def cancel(self, job_id: str) -> AnalysisJob:
        job = self.get(job_id)
        if job.status in ACTIVE_JOB_STATUSES:
            if task := self.tasks.get(job_id):
                task.cancel()
            job.status = JobStatus.CANCELLED
            job.message = "Analysis cancelled"
            job.updated_at = _now()
            self.store.save(job)
        return job

    async def _run(self, job_id: str) -> None:
        await self.semaphore.acquire()
        try:
            job = self.get(job_id)
            input_path = next(self.store.job_dir(job_id).glob("input.*"))

            async def report(stage: str) -> None:
                status, progress, message = STAGE_DETAILS[stage]
                current = self.get(job_id)
                if current.status == JobStatus.CANCELLED:
                    raise asyncio.CancelledError()
                current.status = status
                current.progress = progress
                current.message = message
                current.updated_at = _now()
                self.store.save(current)

            score = await self.pipeline_factory().run(
                SourceRequest(source_type=SourceType.LOCAL, path=input_path, rights_confirmed=True),
                {"melody_mode": job.melody_mode, "chord_complexity": job.chord_complexity},
                progress_callback=report,
            )
            job = self.get(job_id)
            if job.status == JobStatus.CANCELLED:
                return
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.message = "Analysis complete"
            job.score = score
            job.updated_at = _now()
            self.store.save(job)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            job = self.get(job_id)
            if job.status != JobStatus.CANCELLED:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.message = "Analysis failed"
                job.updated_at = _now()
                self.store.save(job)
        finally:
            self.semaphore.release()
            self.tasks.pop(job_id, None)
