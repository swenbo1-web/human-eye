"""Archive the six closed camera controls and their original runtime bytes."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_camera_001').resolve()
ARCHIVE = HERE / 'runtime_archive'
SLOTS = ('OLD_extreme', 'NEW_extreme', 'OLD_origin', 'NEW_origin',
         'OLD_peripheral', 'NEW_peripheral')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot():
    rows = []
    for path in sorted(RUNTIME.rglob('*')):
        if path.is_symlink():
            raise ValueError('unexpected_runtime_symlink')
        if path.is_file():
            path.resolve().relative_to(RUNTIME)
            if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
                raise ValueError('unexpected_bytecode_requires_explicit_archive_decision')
            data = path.read_bytes()
            rows.append((path, len(data), digest(data)))
    return rows


def main():
    for name in SLOTS:
        result = json.loads((RUNTIME / 'controls' / name / 'RESULT.json').read_bytes())
        if (result['passed'] is not True or result['errors']
                or not result['MCP_runtime_exit']['confirmed']
                or result['MCP_runtime_exit']['exit_code'] != 0
                or result['native_close']['exit_code'] != 0
                or not result['native_close']['process_reaped']):
            raise ValueError('closed_control_required_' + name)
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
        raise ValueError('runtime_changed_during_archive')
    result = dict(schema='m4-target-camera-runtime-archive-v1', runtime_root=str(RUNTIME),
                  files=records, file_count=len(records), bytes=sum(row['bytes'] for row in records),
                  all_copies_verified_byte_exact=True, original_runtime_retained=True,
                  excluded_files=[], all_six_controls_closed=True)
    with (HERE / 'RUNTIME_ARCHIVE.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(files=len(records), bytes=result['bytes'])))


if __name__ == '__main__':
    main()
