"""Run the same direct task unittest against one installed product."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time


REPO = Path(__file__).resolve().parents[3]
TEST = ('verification.m3_whole_object_rounded_witness_compat_001.regression.'
        'test_closed_relation_point.ClosedRelationPointTests')
DRIVER = """
import sys
import unittest

sys.path[:0] = sys.argv[1:4]
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(sys.argv[4]))
sys.exit(not result.wasSuccessful())
"""


def run(binding_file, output, *, expect_defect=False):
    data = binding_file.read_bytes()
    binding = json.loads(data)
    product = Path(binding['install_root']).resolve(strict=True)
    paths = {'human_eye_plugin/surface_proximity.py', 'human_eye_plugin/surface_geometry.py',
             'human_eye_plugin/task_query.py', 'human_eye_plugin/live_service.py'}
    manifest = {row['path']: row['sha256'] for row in binding['source_manifest']}
    for path in sorted(paths):
        if sha256((product / path).read_bytes()).hexdigest() != manifest[path]:
            raise ValueError(f'Installed source mismatch: {path}')

    output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, '-IB', '-X', 'utf8', '-c', DRIVER, str(product),
               binding['dependency_root'], str(REPO), TEST]
    start = time.perf_counter_ns()
    proc = subprocess.run(command, cwd=REPO, capture_output=True, timeout=60, check=False)
    elapsed_ns = time.perf_counter_ns() - start
    logs = {'STDOUT.bin': proc.stdout, 'STDERR.bin': proc.stderr}
    for name, raw in logs.items():
        (output / name).write_bytes(raw)
    stderr = proc.stderr.decode('utf8')
    failures = [line for line in stderr.splitlines() if line.startswith('FAIL:')]
    known = 'AssertionError: 2 != 3 : [[1.0, 0.4375, 0.25], [1.0, 0.4375, 0.25]]'
    expected = ((proc.returncode == 1 and len(failures) == 5 and stderr.count(known) == 5)
                if expect_defect else (proc.returncode == 0 and not failures))
    passed = expected and 'Ran 2 tests' in stderr and '\nERROR:' not in stderr
    result = {'passed_expected_outcome': passed, 'expect_defect': expect_defect,
              'returncode': proc.returncode, 'failing_subtests': failures, 'elapsed_ns': elapsed_ns,
              'preparation_git': binding['preparation_git'],
              'source_sha256': binding['source_sha256'],
              'binding_sha256': sha256(data).hexdigest(), 'interpreter': sys.executable,
              'verified_sources': {path: manifest[path] for path in sorted(paths)},
              'logs': {name: {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
                       for name, raw in logs.items()}}
    (output / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8', newline='\n')
    if not passed:
        raise SystemExit(f'Unexpected outcome: {output}')
    print(f'Direct task regression expectation confirmed: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-defect', action='store_true')
    args = parser.parse_args()
    run(args.binding, args.output, expect_defect=args.expect_defect)
