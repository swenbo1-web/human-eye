"""Archive the closed recovery originals without changing either owned run."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
RUN = Path('D:/he_perf050_dense_micro_surface_holdout_recovery_001')
SECRET = re.compile(rb'(?i)\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{30,}|ghp_[A-Za-z0-9]{36}|'
                    rb'github_pat_[A-Za-z0-9_]{40,}|Bearer [A-Za-z0-9._~-]{24,}|'
                    rb'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{10,})\b')
PRIVATE_NAMES = {'auth.json','credentials.json','.env','id_ed25519','id_rsa','.gitconfig'}


def digest(data):
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def write(path,data):
    with path.open('xb') as handle:
        handle.write((json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode())


def check_named_bytes(name, data):
    if any(part.casefold() in PRIVATE_NAMES for part in Path(name).parts) or SECRET.search(data):
        raise ValueError(f'private_material_in_publishable_originals/{name}')
    if name.endswith('.zip'):
        from io import BytesIO
        with ZipFile(BytesIO(data)) as bundle:
            for item in bundle.infolist():
                if not item.is_dir():
                    check_named_bytes(item.filename,bundle.read(item))


def archive(extra):
    freeze = NS/'FROZEN.json'
    token = digest(freeze.read_bytes())['sha256']
    for row in read(freeze)['direct_inputs']:
        assert digest(Path(row['path']).read_bytes())=={k:row[k] for k in ('sha256','bytes')},row['path']
    journal = RUN/'preflight/FORMAL_SEQUENCE.jsonl'
    (NS/'evidence'/'FORMAL_SEQUENCE.jsonl').write_bytes(journal.read_bytes())
    planned = read(freeze)['slots']
    status = {}
    for label in planned:
        slot = RUN/'slots'/label
        if not slot.exists():
            status[label]={'owned':'unrun','model_consumers':0}
            continue
        r, p = slot/'SLOT_RESULT.json',slot/'SLOT_PUBLICATION.json'
        availability = {'started':(slot/'SLOT_STARTED.json').is_file(),'result':r.is_file(),'publication':p.is_file()}
        if not all(availability.values()):
            status[label]={'owned':'unconfirmed','evidence':availability,'model_consumers':None}
            continue
        source, publication = read(r),read(p)
        assert source['freeze_sha256']==token and publication['result_sha256']==digest(r.read_bytes())['sha256']
        assert source['paid_API_calls']==0
        for path in (r,p):
            (NS/'evidence'/f'{label}_{path.name}').write_bytes(path.read_bytes())
        status[label]={'owned':publication['status'],'model_consumers':source['model_consumers'],
            'safe_closed':(source.get('closure_verification') or {}).get('passed') is True,
            'complete_slot_ns':publication['complete_slot_ns'],'result_sha256':publication['result_sha256']}
    sources={'runtime':RUN}
    for raw in extra:
        path = Path(raw).resolve(strict=True)
        sources[path.name]=path
    indexed={}
    entries=[]
    for key, folder in sources.items():
        for path in sorted(folder.rglob('*')):
            if not path.is_file():
                continue
            name=key+'/'+path.relative_to(folder).as_posix()
            data=path.read_bytes()
            check_named_bytes(name,data)
            indexed[name]=digest(data)
            entries.append((name,path))
    target=NS/'ORIGINAL_RUNTIME.zip'
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=6) as bundle:
        for name,path in entries:
            data=path.read_bytes()
            assert digest(data)==indexed[name],name
            bundle.writestr(name,data)
    with ZipFile(target) as bundle:
        assert set(bundle.namelist())==set(indexed)
        assert all(digest(bundle.read(name))==row for name,row in indexed.items())
    write(NS/'RAW_INDEX.json',{'freeze_sha256':token,'archive':{'name':target.name,**digest(target.read_bytes())},
             'member_count':len(indexed),'slots':status,'original_QN_reused':True,'members':indexed})
    print('Verified',len(indexed),'archived original members',digest(target.read_bytes()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('preflight_directories',nargs='*')
    archive(parser.parse_args().preflight_directories)
