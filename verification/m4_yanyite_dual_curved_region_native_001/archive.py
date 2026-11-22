"""Seal the original owned captures and delivery evidence without moving them."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZIP_DEFLATED, ZipFile


NS = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_m4_yanyite_dual_curved_region_native_001').resolve()


def digest(data):
    return {'bytes':len(data),'sha256':sha256(data).hexdigest()}


def write(path,value):
    with path.open('x',encoding='utf8',newline='\n') as out:
        json.dump(value,out,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        out.write('\n')


def seal():
    freeze = NS/'FROZEN.json'
    freeze_hash = digest(freeze.read_bytes())['sha256'] if freeze.is_file() else None
    prior = NS.parent/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'
    inspect = run_path(str(prior))['check_named_bytes']
    sealed = EXTERNAL/'sealed'
    sealed.mkdir(exist_ok=False)
    target = sealed/'ORIGINAL_RUNTIME.zip'
    members = {}
    files = sorted(path for path in EXTERNAL.rglob('*') if path.is_file() and not path.is_relative_to(sealed))
    with ZipFile(target,'x',compression=ZIP_DEFLATED,compresslevel=5) as archive:
        for path in files:
            key = 'runtime/'+path.relative_to(EXTERNAL).as_posix()
            raw = path.read_bytes()
            inspect(key,raw)
            members[key] = digest(raw)
            archive.writestr(key,raw)
    with ZipFile(target) as packed:
        if len(packed.namelist()) != len(members) or set(packed.namelist()) != members.keys():
            raise ValueError('private_evidence_archive_member_roster_changed')
        for key,receipt in members.items():
            if digest(packed.read(key)) != receipt:
                raise ValueError('private_evidence_archive_source_changed/'+key)
    record = {'freeze_sha256':freeze_hash,'file':str(target),'sealed_unmodified_raw_members':len(members),
              'archive':digest(target.read_bytes())}
    write(sealed/'RAW_INDEX.json',{**record,'members':members})
    print(json.dumps(record,ensure_ascii=False),flush=True)


if __name__=='__main__':
    seal()
