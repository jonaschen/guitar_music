"""Versioned structure-only editing. No writes to analysis jobs or root practice."""
import asyncio
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from .core.config import Settings
from .models.jobs import JobStatus
from .services.song_structure import SongStructureStore, StructureConflict, StructureSave, source_and_audio_for_job
from .services.song_structure import StructureModel, Digest
from .services.structure_analysis_jobs import StructureAnalysisJobs


def get_song_structure_store():
    return SongStructureStore(Settings.from_env().work_dir / 'song-structure.sqlite3')


@lru_cache(maxsize=1)
def get_structure_analysis_jobs():
    return StructureAnalysisJobs.from_env(Settings.from_env().work_dir)


class StructureAnalysisRequest(StructureModel):
    fingerprint: Digest
    audio_sha256: Digest
    force: bool = False


def create_song_structure_router(get_job_service):
    router = APIRouter(prefix='/api/v1/jobs', tags=['Song structure'])

    def read_source_and_audio(job_id, service):
        try:
            job = service.get(job_id)
            if job.status != JobStatus.COMPLETED or job.score is None:
                raise HTTPException(409, '請等歌曲分析完成後再編輯結構。')
            source, path = source_and_audio_for_job(job, service.store.job_dir(job_id))
            return source.model_dump(mode='json'), path
        except FileNotFoundError:
            raise HTTPException(404, '原音訊或分析已不在主機；已保存結構仍可下載。')
        except StructureConflict:
            raise HTTPException(409, '原音訊來源不明或讀取時已變動，請重新載入。')
        except OSError:
            raise HTTPException(503, '目前無法讀取原音訊，請保留草稿後重試。')

    async def current_source_and_audio(job_id, service):
        return await asyncio.to_thread(read_source_and_audio, job_id, service)

    @router.get('/{job_id}/song-structure/analysis')
    async def analysis_status(job_id: str, service=Depends(get_job_service), manager=Depends(get_structure_analysis_jobs)):
        source, _ = await current_source_and_audio(job_id, service)
        return await asyncio.to_thread(manager.status, job_id, source)

    @router.post('/{job_id}/song-structure/analysis')
    async def analysis_start(job_id: str, body: StructureAnalysisRequest, service=Depends(get_job_service),
                             manager=Depends(get_structure_analysis_jobs)):
        source, audio = await current_source_and_audio(job_id, service)
        if body.fingerprint != source['fingerprint'] or body.audio_sha256 != source['audio_sha256']:
            raise HTTPException(409, '原曲來源已變動，請重新載入後再分析結構。')
        job = await asyncio.to_thread(service.get, job_id)
        return await asyncio.to_thread(manager.start, job_id, source, audio, job.score.song.title or job_id,
                                       lambda: read_source_and_audio(job_id, service)[0], force=body.force)

    @router.delete('/{job_id}/song-structure/analysis')
    async def analysis_cancel(job_id: str, manager=Depends(get_structure_analysis_jobs)):
        # Cancellation must remain possible even if the source file disappeared.
        return await asyncio.to_thread(manager.cancel, job_id)

    @router.get('/{job_id}/song-structure/audio')
    async def audio(job_id: str, fingerprint: str = Query(pattern=r'^[a-f0-9]{64}$'),
                    audio_sha256: str = Query(pattern=r'^[a-f0-9]{64}$'),
                    service=Depends(get_job_service)):
        source, path = await current_source_and_audio(job_id, service)
        if source['fingerprint'] != fingerprint or source['audio_sha256'] != audio_sha256:
            raise HTTPException(409, '原曲或音訊已變動，不能與這份結構混用；請先下載備份。')
        # Browser range requests must come back through both source checks.
        return FileResponse(path, headers={'Cache-Control': 'no-store'})

    def snapshot(result, source, error=None):
        matches = source is not None and (result['document'] is None or result['document']['source'] == source)
        return dict(**result, current_source=source, source_matches=matches,
                    source_error=error or (None if matches else '來源已變動，請先下載舊稿；不能直接寫入目前歌曲。'))

    @router.get('/{job_id}/song-structure')
    async def get_structure(job_id: str, service=Depends(get_job_service), store=Depends(get_song_structure_store)):
        result = await asyncio.to_thread(store.read, job_id)
        try:
            source, _ = await current_source_and_audio(job_id, service)
        except HTTPException as error:
            if result['document'] is None:
                raise
            return snapshot(result, None, error.detail)
        return snapshot(result, source)

    @router.put('/{job_id}/song-structure')
    async def save_structure(job_id: str, body: StructureSave, service=Depends(get_job_service), store=Depends(get_song_structure_store)):
        source, _ = await current_source_and_audio(job_id, service)
        if body.document.source.model_dump(mode='json') != source:
            raise HTTPException(409, '結構稿與目前歌曲或音訊來源不符，請先下載草稿再重新載入。')
        try:
            result = await asyncio.to_thread(store.save, job_id, body.document, body.expected_version)
        except StructureConflict:
            raise HTTPException(409, '其他分頁或來源已更新；本頁草稿請先下載，再載入最新版本。')
        except ValueError:
            raise HTTPException(422, '歌曲結構格式或來源不符。')
        return snapshot(result, source)

    @router.get('/{job_id}/song-structure/history')
    async def history(job_id: str, store=Depends(get_song_structure_store)):
        return await asyncio.to_thread(store.history, job_id)

    @router.get('/{job_id}/song-structure/export')
    async def export(job_id: str, store=Depends(get_song_structure_store)):
        result = await asyncio.to_thread(store.read, job_id)
        if result['document'] is None:
            raise HTTPException(404, '這首歌尚未保存結構。')
        return JSONResponse(result['document'], headers={'Content-Disposition': 'attachment; filename="song-structure.json"'})

    return router
