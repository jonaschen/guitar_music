"""Read existing production sources and caches; write diagnostics only, never user drafts."""
import hashlib,json,sqlite3,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.jobs import AnalysisJob
from app.services.root_practice import PracticeDocument, initial_document, source_for_job
from app.services.root_candidate_jobs import RootCandidateJobs
from app.services.root_segments import PracticeGrid, segmentation_plan
root=Path(__file__).resolve().parents[2]
work=root/'output/web-preview/work';out=root/'output/evaluation/root-practice-metrical-2026-11-12'
out.mkdir(parents=True,exist_ok=True)
results=[]
for job_id in ['83a3643ab3814172a046cebf709f3413','a3be29912a7045448765290d7cba2f6c']:
    with sqlite3.connect(f'file:{work}/jobs/jobs.sqlite3?mode=ro',uri=True) as db:
        job=AnalysisJob.model_validate_json(db.execute('SELECT payload FROM jobs WHERE id=?',(job_id,)).fetchone()[0])
    with sqlite3.connect(f'file:{work}/root-practice.sqlite3?mode=ro',uri=True) as db:
        row=db.execute('SELECT document,version FROM root_practice WHERE job_id=?',(job_id,)).fetchone()
    document=json.loads(row[0]) if row else initial_document(job).model_dump(mode='json')
    evidence=RootCandidateJobs().evidence(work/'jobs'/job_id,source_for_job(job).model_dump(mode='json'))
    start=time.monotonic();plan=segmentation_plan(document,PracticeGrid(bpm=115,beats=4,anchor=15.959),evidence);elapsed=time.monotonic()-start
    PracticeDocument.model_validate(plan['document'])
    cache=work/'jobs'/job_id/'root-evidence-v1.json'
    result=dict(job=job_id,source_fingerprint=document['source']['fingerprint'],source_start=document['source']['source_start'],duration=document['source']['duration'],practice_version=row[1] if row else 0,grid=plan['document']['grid'],old_segments=len(document['segments']),new_segments=len(plan['document']['segments']),bars=plan['bars'],exceptions=plan['exceptions'],preserved=plan['preserved'],review_count=len(plan['review']),evidence_available=plan['evidence_available'],cache_sha256=hashlib.sha256(cache.read_bytes()).hexdigest() if cache.exists() else None,elapsed_seconds=elapsed,music_correctness='unknown; no reference labels; second-song BPM is a control grid, not a tempo claim',user_data_written=False)
    (out/f'segments-{job_id}.json').write_text(json.dumps(dict(summary=result,plan=plan),ensure_ascii=False,indent=2)+'\n');results.append(result)
(out/'sources.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{k:r[k] for k in ['job','old_segments','new_segments','bars','review_count','preserved','elapsed_seconds']}|{'exceptions':len(r['exceptions'])} for r in results]))
