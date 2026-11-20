"""Freeze the fixed rail task, actual installed products, source, and gates."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import SCHEMA, verify_freeze
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, BINDINGS, BLENDER, EXTERNAL, GEOMETRY, GEOMETRY_SHA256, ORDER,
                    PRODUCTS, ROOT, TRUTH, V, product_for, read, save, sha)

BASE = 'a3277cd787606c1e674be64764c109a87b0b69a0'
PLAN = 'd31019fc79d96ae318eab508bd95f30c1167a73a:docs/M4_RAIL_BLOCKER_CONSUMPTION_001_PLAN.md'
PLAN_SHA = 'e00ac0bed2ae18e2dddb9dfba092cbc8636f4c609c04b54143ad3168814c2cda'
TRUTH_SHA = 'd4daeb84945dddb0b1d511dd0931dc38adcbaae7eb2e7c68080fd068a972ebe0'
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
WHEELS = {'A': '46664941fbd83be143ae4866486d1a76593c82c7331a4c9926a600189c8ee347',
          'B': 'd6e5cfe2a57bca90ace2bd5c67bc94c02fdc15f14df8d337c74ec929fd6228c6'}


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or EXTERNAL.exists():
        raise ValueError('fresh_runtime_directory_and_isolated_interpreter_required')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() != BASE:
        raise ValueError('must_freeze_on_registered_base')
    actual_plan = subprocess.check_output(['git', 'show', PLAN], cwd=ROOT)
    plan = NS / 'inputs/PLAN.md'
    if plan.read_bytes() != actual_plan:
        raise ValueError('original_plan_bytes_changed')

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((digest is not None and row['sha256'] != digest)
                or (size is not None and row['bytes'] != size) or path.suffix == '.pyc'):
            raise ValueError('frozen_input_mismatch/' + str(path))

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    pin(plan, PLAN_SHA)
    pin(ASSET, ASSET_SHA256)
    pin(GEOMETRY, GEOMETRY_SHA256)
    pin(TRUTH, TRUTH_SHA)
    pin(BLENDER)
    truth = read(TRUTH)
    if truth['passed'] is not True or len(truth['eligible']) != 4:
        raise ValueError('independent_truth_incomplete')
    pin_rows(truth['source_pins'])
    for arm, path in BINDINGS.items():
        _, binding = product_for('Q' + arm)
        installation = read(path.parent / 'BUILD_INSTALL.json')
        if (installation['passed'] is not True or installation['binding'] != binding
                or binding['wheel_sha256'] != WHEELS[arm]
                or read(NS / 'inputs/PRODUCT_SCHEMA.json') != read(path.parent / 'PRODUCT_SCHEMA.json')):
            raise ValueError('installed_arm_identity_or_product_schema_changed/' + arm)
        pin(path)
        pin(binding['wheel_path'], WHEELS[arm])
        for name in ('BUILD_INSTALL.json', 'PRODUCT_SCHEMA.json', 'TOOLS_SCHEMA.json'):
            pin(path.parent / name)
        for key in ('installed_files', 'execution_and_input_pins'):
            pin_rows(installation[key])

    prior_names = ('m4_live_source_region_task_003', 'm4_global_local_qualification_001',
                   'm4_cross_scale_live_task_formal_001', 'm4_cross_scale_live_qualification_001',
                   'm4_cross_scale_discovery_001', 'm4_cross_scale_local_first_view_001',
                   'm4_cross_scale_pixel_evidence_001', 'm4_cross_scale_assembly_transfer_001',
                   'm4_dense_panel_sweep_001', 'm4_dense_panel_sweep_formal_001',
                   'm4_dense_region_brief_001', 'm4_bound_blocker_evidence_001')
    for name in prior_names:
        directory = V / name
        for path in directory.rglob('*.py'):
            pin(path)
    preflight = read(NS / 'harness/DISPATCH_PREFLIGHT.json')
    if (not preflight['passed'] or any(preflight[key] != 0 for key in
            ('actual_Blender_processes', 'actual_model_runs', 'actual_raster_attempts'))):
        raise ValueError('registered_zero_model_dispatch_preflight_failed')
    pin_rows(preflight.get('source_pins', []))
    proof = preflight['cli_proof']
    if (proof['CLI_sha256'] != CLI_SHA or proof['CLI_version'] != '0.152.1' or proof['model'] != 'gpt-6.1-sol'
            or proof['reasoning_effort'] != 'medium' or proof['service_tier'] != 'default'
            or Path(proof['Python_path']).resolve() != Path(sys.executable).resolve()):
        raise ValueError('registered_cli_identity_changed')
    pin(proof['CLI_path'], CLI_SHA)
    pin(proof['Python_path'], proof['Python_sha256'])
    pin_rows(proof['execution_sources'])
    login = subprocess.run([proof['CLI_path'], 'login', 'status'], capture_output=True, check=True, timeout=15)
    if b'Logged in using ChatGPT' not in login.stdout + login.stderr:
        raise ValueError('current_fixed_CLI_ChatGPT_login_required')
    for name in ('qualification/PREFLIGHT.json', 'scoring/SCORER_PREFLIGHT.json'):
        if read(NS / name)['passed'] is not True:
            raise ValueError('registered_offline_gate_failed/' + name)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    output = NS / 'FROZEN.json'
    save(output, {'schema': SCHEMA, 'slots': list(ORDER), 'products': PRODUCTS, 'ledger_limits': LIMITS,
                  'plan': PLAN, 'plan_sha256': PLAN_SHA, 'asset_sha256': ASSET_SHA256, 'source_sha256': GEOMETRY_SHA256,
                  'truth_sha256': TRUTH_SHA, 'started_ns': started, 'completed_ns': time.perf_counter_ns(),
                  'task_s': 450, 'owned_s': 600, 'product_diff_files': 0,
                  'request_model': {key: proof[key] for key in ('CLI_version', 'CLI_sha256', 'model',
                                      'reasoning_effort', 'service_tier')},
                  'performance_gate': {'complete_correct_per_arm': 3, 'B_all_blocker_evidence_used_per_slot': 3,
                    'minimum_pairs_with_fewer_blocker_followups': 2, 'minimum_faster_pairs': 2,
                    'complete_paired_median_reduction_min': .10, 'raw_cli_input_output_delta_max': 0},
                  'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze both installed arms, source, score, and eight routes', len(pins), verify_freeze(output))


if __name__ == '__main__':
    freeze()
