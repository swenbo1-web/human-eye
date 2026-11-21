"""Recheck the existing sample-path contract and paired legacy unit results."""

import base64
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys


NS = Path(__file__).resolve().parents[1]
V = NS.parent
PREVIOUS = V / 'm4_source_region_blocker_producer_reuse_001'
BINDINGS = {'A': PREVIOUS / 'install/PRODUCT_RUN_BINDING.json',
            'B': NS / 'install/PRODUCT_RUN_BINDING.json'}


def read(path):
    return json.loads(path.read_bytes())


def require(condition, error):
    if not condition:
        raise ValueError(error)


def unit_worker(binding):
    import unittest

    record = read(binding)
    sys.path[:0] = [record['install_root'], record['dependency_root'], str(V.parent)]
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == record['source_sha256'], 'wrong_installed_version')
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        'verification.test_live_spatial_mcp',
        'verification.test_source_region_display_host',
        'verification.m4_m5_source_region_001.core_tests.test_source_region_core',
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'tests': result.testsRun, 'failures': [str(test) for test, _ in result.failures],
                      'errors': [str(test) for test, _ in result.errors]}))
    return int(not result.wasSuccessful())


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    legacy_inputs = run_path(str(V / 'm1_sampled_image_path_producer_reuse_001/checks/positives.py'))
    raw, path, pins = legacy_inputs['frozen_media']()
    request = read(legacy_inputs['REQ'])
    tx = b''.join((json.dumps(dict(request, id=case))+'\n').encode() for case in ('cold', 'retained', 'stale'))
    (output/'SAMPLE_TX.bin').write_bytes(tx)
    replies, unit_reports = {}, {}
    for arm, binding in BINDINGS.items():
        sample = subprocess.run([sys.executable, '-IB', str(PREVIOUS/'checks/sample_path.py'),
                                 '--worker', str(binding), str(legacy_inputs['SOURCE'])],
                                input=tx, capture_output=True, timeout=45)
        (output/f'{arm}_SAMPLE_RX.bin').write_bytes(sample.stdout)
        (output/f'{arm}_SAMPLE_STDERR.bin').write_bytes(sample.stderr)
        sample.check_returncode()
        require(not sample.stderr, 'unexpected_sample_STDERR')
        replies[arm] = sample.stdout

        units = subprocess.run([sys.executable, '-IB', str(Path(__file__).resolve()), '--units', str(binding)],
                               capture_output=True, timeout=45)
        (output/f'{arm}_UNIT_STDOUT.json').write_bytes(units.stdout)
        (output/f'{arm}_UNIT_STDERR.txt').write_bytes(units.stderr)
        units_report = json.loads(units.stdout)
        require(units.returncode == int(bool(units_report['failures'] or units_report['errors'])),
                'unit_test_reporting_error')
        unit_reports[arm] = units_report
    require(unit_reports['A'] == unit_reports['B'] == read(PREVIOUS/'checks/LEGACY_UNITTEST.json')['A'],
            'the_frozen_legacy_unit_failures_changed')
    require(replies['A'] == replies['B'], 'sample_path_wire_changed')
    cases = []
    for line, expected_id, expected_path in zip(replies['B'].splitlines(), ('cold', 'retained', 'stale'),
                                                 (path.as_posix(), path.as_posix(), None), strict=True):
        rpc = json.loads(line)
        text, image = rpc['result']['content']
        require(rpc['id'] == expected_id and rpc['result']['isError'] is False
                and json.loads(text['text'])['images'][0].get('local_image_path') == expected_path
                and base64.b64decode(image['data'], validate=True) == raw, 'sample_reply_changed')
        cases.append({'case': rpc['id'], 'text_bytes': len(text['text'].encode()), 'path': expected_path})
    record = {'sample_path_passed': len(cases), 'sample_path_planned': 3,
              'sample_path_exact_wire': True, 'sample_path_cases': cases, 'legacy_units': unit_reports,
              'original_evidence': pins}
    (output/'COMPATIBILITY.json').write_bytes((json.dumps(record, indent=2)+'\n').encode())
    print(json.dumps({'sample_path_passed': len(cases), 'legacy_units': unit_reports}))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--units':
        sys.exit(unit_worker(Path(sys.argv[2])))
    run(Path(sys.argv[1]))
