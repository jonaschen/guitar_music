"""Apply the unchanged bounded policy to the user's newly confirmed grid."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.services.chord_timing_candidate import build_timing_candidate,restore_detected_timing
from app.exporters.midi import compile_playback_manifest,export_midi

root=Path(__file__).resolve().parents[2]
prior=root/'output/evaluation/accompaniment-regression-2026-10-26/third-candidate.json'
source=root/'output/evaluation/cross-source-chords-2026-10-26-verified/third-source.wav'
out=root/'output/evaluation/confirmed-third-timing-2026-10-26';out.mkdir(parents=True,exist_ok=False)
score=SongScore.model_validate_json(prior.read_bytes())
assert score.song.duration_seconds==20
source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
assert source_hash==score.provenance.parameters['chord_source_audio_sha256']
protocol=dict(score_sha256=hashlib.sha256(prior.read_bytes()).hexdigest(),source_sha256=source_hash,
              policy='late-downbeat-v1 unchanged',source_window=[20,40],local_window=[0,20],
              user_feedback=['答答聲：在拍上','較高的重音：像小節第一拍'],
              mapping={'A':'original detected boundaries','B':'bounded late-downbeat candidate'},
              action='Independent preview only; no job or revision writes')
(out/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
candidate,changes,skipped=build_timing_candidate(score,0,20)
assert restore_detected_timing(candidate)==score
manifests=[compile_playback_manifest(s) for s in [score,candidate]]
guitars=[[e for e in m.events if e.track=='guitar'] for m in manifests]
assert [(e.start,e.stroke) for e in guitars[0]]==[(e.start,e.stroke) for e in guitars[1]]
assert [e for e in manifests[0].events if e.track!='guitar']==[e for e in manifests[1].events if e.track!='guitar']
changed=[dict(time=a.start,A=a.source_id,B=b.source_id) for a,b in zip(*guitars) if a.pitches!=b.pitches]
for label,s,m in zip(['A','B'],[score,candidate],manifests):
    (out/f'{label}-score.json').write_text(s.model_dump_json(indent=2))
    (out/f'{label}-manifest.json').write_text(m.model_dump_json(indent=2))
    (out/f'{label}.mid').write_bytes(export_midi(s))
shutil.copy2(source,out/'source.wav')
report=dict(window=[0,20],source_sha256=source_hash,changes=changes,skipped=skipped,
            changed_attacks=changed,stroke_count=len(guitars[0]),identical_rhythm=True,
            identical_non_guitar_events=True,exact_restoration=True,
            listening_hint='每段 20 秒。這是剛才已確認拍格的第三來源，只比較實際刷奏的換和弦時機。')
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(changes=changes,changed_attacks=changed,strokes=len(guitars[0])),indent=2))
