"""Routes kept separate from the existing score/editing API."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .core.config import Settings
from .models.jobs import JobStatus
from .services.root_practice import RootPracticeStore, PracticeDocument, PracticeSave, PracticeConflict, initial_document, source_for_job
from .services.root_candidate_jobs import RootCandidateJobs
from .services.root_candidates import candidates_for_range
from .services.root_segments import PracticeGrid, segmentation_plan

manager = RootCandidateJobs()


def get_root_practice_store():
    return RootPracticeStore(Settings.from_env().work_dir / 'root-practice.sqlite3')


class CandidateRange(BaseModel):
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)


class SegmentPlan(BaseModel):
    document: PracticeDocument
    grid: PracticeGrid


def create_root_router(get_job_service):
    router = APIRouter(prefix='/api/v1/jobs', tags=['Root practice'])

    def job_for(job_id, service):
        try:
            job = service.get(job_id)
        except FileNotFoundError:
            raise HTTPException(404, '原曲已不在此主機，已保存的練習仍可下載。')
        if job.status != JobStatus.COMPLETED or job.score is None:
            raise HTTPException(409, '請等原曲分析完成後再開始練習。')
        return job

    def audio_for(job, directory):
        # Cropped sources also exist when skip=0 and analysis_seconds is set.
        cropped = directory / 'analysis-source.wav'
        paths = [cropped] if job.skip_seconds > 0 or job.analysis_seconds is not None else list(directory.glob('input.*'))
        paths = [p for p in paths if p.is_file()]
        if not paths:
            raise HTTPException(404, '原曲音訊已不在此主機，仍可使用已保存的練習。')
        return paths[0]

    @router.get('/{job_id}/root-practice/audio')
    async def audio(job_id: str, fingerprint: str, service=Depends(get_job_service)):
        job = job_for(job_id, service)
        if fingerprint != source_for_job(job).fingerprint:
            raise HTTPException(409, '原曲來源已變動，不能與這份練習混用。請先下載備份。')
        return FileResponse(audio_for(job, service.store.job_dir(job_id)))

    @router.get('/{job_id}/root-practice')
    async def read(job_id: str, service=Depends(get_job_service), store=Depends(get_root_practice_store)):
        result = await asyncio.to_thread(store.read, job_id)
        if result['document'] is None:
            job = job_for(job_id, service)
            evidence = await asyncio.to_thread(manager.evidence, service.store.job_dir(job_id), source_for_job(job).model_dump(mode='json'))
            result['document'] = (await asyncio.to_thread(initial_document, job, evidence)).model_dump(mode='json')
        return result

    @router.put('/{job_id}/root-practice')
    async def save(job_id: str, body: PracticeSave, service=Depends(get_job_service), store=Depends(get_root_practice_store)):
        existing = await asyncio.to_thread(store.read, job_id)
        if not existing['version'] and body.document.source != source_for_job(job_for(job_id, service)):
            raise HTTPException(409, '來源已變動，請下載草稿並重新開啟這首歌。')
        try:
            return await asyncio.to_thread(store.save, job_id, body.document, body.expected_version)
        except PracticeConflict:
            raise HTTPException(409, '其他分頁已更新進度；請先下載草稿，再載入最新版本。')
        except ValueError:
            raise HTTPException(422, '練習資料與原曲不符。')

    @router.get('/{job_id}/root-practice/history')
    async def history(job_id: str, store=Depends(get_root_practice_store)):
        return await asyncio.to_thread(store.history, job_id)

    @router.post('/{job_id}/root-practice/segment-plan')
    async def plan(job_id: str, body: SegmentPlan, service=Depends(get_job_service)):
        job = job_for(job_id, service)
        source = source_for_job(job)
        if body.document.source != source:
            raise HTTPException(409, '拍格草稿與原曲來源不符。')
        evidence = await asyncio.to_thread(manager.evidence, service.store.job_dir(job_id), source.model_dump(mode='json'))
        try:
            return await asyncio.to_thread(segmentation_plan, body.document.model_dump(mode='json'), body.grid, evidence)
        except ValueError as error:
            raise HTTPException(422, str(error))

    @router.get('/{job_id}/root-candidates')
    async def evidence_status(job_id: str, service=Depends(get_job_service)):
        job = job_for(job_id, service)
        return await asyncio.to_thread(manager.status, service.store.job_dir(job_id), source_for_job(job).model_dump(mode='json'))

    @router.post('/{job_id}/root-candidates')
    async def prepare(job_id: str, service=Depends(get_job_service)):
        job = job_for(job_id, service)
        directory = service.store.job_dir(job_id)
        return manager.start(directory, source_for_job(job).model_dump(mode='json'), audio_for(job, directory))

    @router.delete('/{job_id}/root-candidates')
    async def cancel(job_id: str, service=Depends(get_job_service)):
        job_for(job_id, service)
        return manager.cancel(service.store.job_dir(job_id))

    @router.post('/{job_id}/root-candidates/rank')
    async def rank(job_id: str, body: CandidateRange, service=Depends(get_job_service)):
        job = job_for(job_id, service)
        source = source_for_job(job).model_dump(mode='json')
        if body.fingerprint != source['fingerprint'] or not 0 <= body.start < body.end <= source['duration']:
            raise HTTPException(409, '這段練習與原曲範圍不符。')
        evidence = await asyncio.to_thread(manager.evidence, service.store.job_dir(job_id), source)
        if evidence is None:
            raise HTTPException(409, '參考音尚未準備完成。')
        result = await asyncio.to_thread(candidates_for_range, evidence, body.start, body.end)
        return dict(result, fingerprint=source['fingerprint'])

    return router
