"""Seal this run's original private evidence for local custody only."""

from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
from stat import FILE_ATTRIBUTE_REPARSE_POINT
from zipfile import ZIP_DEFLATED, ZipFile

RUN = Path('D:/he_m4_source_region_visual_scope_proof_001')
EXCLUDE = frozenset(('sealed', '.git', '.ssh', '.env', 'auth.json', 'credentials.json', 'id_rsa', 'id_ed25519'))


def ordinary(path):
    flags = getattr(path.lstat(), 'st_file_attributes', 0)
    return not path.is_symlink() and not flags & FILE_ATTRIBUTE_REPARSE_POINT


def read_pin(path):
    with path.open('rb') as stream:
        value = file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes':path.stat().st_size, 'sha256':value}


def source_files(root):
    for folder, directories, files in os.walk(root, followlinks=False):
        directory = Path(folder)
        directories[:] = sorted(name for name in directories
                                if name.casefold() not in EXCLUDE and ordinary(directory/name))
        for name in sorted(files):
            path = directory/name
            if name.casefold() not in EXCLUDE and ordinary(path) and path.is_file():
                yield path


def seal():
    assert RUN.is_dir() and RUN == RUN.resolve()
    files = list(source_files(RUN))
    assert files and all(RUN/name in files for name in ('cases/main/RUN_RESULT.json', 'cases/yanyite/RUN_RESULT.json', 'AUXILIARY.json', 'CONTROLS.json'))
    root = RUN/'sealed'
    root.mkdir(exist_ok=False)
    bundle = root/'ORIGINAL_RUNTIME.zip'
    index = {}
    with ZipFile(bundle,'x',compression=ZIP_DEFLATED,compresslevel=6) as archive:
        for path in files:
            name = path.relative_to(RUN).as_posix()
            assert name not in index
            data = path.read_bytes()
            index[name] = {'bytes':len(data),'sha256':sha256(data).hexdigest()}
            archive.writestr(name,data)
    with ZipFile(bundle) as archive:
        assert archive.testzip() is None and sorted(archive.namelist()) == sorted(index)
        for name,row in index.items():
            data = archive.read(name)
            assert sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes']
            assert (RUN/name).read_bytes() == data
    result = {'archive':read_pin(bundle),'member_count':len(index),'members':index,
              'scope':'local private custody; visited regular files only; no publication of payloads'}
    with (root/'RAW_INDEX.json').open('x',encoding='utf8',newline='\n') as out:
        json.dump(result,out,ensure_ascii=False,indent=2,sort_keys=True)
        out.write('\n')
    print({'archive':result['archive'],'members':len(index),'index':read_pin(root/'RAW_INDEX.json')})


if __name__ == '__main__':
    seal()
