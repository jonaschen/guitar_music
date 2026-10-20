#!/usr/bin/env python3
"""Create a read-only Bar 28–35 listening packet from an explicit saved revision."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.request import urlopen
from urllib.parse import quote
import wave

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', required=True)
parser.add_argument('--api', default='http://127.0.0.1:8000')
args = parser.parse_args()
frontend = Path(__file__).resolve().parents[1]
with urlopen(args.api.rstrip('/') + '/revisions/' + quote(args.revision, safe=''), timeout=20) as response:
    score = json.load(response)
params = score['provenance']['parameters']
job = params['analysis_source_job_id']
if not re.fullmatch(r'[a-zA-Z0-9_-]+', job):
    raise ValueError('Invalid source job identifier')
start = next(b['time'] for b in score['beats'] if b['measure'] == 28 and b['beat'] == 1)
end = next(b['time'] for b in score['beats'] if b['measure'] == 36 and b['beat'] == 1)
if not 0 <= start < end:
    raise ValueError('Invalid bar range')
source = frontend.parent / 'output/work/jobs' / job / 'analysis-source.wav'
packet = frontend / 'public/listening/ensemble-2026-10-18'
packet.mkdir(parents=True, exist_ok=True)
# The analysis source already excludes source_start_seconds. Do not crop twice.
with wave.open(str(source), 'rb') as audio:
    rate = audio.getframerate()
    first, last = round(start * rate), round(end * rate)
    if last > audio.getnframes():
        raise ValueError('Source does not cover the selected bars')
    audio.setpos(first)
    with wave.open(str(packet / 'source.wav'), 'wb') as clip:
        clip.setparams(audio.getparams())
        clip.writeframes(audio.readframes(last - first))
(packet / 'config.json').write_text(json.dumps(dict(revision=args.revision, start=start, end=end)))
shutil.copyfile(frontend / 'scripts/ensemble-listening.html', packet / 'index.html')
(packet / 'provenance.json').write_text(json.dumps(dict(
    revision=args.revision, job=job, source_start_seconds=score['song'].get('source_start_seconds', 0),
    analysis_start=start, analysis_end=end, source_frames=[first, last], sample_rate=rate,
    clip_sha256=hashlib.sha256((packet / 'source.wav').read_bytes()).hexdigest(),
), indent=2))
print(packet / 'index.html')
