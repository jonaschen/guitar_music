"""Temporary real root/structure APIs and recording for reuse browser tests."""
import argparse, hashlib, json, math, struct, sys, wave
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
from app.models.jobs import JobStatus
from app.models.score import SongScore
from app.services.root_practice import RootPracticeStore,PracticeDocument,source_for_job
from app.services.song_structure import SongStructureStore,StructureDocument,source_and_audio_for_job
from app.root_practice_api import create_root_router,get_root_practice_store
from app.song_structure_api import create_song_structure_router,get_song_structure_store

def main():
 p=argparse.ArgumentParser();p.add_argument('--frontend',type=Path,required=True);p.add_argument('--port',type=int,default=5288);args=p.parse_args()
 with TemporaryDirectory(prefix='guitarscribe-reuse-') as temp:
  root=Path(temp); job=SimpleNamespace(id='reuse-fixture',status=JobStatus.COMPLETED,skip_seconds=42.,analysis_seconds=24.,score=SongScore.model_validate({'song':{'title':'Reuse fixture','duration_seconds':24.,'source_start_seconds':42.}}))
  with wave.open(str(root/'analysis-source.wav'),'wb') as a:
   a.setnchannels(1);a.setsampwidth(2);a.setframerate(8000);a.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i/8000*2*math.pi*220))) for i in range(24*8000)))
  store=RootPracticeStore(root/'root-practice.sqlite3');source=source_for_job(job).model_dump(mode='json')
  store.save(job.id,PracticeDocument.model_validate({'schema_version':2,'grid':{'bpm':60.,'beats':4,'anchor':0.},'source':source,'segments':[{'id':f'r{i}','start':float(i*4),'end':float((i+1)*4),'original_root':None,'root':[0,7,None,None,None,None][i],'status':['confirmed','confirmed','pending','unsure','pending','pending'][i]} for i in range(6)]}),0)
  structure=SongStructureStore(root/'song-structure.sqlite3');structure.save(job.id,StructureDocument.model_validate({'schema_version':1,'source':source_and_audio_for_job(job,root)[0].model_dump(mode='json'),'candidate_sha256':None,'sections':[{'id':f's{i}','start':float(i*8),'end':float((i+1)*8),'label':'chorus' if i<2 else 'outro','display_label':'副歌' if i<2 else '尾奏'} for i in range(3)]}),0)
  structure_hash=hashlib.sha256(structure.path.read_bytes()).hexdigest();score=job.score.model_dump_json()
  def get(identifier):
   if identifier!=job.id:raise FileNotFoundError(identifier)
   return job
  service=SimpleNamespace(get=get,store=SimpleNamespace(job_dir=lambda _:root));api=FastAPI();api.include_router(create_root_router(lambda:service));api.include_router(create_song_structure_router(lambda:service))
  api.dependency_overrides[get_root_practice_store]=lambda:store;api.dependency_overrides[get_song_structure_store]=lambda:structure
  @api.get('/fixture/invariants')
  def invariants():return {'structure_unchanged':hashlib.sha256(structure.path.read_bytes()).hexdigest()==structure_hash,'score_unchanged':score==job.score.model_dump_json()}
  app=FastAPI();app.mount('/backend',api);app.mount('/',StaticFiles(directory=args.frontend,html=True));uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')
if __name__=='__main__':main()
