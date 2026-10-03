"""Experimental, bounded simplification of the frame-faithful note baseline.

Never deletes voiced frames or fills rests. Only removes isolated boundary
chatter: a one/two-frame excursion between matching, stable neighbours whose
raw pitches lie within 0.15 semitones of the rounding boundary. Short genuine
plateaus, leaps, phrase edges and uncertain cases stay available for editing.
Not wired into the production analysis pipeline.
"""
import math
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

from ..models.melody_contour import MelodyContour
from .source_timed_audit import frame_faithful_notes, connected_note_frames, rounded_contour_frames, frame_loss
from .pitch_contour import render_pitch_contour
from ..models.analysis import MelodyNote
from ..analyzers.melody.basic_pitch_adapter import midi_to_note_name


def decode_bounded(contour: MelodyContour):
    """Experimental integer path with a hard 0.6-semitone source bound.

    No minimum note length or confidence deletion. A 0.35 switching cost
    suppresses ambiguous rounding chatter without allowing a real semitone
    plateau to be absorbed. Costs are unweighted source pitch squared errors.
    Constants are experimental, not calibrated musical accuracy claims.
    """
    notes = []
    left = 0
    frequencies = contour.frequencies_hz
    while left < len(frequencies):
        if frequencies[left] is None:
            left += 1
            continue
        right = left + 1
        while right < len(frequencies) and frequencies[right] is not None:
            right += 1
        values = np.array([69 + 12 * math.log2(hz / 440) for hz in frequencies[left:right]])
        if np.any((values < 0) | (values > 127)):
            raise ValueError("Source pitch is outside MIDI range")
        pitches = np.arange(max(0, math.floor(values.min())), min(127, math.ceil(values.max())) + 1)
        back = np.zeros((len(values), len(pitches)), dtype=int)
        cost = np.where(np.abs(pitches - values[0]) <= .6 + 1e-9, (pitches - values[0])**2, np.inf)
        for frame in range(1, len(values)):
            best = int(np.argmin(cost))
            switch = cost[best] + .35 < cost
            back[frame] = np.where(switch, best, np.arange(len(pitches)))
            error = (pitches - values[frame])**2
            cost = np.where(switch, cost[best] + .35, cost) + error
            cost[np.abs(pitches - values[frame]) > .6 + 1e-9] = np.inf
        path = np.zeros(len(values), dtype=int)
        selected = int(np.argmin(cost))
        for frame in range(len(values)-1, -1, -1):
            path[frame] = pitches[selected]
            selected = back[frame, selected]
        begin = 0
        while begin < len(path):
            stop = begin + 1
            while stop < len(path) and path[stop] == path[begin]:
                stop += 1
            pitch = int(path[begin])
            probabilities = contour.voiced_probabilities[left+begin:left+stop]
            notes.append(MelodyNote(id=f"bounded-{len(notes)+1}", midi=pitch, note=midi_to_note_name(pitch),
                start=contour.source_start+(left+begin)*contour.hop_seconds,
                end=min(contour.source_end, contour.source_start+(left+stop)*contour.hop_seconds),
                confidence=sum(p or 0 for p in probabilities)/len(probabilities)))
            begin = stop
        left = right
    return notes


def decode_conservatively(contour: MelodyContour):
    notes = frame_faithful_notes(contour)
    result = []
    changes = []
    index = 0
    # Inspect original triples, not repeatedly simplified data: no cascading
    # merges that silently exceed the local evidence bound.
    while index < len(notes):
        if index + 2 < len(notes):
            left, middle, right = notes[index:index + 3]
            first = round((middle.start - contour.source_start) / contour.hop_seconds)
            last = round((middle.end - contour.source_start) / contour.hop_seconds)
            raw = [69 + 12 * math.log2(hz / 440)
                   for hz in contour.frequencies_hz[first:last] if hz is not None]
            boundary = (left.midi + middle.midi) / 2
            qualifies = (
                left.midi == right.midi and abs(left.midi - middle.midi) == 1
                and abs(left.end - middle.start) < 1e-9
                and abs(middle.end - right.start) < 1e-9
                and 1 <= last - first <= 2
                and left.end - left.start >= 3 * contour.hop_seconds - 1e-9
                and right.end - right.start >= 3 * contour.hop_seconds - 1e-9
                and len(raw) == last - first
                and all(abs(pitch - boundary) <= .15 for pitch in raw)
            )
            if qualifies:
                # Preserve evidence confidence over all original source frames.
                begin = round((left.start - contour.source_start) / contour.hop_seconds)
                stop = round((right.end - contour.source_start) / contour.hop_seconds)
                probabilities = contour.voiced_probabilities[begin:stop]
                confidence = sum(p or 0 for p in probabilities) / len(probabilities)
                result.append(left.model_copy(update={"end": right.end, "confidence": confidence}))
                changes.append({"start": middle.start, "end": middle.end,
                                "from_midi": middle.midi, "to_midi": left.midi,
                                "reason": "isolated_near_boundary_chatter"})
                index += 3
                continue
        result.append(notes[index].model_copy(deep=True))
        index += 1
    return result, changes


def audition(source: Path, output: Path, start: float = 50, end: float = 63):
    raw = source.read_bytes()
    contour = MelodyContour.model_validate_json(raw)
    if contour.source_start != 0 or not 0 <= start < end <= contour.source_end:
        raise ValueError("Requires a zero-origin contour covering the audition")
    notes, changes = decode_conservatively(contour)
    reference = rounded_contour_frames(contour)
    frames = connected_note_frames(notes, contour)
    bounded = decode_bounded(contour)
    bounded_frames = connected_note_frames(bounded, contour)
    bounded_loss = frame_loss(reference, bounded_frames, contour.hop_seconds, 0, contour.source_end)
    if bounded_loss["dropped"] or bounded_loss["invented_voicing"]:
        raise ValueError("Bounded candidate changed source voiced mask")
    maximum_error = max((abs(12 * math.log2(decoded / hz)) for hz, decoded in
                         zip(contour.frequencies_hz, bounded_frames) if hz is not None), default=0)
    if maximum_error > .6 + 1e-9:
        raise ValueError("Bounded candidate exceeded source pitch error limit")
    total_loss = frame_loss(reference, frames, contour.hop_seconds, 0, contour.source_end)
    if total_loss["dropped"] or total_loss["invented_voicing"]:
        raise ValueError("Conservative candidate changed the source voiced mask")
    report = dict(status="experimental_pending_listening", source_sha256=hashlib.sha256(raw).hexdigest(),
                  analysis_seconds=[start, end], baseline_notes=len(frame_faithful_notes(contour)),
                  candidate_notes=len(notes), full_loss_vs_E=total_loss,
                  bounded_notes=len(bounded), bounded_full_loss_vs_E=bounded_loss,
                  bounded_max_source_error_semitones=maximum_error,
                  bounded_parameters={"switch_cost": .35, "max_error_semitones": .6,
                                      "min_duration": None, "confidence_filter": False},
                  bounded_excerpt_loss_vs_E=frame_loss(reference, bounded_frames, contour.hop_seconds, start, end),
                  excerpt_loss_vs_E=frame_loss(reference, frames, contour.hop_seconds, start, end),
                  changes=changes, warning="Source fidelity is not musical accuracy; no production changes.")
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, indent=2))
    (output / "candidate-notes.json").write_text(json.dumps([note.model_dump(mode="json") for note in notes], indent=2))
    (output / "bounded-notes.json").write_text(json.dumps([note.model_dump(mode="json") for note in bounded], indent=2))
    for name, frequencies in [("F-conservative-connected.wav", frames),
                              ("G-bounded-connected.wav", bounded_frames),
                              ("E-frame-semitones-connected.wav", reference),
                              ("C-source-contour.wav", list(contour.frequencies_hz))]:
        render_pitch_contour(frequencies, contour.hop_seconds, 0, start, end,
                             output / name, interpolate_frames=False)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start", type=float, default=50)
    parser.add_argument("--end", type=float, default=63)
    args = parser.parse_args()
    report = audition(args.source, args.output, args.start, args.end)
    print(json.dumps({key: value for key, value in report.items() if key != "changes"}, indent=2))
