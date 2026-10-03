"""Re-decode a saved vocal contour into a separate candidate, never edit a job.

python -m app.evaluation.source_timed_audit JOBS_ROOT JOB_ID NEW_OUTPUT_DIRECTORY
Outputs a candidate full score and matched 50–63 second listening controls.
No inference, automatic ground-truth claim or production revision writes.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from ..analyzers.melody.pyin_adapter import frames_to_notes
from ..models.melody_contour import MelodyContour
from ..models.score import SongScore
from ..postprocess.melody import MelodyPostProcessor
from ..models.analysis import MelodyAnalysis
from ..models.analysis import MelodyNote
from ..analyzers.melody.basic_pitch_adapter import midi_to_note_name
from ..fretboard.mapper import SimpleFretboardMapper
from .diagnostic_audio import render_melody_diagnostic
from .pitch_contour import render_pitch_contour


def connected_note_frames(notes, contour: MelodyContour) -> list[float | None]:
    """Project monophonic notes onto source frames without filling rests.

    This only controls audition synthesis; it does not edit score boundaries.
    """
    ordered = sorted(notes, key=lambda note: note.start)
    if any(b.start < a.end - 1e-9 for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Connected audition requires monophonic notes")
    result = []
    index = 0
    for frame in range(len(contour.frequencies_hz)):
        time = contour.source_start + frame * contour.hop_seconds
        while index < len(ordered) and ordered[index].end <= time + 1e-9:
            index += 1
        note = ordered[index] if index < len(ordered) else None
        result.append(440 * 2 ** ((note.midi - 69) / 12)
                      if note is not None and note.start <= time + 1e-9 else None)
    return result


def rounded_contour_frames(contour: MelodyContour) -> list[float | None]:
    """Change only frame pitch to the nearest semitone; retain every rest."""
    return [None if hz is None else 440 * 2 ** (round(12 * math.log2(hz / 440)) / 12)
            for hz in contour.frequencies_hz]


def frame_faithful_notes(contour: MelodyContour) -> list[MelodyNote]:
    """Diagnostic notation baseline: preserve every rounded frame and rest.

    No minimum-duration or confidence gate. This can produce too many tiny
    notes for useful notation and must not be enabled as a production decoder.
    """
    result = []
    frames = rounded_contour_frames(contour)
    left = 0
    while left < len(frames):
        right = left + 1
        while right < len(frames) and frames[right] == frames[left]:
            right += 1
        if frames[left] is not None:
            pitch = round(69 + 12 * math.log2(frames[left] / 440))
            probabilities = [p if p is not None else 0 for p in contour.voiced_probabilities[left:right]]
            result.append(MelodyNote(
                id=f"frame-reference-{len(result)+1}",
                start=contour.source_start + left * contour.hop_seconds,
                end=min(contour.source_end, contour.source_start + right * contour.hop_seconds),
                midi=pitch, note=midi_to_note_name(pitch),
                confidence=sum(probabilities) / len(probabilities),
            ))
        left = right
    return result


def frame_loss(reference, candidate, hop: float, start: float, end: float) -> dict:
    """Count source-relative losses, never musical correctness."""
    if len(reference) != len(candidate):
        raise ValueError("Frame counts must match")
    counts = dict(voiced=0, dropped=0, changed_pitch=0, invented_voicing=0)
    for i, (source, decoded) in enumerate(zip(reference, candidate)):
        if not start <= i * hop < end:
            continue
        if source is not None:
            counts["voiced"] += 1
            if decoded is None:
                counts["dropped"] += 1
            elif abs(12 * math.log2(decoded / source)) > 1e-6:
                counts["changed_pitch"] += 1
        elif decoded is not None:
            counts["invented_voicing"] += 1
    return counts


def build_candidate(score: SongScore, contour: MelodyContour) -> SongScore:
    if abs(score.song.duration_seconds - contour.source_end) > .05 or contour.source_start != 0:
        raise ValueError("Score and contour must share the same complete analysis timeline")
    values = [None if hz is None else 69 + 12 * math.log2(hz / 440) for hz in contour.frequencies_hz]
    notes = frames_to_notes(values, contour.voiced_probabilities, hop_seconds=contour.hop_seconds)
    notes = MelodyPostProcessor().process_source_timed(notes)
    candidate = score.model_copy(deep=True)
    mapper = SimpleFretboardMapper()
    mapper.string_tuning = list(score.guitar.tuning)
    mapped = mapper.map_notes(MelodyAnalysis(notes=notes), capo=score.analysis.capo,
                              max_fret=score.guitar.max_fret, preference=score.guitar.tab_preference)
    candidate.melody = mapped.notes
    candidate.song.title += " · source-timed-v2 listening candidate"
    candidate.provenance.parameters["melody_note_processing"] = "source-timed-semitone-v2"
    candidate.provenance.parameters["listening_candidate"] = True
    candidate.analysis.warnings = [w for w in candidate.analysis.warnings if "cross-checked" not in w]
    candidate.analysis.warnings.append("Listening candidate from the saved vocal contour; source timing preserved, no beat snapping. Pitch accuracy and bar alignment are not verified.")
    return candidate


def audit(jobs_root: Path, job_id: str, output: Path, start: float = 50, end: float = 63):
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("Expected a saved job ID")
    with sqlite3.connect(f"file:{jobs_root / 'jobs.sqlite3'}?mode=ro", uri=True) as connection:
        jobs = [json.loads(row[0]) for row in connection.execute("select payload from jobs")]
    job = next(j for j in jobs if j["id"] == job_id)
    score = SongScore.model_validate(job["score"])
    if score.provenance.melody_engine != "pyin_vocal" or not job.get("separate_vocals"):
        raise ValueError("Requires a source-separated pYIN analysis")
    raw = (jobs_root / job_id / "melody-contour.json").read_bytes()
    contour = MelodyContour.model_validate_json(raw)
    if not 0 <= start < end <= score.song.duration_seconds:
        raise ValueError("Invalid listening range")
    candidate = build_candidate(score, contour)
    segmented_notes = frames_to_notes(
        [None if hz is None else 69 + 12 * math.log2(hz / 440) for hz in contour.frequencies_hz],
        contour.voiced_probabilities, hop_seconds=contour.hop_seconds)
    reference_notes = frame_faithful_notes(contour)
    reference_frames = rounded_contour_frames(contour)
    if connected_note_frames(reference_notes, contour) != reference_frames:
        # Hz round trips may have harmless floating-point error.
        loss = frame_loss(reference_frames, connected_note_frames(reference_notes, contour),
                          contour.hop_seconds, 0, contour.source_end)
        if any(loss[key] for key in ("dropped", "changed_pitch", "invented_voicing")):
            raise ValueError("Frame-reference round trip lost source information")
    output.mkdir(parents=True, exist_ok=False)
    (output / "frame-reference-notes.json").write_text(json.dumps({
        "status": "diagnostic_only_not_a_production_score", "source_sha256": hashlib.sha256(raw).hexdigest(),
        "notes": [note.model_dump(mode="json") for note in reference_notes],
    }, indent=2))
    (output / "candidate-score.json").write_text(candidate.model_dump_json(indent=2))
    for filename, notes in [("A-current-notes.wav", score.melody), ("B-source-timed-notes.wav", candidate.melody)]:
        clipped = [n.model_copy(update={"start": max(start, n.start) - start, "end": min(end, n.end) - start, "confidence": .8})
                   for n in notes if n.start < end and n.end > start]
        render_melody_diagnostic(clipped, end - start, output / filename)
    render_pitch_contour(list(contour.frequencies_hz), contour.hop_seconds, 0, start, end,
                         output / "C-source-contour.wav", interpolate_frames=False)
    for filename, frames in [
        ("D-candidate-connected.wav", connected_note_frames(candidate.melody, contour)),
        ("E-frame-semitones-connected.wav", rounded_contour_frames(contour)),
    ]:
        render_pitch_contour(frames, contour.hop_seconds, contour.source_start, start, end,
                             output / filename, interpolate_frames=False)
    report = {"status": "pending_human_listening", "source_job_id": job_id, "analysis_seconds": [start, end],
              "source_start_seconds": score.song.source_start_seconds, "contour_sha256": hashlib.sha256(raw).hexdigest(),
              "old_notes": len(score.melody), "candidate_notes": len(candidate.melody),
              "frame_reference_notes": len(reference_notes),
              "segmentation_loss_before_confidence_filter": frame_loss(reference_frames,
                  connected_note_frames(segmented_notes, contour), contour.hop_seconds, start, end),
              "candidate_loss_vs_rounded_frames": frame_loss(reference_frames,
                  connected_note_frames(candidate.melody, contour), contour.hop_seconds, start, end),
              "unchanged": ["beats", "chords", "rhythm", "source audio", "saved revisions"],
              "comparison": "A/B use matched per-note synthesis and gain. C/D/E share continuous-phase synthesis and gain: C raw F0, D candidate notes projected to source frames, E frame-rounded semitones without segmentation or filtering. B/D differ in envelope, phase and gain; frame projection may shift boundaries by up to one hop. None is ground truth."}
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs_root", type=Path)
    parser.add_argument("job_id")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.jobs_root, args.job_id, args.output), indent=2))
