"""Preserve the closed, bounded acceptance runtime as byte-exact evidence."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_view_reuse_001/run').resolve()
ARCHIVE = HERE / 'runtime_archive'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot():
    rows = []
    for path in sorted(RUNTIME.rglob('*')):
        if path.is_symlink():
            raise ValueError('unexpected_runtime_symlink')
        if path.is_file():
            path.resolve().relative_to(RUNTIME)
            data = path.read_bytes()
            rows.append((path, len(data), digest(data)))
    return rows


def main():
    for name in ('integration_01/INTEGRATION_RESULT.json', 'benchmark_01/COST_RESULT.json'):
        result = json.loads((RUNTIME / name).read_bytes())
        if result['passed'] is not True:
            raise ValueError('completed_acceptance_required')
    if ARCHIVE.exists() or (HERE / 'RUNTIME_ARCHIVE.json').exists():
        raise FileExistsError('archive_is_write_once')
    before = snapshot()
    ARCHIVE.mkdir()
    records = []
    for number, (source, size, expected) in enumerate(before, 1):
        data = source.read_bytes()
        if len(data) != size or digest(data) != expected:
            raise ValueError('runtime_changed_during_archive')
        target = ARCHIVE / ('f' + str(number).zfill(5) + '_' + source.name[:110])
        with target.open('xb') as stream:
            stream.write(data)
        if target.read_bytes() != data:
            raise ValueError('archive_copy_mismatch')
        records.append(dict(original_path=str(source), relative_path=source.relative_to(RUNTIME).as_posix(),
                            archive_path=target.relative_to(HERE).as_posix(), bytes=size, sha256=expected))
    if snapshot() != before:
        raise ValueError('runtime_file_set_changed_during_archive')
    result = dict(schema='view-reuse-runtime-archive-v1', runtime_root=str(RUNTIME),
                  files=records, file_count=len(records), bytes=sum(row['bytes'] for row in records),
                  all_copies_verified_byte_exact=True, original_runtime_retained=True,
                  product_install_scope='141 installed source files are bound separately to the committed wheel.')
    with (HERE / 'RUNTIME_ARCHIVE.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(files=len(records), bytes=result['bytes'])))


if __name__ == '__main__':
    main()
