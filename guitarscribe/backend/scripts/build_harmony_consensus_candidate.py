"""Build an evaluation-only first-strum candidate from acoustic consensus, never lyric taps."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.harmony_consensus import select_boundary_consensus
from app.evaluation.strum_timing import FirstStrumDelay, apply_first_strum_delays
from app.exporters.midi import PlaybackManifest, compile_playback_manifest, export_manifest_midi
from app.models.score import SongScore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new output directory; previous trials are immutable')
    score = SongScore.model_validate_json((args.packet/'score.json').read_text())
    base = PlaybackManifest.model_validate_json((args.packet/'manifest.json').read_text())
    config = json.loads((args.packet/'config.json').read_text())
    evidence = json.loads(args.audit.read_text())
    if evidence['revision'] != config['revision'] or compile_playback_manifest(score) != base:
        raise ValueError('Evidence, score and performance must refer to the same source')
    decisions = select_boundary_consensus(evidence)
    adjustments, excluded = [], []
    for row in decisions['rows']:
        if not row['accepted']:
            continue
        old, new = row['saved_time'], row['target_time']
        firsts = [event for event in base.events if event.track == 'guitar' and event.start == old]
        if firsts and any(event.track == 'guitar' and event.source_id == firsts[0].source_id and event.start < old for event in base.events):
            firsts = []
        if new <= old or len(firsts) != 1:
            excluded.append({**row, 'performance_reason': 'Only unambiguous delayed first strokes supported by this trial'})
            continue
        change = FirstStrumDelay(source_id=firsts[0].source_id, expected_start=old, delay_seconds=new-old)
        try:
            apply_first_strum_delays(base, [change], expected_revision=base.revision)
        except ValueError as error:
            excluded.append({**row, 'performance_reason': str(error)})
            continue
        adjustments.append(change)
    if not adjustments:
        raise ValueError('No safe first-strum candidate; do not render an unchanged trial')
    candidate = apply_first_strum_delays(base, adjustments, expected_revision=base.revision)
    assert [e for e in base.events if e.track != 'guitar'] == [e for e in candidate.events if e.track != 'guitar']
    assert len(base.events) == len(candidate.events)
    recipe = {'revision':config['revision'], 'base_manifest_revision':base.revision,
              'adjustments':[c.model_dump() for c in adjustments]}
    args.output.mkdir(parents=True, exist_ok=False)
    for name, data in [('consensus',decisions), ('recipe',recipe), ('report',{
        'source_config_id':config['config_id'], 'candidate_revision':candidate.revision,
        'changed_first_strokes':len(adjustments), 'excluded_performance_candidates':excluded,
        'human_marks_used_for_timing':False, 'saved_score_written':False,
        'scope':'Only selected first attacks and matching preceding release endpoints move. Later strums, harmony labels, melody and tempo stay fixed.',
        'limitations':'Acoustic crossings have analysis-window bias; agreement is not independent ground truth. Unresolved boundaries remain unchanged. This is a partial listening hypothesis, not a whole-song repair.'})]:
        (args.output/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    (args.output/'manifest.json').write_text(candidate.model_dump_json(indent=2))
    (args.output/'performance.mid').write_bytes(export_manifest_midi(candidate))
    print(json.dumps(recipe,indent=2))


if __name__ == '__main__':
    main()
