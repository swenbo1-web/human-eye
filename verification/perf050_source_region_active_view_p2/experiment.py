"""Freeze and run exactly one fresh consumer of the accepted active-view build."""

import argparse
import ast
from hashlib import file_digest
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
RUN = Path('D:/he_perf050_source_region_active_view_p2')
ASSET = Path('D:/he_m5_joint_brief_source_projection_recovery_001/slots/B/native/input.blend')
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
ACTIVE = NS.parent / 'm4_source_region_active_view_001'
PILOT = NS.parent / 'perf050_readonly_product_pilot_001'
INSTALL = ACTIVE / 'install'
PROMPT = PILOT / 'inputs/PROMPT.txt'
PROMPT_SHA = 'ee9e22bfef64fc8799b57f0569a320ebe93a16ff8862c7e3d6ed6236b92be98e'
PLAN = 'd0cebe6b6dd1ec573c0473d9a3b20410325b9a70:docs/PERF050_SOURCE_REGION_ACTIVE_VIEW_P2_PLAN.md'
HISTORY = 'c18b7bdc26e59d4af672872f4b6645bb66e07d88'
SLOT = 'P2'
SCHEMA = 'perf050-source-region-active-view-p2-v1'
PRODUCT = {
    'commit': '30c9cfc121bbdee72b61afda59cbcf23e9080b67',
    'source_sha256': '2ad989728b7229934d164cf4c763eeb89b28e86d6fbfe7b90bace82055b2683c',
    'wheel_sha256': '706cab599faafe0ec31a1625cbc8035530342824dbfd34afe3835e0d4ebcf100',
}
ARCHIVE = NS.parent / 'm4_cross_scale_live_task_formal_001/publish.py'


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


def freeze():
    if RUN.exists() or git('rev-parse', 'HEAD').decode().strip() != HISTORY or git('diff', '--name-only', HISTORY):
        raise ValueError('fresh_single_slot_and_zero_product_delta_required')
    if (NS / 'PLAN.md').read_bytes() != git('show', PLAN):
        raise ValueError('registered_P2_plan_changed')

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((digest is not None and row['sha256'] != digest) or (size is not None and row['bytes'] != size)
                or path.suffix == '.pyc'):
            raise ValueError('frozen_P2_input_changed/' + str(path))
        return row

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    pin(ASSET, ASSET_SHA)
    pin(PROMPT, PROMPT_SHA, 387)
    binding_path = INSTALL / 'PRODUCT_RUN_BINDING.json'
    binding, build = (read(path) for path in (binding_path, INSTALL / 'BUILD_INSTALL.json'))
    actual_product = {k: binding[field] for k, field in (
        ('commit', 'preparation_git'), ('source_sha256', 'source_sha256'), ('wheel_sha256', 'wheel_sha256'))}
    if (actual_product != PRODUCT or build['binding'] != binding or build['passed'] is not True
            or len(binding['source_manifest']) != 143 or build['wheel_RECORD_verified'] is not True
            or build['tool_schema_matches_historical_actual_directory'] is not True):
        raise ValueError('accepted_engineering_install_must_be_reused_verbatim')
    pin(binding['wheel_path'], PRODUCT['wheel_sha256'])
    for name in ('PRODUCT_RUN_BINDING.json', 'BUILD_INSTALL.json', 'TOOLS_SCHEMA.json', 'PRODUCT_SCHEMA.json'):
        pin(INSTALL / name)
    bind(build['installed_files'])

    accepted = ACTIVE / 'checks/LIVE_REVIEW_RECONCILED.json'
    failed_review = ACTIVE / 'checks/LIVE_REVIEW.json'
    accepted_freeze = ACTIVE / 'FROZEN.json'
    accepted_receipt = read(accepted)
    first_review = read(failed_review)
    if (accepted_receipt['passed'] is not True or accepted_receipt['denominators']['qualified'] != 2
            or first_review['passed'] is not False or first_review['denominators']['qualified'] != 0
            or first_review['freeze_sha256'] != accepted_receipt['freeze_sha256']
            or read(accepted_freeze)['products']['B'] != PRODUCT):
        raise ValueError('original_engineering_results_changed')
    pin(accepted_freeze, accepted_receipt['freeze_sha256'])
    bind(read(accepted_freeze)['direct_inputs'])
    for name in ('checks/LIVE_REVIEW_RECONCILED.json', 'checks/LIVE_REVIEW.json', 'RUNTIME_INDEX.json'):
        pin(ACTIVE / name)
    runtime_zip = read(ACTIVE / 'RUNTIME_INDEX.json')['archive']
    pin(runtime_zip['path'], runtime_zip['sha256'], runtime_zip['bytes'])

    pilot_quality = read(PILOT / 'QUALITY.json')
    if [(row['label'], row['earned'], row['possible']) for row in pilot_quality['rows']] != [('N1', 5, 5), ('P1', 3, 5)]:
        raise ValueError('sealed_historical_pair_outcome_changed')
    for name in ('FROZEN.json', 'RUBRIC.md', 'QUALITY.json', 'RUNTIME_INDEX.json', 'truth/TRUTH.json',
                 'consumer/COSTS.json', 'answers/N1.txt', 'answers/P1.txt', 'IMAGE_REVIEW.json'):
        pin(PILOT / name)
    pilot_zip = read(PILOT / 'RUNTIME_INDEX.json')['archive']
    pin(pilot_zip['path'], pilot_zip['sha256'], pilot_zip['bytes'])

    receipts = {}
    for path in (NS / 'harness/HOST_PREFLIGHT.json', NS / 'consumer/PREFLIGHT.json', NS / 'checks/PREFLIGHT.json'):
        data = read(path)
        if data['passed'] is not True:
            raise ValueError('offline_P2_admission_did_not_pass/' + path.name)
        bind(data['source_pins'])
        receipts[path.relative_to(NS).as_posix()] = pin(path)['sha256']
    cmd = [sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), SLOT, '--dispatch-smoke']
    smoke = json.loads(subprocess.check_output(cmd, cwd=ROOT, timeout=45))
    prior_tools = read(PILOT / 'FROZEN.json')['fresh_dispatch']['P1']['tools']
    if (smoke['fresh_process_prepared_only'] is not True or smoke['slot'] != SLOT or smoke['group'] != 'P'
            or smoke['schema'] != SCHEMA or smoke['product'] != PRODUCT or smoke['tools'] != prior_tools
            or Path(smoke['asset']).resolve() != ASSET.resolve() or Path(smoke['run_root']).resolve() != RUN.resolve()
            or Path(smoke['mcp_entry']).resolve() != (NS / 'harness/mcp_entry.py').resolve()
            or Path(smoke['consumer_driver']).resolve() != (NS / 'consumer/driver.py').resolve()
            or Path(smoke['admission']).resolve() != (NS / 'harness/admission.py').resolve()
            or Path(smoke['actual_product_schema']).resolve() != (INSTALL / 'PRODUCT_SCHEMA.json').resolve()):
        raise ValueError('actual_fresh_P2_entrypoint_differs_from_registered_path')
    pin(ARCHIVE)
    pin(sys.executable)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)

    target = NS / 'FROZEN.json'
    write(target, {'schema': SCHEMA, 'slots': [SLOT], 'product': PRODUCT,
          'asset_path': str(ASSET.resolve()), 'asset_sha256': ASSET_SHA, 'prompt_sha256': PROMPT_SHA,
          'prompt_bytes': 387, 'passed_offline_preflight': True, 'preflights': receipts, 'fresh_dispatch': smoke,
          'historical_pair_rubric_sha256': sha(PILOT / 'RUBRIC.md'), 'accepted_engineering_review_sha256': sha(accepted),
          'max_business_per_slot': 12, 'max_raster_per_slot': 12, 'max_model_consumers': 1,
          'task_s': 450, 'owned_s': 600, 'replacements': 0, 'new_qualification_slots': 0, 'product_delta_files': 0,
          'product_builds': 0, 'new_assets': 0, 'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze sole P2', sha(target), len(pins), flush=True)


def sequence():
    sys.path.insert(0, str(NS / 'harness'))
    from admission import can_continue, publication, verify_freeze

    frozen = NS / 'FROZEN.json'
    token = verify_freeze(frozen)
    if token != sha(frozen) or RUN.exists():
        raise ValueError('registered_sole_P2_instance_requires_fresh_output')
    journal = RUN / 'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True)
    write(journal, {'event': 'start', 'label': SLOT, 'started_ns': time.perf_counter_ns(), 'freeze_sha256': token})
    proc = subprocess.run([sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), SLOT], cwd=ROOT)
    try:
        result, receipt = publication(SLOT, token)
    except Exception as error:
        write(journal, {'event': 'unconfirmed', 'label': SLOT, 'error': str(error),
                        'error_type': type(error).__name__, 'exit_code': proc.returncode}, 'a')
        return 1
    safe = can_continue(result, receipt)
    write(journal, {'event': 'publication', 'label': SLOT, 'closed_ns': time.perf_counter_ns(),
                    'exit_code': proc.returncode, 'status': receipt['status'], 'safe_to_continue': safe,
                    'result_sha256': receipt['result_sha256'], 'model_consumers': result['model_consumers']}, 'a')
    return 0 if safe and receipt['status'] == 'completed' and proc.returncode == 0 else 1


def archive():
    spec = spec_from_file_location('_P2_original_archive', ARCHIVE)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NS, module.EXTERNAL = NS, RUN
    module.archive()


def seal():
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    if any(not row.startswith(prefix) for row in git('diff', '--name-only', HISTORY).decode().splitlines()):
        raise ValueError('unrelated_changes_outside_the_P2_evidence_namespace')
    manifest = NS / 'CONTENT_MANIFEST.json'
    rows = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
            for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(item['path'].endswith(('.pyc', '.bak')) for item in rows):
        raise ValueError('unexpected_generated_evidence')
    write(manifest, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Sealed', len(rows), sha(manifest), flush=True)


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit('Use the pinned interpreter with -I -B.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'sequence', 'archive', 'seal'))
    raise SystemExit(globals()[parser.parse_args().action]())
