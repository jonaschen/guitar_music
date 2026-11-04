"""Verify the opt-in runtime decoder exactly matches every offline full-song case.

Usage: python verify_timing_batch_runtime.py MAIN_BATCH CONTINUITY_BATCH OUTPUT_JSON
Uses cached frames; does not repeat neural inference or mutate saved jobs.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.analyzers.beats.beat_this_main import BeatThisMainAnalyzer
from app.analyzers.beats.timing_diagnostics import BeatProjectionError
from app.models.audio import NormalizedAudio
from app.models.score import SongScore
from app.services.timing_checkpoint_candidate import build_checkpoint_candidate
from app.exporters.midi import compile_playback_manifest,export_midi


async def run(main,continuity,output):
    import numpy as np
    import torch
    from beat_this.model.postprocessor import Postprocessor
    torch.set_num_threads(2);rows=[]
    for case in json.loads((main/'plan.json').read_text())['cases']:
        job=case['job'];report=json.loads((continuity/job/'report.json').read_text())
        target=report['decoders'][report['selected_decoder']]
        with np.load(main/job/'logits.npz') as data:frames=tuple(torch.from_numpy(data[k]) for k in ('beat','downbeat'))
        engine=BeatThisMainAnalyzer(frame_predictor=lambda _:frames,decoder=Postprocessor('dbn'))
        result=None
        try:result=await engine.analyze(NormalizedAudio(path=Path(case['source']),duration_seconds=case['duration']))
        except BeatProjectionError:assert not target['engineering_pass']
        assert (result is not None)==target['engineering_pass']
        assert engine.recovery_report['candidate']['beats']==target['beats']
        assert engine.recovery_report['candidate']['downbeats']==target['downbeats']
        db=sqlite3.connect(f"file:{case['work']}/jobs/jobs.sqlite3?mode=ro",uri=True)
        payload=db.execute('SELECT payload FROM jobs WHERE id=?',(job,)).fetchone()[0];db.close()
        assert hashlib.sha256(payload.encode()).hexdigest()==case['payload_sha256']
        assert hashlib.sha256(Path(case['source']).read_bytes()).hexdigest()==case['source_sha256']
        score=SongScore.model_validate(json.loads(payload)['score']);candidate=None
        matching_source=score.song.source_url==case['source_url']
        if result is not None and score.analysis.timing_status=='unmetered' and matching_source:
            candidate=build_checkpoint_candidate(score,report)
            assert candidate.beats==result.beats
            assert candidate.chords==score.chords and candidate.rhythm==score.rhythm
            manifest=compile_playback_manifest(candidate)
            assert all(0<=e.start<e.end<=candidate.song.duration_seconds for e in manifest.events)
            assert export_midi(candidate).startswith(b'MThd')
        rows.append(dict(job=job,runtime_matches_offline=True,engineering_pass=result is not None,
            original_timing=score.analysis.timing_status,candidate_checked=candidate is not None,
            score_source_url_matches=matching_source,
            source_and_job_unchanged=True))
        output.write_text(json.dumps(rows,indent=2))
        print(job, 'pass' if result is not None else 'rejected',flush=True)
    output.write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))


if __name__=='__main__':asyncio.run(run(*map(Path,sys.argv[1:])))
