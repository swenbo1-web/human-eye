"""Freeze the six engineering slots and their checked isolated installations."""

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import SCHEMA, registered_products, verify_freeze
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, BINDINGS, EXTERNAL, GEOMETRY, ORDER, REQUEST, ROOT, TRUTH,
                    asset_identity, read, save, sha)


BASE_EVIDENCE = '9547ec8ee2ddea85263da761dc4fed3adbdecca8'
BASE_PRODUCT = 'f72e648f763fb6399f82c8e5d7f2b35840597bed'
CANDIDATE = '9552d5c7103d9d8a08799adde96534990c6815f9'
CHANGED = 'human_eye_plugin/attention_raster.py'
PLAN = '1cc8d898b8745b6dbd1d4fd15df14f86d7724e02:docs/M4_DENSE_RASTER_CROSS_001_PLAN.md'
OLD = NS.parent / 'm4_global_pixel_bound_short_circuit_001'
OLD_FREEZE = '8c9424b343f2794158f0b7d7a584f9d697fa9ea0a2c999207bbdeb9ad84b381e'
OLD_MANIFEST = '976ddf589c57b39bbaef9fdbaffae6c252996ca17b0bd5b5e42c4a9b1ba26209'
OLD_ARCHIVE = '853d1bbde7295110e2a5a7214c40eb59a7cfed5169302e5f94e0c5b96fd6c9ef'
FIRST_FREEZE = 'e1219796918e28031ea8f3b1546d97813e596a26cd3bf97b32a9edd41fbd9656'
TRUTH_SHA = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def regression_pair(receipt):
    """Compare historical failures by test and assertion, independently of the arm's installed path."""
    keys = ('tests_run', 'failures', 'errors', 'skipped')
    signatures = []
    for arm in ('A', 'B'):
        row = receipt['cases'][arm]
        trace = row['unittest_summary']
        signatures.append((tuple(row[name] for name in keys), re.findall(
            r'^(?:(?:FAIL|ERROR): |[A-Za-z]+Error: ).*$', trace, re.MULTILINE)))
    if signatures[0] != signatures[1] or signatures[0][0][0] <= 0:
        raise ValueError('existing_synthetic_test_outcomes_changed_between_arms')
    return dict(zip(keys, signatures[0][0], strict=True))


def freeze():
    start = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('fresh_slot_directory_and_isolated_interpreter_required')
    if git('rev-parse', 'HEAD').decode().strip() != BASE_EVIDENCE:
        raise ValueError('fixed_evidence_base_required')
    if (git('rev-list', '--parents', '-n', '1', CANDIDATE).decode().split() != [CANDIDATE, BASE_PRODUCT] or
            git('diff', '--name-only', BASE_PRODUCT, CANDIDATE).decode().splitlines() != [CHANGED]):
        raise ValueError('registered_single_file_product_candidate_required')
    plan = NS / 'PLAN.md'
    if plan.read_bytes() != git('show', PLAN):
        raise ValueError('published_plan_bytes_changed')

    pinned = {}

    def pin(path, expected=None, size=None):
        path = Path(path).resolve()
        if path not in pinned:
            pinned[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pinned[path]
        if ((expected is not None and row['sha256'] != expected) or (size is not None and row['bytes'] != size)
                or path.suffix == '.pyc'):
            raise ValueError('frozen_input_changed/' + str(path))

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    asset, asset_sha = asset_identity()
    if asset.resolve() != ASSET.resolve() or asset_sha != ASSET_SHA256:
        raise ValueError('original_dense_asset_changed')
    pin(asset, ASSET_SHA256)
    pin(GEOMETRY)
    pin(TRUTH, TRUTH_SHA)
    pin(REQUEST)
    pin(plan)
    pin(OLD / 'FROZEN.json', OLD_FREEZE)
    pin_rows(read(OLD / 'FROZEN.json')['direct_inputs'])
    pin(OLD / 'CONTENT_MANIFEST.json', OLD_MANIFEST)
    for item in read(OLD / 'CONTENT_MANIFEST.json')['files']:
        pin(OLD / item['path'], item['sha256'], item['bytes'])
    archive = read(OLD / 'RUNTIME_INDEX.json')['archive']
    pin(archive['path'], OLD_ARCHIVE, archive['bytes'])
    # The archive writer is retained from a previously admitted benchmark.
    pin(NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py')

    installed = {arm: read(path) for arm, path in BINDINGS.items()}
    build = read(NS / 'install/BUILD_INSTALL.json')
    baseline_sources, candidate_sources = ({row['path']: row['sha256'] for row in installed[arm]['source_manifest']}
                                          for arm in ('A', 'B'))
    if (build['passed'] is not True or build['actual_candidate_wheels'] != 1 or build['binding'] != installed['B']
            or build['tool_schema_matches_historical_actual_directory'] is not True
            or build['historical_git_wheel_install_sources_verified'] != 143 or len(baseline_sources) != 143
            or baseline_sources.keys() != candidate_sources.keys() or
            [name for name in baseline_sources if baseline_sources[name] != candidate_sources[name]] != [CHANGED]
            or any(installed[arm]['preparation_git'] != value for arm, value in (('A', BASE_PRODUCT), ('B', CANDIDATE)))):
        raise ValueError('isolated_wheel_sources_or_public_catalogue_changed')
    for arm, path in BINDINGS.items():
        pin(path)
        pin(installed[arm]['wheel_path'], installed[arm]['wheel_sha256'])
        pin(path.with_name('TOOLS_SCHEMA.json'))
        pin(path.with_name('PRODUCT_SCHEMA.json'))
    for key in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        pin_rows(build[key])

    offline = NS / 'checks/OFFLINE_CONTROLS.json'
    dispatch = NS / 'harness/DISPATCH_PREFLIGHT_RECOVERY.json'
    live_preflight = NS / 'checks/LIVE_PREFLIGHT.json'
    for path in (offline, dispatch, live_preflight):
        receipt = read(path)
        if receipt['passed'] is not True:
            raise ValueError('registered_offline_gate_failed/' + path.name)
        pin_rows(receipt.get('source_pins', []))
    regression = read(NS / 'checks/REGRESSION.json')
    unchanged_regression_outcomes = regression_pair(regression)
    pin_rows(regression['source_pins'])
    pin(NS / 'prelaunch/FROZEN.json', FIRST_FREEZE)
    initial = read(NS / 'prelaunch/FAILURE.json')
    if initial['freeze_sha256'] != FIRST_FREEZE or any(initial[key] != 0 for key in (
            'actual_Blender_starts', 'actual_business_calls', 'actual_rasters', 'actual_models')):
        raise ValueError('initial_sequence_failure_must_precede_all_owned_work')
    smoke = json.loads(subprocess.check_output(
        [sys.executable, '-I', '-B', str(NS / 'run_sequence.py'), '--dispatch-smoke'], cwd=ROOT, timeout=20))
    if (smoke['status'] != 'prepared' or smoke['fresh_process_prepared_only'] is not True
            or Path(smoke['run_root']).resolve() != EXTERNAL.resolve() or tuple(smoke['order']) != tuple(ORDER)
            or smoke['schema'] != SCHEMA or smoke['products'] != registered_products()):
        raise ValueError('fresh_sequence_process_no_longer_routes_to_frozen_trial')
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    pin(sys.executable)
    path = NS / 'FROZEN.json'
    save(path, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'products': registered_products(),
          'candidate_single_changed_file': CHANGED, 'asset_sha256': ASSET_SHA256, 'truth_sha256': TRUTH_SHA,
          'started_ns': start, 'completed_ns': time.perf_counter_ns(),
          'unchanged_historical_synthetic_outcomes': unchanged_regression_outcomes,
          'offline_controls_sha256': sha(offline), 'dispatch_preflight_sha256': sha(dispatch),
          'live_checker_preflight_sha256': sha(live_preflight),
          'initial_prelaunch_freeze_sha256': FIRST_FREEZE, 'fresh_sequence_preflight': smoke,
          'raster_views_measured': ['SCENE', 'LEFT'], 'extra_algorithm_instrumentation_during_measurement': False,
          'minimum_median_paired_raster_reduction_percent': 10, 'minimum_cold_RPC_improved_pairs': 2,
          'require_negative_median_cold_RPC_delta': True, 'asset_rebuilds': 0, 'additional_qualifications': 0,
          'model_consumers': 0, 'body_cap_bytes': 10800, 'owned_s': 600, 'task_s': 450,
          'fixed_CLI': {'version': '0.152.1', 'MCP_bytes': 12000, 'history_approximate_tokens': 3000,
                        'header_bytes': [33, 34, 35]},
          'direct_inputs': [pinned[path] for path in sorted(pinned)]})
    print('Froze six uninstrumented raster engineering slots', len(pinned), verify_freeze(path), flush=True)


if __name__ == '__main__':
    freeze()
