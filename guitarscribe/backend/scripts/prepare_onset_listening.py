"""Prepare read-only real-song comparisons after the synthetic checkpoint passes."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.evaluation.onset_notes import decode_onset_aware
from app.evaluation.conservative_notes import decode_bounded
from app.evaluation.source_timed_audit import connected_note_frames, rounded_contour_frames, frame_loss
from app.models.score import SongScore
from app.models.melody_contour import MelodyContour
from app.exporters.midi import compile_playback_manifest, _selected_voicing_pitches
from app.services.playable_chords import with_default_voicings


def write(path,data):
    def native(value):
        if isinstance(value,np.generic):
            return value.item()
        raise TypeError(f'Unsupported JSON value: {type(value).__name__}')
    path.write_text(json.dumps(data,indent=2,allow_nan=False,default=native)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_payload(path,table,id):
    if table not in ('jobs','revisions'):
        raise ValueError('Unexpected table')
    with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as connection:
        row=connection.execute(f'select payload from {table} where id=?',(id,)).fetchone()
    if row is None:
        raise ValueError('Source record missing')
    return json.loads(row[0])


def clip_audio(source,target,start,end):
    with sf.SoundFile(source) as sound:
        sr=sound.samplerate
        sound.seek(round(start*sr))
        audio=sound.read(round((end-start)*sr),always_2d=True)
    if len(audio)!=round((end-start)*sr):
        raise ValueError('Source audio is too short')
    sf.write(target,audio,sr,subtype='PCM_16')


def stats(notes,start,end):
    selected=[n for n in notes if n.start<end and n.end>start]
    return dict(events=len(selected),under_100ms=sum(n.end-n.start<.1 for n in selected),
        under_10ms=sum(n.end-n.start<.01 for n in selected),
        voiced_seconds=sum(min(n.end,end)-max(n.start,start) for n in selected))


def run(root,checkpoint,output):
    gate=json.loads(checkpoint.read_text())
    implementation=Path(__file__).resolve().parents[1]/'app/evaluation/onset_notes.py'
    if not gate['passed'] or gate['candidate_sha256']!=sha(implementation):
        raise ValueError('This exact candidate must pass the independent checkpoint first')
    output.mkdir(parents=True,exist_ok=False)
    began=time.monotonic()
    report=dict(status='engineering_comparison_not_human_accepted',candidate_sha256=sha(implementation),
        checkpoint_sha256=sha(checkpoint),cases=[])
    write(output/'report.json',report)
    packet=dict(groups=[])
    configurations=[
        ('new-song','db79e1145ea046088b8aa5ef421d0e3f',8,16,None,'1 · 先前零落的片段'),
        ('saved-G','3ba648f12cb74dd59a45c1b2d4bc83ab',28,36,'db8c657e-62a5-4fad-a33e-cde25a9e1c0d','2 · 先前自然連貫的片段'),
    ]
    for name,id,first_bar,last_bar,revision,title in configurations:
        job=read_payload(root/'jobs/jobs.sqlite3','jobs',id)
        score=SongScore.model_validate(job['score'])
        directory=root/'jobs'/id
        contour=MelodyContour.model_validate_json((directory/'melody-contour.json').read_bytes())
        stem=directory/'vocal-stem.wav'
        if contour.source_start!=0 or contour.source_artifact_sha256!=sha(stem):
            raise ValueError('Contour and vocal audio do not share an origin/identity')
        if abs(score.song.duration_seconds-contour.source_end)>.05:
            raise ValueError('Score and contour durations differ')
        baseline=decode_bounded(contour)
        if revision:
            saved=SongScore.model_validate(read_payload(root/'revisions/guitarscribe.sqlite3','revisions',revision))
            if [(n.start,n.end,n.midi) for n in saved.melody]!=[(n.start,n.end,n.midi) for n in baseline]:
                raise ValueError('Saved G differs from baseline; do not silently substitute')
            score=saved
            baseline=saved.melody
        start=next(b.time for b in score.beats if b.measure==first_bar and b.beat==1)
        end=next(b.time for b in score.beats if b.measure==last_bar and b.beat==1)
        samples,sr=sf.read(stem)
        # librosa's 22.05kHz resampling rounds duration upward for an odd
        # 44.1kHz frame count. Account for that one final sample explicitly;
        # never hide a real source/contour length mismatch.
        padding=round((contour.source_end-contour.source_start)*sr)-len(samples)
        if padding>1:
            raise ValueError('Audio/contour duration mismatch exceeds one sample')
        if padding==1:
            samples=np.pad(samples,((0,1),(0,0)) if samples.ndim==2 else (0,1))
        candidate=decode_onset_aware(contour,samples,sr)
        assert all(n.start>=0 and n.end>n.start and n.end<=contour.source_end+1e-9 for n in candidate)
        assert all(a.end<=b.start+1e-9 for a,b in zip(candidate,candidate[1:]))
        changed=score.model_copy(deep=True)
        changed.melody=candidate
        manifest=compile_playback_manifest(changed)
        events=[e for e in manifest.events if e.track=='melody']
        assert [(e.start,e.end,e.pitches[0]) for e in events]==[(n.start,n.end,n.midi) for n in candidate]
        for label,notes in [('baseline',baseline),('candidate',candidate)]:
            write(output/f'{name}-{label}.json',[n.model_dump(mode='json') for n in notes])
        clip_audio(directory/'analysis-source.wav',output/f'{name}-source.wav',start,end)
        clip_audio(stem,output/f'{name}-vocal.wav',start,end)
        write(output/f'{name}-render.json',dict(start=start,end=end,
            baseline=[n.model_dump(mode='json') for n in baseline if n.start<end and n.end>start],
            candidate=[n.model_dump(mode='json') for n in candidate if n.start<end and n.end>start]))
        current=stats(baseline,start,end); revised=stats(candidate,start,end)
        loss=frame_loss(rounded_contour_frames(contour),connected_note_frames(candidate,contour),
                        contour.hop_seconds,start,end)
        report['cases'].append(dict(id=name,job_id=id,saved_revision=revision,
            bars=[first_bar,last_bar-1],analysis_seconds=[start,end],
            original_seconds=[start+score.song.source_start_seconds,end+score.song.source_start_seconds],
            stem_sha256=sha(stem),contour_sha256=sha(directory/'melody-contour.json'),
            final_zero_padding_samples=max(0,padding),
            source_excerpt_sha256=sha(output/f'{name}-source.wav'),
            baseline=current,candidate=revised,frame_difference_vs_contour=loss,
            compiler_preserves_candidate=True,
            caution='Changes and frame differences are not accuracy estimates; inward trimming deliberately removes smeared F0 tails.'))
        write(output/'report.json',report)
        packet['groups'].append(dict(id=name,title=title,
            question='候選版的音符長短與連貫性：較好／差不多／較差？有沒有新增奇怪碎音？',
            tracks=[dict(label='聽人聲參考',file=f'{name}-vocal.wav'),
                    dict(label='聽目前 G',file=f'{name}-baseline.wav'),
                    dict(label='聽候選版',file=f'{name}-candidate.wav')]))
        if name=='new-song':
            playable=with_default_voicings(score)
            chords=[dict(start=c.start,end=c.end,symbol=c.symbol,pitches=_selected_voicing_pitches(playable,c))
                    for c in playable.chords if c.start<end and c.end>start]
            write(output/'harmony-render.json',dict(start=start,end=end,chords=chords,
                manifest=compile_playback_manifest(score).model_dump(mode='json')))
            report['harmony_caution']=[c for c in chords if len(c['pitches'])<3]
    packet['groups'].append(dict(id='harmony',title='3 · 分開確認換和弦位置',
        question='長音和弦仍在奇怪位置切換嗎？仍會／明顯較貼合／不確定。只比較切換位置，不比較音色。',
        tracks=[dict(label='聽原曲',file='new-song-source.wav'),
                dict(label='原曲＋現有刷奏',file='harmony-strum.wav'),
                dict(label='原曲＋長音和弦',file='harmony-held.wav')]))
    write(output/'packet.json',packet)
    report['wall_seconds']=time.monotonic()-began
    write(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('checkpoint',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    run(args.root,args.checkpoint,args.output)
    print((args.output/'report.json').read_text())
