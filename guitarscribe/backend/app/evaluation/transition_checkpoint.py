"""Build a read-only-source transition candidate and one listening comparison.

python -m app.evaluation.transition_checkpoint JOB_DIR SAVED_SCORE NEW_OUTPUT
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from ..models.score import SongScore
from ..models.melody_contour import MelodyContour
from ..exporters.midi import compile_playback_manifest
from .conservative_notes import decode_bounded
from .transition_notes import repair_transitions, detect_attacks
from .source_timed_audit import connected_note_frames, frame_loss
from .pitch_contour import render_pitch_contour


def packet(job_dir: Path, saved_score: Path, output: Path):
    score_raw = saved_score.read_bytes()
    score = SongScore.model_validate_json(score_raw)
    contour_raw = (job_dir/'melody-contour.json').read_bytes()
    contour = MelodyContour.model_validate_json(contour_raw)
    if (score.melody_edits or any(n.edited for n in score.melody)
            or score.key_context.transpose_semitones or contour.source_start != 0
            or abs(score.song.duration_seconds-contour.source_end) > .05):
        raise ValueError('Requires unedited source-aligned G; never replace manual work')
    source_job = score.provenance.parameters.get('candidate_source_job_id')
    if source_job != job_dir.name:
        raise ValueError('Saved G source job does not match audio directory')
    baseline = decode_bounded(contour)
    triples = lambda notes: [(n.start,n.end,n.midi) for n in notes]
    if (triples(baseline) != triples(score.melody)
            or any(abs(a.confidence-b.confidence)>1e-9 for a,b in zip(baseline,score.melody))):
        raise ValueError('Saved G does not match this source contour')
    stem_path = job_dir/'vocal-stem.wav'
    audio,sr = sf.read(stem_path)
    if abs(len(audio)/sr-contour.source_end) > .1:
        raise ValueError('Stem and contour duration differ')
    attacks = detect_attacks(audio,sr,contour.hop_seconds)
    notes,changes = repair_transitions(score.melody,contour,attacks)
    candidate = score.model_copy(deep=True)
    candidate.melody = notes
    # Confidence remains source voicing evidence, recalculated over new spans.
    for n in candidate.melody:
        a=round(n.start/contour.hop_seconds); b=round(n.end/contour.hop_seconds)
        p=contour.voiced_probabilities[a:b]
        if p: n.confidence=sum(v or 0 for v in p)/len(p)
    candidate.song.title += ' · H transition experiment'
    candidate.provenance.parameters.update(melody_note_processing='transition-bridge-v1',
        listening_candidate=True, transition_parent='bounded-source-v1')
    candidate.analysis.warnings.append('Experimental transition reassignment; may remove real legato ornaments. Not accepted or saved.')
    before = connected_note_frames(score.melody,contour)
    after = connected_note_frames(notes,contour)
    loss=frame_loss(before,after,contour.hop_seconds,0,contour.source_end)
    if loss['dropped'] or loss['invented_voicing']:
        raise ValueError('Candidate changed voicing')
    manifest = compile_playback_manifest(candidate)
    events = [e for e in manifest.events if e.track=='melody']
    if [(e.start,e.end,e.pitches[0]) for e in events] != triples(notes):
        raise ValueError('Manifest altered candidate timing')
    start=next(b.time for b in score.beats if b.measure==28 and b.beat==1)
    end=next(b.time for b in score.beats if b.measure==36 and b.beat==1)
    output.mkdir(parents=True,exist_ok=False)
    for label,frames in [('G',before),('H',after)]:
        render_pitch_contour(frames,contour.hop_seconds,0,start,end,output/f'{label}.wav',sample_rate=22050,interpolate_frames=False)
    # Same source interval for the musical reference, with only fixed gain normalization.
    source,source_sr=sf.read(job_dir/'analysis-source.wav')
    if abs(len(source)/source_sr-contour.source_end) > .1 or len(source)/source_sr < end:
        raise ValueError('Reference audio does not cover the source timeline')
    excerpt=source[round(start*source_sr):round(end*source_sr)]
    peak=float(np.max(np.abs(excerpt)))
    sf.write(output/'source.wav',excerpt*(.85/peak if peak else 1),source_sr,subtype='PCM_16')
    report=dict(status='experimental_pending_listening',hypothesis='short monotone transitions oversegmented',
        source_job_id=source_job,
        reference_sha256=hashlib.sha256((job_dir/'analysis-source.wav').read_bytes()).hexdigest(),
        saved_score_sha256=hashlib.sha256(score_raw).hexdigest(),
        contour_sha256=hashlib.sha256(contour_raw).hexdigest(),
        stem_sha256=hashlib.sha256(stem_path.read_bytes()).hexdigest(),
        baseline_notes=len(score.melody),candidate_notes=len(notes),
        detected_attack_count=len(attacks),changes=changes,full_loss=loss,
        analysis_seconds=[start,end],source_seconds=[start+score.song.source_start_seconds,end+score.song.source_start_seconds],
        excerpt_changes=[c for c in changes if c['start']<end and c['end']>start],
        parameters=dict(bridge_note_max_frames=2,bridge_total_max_frames=5,anchor_min_frames=3,bridge_confidence_below=.6),
        warning='No accuracy claim; genuine fast legato notes can be lost; G and stored jobs/revisions unchanged')
    (output/'candidate-score.json').write_text(candidate.model_dump_json(indent=2))
    (output/'report.json').write_text(json.dumps(report,indent=2))
    (output/'index.html').write_text(Path(__file__).with_name('transition_listening.html').read_text())
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_dir',type=Path);parser.add_argument('saved_score',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    report=packet(args.job_dir,args.saved_score,args.output)
    print(json.dumps({k:v for k,v in report.items() if k!='changes'},indent=2))
