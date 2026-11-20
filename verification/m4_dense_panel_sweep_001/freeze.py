"""Freeze the one dense-panel comparison and its installed tool identities."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import PRODUCT, SCHEMA, verify_freeze
from budget import LIMITS
from common import (ASSET, ASSET_SHA256, ASSEMBLY, EXTERNAL, GEOMETRY, GEOMETRY_SHA256, ORDER,
                    PRODUCT_BINDING, PROJECTED, ROOT, asset_identity, read, save, sha)


BASE = '17bce4aa30f8cf9a3d044c0eb856935a8dccf9d9'
PLAN = '30abaf94d884127b2317e8208dafee52e8235c7a6f988e278c2804300adcf039'
ORDERED_CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/'
                   '0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
MANIFESTS = (
    (PROJECTED, '4655f4c824a46f6fc59cec1e0c629f7a4181318c5b7825f1718efc88836e0023',
     '163706e7167ca02220412321d268e53cb0f877537a708a4dd05ecabaf9e37775'),
    (ASSEMBLY, '5c42ef83e0bc6761798d0c18d6210684a59216eca3071202853fcf3d2adced69',
     '0be1c09cf34ce3392b02a5698db0922a4ed05a39a62ab6194c75e007853213b3'),
)


def prompt_contract(truth, request):
    common = (NS / 'inputs/PROMPT_COMMON.txt').read_bytes()
    arms = {arm: (NS / f'inputs/PROMPT_{arm}.txt').read_bytes() for arm in ('N', 'P')}
    names = [row['object_name'].encode() for row in truth['eligible']]
    expected = {'query': {'mode': 'active_observation',
                'region_task': {'area_min_m2': 1.0, 'area_max_m2': 1.0, 'normal_z_min': 0.0}},
                'include_image': True, 'response_detail': 'brief'}
    if (not common.endswith(b'\n\n') or request != expected
            or any(not prompt.startswith(common) or prompt[-1:] != b'\n'
                   or len(prompt[len(common):-1]) != 204 or b'\n' in prompt[len(common):-1]
                   or any(name in prompt for name in names) for prompt in arms.values())):
        raise ValueError('freeze_identical_task_single_matched_start_without_truth')
    starting = arms['P'][len(common):].decode()
    arguments = starting.split('human_eye_scene_observe(', 1)[1].rsplit(')', 1)[0]
    if (json.loads(arguments) != request or b'scene_data()' not in arms['N']
            or b'human_eye_scene_observe' in arms['N']):
        raise ValueError('native_and_plugin_starting_guidance_binding_changed')


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('isolated_interpreter_and_unused_schedule_required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    if head != BASE:
        raise ValueError('wrong_evidence_base')
    truth = read(NS / 'truth/CURRENT_TRUTH.json')
    if (truth['asset_sha256'] != ASSET_SHA256 or truth['geometry_sha256'] != GEOMETRY_SHA256
            or truth['counts'] != {'objects': 14, 'vertices': 3478, 'triangles': 6148}
            or truth['passed'] is not True):
        raise ValueError('independent_truth_not_bound_to_fixed_full_geometry')
    prompt_contract(truth, read(NS / 'inputs/REQUEST.json'))

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        believed = pins.get(path)
        if believed is None:
            believed = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((digest is not None and believed['sha256'] != digest)
                or (size is not None and believed['bytes'] != size) or path.suffix == '.pyc'):
            raise ValueError('registered_input_changed/' + str(path))
        pins[path] = believed

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    pin(NS / 'inputs/PLAN.md', PLAN)
    asset, asset_sha = asset_identity()
    if asset != ASSET.resolve() or asset_sha != ASSET_SHA256:
        raise ValueError('registered_independent_asset_required')
    pin(asset, asset_sha)
    pin(GEOMETRY, GEOMETRY_SHA256)
    pin_rows(truth['source_pins'])
    for directory, freeze_digest, manifest_digest in MANIFESTS:
        frozen = directory / 'FROZEN.json'
        manifest = directory / 'CONTENT_MANIFEST.json'
        pin(frozen, freeze_digest)
        pin(manifest, manifest_digest)
        pin_rows(read(frozen)['direct_inputs'])
        for row in read(manifest)['files']:
            pin(directory / row['path'], row['sha256'], row['bytes'])

    pinned = read(PRODUCT_BINDING)
    install = read(PRODUCT_BINDING.parent / 'BUILD_INSTALL.json')
    if (pinned['preparation_git'] != PRODUCT['commit'] or pinned['source_sha256'] != PRODUCT['source_sha256']
            or len(pinned['source_manifest']) != 143 or pinned != install['binding'] or install['passed'] is not True
            or any((NS / 'inputs' / name).read_bytes() != (PRODUCT_BINDING.parent / name).read_bytes()
                   for name in ('PRODUCT_SCHEMA.json', 'TOOLS_SCHEMA.json'))):
        raise ValueError('unverified_same_143_source_install_or_tool_schema')
    pin(PRODUCT_BINDING)
    pin_rows(install['installed_files'])
    pin(ORDERED_CLI, CLI_SHA)
    version = subprocess.check_output([str(ORDERED_CLI), '--version'], timeout=15).decode().strip()
    login = subprocess.run([str(ORDERED_CLI), 'login', 'status'], capture_output=True, check=True, timeout=15)
    if version != 'codex-cli 0.152.1' or b'Logged in using ChatGPT' not in login.stdout + login.stderr:
        raise ValueError('fixed_cli_and_local_pro_login_required')

    for name in ('checks/qualify_product.py', 'truth/CURRENT_TRUTH.json', 'scoring/RUBRIC.md'):
        if not (NS / name).is_file():
            raise ValueError('registered_assessment_required/' + name)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    path = NS / 'FROZEN.json'
    save(path, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'product': PRODUCT,
                'product_diff_files': 0, 'asset_sha256': ASSET_SHA256, 'source_geometry_sha256': GEOMETRY_SHA256,
                'truth_sha256': sha(NS / 'truth/CURRENT_TRUTH.json'), 'owned_s': 600, 'task_s': 450,
                'started_ns': started, 'completed_ns': time.perf_counter_ns(),
                'first_product_qualification_required': True, 'model_slots_max': 6,
                'consumer': {'CLI_path': str(ORDERED_CLI), 'CLI_sha256': CLI_SHA, 'CLI_version': '0.152.1',
                             'login': 'ChatGPT', 'requested_model': 'gpt-6.1-sol', 'reasoning_effort': 'medium',
                             'service_tier': 'default', 'matched_starting_line_UTF8_bytes': 204},
                'direct_inputs': [pins[name] for name in sorted(pins)]})
    print('Froze first QP qualification and the ordered comparison', len(pins), verify_freeze())


if __name__ == '__main__':
    freeze()
