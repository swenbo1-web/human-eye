"""Freeze the six engineering slots and their checked isolated installations."""

import ast
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


BASE_EVIDENCE = 'a17083c0dff7d4e90daae59406b4a19960583df4'
BASE_PRODUCT = 'e03ee486dc8f86f6a7d2fb75d012d181edcf8f3c'
CANDIDATE = 'f72e648f763fb6399f82c8e5d7f2b35840597bed'
CHANGED = 'human_eye_plugin/active_observation_region_task.py'
PLAN = '14245c47068debaaef66042d4019649da79350f8:docs/M4_GLOBAL_PIXEL_BOUND_SHORT_CIRCUIT_001_PLAN.md'
OLD = NS.parent / 'm4_bound_blocker_evidence_001'
OLD_FREEZE = 'bf67bed87a13903773139366a21ebe669f40552782651225d2be7da5e4928ce7'
OLD_MANIFEST = 'e410cf74cb0d258d5b9f4e48cb899c922c1caa0eb916bea2dfc2f35e808a281a'
OLD_ARCHIVE = '18c91c9903cba5f0c7b40e180e7f6a3b503b221eb80c0512ac1c8c12026423b4'
FIRST_FREEZE = '0fccb36d2a076bcb4bf11dbd1857a116b49e3ba8983eb9fb79eb0ea0436e367d'
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
    first = read(NS / 'prelaunch/FAILURE.json')
    if first['freeze_sha256'] != FIRST_FREEZE or any(first[field] != 0 for field in (
            'actual_Blender_starts', 'actual_business_calls', 'actual_rasters', 'actual_models')):
        raise ValueError('prelaunch_adapter_failure_must_have_consumed_no_owned_slots')
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
          'first_frozen_prelaunch_sha256': FIRST_FREEZE, 'owned_slots_consumed_by_prelaunch_failure': 0,
          'expected_actual_LEFT_bound_calls': {'A': 10, 'B': 1},
          'minimum_median_paired_LEFT_stage_reduction_percent': 70, 'minimum_cold_RPC_improved_pairs': 2,
          'require_negative_median_cold_RPC_delta': True, 'asset_rebuilds': 0, 'additional_qualifications': 0,
          'model_consumers': 0, 'body_cap_bytes': 10800, 'owned_s': 600, 'task_s': 450,
          'fixed_CLI': {'version': '0.152.1', 'MCP_bytes': 12000, 'history_approximate_tokens': 3000,
                        'header_bytes': [33, 34, 35]},
          'direct_inputs': [pinned[path] for path in sorted(pinned)]})
    print('Froze six engineering slots', len(pinned), verify_freeze(path), flush=True)


if __name__ == '__main__':
    freeze()
