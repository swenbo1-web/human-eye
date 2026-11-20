"""Freeze the sole joint measurement projection and the single live qualification."""

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


BASE = '9552d5c7103d9d8a08799adde96534990c6815f9'
CANDIDATE = '3e6a41afc151162bdde1d4ba2247541a4c9616b4'
SOURCE = '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd'
WHEEL = '8808035c973d2193dd32777c2166855402314f6be0f93ca3479c9f1a7ca85e45'
CHANGED = 'human_eye_plugin/live_spatial_mcp.py'
HISTORY = '6562ba5ef6569512465adad2725f2bfa50748423'
PLAN = '5cd8169ed178e01943010bcd2a150273d927db94:docs/M5_JOINT_BRIEF_SOURCE_PROJECTION_001_PLAN.md'
OLD = NS.parent / 'm5_global_observe_measure_qualification_001'
OLD_B = NS.parent / 'm4_dense_raster_cross_001/install/PRODUCT_RUN_BINDING.json'
OLD_FREEZE = '023256f3195113d417dad1fafb3f3a05c6df65356bb0c8326f9e7e0601cd9246'
OLD_MANIFEST = 'f8263958af7d011ec854e079dc110bc454b44115de53d0c81777934e2730dc5b'
OLD_ARCHIVE = '8d584ee6444fc46f7d2756057178ff8bee0bf13e2902c37e43d2772e8e91cfdd'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or any(
            (EXTERNAL / name).exists() for name in ('slots', 'budget', 'preflight')):
        raise ValueError('fresh_qualification_run_and_isolated_interpreter_required')
    if (git('rev-parse', 'HEAD').decode().strip() != HISTORY or
            git('rev-list', '--parents', '-n', '1', CANDIDATE).decode().split() != [CANDIDATE, BASE]
            or git('diff', '--name-only', BASE, CANDIDATE).decode().splitlines() != [CHANGED]):
        raise ValueError('the_experiment_requires_the_registered_one_file_candidate')
    plan = NS / 'PLAN.md'
    if plan.read_bytes() != git('show', PLAN):
        raise ValueError('original_registered_plan_changed')

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((digest is not None and row['sha256'] != digest) or (size is not None and row['bytes'] != size)
                or path.suffix == '.pyc'):
            raise ValueError('frozen_input_changed/' + str(path))

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    asset, asset_sha = asset_identity()
    if asset.resolve() != ASSET.resolve() or asset_sha != ASSET_SHA256:
        raise ValueError('the_same_original_28_object_asset_is_required')
    for path, digest in ((plan, None), (asset, ASSET_SHA256), (GEOMETRY, GEOMETRY_SHA256),
                         (TRUTH, None), (OLD / 'FROZEN.json', OLD_FREEZE),
                         (OLD / 'CONTENT_MANIFEST.json', OLD_MANIFEST)):
        pin(path, digest)
    bind(read(OLD / 'FROZEN.json')['direct_inputs'])
    for item in read(OLD / 'CONTENT_MANIFEST.json')['files']:
        pin(OLD / item['path'], item['sha256'], item['bytes'])
    old_arc = read(OLD / 'RUNTIME_INDEX.json')['archive']
    pin(old_arc['path'], OLD_ARCHIVE, old_arc['bytes'])
    for request in REQUESTS.values():
        pin(request)

    binding, base = read(PRODUCT_BINDING), read(OLD_B)
    build = read(PRODUCT_BINDING.with_name('BUILD_INSTALL.json'))
    left, right = ({row['path']: row['sha256'] for row in item['source_manifest']} for item in (base, binding))
    if (binding['preparation_git'] != CANDIDATE or binding['source_sha256'] != SOURCE or binding['wheel_sha256'] != WHEEL
            or base['preparation_git'] != BASE or len(left) != 143 or left.keys() != right.keys()
            or [key for key in left if left[key] != right[key]] != [CHANGED]
            or build['passed'] is not True or build['binding'] != binding
            or build['tool_schema_matches_historical_actual_directory'] is not True):
        raise ValueError('registered_installed_sources_or_tool_definition_changed')
    for path in (PRODUCT_BINDING, OLD_B, CATALOGUE, PRODUCT_SCHEMA):
        pin(path)
    pin(binding['wheel_path'], WHEEL)
    for key in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        bind(build[key])

    offline = NS / 'checks/OFFLINE_CONTROLS.json'
    dispatch = NS / 'harness/DISPATCH_PREFLIGHT.json'
    scorer = NS / 'checks/LIVE_PREFLIGHT.json'
    for receipt in (offline, dispatch, scorer):
        value = read(receipt)
        if value['passed'] is not True:
            raise ValueError('the_registered_offline_gate_did_not_pass/' + receipt.name)
        pin(receipt)
        bind(value.get('source_pins', []))

    smoke = json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(NS / 'run_sequence.py'),
        '--dispatch-smoke'], cwd=ROOT, timeout=20))
    if (smoke['fresh_process_prepared_only'] is not True or smoke['order'] != list(ORDER) or smoke['schema'] != SCHEMA
            or Path(smoke['admission']).resolve() != (NS / 'harness/admission.py').resolve()
            or Path(smoke['run_root']).resolve() != EXTERNAL.resolve() or smoke['current_product'] != registered_product()):
        raise ValueError('fresh_top_entry_must_bind_current_admission')
    pin(sys.executable)
    pin(NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py')
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)

    output = NS / 'FROZEN.json'
    save(output, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'product': registered_product(),
        'asset_sha256': ASSET_SHA256, 'terminal_source_sha256': GEOMETRY_SHA256,
        'historical_false_gate_freeze_sha256': OLD_FREEZE, 'only_changed_product_file': CHANGED,
        'offline_controls_sha256': sha(offline), 'dispatch_preflight_sha256': sha(dispatch),
        'live_preflight_sha256': sha(scorer), 'fresh_sequence_preflight': smoke,
        'started_ns': started, 'completed_ns': time.perf_counter_ns(),
        'max_outer_text_UTF8_bytes': 10800, 'task_s': 450, 'owned_s': 600,
        'fixed_CLI': {'version': '0.152.1', 'MCP_bytes': 12000, 'history_approximate_tokens': 3000,
                      'header_bytes': [33, 34, 35]},
        'model_consumers': 0, 'asset_rebuilds': 0, 'replacements': 0,
        'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze the single joint brief qualification', len(pins), verify_freeze(output), flush=True)


if __name__ == '__main__':
    freeze()
