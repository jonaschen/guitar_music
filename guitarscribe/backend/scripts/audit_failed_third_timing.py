"""Audit source alignment and acoustic evidence without changing any timing."""
import hashlib
import json
import math
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import correlate, resample_poly

ROOT=Path(__file__).resolve().parents[2]
JOB=ROOT/'output/work/jobs/f303ec8a86834633b060920fa85430af'
OUT=ROOT/'output/evaluation/failed-third-timing-audit-2026-10-26'


def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def mono(path,rate):
    y,sr=sf.read(path,always_2d=True);y=y.mean(axis=1)
    divisor=math.gcd(sr,rate)
    return resample_poly(y,rate//divisor,sr//divisor)


def normalized_lag(reference,signal,rate,maximum=1):
    padding=round(maximum*rate);template=reference[padding:-padding];size=len(template)
    template=template-template.mean()
    numerator=correlate(signal,template,mode='valid',method='fft')
    sums=np.r_[0.,np.cumsum(signal)];squares=np.r_[0.,np.cumsum(signal**2)]
    local_sum=sums[size:]-sums[:-size]
    variance=squares[size:]-squares[:-size]-local_sum**2/size
    correlation=numerator/np.sqrt(np.maximum(variance,1e-15)*np.sum(template**2))
    best=int(np.argmax(correlation))
    return dict(lag_seconds=(best-padding)/rate,correlation=float(correlation[best]),zero_lag_correlation=float(correlation[padding]))


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    write('protocol.json',dict(job=JOB.name,window=[20,40],
        alignment='8kHz mono cross-correlation; original vs sum of existing stems, +/-1s; fixed 0–20/20–40/40–60 windows; positive lag means stems later',
        evidence='Existing accompaniment chroma STFT 22050Hz/2048FFT/512hop tuning=0. Binary selected-voicing pitch-class templates. Compare old/new in four one-beat bands around each saved boundary.',
        restriction='No candidate, offset correction, model inference, parameter sweep or musical ground truth.'))
    files=['analysis-source.wav','vocal-stem.wav','accompaniment-stem.wav']
    metadata={name:dict(sha256=hashlib.sha256((JOB/name).read_bytes()).hexdigest(),rate=sf.info(JOB/name).samplerate,
                        seconds=sf.info(JOB/name).duration) for name in files}
    audio=[mono(JOB/name,8000) for name in files]
    assert len(set(map(len,audio)))==1
    reconstructed=audio[1]+audio[2]
    alignment=[]
    for start in [0,20,40]:
        a,b=start*8000,(start+20)*8000
        alignment.append(dict(window=[start,start+20],**normalized_lag(audio[0][a:b],reconstructed[a:b],8000)))
    # Validate sign/scale with a deliberately delayed non-musical control.
    rng=np.random.default_rng(16);reference=rng.normal(size=160000)
    delayed=np.r_[np.zeros(4480),reference[:-4480]]
    control=normalized_lag(reference,delayed,8000)
    assert abs(control['lag_seconds']-.56)<1/8000
    score=json.loads((ROOT/'output/evaluation/confirmed-third-timing-2026-10-26/A-score.json').read_text())
    bscore=json.loads((ROOT/'output/evaluation/confirmed-third-timing-2026-10-26/B-score.json').read_text())
    manifests=[json.loads((ROOT/f'output/evaluation/confirmed-third-timing-2026-10-26/{label}-manifest.json').read_text()) for label in ['A','B']]
    y,sr=librosa.load(JOB/'accompaniment-stem.wav',sr=22050)
    chroma=librosa.feature.chroma_stft(y=y,sr=sr,n_fft=2048,hop_length=512,norm=2,tuning=0)
    times=librosa.frames_to_time(np.arange(chroma.shape[1]),sr=sr,hop_length=512)
    def template(chord):
        v=next(v for v in chord['available_voicings'] if v['id']==chord['voicing_id'])
        pitches={(t+f)%12 for t,f in zip(score['guitar']['tuning'],v['frets']) if f is not None}
        result=np.zeros(12);result[list(pitches)]=1
        return result/np.linalg.norm(result)
    rows=[]
    beats=score['beats']
    for i,(old,new) in enumerate(zip(score['chords'],score['chords'][1:]),1):
        t=new['start'];nearest=min(range(len(beats)-1),key=lambda j:abs(beats[j]['time']-t))
        period=beats[nearest+1]['time']-beats[nearest]['time']
        contrast=(template(new)-template(old))@chroma
        bands=[]
        for k in [-2,-1,0,1]:
            start,end=t+k*period,t+(k+1)*period
            mask=(times>=20+start)&(times<20+end)
            bands.append(dict(relative_beats=[k,k+1],mean_new_minus_old=float(contrast[mask].mean()),frames=int(mask.sum())))
        first=[]
        for manifest in manifests:
            events=[e for e in manifest['events'] if e['track']=='guitar' and e['source_id']==new['id']]
            first.append(min(e['start'] for e in events) if events else None)
        rows.append(dict(old=old['symbol'],new=new['symbol'],detected=t,B_boundary=bscore['chords'][i]['start'],
                         A_first_attack=first[0],B_first_attack=first[1],local_beat=period,acoustic_bands=bands))
    report=dict(metadata=metadata,alignment=alignment,lag_control=control,transitions=rows,
                limitations=['Sum-of-stems alignment does not prove either stem is artifact-free.',
                             'Chroma-template agreement is not harmonic truth; shared notes and harmonics can bias it.',
                             'One beat late remains a subjective observation, not a fitted shift.'])
    write('report.json',report)
    print('alignment',alignment)
    for row in rows:print(round(row['detected'],3),row['old'],'->',row['new'],'B attack',row['B_first_attack'],
                         'contrast', [round(x['mean_new_minus_old'],3) for x in row['acoustic_bands']])


if __name__=='__main__':main()
