"""Byte-exact, write-once archive of this recovery chain's runtime originals."""

import hashlib
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m5_harness_recovery_001').resolve()
ARCHIVE = HERE / 'runtime_archive'
REPORTS = ('QUALIFICATION.json', 'RUNTIME_REVIEW.json', 'DECISION.json', 'REPORT.md')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def snapshot():
    result = []
    for directory, names, files in os.walk(RUNTIME, topdown=True, followlinks=False):
        for name in names + files:
            path = Path(directory) / name
            if path.is_symlink() or path.is_junction():
                raise ValueError('runtime_reparse_entry')
            path.resolve().relative_to(RUNTIME)
        result.extend(Path(directory) / name for name in files)
    return [(path.relative_to(RUNTIME).as_posix(), path.stat().st_size, sha(path)) for path in sorted(result)]


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
        raise FileExistsError('runtime_archive_write_once')
    for name in REPORTS:
        if not (HERE / name).is_file():
            raise ValueError('final_report_required_' + name)
    qualification = read(HERE / 'QUALIFICATION.json')
    review = read(HERE / 'RUNTIME_REVIEW.json')
    decision = read(HERE / 'DECISION.json')
    if (qualification['schema'] != 'm5-harness-recovery-independent-qualification-v1'
            or qualification['denominator'] != 2 or [row['group'] for row in qualification['records']] != ['A', 'B']
            or review['schema'] != 'm5-harness-recovery-runtime-review-v1'
            or [row['group'] for row in review['sessions']] != ['A', 'B']):
        raise ValueError('complete_two_session_reviews_required')
    if ((qualification['passed_checked_scope'] is not True or review['passed_checked_scope'] is not True)
            and decision['accepted_harness_recovery'] is not False):
        raise ValueError('failed_review_cannot_accept_recovery')
    if decision['product_or_model_benefit_claim'] is not False:
        raise ValueError('recovery_scope_only')
    before = snapshot()
    if not before:
        raise ValueError('runtime_originals_required')
    ARCHIVE.mkdir()
    rows = []
    for index, (relative, expected_size, expected_sha) in enumerate(before, 1):
        original = RUNTIME / relative
        target = ARCHIVE / ('f' + str(index).zfill(6) + '_' + original.name[:110])
        actual, size = hashlib.sha256(), 0
        with original.open('rb') as source, target.open('xb') as output:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                output.write(block)
                actual.update(block)
                size += len(block)
            output.flush()
            os.fsync(output.fileno())
        if size != expected_size or actual.hexdigest() != expected_sha or not same_bytes(original, target):
            raise ValueError('archive_byte_identity_changed_' + relative)
        rows.append({'relative_path': relative, 'original_path': str(original),
            'archive_path': target.relative_to(HERE).as_posix(), 'bytes': size, 'sha256': expected_sha})
    if snapshot() != before:
        raise ValueError('runtime_changed_during_archive')
    result = {'schema': 'm5-harness-recovery-runtime-archive-v1', 'runtime_root': str(RUNTIME),
        'files': rows, 'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows),
        'original_runtime_retained': True, 'runtime_exclusions': [], 'all_copies_verified_byte_exact': True,
        'report_pins': {name: sha(HERE / name) for name in REPORTS},
        'scope': 'All original bytes for the two recovery sessions, including errors and any bytecode. Process closure remains a separately reviewed fact.',
        'new_actual_operations': 0}
    with (HERE / 'RUNTIME_ARCHIVE.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'files': len(rows), 'bytes': result['bytes'], 'byte_exact': True}))


if __name__ == '__main__':
    main()
