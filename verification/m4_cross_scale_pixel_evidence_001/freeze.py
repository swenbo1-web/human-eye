"""Freeze pixel evidence controls, identical requests and the installed candidate."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCTS, SCHEMA, verify_freeze
from budget import LIMITS
from common import ASSEMBLY, BINDINGS, EXTERNAL, FORMAL, ORDER, ROOT, asset_identity, read, save, sha


BASE = '39fd39cdad162bbe7e5eb68243881d39bb67d285'
PRODUCT_BASE = '21e608db565cf20d21fca735f913ae780e231470'
PRODUCT_SOURCE_BASE = 'ea93acca1a4ba0bcd527f9702657e9180bac05e2cb126e10474fb525b7fa1ca7'
PLAN_SHA = '254e92647c1aa6ba3ac9158f1422f89b8015376f122dc7d6533cad6c12751001'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
OLD = Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/P1')
RELATIVE_PRODUCT_FILE = 'human_eye_plugin/live_spatial_mcp.py'


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('pinned_interpreter_and_unused_schedule_required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    if head != BASE or sha(NS / 'inputs/PLAN.md') != PLAN_SHA:
        raise ValueError('registered_evidence_or_plan_changed')
    ancestry = subprocess.check_output(
        ['git', 'rev-list', '--parents', '-n', '1', PRODUCTS['P']['commit']], cwd=ROOT).decode().split()
    changes = subprocess.check_output(
        ['git', 'diff', '--name-only', PRODUCT_BASE, PRODUCTS['P']['commit']], cwd=ROOT).decode().splitlines()
    if ancestry != [PRODUCTS['P']['commit'], PRODUCT_BASE] or changes != [RELATIVE_PRODUCT_FILE]:
        raise ValueError('candidate_must_be_direct_single_formatter_delta')
    request = NS / 'inputs/REQUEST.json'
    pred = NS / 'inputs/PREDICTION.json'
    if (request.read_bytes() != (ASSEMBLY / 'inputs/REQUEST.json').read_bytes()
            or any(read(OLD / f'owner/tool_{ordinal:02d}/PRODUCT_REQUEST.json')['params']['arguments'] != read(path)
                   for ordinal, path in enumerate((request, pred), 1))
            or read(pred) != dict(read(request), include_image=False, response_detail='full')):
        raise ValueError('same_two_formal_assembly_requests_required')

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

    path = BINDINGS['P']
    cold = NS.parent / 'm4_cross_scale_cold_frustum_001/install/PRODUCT_RUN_BINDING.json'
    a, b = read(cold), read(path)
    if (a['preparation_git'] != PRODUCT_BASE or a['source_sha256'] != PRODUCT_SOURCE_BASE
            or b['preparation_git'] != PRODUCTS['P']['commit']
            or b['source_sha256'] != PRODUCTS['P']['source_sha256']
            or a['dependency_root'] != b['dependency_root']):
        raise ValueError('unregistered_product_or_dependency')
    before = {row['path']: row['sha256'] for row in a['source_manifest']}
    after = {row['path']: row['sha256'] for row in b['source_manifest']}
    if (len(before) != 143 or before.keys() != after.keys()
            or [name for name in before if before[name] != after[name]] != [RELATIVE_PRODUCT_FILE]):
        raise ValueError('actual_install_is_not_one_formatter_delta')
    install = read(NS / 'install/BUILD_INSTALL.json')
    if (install['passed'] is not True or install['binding'] != b or install['actual_candidate_wheels'] != 1
            or install['historical_git_wheel_install_sources_verified'] != 143
            or install['tool_schema_matches_historical_actual_directory'] is not True
            or read(NS / 'install/PRODUCT_SCHEMA.json') != read(NS / 'inputs/PRODUCT_SCHEMA.json')):
        raise ValueError('registered_isolated_product_install_not_verified')
    for key in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        pin_rows(install[key])
    controls_path = NS / 'checks/PIXEL_CONTROLS.json'
    controls = read(controls_path)
    if controls['passed'] is not True:
        raise ValueError('offline_exact_pixel_and_delivery_preflight_failed')
    pin_rows(controls['source_pins'])
    asset, digest = asset_identity()
    pin(asset, ASSET_SHA)
    asset_record = read(ASSEMBLY / 'fixture/ASSET_BINDING.json')
    pin_rows([asset_record['archived_terminal']])
    pin_rows(asset_record['source_pins'])
    manifest = ASSEMBLY / 'CONTENT_MANIFEST.json'
    pin(manifest, '0be1c09cf34ce3392b02a5698db0922a4ed05a39a62ab6194c75e007853213b3')
    for row in read(manifest)['files']:
        pin(ASSEMBLY / row['path'], row['sha256'], row['bytes'])
    original_formal = FORMAL / 'FROZEN.json'
    pin(original_formal, '267a2af4cd3a360484790b01b801522f6b27cbf68c619dfa8c9addb189d7aa2c')
    pin_rows(read(original_formal)['direct_inputs'])
    for name in ('m4_cross_scale_local_first_view_001/checks/assess_pairs.py',
                 'm4_cross_scale_live_task_recovery_001/qualify.py',
                 'm4_cross_scale_discovery_001/oracle/check_saved.py'):
        pin(NS.parent / name)
    pin(OLD.parents[1] / 'ORIGINAL_RUNTIME.zip',
        'bf7be101396593b151411e567b05af32e0e0754ac18dc733a6a10191fcae3627')
    for ordinal in (1, 2):
        pin(OLD / f'owner/tool_{ordinal:02d}/PRODUCT_REQUEST.json')
    if not (NS / 'checks/assess_live.py').is_file():
        raise ValueError('independent_live_checker_required_before_slot')
    for item in NS.rglob('*'):
        if item.is_file():
            if item.suffix == '.py':
                ast.parse(item.read_bytes(), filename=str(item))
            pin(item)
    frozen = NS / 'FROZEN.json'
    save(frozen, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'products': PRODUCTS,
         'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'owned_s': 600, 'task_s': 450,
         'asset_sha256': digest, 'runtime_model_quota': 0,
         'direct_inputs': [pins[key] for key in sorted(pins)]})
    verify_freeze()
    print('Froze the one pixel evidence slot', len(pins), sha(frozen))


if __name__ == '__main__':
    freeze()
