"""Read source-bound structure JSON snapshots and report net editing burden.

Accepts a document or API snapshot. No models, network, database writes or audio.
Use the original source-matched independent-reference scorer separately for accuracy.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.evaluation.structure_review_summary import review_summary


def report(paths):
    rows=[]
    for path in paths:
        raw=json.loads(Path(path).read_text())
        if 'document' in raw:
            if raw.get('source_matches') is not True or raw.get('current_source')!=raw['document']['source']:
                raise ValueError('Snapshot does not match its current audio source')
            row=review_summary(raw['document']);row['saved_version']=raw.get('version')
        else:
            row=review_summary(raw);row['saved_version']=None
        if any(x['source']['audio_sha256']==row['source']['audio_sha256'] for x in rows):
            raise ValueError('Do not count the same recording twice')
        rows.append(row)
    return dict(schema_version=1,songs=rows,semantic_quality='awaiting_independent_reference',
                correction_time='not_measured',music_accuracy_claim=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshots',nargs='+',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(); result=json.dumps(report(args.snapshots),ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.write_text(result);args.output.chmod(0o600)
    else: print(result,end='')
