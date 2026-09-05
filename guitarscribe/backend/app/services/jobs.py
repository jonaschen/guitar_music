import asyncio
import shutil
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
    """Small filesystem-backed store for the single-process MVP worker."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def save(self, job: AnalysisJob) -> None:
        directory = self.job_dir(job.id)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / "job.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(destination)

    def load(self, job_id: str) -> AnalysisJob:
        path = self.job_dir(job_id) / "job.json"
        if not path.exists():
            raise FileNotFoundError(job_id)
        return AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))

    def cleanup_expired(self, ttl_seconds: int) -> int:
        cutoff = time.time() - ttl_seconds
        removed = 0
        for directory in self.root.iterdir():
            if directory.is_dir() and directory.stat().st_mtime < cutoff:
                shutil.rmtree(directory)
                removed += 1
        return removed

    def mark_interrupted_jobs_failed(self) -> None:
        for path in self.root.glob("*/job.json"):
            job = AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))
            if job.status in ACTIVE_JOB_STATUSES:
                job.status = JobStatus.FAILED
                job.error = "The server restarted before this analysis completed."
                job.message = "Analysis interrupted by server restart"
                job.updated_at = _now()
                self.save(job)


class AnalysisJobService:
    def __init__(self, store: JobStore, pipeline_factory: Callable[[], AnalysisPipeline], max_concurrent_jobs: int = 1, job_ttl_seconds: int = 24 * 60 * 60):
        self.store = store
        self.pipeline_factory = pipeline_factory
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent_jobs)
        self.store.cleanup_expired(job_ttl_seconds)
        self.store.mark_interrupted_jobs_failed()

    async def submit(
        self,
        filename: str,
        content: bytes,
        melody_mode: str,
        chord_complexity: str,
    ) -> AnalysisJob:
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
            task = self.tasks.get(job_id)
            if task:
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
