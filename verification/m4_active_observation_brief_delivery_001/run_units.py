"""Run directly affected tests with real raster construction forbidden."""

import argparse
from contextlib import ExitStack
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch


MODULES = (
    'verification.test_active_observation_brief',
    'verification.test_active_observation_service',
    'verification.test_live_spatial_mcp',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    sys.path.insert(0, str(args.repo.resolve()))
    started = time.perf_counter_ns()
    children = []
    forbidden_calls = []
    original_popen = subprocess.Popen

    def popen(command, *positional, **keywords):
        executable = command[0] if isinstance(command, (list, tuple)) else command
        if Path(executable).name.lower().startswith('blender'):
            forbidden_calls.append({'kind': 'Blender', 'command': str(command)})
            raise AssertionError('No Blender process is allowed in this unit batch')
        process = original_popen(command, *positional, **keywords)
        children.append((process, command))
        return process

    def no_raster(*args, **kwargs):
        forbidden_calls.append({'kind': 'real_raster'})
        raise AssertionError('No real raster is allowed in this unit batch')

    with ExitStack() as stack:
        stack.enter_context(patch('subprocess.Popen', side_effect=popen))
        for target in ('human_eye_plugin.attention_raster.rasterize_attention',
                       'human_eye_plugin.attention_rendering.rasterize_attention',
                       'human_eye_plugin.active_observation_images.rasterize_attention'):
            stack.enter_context(patch(target, side_effect=no_raster))
        suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    child_rows = [{'pid': process.pid, 'command': command, 'exit_code': process.poll()}
                  for process, command in children]
    receipt = {'schema': 'm4-active-brief-unit-result-v1',
               'passed': result.wasSuccessful() and not forbidden_calls
                         and all(row['exit_code'] is not None for row in child_rows),
               'modules': list(MODULES), 'run': result.testsRun,
               'failures': [name.id() for name, _ in result.failures],
               'errors': [name.id() for name, _ in result.errors],
               'forbidden_calls': forbidden_calls, 'real_rasters': 0,
               'Blender_processes': 0, 'Python_test_children': child_rows,
               'started_ns': started, 'closed_before_publication_ns': time.perf_counter_ns()}
    with (args.output / 'UNIT_TESTS.txt').open('x', encoding='utf-8') as log:
        log.write(stream.getvalue())
    with (args.output / 'UNIT_RESULT.json').open('x', encoding='utf-8') as log:
        json.dump(receipt, log, sort_keys=True, indent=2)
        log.write('\n')
    print(json.dumps(receipt))
    if not receipt['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
