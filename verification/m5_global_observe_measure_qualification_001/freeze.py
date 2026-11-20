"""Freeze the same installed product for the two read-only M5 qualifications."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import SCHEMA, registered_product, verify_freeze
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, CATALOGUE, EXTERNAL, GEOMETRY, GEOMETRY_SHA256, ORDER,
                    PRODUCT_BINDING, PRODUCT_SCHEMA, REQUESTS, ROOT, TRUTH, asset_identity, read, save, sha)


EVIDENCE = '42e72c2611b99a477e88a5fb26ead0cbad5e71b1'
PRODUCT = '9552d5c7103d9d8a08799adde96534990c6815f9'
PRODUCT_SOURCE = '301caf777d446938497b53d5d49d67279cdcdb4ba2ee03e8aeb7e737c66076b6'
WHEEL = '289cd77e16eb56bbcee3442db5e882b7ce3650732420c0a1e081ee737f3bf177'
PLAN = '4085ddef47975c95b00dc9c647cc2d5a3c4cc290:docs/M5_GLOBAL_OBSERVE_MEASURE_QUALIFICATION_001_PLAN.md'
RASTER = NS.parent / 'm4_dense_raster_cross_001'
RASTER_FREEZE = 'da2979f1fbc65d8a3ebac64f3c028f9781b2e8e8d124e5087d3f3728da791447'
RASTER_MANIFEST = '5b51f4ab8bdd7d84b2e609740453757d16b5d268eda2d8b9cd565285df38f40e'


def freeze():
    start = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or EXTERNAL.exists():
        raise ValueError('fresh_qualification_runtime_and_isolated_interpreter_required')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() != EVIDENCE:
        raise ValueError('registered_evidence_base_required')

    pins = {}

    def pin(path, expected=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((expected is not None and row['sha256'] != expected) or (size is not None and row['bytes'] != size)
                or path.suffix == '.pyc'):
            raise ValueError('registered_frozen_input_changed/' + str(path))

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    plan = NS / 'PLAN.md'
    if plan.read_bytes() != subprocess.check_output(['git', 'show', PLAN], cwd=ROOT):
        raise ValueError('original_planning_commit_bytes_changed')
    pin(plan)
    asset, asset_sha = asset_identity()
    if asset.resolve() != ASSET.resolve() or asset_sha != ASSET_SHA256:
        raise ValueError('original_asset_bytes_changed')
    pin(asset, ASSET_SHA256)
    pin(GEOMETRY, GEOMETRY_SHA256)
    pin(TRUTH)
    measure = NS / 'truth/MEASUREMENT_TRUTH.json'
    dispatch = NS / 'harness/DISPATCH_PREFLIGHT.json'
    live_preflight = NS / 'checks/LIVE_PREFLIGHT.json'
    for receipt in (measure, dispatch, live_preflight):
        evidence = read(receipt)
        if evidence['passed'] is not True:
            raise ValueError('registered_preflight_failed/' + receipt.name)
        pin(receipt)
        bind(evidence.get('source_pins', []))
    for request in REQUESTS.values():
        pin(request)
    measure_request = {'mode': 'task', 'objects': [{'name': 'N11'}, {'name': 'N22'}],
                       'requested_facts': ['surface_proximity']}
    observe_request = {'mode': 'active_observation',
                       'region_task': {'area_min_m2': .025, 'area_max_m2': .05, 'normal_z_min': .75}}
    forms = {'OBSERVE': (observe_request, True), 'MEASURE': (measure_request, False),
             'JOINT': ({**observe_request, 'task_query': measure_request}, True)}
    for name, (query, image) in forms.items():
        if read(REQUESTS[name]) != {'query': query, 'include_image': image, 'response_detail': 'brief'}:
            raise ValueError('registered_split_or_joint_request_changed/' + name)
    entry = json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(NS / 'run_sequence.py'),
        '--dispatch-smoke'], cwd=ROOT, timeout=20))
    if (entry['fresh_process_prepared_only'] is not True or entry['order'] != list(ORDER)
            or entry['schema'] != SCHEMA or Path(entry['run_root']).resolve() != EXTERNAL.resolve()
            or Path(entry['admission']).resolve() != (NS / 'harness/admission.py').resolve()
            or entry['current_product'] != registered_product()):
        raise ValueError('fresh_sequence_admission_or_run_root_changed')

    pin(RASTER / 'FROZEN.json', RASTER_FREEZE)
    bind(read(RASTER / 'FROZEN.json')['direct_inputs'])
    pin(RASTER / 'CONTENT_MANIFEST.json', RASTER_MANIFEST)
    for row in read(RASTER / 'CONTENT_MANIFEST.json')['files']:
        pin(RASTER / row['path'], row['sha256'], row['bytes'])
    binding = read(PRODUCT_BINDING)
    install = read(PRODUCT_BINDING.with_name('BUILD_INSTALL.json'))
    if (binding['preparation_git'] != PRODUCT or binding['source_sha256'] != PRODUCT_SOURCE
            or binding['wheel_sha256'] != WHEEL or len(binding['source_manifest']) != 143 or install['passed'] is not True
            or install['binding'] != binding or type(install['tool_schema_matches_historical_actual_directory']) is not bool
            or not install['tool_schema_matches_historical_actual_directory']):
        raise ValueError('one_identical_isolated_product_required')
    pin(PRODUCT_BINDING)
    pin(binding['wheel_path'], WHEEL)
    pin(CATALOGUE)
    pin(PRODUCT_SCHEMA)
    for key in ('installed_files', 'execution_and_input_pins'):
        bind(install[key])
    pin(NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py')
    pin(sys.executable)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)

    output = NS / 'FROZEN.json'
    save(output, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS,
        'product': registered_product(), 'product_diff_files': 0,
        'asset_sha256': ASSET_SHA256, 'terminal_source_sha256': GEOMETRY_SHA256, 'region_truth_sha256': sha(TRUTH),
        'measurement_truth_sha256': sha(measure), 'dispatch_preflight_sha256': sha(dispatch),
        'live_checker_preflight_sha256': sha(live_preflight), 'fresh_sequence_preflight': entry,
        'started_ns': start, 'completed_ns': time.perf_counter_ns(),
        'planned_outer_batches': {'A': 1, 'B': 1}, 'planned_public_business_calls': {'A': 2, 'B': 1},
        'planned_raster_attempts': {'A': 3, 'B': 3}, 'owned_s': 600, 'task_s': 450,
        'model_consumers': 0, 'asset_rebuilds': 0, 'product_rebuilds': 0, 'replacements': 0,
        'fixed_CLI': {'version': '0.152.1', 'MCP_bytes': 12000, 'history_approximate_tokens': 3000,
                      'header_bytes': [33, 34, 35]},
        'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze two same-version qualifications', len(pins), verify_freeze(output), flush=True)


if __name__ == '__main__':
    freeze()
