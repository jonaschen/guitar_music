"""Read-only current melody lineage and fixed external-input preflight."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.exporters.midi import compile_playback_manifest

ROOT=Path(__file__).resolve().parents[2]

def main():
    # SQLite read-only access: do not create/initialize a store for this audit.
    import sqlite3
    from app.models.score import SongScore
    conn=sqlite3.connect(f'file:{ROOT / "output/work/revisions/guitarscribe.sqlite3"}?mode=ro',uri=True)
    def load(identifier):
        row=conn.execute('SELECT payload FROM revisions WHERE id=?',(identifier,)).fetchone()
        assert row is not None,identifier
        return SongScore.model_validate_json(row[0])
    parent=load('db8c657e-62a5-4fad-a33e-cde25a9e1c0d')
    excerpt=load('bc41b274-69d4-430f-8dda-52bd0759119d')
    grid=load('4384c826-a4f0-4442-b1d4-ef7bbc7888f4')
    offset=excerpt.song.source_start_seconds-parent.song.source_start_seconds
    end=offset+excerpt.song.duration_seconds
    expected=[(n.id,n.midi,max(0,n.start-offset),min(excerpt.song.duration_seconds,n.end-offset)) for n in parent.melody if n.end>offset and n.start<end]
    actual=[(n.id,n.midi,n.start,n.end) for n in excerpt.melody]
    assert len(expected)==len(actual)
    for a,b in zip(expected,actual):
        assert a[:2]==b[:2] and abs(a[2]-b[2])<1e-8 and abs(a[3]-b[3])<1e-8
    assert excerpt.melody==grid.melody
    stats=[]
    for name,s in [('saved_G',parent),('excerpt',excerpt),('grid_excerpt',grid)]:
        events={e.source_id:e for e in compile_playback_manifest(s).events if e.track=='melody'}
        assert len(events)==len(s.melody)
        for n in s.melody:
            e=events[n.id];assert (e.start,e.end,e.pitches)==(n.start,n.end,(n.midi,))
        durations=[n.end-n.start for n in s.melody]
        gaps=[b.start-a.end for a,b in zip(s.melody,s.melody[1:]) if b.start>a.end]
        stats.append(dict(name=name,notes=len(durations),under_100ms=sum(d<.1 for d in durations),median_seconds=statistics.median(durations),positive_gaps=len(gaps),gap_seconds=sum(gaps),manifest_exact=True))
    packet=ROOT/'output/evaluation/existing-tool-integration-2026-10-26'
    manifest=json.loads((packet/'manifest.json').read_text());verified=[]
    import soundfile as sf
    with zipfile.ZipFile(packet/'comparison-inputs.zip') as archive:
        for item in manifest['files']:
            data=(packet/item['file']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==item['sha256']
            assert archive.read(item['file'])==data
            info=sf.info(packet/item['file']);assert info.duration<=15 and abs(info.duration-item['duration_seconds'])<1e-8
            verified.append(dict(file=item['file'],sha256=item['sha256'],duration_seconds=info.duration,bytes=len(data)))
    conn.close()
    print(json.dumps(dict(scope='Read-only lineage and transport checks, not melody accuracy',stats=stats,excerpt_matches_saved_G=True,grid_preserves_melody=True,external_packet=verified,uploaded=False),indent=2))

if __name__=='__main__':main()
