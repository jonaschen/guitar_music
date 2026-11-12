"""Subprocess entrypoint: the observation plugin cannot affect the main server."""
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    # Imports after environment setup by the parent; never changes host VAMP_PATH.
    import librosa
    import vamp
    from .root_candidates import compact_trace
    config = json.loads(Path(sys.argv[1]).read_text())
    library = Path(vamp.vampyhost.get_library_for('nnls-chroma:chordino')).resolve()
    if library != Path(config['library']).resolve() or hashlib.sha256(library.read_bytes()).hexdigest() != config['library_sha256']:
        raise ValueError('Unexpected observer plugin')
    if hashlib.sha256(Path(config['audio']).read_bytes()).hexdigest() != config['audio_sha256']:
        raise ValueError('Source audio changed')
    y, sr = librosa.load(config['audio'], sr=44100, duration=config['duration'])
    data = vamp.collect(y, sr, 'nnls-chroma:chordino')
    evidence = compact_trace(json.loads(Path(os.environ['GUITARSCRIBE_TRACE_PATH']).read_text()))
    evidence.update(source=config['source'], audio_sha256=config['audio_sha256'], library_sha256=config['library_sha256'],
                    raw_events=[{'timestamp': float(e['timestamp']), 'label': e['label']} for e in data['list']])
    Path(config['output']).write_text(json.dumps(evidence, allow_nan=False))


if __name__ == '__main__':
    main()
