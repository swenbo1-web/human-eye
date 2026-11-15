"""Write one byte-exact snapshot of all final runtime originals without deletion."""

import hashlib
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m5_task_consume_001').resolve()
ARCHIVE = HERE / 'runtime_archive'
ORDER = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3']
REPORTS = ['QUALITY.json', 'QUALITY_SEAL.json', 'DECISION.json', 'RUNTIME_REVIEW.json',
           'COST_CHECKER_REVIEW.json', 'REPORT.md']


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def snapshot():
    paths = []
    for current, names, files in os.walk(RUNTIME, topdown=True, followlinks=False):
        for name in names + files:
            path = Path(current) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError('runtime_reparse_entry')
            path.resolve().relative_to(RUNTIME)
        paths.extend(Path(current) / name for name in files)
    return [(path.relative_to(RUNTIME).as_posix(), path.stat().st_size, sha(path)) for path in sorted(paths)]


def same_bytes(first, second):
    with first.open('rb') as a, second.open('rb') as b:
        while True:
            left, right = a.read(1024 * 1024), b.read(1024 * 1024)
            if left != right:
                return False
            if not left:
                return True


def main():
    if ARCHIVE.exists() or (HERE / 'RUNTIME_ARCHIVE.json').exists():
        raise FileExistsError('runtime_archive_is_write_once')
    for name in REPORTS:
        if not (HERE / name).is_file():
            raise ValueError('final_report_required_' + name)
    review = read(HERE / 'RUNTIME_REVIEW.json')
    run = read(RUNTIME / 'RUN_RESULT.json')
    decision = read(HERE / 'DECISION.json')
    if (review['schema'] != 'm5-task-runtime-review-v1' or review['qualification_only'] is not False
            or type(review['passed_checked_scope']) is not bool
            or review['formal_dispatch'] != run
            or [row['slot_id'] for row in run['records']] != ORDER
            or run['outer_retries'] != 0 or run['replacement_samples'] != 0):
        raise ValueError('complete_original_formal_review_required')
    if review['passed_checked_scope'] is not True and decision['passed_frozen_gates'] is not False:
        raise ValueError('failed_runtime_review_cannot_accept_candidate')
    if (RUNTIME / 'ROOT_OPERATOR_STOP.json').is_file() and decision['passed_frozen_gates'] is not False:
        raise ValueError('operator_stopped_interfered_batch_cannot_accept_candidate')
    before = snapshot()
    if not before:
        raise ValueError('runtime_originals_required')
    ARCHIVE.mkdir()
    rows = []
    for index, (relative, expected_size, expected_sha) in enumerate(before, 1):
        original = RUNTIME / relative
        target = ARCHIVE / ('f' + str(index).zfill(6) + '_' + original.name[:110])
        actual, size = hashlib.sha256(), 0
        with original.open('rb') as incoming, target.open('xb') as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                outgoing.write(block)
                actual.update(block)
                size += len(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if size != expected_size or actual.hexdigest() != expected_sha or not same_bytes(original, target):
            raise ValueError('archive_original_bytes_changed_' + relative)
        rows.append({'original_path': str(original), 'relative_path': relative,
            'archive_path': target.relative_to(HERE).as_posix(), 'bytes': size, 'sha256': expected_sha})
    if snapshot() != before:
        raise ValueError('runtime_changed_during_snapshot')
    output = {'schema': 'm5-task-consumption-runtime-archive-v1', 'runtime_root': str(RUNTIME),
        'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows), 'files': rows,
        'all_copies_verified_byte_exact': True, 'original_runtime_retained': True, 'runtime_exclusions': [],
        'runtime_review_passed_checked_scope': review['passed_checked_scope'],
        'report_pins': {name: sha(HERE / name) for name in REPORTS},
        'scope': 'All original runtime bytes, including failed and partial records. Static bytes do not independently prove process closure. Original terminal/unknown states remain in the runtime review.',
        'new_Blender_raster_model_paid_calls': 0}
    with (HERE / 'RUNTIME_ARCHIVE.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(output, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'files': len(rows), 'bytes': output['bytes'], 'byte_exact': True}))


if __name__ == '__main__':
    main()
