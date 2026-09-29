"""Export a faithful frame-pitch audition without creating notation notes.

python -m app.evaluation.contour_playback FRAMES_JSON NEW_DIRECTORY --start 26 --end 46
Optional --reference-audio is the exact audio of the saved analysis context.
"""

import argparse
import hashlib
import json
from math import isfinite
from pathlib import Path

import soundfile as sf

from ..models.melody_contour import MelodyContour
from .pitch_contour import render_pitch_contour


def load_saved_contour(source: Path) -> MelodyContour:
    raw = source.read_bytes()
    data = json.loads(raw)
    offset, end = data["analysis_context"]
    hop = data["frame_hop_seconds"]
    for index, frame in enumerate(data["frames"]):
        if not isfinite(frame["time"]) or abs(frame["time"] - (offset + index * hop)) > 1e-6:
            raise ValueError("Frame timestamps disagree with recorded hop")
    return MelodyContour(
        source_artifact_sha256=hashlib.sha256(raw).hexdigest(),
        source_start=offset, source_end=end, hop_seconds=hop,
        frequencies_hz=tuple(f["hz"] for f in data["frames"]),
        voiced_probabilities=tuple(f["voiced_probability"] for f in data["frames"]),
    )


def render_contour_playback(contour: MelodyContour, start: float, end: float, output: Path) -> None:
    if not all(isfinite(t) for t in (start, end)) or not contour.source_start <= start < end <= contour.source_end:
        raise ValueError("Audition must lie within the saved source context")
    render_pitch_contour(list(contour.frequencies_hz), contour.hop_seconds,
                         contour.source_start, start, end, output,
                         interpolate_frames=False)


def export_audition(source: Path, output: Path, start: float, end: float,
                    reference_audio: Path | None = None) -> dict:
    contour = load_saved_contour(source)
    if not all(isfinite(t) for t in (start, end)) or not contour.source_start <= start < end <= contour.source_end:
        raise ValueError("Audition must lie within the saved source context")
    if end - start > 60 or any(hz is not None and hz >= 8000 for hz in contour.frequencies_hz):
        raise ValueError("Use a short audition with frequencies below renderer Nyquist")
    reference, rate, reference_digest = None, None, None
    if reference_audio is not None:
        info = sf.info(reference_audio)
        if abs(info.duration - (contour.source_end - contour.source_start)) > 1 / info.samplerate:
            raise ValueError("Reference must cover exactly the recorded analysis context")
        first = round((start - contour.source_start) * info.samplerate)
        last = round((end - contour.source_start) * info.samplerate)
        reference, rate = sf.read(reference_audio, start=first, stop=last)
        reference_digest = hashlib.sha256(reference_audio.read_bytes()).hexdigest()
    # Round-trip the exported representation before rendering; never use MelodyNote.
    serialized = contour.model_dump_json(indent=2)
    restored = MelodyContour.model_validate_json(serialized)
    report = {
        "status": "experimental_pending_extended_listening", "audition": [start, end],
        "source_artifact_sha256": contour.source_artifact_sha256,
        "reference_audio_sha256": reference_digest,
        "playback_kind": contour.playback_kind, "notation_notes_generated": False,
        "pitch_rounding": False, "beat_quantization": False,
        "gap_filling": False, "confidence_filtering": False,
        "files": ["contour.json", "melody-contour.wav"] + (["reference-vocals.wav"] if reference is not None else []),
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "contour.json").write_text(serialized)
    render_contour_playback(restored, start, end, output / "melody-contour.wav")
    if reference is not None:
        sf.write(output / "reference-vocals.wav", reference, rate, subtype="PCM_16")
    (output / "manifest.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--reference-audio", type=Path)
    args = parser.parse_args()
    print(json.dumps(export_audition(args.source, args.output, args.start, args.end, args.reference_audio), indent=2))
