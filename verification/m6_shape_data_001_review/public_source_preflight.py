"""Acquire two official research sources for the next bounded trial, no scoring."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time
import urllib.request

HERE=Path(__file__).resolve().parent
PRIVATE=HERE/'private/public_sources'
PRIVATE.mkdir(parents=True,exist_ok=True)
sources=[('Stanford_Armadillo','https://graphics.stanford.edu/pub/3Dscanrep/armadillo/Armadillo.ply.gz',None,'validation'),
         ('Stanford_Bunny','https://graphics.stanford.edu/pub/3Dscanrep/bunny.tar.gz','bunny/reconstruction/bun_zipper.ply','reserved_test')]
result={'catalog_url':'https://graphics.stanford.edu/data/3Dscanrep/','usage':'Local research evaluation only; Stanford Computer Graphics Laboratory attribution; no product distribution or production activation.','selection_before_training':True,'sources':[]}
def record(p):
    data=p.read_bytes()
    return {'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
for name,url,member,purpose in sources:
    started=time.perf_counter(); package=PRIVATE/url.rsplit('/',1)[1]
    if not package.exists():
        with urllib.request.urlopen(url,timeout=40) as response:
            data=response.read(12*1024*1024+1)
            assert len(data)<=12*1024*1024
            package.write_bytes(data)
    raw=gzip.decompress(package.read_bytes())
    if member:
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
            entry=archive.getmember(member)
            assert entry.isfile()
            raw=archive.extractfile(entry).read()
    ply=PRIVATE/(name+'.ply')
    if ply.exists(): assert ply.read_bytes()==raw
    else: ply.write_bytes(raw)
    at=raw.index(b'end_header')
    header=raw[:at+len(b'end_header')].decode('ascii')
    result['sources'].append({'name':name,'url':url,'purpose':purpose,'archive':record(package),'ply':record(ply),'archive_member':member,'header':header,'preflight_wall_s':time.perf_counter()-started,'unit':'Not established by the download header; preserve native units and report normalized length, do not label physical millimetres without evidence.','scope':'Metadata/bytes only; no patch or target quality inspected.'})
(HERE/'PUBLIC_SOURCE_PREFLIGHT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(result))
