"""Issue #2: controlled four-stem source review, not violin isolation.

Keep MELODIA settings fixed. Compare locally separated no-vocals control
against other (without estimated drums/bass/vocals). No job/revision writes.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf

from .melodia_benchmark import PARAMETERS,RATE,HOP,validate_pitch
from .pitch_contour import render_pitch_contour
from .stem_source_review import digest


def source_variants(stems):
    required={"vocals","drums","bass","other"}
    if set(stems)!=required:
        raise ValueError("Requires exactly four named source estimates")
    shapes={x.shape for x in stems.values()}
    if len(shapes)!=1 or any(x.ndim!=2 or not np.all(np.isfinite(x)) for x in stems.values()):
        raise ValueError("Invalid stem shapes or samples")
    return {"N-local-accompaniment":stems["drums"]+stems["bass"]+stems["other"],
            "O-other":stems["other"].copy()}


def benchmark(source: Path,output: Path):
    import torch
    import librosa
    import essentia.standard as es
    from demucs.hf import load_safetensors_model
    from demucs.apply import apply_model, BagOfModels
    from huggingface_hub import hf_hub_download
    import yaml

    if sf.info(source).duration<235:
        raise ValueError("Source does not cover context")
    output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(2)
    torch.manual_seed(0)
    samples,_=librosa.load(source,sr=RATE,mono=False,offset=218,duration=17)
    if samples.shape!=(2,17*RATE) or not np.all(np.isfinite(samples)):
        raise ValueError("Expected finite stereo 17-second context")
    # Pin the actual snapshot: current Demucs loads from HF, not torch.hub.
    repository="adefossez/HTDemucs"
    revision="cbc8a9b1a87023b7fd74e7b3412e6321c0eab003"
    config=Path(hf_hub_download(repository,"htdemucs.yaml",revision=revision))
    bag=yaml.safe_load(config.read_text())
    weights=[Path(hf_hub_download(repository,f"{sig}.safetensors",revision=revision)) for sig in bag["models"]]
    model=BagOfModels([load_safetensors_model(p) for p in weights],bag.get("weights"),bag.get("segment")).cpu().eval()
    if model.samplerate!=RATE or model.audio_channels!=2:
        raise ValueError("Unexpected model audio format")
    audio=torch.from_numpy(samples)
    reference=audio.mean(0)
    mean,std=reference.mean(),reference.std()
    if std<1e-8:
        raise ValueError("Silent source")
    before=time.monotonic()
    with torch.inference_mode():
        estimates=apply_model(model,((audio-mean)/std)[None],device="cpu",shifts=0,
            split=True,overlap=.25,num_workers=0,progress=False)[0]*std+mean
    elapsed=time.monotonic()-before
    stems={name:value.cpu().numpy().T for name,value in zip(model.sources,estimates)}
    if any(value.shape!=(17*RATE,2) for value in stems.values()):
        raise ValueError("Separation changed source duration or channels")
    variants=source_variants(stems)
    for name,samples in stems.items():
        sf.write(output/f"context-{name}.wav",samples,RATE,subtype="FLOAT")
    peak=max(float(np.max(np.abs(x))) for x in variants.values())
    gain=min(1,.98/peak) if peak else 1
    report=dict(status="pending_source_and_pitch_listening",issue=2,source_sha256=digest(source),
        context_seconds=[218,235],analysis_seconds=[220,233],model="htdemucs",
        demucs_version=importlib.metadata.version("demucs"),torch_version=torch.__version__,
        essentia_version=importlib.metadata.version("essentia"),separation_seconds=elapsed,
        shifts=0,overlap=.25,seed=0,source_audition_shared_gain=gain,melodia_parameters=PARAMETERS,
        model_repository=repository,model_revision=revision,
        weights={p.name:digest(p) for p in [config,*weights]},variants=[],
        caveat="other is a residual instrument group, not isolated violin. Local separation differs from whole-song M1; N controls for this. No automatic source routing or score changes.")
    for name,samples in variants.items():
        sf.write(output/f"{name}-source.wav",samples[2*RATE:15*RATE]*gain,RATE,subtype="PCM_16")
        mono=samples.mean(axis=1).astype(np.float32)
        hz,confidence=es.PredominantPitchMelodia(**PARAMETERS)(es.EqualLoudness(sampleRate=RATE)(mono))
        frames=validate_pitch(hz,confidence)
        (output/f"{name}.json").write_text(json.dumps(dict(frequencies_hz=frames,
            raw_confidence=[float(p) for p in confidence],context_seconds=[218,235],hop_seconds=HOP/RATE)))
        render_pitch_contour(frames,HOP/RATE,218,220,233,output/f"{name}.wav",interpolate_frames=False)
        report["variants"].append(dict(name=name,rms=float(np.sqrt(np.mean(samples.astype(float)**2))),
            voiced_frames=sum(f is not None for i,f in enumerate(frames) if 220<=218+i*HOP/RATE<233)))
    (output/"report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    print(json.dumps(benchmark(args.source,args.output),indent=2))
