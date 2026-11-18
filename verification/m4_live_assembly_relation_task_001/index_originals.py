"""Index immutable local runtime evidence and verify the compressed copy."""

import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from common import EXTERNAL, save, sha


def inventory():
    paths = []
    for part in ('slots', 'budget', 'preflight'):
        root = EXTERNAL / part
        for path in root.rglob('*'):
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('unexpected_evidence_reparse_point')
            if path.is_file():
                paths.append(path)
    return sorted(paths)


def main():
    began = time.perf_counter_ns()
    paths = inventory()
    rows = [{'path': path.relative_to(EXTERNAL).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in paths]
    target = EXTERNAL / 'ORIGINAL_RUNTIME.zip'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
        for path, row in zip(paths, rows, strict=True):
            archive.write(path, row['path'])
    with zipfile.ZipFile(target, 'r') as archive:
        if archive.namelist() != [row['path'] for row in rows]:
            raise ValueError('runtime_archive_members_changed')
        for path, row in zip(paths, rows, strict=True):
            with archive.open(row['path']) as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != row['sha256'] or sha(path) != actual or path.stat().st_size != row['bytes']:
                raise ValueError('runtime_archive_or_original_bytes_changed/' + row['path'])
    if paths != inventory():
        raise ValueError('runtime_inventory_changed_during_archive')
    index = {'schema': 'm4-live-source-region-runtime-index-v1', 'started_ns': began,
             'closed_ns': time.perf_counter_ns(), 'local_root': str(EXTERNAL), 'file_count': len(rows),
             'original_bytes': sum(row['bytes'] for row in rows), 'original_files_deleted': 0,
             'archive': {'path': str(target), 'bytes': target.stat().st_size, 'sha256': sha(target)},
             'publication_scope': 'The repository contains the original byte identities and public answer. The local archive holds exact runtime bytes, including private asset copies, geometry and raw process events.',
             'files': rows}
    save(NS / 'RUNTIME_INDEX.json', index)
    print(json.dumps({key: index[key] for key in ('file_count', 'original_bytes', 'archive')}))


if __name__ == '__main__':
    main()
