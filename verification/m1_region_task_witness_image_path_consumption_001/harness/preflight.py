"""Offline dispatch, catalogue and mocked held-close qualification; no live work."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (EXTERNAL, HERE, NS, ORDER, PRODUCT, SOURCE_SHA, catalogue_for,
                    evidence_enabled, product_for, read, save)


def close_checks():
    import runtime

    cases = []
    for mutation in ('none', 'missing_stdout_eof', 'wrong_source', 'os_exit_one',
                     'unconsumed_reply', 'missing_worker_exit', 'input_not_eof'):
        with tempfile.TemporaryDirectory(prefix='region-task-offline-close-') as directory:
            root = Path(directory)
            evidence = root / 'evidence'
            evidence.mkdir()
            output = root / 'output'
            output.mkdir()
            eof = {'pid': 12345, 'source_sha256': SOURCE_SHA, 'closed': True,
                   'host_close_called': True, 'input_eof_observed': True}
            exited = {'pid': 12345, 'source_sha256': SOURCE_SHA, 'input_eof_observed': True,
                      'production_returned': True, 'production_return_code': 0,
                      'service_constructed': True, 'installed_source_verified': True}
            original = {'confirmed': True, 'exit_code': 0, 'errors': []}
            if mutation == 'wrong_source':
                exited['source_sha256'] = '0' * 64
            if mutation == 'os_exit_one':
                original.update(confirmed=False, exit_code=1)
            if mutation == 'input_not_eof':
                eof['input_eof_observed'] = False
            save(evidence / 'EOF.json', eof)
            if mutation != 'missing_worker_exit':
                save(evidence / 'WORKER_EXIT.json', exited)
            child = object.__new__(runtime.ProductionStdioClient)
            child.worker_evidence, child.output = evidence, output
            child._production_close = None
            child.expected_source_sha256 = SOURCE_SHA
            child.process = SimpleNamespace(pid=12345)
            child.events, child.records = queue.Queue(), []
            if mutation != 'missing_stdout_eof':
                child.events.put(('eof', None, 1))
            if mutation == 'unconsumed_reply':
                child.events.put(('reply', b'{}', 1))
            with patch.object(runtime.transport.StdioClient, 'finish', return_value=deepcopy(original)):
                result = child.finish()
                repeated = child.finish()
            passed = result['confirmed'] is (mutation == 'none') and repeated is result
            cases.append({'case': mutation, 'passed': passed,
                          'observed_confirmed': result['confirmed'], 'expected_confirmed': mutation == 'none'})
    return cases


def main():
    path = HERE / 'HOST_PREFLIGHT.json'
    if path.exists():
        raise FileExistsError('offline_preflight_first_result_already_present')
    output = EXTERNAL / 'offline_preflight_01'
    output.mkdir(parents=True, exist_ok=False)
    rows = {}
    for label in ORDER:
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'run_slot.py'), label, '--dispatch-smoke']
        call = subprocess.run(command, cwd=NS.parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=30)
        (output / (label + '_stdout.bin')).write_bytes(call.stdout)
        (output / (label + '_stderr.bin')).write_bytes(call.stderr)
        row = {'command': command, 'exit_code': call.returncode,
               'stdout_sha256': hashlib.sha256(call.stdout).hexdigest(),
               'stderr_sha256': hashlib.sha256(call.stderr).hexdigest()}
        if call.returncode == 0:
            row['dispatch'] = json.loads(call.stdout)
        rows[label] = row
    expected_tools = ['execute_blender_code', 'execute_python', 'human_eye_scene_observe',
                      'read_images', 'render_local', 'render_views']
    dispatch_passed = all(
        row['exit_code'] == 0 and row['dispatch']['slot'] == label
        and row['dispatch']['product'] == product_for(label) and row['dispatch']['group'] == 'P'
        and row['dispatch']['tools'] == sorted(expected_tools)
        and row['dispatch']['run_root'] == str(EXTERNAL.resolve())
        and row['dispatch']['endpoint_flag'] == ('--region-task-evidence' if evidence_enabled(label) else None)
        and Path(row['dispatch']['actual_catalogue_path']) == catalogue_for(label).resolve()
        for label, row in rows.items())
    standard, evidence = read(catalogue_for('QA')), read(catalogue_for('QB'))
    normalized = deepcopy(evidence)
    differences = []
    for left, right in zip(standard, normalized):
        if left != right:
            differences.append({'name': left.get('name'),
                                'UTF8_description_increment': len(right['description'].encode('utf8'))
                                    - len(left['description'].encode('utf8'))})
            right['description'] = left['description']
    catalogue_passed = standard == normalized and differences == []
    mocked = close_checks()
    result = {'schema': 'region-task-witness-path-consumption-offline-host-v1',
              'passed': dispatch_passed and catalogue_passed and all(row['passed'] for row in mocked),
              'fresh_dispatch': rows, 'catalogue_passed': catalogue_passed,
              'catalogue_differences': differences, 'mocked_held_close': mocked,
              'actual_work': {'dispatch_subprocesses': len(rows), 'mocked_close_cases': len(mocked),
                              'Blender_processes': 0, 'live_product_processes': 0,
                              'product_business_calls': 0, 'rasters': 0, 'model_consumers': 0},
              'scope': 'Dispatch imports plus mocked held-close predicates only; actual production/host/EOF/PNG qualification remains untested.'}
    save(path, result)
    print(json.dumps({'passed': result['passed'], 'dispatches': len(rows),
                      'mocked_close_cases': len(mocked), 'path': str(path)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
