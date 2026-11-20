"""Bind the prior validated runtime and exactly one fresh brief-entry slot."""

import ast
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
from admission import LIMITS, OLD, OLD_ADMISSION_SHA, OLD_FREEZE_SHA, SCHEMA, validate_admission
from common import EXTERNAL, PRODUCT_BINDING, ROOT, SOURCE_SHA, asset_identity, read, save, sha


BASE = '9f743878d3a868575c5be43f00a9ba4e011b5161'
PLAN_SHA = 'a03c200bdb509008fb7d0ee2cf41c34573557ab12c925975f5baf26c420c2399'
ORIGINAL_ARCHIVE = Path('D:/he_m4_cross_scale_live_task_formal_001/ORIGINAL_RUNTIME.zip')
ORIGINAL_CONFIGURATION = ORIGINAL_ARCHIVE.parent / 'slots/P1/consumer/ACTUAL_CONFIGURATION.json'
SUBMISSION_CHANGE = b',"response_detail":"brief"'
PROMPT_ANCHOR = b',"include_image":true'
EXACT_COPIES = (
    'bridge.py', 'frame_device.py', 'thin_stdio.py', 'RUBRIC.md',
    'harness/runtime.py', 'harness/mcp_entry.py', 'harness/closure.py',
    'fixture/ASSET_BINDING.json', 'fixture/CURRENT_TRUTH.json', 'fixture/GEOMETRY.json',
    'fixture/ROLE_MAP.json', 'inputs/PROMPT_COMMON.txt', 'inputs/PRODUCT_SCHEMA.json',
)
SCOPED_CHANGES = {
    'harness/common.py': (
        (b'he_m4_cross_scale_live_task_formal_001', b'he_m4_cross_scale_brief_entry_001'),
        (b"{'N1': ('N', 'formal'), 'P1': ('P', 'formal')}", b"{'P1': ('P', 'formal')}")),
    'harness/budget.py': (
        (b"'Blender_start_attempts': 2, 'all_rasters': 24, 'consumer_tasks': 2",
         b"'Blender_start_attempts': 1, 'all_rasters': 12, 'consumer_tasks': 1"),),
    'harness/consumer.py': (
        (b'M4-CROSS-SCALE-LIVE-TASK-FORMAL-001-', b'M4-CROSS-SCALE-BRIEF-ENTRY-001-'),),
    'harness/run_slot.py': (
        (b"validate_admission(label, NS / 'FROZEN.json')",
         b"validate_admission(label, NS / 'FROZEN.json', before_start=True)"),),
    'inputs/PROMPT_P.txt': ((PROMPT_ANCHOR + b'})', PROMPT_ANCHOR + SUBMISSION_CHANGE + b'})'),),
    'inputs/REQUEST.json': ((b'"include_image": true\n}',
                            b'"include_image": true,\n  "response_detail": "brief"\n}'),),
}


def check_scope():
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() != BASE:
        raise ValueError('registered_implementation_base_required_before_freeze')
    if sha(NS / 'inputs/PLAN.md') != PLAN_SHA:
        raise ValueError('plan_bytes_changed')
    for name in (*EXACT_COPIES, *SCOPED_CHANGES):
        predecessor = OLD / name
        expected = subprocess.check_output(
            ['git', 'show', f'{BASE}:{predecessor.relative_to(ROOT).as_posix()}'], cwd=ROOT)
        if predecessor.read_bytes() != expected:
            raise ValueError('historical_baseline_changed/' + name)
        for before, after in SCOPED_CHANGES.get(name, ()):
            if expected.count(before) != 1:
                raise ValueError('one_scoped_change_required/' + name)
            expected = expected.replace(before, after)
        if (NS / name).read_bytes() != expected:
            raise ValueError('unregistered_input_or_runtime_change/' + name)


def freeze():
    started = time.perf_counter_ns()
    if not sys.flags.isolated or not sys.dont_write_bytecode or (EXTERNAL / 'slots').exists():
        raise ValueError('pinned_interpreter_and_fresh_slot_required')
    check_scope()
    previous_freeze = OLD / 'FROZEN.json'
    previous_gate = OLD / 'ADMISSION.json'
    if sha(previous_freeze) != OLD_FREEZE_SHA or sha(previous_gate) != OLD_ADMISSION_SHA:
        raise ValueError('accepted_formal_qualification_changed')
    old_check = ("import sys; from pathlib import Path; p=Path(sys.argv[1]); "
                 "sys.path.insert(0,str(p/'harness')); from admission import validate_admission; "
                 "validate_admission('P1',p/'FROZEN.json')")
    subprocess.run([sys.executable, '-I', '-B', '-c', old_check, str(OLD)], check=True, timeout=30)
    anchors = {}

    def pin(path, digest=None, length=None):
        path = Path(path).resolve()
        row = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        if ((digest is not None and row['sha256'] != digest)
                or (length is not None and row['bytes'] != length)
                or (path in anchors and anchors[path] != row) or path.suffix == '.pyc'):
            raise ValueError('fixed_input_changed/' + str(path))
        anchors[path] = row

    for row in read(previous_freeze)['direct_inputs']:
        pin(row['path'], row['sha256'], row['bytes'])
    pin(previous_freeze, OLD_FREEZE_SHA)
    pin(previous_gate, OLD_ADMISSION_SHA)
    manifest = OLD / 'CONTENT_MANIFEST.json'
    pin(manifest, '9267a6a70897fd44fbe869c22e461e676ad4c10dd1f71e8fb471c88b147ca946')
    for row in read(manifest)['files']:
        pin(OLD / row['path'], row['sha256'], row['bytes'])
    pin(ORIGINAL_ARCHIVE, '38be66d67b301524de5594acab12158342da7c31e2aa75629109e2fe4ff8a89d')
    pin(ORIGINAL_CONFIGURATION, '3974a636471b51abfa16932ef01d554f923dea0d6cf3240d4c0f9b0ef354ff51')
    preflight = NS / 'checks/PREFLIGHT.json'
    checked = read(preflight)
    if checked['passed'] is not True:
        raise ValueError('offline_preflight_did_not_pass')
    for row in checked['source_pins']:
        pin(row['path'], row['sha256'], row['bytes'])
    asset, asset_sha = asset_identity()
    pin(asset, 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce')
    pin(NS / 'fixture/CURRENT_TRUTH.json', '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922')
    binding = read(PRODUCT_BINDING)
    if (binding['source_sha256'] != SOURCE_SHA or len(binding['source_manifest']) != 143
            or not {'brief', 'full'} <= set(read(NS / 'inputs/PRODUCT_SCHEMA.json')
                                          ['inputSchema']['properties']['response_detail']['enum'])):
        raise ValueError('fixed_product_and_original_detail_choices_required')
    requested = read(ORIGINAL_CONFIGURATION)
    shared = read(NS.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    from consumer import consumer_adapter
    _, cli, _ = consumer_adapter()
    if (cli['model'] != requested['requested_model']
            or cli['reasoning_effort'] != requested['requested_effort']
            or cli['service_tier'] != requested['requested_service_tier']
            or cli['CLI_sha256'] != '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
            or Path(cli['Python_path']).resolve() != Path(sys.executable).resolve()):
        raise ValueError('historical_CLI_execution_configuration_changed')
    for row in cli['execution_sources']:
        pin(row['path'], row['sha256'], row['bytes'])
    auth = subprocess.run([cli['CLI_path'], 'login', 'status'], check=True, capture_output=True, timeout=15)
    if b'Logged in using ChatGPT' not in auth.stdout + auth.stderr:
        raise ValueError('fixed_local_ChatGPT_login_required')
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    frozen = NS / 'FROZEN.json'
    save(frozen, {'schema': SCHEMA, 'slots': ['P1'], 'limits': LIMITS,
         'started_ns': started, 'completed_ns': time.perf_counter_ns(),
         'direct_inputs': [anchors[path] for path in sorted(anchors)],
         'previous_formal_freeze_sha256': OLD_FREEZE_SHA,
         'old_plugin_configuration_sha256': sha(ORIGINAL_CONFIGURATION),
         'requested_model': {key: requested[key] for key in
                             ('requested_model', 'requested_effort', 'requested_service_tier')},
         'quotas_before_freeze': {'builder': 0, 'owned': 0, 'consumers': 0}})
    gate = NS / 'ADMISSION.json'
    save(gate, {'schema': SCHEMA, 'passed': True, 'slots': ['P1'], 'freeze_sha256': sha(frozen),
         'asset_sha256': asset_sha, 'product_source_sha256': SOURCE_SHA,
         'evidence': anchors[preflight.resolve()], 'admission_ns': time.perf_counter_ns()})
    validate_admission('P1', frozen, before_start=True)
    print('Frozen and admitted one P1', len(anchors), sha(frozen), sha(gate))


if __name__ == '__main__':
    freeze()
