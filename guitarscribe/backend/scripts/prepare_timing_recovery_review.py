"""Fixed two-source timing-only listening checkpoint; no score/database writes.

Usage: python prepare_timing_recovery_review.py GUITARSCRIBE_ROOT OUTPUT_DIR
Windows target previously inconsistent intro/outro, not already accepted excerpts.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.analysis_health import pulse_density_summary
from app.analyzers.beats.guarded_recovery import check_recovery

CASES = [
    ('遇見：鋼琴前奏進主歌', '656a21b59b9a4b7e990a8bd586276c28', 0, 40),
    ('君が好きだと叫びたい（灌籃高手）：尾段', 'fe26276f754d4578849081cf2490064f', 193, 226),
]


def prepare(root, output):
    output.mkdir(parents=True, exist_ok=False)
    work = root/'output/work'
    db = sqlite3.connect(f'file:{work}/jobs/jobs.sqlite3?mode=ro', uri=True)
    rows = []
    for i, (title, job_id, start, end) in enumerate(CASES, 1):
        folder = output/str(i); folder.mkdir()
        payload = db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()[0]
        job = json.loads(payload)
        source = work/'jobs'/job_id/'input.wav'
        report = json.loads((root/'output/evaluation/cross-song-decoders-2026-11-02/catalog'/job_id/'report.json').read_text())
        assert report['baseline_exact_parity']
        assert report['job_payload_sha256'] == hashlib.sha256(payload.encode()).hexdigest()
        assert report['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
        candidate = report['decoders']['dbn']
        primary = report['decoders']['minimal']
        _, guard = check_recovery(primary['beats'], primary['downbeats'], candidate['beats'], candidate['downbeats'],
                                  job['score']['song']['duration_seconds'], report['beat_this'])
        assert guard['eligible'], guard['reasons']
        assert candidate['structural_gate'] == 'passed'
        assert not pulse_density_summary(candidate['beats'], job['score']['song']['duration_seconds'])['octave_density_changes']
        assert not candidate['pulse_intervals']['deviations'], 'Unresolved gaps/density changes: no listening packet'
        assert 0 <= start < end <= job['score']['song']['duration_seconds']
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-af',
                        f'atrim=start={start}:end={end},asetpts=PTS-STARTPTS', '-ar', '22050', '-ac', '1',
                        '-c:a', 'pcm_f32le', str(folder/'source-raw.wav')], check=True)
        audio, rate = sf.read(folder/'source-raw.wav'); assert rate == 22050
        clicks = np.zeros(len(audio)); schedule = []
        for beat in candidate['projection']['beats']:
            if not start <= beat['time'] < end:
                continue
            down = beat['beat'] == 1
            t = np.arange(round(.065*rate))/rate
            pulse = (.30 if down else .18)*np.sin(2*np.pi*(1500 if down else 1000)*t)*np.exp(-t/.015)
            at = round((beat['time']-start)*rate); n = min(len(pulse), len(audio)-at)
            clicks[at:at+n] += pulse[:n]
            schedule.append(dict(time=beat['time']-start, downbeat=down, measure=beat['measure']))
        original = audio*.45; mix = original+clicks
        gain = min(1, .95/max(float(np.max(np.abs(mix))), float(np.max(np.abs(original))), 1e-9))
        checks = {}
        for name, wave in [('source', original), ('click', mix)]:
            assert np.isfinite(wave).all()
            path = folder/(name+'.wav'); sf.write(path, wave*gain, rate, subtype='PCM_16')
            checks[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (folder/'source-raw.wav').unlink()
        # Read-only sample notation: each cell spans two detected downbeats.
        downbeats = candidate['downbeats']; bars = []
        for a, b in zip(downbeats, downbeats[1:]):
            if b <= start or a >= end:
                continue
            labels = []
            for chord in job['score']['chords']:
                if chord['end'] > a and chord['start'] < b and (not labels or labels[-1] != chord['symbol']):
                    labels.append(chord['symbol'])
            bars.append(dict(start=a-start, end=b-start, chords=' → '.join(labels)))
        rows.append(dict(title=title, job=job_id, start=start, end=end, gain=gain, rate=rate,
                         duration_seconds=len(audio)/rate, source_url=job['source_url'],
                         source_sha256=report['source_sha256'], files=checks, clicks=schedule, bars=bars,
                         recovery_guard=guard,
                         musical_verdict='unconfirmed', original_score_unchanged=True))
        assert db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()[0] == payload
    db.close()
    (output/'packet.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    template = root/'frontend/scripts/timing-recovery-review.html'
    (output/'index.html').write_text(template.read_text())
    print(json.dumps([dict(title=r['title'], seconds=r['duration_seconds'], clicks=len(r['clicks'])) for r in rows], ensure_ascii=False))


if __name__ == '__main__':
    prepare(*map(Path, sys.argv[1:]))
