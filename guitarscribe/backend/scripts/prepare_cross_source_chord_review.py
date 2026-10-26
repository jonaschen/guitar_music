"""Matched existing-window Chordino comparison; only the mix control is new."""
import hashlib
import json
from pathlib import Path
import time
import struct

import librosa
import numpy as np
import soundfile as sf
import vamp

ROOT=Path(__file__).resolve().parents[2]
PRIOR=ROOT/'output/evaluation/accompaniment-regression-2026-10-26'
OUT=ROOT/'output/evaluation/cross-source-chords-2026-10-26-verified'


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    cases=json.loads((PRIOR/'protocol.json').read_text())['cases']
    reports=json.loads((PRIOR/'report.json').read_text())
    write(OUT/'protocol.json',dict(cases=cases,method='Same fixed cropped inputs and plugin defaults; compare original mix to previously generated stem candidate',
                                  policy='No tuning or new separation; metrics are agreement, not correctness; no candidate applied'))
    results=[]
    library=Path(vamp.vampyhost.get_library_for('nnls-chroma:chordino'))
    library_hash=hashlib.sha256(library.read_bytes()).hexdigest()
    for (name,job,start,end),prior in zip(cases,reports,strict=True):
        began=time.monotonic()
        assert library_hash==prior['provenance']['chordino_library_sha256']
        # Match the prior crop's FLOAT encoding and hash exactly before inference.
        path=ROOT/'output/work/jobs'/job/'analysis-source.wav'
        with sf.SoundFile(path) as audio:
            sr=audio.samplerate;audio.seek(round(start*sr))
            samples=audio.read(round((end-start)*sr),always_2d=True)
        assert len(samples)==round((end-start)*sr)
        clip=OUT/f'{name}-source.wav';sf.write(clip,samples,sr,subtype='FLOAT')
        # FLOAT WAV contains a libsndfile PEAK creation timestamp. Restore only
        # that metadata when it yields an exact match to the saved input hash.
        data=bytearray(clip.read_bytes());target=prior['provenance']['chord_source_audio_sha256']
        peak=data.find(b'PEAK',0,128)
        if hashlib.sha256(data).hexdigest()!=target and peak>=0:
            previous_time=int((PRIOR/'report.json').stat().st_mtime)
            for timestamp in range(previous_time-120,previous_time+1):
                struct.pack_into('<I',data,peak+12,timestamp)
                if hashlib.sha256(data).hexdigest()==target:
                    clip.write_bytes(data);break
        assert hashlib.sha256(clip.read_bytes()).hexdigest()==prior['provenance']['chord_source_audio_sha256']
        y,sr=librosa.load(clip,sr=sr)
        raw=vamp.collect(y,sr,'nnls-chroma:chordino')['list']
        raw_events=[dict(start=float(e['timestamp']),end=float(raw[i+1]['timestamp']) if i+1<len(raw) else end-start,symbol=e['label']) for i,e in enumerate(raw)]
        write(OUT/f'{name}-raw-mix.json',raw_events)
        mixed=[dict(start=max(0,e['start']),end=min(end-start,e['end']),symbol=e['symbol']) for e in raw_events if e['start']<end-start and e['end']>e['start']]
        saved=json.loads((PRIOR/f'{name}-candidate.json').read_text())
        stem=[dict(start=e['start'],end=e['end'],symbol=e['symbol']) for e in saved['chords']]
        for events in [mixed,stem]:
            assert all(0<=e['start']<e['end']<=end-start for e in events)
            assert all(a['end']<=b['start']+1e-8 for a,b in zip(events,events[1:]))
        edges=sorted({0.,end-start,*[e[k] for events in [mixed,stem] for e in events for k in ['start','end']]})
        differing=[];same=0
        for a,b in zip(edges,edges[1:]):
            mid=(a+b)/2
            labels=[next((e['symbol'] for e in events if e['start']<=mid<e['end']),'N') for events in [mixed,stem]]
            if labels[0]==labels[1]:same+=b-a
            else:differing.append(dict(start=a,end=b,mix=labels[0],stem=labels[1]))
        result=dict(id=name,job=job,window=[start,end],duration=end-start,mix=mixed,stem=stem,
                    identical_label_seconds=same,differences=differing,source_sha256=hashlib.sha256(clip.read_bytes()).hexdigest(),
                    stem_candidate_sha256=hashlib.sha256((PRIOR/f'{name}-candidate.json').read_bytes()).hexdigest(),
                    library_sha256=library_hash,seconds=time.monotonic()-began)
        results.append(result)
        print(name,'mix events',len(mixed),'stem events',len(stem),'same label seconds',round(same,3),'of',end-start)
        for row in differing: print(' ',row)
    write(OUT/'report.json',results)


if __name__=='__main__':main()
