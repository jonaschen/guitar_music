"""Build an isolated static review from completed runs; never modifies live data."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.song_structure import load_ready_candidate, render_review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    candidates = [load_ready_candidate(path) for path in args.run]
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'index.html').write_text(render_review(candidates))
    print(f'Built {len(candidates)} unreviewed candidates in {args.out}')


if __name__ == '__main__':
    main()
