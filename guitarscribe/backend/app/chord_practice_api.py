"""Section-scoped chord drafts. The analysis, root and structure APIs stay separate."""
import asyncio
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .core.config import Settings
from .models.jobs import JobStatus
from .services.chord_practice import ChordPracticeStore, ChordSave, ChordConflict, initial_document, read_structure
from .services.song_structure import source_for_job, StructureConflict


def get_chord_practice_store():
    return ChordPracticeStore(Settings.from_env().work_dir / 'chord-practice.sqlite3')


def get_chord_structure_path():
    return Settings.from_env().work_dir / 'song-structure.sqlite3'


def create_chord_practice_router(get_job_service):
    router = APIRouter(prefix='/api/v1/jobs', tags=['Chord practice'])

    def current(job_id, service):
        try:
            job = service.get(job_id)
            if job.status != JobStatus.COMPLETED or job.score is None:
                raise HTTPException(409, '請等歌曲分析完成後再練習和弦。')
            return source_for_job(job, service.store.job_dir(job_id)).model_dump(mode='json'), job
        except FileNotFoundError:
            raise HTTPException(404, '錄音或分析已不在主機，已保存和弦仍可下載。')
        except StructureConflict:
            raise HTTPException(409, '原曲讀取時已變動，請重新載入。')
        except OSError:
            raise HTTPException(503, '目前無法讀取原曲，請保留草稿後重試。')

    def snapshot(result, source, structure, error=None):
        matches = bool(source and result['document'] and result['document']['source'] == source
                       and structure and structure['source'] == source)
        return dict(**result, current_source=source, source_matches=matches,
                    source_error=error or (None if matches else '原曲或歌曲結構來源不符，請保留草稿並重新載入。'))

    async def run(action):
        try: return await asyncio.to_thread(action)
        except ChordConflict as error: raise HTTPException(409, str(error))
        except ValueError as error: raise HTTPException(422, str(error))
        except sqlite3.OperationalError:
            raise HTTPException(503, '保存資料暫時忙碌，請保留草稿後重試。')

    @router.get('/{job_id}/chord-practice')
    async def read(job_id: str, service=Depends(get_job_service), store=Depends(get_chord_practice_store),
                   structure_path=Depends(get_chord_structure_path)):
        def action():
            result = store.read(job_id)
            try: source, job = current(job_id, service)
            except HTTPException as error:
                if result['document'] is None: raise
                return snapshot(result, None, None, error.detail)
            if result['document'] is None: result['document'] = initial_document(job, source)
            structure, _ = read_structure(structure_path, job_id)
            return snapshot(result, source, structure)
        return await run(action)

    @router.put('/{job_id}/chord-practice')
    async def save(job_id: str, body: ChordSave, service=Depends(get_job_service), store=Depends(get_chord_practice_store),
                   structure_path=Depends(get_chord_structure_path)):
        def provider():
            source, job = current(job_id, service)
            return source, initial_document(job, source)
        def action():
            # Check availability before waiting for a structure lock. Recheck
            # both source hashes inside the guarded save via provider.
            current(job_id, service)
            result = store.save(job_id, body, provider, structure_path)
            return snapshot(result, result['document']['source'], dict(source=result['document']['source']))
        return await run(action)

    @router.get('/{job_id}/chord-practice/history')
    async def history(job_id: str, store=Depends(get_chord_practice_store)):
        return await run(lambda: store.history(job_id))

    return router
