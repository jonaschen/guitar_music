"""Persist personal hypotheses without treating them as music ground truth."""
import asyncio
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from .core.config import Settings
from .models.jobs import JobStatus
from .services.song_structure import source_for_job, StructureConflict
from .services.learning_practice import LearningStore, LearningDocument, LearningSave, LearningConflict


def get_learning_store():return LearningStore(Settings.from_env().work_dir/'learning-practice.sqlite3')


def create_learning_router(get_job_service):
    router=APIRouter(prefix='/api/v1/jobs',tags=['Learning practice'])
    def current(job,service):
        try:
            item=service.get(job)
            if item.status!=JobStatus.COMPLETED or item.score is None:raise HTTPException(409,'請先完成歌曲分析。')
            return source_for_job(item,service.store.job_dir(job)).model_dump(mode='json')
        except FileNotFoundError:raise HTTPException(404,'來源錄音不在主機，已保存筆記仍保留。')
        except StructureConflict:raise HTTPException(409,'錄音來源已變動。')
        except OSError:raise HTTPException(503,'錄音來源暫時無法核對。')
    async def run(action):
        try:return await asyncio.to_thread(action)
        except LearningConflict as error:raise HTTPException(409,str(error))
        except ValueError as error:raise HTTPException(422,str(error))
        except sqlite3.OperationalError:raise HTTPException(503,'學習筆記保存暫時忙碌，草稿請先保留。')
    def snapshot(value,source,error=None):
        return dict(**value,current_source=source,source_matches=bool(source and value['document']['source']==source),source_error=error)
    @router.get('/{job_id}/learning-practice')
    async def read(job_id:str,service=Depends(get_job_service),store=Depends(get_learning_store)):
        def action():
            value=store.read(job_id)
            try:source=current(job_id,service)
            except HTTPException as error:
                if value['document'] is None:raise
                return snapshot(value,None,error.detail)
            if value['document'] is None:value['document']=LearningDocument(source=source).model_dump(mode='json')
            return snapshot(value,source)
        return await run(action)
    @router.put('/{job_id}/learning-practice')
    async def save(job_id:str,body:LearningSave,service=Depends(get_job_service),store=Depends(get_learning_store)):
        return await run(lambda:snapshot(store.save(job_id,body.document,body.expected_version,lambda:current(job_id,service)),body.document.source.model_dump(mode='json')))
    @router.get('/{job_id}/learning-practice/history')
    async def history(job_id:str,store=Depends(get_learning_store)):
        return await run(lambda:store.history(job_id))
    return router
