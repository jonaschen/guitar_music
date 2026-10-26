"""Read existing artifacts only; freeze a window before rendering a diagnostic click."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/evaluation/frozen-click-2026-10-26'
PUBLIC = ROOT / 'frontend/public/listening/frozen-click-2026-10-26'
JOB = 'db79e1145ea046088b8aa5ef421d0e3f'


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    began = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=False)
    directory = ROOT / 'output/work/jobs' / JOB
    with sqlite3.connect(f'file:{ROOT}/output/work/jobs/jobs.sqlite3?mode=ro', uri=True) as db:
        score = json.loads(db.execute('select payload from jobs where id=?', (JOB,)).fetchone()[0])['score']
    timing = read(directory / 'timing-analysis.json')
    assert score['beats'] == timing['beats']
    bars = [next(b['time'] for b in score['beats'] if b['measure'] == m and b['beat'] == 1) for m in (8, 16)]
    assert np.allclose(bars, [16.62, 34.56])
    # Predeclared 30-second context, containing the complete historical failed window.
    start, end = 10.0, 40.0
    beats = [b for b in score['beats'] if start <= b['time'] < end]
    frozen = dict(job=JOB, original_bars=[8, 15], original_window=bars,
                  window=[start, end], reason='30-second context enclosing the fixed failed bars; no audition-based selection',
                  source_start_seconds=score['song']['source_start_seconds'],
                  source_sha256=sha(directory / 'analysis-source.wav'),
                  timing_sha256=sha(directory / 'timing-analysis.json'), beats=beats,
                  diagnostic_only=True, beat_engine=timing['engine'], warnings=timing['warnings'],
                  second_pitch_estimator='No independently saved frame F0 found in inspected ROSVOT output; no inference run',
                  second_beat_estimator='No independent same-source beat track used; no inference run',
                  low_energy_rule=dict(frame_ms=20, relative_to_peak_rms_db=-40, minimum_seconds=.3,
                                       interpretation='diagnostic only, not verified rests'))
    write(OUT / 'frozen-inputs.json', frozen)  # Written before audio is generated.

    rosvot = ROOT / 'output/evaluation/rosvot-checkpoint-2026-10-25'
    results = []
    verdicts = ['兩者都不好，B 感覺稍差', '兩者都不好，B 感覺稍好', 'A 明顯較好；未宣布可用']
    for item, verdict in zip(read(rosvot / 'listening-inputs.json'), verdicts):
        audio_path = rosvot / item['file']
        assert sha(audio_path) == item['sha256']
        audio, sr = sf.read(audio_path, always_2d=True)
        hop = round(sr * .02)
        count = len(audio) // hop
        rms = np.sqrt(np.mean(audio[:count * hop].reshape(count, hop, -1) ** 2, axis=(1, 2)))
        low = rms < rms.max() * .01
        edges = np.diff(np.r_[False, low, False].astype(int))
        intervals = [(a * hop / sr, b * hop / sr) for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]) if (b-a)*hop/sr >= .3]
        row = dict(id=item['id'], verdict=verdict, duration=len(audio)/sr,
                   source_sha256=sha(audio_path), low_energy_intervals=intervals,
                   lyrics_ratio=None, lyrics_reason='No verified performed syllable count', candidates={})
        for label, path in [('G', Path(item['baseline'])), ('ROSVOT', rosvot / f"{item['id']}-notes.json")]:
            notes = read(path)
            durations = [n['end']-n['start'] for n in notes]
            overlap = [sum(max(0, min(b,n['end'])-max(a,n['start'])) for n in notes) for a,b in intervals]
            row['candidates'][label] = dict(notes=len(notes), under_100ms=sum(d < .1 for d in durations),
                                           median_seconds=float(np.median(durations)),
                                           low_energy_overlap_seconds=overlap, notes_sha256=sha(path))
        results.append(row)

    with sf.SoundFile(directory / 'analysis-source.wav') as source:
        sr = source.samplerate
        source.seek(round(start * sr))
        original = source.read(round((end-start)*sr), always_2d=True)
    assert len(original) == round(30 * sr)
    clicks = np.zeros_like(original)
    event_samples = []
    for beat in beats:
        index = round((beat['time']-start)*sr)
        length = min(round(.045*sr), len(clicks)-index)
        t = np.arange(length)/sr
        accent = beat['beat'] == 1
        wave = np.cos(2*np.pi*(1500 if accent else 950)*t)*np.exp(-t/.009)
        clicks[index:index+length] += (.65 if accent else .5)*wave[:, None]
        event_samples.append(dict(sample=index, accent=accent, beat=beat['beat'], measure=beat['measure']))
    source_gain = .65 / max(float(np.max(np.abs(original))), 1e-9)
    mixed = original * source_gain + clicks
    common_gain = min(1., .95 / max(float(np.max(np.abs(mixed))), 1e-9))
    sf.write(OUT / 'original-plus-click.wav', mixed * common_gain, sr, subtype='PCM_16')
    sf.write(OUT / 'click-only.wav', clicks * common_gain, sr, subtype='PCM_16')
    decoded, actual_sr = sf.read(OUT / 'original-plus-click.wav', always_2d=True)
    assert actual_sr == sr and decoded.shape == original.shape
    assert np.max(np.abs(decoded-mixed*common_gain)) <= 1/32768 + 1e-12
    assert np.max(np.abs(decoded)) < .951
    assert all(abs(e['sample']/sr-(b['time']-start)) <= .5/sr+1e-12 for e,b in zip(event_samples, beats))
    iois = np.diff([b['time'] for b in beats])
    report = dict(cases=results, click=dict(events=len(beats), accents=sum(e['accent'] for e in event_samples),
                  sr=sr, duration=30, source_gain=source_gain, common_gain=common_gain,
                  peak=float(np.max(np.abs(decoded))), sample_events=event_samples,
                  ioi_min=float(iois.min()), ioi_max=float(iois.max()), ioi_cv=float(iois.std()/iois.mean()),
                  audio_sha256=sha(OUT/'original-plus-click.wav'), sample_rounding_max_seconds=.5/sr,
                  checks='original timing unchanged; no time stretch; PCM readback within one LSB; no clipping'),
                  script_seconds=time.monotonic()-began,
                  caution='No quality pass, model ranking or causal diagnosis follows from these descriptors')
    write(OUT / 'report.json', report)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT / 'original-plus-click.wav', PUBLIC)
    shutil.copy2(ROOT / 'frontend/scripts/frozen-click.html', PUBLIC / 'index.html')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
