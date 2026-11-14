"""Copy the closed single-slot runtime without changing its original evidence."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_consume_001').resolve()
DESTINATION = HERE / 'external_archive'
INDEX = HERE / 'EXTERNAL_ARCHIVE.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot():
    rows = []
    for path in sorted(RUNTIME.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'unexpected_runtime_symlink: {path}')
        if not path.is_file():
            continue
        resolved = path.resolve()
        resolved.relative_to(RUNTIME)
        data = resolved.read_bytes()
        rows.append((resolved, len(data), digest(data)))
    return rows


def main():
    if not (HERE / 'FORMAL_PROCESS.json').is_file():
        raise ValueError('closed_parent_receipt_required')
    if not (RUNTIME / 'formal/RUN_RESULT.json').is_file():
        raise ValueError('original_single_route_record_required')
    if DESTINATION.exists() or INDEX.exists():
        raise FileExistsError('archive_is_write_once')
    before = snapshot()
    DESTINATION.mkdir()
    records = []
    for number, (source, size, expected) in enumerate(before, 1):
        destination = DESTINATION / f'f{number:05d}_{source.name[:110]}'
        data = source.read_bytes()
        if len(data) != size or digest(data) != expected:
            raise ValueError(f'runtime_changed_during_archive: {source}')
        with destination.open('xb') as stream:
            stream.write(data)
        if destination.read_bytes() != data:
            raise ValueError(f'archive_copy_mismatch: {source}')
        records.append({
            'original_path': str(source),
            'original_relative_path': source.relative_to(RUNTIME).as_posix(),
            'archive_path': destination.relative_to(HERE).as_posix(),
            'bytes': size,
            'sha256': expected,
        })
    if snapshot() != before:
        raise ValueError('runtime_file_set_changed_during_archive')
    result = {
        'schema': 'consumable-observation-runtime-archive-v1',
        'runtime_root': str(RUNTIME),
        'files': records,
        'file_count': len(records),
        'bytes': sum(row['bytes'] for row in records),
        'all_copies_verified_byte_exact': True,
        'original_runtime_retained': True,
        'slot_count': 1,
        'outer_retries': 0,
    }
    with INDEX.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'file_count': result['file_count'], 'bytes': result['bytes'],
                      'index_sha256': digest(INDEX.read_bytes())}))


if __name__ == '__main__':
    main()
