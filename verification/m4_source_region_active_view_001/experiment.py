"""Freeze the registered candidate and run the two unchanged real requests."""

import argparse
import ast
from hashlib import file_digest
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
RUN = Path('D:/he_m4_source_region_active_view_001')
ASSET = Path('D:/he_m5_joint_brief_source_projection_recovery_001/slots/B/native/input.blend')
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
PILOT = NS.parent / 'perf050_readonly_product_pilot_001'
OLD_RUNTIME = Path('D:/he_perf050_readonly_product_pilot_001')
REQUEST = OLD_RUNTIME / 'slots/P1/owner/tool_03/PRODUCT_REQUEST.json'
PLAN = 'd299814cb1f06eac64646d7f1814d4574688837a:docs/M4_SOURCE_REGION_ACTIVE_VIEW_001_PLAN.md'
HISTORY = 'd59b954f41e767179d1e9d2a265958de00f11b2e'
BASE_BINDING = NS.parent / 'm5_joint_brief_source_projection_001/install/PRODUCT_RUN_BINDING.json'
NEW_BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'
BASE = {'commit': '3e6a41afc151162bdde1d4ba2247541a4c9616b4',
        'source_sha256': '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd',
        'wheel_sha256': '8808035c973d2193dd32777c2166855402314f6be0f93ca3479c9f1a7ca85e45'}
ORDER = ('A', 'B')
SCHEMA = 'm4-source-region-active-view-v1'
RETAINED_ARCHIVE = NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with Path(path).open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def write(path, value, mode='x'):
    with path.open(mode, encoding='utf-8', newline='\n') as output:
        json.dump(value, output, ensure_ascii=False, indent=2 if mode == 'x' else None, allow_nan=False)
        output.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def identity(path):
    record = read(path)
    return {k: record[field] for k, field in (
        ('commit', 'preparation_git'), ('source_sha256', 'source_sha256'), ('wheel_sha256', 'wheel_sha256'))}


def freeze():
    if RUN.exists() or git('rev-parse', 'HEAD').decode().strip() != HISTORY or git('diff', '--name-only', HISTORY):
        raise ValueError('fresh_recovery_run_and_isolated_evidence_branch_required')
    if (NS / 'PLAN.md').read_bytes() != git('show', PLAN):
        raise ValueError('registered_active_view_plan_changed')
    products = {'A': identity(BASE_BINDING), 'B': identity(NEW_BINDING)}
    candidate = products['B']['commit']
    lineage = git('rev-list', '--parents', '-n', '1', candidate).decode().split()
    build = read(NEW_BINDING.with_name('BUILD_INSTALL.json'))
    changed = git('diff', '--name-only', BASE['commit'], candidate).decode().splitlines()
    if (products['A'] != BASE or lineage != [candidate, BASE['commit']] or build['passed'] is not True
            or build['binding'] != read(NEW_BINDING) or len(build['binding']['source_manifest']) != 143
            or changed != build['binding']['changed_product_sources']
            or build['tool_schema_matches_historical_actual_directory'] is not True):
        raise ValueError('same_baseline_and_single_isolated_product_commit_required')
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if (digest is not None and row['sha256'] != digest or size is not None and row['bytes'] != size
                or path.suffix == '.pyc'):
            raise ValueError('frozen_active_view_input_changed/' + str(path))
        return row

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    pin(ASSET, ASSET_SHA)
    pilot_quality = read(PILOT / 'QUALITY.json')
    pilot_freeze = PILOT / 'FROZEN.json'
    if [(row['label'], row['earned'], row['possible']) for row in pilot_quality['rows']] != [('N1', 5, 5), ('P1', 3, 5)]:
        raise ValueError('old_actual_first_pair_outcome_changed')
    pin(pilot_freeze, pilot_quality['freeze_sha256'])
    bind(read(pilot_freeze)['direct_inputs'])
    for name in ('QUALITY.json', 'RUNTIME_INDEX.json', 'truth/TRUTH.json', 'consumer/COSTS.json'):
        pin(PILOT / name)
    index = read(PILOT / 'RUNTIME_INDEX.json')
    old_archive = pin(index['archive']['path'], index['archive']['sha256'], index['archive']['bytes'])
    name = REQUEST.relative_to(OLD_RUNTIME).as_posix()
    original, = (entry for entry in index['files'] if entry['path'] == name)
    pin(REQUEST, original['sha256'], original['bytes'])
    with ZipFile(old_archive['path']) as archive:
        if archive.read(name) != REQUEST.read_bytes():
            raise ValueError('fixed_source_region_mcp_request_differs_from_actual_archive')
    params = read(REQUEST)['params']
    if (params['name'] != 'human_eye_scene_observe' or params['arguments']['query']['mode'] != 'source_region'
            or params['arguments']['include_image'] is not True or params['arguments']['response_detail'] != 'brief'):
        raise ValueError('expected_actual_P1_source_region_request')
    pin(BASE_BINDING)
    for name in ('PRODUCT_RUN_BINDING.json', 'BUILD_INSTALL.json', 'PRODUCT_SCHEMA.json', 'TOOLS_SCHEMA.json'):
        pin(NEW_BINDING.parent / name)
    for key in ('installed_files', 'historical_installed_files', 'execution_and_input_pins'):
        bind(build[key])
    for key in ('PRODUCT_SCHEMA.json', 'TOOLS_SCHEMA.json'):
        pin(BASE_BINDING.parent / key)
        if read(BASE_BINDING.parent / key) != read(NEW_BINDING.parent / key):
            raise ValueError('formal_public_tool_schema_changed')

    receipts = {}
    for path in (NS / 'harness/HOST_PREFLIGHT.json', NS / 'checks/OFFLINE.json'):
        value = read(path)
        if value['passed'] is not True:
            raise ValueError('offline_active_view_gate_failed/' + str(path))
        bind(value['source_pins'])
        receipts[path.relative_to(NS).as_posix()] = pin(path)['sha256']
    smoke = {}
    for label in ORDER:
        cmd = [sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label, '--dispatch-smoke']
        smoke[label] = json.loads(subprocess.check_output(cmd, cwd=ROOT, timeout=45))
        result = smoke[label]
        binding_path = BASE_BINDING if label == 'A' else NEW_BINDING
        if (result['fresh_process_prepared_only'] is not True or result['slot'] != label
                or result['schema'] != SCHEMA or result['current_product'] != products[label]
                or Path(result['run_root']).resolve() != RUN.resolve()
                or Path(result['admission']).resolve() != (NS / 'harness/admission.py').resolve()
                or Path(result['current_binding']).resolve() != binding_path.resolve()
                or Path(result['mcp_entry']).resolve() != (NS / 'harness/mcp_entry.py').resolve()
                or Path(result['actual_product_schema']).resolve() != BASE_BINDING.with_name('PRODUCT_SCHEMA.json').resolve()
                or [packet['params'] for packet in result['wrapper']] != [params, params]):
            raise ValueError('actual_dispatch_does_not_bind_the_exact_fixed_request/' + label)
    for path in (Path(sys.executable), RETAINED_ARCHIVE):
        pin(path)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    output = NS / 'FROZEN.json'
    write(output, {'schema': SCHEMA, 'slots': list(ORDER), 'products': products, 'asset_sha256': ASSET_SHA,
          'asset_path': str(ASSET.resolve()), 'passed_offline_preflight': True, 'preflights': receipts,
          'exact_formal_request': pin(REQUEST), 'fresh_dispatch': smoke, 'single_candidate_changed_product_files': changed,
          'max_owned_starts': 2, 'max_business_admissions': 4, 'actual_raster_caps': {'A': 1, 'B': 2},
          'task_s': 450, 'owned_s': 600, 'model_consumers': 0, 'replacement_slots': 0, 'new_assets': 0,
          'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze active source-region candidate', sha(output), len(pins), flush=True)


def sequence():
    sys.path.insert(0, str(NS / 'harness'))
    from admission import can_continue, publication, verify_freeze

    freeze_path = NS / 'FROZEN.json'
    token = verify_freeze(freeze_path)
    if token != sha(freeze_path) or RUN.exists():
        raise ValueError('sequence_requires_this_frozen_fresh_run')
    journal = RUN / 'preflight/SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True)
    journal.touch(exist_ok=False)
    all_complete = True
    for label in ORDER:
        write(journal, {'event': 'start', 'label': label, 'started_ns': time.perf_counter_ns(),
                        'freeze_sha256': token}, 'a')
        proc = subprocess.run([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label], cwd=ROOT)
        try:
            result, receipt = publication(label, token)
        except Exception as error:
            write(journal, {'event': 'unconfirmed', 'label': label, 'error': str(error),
                            'error_type': type(error).__name__, 'exit_code': proc.returncode}, 'a')
            return 1
        safe = can_continue(result, receipt)
        write(journal, {'event': 'publication', 'label': label, 'closed_ns': time.perf_counter_ns(),
                        'exit_code': proc.returncode, 'status': receipt['status'], 'safe_to_continue': safe,
                        'result_sha256': receipt['result_sha256']}, 'a')
        all_complete &= receipt['status'] == 'completed' and proc.returncode == 0
        if not safe:
            return 1
    return 0 if all_complete else 1


def archive():
    spec = spec_from_file_location('_source_region_active_view_archive', RETAINED_ARCHIVE)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NS, module.EXTERNAL = NS, RUN
    module.archive()


def seal():
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    if any(not row.startswith(prefix) for row in git('diff', '--name-only', HISTORY).decode().splitlines()):
        raise ValueError('changes_outside_the_assay_evidence_namespace')
    manifest = NS / 'CONTENT_MANIFEST.json'
    items = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
             for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(row['path'].endswith(('.pyc', '.bak')) for row in items):
        raise ValueError('unexpected_generated_evidence')
    write(manifest, {'count': len(items), 'files': items, 'self_excluded': True})
    print('Sealed', len(items), sha(manifest), flush=True)


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit('Use the pinned interpreter with -I -B.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'sequence', 'archive', 'seal'))
    raise SystemExit(globals()[parser.parse_args().action]())
