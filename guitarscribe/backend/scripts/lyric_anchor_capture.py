"""Prepare or serve an original-audio lyric landmark packet; no score writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from urllib.parse import quote
from urllib.request import Request, urlopen
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def read_json(url, data=None):
    request = Request(url, data=None if data is None else json.dumps(data).encode(), headers={'Content-Type':'application/json'})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def prepare(args):
    if args.packet.exists():
        raise ValueError('Use a new packet directory; preserve previous annotation sources')
    anchor_doc = json.loads(args.anchors.read_text())
    anchors = anchor_doc['anchors']
    if not 1 <= len(anchors) <= 100:
        raise ValueError('Expected 1 to 100 lyric anchors')
    for a in anchors:
        if a['phrase'][a['character_index']] != a['character']:
            raise ValueError('Ambiguous lyric character')
    if not 0 <= args.analysis_start or not 0 < args.content_duration:
        raise ValueError('Invalid analysis-time origin or content length')
    with wave.open(str(args.audio), 'rb') as audio:
        duration = audio.getnframes()/audio.getframerate()
    if args.content_duration > duration:
        raise ValueError('Audio is shorter than content duration')
    revision = anchor_doc['revision']; url = args.api.rstrip('/')+'/revisions/'+quote(revision,safe='')
    score = read_json(url)
    if args.analysis_start+args.content_duration > score['song']['duration_seconds']+.001:
        raise ValueError('Audio interval exceeds score source')
    manifest = read_json(args.api.rstrip('/')+'/scores/playback/manifest',score)
    if read_json(url) != score:
        raise ValueError('Score changed during packet preparation')
    config = {'revision':revision,'analysis_start':args.analysis_start,'content_duration':args.content_duration,
              'source_start_seconds':score['song'].get('source_start_seconds',0),
              'audio_sha256':hashlib.sha256(args.audio.read_bytes()).hexdigest(),
              'anchors':anchors,'manifest_revision':manifest['revision']}
    config['config_id'] = hashlib.sha256(json.dumps({'config':config,'score':score,'manifest':manifest},sort_keys=True).encode()).hexdigest()
    args.packet.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(args.audio,args.packet/'audio.wav')
    shutil.copyfile(Path(__file__).resolve().parents[2]/'frontend/scripts/lyric-anchor-capture.html',args.packet/'index.html')
    for name,data in [('config',config),('score',score),('manifest',manifest)]:
        (args.packet/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    print(args.packet)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--packet',type=Path,required=True)
    prep.add_argument('--anchors',type=Path,required=True)
    prep.add_argument('--audio',type=Path,required=True)
    prep.add_argument('--analysis-start',type=float,required=True)
    prep.add_argument('--content-duration',type=float,required=True)
    prep.add_argument('--api',default='http://127.0.0.1:8000')
    serve = commands.add_parser('serve')
    serve.add_argument('--packet',type=Path,required=True)
    serve.add_argument('--receipts',type=Path,required=True)
    serve.add_argument('--port',type=int,default=8001)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args)
    else:
        import uvicorn
        from app.evaluation.anchor_capture import create_capture_app
        uvicorn.run(create_capture_app(args.packet,args.receipts),host='127.0.0.1',port=args.port)


if __name__ == '__main__':main()
