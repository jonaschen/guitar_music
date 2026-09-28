"""Render a discrete-note audition from a saved short F0 diagnostic.

Run: python -m app.evaluation.contour_review frames-and-notes.json NEW_DIRECTORY
This does not run inference, modify a saved job, or use score/key priors.
"""

import argparse
import hashlib
import json
from math import isfinite, log2
from pathlib import Path

from .contour_notes import decode_contour_notes
from .sonification import render_note_sonification


def render_review(source: Path, output: Path) -> dict:
    raw = source.read_bytes()
    data = json.loads(raw)
    frames = data["frames"]
    hop = float(data["frame_hop_seconds"])
    offset, context_end = map(float, data["analysis_context"])
    start, end = map(float, data["audition"])
    if not all(isfinite(x) for x in (hop, offset, context_end, start, end)) or not (
        hop > 0 and 0 <= offset <= start < end <= context_end
    ):
        raise ValueError("Invalid time window")
    # Quadratic segment search is deliberately limited to short diagnostics.
    if context_end - offset > 60 or len(frames) > 3000:
        raise ValueError("Use a short contour diagnostic (at most 60s / 3000 frames)")
    values = []
    probabilities = []
    for index, frame in enumerate(frames):
        time = float(frame["time"])
        if not isfinite(time) or abs(time - (offset + index * hop)) > 1e-6:
            raise ValueError("Frames must be uniformly spaced at the recorded hop")
        hz = frame["hz"]
        if hz is not None and (not isfinite(hz) or hz <= 0):
            raise ValueError("Frequency must be positive and finite, or null")
        values.append(None if hz is None else 69 + 12 * log2(hz / 440))
        probabilities.append(frame["voiced_probability"])
    notes = decode_contour_notes(values, probabilities, hop_seconds=hop)
    for note in notes:
        note.start += offset
        note.end += offset
    report = {
        "status": "experimental_not_production_not_human_validated",
        "source": str(source), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "analysis_context": [offset, context_end], "audition": [start, end],
        "decoder": {"min_duration": 0.10, "transition_cost": 1.0},
        "manual_pitch_edits": False, "beat_quantization": False,
        "notes": [note.model_dump(mode="json") for note in notes],
    }
    output.mkdir(parents=True, exist_ok=False)
    render_note_sonification(notes, start, end, output / "decoded-notes.wav")
    (output / "decoded-notes.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = render_review(args.source, args.output)
    print(json.dumps({"audition": result["audition"], "note_count": len(result["notes"])}))
