"""Two frozen full-song original Chordino baselines; local research artifacts only."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_chord_bass_ablation import sha,write
from app.evaluation.annotations import QualityAnnotation,ChordRegionAnnotation
from app.evaluation.chord_errors import diagnose_chord_errors,diagnostic_label,_identity
from app.evaluation.quality_report import _mir_eval_chord_label
from app.models.score import SongScore,SongInfo,AnalysisSummary
from app.models.analysis import ChordEvent
import mir_eval


FIELDS=('id','title','artist','source','license','released','duration','audio','audio_offset','reference','downbeats')


def annotation(metadata,source,duration):
    """Never shift, repair gaps, drop unsupported labels or infer a meter."""
    if metadata['audio_offset']!=0:raise ValueError('Unexpected offset; no automatic alignment')
    if metadata['license']!='CC BY-NC 4.0':raise ValueError('Unexpected source license')
    if not math.isfinite(duration) or duration<=0:raise ValueError('Invalid decoded duration')
    regions=metadata['reference']
    if not regions or regions[0][0]!=0:raise ValueError('Reference must start at zero')
    cursor=0.
    for start,end,label in regions:
        if not all(math.isfinite(v) for v in (start,end)) or start!=cursor or end<=start:
            raise ValueError('Reference must be finite, contiguous and ordered')
        full=diagnostic_label(label);_identity(full);mir_eval.chord.encode(_mir_eval_chord_label(label))
        cursor=end
    end=min(duration,regions[-1][1])
    # Validate all rows before clipping: errors outside the domain remain visible.
    chords=[ChordRegionAnnotation(start=a,end=min(b,end),label=label) for a,b,label in regions if a<end]
    downbeats=metadata['downbeats']
    if any(not math.isfinite(v) or v<0 for v in downbeats) or any(b<=a for a,b in zip(downbeats,downbeats[1:])):
        raise ValueError('Invalid downbeat sequence')
    return QualityAnnotation(recording_id='MIREX2026_'+metadata['id'],evaluation_tier='smoke',
        annotation_status='draft',source_file=str(source),source_sha256=sha(source),
        rights_note=f"{metadata['title']} — {metadata['artist']}; {metadata['source']}; CC BY-NC 4.0 https://creativecommons.org/licenses/by-nc/4.0/ . Reference: Junyan Jiang, same license per official demo. Local noncommercial research only.",
        difficulty='hard',excerpt_start=0,excerpt_end=end,meter='',
        chords=chords,downbeats=[dict(time=t) for t in downbeats if t<end],
        listening_notes=['External published human reference; smoke tier permits full-song diagnostics, not quality acceptance. No predicted/official-system labels used. No beat or meter inference.'])


def run(root,plan_path,output):
    import soundfile as sf
    root,plan_path,output=root.resolve(),plan_path.resolve(),output.resolve()
    plan=json.loads(plan_path.read_text());plan_hash=sha(plan_path)
    began=time.monotonic();deadline=began+2700;output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONPATH='/home/jonas/.cache/guitarscribe-chordino-diagnostic/python')
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='2'
    def checked(entry):
        p=Path(entry['path']);p=p if p.is_absolute() else root/p
        if sha(p)!=entry['sha256']:raise ValueError('Frozen hash mismatch: '+str(p))
        return p
    def execute(command,log):
        left=deadline-time.monotonic()
        if left<=0:raise TimeoutError('45-minute limit reached')
        with log.open('x') as h:subprocess.run(command,env=env,stdout=h,stderr=subprocess.STDOUT,check=True,timeout=left,cwd=output)
    try:
        library=checked(plan['library']);env['VAMP_PATH']=str(library.parent)
        if (library.parent/'chord.dict').exists():raise ValueError('External dictionary')
        for item in plan['implementation']:checked(item)
        ffmpeg=checked(plan['ffmpeg']); prepared=[];requests=0
        # Acquire and validate both sources before either inference.
        for case in plan['cases']:
            original=checked(case['metadata']);raw=json.loads(original.read_text())
            metadata={key:raw[key] for key in FIELDS}  # explicitly exclude systems
            rid=metadata['id'];folder=output/rid;folder.mkdir()
            if rid!=case['recording_id'] or metadata['audio']!='audio/'+rid+'.mp3':raise ValueError('Unexpected recording')
            write(folder/'reference-metadata.json',metadata)
            source=folder/'source.mp3';requests+=1
            request=urllib.request.Request(case['audio_url'],headers={'User-Agent':'GuitarScribe local noncommercial reference evaluation'})
            with urllib.request.urlopen(request,timeout=60) as response,source.open('xb') as handle:
                if response.status!=200:raise ValueError('Audio HTTP failure')
                size=0
                while chunk:=response.read(1048576):
                    size+=len(chunk)
                    if size>100_000_000 or time.monotonic()>deadline:raise ValueError('Audio resource limit')
                    handle.write(chunk)
                download=dict(url=case['audio_url'],final_url=response.url,bytes=size,sha256=sha(source),status=response.status)
            write(folder/'download.json',download)
            wav=folder/'analysis-source.wav'
            execute([str(ffmpeg),'-nostdin','-n','-i',str(source),'-ar','44100','-ac','1','-sample_fmt','s16','-f','wav',str(wav)],folder/'decode.log')
            info=sf.info(wav)
            if info.samplerate!=44100 or info.channels!=1 or info.subtype!='PCM_16':raise ValueError('Unexpected normalized audio format')
            ann=annotation(metadata,wav,info.frames/info.samplerate)
            write(folder/'annotation.json',ann.model_dump(mode='json'))
            prepared.append(dict(recording_id=rid,audio=str(wav),audio_sha256=sha(wav),audio_frames=info.frames,sample_rate=info.samplerate,
                decoded_duration=info.duration,metadata_duration=metadata['duration'],evaluation_interval=[0,ann.excerpt_end],
                reference_end=metadata['reference'][-1][1],excluded_reference_tail_seconds=max(0,metadata['reference'][-1][1]-ann.excerpt_end),
                excluded_audio_tail_seconds=max(0,info.duration-ann.excerpt_end),annotation_sha256=sha(folder/'annotation.json'),download=download))
        if sha(plan_path)!=plan_hash:raise ValueError('Plan changed before inference')
        write(output/'before-inference-manifest.json',dict(plan_sha256=plan_hash,runner_sha256=sha(__file__),prepared=prepared,requests=requests))
        rows=[]
        for case in prepared:
            rid=case['recording_id'];folder=output/rid;target=folder/'events.json'
            config=dict(audio=case['audio'],audio_sha256=case['audio_sha256'],duration_seconds=case['decoded_duration'],
                        library=str(library),library_sha256=sha(library),output=str(target))
            conf=folder/'worker-config.json';write(conf,config)
            execute([sys.executable,str(root/'backend/scripts/run_chord_bass_ablation.py'),'worker',str(conf)],folder/'chordino.log')
            data=json.loads(target.read_text());events=[ChordEvent.model_validate(x) for x in data['chords']]
            if any(e.start<0 or e.end>case['decoded_duration'] for e in events):raise ValueError('Decoded event out of bounds')
            ann=QualityAnnotation.model_validate_json((folder/'annotation.json').read_text())
            metadata=json.loads((folder/'reference-metadata.json').read_text())
            score=SongScore(song=SongInfo(title=metadata['title'],source_type='local',source_url=metadata['source'],duration_seconds=case['decoded_duration']),
                analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature='',confidence=0),chords=events)
            write(folder/'score.json',score.model_dump(mode='json'))
            report=diagnose_chord_errors(score,ann)
            if abs(sum(x['seconds'] for x in report['intervals'])-ann.excerpt_end)>1e-7:raise ValueError('Interval duration not conserved')
            if abs(sum(report['summary']['category_seconds'].values())-ann.excerpt_end)>1e-7:raise ValueError('Category duration not conserved')
            write(folder/'diagnostic.json',report)
            rows.append(dict(**case,summary=report['summary'],boundaries=report['boundaries'],inference_seconds=data['inference_seconds']))
            print(json.dumps(dict(recording_id=rid,metrics=report['summary']['metrics'])),flush=True)
        if sha(plan_path)!=plan_hash:raise ValueError('Plan changed during run')
        for entry in plan['implementation']:checked(entry)
        for entry in plan['cases']:checked(entry['metadata'])
        checked(plan['library']);checked(plan['ffmpeg'])
        for row in prepared:
            if sha(row['audio'])!=row['audio_sha256']:raise ValueError('Audio changed during run')
            if sha(output/row['recording_id']/'annotation.json')!=row['annotation_sha256']:raise ValueError('Annotation changed during run')
        write(output/'result.json',dict(plan_sha256=plan_hash,sources=rows,wall_seconds=time.monotonic()-began,
             chordino_runs=2,audio_download_requests=requests,new_models=0,product_modified=False,
             outcome='full_song_baseline_only_no_quality_or_product_acceptance'))
    except Exception as e:
        write(output/'failure.json',dict(error=repr(e),wall_seconds=time.monotonic()-began));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('plan',type=Path);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root,a.plan,a.output)
