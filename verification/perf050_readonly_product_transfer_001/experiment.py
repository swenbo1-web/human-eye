"""Freeze and run one new paired diagnostic at the accepted original-image build."""

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
RUN = Path('D:/he_perf050_readonly_product_transfer_001')
ASSET = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
FINAL_IMAGE = NS.parent / 'm1_source_region_final_image_001'
P3_HISTORY = NS.parent / 'perf050_source_region_final_image_p3'
PILOT = NS.parent / 'perf050_readonly_product_pilot_001'
INSTALL = FINAL_IMAGE / 'install'
PROMPT = NS / 'inputs/PROMPT.txt'
TRUTH = NS / 'truth/TRUTH.json'
PROMPT_SHA = '009941cb3fdd100d46975a08a2e03c51708b70299be5f60ff4e1c2a399e7e9b9'
PLAN = '536a1db264b661690679ba9d503940e84a9142fa:docs/PERF050_READONLY_PRODUCT_TRANSFER_001_PLAN.md'
HISTORY = '11481bd57447bb9dace6b9a0d0a070fd17ac526a'
ORDER = ('N1', 'P1')
SCHEMA = 'perf050-readonly-product-transfer-v1'
PRODUCT = {
    'commit': '470a36f111cd5e96845569c258f464d4bbcf2824',
    'source_sha256': '5b2e2ff21b068936b8ab951be585272d9b871a896d7a0a882dfed020896298c7',
    'wheel_sha256': '78f9626dc30ace6523f4715512a934d1a42ddca977066a614067f3ed61586eb8',
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
        raise ValueError('fresh_serial_pair_and_zero_product_delta_required')
    if (NS / 'PLAN.md').read_bytes() != git('show', PLAN):
        raise ValueError('registered_transfer_plan_changed')

    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if ((digest is not None and row['sha256'] != digest) or (size is not None and row['bytes'] != size)
                or path.suffix == '.pyc'):
            raise ValueError('frozen_transfer_input_changed/' + str(path))
        return row

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    pin(ASSET, ASSET_SHA)
    prompt = pin(PROMPT, PROMPT_SHA)
    truth = read(TRUTH)
    if (truth['region']['object_name'] != 'M09' or truth['region']['source_triangle_indices'] != [0, 1]
            or truth['function_region_is_whole_M09'] is not True
            or truth['measurement']['objects_in_order'] != ['M09', 'M03']
            or truth['measurement']['distance_m'] != '15/64'
            or truth['measurement']['direction_a_to_b_world'] != [0, 0, 1]):
        raise ValueError('preflight_truth_does_not_match_the_registered_transfer_task')
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

    p3_quality = P3_HISTORY / 'QUALITY.json'
    p3_result = read(p3_quality)
    p3_freeze = P3_HISTORY / 'FROZEN.json'
    if ((p3_result['actual_slot']['quality_earned'], p3_result['actual_slot']['quality_possible']) != (5, 5)
            or p3_result['same_prompt_sampling_closed'] is not True or read(p3_freeze)['product'] != PRODUCT
            or p3_result['original_candidate_view']['actual_final_link_reopens_exact_original_after_close'] is not True):
        raise ValueError('sealed_prior_task_close_changed')
    pin(p3_freeze, p3_result['freeze_sha256'])
    bind(read(p3_freeze)['direct_inputs'])
    for name in ('QUALITY.json', 'RUNTIME_INDEX.json', 'answers/P3.txt', 'checks/HOST_REOPEN.json',
                 'checks/WHOLE_SCOPE.json'):
        pin(P3_HISTORY / name)
    runtime_zip = read(P3_HISTORY / 'RUNTIME_INDEX.json')['archive']
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
    for path in (NS / 'harness/HOST_PREFLIGHT.json', NS / 'consumer/PREFLIGHT.json', NS / 'checks/PREFLIGHT.json', TRUTH):
        data = read(path)
        if data['passed'] is not True:
            raise ValueError('offline_transfer_admission_did_not_pass/' + path.name)
        bind(data['source_pins'])
        receipts[path.relative_to(NS).as_posix()] = pin(path)['sha256']
    smoke = {}
    previous_tools = read(PILOT / 'FROZEN.json')['fresh_dispatch']
    for label in ORDER:
        cmd = [sys.executable, '-I', '-B', str(NS / 'harness/run_slot.py'), label, '--dispatch-smoke']
        cell = smoke[label] = json.loads(subprocess.check_output(cmd, cwd=ROOT, timeout=45))
        if (cell['fresh_process_prepared_only'] is not True or cell['slot'] != label or cell['group'] != label[0]
                or cell['schema'] != SCHEMA or cell['product'] != PRODUCT or cell['tools'] != previous_tools[label]['tools']
                or Path(cell['asset']).resolve() != ASSET.resolve() or Path(cell['run_root']).resolve() != RUN.resolve()
                or Path(cell['mcp_entry']).resolve() != (NS / 'harness/mcp_entry.py').resolve()
                or Path(cell['consumer_driver']).resolve() != (NS / 'consumer/driver.py').resolve()
                or Path(cell['admission']).resolve() != (NS / 'harness/admission.py').resolve()
                or Path(cell['actual_product_schema']).resolve() != (INSTALL / 'PRODUCT_SCHEMA.json').resolve()):
            raise ValueError('actual_transfer_dispatch_differs_from_registered_path/' + label)
    pin(ARCHIVE)
    pin(sys.executable)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)

    target = NS / 'FROZEN.json'
    write(target, {'schema': SCHEMA, 'slots': list(ORDER), 'product': PRODUCT,
          'asset_path': str(ASSET.resolve()), 'asset_sha256': ASSET_SHA, 'prompt_sha256': PROMPT_SHA,
          'prompt_bytes': prompt['bytes'], 'passed_offline_preflight': True, 'preflights': receipts, 'fresh_dispatch': smoke,
          'historical_pair_rubric_sha256': sha(PILOT / 'RUBRIC.md'), 'historical_P3_closed_task_sha256': sha(p3_quality),
          'max_business_per_slot': 12, 'max_raster_per_slot': 12, 'max_model_consumers': 2,
          'task_s': 450, 'owned_s': 600, 'replacements': 0, 'new_qualification_slots': 0, 'product_delta_files': 0,
          'product_builds': 0, 'new_assets': 0, 'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze transfer pair', sha(target), len(pins), flush=True)


def sequence():
    sys.path.insert(0, str(NS / 'harness'))
    from admission import can_continue, publication, verify_freeze

    frozen = NS / 'FROZEN.json'
    token = verify_freeze(frozen)
    if token != sha(frozen) or RUN.exists():
        raise ValueError('registered_transfer_pair_requires_fresh_output')
    journal = RUN / 'preflight/FORMAL_SEQUENCE.jsonl'
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
                        'result_sha256': receipt['result_sha256'], 'model_consumers': result['model_consumers']}, 'a')
        all_complete &= receipt['status'] == 'completed' and proc.returncode == 0
        if not safe:
            return 1
    return 0 if all_complete else 1


def archive():
    spec = spec_from_file_location('_transfer_original_archive', ARCHIVE)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NS, module.EXTERNAL = NS, RUN
    module.archive()


def seal():
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    if any(not row.startswith(prefix) for row in git('diff', '--name-only', HISTORY).decode().splitlines()):
        raise ValueError('unrelated_changes_outside_the_transfer_evidence_namespace')
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
