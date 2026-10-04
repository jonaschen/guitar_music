"""Review time-aligned saved source stems without inference or score changes.

python -m app.evaluation.stem_source_review JOB_DIRECTORY NEW_OUTPUT
Stem identity is a listening question, not an energy/classifier conclusion.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from ..models.melody_contour import MelodyContour


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            result.update(block)
    return result.hexdigest()


def review(directory: Path, output: Path, windows=(("middle",100,113),("late",220,233))):
    contour_path = directory / "melody-contour.json"
    contour = MelodyContour.model_validate_json(contour_path.read_bytes())
    sources = {"original":directory / "analysis-source.wav",
               "vocal":directory / "vocal-stem.wav",
               "accompaniment":directory / "accompaniment-stem.wav"}
    hashes = {name:digest(path) for name,path in sources.items()}
    if contour.source_artifact_kind != "audio" or hashes["vocal"] != contour.source_artifact_sha256:
        raise ValueError("Saved vocal stem does not match contour source hash")
    if contour.source_start != 0:
        raise ValueError("Expected zero-origin analysis timeline")
    labels = [label for label,_,_ in windows]
    if len(labels) != len(set(labels)) or any(not label.isascii() or not label.isalnum() for label in labels):
        raise ValueError("Window labels must be unique ASCII alphanumeric names")
    clips = []
    for label,start,end in windows:
        if not np.isfinite(start) or not np.isfinite(end) or not 0 <= start < end <= contour.source_end or end-start > 30:
            raise ValueError("Use valid source windows of at most 30 seconds")
        samples = {}
        for name,path in sources.items():
            with sf.SoundFile(path) as audio:
                if abs(len(audio)/audio.samplerate-contour.source_end) > .05:
                    raise ValueError("Source and contour durations differ")
                audio.seek(round(start*audio.samplerate))
                data = audio.read(round(end*audio.samplerate)-round(start*audio.samplerate), dtype="float32",always_2d=True)
                if not np.all(np.isfinite(data)):
                    raise ValueError("Source contains non-finite audio")
                samples[name] = (data,audio.samplerate)
        clips.append((label,start,end,samples))
    # Shared attenuation only if needed; no per-stem loudness normalization
    # that could make weak accompaniment leakage sound like a strong voice.
    peak = max((float(np.max(np.abs(data))) for _,_,_,samples in clips for data,_ in samples.values()), default=0)
    gain = min(1,.98/peak) if peak else 1
    output.mkdir(parents=True,exist_ok=False)
    report = dict(status="pending_source_listening", source_sha256=hashes,
                  contour_sha256=digest(contour_path), contour_source_verified=True,
                  shared_gain=gain, analysis_timeline=True, windows=[],
                  caveat="Energy and voiced probability do not identify the lead instrument or prove pitch correctness. No tuning correction or re-analysis applied.")
    for label,start,end,samples in clips:
        stats = {}
        for name,(data,rate) in samples.items():
            sf.write(output / f"{label}-{name}.wav",data*gain,rate,subtype="PCM_16")
            stats[name] = dict(rms=float(np.sqrt(np.mean(data.astype(float)**2))),
                              peak=float(np.max(np.abs(data))),sample_rate=rate,channels=data.shape[1])
        indices = [i for i,hz in enumerate(contour.frequencies_hz)
                   if start <= i*contour.hop_seconds < end and hz is not None]
        pitches = [69+12*np.log2(contour.frequencies_hz[i]/440) for i in indices]
        probabilities = [contour.voiced_probabilities[i] or 0 for i in indices]
        report["windows"].append(dict(label=label,analysis_seconds=[start,end],audio=stats,
            voiced_frames=len(indices), voiced_probability_median=float(np.median(probabilities)) if probabilities else None,
            midi_p10_p50_p90=np.percentile(pitches,[10,50,90]).tolist() if pitches else []))
    (output / "report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("output",type=Path)
    args = parser.parse_args()
    print(json.dumps(review(args.directory,args.output),indent=2))
