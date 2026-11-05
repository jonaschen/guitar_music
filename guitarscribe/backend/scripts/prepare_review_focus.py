"""Create separate focus/solo files from an immutable same-gain A/B packet."""
import hashlib,json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.evaluation.review_mix import focus_mix


def run(prior,output):
    output.mkdir(parents=True,exist_ok=False);reports=[]
    for row in json.loads((prior/'packet.json').read_text()):
        number=row['number'];waves={};hashes={}
        for suffix in ('source','a-mix','b-mix'):
            p=prior/f'{number}-{suffix}.wav';digest=hashlib.sha256(p.read_bytes()).hexdigest()
            expected=row['files'][p.name] if 'files'in row else row['checks']['audio'][suffix]['sha256']
            assert digest==expected
            waves[suffix],rate=sf.read(p);assert rate==22050;hashes[p.name]=digest
        outputs,gain=focus_mix(waves['source'],waves['a-mix'],waves['b-mix']);files={}
        for suffix,data in outputs.items():
            p=output/f'{number}-{suffix}.wav';sf.write(p,data,rate,subtype='PCM_16')
            decoded,_=sf.read(p);assert len(decoded)==len(data) and np.max(np.abs(decoded))<=.951
            files[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
        reports.append(dict(number=number,inputs=hashes,files=files,master_gain=gain,source_gain=.5,
            auxiliary_gain=1,frames=len(waves['source']),rate=rate,
            extraction='Existing PCM mix minus same-gain PCM source; includes <=1 LSB rounding noise.',
            timing_changed=False,prior_files_unchanged=True))
        for name,digest in hashes.items():assert hashlib.sha256((prior/name).read_bytes()).hexdigest()==digest
    (output/'focus-checks.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))


if __name__=='__main__':run(*map(Path,sys.argv[1:]))
