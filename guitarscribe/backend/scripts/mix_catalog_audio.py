"""Mix a product-voice float render with its full source; shared gain per song."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf


def mix(source, guitar, output, duration):
    rate=22050;frames=round((duration+.35)*rate)
    source_float=output/'source-float.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-af',
        f'atrim=end={duration},asetpts=PTS-STARTPTS,volume=0.45,afade=t=in:d=0.005,afade=t=out:st={duration-.005}:d=0.005,apad=pad_dur=0.35',
        '-ar',str(rate),'-ac','1','-c:a','pcm_f32le',str(source_float)],check=True)
    original,sr=sf.read(source_float);assert sr==rate and abs(len(original)-frames)<=2
    original=np.pad(original[:frames],(0,max(0,frames-len(original))))
    voice=np.fromfile(guitar,dtype='<f4').astype(np.float64);assert len(voice)==frames
    waves={'source':original,'guitar':voice,'mix':original+voice}
    peak=max(float(np.max(np.abs(w))) for w in waves.values())
    gain=min(1.,.95/max(peak,1e-12));reports={}
    for name,data in waves.items():
        assert np.isfinite(data).all()
        path=output/(name+'.wav');sf.write(path,data*gain,rate,subtype='PCM_16')
        decoded,actual=sf.read(path);assert len(decoded)==frames and actual==rate
        assert np.max(np.abs(decoded-data*gain))<=1/32768+1e-12
        assert np.max(np.abs(decoded))<.951
        reports[name]=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          rms=float(np.sqrt(np.mean(decoded**2))),frames=frames,rate=rate)
    decoded={name:sf.read(output/(name+'.wav'))[0] for name in waves}
    assert np.max(np.abs(decoded['mix']-decoded['guitar']-decoded['source']))<=2/32768
    source_float.unlink()
    return dict(audio=reports,common_gain=gain,frames=frames,rate=rate,duration=frames/rate)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('guitar',type=Path)
    parser.add_argument('output',type=Path);parser.add_argument('duration',type=float);args=parser.parse_args()
    report=mix(args.source,args.guitar,args.output,args.duration)
    (args.output/'audio-checks.json').write_text(json.dumps(report,indent=2)+'\n')
