"""Build private, explicit migration artifacts; never uploads or changes live data.

Runtime copies target Ubuntu 24.04 / CPython 3.12 / x86_64 only. Installed
package metadata/licenses and source commit are retained for maintenance.
"""
import argparse
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def digest_database(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        return hashlib.sha256('\n'.join(db.iterdump()).encode()).hexdigest()


def private_work_copy(source, target):
    """Snapshot SQLite through its API, validate no concurrent edits; never copy WAL."""
    source, target = Path(source), Path(target)
    from host_activity import active_analysis
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Workspace symlinks are not migrated')
    if active_analysis(source):
        raise RuntimeError('Wait for current analysis before copying the workspace')
    def file_hashes(root):
        return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
                if p.is_file() and '.sqlite3' not in p.name and not p.name.endswith('.lock')
                and not any(part.startswith('root-candidates-') for part in p.relative_to(root).parts)}
    files_before = file_hashes(source)
    databases = sorted(source.rglob('*.sqlite3'))
    before = {str(p.relative_to(source)): digest_database(p) for p in databases}
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3-*', '*.lock', 'root-candidates-*'))
    for path in databases:
        copied = target / path.relative_to(source)
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(copied)) as dst:
                src.backup(dst)
                dst.execute('PRAGMA journal_mode=DELETE')
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Database backup failed integrity check')
        if digest_database(copied) != before[str(path.relative_to(source))]:
            raise RuntimeError('Progress changed during backup; retry without replacing live files')
    after = {str(p.relative_to(source)): digest_database(p) for p in source.rglob('*.sqlite3')}
    if before != after or active_analysis(source):
        raise RuntimeError('Workspace changed during backup; retry')
    if files_before != file_hashes(target) or files_before != file_hashes(source):
        raise RuntimeError('Audio or result files changed during backup; retry')
    return {'sqlite_logical_sha256': before, 'files_sha256': files_before}


def pack(path, entries):
    if path.exists():
        raise FileExistsError(path)
    with tarfile.open(path, 'w:gz', compresslevel=1) as archive:
        for source, destination in entries:
            archive.add(source, arcname=destination, filter=lambda m: None if '__pycache__' in Path(m.name).parts else m)


def prepare(repo, cache, out, *, app_only=False):
    repo, cache, out = Path(repo).resolve(), Path(cache).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    manifest = {'commit': commit, 'target': 'Ubuntu 24.04 x86_64 CPython 3.12', 'private_data': True}
    with tempfile.TemporaryDirectory(prefix='guitarscribe-cloud-build-') as temporary:
        stage = Path(temporary)
        paths = ['guitarscribe/backend/app', 'guitarscribe/backend/scripts', 'guitarscribe/backend/pyproject.toml',
                 'guitarscribe/backend/examples', 'guitarscribe/frontend', 'guitarscribe/rhythm-patterns']
        payload = subprocess.check_output(['git', '-C', str(repo), 'archive', commit, '--', *paths])
        with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
            archive.extractall(stage, filter='data')
        app = stage / 'guitarscribe'
        frontend = app / 'frontend'
        # Never use the working tree's dist or public directory.
        shutil.rmtree(frontend / 'public', ignore_errors=True)
        subprocess.run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=frontend, check=True)
        subprocess.run(['npm', 'run', 'build'], cwd=frontend, check=True)
        site = stage / 'site'; site.mkdir()
        shutil.copy(frontend / 'dist/index.html', site)
        shutil.copytree(frontend / 'dist/assets', site / 'assets')
        toolbar = Path(__file__).with_name('cloud_toolbar.js')
        shutil.copy(toolbar, site / 'cloud-toolbar.js')
        index = site / 'index.html'
        index.write_text(index.read_text().replace('</body>', '<script src="/cloud-toolbar.js" defer></script></body>'))
        manifest['cloud_toolbar_sha256'] = sha(toolbar)
        # The VM-specific wrapper is recorded independently of the base commit.
        host = Path(__file__).with_name('host_activity.py')
        shutil.copy(host, app / 'backend/host_activity.py')
        manifest['host_wrapper_sha256'] = sha(host)
        for helper in ('prepare_release.py', 'backup_work.py', 'release_workspace.py', 'apply_app_release.py'):
            source = Path(__file__).with_name(helper)
            shutil.copy(source, app / 'backend' / helper)
            manifest[helper + '_sha256'] = sha(source)
        pack(out / 'app.tar.gz', [(app / 'backend', 'app/backend'), (app / 'rhythm-patterns', 'app/rhythm-patterns'), (site, 'site')])
        if app_only:
            manifest['release_kind'] = 'app_only'
            manifest['artifacts'] = {'app.tar.gz': {'sha256': sha(out / 'app.tar.gz'), 'bytes': (out / 'app.tar.gz').stat().st_size}}
            (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            return manifest

        runtime = [
            (cache / 'guitarscribe-runtime/lib/python3.12/site-packages', 'runtime/main/lib/python3.12/site-packages'),
            (cache / 'guitarscribe-structure-runtime/lib/python3.12/site-packages', 'runtime/structure/lib/python3.12/site-packages'),
            (cache / 'guitarscribe-beat-dbn/python', 'runtime/dbn'),
            (cache / 'guitarscribe-chordino-diagnostic/python', 'runtime/vamp-python'),
            (cache / 'guitarscribe-chordino-diagnostic/source/nnls-chroma.so', 'runtime/chordino/nnls-chroma.so'),
            (cache / 'guitarscribe-chordino-diagnostic/source/COPYING', 'runtime/chordino/COPYING'),
            (cache / 'guitarscribe-root-candidates/plugin', 'runtime/root-plugin'),
            (cache / 'guitarscribe-song-structure/model-cache', 'runtime/structure-models'),
            (cache / 'torch/hub/checkpoints', 'runtime/torch/hub/checkpoints'),
            (Path.home() / '.nvm/versions/node/v24.14.0/bin/node', 'runtime/bin/node'),
        ]
        for original, destination in runtime:
            if not original.exists():
                raise FileNotFoundError(original)
        pack(out / 'runtime.tar.gz', runtime)
        for name in ('main', 'structure'):
            binary = cache / ('guitarscribe-runtime' if name == 'main' else 'guitarscribe-structure-runtime') / 'bin/python'
            freeze = subprocess.check_output([str(binary), '-m', 'pip', 'freeze'], text=True)
            (out / f'{name}-packages.txt').write_text(freeze)
        protocol = json.loads((repo / 'guitarscribe/output/web-preview/structure-runtime/protocol.json').read_text())
        if protocol.get('sources'):
            raise ValueError('Runtime protocol must not embed private source paths')
        protocol['preprocessing']['python'] = '/srv/guitarscribe/runtime/main/bin/python'
        protocol['model_cache'] = '/srv/guitarscribe/runtime/structure-models'
        for entry in protocol['runtime_weights']:
            filename = Path(entry['path']).name
            folder = '/srv/guitarscribe/runtime/structure-models/checkpoints' if filename.endswith('.pth') else '/srv/guitarscribe/runtime/torch/hub/checkpoints'
            entry['path'] = f'{folder}/{filename}'
        (out / 'protocol.json').write_text(json.dumps(protocol, ensure_ascii=False, indent=2))
        manifest.update(private_work_copy(repo / 'guitarscribe/output/web-preview/work', stage / 'work'))
        pack(out / 'personal-work.tar.gz', [(stage / 'work', 'work')])
    manifest['artifacts'] = {p.name: {'sha256': sha(p), 'bytes': p.stat().st_size} for p in sorted(out.iterdir())}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache')
    parser.add_argument('--app-only', action='store_true', help='Build only code; never inspect or package work/runtime')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.repo, args.cache, args.out, app_only=args.app_only)
    print(json.dumps({'commit': result['commit'], 'artifacts': result['artifacts']}, indent=2))
