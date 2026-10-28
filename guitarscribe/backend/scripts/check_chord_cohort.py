"""Audit frozen local jobs without inference, score writes or quality rankings.

Run with PYTHONPATH=backend. Optional --base-url checks deployed playback/exports.
Missing local data is an error, never a silently excluded failed case.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app.analyzers.beats.timing_diagnostics import describe_observations
from app.models.score import SongScore


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_checks(base_url, score):
    payload = json.dumps(score, allow_nan=False).encode()

    def post(endpoint):
        request = Request(base_url.rstrip('/') + '/scores/' + endpoint, data=payload,
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=60) as response:
            return response.read()

    manifest = json.loads(post('playback/manifest'))
    events = manifest['events']
    assert events and all(e['track'] != 'melody' for e in events)
    assert all(0 <= e['start'] < e['end'] for e in events)
    assert post('midi').startswith(b'MThd')
    assert ElementTree.fromstring(post('musicxml')).tag == 'score-partwise'
    chordpro = post('chordpro').decode()
    assert all('[' + c['symbol'] + ']' in chordpro for c in score['chords'])
    return dict(playback_events=len(events), midi='readable_header',
                musicxml='parsed', chordpro='chord_labels_present')


def audit(root, cohort, base_url=None):
    directory = root / 'output/work/jobs'
    uri = (directory / 'jobs.sqlite3').resolve().as_uri() + '?mode=ro'
    reports = []
    with sqlite3.connect(uri, uri=True) as db:
        for case in cohort['cases']:
            row = db.execute('SELECT payload FROM jobs WHERE id=?', (case['job'],)).fetchone()
            assert row, f"Missing local job: {case['job']}"
            payload = row[0]
            job = json.loads(payload)
            assert job['source_url'] == 'https://www.youtube.com/watch?v=' + case['video']
            assert all(job[k] == v for k, v in cohort['options'].items()), 'Options differ'
            assert job['status'] in ('completed', 'failed'), 'Job is still active'
            files = directory / case['job']
            source_hash = digest(files / 'analysis-source.wav')
            assert source_hash == case['source_sha256'], 'Cohort source audio changed'
            report = dict(**case, status=job['status'], error=job.get('error'),
                          exports='not_run')
            score = job.get('score')
            if job['status'] == 'completed':
                SongScore.model_validate(score)
                assert not score['melody'] and score['provenance']['melody_engine'] == 'disabled'
                assert score['song']['duration_seconds'] == cohort['options']['analysis_seconds']
                beats = [b['time'] for b in score['beats']]
                downbeats = [b['time'] for b in score['beats'] if b['beat'] == 1]
                chords = score['chords']
                assert chords and all(c['start'] < c['end'] for c in chords)
                report['out_of_audio_bounds'] = [dict(id=c['id'], start=c['start'], end=c['end'])
                                                for c in chords if not 0 <= c['start'] < c['end'] <= score['song']['duration_seconds']]
                assert all(a['end'] <= b['start'] + 1e-9 for a, b in zip(chords, chords[1:]))
                report['chords'] = dict(count=len(chords), shortest_seconds=min(c['end']-c['start'] for c in chords),
                                       under_half_second=[dict(start=c['start'], end=c['end'], symbol=c['symbol'])
                                                          for c in chords if c['end']-c['start'] < .5])
                report['provenance'] = score['provenance']
                if base_url:
                    report['exports'] = export_checks(base_url, score)
            else:
                assert score is None, 'Failed job unexpectedly exposes a score'
                path = files / 'timing-rejection.json'
                if not path.exists():
                    path = files / 'timing-audit.json'
                evidence = json.loads(path.read_text())
                if 'sha256' in evidence:
                    assert evidence['sha256'] == source_hash, 'Frozen audio differs'
                beats, downbeats = evidence['beats'], evidence['downbeats']
                report['evidence_file'] = path.name
                report['evidence_sha256'] = digest(path)
            report['timing'] = describe_observations(beats, downbeats)
            assert report['timing']['aligned_observations']
            assert db.execute('SELECT payload FROM jobs WHERE id=?', (case['job'],)).fetchone()[0] == payload
            report['job_payload_unchanged'] = True
            reports.append(report)
    return dict(scope=cohort['scope'], options=cohort['options'], cases=reports,
                note='Counts describe structure, not musical accuracy or manual correction effort.')


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, default=root / 'backend/fixtures/chord-cohort-2026-10-28.json')
    parser.add_argument('--base-url')
    args = parser.parse_args()
    print(json.dumps(audit(root, json.loads(args.cohort.read_text()), args.base_url), ensure_ascii=False, indent=2, allow_nan=False))
