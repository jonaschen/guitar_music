"""Short source-specific experiments; no production inference or score writes.

python -m app.evaluation.source_candidates JOB_DIRECTORY NEW_OUTPUT vocal|instrument
Instrument candidates are spectral hypotheses, not isolated violin stems.
"""
import argparse
import json
import math
from pathlib import Path
import time

import numpy as np

from .pitch_contour import render_pitch_contour
from .stem_source_review import digest
from ..models.melody_contour import MelodyContour

RATE = 22050
HOP = 512


def select_path(candidates, alternate=None):
    """Decode variable-size spectral peak sets; empty frames remain silent.

    Harmonic score plus a capped pitch-jump cost; second path discounts peaks
    near the first. Neither cost nor score is calibrated confidence.
    """
    result = [None]*len(candidates)
    left = 0
    while left < len(candidates):
        if not candidates[left]:
            left += 1
            continue
        right = left+1
        while right < len(candidates) and candidates[right]:
            right += 1
        previous_pitches = None
        back = []
        cost = None
        for index in range(left,right):
            pitches = np.array([69+12*math.log2(hz/440) for hz,_ in candidates[index]])
            weights = np.array([weight for _,weight in candidates[index]])
            emission = -np.log(np.maximum(weights,1e-12)/max(float(weights.max()),1e-12))
            if alternate is not None and alternate[index] is not None:
                anchor = 69+12*math.log2(alternate[index]/440)
                emission += np.where(np.abs(pitches-anchor)<.75,1.5,0)
            if cost is None:
                cost = emission
                back.append(np.zeros(len(pitches),dtype=int))
            else:
                transitions = cost[:,None]+.12*np.minimum(np.abs(previous_pitches[:,None]-pitches),12)
                parents = np.argmin(transitions,axis=0)
                cost = emission+transitions[parents,np.arange(len(pitches))]
                back.append(parents)
            previous_pitches = pitches
        selected = int(np.argmin(cost))
        for index in range(right-1,left-1,-1):
            result[index] = candidates[index][selected][0]
            selected = int(back[index-left][selected])
        left = right
    return result


def spectral_candidates(samples):
    import librosa
    spectrum = np.abs(librosa.stft(samples,n_fft=4096,hop_length=HOP))
    frequencies,magnitudes = librosa.piptrack(S=spectrum,sr=RATE,n_fft=4096,
        hop_length=HOP,fmin=196,fmax=1568,threshold=.1)
    bins = librosa.fft_frequencies(sr=RATE,n_fft=4096)
    candidates = []
    for frame in range(spectrum.shape[1]):
        if float(spectrum[:,frame].max()) < 1e-4:
            candidates.append([])
            continue
        peaks = np.flatnonzero(magnitudes[:,frame]>0)
        ranked = []
        for peak in peaks:
            hz = float(frequencies[peak,frame])
            fundamental = float(magnitudes[peak,frame])
            # Require an observed fundamental peak; never invent subharmonics.
            support = sum(float(np.interp(hz*h,bins,spectrum[:,frame],right=0))/h for h in range(2,6))
            ranked.append((hz,fundamental+.5*support))
        candidates.append(sorted(ranked,key=lambda item:item[1],reverse=True)[:6])
    return candidates


def experiment(directory: Path, output: Path, kind: str):
    import librosa
    if kind not in ("vocal","instrument"):
        raise ValueError("Unknown experiment")
    saved = MelodyContour.model_validate_json((directory / "melody-contour.json").read_bytes())
    if saved.source_start != 0:
        raise ValueError("Expected zero-origin saved contour")
    source = directory / ("vocal-stem.wav" if kind == "vocal" else "accompaniment-stem.wav")
    source_hash = digest(source)
    if kind == "vocal" and source_hash != saved.source_artifact_sha256:
        raise ValueError("Vocal source hash mismatch")
    start,end = (100,113) if kind == "vocal" else (220,233)
    if end+2 > saved.source_end:
        raise ValueError("Source too short")
    offset = math.floor((start-2)*RATE/HOP)*HOP/RATE
    samples,_ = librosa.load(source,sr=RATE,mono=True,offset=offset,duration=end+2-offset)
    if len(samples)/RATE < end-offset:
        raise ValueError("Source does not cover audition")
    output.mkdir(parents=True,exist_ok=False)
    report = dict(status="experimental_pending_listening",kind=kind,source_sha256=source_hash,
        analysis_seconds=[start,end],context_seconds=[offset,offset+len(samples)/RATE],
        sample_rate=RATE,hop_length=HOP,librosa_version=librosa.__version__,variants=[],
        warning="No score/key correction or G decoding. Candidate identity and accuracy require listening.")
    if kind == "vocal":
        variants = []
        for label,resolution in [("V-coarse-control",.5),("V-fine",.1)]:
            before = time.monotonic()
            hz,_,prob = librosa.pyin(samples,sr=RATE,fmin=98,fmax=1047,frame_length=2048,
                hop_length=HOP,resolution=resolution,n_thresholds=32)
            values = [float(x) if np.isfinite(x) else None for x in hz]
            variants.append((label,values))
            report["variants"].append(dict(name=label,resolution=resolution,thresholds=32,
                frame_length=2048,elapsed_seconds=time.monotonic()-before,
                voiced_frames=sum(x is not None for x in values)))
            (output / f"{label}.json").write_text(json.dumps(dict(frequencies_hz=values,
                voiced_probabilities=[float(p) if np.isfinite(p) else None for p in prob]),indent=2))
        pairs = [(a,b) for i,(a,b) in enumerate(zip(variants[0][1],variants[1][1]))
                 if start <= offset+i*HOP/RATE < end]
        differences = [abs(12*math.log2(a/b)) for a,b in pairs if a is not None and b is not None]
        report["comparison"] = dict(voicing_changed_frames=sum((a is None)!=(b is None) for a,b in pairs),
            shared_voiced_frames=len(differences),
            absolute_semitone_difference_p50_p90=np.percentile(differences,[50,90]).tolist() if differences else [],
            note="Same local audio context; differences are not accuracy measurements. Whole-song saved C can differ at context boundaries.")
    else:
        candidates = spectral_candidates(samples)
        first = select_path(candidates)
        second = select_path(candidates,first)
        variants = [("I-primary",first),("I-alternative",second)]
        report["spectral_parameters"] = dict(n_fft=4096,fmin=196,fmax=1568,threshold=.1,
            candidates_per_frame=6,harmonic_support_weight=.5,harmonics=[2,3,4,5],jump_cost=.12,
            max_jump_cost_semitones=12,alternative_discount=1.5,alternative_radius_semitones=.75)
        report["variants"] = [dict(name=name,voiced_frames=sum(x is not None for x in values)) for name,values in variants]
        (output / "spectral-candidates.json").write_text(json.dumps(candidates))
        for name,values in variants:
            (output / f"{name}.json").write_text(json.dumps(dict(frequencies_hz=values)))
    for name,values in variants:
        render_pitch_contour(values,HOP/RATE,offset,start,end,output / f"{name}.wav",interpolate_frames=False)
    (output / "report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("kind",choices=["vocal","instrument"])
    args = parser.parse_args()
    print(json.dumps(experiment(args.directory,args.output,args.kind),indent=2))
