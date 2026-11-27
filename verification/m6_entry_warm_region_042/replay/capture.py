"""One post-business, original-connector capture from an already owned GUI.

Import capture_current from the live runner. This helper neither starts nor
closes Blender. Its fresh child prevents a previously imported R3 package from
standing in for the pinned 032 connector. It never calls a geometry solver.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay_common import BOX, PYTHON, REFERENCE, TARGET, dump, installation, need, pin, read


def capture_current(host, port, output_dir, *, project_root=None,
                    expected_target=None, expected_reference=None, box=None,
                    expected_geometry=None, timeout_s=30):
    """Capture once after all primary endpoints; return immutable receipt refs.

    expected_target/reference may be name strings, selector dictionaries or
    frozen object identity dictionaries. Optional native identities are checked.
    output_dir must not already exist. Failures are retained and never retried.
    """
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    expected_target = {'name': expected_target} if isinstance(expected_target, str) else expected_target
    expected_reference = {'name': expected_reference} if isinstance(expected_reference, str) else expected_reference
    intent = {'host': host, 'port': port, 'project_root': str(project_root) if project_root else None,
              'expected_target': expected_target or TARGET,
              'expected_reference': expected_reference or REFERENCE,
              'box': box or BOX, 'expected_geometry': expected_geometry,
              'timeout_s': timeout_s, 'source': pin(__file__),
              'scope': 'post-primary original connector capture only; no solver; no Blender lifecycle'}
    dump(directory / 'INTENT.json', intent)
    command = [str(PYTHON), '-I', '-B', str(Path(__file__).resolve()), '--child', str(directory)]
    start = time.perf_counter_ns()
    try:
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=timeout_s + 30, check=False)
        (directory / 'STDOUT.bin').write_bytes(process.stdout)
        (directory / 'STDERR.bin').write_bytes(process.stderr)
        execution = {'command': command, 'started_ns': start, 'closed_ns': time.perf_counter_ns(),
                     'returncode': process.returncode}
    except BaseException:
        execution = {'command': command, 'started_ns': start, 'closed_ns': time.perf_counter_ns(),
                     'returncode': None, 'error': traceback.format_exc()}
    execution['wall_ns'] = execution['closed_ns'] - execution['started_ns']
    dump(directory / 'CHILD_EXECUTION.json', execution)
    receipt = directory / 'RECEIPT.json'
    return {'status': read(receipt)['status'] if receipt.is_file() else 'failed_without_receipt',
            'receipt': pin(receipt) if receipt.is_file() else None,
            'execution': pin(directory / 'CHILD_EXECUTION.json'),
            'capture': pin(directory / 'CAPTURE.json') if (directory / 'CAPTURE.json').is_file() else None}


def _selector(expected):
    return {'id': expected['id']} if 'id' in expected else {'name': expected['name']}


def _child(directory):
    directory = Path(directory)
    intent = read(directory / 'INTENT.json')
    result = {'status': 'failed', 'intent': pin(directory / 'INTENT.json'),
              'native_calls': 0, 'solver_calls': 0, 'raw_wire_recorded': False,
              'scope': 'full materialized return from unmodified installed connector'}
    host = None
    try:
        install = installation('032')
        site = Path(install['site_packages'])
        need(intent['project_root'] is None or Path(intent['project_root']).resolve() == site.resolve(),
             'capture_requires_pinned_032_project_root')
        sys.path.insert(0, str(site))
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost
        target = _selector(intent['expected_target'])
        reference = _selector(intent['expected_reference'])
        host = BlenderMCPHost(site, host=intent['host'], port=intent['port'], timeout_s=intent['timeout_s'])
        result.update(installation=install, host_source_sha256=host._readonly_host_source_sha256,
                      connector_source=pin(site / 'human_eye_plugin/blender_mcp_host.py'),
                      host_source=pin(site / 'human_eye_plugin/blender_host.py'),
                      method='BlenderMCPHost.capture_source_region_pair', target=target,
                      reference=reference, box=intent['box'])
        started = time.perf_counter_ns()
        result['native_calls'] = 1
        capture = host.capture_source_region_pair(target, reference, intent['box'],
                    started + int(intent['timeout_s'] * 1e9), 64 * 1024 * 1024)
        result['capture_wall_ns_diagnostic_only'] = time.perf_counter_ns() - started
        dump(directory / 'CAPTURE.json', capture)
        result['capture'] = pin(directory / 'CAPTURE.json')
        for key in ('target', 'reference'):
            expected = intent['expected_' + key]
            got = capture['binding'][key]
            for field in ('name', 'object_id', 'instance_id'):
                if field in expected:
                    need(got[field] == expected[field], 'capture_' + key + '_' + field)
        region, ref = capture['region'], capture['reference']
        counts = {'selected_triangles': len(region['faces']), 'selected_vertices': len(region['vertices']),
                  'source_vertices': region['source_vertex_count'], 'source_triangles': region['source_triangle_count'],
                  'reference_vertices': len(ref['vertices']), 'reference_triangles': len(ref['faces'])}
        expected = intent['expected_geometry'] or {'selected_triangles': 262, 'selected_vertices': 173,
                    'source_vertices': 27304, 'source_triangles': 53264,
                    'reference_vertices': 8, 'reference_triangles': 12}
        need(all(counts[k] == v for k, v in expected.items()), 'capture_geometry_counts')
        need(capture['binding']['host_source_sha256'] == result['host_source_sha256'], 'capture_host_binding')
        result.update(status='pass', counts=counts, connector_validation_completed=True)
    except BaseException:
        result['error'] = traceback.format_exc()
    finally:
        if host is not None:
            host.close()
        result['connector_closed'] = True
        dump(directory / 'RECEIPT.json', result)
    print(json.dumps({'status': result['status'], 'receipt': pin(directory / 'RECEIPT.json')}), flush=True)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', required=True)
    raise SystemExit(_child(parser.parse_args().child))
