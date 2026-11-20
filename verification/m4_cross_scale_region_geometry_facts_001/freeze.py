"""Bind the one product delta, installation, historical control and offline receipts."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import (CANDIDATE, GATE_INPUTS, LIMITS, OLD, OLD_ADMISSION_SHA, OLD_FREEZE_SHA,
                       SCHEMA, validate_admission)
from common import EXTERNAL, PRODUCT_BINDING, ROOT, SOURCE_SHA, asset_identity, read, save, sha


BASE = '108c01fea0f188d587a14c690a4e6f5fd69a0c7b'
PRODUCT_FILE = 'human_eye_plugin/live_spatial_mcp.py'
PLAN_SHA = '5a74cb40efabb00a21a72a7b16d2ca7baf82237bc6685f661dabb3e2df7a1711'
HISTORICAL_RUN = Path('D:/he_m4_cross_scale_brief_entry_001')
OLD_PRODUCT_SHA = '0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b'


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('pinned_interpreter_and_fresh_slot_required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    changes = subprocess.check_output(['git', 'diff', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    if head != CANDIDATE or changes != [PRODUCT_FILE] or sha(NS / 'inputs/PLAN.md') != PLAN_SHA:
        raise ValueError('registered_plan_or_candidate_scope_changed')
    for name in ('inputs/PROMPT_P.txt', 'inputs/PROMPT_COMMON.txt', 'inputs/REQUEST.json',
                 'inputs/PRODUCT_SCHEMA.json', 'RUBRIC.md', 'bridge.py', 'frame_device.py',
                 'thin_stdio.py', 'harness/runtime.py', 'harness/run_slot.py', 'harness/budget.py',
                 'harness/mcp_entry.py', 'harness/closure.py'):
        original = subprocess.check_output(
            ['git', 'show', f'{BASE}:{(OLD / name).relative_to(ROOT).as_posix()}'], cwd=ROOT)
        if original != (NS / name).read_bytes() or original != (OLD / name).read_bytes():
            raise ValueError('unchanged_task_or_runtime_bytes_required/' + name)

    pins = {}

    def pin(path, expected=None, length=None):
        path = Path(path).resolve()
        row = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((expected is not None and expected != row['sha256'])
                or (length is not None and length != row['bytes'])
                or (path in pins and pins[path] != row) or path.suffix == '.pyc'):
            raise ValueError('pinned_input_changed/' + str(path))
        pins[path] = row

    def pin_rows(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row['bytes'])

    previous_freeze = OLD / 'FROZEN.json'
    previous_gate = OLD / 'ADMISSION.json'
    pin(previous_freeze, OLD_FREEZE_SHA)
    pin(previous_gate, OLD_ADMISSION_SHA)
    pin_rows(read(previous_freeze)['direct_inputs'])
    manifest = OLD / 'CONTENT_MANIFEST.json'
    pin(manifest, '69da995555d4c997127aaf7332ee2abc7b13a9a7fd948bc07552d010277401d2')
    for row in read(manifest)['files']:
        pin(OLD / row['path'], row['sha256'], row['bytes'])
    pin(HISTORICAL_RUN / 'ORIGINAL_RUNTIME.zip',
        '1fa86e8346e08c63fa4f3d98e992d239391da0bc7dcca6ed15b6b5f3ba51635e')
    original_config = HISTORICAL_RUN / 'slots/P1/consumer/ACTUAL_CONFIGURATION.json'
    pin(original_config, '0cabd71e86ca22d0bce3220ed5beccc9b0a2b3d53df7cfd27d8526b7f9172f5a')
    older_check = ("import sys; from pathlib import Path; p=Path(sys.argv[1]); "
                   "sys.path.insert(0,str(p/'harness')); from admission import validate_admission; "
                   "validate_admission('P1',p/'FROZEN.json')")
    subprocess.run([sys.executable, '-I', '-B', '-c', older_check, str(OLD)], check=True, timeout=30)

    product = read(PRODUCT_BINDING)
    old_binding = NS.parent / 'm4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
    old_product = read(old_binding)
    old_sources = {row['path']: row for row in old_product['source_manifest']}
    new_sources = {row['path']: row for row in product['source_manifest']}
    if (old_product['source_sha256'] != OLD_PRODUCT_SHA or len(old_sources) != 143 or len(new_sources) != 143
            or set(old_sources) != set(new_sources)
            or {path for path in old_sources if old_sources[path] != new_sources[path]} != {PRODUCT_FILE}
            or product['preparation_git'] != CANDIDATE
            or product['dependency_root'] != old_product['dependency_root']
            or not Path(product['install_root']).resolve().is_relative_to((EXTERNAL / 'install').resolve())
            or read(NS / 'install/PRODUCT_SCHEMA.json') != read(NS / 'inputs/PRODUCT_SCHEMA.json')):
        raise ValueError('candidate_is_not_the_one_file_delta_on_the_historical_install')
    for name, row in new_sources.items():
        pin(Path(product['install_root']) / name, row['sha256'], row.get('bytes'))
    pin(ROOT / PRODUCT_FILE)
    build = read(NS / 'install/BUILD_INSTALL.json')
    if (build['passed'] is not True or build['binding'] != product
            or build['tool_schema_matches_historical_actual_directory'] is not True):
        raise ValueError('candidate_build_or_actual_tools_list_is_not_bound')
    pin_rows(build['installed_files'])
    pin_rows(build['execution_and_input_pins'])
    pin_rows([build['initial_transplant_preflight']['retained_stage']])

    for name in GATE_INPUTS[:-1]:
        report = read(NS / name)
        if report['passed'] is not True:
            raise ValueError('engineering_preflight_failed/' + name)
        pin_rows(report['source_pins'])
    asset, asset_sha = asset_identity()
    pin(asset, 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce')
    pin(NS / 'fixture/CURRENT_TRUTH.json', '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922')
    shared = read(NS.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), product['dependency_root'], shared['dependency_root']]
    from consumer import consumer_adapter
    _, cli, _ = consumer_adapter()
    request = read(original_config)
    expected_settings = {'model': request['requested_model'], 'reasoning_effort': request['requested_effort'],
                         'service_tier': request['requested_service_tier']}
    if (any(cli[key] != value for key, value in expected_settings.items())
            or cli['CLI_sha256'] != '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
            or Path(cli['Python_path']).resolve() != Path(sys.executable).resolve()):
        raise ValueError('historical_CLI_execution_configuration_changed')
    pin_rows(cli['execution_sources'])
    auth = subprocess.run([cli['CLI_path'], 'login', 'status'], check=True, capture_output=True, timeout=15)
    if b'Logged in using ChatGPT' not in auth.stdout + auth.stderr:
        raise ValueError('fixed_local_ChatGPT_login_required')
    for path in NS.rglob('*'):
        if path.is_file() and path != NS / 'checks/review_live.py':
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    frozen = NS / 'FROZEN.json'
    save(frozen, {'schema': SCHEMA, 'slots': ['P1'], 'limits': LIMITS, 'candidate_commit': CANDIDATE,
         'started_ns': started, 'completed_ns': time.perf_counter_ns(),
         'direct_inputs': [pins[path] for path in sorted(pins)],
         'historical_freeze_sha256': OLD_FREEZE_SHA, 'historical_configuration_sha256': sha(original_config),
         'requested_model': expected_settings, 'quotas_before_freeze': {'builder': 0, 'owned': 0, 'consumers': 0}})
    gate = NS / 'ADMISSION.json'
    save(gate, {'schema': SCHEMA, 'passed': True, 'slots': ['P1'], 'freeze_sha256': sha(frozen),
         'asset_sha256': asset_sha, 'product_source_sha256': SOURCE_SHA, 'product_binding_sha256': sha(PRODUCT_BINDING),
         'gate_evidence_sha256': {name: sha(NS / name) for name in GATE_INPUTS},
         'admission_ns': time.perf_counter_ns()})
    validate_admission('P1', frozen, before_start=True)
    print('Admitted one candidate P1', len(pins), sha(frozen), sha(gate))


if __name__ == '__main__':
    freeze()
