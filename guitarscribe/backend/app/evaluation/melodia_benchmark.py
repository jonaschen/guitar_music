"""Optional, isolated Essentia MELODIA benchmark. Not production integration.

Install Essentia only in a disposable benchmark environment; no project
dependency is added. Check upstream licensing before any product adoption.
python -m app.evaluation.melodia_benchmark JOB_DIRECTORY NEW_OUTPUT
"""
import argparse
import importlib.metadata
import json
import math
from pathlib import Path
import time

import numpy as np

from .pitch_contour import render_pitch_contour
from .stem_source_review import digest

RATE = 44100
HOP = 128
PARAMETERS = dict(sampleRate=RATE,hopSize=HOP,frameSize=2048,minFrequency=80,
                  maxFrequency=1760,guessUnvoiced=False)


def validate_pitch(pitches, confidences):
    """Preserve algorithm unvoiced frames and raw confidence separately."""
    if len(pitches) != len(confidences) or not len(pitches):
        raise ValueError("Invalid pitch/confidence frame counts")
    result = []
    for hz,confidence in zip(pitches,confidences):
        if not math.isfinite(float(hz)) or not math.isfinite(float(confidence)):
            raise ValueError("Non-finite algorithm output")
        if hz <= 0 or confidence <= 0:
            result.append(None)
        elif hz >= 8000:
            raise ValueError("Pitch exceeds audition Nyquist")
        else:
            result.append(float(hz))
    return result


def benchmark(directory: Path, output: Path):
    import essentia
    import essentia.standard as es
    import librosa
    import soundfile as sf

    sources = [("M1-accompaniment",directory / "accompaniment-stem.wav"),
               ("M2-original",directory / "analysis-source.wav")]
    start,end = 220,233
    offset,stop = 218,235
    for _,source in sources:
        if sf.info(source).duration < stop:
            raise ValueError("Source does not cover the benchmark context")
    output.mkdir(parents=True,exist_ok=False)
    report = dict(status="pending_human_listening_not_production",issue=2,
        engine="Essentia PredominantPitchMelodia",essentia_version=essentia.__version__,
        package_version=importlib.metadata.version("essentia"),
        numpy_version=np.__version__,librosa_version=librosa.__version__,
        analysis_seconds=[start,end],context_seconds=[offset,stop],parameters=PARAMETERS,
        preprocessing="mono, resample 44100Hz, EqualLoudness; no normalization or key correction",
        license_review="Isolated local evaluation only; product adoption remains blocked on license review.",
        variants=[])
    for label,source in sources:
        samples,_ = librosa.load(source,sr=RATE,mono=True,offset=offset,duration=stop-offset)
        if len(samples) != (stop-offset)*RATE or not np.all(np.isfinite(samples)):
            raise ValueError("Invalid source context")
        samples = es.EqualLoudness(sampleRate=RATE)(samples.astype(np.float32))
        algorithm = es.PredominantPitchMelodia(**PARAMETERS)
        before = time.monotonic()
        pitch,confidence = algorithm(samples)
        elapsed = time.monotonic()-before
        frequencies = validate_pitch(pitch,confidence)
        if len(frequencies)*HOP/RATE < end-offset:
            raise ValueError("Algorithm output does not cover audition")
        metadata = dict(name=label,source_sha256=digest(source),elapsed_seconds=elapsed,
            frame_count=len(frequencies),
            voiced_audition_frames=sum(hz is not None for i,hz in enumerate(frequencies)
                                      if start <= offset+i*HOP/RATE < end))
        report["variants"].append(metadata)
        (output / f"{label}.json").write_text(json.dumps(dict(
            **metadata,context_seconds=[offset,stop],hop_seconds=HOP/RATE,
            frequencies_hz=frequencies,raw_pitch_hz=[float(p) for p in pitch],
            raw_pitch_confidence=[float(c) for c in confidence]),indent=2))
        render_pitch_contour(frequencies,HOP/RATE,offset,start,end,
                             output / f"{label}.wav",interpolate_frames=False)
    (output / "report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("output",type=Path)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.directory,args.output),indent=2))
