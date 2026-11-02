"""Cheap, deterministic diagnostics for every song; no model calls or score edits.

These describe data and scheduling, not musical correctness. In particular,
two pulse densities can reflect a real tempo change or a metrical ambiguity.
"""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median

from ..models.score import SongScore
from ..exporters.midi import compile_playback_manifest
from .playable_chords import with_default_voicings

POLICY = 'cross-song-health-v1'
NO_CHORD = {'n', 'nc', 'n.c.', 'no_chord'}


def pulse_density_summary(times: list[float], duration: float) -> dict:
    valid = len(times) >= 2 and all(isinstance(t, (int, float)) and not isinstance(t, bool)
                                 and math.isfinite(t) and t >= 0 for t in times)
    valid = valid and all(b > a for a, b in zip(times, times[1:]))
    if not valid:
        return dict(valid=False, observed_beats=len(times), windows=[], octave_density_changes=[])
    intervals = [(a, b - a) for a, b in zip(times, times[1:])]
    windows = []
    for start in range(0, math.ceil(duration), 10):
        values = [d for t, d in intervals if start <= t < start + 10]
        if len(values) >= 4:
            windows.append(dict(start=start, end=min(start + 10, duration),
                                intervals=len(values), median_seconds=median(values)))
    changes = []
    for a, b in zip(windows, windows[1:]):
        if a['end'] != b['start']:
            continue
        ratio = b['median_seconds'] / a['median_seconds']
        if 1.8 <= ratio <= 2.2 or 1 / 2.2 <= ratio <= 1 / 1.8:
            changes.append(dict(before=[a['start'], a['end']], after=[b['start'], b['end']],
                                interval_ratio=ratio))
    return dict(valid=True, observed_beats=len(times), median_seconds=median(d for _, d in intervals),
                windows=windows, octave_density_changes=changes)


def build_analysis_health(score: SongScore, timing_evidence: dict | None = None) -> dict:
    duration = score.song.duration_seconds
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('A finite positive duration is required')
    evidence = timing_evidence or {}
    times = evidence.get('beats') if score.analysis.timing_status == 'unmetered' else [b.time for b in score.beats]
    times = times if isinstance(times, list) else []
    lengths = [c.end - c.start for c in score.chords if math.isfinite(c.start + c.end) and c.end > c.start]
    incomplete = []
    for c in with_default_voicings(score).chords:
        if c.symbol.strip().lower() in NO_CHORD:
            continue
        shape = next((v for v in c.available_voicings if v.id == c.voicing_id),
                     c.available_voicings[0] if c.available_voicings else None)
        if shape is None or 'incomplete' in shape.tags:
            incomplete.append(c.id)
    try:
        manifest = compile_playback_manifest(score)
        events = [e for e in manifest.events if e.track == 'guitar']
        played = {e.source_id for e in events}
        playback = dict(revision=manifest.revision, guitar_events=len(events),
                        single_pitch_events=sum(len(e.pitches) == 1 for e in events),
                        unstruck_chord_ids=[c.id for c in score.chords if c.id not in played
                                           and c.symbol.strip().lower() not in NO_CHORD])
    except (ValueError, TypeError, IndexError) as error:
        playback = dict(error=str(error))
    return dict(policy=POLICY, score_sha256=hashlib.sha256(score.model_dump_json().encode()).hexdigest(),
                duration_seconds=duration, timing_status=score.analysis.timing_status,
                timing_source='rejected_observations' if score.analysis.timing_status == 'unmetered' else 'score_grid',
                rejection_reason=evidence.get('rejection_reason'),
                downbeat_gap_counts=dict(Counter(evidence.get('beats_per_downbeat_interval', []))),
                pulse_density=pulse_density_summary(times, duration),
                chords=dict(count=len(score.chords), under_half_second=sum(d < .5 for d in lengths),
                            under_one_second=sum(d < 1 for d in lengths), median_seconds=median(lengths) if lengths else None,
                            incomplete_voicing_ids=incomplete), playback=playback,
                engines=score.provenance.model_dump(mode='json'),
                musical_accuracy_evaluated=False, human_feedback='not_loaded_or_overwritten', automatic_edits=False,
                limitation='Engineering observations only. Counts and pulse-density changes are not accuracy scores or instructions to remove chords, repair beats or change tempo.')


def write_analysis_health(score: SongScore, directory: Path) -> dict:
    evidence_path = directory / 'timing-rejection.json'
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else None
    report = build_analysis_health(score, evidence)
    temporary = directory / 'analysis-health.next.json'
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    temporary.replace(directory / 'analysis-health.json')
    return report
