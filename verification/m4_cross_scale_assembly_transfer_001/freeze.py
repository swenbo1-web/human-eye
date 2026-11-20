"""Freeze the revised assembly truth, common task and current installed consumer."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCT_GIT, SCHEMA, verify_freeze
from budget import LIMITS
from common import EXTERNAL, PRODUCT_BINDING, ROOT, SLOTS, SOURCE_SHA, asset_identity, read, save, sha


BASE = '069a7b5d96f4f0f38d6340b2d041088ed6174bc8'
PLAN_SHA = 'e8b815993aa82ee1315746d13820873289634e7286cae0a85a8ad1c025a787f4'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
TERMINAL_SHA = '81c84f4d7273cd9045702c7afb95b9c8fc21b02764106ff9d8289c7120e0964c'
V = NS.parent
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
PRIOR_COLD = PRODUCT_BINDING.parents[1]


def verify_prompts():
    common = (NS / 'inputs/PROMPT_COMMON.txt').read_bytes()
    prompts = {(arm): (NS / f'inputs/PROMPT_{arm}.txt').read_bytes() for arm in ('N', 'P')}
    if any(not prompt.startswith(common) or not prompt.endswith(b'\n') or
           len(prompt[len(common):-1]) != 208 or b'\n' in prompt[len(common):-1]
           for prompt in prompts.values()):
        raise ValueError('byte_identical_shared_task_and_matched_starting_lines_required')
    if any(name in prompt for name in (b'N10', b'N11', b'N22', b'5026', b'8835', b'1489')
           for prompt in prompts.values()):
        raise ValueError('consumer_prompt_contains_presently_hidden_truth')
    guidance = prompts['P'][len(common):].decode()
    payload = guidance.split('human_eye_scene_observe(', 1)[1].rsplit(')', 1)[0]
    expected = {'query': {'mode': 'active_observation', 'region_task': {
        'area_min_m2': 0.025, 'area_max_m2': 0.05, 'normal_z_min': 0.75}},
        'include_image': True, 'response_detail': 'brief'}
    if (json.loads(payload) != expected or read(NS / 'inputs/REQUEST.json') != expected
            or b'human_eye_scene_observe' in prompts['N'] or b'scene_data()' not in prompts['N']):
        raise ValueError('ordinary_and_installed_starts_outside_registered_task')


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('pinned_interpreter_and_unused_schedule_required')
    if sha(NS / 'inputs/PLAN.md') != PLAN_SHA:
        raise ValueError('updated_qualification_plan_not_frozen')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() != BASE:
        raise ValueError('registered_evidence_base_not_found')
    verify_prompts()
    for name in ('bridge.py', 'frame_device.py', 'thin_stdio.py', 'harness/runtime.py', 'harness/closure.py'):
        if (NS / name).read_bytes() != (FORMAL / name).read_bytes():
            raise ValueError('registered_shared_runtime_changed/' + name)

    pins = {}

    def pin(path, expected=None, length=None):
        path = Path(path).resolve()
        row = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((expected is not None and expected != row['sha256'])
                or (length is not None and length != row['bytes'])
                or (path in pins and pins[path] != row) or path.suffix == '.pyc'):
            raise ValueError('registered_input_changed/' + str(path))
        pins[path] = row

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row['bytes'])

    fixed = FORMAL / 'FROZEN.json'
    pin(fixed, '267a2af4cd3a360484790b01b801522f6b27cbf68c619dfa8c9addb189d7aa2c')
    pin_rows(read(fixed)['direct_inputs'])
    manifest = PRIOR_COLD / 'CONTENT_MANIFEST.json'
    pin(manifest, '51c647546fc421e853a92894c7f67aed835d3da2a7d57df4272c226c6e21fd38')
    for row in read(manifest)['files']:
        pin(PRIOR_COLD / row['path'], row['sha256'], row['bytes'])
    binding = read(PRODUCT_BINDING)
    build = read(PRODUCT_BINDING.parent / 'BUILD_INSTALL.json')
    if (binding['preparation_git'] != PRODUCT_GIT or binding['source_sha256'] != SOURCE_SHA
            or len(binding['source_manifest']) != 143 or build['binding'] != binding or build['passed'] is not True
            or read(NS / 'inputs/PRODUCT_SCHEMA.json') != read(PRODUCT_BINDING.parent / 'PRODUCT_SCHEMA.json')):
        raise ValueError('fixed_143_source_installed_product_disagrees')
    pin_rows(build['installed_files'])
    pin_rows(build['execution_and_input_pins'])
    asset, digest = asset_identity()
    pin(asset, ASSET_SHA)
    asset_record = read(NS / 'fixture/ASSET_BINDING.json')
    if asset_record['archived_terminal']['sha256'] != TERMINAL_SHA:
        raise ValueError('verified_original_assembly_terminal_changed')
    pin_rows([asset_record['archived_terminal']])
    pin_rows(asset_record['source_pins'])
    truth = read(NS / 'fixture/CURRENT_TRUTH.json')
    if (truth['asset_sha256'] != ASSET_SHA or truth['passed'] is not True
            or truth['counts'] != {'objects': 28, 'vertices': 416, 'triangles': 744}
            or {row['object_name']: set(row['eligible_complete_views']) for row in truth['eligible']} !=
               {'N10': {'TOP'}, 'N11': set(), 'N22': set(truth['directions'])}):
        raise ValueError('fixed_assembly_truth_not_verified')
    pin_rows(truth.get('source_pins', truth.get('oracle_source_pins', [])))
    preflight = read(NS / 'checks/HARNESS_PREFLIGHT.json')
    if preflight['passed'] is not True:
        raise ValueError('same_dependency_and_CLI_contract_preflight_failed')
    pin_rows(preflight['source_pins'])

    shared = read(V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    from consumer import consumer_adapter
    _, cli, _ = consumer_adapter()
    if (cli['CLI_sha256'] != '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
            or cli['CLI_version'] != '0.152.1' or cli['model'] != 'gpt-6.1-sol'
            or cli['reasoning_effort'] != 'medium' or cli['service_tier'] != 'default'
            or Path(cli['Python_path']).resolve() != Path(sys.executable).resolve()):
        raise ValueError('original_CLI_request_configuration_changed')
    pin_rows(cli['execution_sources'])
    auth = subprocess.run([cli['CLI_path'], 'login', 'status'], check=True, capture_output=True, timeout=15)
    if b'Logged in using ChatGPT' not in auth.stdout + auth.stderr:
        raise ValueError('prescribed_local_ChatGPT_login_required')
    mandatory = ('qualification/diagnostic.py', 'qualification/qualify.py', 'scoring/score.py')
    if not all((NS / name).is_file() for name in mandatory):
        raise ValueError('independent_registration_and_quality_checkers_required')
    for item in NS.rglob('*'):
        if item.is_file():
            if item.suffix == '.py':
                ast.parse(item.read_bytes(), filename=str(item))
            pin(item)
    frozen = NS / 'FROZEN.json'
    save(frozen, {'schema': SCHEMA, 'slots': list(SLOTS), 'ledger_limits': LIMITS,
         'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'owned_s': 600, 'task_s': 450,
         'asset_sha256': digest, 'terminal_sha256': TERMINAL_SHA, 'product_git': PRODUCT_GIT,
         'product_source_sha256': SOURCE_SHA, 'product_diff_files': 0,
         'qualification_gates': ['actual_N22_complete_witness', 'N10_actual_TOP_pixel_outcome',
                                 'N11_finite_geometric_occlusion', 'current_identity', 'CLI_delivery'],
         'model_ceiling': 2, 'shared_guidance_UTF8_bytes': 208,
         'direct_inputs': [pins[key] for key in sorted(pins)]})
    verify_freeze(frozen)
    print('Froze QN, QP, N1, P1', len(pins), sha(frozen))


if __name__ == '__main__':
    freeze()
