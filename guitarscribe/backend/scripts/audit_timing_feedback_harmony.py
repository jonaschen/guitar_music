"""Frozen score-only audit for 11-05 feedback. No inference, editing or listening candidates."""
import json
import hashlib
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.models.analysis import BeatInfo,RhythmSuggestion
from app.evaluation.sustained_harmony import audit_sustained_harmony
from app.services.downbeat_rhythm import PATTERN_ID


def run(root,output):
    output.mkdir(parents=True,exist_ok=False)
    frozen=root/'output/evaluation/timing-batch-review-2026-11-04'
    main=root/'output/evaluation/timing-main-model-2026-11-04'
    score=SongScore.model_validate_json((frozen/'strumming-input/3/a-score.json').read_text())
    reviewed=audit_sustained_harmony(score,24,64)
    reviewed['score_sha256']=hashlib.sha256(score.model_dump_json().encode()).hexdigest()
    reviewed['human_reported_player_window']=[18,24]
    (output/'reviewed-a.json').write_text(json.dumps(reviewed,ensure_ascii=False,indent=2))
    rows=[]
    for case in json.loads((main/'plan.json').read_text())['cases']:
        db=sqlite3.connect(f"file:{case['work']}/jobs/jobs.sqlite3?mode=ro",uri=True)
        payload=db.execute('SELECT payload FROM jobs WHERE id=?',(case['job'],)).fetchone()[0];db.close()
        assert hashlib.sha256(payload.encode()).hexdigest()==case['payload_sha256']
        original=SongScore.model_validate(json.loads(payload)['score']);s=original.model_copy(deep=True)
        timing=json.loads((main/case['job']/'report.json').read_text())['decoders']['dbn']
        basis='original_metered_score'
        if s.analysis.timing_status=='unmetered':
            if not timing['engineering_pass']:
                rows.append(dict(job=case['job'],source=case['source_url'],action='no_usable_full_grid'));continue
            projection=timing['projection'];basis='unconfirmed_final0_dbn'
            s.beats=[BeatInfo.model_validate(b) for b in projection['beats']]
            s.analysis.timing_status='metered';s.analysis.bpm=projection['bpm'];s.analysis.time_signature=projection['time_signature']
        s.rhythm=RhythmSuggestion(pattern_id=PATTERN_ID,label='每小節一下')
        audit=audit_sustained_harmony(s,0,s.song.duration_seconds)
        (output/(case['job']+'.json')).write_text(json.dumps(audit,ensure_ascii=False,indent=2))
        rows.append(dict(job=case['job'],source=case['source_url'],grid_basis=basis,
            events=audit['events'],majority_other_events=audit['majority_other_events'],
            other_score_harmony_seconds=audit['other_score_harmony_seconds'],applied=False))
        assert s.chords==original.chords
    (output/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print(json.dumps({'reviewed':{k:reviewed[k]for k in ['events','majority_other_events','other_score_harmony_seconds']},
        'near_20_seconds':[r for r in reviewed['rows'] if r['clip_end']>=42 and r['clip_start']<48], 'corpus':rows},ensure_ascii=False,indent=2))


if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]))
