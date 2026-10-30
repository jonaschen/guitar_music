"""Use one shared gain for both A/B variants and the original excerpt."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf

source,output,number=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
original,rate=sf.read(source/'source.wav');assert rate==22050
voices={key:np.fromfile(source/(key+'.f32'),dtype='<f4').astype(float) for key in ('a','b')}
assert all(abs(len(v)-len(original))<=1 for v in voices.values())
frames=min(len(original),*(len(v) for v in voices.values()))
fade=np.ones(frames);n=round(.005*rate);fade[:n]=np.linspace(0,1,n);fade[-n:]=np.linspace(1,0,n)
waves={'source':original[:frames]*.45*fade}
for key,voice in voices.items():
    waves[key+'-guitar']=voice[:frames]*fade
    waves[key+'-mix']=waves['source']+waves[key+'-guitar']
peak=max(float(np.max(np.abs(v))) for v in waves.values());gain=min(1,.95/max(peak,1e-12))
report={'gain':gain,'rate':rate,'frames':frames,'audio':{}}
for key,wave in waves.items():
    assert np.isfinite(wave).all()
    path=output/f'{number}-{key}.wav';sf.write(path,wave*gain,rate,subtype='PCM_16')
    decoded,_=sf.read(path);assert np.max(np.abs(decoded))<.951
    report['audio'][key]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rms':float(np.sqrt(np.mean(decoded**2)))}
(output/f'{number}-checks.json').write_text(json.dumps(report,indent=2))
