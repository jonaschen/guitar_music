"""Bounded local-only SOME evaluation, not a production adapter."""
import hashlib
import json
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path.home() / '.cache/guitarscribe-some-evaluation'
OUT = ROOT / 'output/evaluation/final-some-2026-10-27'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name, data): (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def main():
    assert (OUT/'protocol.json').exists(), 'Freeze protocol first'
    assert not (OUT/'inference-report.json').exists(), 'Do not overwrite evaluated outputs'
    sys.path[:0] = [str(CACHE/'source'), str(CACHE/'deps')]
    import numpy as np
    import torch
    import librosa
    import yaml
    from inference.me_infer import MIDIExtractionInference
    from utils.slicer2 import Slicer
    from utils.infer_utils import build_midi_file
    torch.set_num_threads(2); torch.manual_seed(114514); np.random.seed(114514)
    # Older local CPU has AVX but no AVX2; use portable math kernels.
    torch.backends.mkldnn.enabled = False
    torch.backends.mha.set_fastpath_enabled(False)
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    model = CACHE/'model/0918_continuous256_clean_3spk_fixmel/model_steps_64000_simplified.ckpt'
    config_path = model.with_name('config.yaml')
    config = yaml.safe_load(config_path.read_text())
    engine = MIDIExtractionInference(config=config, model_path=model, device='cpu')
    inputs = json.loads((ROOT/'output/evaluation/rosvot-checkpoint-2026-10-25/listening-inputs.json').read_text())
    prior = ROOT/'frontend/public/listening/rosvot-checkpoint-2026-10-25'
    reports=[]
    def timeout(*_): raise TimeoutError('Per-clip 300 second limit')
    signal.signal(signal.SIGALRM,timeout)
    for meta in inputs:
        source=prior/meta['file']; assert sha(source)==meta['sha256']
        shutil.copyfile(source, OUT/meta['file'])
        started=time.monotonic();signal.alarm(300)
        waveform,_=librosa.load(source,sr=config['audio_sample_rate'],mono=True)
        chunks=Slicer(sr=config['audio_sample_rate'],max_sil_kept=1000).slice(waveform)
        outputs=engine.infer([c['waveform'] for c in chunks]);signal.alarm(0)
        midi=build_midi_file([c['offset'] for c in chunks],outputs,tempo=120)
        midi.save(OUT/(meta['id']+'.mid'))
        # Preserve raw rest durations and continuous model pitch separately.
        raw=[dict(offset=c['offset'],**{k:v.tolist() for k,v in result.items()}) for c,result in zip(chunks,outputs)]
        write(meta['id']+'-raw.json',raw)
        notes=[];t=0.;active={}
        for msg in midi:
            t+=msg.time
            if msg.type=='note_on' and msg.velocity>0:active[(msg.channel,msg.note)]=t
            elif msg.type=='note_off' or (msg.type=='note_on' and msg.velocity==0):
                start=active.pop((msg.channel,msg.note));notes.append(dict(start=start,end=t,midi=msg.note))
        assert not active and notes
        assert all(0<=n['start']<n['end']<=meta['duration']+.03 and 0<=n['midi']<=127 for n in notes)
        assert all(a['end']<=b['start']+1e-8 for a,b in zip(notes,notes[1:]))
        write(meta['id']+'-notes.json',notes)
        reports.append(dict(id=meta['id'],input_sha256=sha(source),duration=meta['duration'],notes=len(notes),seconds=time.monotonic()-started,midi_sha256=sha(OUT/(meta['id']+'.mid')),raw_offsets=[c['offset'] for c in chunks],last_note_end=notes[-1]['end']))
    write('inference-report.json',dict(model_sha256=sha(model),config_sha256=sha(config_path),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=CACHE/'source',text=True).strip(),torch=torch.__version__,librosa=librosa.__version__,device='cpu',threads=2,portable_cpu_kernels=True,model_license='CC BY-NC-SA 4.0 evaluation only',trained=False,uploaded=False,postprocessing='Official slicer, inference and MIDI export; no pitch or timing corrections',results=reports))
    write('listening-inputs.json',inputs)
    (OUT/'cpu-compatibility.patch').write_bytes(subprocess.check_output(['git','diff'],cwd=CACHE/'source'))
    print(json.dumps(reports,indent=2))

if __name__=='__main__': main()
