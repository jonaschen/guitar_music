"""Issue #2: two single-factor checks against the accepted M1 baseline.

Never splice a candidate into an accepted section or write a working score.
"""
import argparse
import importlib.metadata
import json
import math
from pathlib import Path

import numpy as np

from .melodia_benchmark import PARAMETERS, RATE, HOP, validate_pitch
from .pitch_contour import render_pitch_contour
from .stem_source_review import digest


def compare_frames(baseline, candidate, start, end, offset=218, hop=HOP/RATE):
    if len(baseline) != len(candidate):
        raise ValueError("Frame counts differ")
    counts = dict(frames=0,baseline_voiced=0,candidate_voiced=0,added=0,dropped=0,changed_over_half_semitone=0)
    for i,(old,new) in enumerate(zip(baseline,candidate)):
        if not start <= offset+i*hop < end:
            continue
        counts["frames"] += 1
        counts["baseline_voiced"] += old is not None
        counts["candidate_voiced"] += new is not None
        counts["added"] += old is None and new is not None
        counts["dropped"] += old is not None and new is None
        counts["changed_over_half_semitone"] += old is not None and new is not None and abs(12*math.log2(new/old))>.5
    return counts


def followup(source: Path, baseline_file: Path, output: Path):
    import essentia.standard as es
    import librosa
    baseline = json.loads(baseline_file.read_text())
    if baseline["source_sha256"] != digest(source) or baseline["context_seconds"] != [218,235] or abs(baseline["hop_seconds"]-HOP/RATE)>1e-12:
        raise ValueError("Baseline source or timing mismatch")
    samples,_ = librosa.load(source,sr=RATE,mono=True,offset=218,duration=17)
    if len(samples) != 17*RATE or not np.all(np.isfinite(samples)):
        raise ValueError("Invalid context")
    samples = es.EqualLoudness(sampleRate=RATE)(samples.astype(np.float32))
    output.mkdir(parents=True,exist_ok=False)
    report = dict(status="pending_listening",issue=2,package_version=importlib.metadata.version("essentia"),
        baseline_sha256=digest(baseline_file),source_sha256=digest(source),context_seconds=[218,235],
        user_feedback="M1 about 55%, mostly correct after local 7s; subjective estimate, not reference annotations",
        baseline_parameters=PARAMETERS,variants=[],
        caveat="Added frames are not necessarily melody. Pitch changes may be legitimate or wrong. No candidate applied.")
    for name,change in [("control",{}),("R-voicing",{"voicingTolerance":.5}),
                        ("W-range",{"maxFrequency":3520})]:
        parameters = {**PARAMETERS,**change}
        hz,confidence = es.PredominantPitchMelodia(**parameters)(samples)
        frames = validate_pitch(hz,confidence)
        if name == "control" and frames != baseline["frequencies_hz"]:
            raise ValueError("Recomputed baseline differs; stop before interpreting parameter changes")
        report["variants"].append(dict(name=name,parameters=parameters,
            first_seven=compare_frames(baseline["frequencies_hz"],frames,220,227),
            accepted_tail=compare_frames(baseline["frequencies_hz"],frames,227,233)))
        (output / f"{name}.json").write_text(json.dumps(dict(frequencies_hz=frames,
            raw_confidence=[float(p) for p in confidence],hop_seconds=HOP/RATE,context_seconds=[218,235])))
        render_pitch_contour(frames,HOP/RATE,218,220,233,output / f"{name}.wav",interpolate_frames=False)
    (output / "report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("baseline",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    print(json.dumps(followup(args.source,args.baseline,args.output),indent=2))
