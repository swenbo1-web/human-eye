"""Freeze and publish the sole cold P2 on the exact accepted installation."""

import argparse
import ast
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
ROOT = NS.parents[1]
VERIFY = NS.parent
REFERENCE = VERIFY / 'perf050_readonly_product_transfer_001'
WINDOWS = VERIFY / 'm1_target_observation_first_image_path_windows_001'
INSTALL = WINDOWS / 'install'
ARCHIVE = VERIFY / 'm4_cross_scale_live_task_formal_001/publish.py'
RUN = Path('D:/he_perf050_target_observation_first_image_p2')
HISTORY = '0cc8afa5082f27a3aff607bebf7793d0d4072bc9'
PLAN = '900b5663ae508c842dc4bb91ed79e07d9c06a552:docs/M1_TARGET_OBSERVATION_FIRST_IMAGE_PATH_WINDOWS_001_INDEPENDENT_REVIEW.md'
SCHEMA = 'perf050-target-observation-first-image-p2-v1'
SLOT = 'P2'


previous = run_path(str(REFERENCE / 'experiment.py'))
sha, read, write, git = (previous[key] for key in ('sha', 'read', 'write', 'git'))


def freeze():
    if RUN.exists() or git('rev-parse', 'HEAD').decode().strip() != HISTORY or git('diff', '--name-only', HISTORY):
        raise ValueError('P2_requires_fresh_runtime_and_zero_product_delta')
    if (NS / 'PLAN.md').read_bytes() != git('show', PLAN):
        raise ValueError('registered_P2_plan_changed')
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        row = pins[path]
        if (digest is not None and row['sha256'] != digest) or (size is not None and row['bytes'] != size):
            raise ValueError('P2_frozen_input_changed/' + str(path))
        return row

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    old = read(REFERENCE / 'FROZEN.json')
    bind(old['direct_inputs'])
    pin(REFERENCE / 'FROZEN.json')
    for name in ('QUALITY.json', 'RUNTIME_INDEX.json', 'consumer/COSTS.json', 'answers/N1.txt', 'answers/P1.txt',
                 'checks/SCOPED_ACTIVE_OBSERVATION.json', 'checks/HOST_REOPENS.json'):
        pin(REFERENCE / name)
    quality = read(REFERENCE / 'QUALITY.json')
    if [(item['label'], item['score'], item['out_of']) for item in quality['slots']] != [('N1', 5, 5), ('P1', 4, 5)]:
        raise ValueError('original_transfer_results_changed')
    bind([read(REFERENCE / 'RUNTIME_INDEX.json')['archive']])
    asset = pin(old['asset_path'], old['asset_sha256'])
    prompt = pin(NS / 'inputs/PROMPT.txt', old['prompt_sha256'], 350)
    if (NS / 'RUBRIC.md').read_bytes() != (REFERENCE / 'RUBRIC.md').read_bytes():
        raise ValueError('P2_original_five_item_rubric_changed')

    decision = read(WINDOWS / 'DECISION.json')
    build = read(INSTALL / 'BUILD_INSTALL.json')
    binding = read(INSTALL / 'PRODUCT_RUN_BINDING.json')
    product = {key: binding[source] for key, source in (
        ('commit', 'preparation_git'), ('source_sha256', 'source_sha256'), ('wheel_sha256', 'wheel_sha256'))}
    if (not decision['qualified_for_frozen_engineering_scope'] or build['binding'] != binding or not build['passed']
            or not build['wheel_RECORD_verified'] or not build['tool_schema_matches_historical_actual_directory']
            or len(binding['source_manifest']) != 143
            or any(product[key] != decision['candidate_' + ('git' if key == 'commit' else key)] for key in product)):
        raise ValueError('accepted_P2_install_changed')
    pin(binding['wheel_path'], product['wheel_sha256'])
    bind(build['installed_files'])
    for name in ('DECISION.json', 'checks/REPLAY.json', 'checks/BYTE_CONTROLS.json',
                 'checks/CANDIDATE_DISPATCH_RX.bin', 'checks/CANDIDATE_ALIAS_DISPATCH_RX.bin',
                 'install/PRODUCT_RUN_BINDING.json', 'install/BUILD_INSTALL.json',
                 'install/PRODUCT_SCHEMA.json', 'install/TOOLS_SCHEMA.json'):
        pin(WINDOWS / name)

    receipts = {}
    for rel in ('harness/HOST_PREFLIGHT.json', 'consumer/PREFLIGHT.json'):
        path = NS / rel
        data = read(path)
        if data['passed'] is not True:
            raise ValueError('P2_offline_preflight_failed/' + rel)
        bind(data['source_pins'])
        receipts[rel] = pin(path)['sha256']
    def smoke(entry, *args):
        return json.loads(subprocess.check_output([sys.executable, '-IB', str(NS / 'harness' / entry),
                                                   *args, '--dispatch-smoke'], cwd=ROOT, timeout=45))
    runner, recorder = smoke('run_slot.py', SLOT), smoke('mcp_entry.py')
    if (runner['schema'] != recorder['schema'] or runner['schema'] != SCHEMA or runner['slot'] != SLOT
            or recorder['label'] != SLOT or runner['product'] != product or runner['group'] != 'P'
            or runner['tools'] != old['fresh_dispatch']['P1']['tools']
            or Path(runner['asset']) != Path(asset['path']) or Path(runner['run_root']) != RUN
            or Path(runner['actual_product_schema']) != INSTALL / 'PRODUCT_SCHEMA.json'
            or Path(runner['mcp_entry']) != Path(recorder['entry'])
            or Path(recorder['absolute_state_file']) != RUN / 'slots/P2/product_state.json'
            or Path(recorder['current_binding']) != INSTALL / 'PRODUCT_RUN_BINDING.json'
            or not runner['fresh_process_prepared_only'] or not recorder['fresh_process_prepared_only']):
        raise ValueError('P2_actual_runner_or_recorder_binding_changed')
    pin(sys.executable)
    pin(ARCHIVE)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    write(NS / 'FROZEN.json', {'schema': SCHEMA, 'slots': [SLOT], 'product': product,
        'asset_path': asset['path'], 'asset_sha256': asset['sha256'], 'prompt_sha256': prompt['sha256'],
        'prompt_bytes': prompt['bytes'], 'passed_offline_preflight': True, 'preflights': receipts,
        'fresh_dispatch': runner, 'fresh_recorder': recorder,
        'max_business_per_slot': 12, 'max_raster_per_slot': 12, 'max_model_consumers': 1,
        'task_s': 450, 'owned_s': 600, 'replacements': 0, 'new_qualification_slots': 0,
        'product_delta_files': 0, 'product_builds': 0, 'new_assets': 0,
        'direct_inputs': [pins[path] for path in sorted(pins)]})
    print('Froze sole P2', sha(NS / 'FROZEN.json'), len(pins), flush=True)


def sequence():
    sys.path.insert(0, str(NS / 'harness'))
    from admission import can_continue, publication, verify_freeze

    freeze_path = NS / 'FROZEN.json'
    token = verify_freeze(freeze_path)
    if token != sha(freeze_path) or RUN.exists():
        raise ValueError('registered_P2_requires_fresh_output')
    journal = RUN / 'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True)
    journal.touch(exist_ok=False)
    write(journal, {'event': 'start', 'label': SLOT, 'started_ns': time.perf_counter_ns(), 'freeze_sha256': token}, 'a')
    proc = subprocess.run([sys.executable, '-IB', str(NS / 'harness/run_slot.py'), SLOT], cwd=ROOT)
    try:
        result, receipt = publication(SLOT, token)
    except Exception as error:
        write(journal, {'event': 'unconfirmed', 'label': SLOT, 'error': str(error),
                        'error_type': type(error).__name__, 'exit_code': proc.returncode}, 'a')
        return 1
    safe = can_continue(result, receipt)
    write(journal, {'event': 'publication', 'label': SLOT, 'closed_ns': time.perf_counter_ns(),
                    'exit_code': proc.returncode, 'status': receipt['status'], 'closure_confirmed': safe,
                    'result_sha256': receipt['result_sha256'], 'model_consumers': result['model_consumers']}, 'a')
    return 0 if safe and receipt['status'] == 'completed' and proc.returncode == 0 else 1


def archive():
    spec = spec_from_file_location('_P2_original_runtime_archive', ARCHIVE)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NS, module.EXTERNAL = NS, RUN
    module.archive()


def seal():
    prefix = NS.relative_to(ROOT).as_posix() + '/'
    if any(not path.startswith(prefix) for path in git('diff', '--name-only', HISTORY).decode().splitlines()):
        raise ValueError('unrelated_changes_outside_P2_evidence_namespace')
    manifest = NS / 'CONTENT_MANIFEST.json'
    files = [path for path in sorted(NS.rglob('*')) if path.is_file() and path != manifest]
    if any(path.suffix in ('.pyc', '.bak') for path in files):
        raise ValueError('unexpected_generated_evidence')
    rows = [{'path': path.relative_to(NS).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in files]
    write(manifest, {'count': len(rows), 'files': rows, 'self_excluded': True})
    print('Sealed', len(rows), sha(manifest), flush=True)


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit('Use the pinned interpreter with -I -B.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'sequence', 'archive', 'seal'))
    raise SystemExit(globals()[parser.parse_args().action]())
