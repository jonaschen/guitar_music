"""Build an isolated static review from completed runs; never modifies live data."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.song_structure import load_ready_candidate, render_review
from app.evaluation.song_structure_feedback import apply_feedback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--feedback', type=Path, action='append', default=[])
    args = parser.parse_args()
    candidates = [load_ready_candidate(path) for path in args.run]
    feedback = [json.loads(path.read_text()) for path in args.feedback]
    if len({f['job'] for f in feedback}) != len(feedback):
        raise ValueError('Only one feedback revision per source is supported')
    for item in feedback:
        matches = [i for i, candidate in enumerate(candidates) if candidate['job'] == item['job']]
        if len(matches) != 1:
            raise ValueError('Feedback requires exactly one matching candidate')
        i = matches[0]
        manifest = json.loads((args.run[i] / 'manifest.json').read_text())
        candidates[i] = apply_feedback(candidates[i], item, manifest['source']['audio_sha256'])
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'index.html').write_text(render_review(candidates))
    (args.out / 'review-data.json').write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + '\n')
    print(f'Built {len(candidates)} review documents in {args.out}')


if __name__ == '__main__':
    main()
