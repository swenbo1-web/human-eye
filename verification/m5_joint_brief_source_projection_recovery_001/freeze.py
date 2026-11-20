"""Freeze the one recovery slot against the sealed candidate and real preflights."""

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


PREVIOUS = NS.parent / 'm5_joint_brief_source_projection_001'
HISTORY = 'c6dba771579f6cab70b1d7ee4921fdd53dc72c59'
PLAN = '8ddda37d40e17f18bbbed5632346fb911b2d9daf:docs/M5_JOINT_BRIEF_SOURCE_PROJECTION_RECOVERY_001_PLAN.md'
FAILED_FREEZE = '7b6418b9431b748ba8d6b8bc9cbadb44f968de0d598af15acfe2204fd258ea56'
FAILED_RESULT = '68f2a461d8ceac7bc39eb66a71c8072fa51d8caf005287c3e3ba25f5dc884e47'
FAILED_MANIFEST = '601b4e95582e2dc800d04669c389dbfda3086bd3b436b142aabc702a76d4ff2f'
FAILED_ARCHIVE = '9f1896c69c26741b11e97436cdf04ee2a59d741a3d25f06dca5ca88a591cc694'
FIXED_PRODUCT = {
    'commit': '3e6a41afc151162bdde1d4ba2247541a4c9616b4',
    'source_sha256': '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd',
    'wheel_sha256': '8808035c973d2193dd32777c2166855402314f6be0f93ca3479c9f1a7ca85e45',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or EXTERNAL.exists():
        raise ValueError('fresh_recovery_root_and_isolated_interpreter_required')
    if git('rev-parse', 'HEAD').decode().strip() != HISTORY or git('diff', '--name-only', HISTORY):
        raise ValueError('recovery_requires_original_evidence_and_no_product_changes')
    if registered_product() != FIXED_PRODUCT or ORDER != ('B',):
        raise ValueError('qualification_product_or_slot_changed')
    plan = NS / 'PLAN.md'
    if plan.read_bytes() != git('show', PLAN):
        raise ValueError('registered_recovery_plan_changed')
    if PRODUCT_SCHEMA.resolve() != (PREVIOUS / 'install/PRODUCT_SCHEMA.json').resolve():
        raise ValueError('startup_and_freeze_must_use_the_original_canonical_schema')

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((digest is not None and row['sha256'] != digest) or
                (size is not None and row['bytes'] != size) or path.suffix == '.pyc'):
            raise ValueError('frozen_input_changed/' + str(path))

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    asset, asset_sha = asset_identity()
    if asset.resolve() != ASSET.resolve() or asset_sha != ASSET_SHA256:
        raise ValueError('the_same_original_28_object_asset_is_required')
    failed_freeze = PREVIOUS / 'FROZEN.json'
    failed_manifest = PREVIOUS / 'CONTENT_MANIFEST.json'
    for path, digest in ((plan, None), (asset, ASSET_SHA256), (GEOMETRY, GEOMETRY_SHA256),
                         (TRUTH, None), (failed_freeze, FAILED_FREEZE), (failed_manifest, FAILED_MANIFEST)):
        pin(path, digest)
    old = read(failed_freeze)
    failure = read(PREVIOUS / 'DECISION.json')
    if (old['product'] != FIXED_PRODUCT or failure['freeze_sha256'] != FAILED_FREEZE
            or failure['passed'] is not False or failure['actual_slot_status'] != 'failed'
            or failure['original_slot_identity']['result_sha256'] != FAILED_RESULT
            or failure['actual_ledger_counts']['Blender_start_attempts'] != 1
            or failure['actual_ledger_counts']['business_admissions'] != 0):
        raise ValueError('historical_failed_slot_changed')
    bind(old['direct_inputs'])
    for item in read(failed_manifest)['files']:
        pin(PREVIOUS / item['path'], item['sha256'], item['bytes'])
    originals = read(PREVIOUS / 'RUNTIME_INDEX.json')
    if originals['count'] != len(originals['files']) or originals['count'] != 42:
        raise ValueError('original_failure_archive_membership_changed')
    old_arc = originals['archive']
    pin(old_arc['path'], FAILED_ARCHIVE, old_arc['bytes'])
    for item in originals['files']:
        pin(Path(old_arc['path']).parent / item['path'], item['sha256'], item['bytes'])

    binding = read(PRODUCT_BINDING)
    build = read(PRODUCT_BINDING.with_name('BUILD_INSTALL.json'))
    if (len(binding['source_manifest']) != 143 or build['passed'] is not True
            or build['binding'] != binding or build['tool_schema_matches_historical_actual_directory'] is not True):
        raise ValueError('canonical_previously_installed_product_required')
    for path in (PRODUCT_BINDING, CATALOGUE, PRODUCT_SCHEMA, *REQUESTS.values()):
        pin(path)
    pin(binding['wheel_path'], FIXED_PRODUCT['wheel_sha256'])
    for key in ('installed_files', 'execution_and_input_pins'):
        bind(build[key])

    receipts = {}
    for path in (NS / 'harness/DISPATCH_PREFLIGHT.json', NS / 'checks/LIVE_PREFLIGHT.json'):
        value = read(path)
        if value['passed'] is not True:
            raise ValueError('recovery_offline_preflight_failed/' + path.name)
        pin(path)
        bind(value['source_pins'])
        receipts[path.name] = sha(path)

    handshake = read(NS / 'harness/DISPATCH_PREFLIGHT.json')['actual_startup_handshake_replay']
    if (Path(handshake['schema_path']).resolve() != PRODUCT_SCHEMA.resolve()
            or handshake['schema_sha256'] != sha(PRODUCT_SCHEMA)
            or Path(handshake['catalogue_path']).resolve() != CATALOGUE.resolve()
            or handshake['catalogue_sha256'] != sha(CATALOGUE)
            or handshake['source_sha256'] != FIXED_PRODUCT['source_sha256']
            or handshake['handshake_methods'] != ['initialize', 'notifications/initialized', 'tools/list']):
        raise ValueError('replayed_startup_must_read_the_frozen_schema_and_catalogue')

    smoke = json.loads(subprocess.check_output([sys.executable, '-I', '-B', str(NS / 'run_sequence.py'),
        '--dispatch-smoke'], cwd=ROOT, timeout=20))
    if (smoke['fresh_process_prepared_only'] is not True or smoke['order'] != list(ORDER)
            or smoke['schema'] != SCHEMA or smoke['current_product'] != FIXED_PRODUCT
            or Path(smoke['admission']).resolve() != (NS / 'harness/admission.py').resolve()
            or Path(smoke['run_root']).resolve() != EXTERNAL.resolve()):
        raise ValueError('fresh_top_entry_must_bind_the_recovery_admission')

    pin(sys.executable)
    pin(NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py')
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    output = NS / 'FROZEN.json'
    save(output, {'schema': SCHEMA, 'slots': list(ORDER), 'ledger_limits': LIMITS, 'product': FIXED_PRODUCT,
        'asset_sha256': ASSET_SHA256, 'terminal_source_sha256': GEOMETRY_SHA256,
        'canonical_product_schema': {'path': str(PRODUCT_SCHEMA.resolve()), 'sha256': sha(PRODUCT_SCHEMA)},
        'historical_failed_freeze_sha256': FAILED_FREEZE, 'historical_failed_result_sha256': FAILED_RESULT,
        'historical_failed_archive_sha256': FAILED_ARCHIVE, 'preflights': receipts, 'fresh_dispatch': smoke,
        'started_ns': started, 'completed_ns': time.perf_counter_ns(), 'max_outer_text_UTF8_bytes': 10800,
        'task_s': 450, 'owned_s': 600,
        'fixed_CLI': {'version': '0.152.1', 'MCP_bytes': 12000, 'history_approximate_tokens': 3000,
                      'header_bytes': [33, 34, 35]},
        'product_delta_files': 0, 'product_builds': 0, 'model_consumers': 0, 'asset_rebuilds': 0, 'replacements': 0,
        'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze the sole recovery slot', len(pins), verify_freeze(output), flush=True)


if __name__ == '__main__':
    freeze()
