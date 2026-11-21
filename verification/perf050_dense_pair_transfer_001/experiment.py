"""Freeze the single dense N1/P1 experiment and reuse the retained publication path."""

import argparse
import ast
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys


NS = Path(__file__).resolve().parent
V = NS.parent
ROOT = V.parent
REFERENCE = V / 'perf050_readonly_product_transfer_001'
ENGINE = V / 'm1_pair_distance_entry_001'
INSTALL = ENGINE / 'install'
HISTORY = 'c07df163476c0fc9af65a7fc2ab7ce2b271a79b2'
PLAN = '796f1bcda4c9127a47ca506261846c3f51f41987:docs/PERF050_DENSE_PAIR_TRANSFER_001_PLAN.md'
SCHEMA = 'perf050-dense-pair-transfer-001-v1'
RUN = Path('D:/he_perf050_dense_pair_transfer_001')
ASSET = Path('D:/he_m4_target_002/assets_01/main.blend')
ASSET_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
PROMPT_SHA = 'cf91954709c15b431d7d111be3de0667f5376222d1212f68c9e28fb38621cf8e'
PRODUCT = {'commit': 'c8f87c540f802fe7b85caae95a8ac86b0f43518f',
           'source_sha256': '0e85052a0a4dec4ee42f8f9f62729a416b57445783224b303723b515ada0a147',
           'wheel_sha256': '319b419852ecd1e7af84f773e3ef2a27fdb5737ae2a186c00e242e9f1d95c503'}
ORDER = ('N1', 'P1')


previous = run_path(str(REFERENCE / 'experiment.py'))
sha, read, write, git = (previous[key] for key in ('sha', 'read', 'write', 'git'))
sequence, archive, seal = (previous[key] for key in ('sequence', 'archive', 'seal'))
sequence.__globals__.update(NS=NS, RUN=RUN, ORDER=ORDER, HISTORY=HISTORY)


def freeze():
    if RUN.exists() or git('rev-parse', 'HEAD').decode().strip() != HISTORY or git('diff', '--name-only', HISTORY):
        raise ValueError('dense_trial_must_start_fresh_with_zero_product_delta')
    if (NS / 'PLAN.md').read_bytes() != git('show', PLAN):
        raise ValueError('registered_plan_changed')
    inputs = {}

    def pin(path, expected=None, length=None):
        path = Path(path).resolve()
        if path not in inputs:
            inputs[path] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        record = inputs[path]
        if ((expected is not None and record['sha256'] != expected)
                or (length is not None and record['bytes'] != length)):
            raise ValueError('frozen_input_mismatch/' + str(path))
        return record

    def bind(rows):
        for row in rows:
            pin(row['path'], row['sha256'], row.get('bytes'))

    original = read(REFERENCE / 'FROZEN.json')
    bind(original['direct_inputs'])
    pin(REFERENCE / 'FROZEN.json')
    pin(REFERENCE / 'QUALITY.json')
    for name in ('perf050_target_observation_first_image_p2', 'perf050_source_region_final_image_p3',
                 'm4_dense_panel_sweep_formal_001'):
        index = V / name / 'RUNTIME_INDEX.json'
        pin(index)
        bind([read(index)['archive']])
    asset = pin(ASSET, ASSET_SHA)
    prompt = pin(NS / 'inputs/PROMPT.txt', PROMPT_SHA, 408)
    decision = read(ENGINE / 'DECISION.json')
    install = read(INSTALL / 'PRODUCT_RUN_BINDING.json')
    build = read(INSTALL / 'BUILD_INSTALL.json')
    product = {key: install[field] for key, field in (
        ('commit', 'preparation_git'), ('source_sha256', 'source_sha256'), ('wheel_sha256', 'wheel_sha256'))}
    if (product != PRODUCT or decision['actual_tool_catalogue_delta'] != ['human_eye_scene_observe.description']
            or not decision['qualified_for_frozen_engineering_scope']
            or build['binding'] != install or not build['passed'] or not build['wheel_RECORD_verified']
            or len(install['source_manifest']) != 143):
        raise ValueError('accepted_ordered_distance_install_changed')
    pin(install['wheel_path'], product['wheel_sha256'])
    bind(build['installed_files'])
    for path in (ENGINE / 'DECISION.json', ENGINE / 'checks/POSITIVE_REPLAY.json', ENGINE / 'checks/REJECTS.json',
                 INSTALL / 'BUILD_INSTALL.json', INSTALL / 'PRODUCT_RUN_BINDING.json',
                 INSTALL / 'PRODUCT_SCHEMA.json', INSTALL / 'TOOLS_SCHEMA.json'):
        pin(path)

    receipts = {}
    for relative in ('harness/HOST_PREFLIGHT.json', 'consumer/PREFLIGHT.json', 'truth/TRUTH.json'):
        path = NS / relative
        report = read(path)
        if report['passed'] is not True:
            raise ValueError('dense_preflight_failed/' + relative)
        bind(report['source_pins'])
        receipts[relative] = pin(path)['sha256']
    truth = read(NS / 'truth/TRUTH.json')
    pair = truth['target_and_pair']
    if (truth['source_counts'] != {'objects': 14, 'vertices': 3478, 'triangles': 6148}
            or pair['pair'] != ['M4_Far_00', 'M4_Focal'] or pair['whole_distance_m_exact'] != '1'
            or pair['whole_direction_world'] != [-1, 0, 0] or pair['top_distance_squared_exact'] != '2'
            or pair['top']['source_triangle_ids'] != [512, 513]
            or any(not arm['proof']['qualifies'] for arm in truth['prior_original_tool_images'].values())):
        raise ValueError('independent_dense_truth_differs_from_registered_scope')
    launch = {}
    for label in ORDER:
        command = [sys.executable, '-IB', str(NS / 'harness/run_slot.py'), label, '--dispatch-smoke']
        cell = launch[label] = json.loads(subprocess.check_output(command, cwd=ROOT, timeout=45))
        if (not cell['fresh_process_prepared_only'] or cell['slot'] != label or cell['group'] != label[0]
                or cell['schema'] != SCHEMA or cell['product'] != product
                or cell['tools'] != original['fresh_dispatch'][label]['tools']
                or Path(cell['asset']) != ASSET or Path(cell['run_root']) != RUN
                or Path(cell['mcp_entry']) != NS / 'harness/mcp_entry.py'
                or Path(cell['actual_product_schema']) != INSTALL / 'PRODUCT_SCHEMA.json'):
            raise ValueError('actual_slot_entry_changed/' + label)
    recorder = json.loads(subprocess.check_output(
        [sys.executable, '-IB', str(NS / 'harness/mcp_entry.py'), '--dispatch-smoke'], cwd=ROOT, timeout=45))
    if (recorder['schema'] != SCHEMA or recorder['label'] != 'P1' or not recorder['fresh_process_prepared_only']
            or Path(recorder['absolute_state_file']) != RUN / 'slots/P1/product_state.json'
            or Path(recorder['current_binding']) != INSTALL / 'PRODUCT_RUN_BINDING.json'):
        raise ValueError('actual_product_recorder_state_changed')
    pin(previous['ARCHIVE'])
    pin(sys.executable)
    for path in NS.rglob('*'):
        if path.is_file():
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    write(NS / 'FROZEN.json', {'schema': SCHEMA, 'slots': list(ORDER), 'product': product,
        'asset_path': asset['path'], 'asset_sha256': asset['sha256'], 'prompt_sha256': prompt['sha256'],
        'prompt_bytes': prompt['bytes'], 'passed_offline_preflight': True, 'preflights': receipts,
        'fresh_dispatch': launch, 'fresh_recorder': recorder, 'new_qualification_slots': 0,
        'max_business_per_slot': 12, 'max_raster_per_slot': 12, 'max_model_consumers': 2,
        'task_s': 450, 'owned_s': 600, 'replacements': 0, 'product_delta_files': 0, 'product_builds': 0,
        'new_assets': 0, 'direct_inputs': [inputs[path] for path in sorted(inputs)]})
    print('Froze the sole dense pair', sha(NS / 'FROZEN.json'), len(inputs), flush=True)


if __name__ == '__main__':
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise SystemExit('Use the pinned interpreter with -I -B.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'sequence', 'archive', 'seal'))
    raise SystemExit(globals()[parser.parse_args().action]())
