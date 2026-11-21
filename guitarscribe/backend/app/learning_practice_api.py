"""Persist personal hypotheses without treating them as music ground truth."""
import asyncio
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from .core.config import Settings
from .models.jobs import JobStatus
from .services.song_structure import source_for_job, StructureConflict, source_and_audio_for_job
from .services.chord_pitch_energy import pitch_energy
from .services.song_structure import StructureModel
from pydantic import Field
import soundfile as sf
from .services.learning_practice import LearningStore, LearningDocument, LearningSave, LearningConflict


class EnergyRequest(StructureModel):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    audio_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    start: float = Field(ge=0,allow_inf_nan=False)
    end: float = Field(gt=0,allow_inf_nan=False)


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
        except (sf.LibsndfileError,OSError):raise HTTPException(503,'錄音暫時無法讀取，原筆記仍保留。')
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
    @router.post('/{job_id}/learning-practice/pitch-energy')
    async def energy(job_id:str,body:EnergyRequest,service=Depends(get_job_service)):
        def action():
            source=current(job_id,service)
            if source['fingerprint']!=body.fingerprint or source['audio_sha256']!=body.audio_sha256:raise HTTPException(409,'錄音來源已變動，請重新載入。')
            if not .5<=body.end-body.start<=30 or body.end>source['duration']:raise HTTPException(422,'請選錄音內 0.5–30 秒的範圍。')
            _,path=source_and_audio_for_job(service.get(job_id),service.store.job_dir(job_id))
            with sf.SoundFile(path) as recording:
                recording.seek(round(body.start*recording.samplerate))
                samples=recording.read(round((body.end-body.start)*recording.samplerate),dtype='float64',always_2d=True)
                result=pitch_energy(samples,recording.samplerate)
            if current(job_id,service)!=source:raise HTTPException(409,'讀取途中錄音已變動。')
            return dict(**result,source=source,start=body.start,end=body.end)
        return await run(action)

    @router.get('/{job_id}/learning-practice/history')
    async def history(job_id:str,store=Depends(get_learning_store)):
        return await run(lambda:store.history(job_id))
    return router
