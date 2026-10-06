"""Build an isolated editable G score and multi-window listening packet.

python -m app.evaluation.bounded_checkpoint JOBS_ROOT JOB_ID NEW_OUTPUT
Never writes jobs or revision stores; not a deployment of the decoder.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from ..models.score import SongScore
from ..models.melody_contour import MelodyContour
from ..models.analysis import MelodyAnalysis
from ..fretboard.mapper import SimpleFretboardMapper
from ..exporters.midi import compile_playback_manifest, export_midi
from ..exporters.musicxml import export_musicxml
from .conservative_notes import decode_bounded
from .source_timed_audit import connected_note_frames, rounded_contour_frames, frame_loss
from .pitch_contour import render_pitch_contour


def build_score(score: SongScore, contour: MelodyContour) -> SongScore:
    if contour.source_start != 0 or abs(score.song.duration_seconds-contour.source_end) > .05:
        raise ValueError("Score and contour timelines differ")
    if score.melody_edits or any(note.edited for note in score.melody) or score.key_context.transpose_semitones:
        raise ValueError("Use an unedited, untransposed analysis; never replace manual work")
    candidate = score.model_copy(deep=True)
    notes = decode_bounded(contour)
    mapper = SimpleFretboardMapper()
    mapper.string_tuning = list(score.guitar.tuning)
    candidate.melody = mapper.map_notes(MelodyAnalysis(notes=notes), capo=score.analysis.capo,
        max_fret=score.guitar.max_fret, preference=score.guitar.tab_preference).notes
    candidate.song.title += " · G bounded candidate (experimental)"
    candidate.provenance.parameters.update(melody_note_processing="bounded-source-v1",
        listening_candidate=True, bounded_switch_cost=.35, bounded_max_error_semitones=.6)
    candidate.analysis.warnings.append("Independent Contour-to-note G candidate: preserves vocal contour timing with bounded semitone decoding. This is not verified whole-song transcription; instrumental passages and ensemble alignment remain unverified. Original analysis warnings are retained as history.")
    return candidate


def packet(jobs_root: Path, job_id: str, output: Path):
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("Invalid job ID")
    with sqlite3.connect(f"file:{jobs_root / 'jobs.sqlite3'}?mode=ro", uri=True) as connection:
        job = next((json.loads(row[0]) for row in connection.execute("select payload from jobs")
                    if json.loads(row[0])["id"] == job_id), None)
    if job is None:
        raise ValueError("Job not found")
    score = SongScore.model_validate(job["score"])
    if score.provenance.melody_engine != "pyin_vocal" or not job.get("separate_vocals"):
        raise ValueError("Requires separated vocal pYIN source")
    raw = (jobs_root / job_id / "melody-contour.json").read_bytes()
    contour = MelodyContour.model_validate_json(raw)
    candidate = build_score(score, contour)
    frames = connected_note_frames(candidate.melody, contour)
    reference = rounded_contour_frames(contour)
    windows = [("early",10,23), ("middle",100,113), ("late",220,233)]
    if any(end > contour.source_end for _, _, end in windows):
        raise ValueError("Source too short for this checkpoint's fixed windows")
    total_loss = frame_loss(reference, frames, contour.hop_seconds, 0, contour.source_end)
    if total_loss["dropped"] or total_loss["invented_voicing"]:
        raise ValueError("Candidate lost source voicing")
    manifest = compile_playback_manifest(candidate)
    events = [event for event in manifest.events if event.track == "melody"]
    if len(events) != len(candidate.melody) or any(
        event.start != note.start or abs(event.end-note.end) > 1e-9 or event.pitches != (note.midi,)
        for event,note in zip(events, candidate.melody)
    ):
        raise ValueError("Compiled melody timing changed")
    output.mkdir(parents=True, exist_ok=False)
    (output / "candidate-score.json").write_text(candidate.model_dump_json(indent=2))
    (output / "candidate.mid").write_bytes(export_midi(candidate))
    (output / "candidate.musicxml").write_text(export_musicxml(candidate))
    report = dict(status="pending_multi_window_listening", source_job_id=job_id,
        contour_sha256=hashlib.sha256(raw).hexdigest(), source_start_seconds=score.song.source_start_seconds,
        candidate_notes=len(candidate.melody), unmapped_notes=sum(n.string is None for n in candidate.melody),
        full_loss_vs_E=total_loss, compiled_melody_timing_verified=True,
        unchanged=["saved jobs", "saved revisions", "chords", "beats", "rhythm"], windows=[])
    for label, start, end in windows:
        for variant, frequencies in [("G",frames), ("C",list(contour.frequencies_hz))]:
            render_pitch_contour(frequencies, contour.hop_seconds, 0, start, end,
                output / f"{label}-{variant}.wav", interpolate_frames=False)
        report["windows"].append(dict(label=label, analysis_seconds=[start,end],
            source_seconds=[start+score.song.source_start_seconds,end+score.song.source_start_seconds],
            note_count=sum(n.start<end and n.end>start for n in candidate.melody),
            loss_vs_E=frame_loss(reference,frames,contour.hop_seconds,start,end)))
    (output / "report.json").write_text(json.dumps(report,indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs_root",type=Path)
    parser.add_argument("job_id")
    parser.add_argument("output",type=Path)
    args = parser.parse_args()
    print(json.dumps(packet(args.jobs_root,args.job_id,args.output),indent=2))
