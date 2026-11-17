"""Explicit, previewed root reuse; all mutations share the root SQLite CAS."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from .models.jobs import JobStatus
from .services.root_practice import PracticeConflict
from .services.root_reuse import RootReuseService, ReuseRequest, ReuseApply, ReuseUndo, ReuseNotFound
from .services.song_structure import source_for_job, StructureConflict


def create_reuse_router(get_job_service, get_root_practice_store):
    router = APIRouter()

    def current_source(job_id, service):
        try:
            job = service.get(job_id)
            if job.status != JobStatus.COMPLETED or job.score is None:
                raise HTTPException(409, '請等原曲分析完成後再沿用根音。')
            return source_for_job(job, service.store.job_dir(job_id)).model_dump(mode='json')
        except FileNotFoundError:
            raise HTTPException(404, '原曲音訊已不在此主機，仍可檢視沿用紀錄。')
        except StructureConflict as error:
            raise HTTPException(409, str(error))
        except OSError:
            raise HTTPException(503, '暫時無法讀取原曲，請稍後重試。')

    async def run(action):
        try:
            return await asyncio.to_thread(action)
        except PracticeConflict as error:
            raise HTTPException(409, str(error))
        except ReuseNotFound as error:
            raise HTTPException(404, str(error))
        except ValueError as error:
            raise HTTPException(422, str(error))

    @router.post('/{job_id}/root-practice/reuse-plan')
    async def plan(job_id: str, body: ReuseRequest, service=Depends(get_job_service),
                   store=Depends(get_root_practice_store)):
        return await run(lambda: RootReuseService(store).plan(job_id, body, current_source(job_id, service)))

    @router.post('/{job_id}/root-practice/reuse-apply')
    async def apply(job_id: str, body: ReuseApply, service=Depends(get_job_service),
                    store=Depends(get_root_practice_store)):
        return await run(lambda: RootReuseService(store).apply(job_id, body, lambda: current_source(job_id, service)))

    @router.get('/{job_id}/root-practice/reuse-ledger')
    async def ledger(job_id: str, service=Depends(get_job_service), store=Depends(get_root_practice_store)):
        def read():
            try:
                source = current_source(job_id, service)
            except HTTPException:
                source = None
            return RootReuseService(store).ledger(job_id, source)
        return await run(read)

    @router.post('/{job_id}/root-practice/reuse-ledger/{operation_id}/undo')
    async def undo(job_id: str, operation_id: str, body: ReuseUndo, service=Depends(get_job_service),
                   store=Depends(get_root_practice_store)):
        return await run(lambda: RootReuseService(store).undo(
            job_id, operation_id, body, lambda: current_source(job_id, service)))

    return router
