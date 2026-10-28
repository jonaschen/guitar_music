"""Create independent, traceable chord workspaces from completed frozen jobs.

No inference. Existing jobs/revisions remain untouched. Output must be new.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen

from app.models.score import SongScore
from app.services.chord_grid_candidate import build_chord_grid_candidate
from app.exporters.midi import compile_playback_manifest, export_midi
from app.exporters.musicxml import export_musicxml

TITLES = {
    'vmmRFJcDJJw': '直到世界的盡頭',
    'QbM3o4qy9RQ': '君が好きだと叫びたい',
}


def prepare(root, output, base_url):
    cohort = json.loads((root / 'backend/fixtures/chord-cohort-2026-10-28.json').read_text())
    output.mkdir(parents=True, exist_ok=False)

    def api(path, data=None):
        request = Request(base_url.rstrip('/') + path, data=None if data is None else json.dumps(data).encode(),
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=30) as response:
            return json.load(response)

    reports = []
    for number, case in enumerate(cohort['cases'], 1):
        if case['video'] not in TITLES:
            continue
        job = api('/api/v1/jobs/' + case['job'])
        assert job['status'] == 'completed'
        assert all(job[k] == v for k, v in cohort['options'].items())
        source = root / 'output/work/jobs' / case['job'] / 'analysis-source.wav'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == case['source_sha256']
        original = SongScore.model_validate(job['score'])
        bounded = original.model_copy(deep=True)
        bounds_changes = []
        for chord in bounded.chords:
            before = [chord.start, chord.end]
            chord.start = max(0, chord.start)
            chord.end = min(bounded.song.duration_seconds, chord.end)
            assert chord.start < chord.end, 'Do not silently delete an out-of-range chord'
            if before != [chord.start, chord.end]:
                bounds_changes.append(dict(id=chord.id, before=before, after=[chord.start, chord.end]))
        candidate, grid = build_chord_grid_candidate(bounded)
        assert not grid['protected'] and not grid['unquantized_edges']
        assert candidate.beats == original.beats and candidate.melody == original.melody == []
        assert len(candidate.chords) == len(original.chords)
        for a, b in zip(original.chords, candidate.chords):
            assert a.model_dump(exclude={'start', 'end'}) == b.model_dump(exclude={'start', 'end'})
        candidate.song.title = TITLES[case['video']]
        candidate.song.source_type = 'youtube'
        candidate.song.source_url = job['source_url']
        candidate.provenance.parameters.update(analysis_source_job_id=case['job'],
            review_audio_bounds='audio-intersection-v1', review_cohort='four-source-2026-10-28')
        # Keep original detector version: this is postprocessing saved observations.
        candidate.analysis.warnings.append('New-source beat phase and chord quality have not been human-verified.')
        manifest = compile_playback_manifest(candidate)
        assert not any(e.track == 'melody' for e in manifest.events)
        assert any(e.track == 'guitar' for e in manifest.events)
        directory = output / f'song-{number}'
        directory.mkdir()
        (directory / 'score.json').write_text(candidate.model_dump_json(indent=2))
        (directory / 'manifest.json').write_text(manifest.model_dump_json(indent=2))
        (directory / 'accompaniment.mid').write_bytes(export_midi(candidate))
        (directory / 'score.musicxml').write_text(export_musicxml(candidate))
        shutil.copyfile(source, directory / 'source.wav')
        revision = api('/revisions', {'score': candidate.model_dump(mode='json')})['revision_id']
        report = dict(**case, number=number, title=candidate.song.title, revision=revision,
                      bounds_changes=bounds_changes, grid=grid,
                      score_sha256=hashlib.sha256(candidate.model_dump_json().encode()).hexdigest(),
                      guitar_events=sum(e.track == 'guitar' for e in manifest.events),
                      musical_verdict='unconfirmed', duration=candidate.song.duration_seconds)
        reports.append(report)
        (output / 'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2)+'\n')
        assert SongScore.model_validate(api('/revisions/' + revision)) == candidate
        assert api('/api/v1/jobs/' + case['job']) == job
    assert len(reports) == 2
    print(json.dumps([dict(title=r['title'], revision=r['revision']) for r in reports], ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parents[2], args.output, args.base_url)
