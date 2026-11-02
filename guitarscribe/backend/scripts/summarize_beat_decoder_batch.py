"""Compare fixed decoders across a frozen inventory, without ranking musical accuracy.

Usage: python summarize_beat_decoder_batch.py INVENTORY OUTPUT_DIR REPORT [REPORT ...]
REPORT files may be reused from earlier identical-policy experiments.
"""
import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.analysis_health import pulse_density_summary
from app.analyzers.beats.guarded_recovery import check_recovery


def unmatched(times, reference, tolerance=.070):
    """Symmetric calls report changed observations, not annotated beat accuracy."""
    count = 0
    for t in times:
        i = bisect_left(reference, t)
        if not any(0 <= j < len(reference) and abs(t-reference[j]) <= tolerance for j in (i-1, i)):
            count += 1
    return count


def summarize(inventory, output, paths):
    jobs = {r['job']: r for r in json.loads(inventory.read_text())['rows']}
    rows, policies, sources = [], set(), set()
    for path in paths:
        report = json.loads(path.read_text())
        assert report['baseline_exact_parity'], f'Unreproduced baseline: {path}'
        job = jobs[report['job']]
        assert report['job_payload_sha256'] == job['payload_sha256'], 'Inventory/report mismatch'
        assert report['source_sha256'] not in sources, 'Duplicate recording must not count twice'
        sources.add(report['source_sha256'])
        policies.add(json.dumps({k: report[k] for k in ('weights_sha256', 'beat_this', 'madmom', 'dbn')}, sort_keys=True))
        duration = job['health']['duration_seconds']
        a, b = report['decoders']['minimal'], report['decoders']['dbn']
        spans = a['structurally_consistent_spans']
        covered = sum(s['end']-s['start'] for s in spans)
        density = pulse_density_summary(b['beats'], duration)
        _, guard = check_recovery(a['beats'], a['downbeats'], b['beats'], b['downbeats'], duration, report['beat_this'])
        rows.append(dict(job=report['job'], source_url=job['source_url'], duration_seconds=duration,
                         source_sha256=report['source_sha256'], report=str(path),
                         report_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         baseline_gate=a['structural_gate'], candidate_gate=b['structural_gate'],
                         baseline_consistent_seconds=covered, baseline_consistent_fraction=covered/duration,
                         baseline_consistent_spans=spans,
                         baseline_beats=len(a['beats']), candidate_beats=len(b['beats']),
                         baseline_downbeats=len(a['downbeats']), candidate_downbeats=len(b['downbeats']),
                         baseline_beats_not_matched=unmatched(a['beats'], b['beats']),
                         candidate_beats_not_matched=unmatched(b['beats'], a['beats']),
                         candidate_density_changes=density['octave_density_changes'],
                         candidate_pulse_deviations=b['pulse_intervals']['deviations'],
                         recovery_guard=guard,
                         proposed_action='keep_primary' if a['structural_gate']=='passed' else 'review_recovery' if guard['eligible'] else 'keep_unmetered',
                         musical_verdict='unconfirmed', automatic_promotion=False))
    assert len(policies) == 1, 'All recordings must use the same weights and decoding policy'
    output.mkdir(parents=True, exist_ok=False)
    result = dict(policy=json.loads(next(iter(policies))), match_tolerance_seconds=.070,
                  inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(), rows=rows,
                  limitation='Structural consistency, pulse density and observation agreement are not musical accuracy.')
    (output/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    print(json.dumps([dict(job=r['job'], baseline=r['baseline_gate'], candidate=r['candidate_gate'],
                          consistent_percent=round(100*r['baseline_consistent_fraction']),
                          density_changes=len(r['candidate_density_changes']),
                          unmatched=[r['baseline_beats_not_matched'], r['candidate_beats_not_matched']]) for r in rows]))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('inventory', type=Path); p.add_argument('output', type=Path)
    p.add_argument('reports', type=Path, nargs='+')
    args = p.parse_args(); summarize(args.inventory, args.output, args.reports)
