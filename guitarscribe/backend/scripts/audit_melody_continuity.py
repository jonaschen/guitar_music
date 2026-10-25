"""Read-only continuity audit of stored vocal contours; no accuracy claims."""
import argparse
import json
from pathlib import Path
import sqlite3
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.bounded_checkpoint import build_score
from app.evaluation.source_timed_audit import connected_note_frames, rounded_contour_frames, frame_loss
from app.exporters.midi import compile_playback_manifest
from app.models.melody_contour import MelodyContour
from app.models.score import SongScore


def audit(root: Path, job_id: str) -> dict:
    if len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id):
        raise ValueError('Invalid job ID')
    with sqlite3.connect(f'file:{root / "jobs.sqlite3"}?mode=ro', uri=True) as connection:
        row = connection.execute('select payload from jobs where id=?', (job_id,)).fetchone()
    if row is None:
        raise ValueError('Job not found')
    job = json.loads(row[0])
    original = SongScore.model_validate(job['score'])
    contour = MelodyContour.model_validate_json((root / job_id / 'melody-contour.json').read_bytes())
    candidate = build_score(original, contour)
    notes = candidate.melody
    durations = [n.end - n.start for n in notes]
    gaps = [b.start - a.end for a, b in zip(notes, notes[1:]) if b.start - a.end > .001]
    events = [e for e in compile_playback_manifest(candidate).events if e.track == 'melody']
    faithful = len(events) == len(notes) and all(
        e.start == n.start and abs(e.end - n.end) < 1e-9 and e.pitches == (n.midi,)
        for e, n in zip(events, notes))
    return {
        'job_id': job_id,
        'scope': 'Derived G from stored contour, not proof of the browser selection or musical accuracy. No job, revision, or audio writes.',
        'duration_seconds': original.song.duration_seconds,
        'original_notes': len(original.melody), 'derived_G_notes': len(notes),
        'under_100ms': sum(d < .1 for d in durations),
        'median_note_seconds': statistics.median(durations) if durations else None,
        'voiced_seconds': sum(durations), 'internal_gap_count': len(gaps),
        'internal_gap_seconds': sum(gaps),
        'manifest_preserves_notes': faithful,
        'source_frame_loss': frame_loss(rounded_contour_frames(contour),
            connected_note_frames(notes, contour), contour.hop_seconds, 0, contour.source_end),
        'five_second_windows': [{'start': t, 'note_onsets': sum(t <= n.start < t + 5 for n in notes),
            'voiced_seconds': sum(max(0, min(n.end, t + 5) - max(n.start, t)) for n in notes)}
            for t in range(0, int(original.song.duration_seconds + .999), 5)],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jobs_root', type=Path)
    parser.add_argument('job_id')
    args = parser.parse_args()
    print(json.dumps(audit(args.jobs_root, args.job_id), indent=2))
