"""Freeze and run one paired product pilot, then seal its original evidence."""

import argparse
import ast
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
EXTERNAL = Path('D:/he_perf050_readonly_product_pilot_001')
ORDER = ('N1', 'P1')
SCHEMA = 'perf050-readonly-product-pilot-v1'
BASE = '0fc8a2cec2248098d914a37c6d6d4a2fc3d42efa'
PLAN = '1c1bea088b99079dc05fa167e84b854927beb1a8:docs/PERF050_READONLY_PRODUCT_PILOT_001_PLAN.md'
RECOVERY = NS.parent / 'm5_joint_brief_source_projection_recovery_001'
INSTALL = NS.parent / 'm5_joint_brief_source_projection_001/install'
ASSET = Path('D:/he_m5_joint_brief_source_projection_recovery_001/slots/B/native/input.blend')
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
PRODUCT = {
    'commit': '3e6a41afc151162bdde1d4ba2247541a4c9616b4',
    'source_sha256': '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd',
    'wheel_sha256': '8808035c973d2193dd32777c2166855402314f6be0f93ca3479c9f1a7ca85e45',
}
PROMPT = NS / 'inputs/PROMPT.txt'
TRUTH = NS / 'truth/TRUTH.json'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as source:
        from hashlib import file_digest
        return file_digest(source, 'sha256').hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write('\n')


def append(path, value):
    with path.open('a', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def freeze():
    if EXTERNAL.exists() or git('rev-parse', 'HEAD').decode().strip() != BASE or git('diff', '--name-only', BASE):
        raise ValueError('new_pilot_and_zero_product_diff_required')
    if (NS / 'PLAN.md').read_bytes() != git('show', PLAN):
        raise ValueError('original_committed_plan_changed')
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((digest is not None and digest != row['sha256']) or (size is not None and size != row['bytes'])
                or path.suffix == '.pyc'):
            raise ValueError('frozen_input_changed/' + str(path))
        return row

    pin(ASSET, ASSET_SHA)
    recovered = read(RECOVERY / 'DECISION.json')
    manifest = read(RECOVERY / 'RUNTIME_INDEX.json')
    original_asset, = (row for row in manifest['files'] if row['path'] == 'slots/B/native/input.blend')
    if recovered['passed'] is not True or recovered['product'] != PRODUCT or original_asset['sha256'] != ASSET_SHA:
        raise ValueError('recovered_readonly_source_not_proven')
    archive = manifest['archive']
    pin(archive['path'], archive['sha256'], archive['bytes'])
    recovery_freeze = RECOVERY / 'FROZEN.json'
    pin(recovery_freeze, recovered['freeze_sha256'])
    for row in read(recovery_freeze)['direct_inputs']:
        pin(row['path'], row['sha256'], row['bytes'])
    for name in ('DECISION.json', 'RUNTIME_INDEX.json', 'checks/LIVE_REVIEW.json'):
        pin(RECOVERY / name)

    build = read(INSTALL / 'BUILD_INSTALL.json')
    binding = read(INSTALL / 'PRODUCT_RUN_BINDING.json')
    if (build['binding'] != binding or build['passed'] is not True or len(binding['source_manifest']) != 143
            or any(binding[field] != PRODUCT[key] for key, field in (
                ('commit', 'preparation_git'), ('source_sha256', 'source_sha256'), ('wheel_sha256', 'wheel_sha256')))):
        raise ValueError('fixed_installed_candidate_required')
    pin(binding['wheel_path'], PRODUCT['wheel_sha256'])
    for name in ('BUILD_INSTALL.json', 'PRODUCT_RUN_BINDING.json', 'TOOLS_SCHEMA.json', 'PRODUCT_SCHEMA.json'):
        pin(INSTALL / name)
    for row in build['installed_files']:
        pin(row['path'], row['sha256'], row['bytes'])

    receipts = {}
    for path in (TRUTH, NS / 'harness/HOST_PREFLIGHT.json', NS / 'consumer/PREFLIGHT.json'):
        value = read(path)
        if value['passed'] is not True:
            raise ValueError('offline_admission_did_not_pass/' + str(path))
        for row in value.get('source_pins', []):
            pin(row['path'], row['sha256'], row.get('bytes'))
        receipts[path.relative_to(NS).as_posix()] = pin(path)['sha256']
    prompt = PROMPT.read_bytes()
    if not prompt.decode('utf-8').strip() or prompt.startswith(b'\xef\xbb\xbf'):
        raise ValueError('one_valid_common_prompt_required')
    if {b'plugin', b'region_task', b'human_eye_scene_observe'} & set(prompt.lower().split()):
        raise ValueError('common_prompt_leaks_product_route')

    smoke = {}
    for label in ORDER:
        output = subprocess.check_output([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'),
                                          label, '--dispatch-smoke'], cwd=ROOT, timeout=45)
        smoke[label] = json.loads(output)
        cell = smoke[label]
        if (cell['fresh_process_prepared_only'] is not True or cell['slot'] != label or cell['group'] != label[0]
                or cell['schema'] != SCHEMA or cell['product'] != PRODUCT
                or Path(cell['admission']).resolve() != (NS / 'harness/admission.py').resolve()
                or Path(cell['run_root']).resolve() != EXTERNAL.resolve()
                or Path(cell['asset']).resolve() != ASSET.resolve()
                or Path(cell['actual_product_schema']).resolve() != (INSTALL / 'PRODUCT_SCHEMA.json').resolve()
                or Path(cell['mcp_entry']).resolve() != (NS / 'harness/mcp_entry.py').resolve()):
            raise ValueError('actual_dispatch_scope_does_not_match_frozen_pilot/' + label)
    native, plugin = (set(smoke[label]['tools']) for label in ORDER)
    if not native < plugin or plugin - native != {'human_eye_scene_observe'}:
        raise ValueError('both_arms_must_share_normal_tools_with_one_real_product_entry')
    retained_archive = NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py'
    pin(retained_archive)
    pin(sys.executable)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    target = NS / 'FROZEN.json'
    save(target, {'schema': SCHEMA, 'slots': list(ORDER), 'product': PRODUCT, 'asset_sha256': ASSET_SHA,
          'asset_path': str(ASSET.resolve()), 'passed_offline_preflight': True, 'preflights': receipts,
          'prompt_sha256': sha256(prompt).hexdigest(), 'fresh_dispatch': smoke,
          'actual_qualifications_allowed': 0, 'max_model_consumers': 2, 'max_business_per_slot': 12,
          'max_raster_per_slot': 12, 'task_s': 450, 'owned_s': 600, 'replacements': 0,
          'product_delta_files': 0, 'product_builds': 0, 'new_assets': 0,
          'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Frozen', sha(target), len(pins), flush=True)


def sequence():
    sys.path.insert(0, str(NS / 'harness'))
    from admission import can_continue, publication, verify_freeze

    frozen = verify_freeze(NS / 'FROZEN.json')
    if frozen != sha(NS / 'FROZEN.json'):
        raise ValueError('launch_requires_the_same_frozen_digest')
    if EXTERNAL.exists():
        raise ValueError('pilot_runtime_must_be_fresh')
    journal = EXTERNAL / 'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True)
    journal.touch(exist_ok=False)
    all_complete = True
    for label in ORDER:
        append(journal, {'event': 'start', 'label': label, 'started_ns': time.perf_counter_ns(),
                         'freeze_sha256': frozen})
        returned = subprocess.run([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label], cwd=ROOT)
        try:
            result, receipt = publication(label, frozen)
        except Exception as exc:
            append(journal, {'event': 'unconfirmed', 'label': label, 'closed_ns': time.perf_counter_ns(),
                             'error_type': type(exc).__name__, 'error': str(exc), 'exit_code': returned.returncode})
            return 1
        safe = can_continue(result, receipt)
        complete = returned.returncode == 0 and receipt['status'] == 'completed'
        append(journal, {'event': 'publication', 'label': label, 'closed_ns': time.perf_counter_ns(),
                         'exit_code': returned.returncode, 'status': receipt['status'], 'safe_to_continue': safe,
                         'model_consumers': result['model_consumers'], 'result_sha256': receipt['result_sha256']})
        all_complete &= complete
        if not safe:
            return 1
    return 0 if all_complete else 1


def archive():
    target = NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py'
    spec = spec_from_file_location('_readonly_pilot_original_archive', target)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NS, module.EXTERNAL = NS, EXTERNAL
    module.archive()


def seal():
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    if any(not row.startswith(prefix) for row in git('diff', '--name-only', BASE).decode().splitlines()):
        raise ValueError('changes_outside_pilot_namespace')
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(item['path'].endswith(('.pyc', '.bak')) for item in files):
        raise ValueError('unexpected_generated_pilot_file')
    save(manifest, {'count': len(files), 'files': files, 'self_excluded': True})
    print('Sealed', len(files), sha(manifest), flush=True)


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit('Use the pinned interpreter with -I -B.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'sequence', 'archive', 'seal'))
    raise SystemExit(globals()[parser.parse_args().action]())
