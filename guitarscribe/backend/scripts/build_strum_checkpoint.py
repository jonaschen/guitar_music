"""Rebuild an explicitly accepted performance recipe without saving a score revision."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.strum_timing import FirstStrumDelay, apply_first_strum_delays
from app.exporters.midi import compile_playback_manifest, export_manifest_midi
from app.models.score import SongScore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Checkpoint directory already exists; use a new output path to preserve prior evidence')
    recipe = json.loads(args.recipe.read_text())
    url = args.api.rstrip('/') + '/revisions/' + quote(recipe['revision'], safe='')
    def read():
        with urlopen(url, timeout=30) as response:
            return json.load(response)
    saved = read()
    base = compile_playback_manifest(SongScore.model_validate(saved))
    changes = [FirstStrumDelay.model_validate(change) for change in recipe['adjustments']]
    candidate = apply_first_strum_delays(base, changes, expected_revision=recipe['base_manifest_revision'])
    # Strong parity with the accepted browser control: only selected guitar times change.
    by_id = {event.id: event for event in candidate.events}
    moves = {c.expected_start: c.expected_start + c.delay_seconds for c in changes}
    for event in base.events:
        expected = event if event.track != 'guitar' else event.model_copy(update={
            'start': moves.get(event.start, event.start),
            'end': moves.get(event.end, event.end),
            'sustain_end': moves.get(event.sustain_end, event.sustain_end),
        })
        if by_id[event.id] != expected:
            raise RuntimeError('Candidate differs from accepted operation')
    if read() != saved:
        raise RuntimeError('Saved score changed during checkpoint generation')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'manifest.json').write_text(candidate.model_dump_json(indent=2))
    (args.output / 'performance.mid').write_bytes(export_manifest_midi(candidate))
    (args.output / 'recipe.json').write_text(json.dumps(recipe, indent=2))
    (args.output / 'report.json').write_text(json.dumps({
        'saved_revision_unchanged': True,
        'base_revision': base.revision, 'candidate_revision': candidate.revision,
        'event_count': len(candidate.events),
        'changed_first_strokes': len(changes),
        'status': 'Local performance checkpoint; not a saved score or product default',
        'midi_limit': 'Standard MIDI uses its instrument envelope; audio timbre/release need not match WebAudio',
    }, indent=2))
    print(args.output)


if __name__ == '__main__':
    main()
