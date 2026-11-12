"""Install an isolated observation plugin from the frozen local Chordino source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.observe_chord_decoder import patch


def build(root, destination):
    preparation = json.loads((root / 'output/evaluation/chord-bass-ablation-2026-11-05/run/before-inference-manifest.json').read_text())
    baseline = preparation['builds']['baseline']
    source = Path(baseline['library']).parent
    plan = json.loads((root / 'docs/evaluation/chord-bass-ablation-plan-v2-2026-11-05.json').read_text())
    destination.mkdir(parents=True, exist_ok=False)
    for name, digest in baseline['source_sha256'].items():
        original = source / name
        if hashlib.sha256(original.read_bytes()).hexdigest() != digest:
            raise ValueError('Frozen source changed: ' + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    cpp = destination / 'Chordino.cpp'
    cpp.write_text(patch(cpp.read_text()))
    subprocess.run(plan['build']['command'], cwd=destination, check=True, timeout=180)
    digest = hashlib.sha256((destination / 'nnls-chroma.so').read_bytes()).hexdigest()
    (destination / 'root-plugin.json').write_text(json.dumps({'library_sha256': digest, 'source_sha256': baseline['source_sha256'],
                                                             'observation_only': True}, indent=2))
    print('Isolated root candidate plugin installed:', destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--destination', type=Path, default=Path.home() / '.cache/guitarscribe-root-candidates/plugin')
    args = parser.parse_args()
    build(args.project.resolve(), args.destination.resolve())
