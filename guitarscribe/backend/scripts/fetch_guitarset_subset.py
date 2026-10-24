"""Fetch selected official GuitarSet ZIP members using bounded HTTP ranges."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

BASE='https://zenodo.org/records/3371780/files/'
SIZES={'annotation.zip':39132574,'audio_mono-mic.zip':656927981}


class RemoteZip(io.RawIOBase):
    def __init__(self,name):
        self.name=name;self.size=SIZES[name];self.position=0;self.transferred=0
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        self.position=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if self.position<0:raise ValueError('Negative seek')
        return self.position
    def read(self,size=-1):
        size=min(self.size-self.position,size if size>=0 else self.size-self.position)
        if size<=0:return b''
        if size>8_000_000:raise ValueError('Refusing large range; use selected members only')
        first=self.position;last=first+size-1
        request=urllib.request.Request(BASE+self.name+f'?download=1&subset={first}-{last}',headers={'Range':f'bytes={first}-{last}'})
        with urllib.request.urlopen(request,timeout=45) as response:
            if response.status!=206 or response.headers['Content-Range']!=f'bytes {first}-{last}/{self.size}':
                raise ValueError('Server did not honor exact range')
            data=response.read(size+1)
        if len(data)!=size:raise ValueError('Truncated range')
        self.position+=size;self.transferred+=size
        return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ids',nargs='*',default=[])
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    sources=[]
    for archive in SIZES:
        remote=RemoteZip(archive)
        with zipfile.ZipFile(remote) as z:
            names=[n for n in z.namelist() if not n.startswith('__MACOSX/')]
            if not args.ids:
                print(archive,[n for n in names if '_comp' in n][:40]);continue
            for identifier in args.ids:
                basename=identifier+('.jams' if archive=='annotation.zip' else '_mic.wav')
                matches=[n for n in names if Path(n).name==basename]
                if len(matches)!=1:raise ValueError(f'Missing or ambiguous {basename}')
                dest=args.output/basename
                if dest.exists():raise ValueError(f'Preserve existing file: {dest}')
                data=z.read(matches[0]) # ZIP CRC is checked by zipfile.
                dest.write_bytes(data)
                sources.append({'file':basename,'archive_url':BASE+archive,'member':matches[0],
                                'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
                                'crc32':z.getinfo(matches[0]).CRC})
                print('Fetched',basename,len(data),flush=True)
        print('Transferred',archive,remote.transferred,flush=True)
    if args.ids:
        (args.output/'provenance.json').write_text(json.dumps({'source':'GuitarSet v1.1.0, Xi et al., Zenodo 3371780',
            'integrity':'Exact HTTP ranges, per-member ZIP CRC and local SHA256; full archive MD5 not verified.',
            'files':sources},indent=2))


if __name__=='__main__':main()
