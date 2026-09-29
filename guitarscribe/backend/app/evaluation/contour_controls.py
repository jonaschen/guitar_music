"""Controlled auditions of saved F0 vs saved notes, with matched synthesis.

python -m app.evaluation.contour_controls FRAMES_JSON NOTES_JSON NEW_DIRECTORY
No inference, decoding, tuning, or production score changes are performed.
"""

import argparse
import hashlib
import json
from math import isfinite
from pathlib import Path

from .pitch_contour import render_pitch_contour


def render_controls(source: Path, decoded: Path, output: Path) -> dict:
    raw = source.read_bytes()
    note_raw = decoded.read_bytes()
    data, saved = json.loads(raw), json.loads(note_raw)
    digest = hashlib.sha256(raw).hexdigest()
    if saved["source_sha256"] != digest:
        raise ValueError("Notes were not decoded from this exact saved contour")
    start, end = map(float, data["audition"])
    offset, context_end = map(float, data["analysis_context"])
    hop = float(data["frame_hop_seconds"])
    if not all(isfinite(x) for x in (start, end, offset, context_end, hop)) or not (
        hop > 0 and 0 <= offset <= start < end <= context_end <= offset + 60
    ):
        raise ValueError("Invalid short diagnostic timing")
    if saved["audition"] != data["audition"] or saved["analysis_context"] != data["analysis_context"]:
        raise ValueError("Saved audition/context windows differ")
    frames = data["frames"]
    if not frames or len(frames) > 3000 or offset + len(frames) * hop < end - 1e-8:
        raise ValueError("Missing or excessive frame coverage")
    notes = sorted(saved["notes"], key=lambda n: n["start"])
    for index, note in enumerate(notes):
        if not all(isfinite(note[key]) for key in ("start", "end", "midi")) or not (
            note["start"] < note["end"] and 0 <= note["midi"] <= 127
        ):
            raise ValueError("Invalid note")
        if index and note["start"] < notes[index - 1]["end"] - 1e-8:
            raise ValueError("Overlapping notes cannot form a monophonic control")
        for boundary in (note["start"], note["end"]):
            position = (boundary - offset) / hop
            if abs(position - round(position)) > 1e-6:
                raise ValueError("Note boundaries must use the original frame grid")
    raw_hz, note_hz = [], []
    for index, frame in enumerate(frames):
        time = offset + index * hop
        if not isfinite(frame["time"]) or abs(frame["time"] - time) > 1e-6:
            raise ValueError("Nonuniform frame timing")
        hz = frame["hz"]
        if hz is not None and (not isfinite(hz) or not 0 < hz < 8000):
            raise ValueError("Invalid source frequency")
        match = next((n for n in notes if n["start"] - 1e-8 <= time < n["end"] - 1e-8), None)
        value = None if match is None else 440 * 2 ** ((match["midi"] - 69) / 12)
        # Do not hide dropped voiced frames or invented sustain under a mask.
        if time < end and time + hop > start and (hz is None) != (value is None):
            raise ValueError("Audition voiced masks differ; cannot isolate pitch conversion")
        raw_hz.append(hz)
        note_hz.append(value)
    variants = [
        ("A-continuous-f0.wav", raw_hz, True),
        ("B-frame-f0-connected.wav", raw_hz, False),
        ("C-note-pitches-connected.wav", note_hz, False),
    ]
    report = {
        "status": "diagnostic_only_pending_listening",
        "source_sha256": digest, "notes_sha256": hashlib.sha256(note_raw).hexdigest(),
        "audition": [start, end], "analysis_context": [offset, context_end],
        "matched_voiced_mask": True, "sample_rate": 16000, "gain": 0.3,
        "phase": "continuous", "fade": "5ms_at_voiced_run_edges_only",
        "comparisons": {
            "A_vs_B": "Same raw frame pitches; linear interpolation vs frame hold",
            "B_vs_C": "Same synthesis and silence; raw frame Hz vs saved discrete note Hz",
        },
        "files": [name for name, _, _ in variants],
    }
    # Validate frequencies before creating outputs, including data outside audition.
    if any(hz is not None and hz >= 8000 for hz in note_hz):
        raise ValueError("Note frequency exceeds renderer Nyquist")
    output.mkdir(parents=True, exist_ok=False)
    for name, values, interpolate in variants:
        render_pitch_contour(values, hop, offset, start, end, output / name,
                             interpolate_frames=interpolate)
    (output / "controls.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("decoded", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(render_controls(args.source, args.decoded, args.output), indent=2))
