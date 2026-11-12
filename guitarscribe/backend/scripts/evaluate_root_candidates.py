"""Replay frozen evidence. Does not run inference or write source scores."""
import hashlib
import json
from pathlib import Path
import sys
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.root_candidates import METHOD, compact_trace, candidates_for_range, initial_segments, pitch_class


def evaluate(root, pooling='mean'):
    trace_dir = root / 'output/evaluation/chord-decoder-trace-2026-11-05'
    manifest = json.loads((trace_dir / 'run-result.json').read_text())
    plan = json.loads((root / 'docs/evaluation/chord-error-plan-2026-11-05.json').read_text())
    cases = {c['recording_id']: c for c in plan['cases']}
    results = []
    for recorded in manifest['sources']:
        rid = recorded['recording_id']; case = cases[rid]
        trace_path = trace_dir / (rid + '-trace.json')
        raw = trace_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == recorded['trace_sha256']
        score_raw = (root / case['estimate']['path']).read_bytes()
        assert hashlib.sha256(score_raw).hexdigest() == case['estimate']['sha256']
        evidence = compact_trace(json.loads(raw), pooling=pooling)
        score = json.loads(score_raw)
        if score['song']['duration_seconds'] <= 0:
            audio_path = root / case['audio']['path']
            assert hashlib.sha256(audio_path.read_bytes()).hexdigest() == case['audio']['sha256']
            score['song']['duration_seconds'] = sf.info(audio_path).duration
        segments = initial_segments(score)
        annotation_raw = (root / case['annotation']['path']).read_bytes()
        assert hashlib.sha256(annotation_raw).hexdigest() == case['annotation']['sha256']
        annotation = json.loads(annotation_raw)
        totals = dict(eligible=0., top1=0., top3=0., baseline=0., baseline_error=0., rescued=0., candidate_covered=0.)
        mixed = 0
        for segment in segments:
            candidates = candidates_for_range(evidence, segment['start'], segment['end'])
            pitches = [c['pitch_class'] for c in candidates['candidates']]
            references = set()
            for interval in annotation['chords']:
                a = max(segment['start'], interval['start'], case['interval'][0])
                b = min(segment['end'], interval['end'], case['interval'][1])
                ref = pitch_class(interval['label'])
                if b <= a or ref is None:
                    continue
                seconds = b - a; references.add(ref)
                totals['eligible'] += seconds
                totals['candidate_covered'] += seconds * bool(pitches)
                totals['top1'] += seconds * bool(pitches and ref == pitches[0])
                totals['top3'] += seconds * (ref in pitches)
                correct = segment['original_root'] == ref
                totals['baseline'] += seconds * correct
                totals['baseline_error'] += seconds * (not correct)
                totals['rescued'] += seconds * (not correct and ref in pitches)
            mixed += len(references) > 1
        results.append(dict(recording_id=rid, seconds=totals, top1=totals['top1']/totals['eligible'],
                            top3=totals['top3']/totals['eligible'], baseline=totals['baseline']/totals['eligible'],
                            error_rescue=totals['rescued']/totals['baseline_error'] if totals['baseline_error'] else None,
                            mixed_root_segments=mixed, segments=len(segments), trace_sha256=recorded['trace_sha256']))
    target = [r for r in results if r['recording_id'].startswith('SWD_')]
    passed = all(r['top3'] >= .8 and r['error_rescue'] >= .4 for r in target)
    return dict(method=f'root-{pooling}-profile-duration-v1', inference_runs=0, sources=results, development_gate_passed=passed,
                decision='proceed_to_collaborative_trial_implementation' if passed else 'do_not_promote_ranking',
                limitation='Previously used development data; not independent generalization or human usability evidence')


if __name__ == '__main__':
    print(json.dumps(evaluate(Path(sys.argv[1]), sys.argv[2] if len(sys.argv)>2 else 'mean'), ensure_ascii=False, indent=2))
