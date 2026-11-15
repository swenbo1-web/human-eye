"""Freeze the complete CLI and saved-scoring closure before any consumer."""

import argparse
import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve()
    blob = path.read_bytes()
    return {'path': str(path), 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}


def check(row):
    current = pin(row['path'])
    if current['sha256'] != row['sha256'] or ('bytes' in row and current['bytes'] != row['bytes']):
        raise ValueError('frozen_input_changed/' + row['path'])
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scorer-ready', type=Path, required=True)
    parser.add_argument('--cli-closure', type=Path, required=True)
    args = parser.parse_args()
    files = {}
    previous = read(HERE / 'QUALIFICATION_FREEZE.json')
    for row in previous['files']:
        current = check(row)
        files[current['path']] = current
    for document in (args.scorer_ready, args.cli_closure):
        closure = read(document)
        rows = closure.get('source_pins', closure.get('source_files', []))
        if not rows:
            raise ValueError('nonempty_source_closure_required/' + str(document))
        for row in rows:
            current = check(row)
            files[current['path']] = current
        files[str(document.resolve())] = pin(document)
    contract = read(HERE / 'admin/SCORING_CONTRACT.json')
    for path, digest in contract['files_sha256'].items():
        current = check({'path': path, 'sha256': digest})
        files[current['path']] = current
    for name in ('admin/QUALIFICATION.json', 'QUALIFICATION_RUNTIME_REVIEW.json'):
        if read(HERE / name)['passed_checked_scope'] is not True:
            raise ValueError('actual_qualification_required/' + name)
    for name in ('QUALIFICATION_FREEZE.json', 'admin/QUALIFICATION.json',
                 'QUALIFICATION_RUNTIME_REVIEW.json', 'BRIDGE_READY.json',
                 'harness/HARNESS_READY.json', 'freeze_formal.py'):
        row = pin(HERE / name)
        files[row['path']] = row
    result = {'schema': 'm5-task-consumption-formal-freeze-v1',
              'frozen_ns': time.perf_counter_ns(), 'files': [files[name] for name in sorted(files)],
              'scope': 'Original qualification execution inputs plus current transitive CLI code, independent scoring contract and complete saved-format implementation. No consumer started at publication.',
              'formal_batch_attempts': 1, 'outer_retries': 0, 'replacement_samples': 0}
    with (HERE / 'FROZEN.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'pinned_files': len(files), 'freeze_sha256': pin(HERE / 'FROZEN.json')['sha256']}))


if __name__ == '__main__':
    main()
