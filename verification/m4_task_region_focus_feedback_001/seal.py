"""Seal the private holdout activity exactly once. Only the receipt is publishable."""
import argparse
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
from stat import FILE_ATTRIBUTE_REPARSE_POINT
from zipfile import ZipFile, ZIP_DEFLATED

BATCH = 'M4-TASK-REGION-FOCUS-FEEDBACK-001'
ADMIN_SHA = '6f4baec050d258f8f934dfdb23350610c132a53ffc00047c7ed1068d4a08ea28'
OMIT = {'.git', '.ssh', '.env', 'auth.json', 'credentials.json', 'id_rsa', 'id_ed25519', 'sealed'}


def digest(path):
    with path.open('rb') as source:
        return file_digest(source,'sha256').hexdigest()


def ordinary(path):
    flags=getattr(path.lstat(),'st_file_attributes',0)
    return not path.is_symlink() and not flags & FILE_ATTRIBUTE_REPARSE_POINT


def private_inputs(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent=Path(directory)
        dirs[:]=sorted(x for x in dirs if x.casefold() not in OMIT and ordinary(parent/x))
        for name in sorted(files):
            path=parent/name
            if name.casefold() not in OMIT and ordinary(path) and path.is_file():
                yield path


def seal(root):
    root=root.resolve(strict=True)
    if root.name!=BATCH or digest(root/'preflight/ADMIN_PLAN.md')!=ADMIN_SHA:
        raise ValueError('registered_task_feedback_only')
    files=list(private_inputs(root))
    destination=root/'sealed'
    destination.mkdir(exist_ok=False)
    bundle=destination/'ORIGINAL_RUNTIME.zip'
    manifest={}
    with ZipFile(bundle,'x',compression=ZIP_DEFLATED,compresslevel=6) as z:
        for path in files:
            name=path.relative_to(root).as_posix()
            raw=path.read_bytes()
            if name in manifest:
                raise ValueError('duplicate_member')
            z.writestr(name,raw)
            manifest[name]={'bytes':len(raw),'sha256':sha256(raw).hexdigest()}
    with ZipFile(bundle) as z:
        if z.testzip() is not None or set(z.namelist())!=set(manifest):
            raise ValueError('sealed_members_integrity')
        for name,pin in manifest.items():
            raw=z.read(name)
            if raw!=(root/name).read_bytes() or len(raw)!=pin['bytes'] or sha256(raw).hexdigest()!=pin['sha256']:
                raise ValueError('sealed_member_changed/'+name)
    index=destination/'RAW_INDEX.json'
    with index.open('x',encoding='utf8',newline='\n') as out:
        json.dump({'archive':{'bytes':bundle.stat().st_size,'sha256':digest(bundle)},
                   'member_count':len(manifest),'members':manifest},out,sort_keys=True,indent=2)
        out.write('\n')
    print(json.dumps({'archive_sha256':digest(bundle),'index_sha256':digest(index),'members':len(manifest)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_root',type=Path)
    seal(p.parse_args().run_root)
