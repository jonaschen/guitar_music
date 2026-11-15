"""Compare a finished candidate to independent annotations; never invent references."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.song_structure import load_ready_candidate
from app.evaluation.song_structure_metrics import compare_structure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    candidate = load_ready_candidate(args.run)
    manifest = json.loads((args.run / 'manifest.json').read_text())
    reference = json.loads(args.reference.read_text())
    report = compare_structure(candidate['sections'], reference, candidate['duration'],
                               manifest['source']['audio_sha256'])
    report.update(job=candidate['job'], title=candidate['title'], protocol_id=manifest['protocol_id'],
                  model=manifest['model'], candidate_commit=manifest['candidate_commit'],
                  reference_provenance={k: reference[k] for k in
                                        ['audio_sha256', 'annotator', 'evidence', 'independent_of_candidate']})
    # Evidence files are immutable: a rerun must use another output name.
    with args.out.open('x') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Wrote reference metrics; dataset/correction gates are not automatically approved.')


if __name__ == '__main__':
    main()
