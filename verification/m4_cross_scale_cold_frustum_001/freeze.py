"""Freeze the frustum gates, same requests, isolated products and pair order."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCTS, SCHEMA, verify_freeze
from budget import LIMITS
from common import BINDINGS, EXTERNAL, FORMAL, ORDER, ROOT, asset_identity, read, save, sha


PLAN_SHA = '74099662a36dbb94d10ec474b3d69589540dd1229b015f76d3fa0a650d813298'
PRIOR_INDEX = NS.parent / 'm4_cross_scale_global_index_reuse_001'
SECONDARY = Path('D:/he_m4_assembly_evidence_consumption_001/slots/A1/TERMINAL_SOURCE.json')
MODEL_BRIEF = NS.parent / 'm4_cross_scale_brief_entry_001'
MODEL_PREDICTION = Path('D:/he_m4_cross_scale_brief_entry_001/slots/P1/owner/tool_02/PRODUCT_REQUEST.json')
OLD_FREEZE_SHA = '267a2af4cd3a360484790b01b801522f6b27cbf68c619dfa8c9addb189d7aa2c'
CHANGED_FILES = ['human_eye_plugin/active_observation.py', 'human_eye_plugin/active_observation_region_task.py']
PERFORMANCE_GATE = {'median_paired_cold_global_index_reduction_percent_min': 20.0,
                    'median_paired_cold_server_rpc_change_ms_exclusive_max': 0}


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('pinned_interpreter_and_unused_schedule_required')
    if sha(NS / 'inputs/PLAN.md') != PLAN_SHA:
        raise ValueError('registered_plan_bytes_changed')
    for name in ('inputs/PRODUCT_SCHEMA.json', 'fixture/CURRENT_TRUTH.json',
                 'fixture/ASSET_BINDING.json', 'fixture/GEOMETRY.json'):
        if (NS / name).read_bytes() != (FORMAL / name).read_bytes():
            raise ValueError('registered_shared_input_changed/' + name)
    request = NS / 'inputs/REQUEST.json'
    args = read(request)
    predictor = read(NS / 'inputs/PREDICTION.json')
    if (request.read_bytes() != (MODEL_BRIEF / 'inputs/REQUEST.json').read_bytes()
            or set(args) != {'query', 'include_image', 'response_detail'}
            or args['include_image'] is not True or args['response_detail'] != 'brief'
            or predictor != dict(args, include_image=False, response_detail='full')
            or predictor != read(MODEL_PREDICTION)['params']['arguments']):
        raise ValueError('exact_registered_brief_prediction_and_hot_arguments_required')
    ancestry = subprocess.check_output(
        ['git', 'rev-list', '--parents', '-n', '1', PRODUCTS['B']['commit']], cwd=ROOT).decode().split()
    scope = subprocess.check_output(['git', 'diff', '--name-only',
        PRODUCTS['A']['commit'], PRODUCTS['B']['commit']], cwd=ROOT).decode().splitlines()
    if ancestry != [PRODUCTS[arm]['commit'] for arm in ('B', 'A')] or scope != CHANGED_FILES:
        raise ValueError('candidate_must_derive_directly_from_actual_baseline_with_two_registered_files')

    pins = {}

    def pin(path, expected=None, length=None):
        path = Path(path).resolve()
        row = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((expected is not None and expected != row['sha256'])
                or (length is not None and length != row['bytes'])
                or (path in pins and pins[path] != row) or path.suffix == '.pyc'):
            raise ValueError('fixed_input_changed/' + str(path))
        pins[path] = row

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row['bytes'])

    products = {}
    for arm, path in BINDINGS.items():
        binding = read(path)
        if (binding['preparation_git'] != PRODUCTS[arm]['commit']
                or binding['source_sha256'] != PRODUCTS[arm]['source_sha256']
                or len(binding['source_manifest']) != 143):
            raise ValueError('actual_registered_arm_source_mismatch/' + arm)
        manifest = {}
        for row in binding['source_manifest']:
            name = row['path']
            pin(Path(binding['install_root']) / name, row['sha256'], row.get('bytes'))
            if name in manifest:
                raise ValueError('duplicate_installed_source_name/' + name)
            manifest[name] = row['sha256']
        products[arm] = manifest
        pin(path)
    if (set(products['A']) != set(products['B'])
            or sorted(path for path in products['A'] if products['A'][path] != products['B'][path]) != CHANGED_FILES
            or read(BINDINGS['A'])['dependency_root'] != read(BINDINGS['B'])['dependency_root']):
        raise ValueError('unregistered_install_or_dependency_difference')

    install = read(NS / 'install/BUILD_INSTALL.json')
    if (install['passed'] is not True or install['binding'] != read(BINDINGS['B'])
            or install['historical_git_wheel_install_sources_verified'] != 143
            or install['actual_candidate_wheels'] != 1
            or install['tool_schema_matches_historical_actual_directory'] is not True
            or read(NS / 'install/PRODUCT_SCHEMA.json') != read(NS / 'inputs/PRODUCT_SCHEMA.json')):
        raise ValueError('direct_candidate_wheel_or_actual_tools_not_verified')
    for key in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        pin_rows(install[key])
    for arm, name in (('A', 'FRUSTUM_BASELINE.json'), ('B', 'FRUSTUM_CONTROLS.json'), ('B', 'FRUSTUM_HOT_REPLAY.json')):
        path = NS / 'checks' / name
        receipt = read(path)
        if (receipt['passed'] is not True or Path(receipt['product_root']).resolve()
                != Path(read(BINDINGS[arm])['install_root']).resolve()
                or receipt['runtime_source_sha256'] != PRODUCTS[arm]['source_sha256']
                or any(receipt[field] != 0 for field in ('actual_new_rasters', 'models', 'owned_Blender'))):
            raise ValueError('installed_offline_qualification_failed/' + arm)
        pin_rows(receipt['source_pins'])
    asset, digest = asset_identity()
    pin(asset, 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce')
    pin(NS / 'fixture/CURRENT_TRUTH.json', '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922')
    baseline = FORMAL / 'FROZEN.json'
    pin(baseline, OLD_FREEZE_SHA)
    pin_rows(read(baseline)['direct_inputs'])
    prior_manifest = PRIOR_INDEX / 'CONTENT_MANIFEST.json'
    pin(prior_manifest, '515e45de130f9cd2dc3eaafe0400eb8ccae456267cea42f96901ec54b6d8069a')
    for row in read(prior_manifest)['files']:
        pin(PRIOR_INDEX / row['path'], row['sha256'], row['bytes'])
    pin(MODEL_PREDICTION)
    pin(SECONDARY, '81c84f4d7273cd9045702c7afb95b9c8fc21b02764106ff9d8289c7120e0964c')
    for item in NS.rglob('*'):
        if item.is_file():
            if item.suffix == '.py':
                ast.parse(item.read_bytes(), filename=str(item))
            pin(item)
    expected = (NS / 'checks/assess_pairs.py').resolve()
    if expected not in pins:
        raise ValueError('pair_quality_checker_required_before_first_slot')
    path = NS / 'FROZEN.json'
    save(path, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'products': PRODUCTS,
         'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'owned_s': 600, 'task_s': 450,
         'asset_sha256': digest, 'baseline_frozen_sha256': OLD_FREEZE_SHA, 'runtime_model_quota': 0,
         'performance_gate': PERFORMANCE_GATE,
         'direct_inputs': [pins[key] for key in sorted(pins)]})
    verify_freeze()
    print('Froze six ordered slots:', len(pins), sha(path))


if __name__ == '__main__':
    freeze()
