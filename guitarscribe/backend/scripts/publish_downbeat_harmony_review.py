"""Assemble A/B without regenerating the previously heard A or changing gain.

Usage: python publish_downbeat_harmony_review.py PRIOR_AUDIO B_AUDIO INPUT_DIR OUTPUT_DIR
The caller can copy the finished packet into the authenticated static site.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def publish(prior,rendered,inputs,output):
    a=json.loads((prior/'audio-checks.json').read_text());b=json.loads((rendered/'audio-checks.json').read_text())
    assert a['gain']==b['gain']==1, 'Stop: shared gain required; do not normalize A/B separately'
    assert a['frames']==b['frames'] and a['rate']==b['rate'] and a['clicks']==b['clicks']
    assert (prior/'source.wav').read_bytes()==(rendered/'source.wav').read_bytes()
    assert (prior/'click.wav').read_bytes()==(rendered/'click.wav').read_bytes()
    assert a['files']['mix']['sha256']=='f11996f70e475ca07f02ab5b78686679bcbe9540e08277ec7b943b91805ee8f2'
    output.mkdir(parents=True,exist_ok=False)
    checks={}
    for filename,path in [('a-mix.wav',prior/'mix.wav'),('a-guitar.wav',prior/'guitar.wav'),
                          ('b-mix.wav',rendered/'mix.wav'),('b-guitar.wav',rendered/'guitar.wav'),('source.wav',prior/'source.wav')]:
        shutil.copy2(path,output/filename)
        checks[filename]=hashlib.sha256((output/filename).read_bytes()).hexdigest()
    assert checks['a-mix.wav']!=checks['b-mix.wav']
    assert checks['a-mix.wav']==a['files']['mix']['sha256']
    assert checks['a-guitar.wav']==a['files']['guitar']['sha256']
    assert checks['b-mix.wav']==b['files']['mix']['sha256']
    root=Path(__file__).resolve().parents[2]
    shutil.copy2(root/'frontend/scripts/downbeat-harmony-review.html',output/'index.html')
    shutil.copy2(inputs/'packet.json',output/'packet.json')
    (output/'checks.json').write_text(json.dumps(dict(files=checks,original_A_reused=True,click_identical=True,
                                                    gain=1,frames=a['frames'],rate=a['rate']),indent=2))
    print(json.dumps(checks,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('prior','rendered','inputs','output'):p.add_argument(n,type=Path)
    a=p.parse_args();publish(a.prior,a.rendered,a.inputs,a.output)
