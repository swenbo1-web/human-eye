"""Freeze and run the fixed dense micro-surface comparison once."""

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
import time


NS = Path(__file__).resolve().parent
sys.path.insert(0, str(NS / 'harness'))
import admission
from common import (ASSET, ASSET_BINDING, ASSET_SHA256, BLENDER, CATALOGUE, EXTERNAL, FORMAL_LABELS,
                    GENERIC_WORKER, ORDER, PRODUCT, PRODUCT_BINDING, PRODUCT_SCHEMA, QUALIFICATION,
                    ROOT, SLOTS, V, append, read, save, sha)


BASE = '721ed392d8313a2554947c1ac3b5f38a98d1465a'
PLAN = 'afb0514d236febaef283ac2623fb1079afcb3f4b:docs/PERF050_DENSE_MICRO_SURFACE_HOLDOUT_001_PLAN.md'
PROMPT_SHA = 'c3eecfa0aa775b27dcdb8494da447a0d38585a51ae924696a09da0c3c6471bd4'
ORIGINAL_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'


def require(test, reason):
    if not test:
        raise ValueError(reason)


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def dispatch(entry, *args):
    return json.loads(subprocess.check_output([sys.executable, '-IB', str(NS / entry), *args], cwd=ROOT, timeout=45))


def freeze():
    namespace = NS.relative_to(ROOT).as_posix() + '/'
    require(not EXTERNAL.exists() and not (NS / 'FROZEN.json').exists(), 'one_fresh_frozen_trial_required')
    require(git('merge-base', BASE, 'HEAD').decode().strip() == BASE and
            all(path.startswith(namespace) for path in git('diff', '--name-only', BASE).decode().splitlines()),
            'zero_product_delta_required')
    require((NS / 'PLAN.md').read_bytes() == git('show', PLAN), 'fixed_plan_changed')
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve(strict=True)
        if path not in pins:
            pins[path] = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        row = pins[path]
        require((digest is None or row['sha256'] == digest) and (size is None or row['bytes'] == size),
                f'freeze_input_mismatch/{path}')
        return row

    pin(ASSET, ASSET_SHA256)
    pin('D:/he_m4_target_002/assets_01/main.blend', ORIGINAL_SHA)
    asset_inputs = read(ASSET_BINDING)
    for field in ('asset', 'reopened_source', 'old_asset', 'old_geometry', 'builder', 'blender', 'readback_helper'):
        row = asset_inputs[field]
        pin(row['path'], row['sha256'], row['bytes'])
    require(asset_inputs['counts'] == {'objects':21, 'vertices':3506, 'triangles':6162}, 'independent_fixture_counts_mismatch')
    prompt = pin(NS / 'inputs/PROMPT.txt', PROMPT_SHA, 1032)
    truth = read(NS / 'fixture/TRUTH.json')
    require(sorted(row['object_name'] for row in truth['eligible']) == ['S021', 'S034', 'S055'], 'independent_eligible_set_mismatch')
    for path in (PRODUCT_BINDING, PRODUCT_SCHEMA, CATALOGUE, GENERIC_WORKER, GENERIC_WORKER.with_name('wire_meter.py'), BLENDER, sys.executable):
        pin(path)
    for name in ('m4_dense_panel_sweep_001/truth/panel_truth.py',
                 'm4_cross_scale_discovery_001/oracle/check_saved.py', 'm4_cross_scale_discovery_001/oracle/expected.py',
                 'm4_cross_scale_discovery_001/oracle/geometry_witness.py', 'm4_dense_region_brief_001/checks/brief_schema.py',
                 'm4_cross_scale_live_qualification_001/checks/delivery.py', 'm4_live_source_region_task_003/thin_stdio.py',
                 'm4_live_source_region_task_003/harness/mcp_entry.py'):
        pin(V / name)
    require(admission.registered_product() == PRODUCT, 'fixed_installed_product_required')
    binding = read(PRODUCT_BINDING)
    pin(binding['wheel_path'], PRODUCT['wheel_sha256'])
    for row in binding['source_manifest']:
        pin(Path(binding['install_root']) / row['path'], row['sha256'])
    for name in ('qualification/PRODUCT_IDENTITY.json', 'qualification/PREFLIGHT.json', 'consumer/PREFLIGHT.json'):
        data = read(NS / name)
        require(data['passed'] is True, f'required_preflight_failed/{name}')
        for row in data.get('source_pins', []):
            pin(row['path'], row['sha256'], row['bytes'])
    replay = read(NS / 'qualification/PRODUCT_SEMANTIC_PREFLIGHT.json')
    require(replay['models'] == replay['owned_Blender'] == 0 and replay['closed'] and
            all(row['CLI']['passed'] for row in replay['results'].values()), 'actual_installed_product_replay_required')

    launch = {label: dispatch('harness/run_slot.py', label, '--dispatch-smoke') for label in ORDER}
    recorders = {}
    for label, details in launch.items():
        group, phase = SLOTS[label]
        require(details['slot'] == label and details['group'] == group and details['schema'] == admission.SCHEMA
                and details['product'] == PRODUCT and Path(details['asset']) == ASSET
                and Path(details['run_root']) == EXTERNAL and Path(details['actual_product_schema']) == PRODUCT_SCHEMA,
                f'dispatch_not_current/{label}')
        expected = set(launch['QN']['tools']) | ({'human_eye_scene_observe'} if group == 'P' else set())
        require(set(details['tools']) == expected and len(launch['QN']['tools']) == 5, f'actual_tool_names_not_fair/{label}')
        for path in details['workspace_sources']:
            pin(path)
        if group == 'P':
            row = dispatch('harness/mcp_entry.py', '--dispatch-smoke', label)
            require(row['label'] == label and Path(row['current_binding']) == PRODUCT_BINDING
                    and Path(row['absolute_state_file']) == EXTERNAL / 'slots' / label / 'product_state.json',
                    f'actual_MCP_recorder_state_not_current/{label}')
            recorders[label] = row
    save(NS / 'harness/HOST_PREFLIGHT.json', {'passed': True, 'fresh_dispatch': launch, 'fresh_recorder': recorders})
    for path in NS.rglob('*'):
        if path.is_file():
            require(path.suffix != '.pyc', 'preflight_cache_must_not_enter_freeze')
            if path.suffix == '.py':
                ast.parse(path.read_bytes(), filename=str(path))
            pin(path)
    save(NS / 'FROZEN.json', {'schema': admission.SCHEMA, 'product': PRODUCT, 'asset_path': str(ASSET),
         'asset_sha256': ASSET_SHA256, 'passed_offline_preflight': True,
         'prompt_sha256': prompt['sha256'], 'prompt_bytes': prompt['bytes'], 'slots': list(ORDER),
         'qualification_slots': list(QUALIFICATION), 'formal_slots': list(FORMAL_LABELS),
         'max_Blender_starts': 8, 'max_models': 6, 'max_business_per_slot': 12,
         'max_qualification_rasters_per_slot': 6, 'max_formal_rasters_per_slot': 12, 'max_all_rasters': 84,
         'task_s': 450, 'owned_s': 600, 'product_diff_files': 0, 'product_builds': 0, 'product_installs': 0,
         'replacements': 0, 'argument_rewrites': 0, 'direct_inputs': [pins[p] for p in sorted(pins)]})
    print('Frozen', admission.verify_freeze(), len(pins), flush=True)


def closed_qualification(label, result, receipt, token):
    from PIL import Image

    proofs = result['qualification']['images']
    slot = (EXTERNAL / 'slots' / label).resolve(strict=True)
    for row in proofs.values():
        path = Path(row['path'])
        resolved = path.resolve(strict=True)
        require(str(resolved) == str(path) and resolved.is_relative_to(slot) and sha(path) == row['sha256']
                and path.stat().st_size == row['bytes'], f'closed_original_png_mismatch/{label}')
        with Image.open(path) as image:
            require(image.format == 'PNG' and image.size == (512, 512), f'closed_png_decode_mismatch/{label}')
            image.load()
    save(EXTERNAL / 'preflight' / f'{label}_CLOSED_IMAGES.json', {'passed': True, 'slot': label,
         'result_sha256': receipt['result_sha256'], 'freeze_sha256': token, 'reopened': proofs})


def sequence():
    token = admission.verify_freeze()
    require(not EXTERNAL.exists(), 'one_fresh_owned_sequence_only')
    sys.path.insert(0, read(PRODUCT_BINDING)['dependency_root'])
    journal = EXTERNAL / 'preflight/FORMAL_SEQUENCE.jsonl'
    journal.parent.mkdir(parents=True)
    journal.touch(exist_ok=False)
    qualifications_passed = True
    all_completed = True
    for label in ORDER:
        if label in FORMAL_LABELS and not qualifications_passed:
            append(journal, {'event': 'formal_not_admitted', 'labels': list(FORMAL_LABELS), 'reason': 'live_qualifications_incomplete'})
            return 1
        append(journal, {'event': 'start', 'label': label, 'started_ns': time.perf_counter_ns(), 'freeze_sha256': token})
        process = subprocess.run([sys.executable, '-IB', str(NS / 'harness/run_slot.py'), label], cwd=ROOT)
        try:
            result, receipt = admission.publication(label, token)
            safe = admission.can_continue(result, receipt)
            complete = safe and process.returncode == 0 and receipt['status'] == 'completed'
            reopened = False
            if label in QUALIFICATION:
                if complete:
                    try:
                        closed_qualification(label, result, receipt, token)
                        reopened = True
                    except (OSError, ValueError) as error:
                        append(journal, {'event': 'closed_image_rejected', 'label': label, 'error': str(error)})
                qualifications_passed &= complete and reopened
            all_completed &= complete
            append(journal, {'event': 'publication', 'label': label, 'exit_code': process.returncode,
                 'safe_to_continue': safe, 'status': receipt['status'], 'closed_images_verified': reopened,
                 'result_sha256': receipt['result_sha256'], 'model_consumers': result['model_consumers']})
        except Exception as error:
            append(journal, {'event': 'unconfirmed', 'label': label, 'exit_code': process.returncode, 'error': str(error)})
            return 1
        if not safe:
            return 1
    return 0 if all_completed else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_interpreter_I_B_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action', choices=('freeze', 'sequence'))
    raise SystemExit(globals()[cli.parse_args().action]())
