"""Fixed source gain and audible quarter-note clicks, accented at bar starts."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf

source, output = map(Path, sys.argv[1:])
packet=json.loads((source/'packet.json').read_text())
manifest=json.loads((source/'manifest.json').read_text())
original,rate=sf.read(source/'source.wav');assert rate==22050
guitar=np.fromfile(source/'guitar.f32',dtype='<f4').astype(float)
assert abs(len(guitar)-len(original))<=1
frames=min(len(guitar),len(original));guitar=guitar[:frames];original=original[:frames]
click=np.zeros(frames);clicks=[]
for e in manifest['events']:
    if e['track']!='metronome' or not packet['start']<=e['start']<packet['end']: continue
    down=e['pitches']==[84];length=round(.065*rate);t=np.arange(length)/rate
    pulse=(.30 if down else .18)*np.sin(2*np.pi*(1500 if down else 1000)*t)*np.exp(-t/0.015)
    at=round((e['start']-packet['start'])*rate);n=min(length,frames-at)
    click[at:at+n]+=pulse[:n];clicks.append(dict(time=e['start'],downbeat=down))
fade=np.ones(frames);n=round(.005*rate);fade[:n]=np.linspace(0,1,n);fade[-n:]=np.linspace(1,0,n)
waves={'source':original*.45,'guitar':guitar,'mix':original*.45+guitar,'click':original*.45+click}
gain=min(1,.95/max(float(np.max(np.abs(v))) for v in waves.values()))
checks={'rate':rate,'frames':frames,'seconds':frames/rate,'gain':gain,'clicks':clicks,'files':{}}
assert [c['time'] for c in clicks if c['downbeat']]==packet['clip_strums']
for name,wave in waves.items():
    assert np.isfinite(wave).all()
    target=output/(name+'.wav');sf.write(target,wave*gain*fade,rate,subtype='PCM_16')
    decoded,_=sf.read(target);assert np.max(np.abs(decoded))<.951
    checks['files'][name]=dict(sha256=hashlib.sha256(target.read_bytes()).hexdigest(),rms=float(np.sqrt(np.mean(decoded**2))))
(output/'audio-checks.json').write_text(json.dumps(checks,indent=2))
