"""Run and seal a single paired comparison of the actual installed Blender path."""

import argparse
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
V = HERE.parent
RUN = Path('D:/he_m2_source_region_shared_normalization_live_001').resolve()
PREFLIGHT_ROOT = RUN/'preflight/final_entry'
HISTORY = Path('D:/he_m4_yanyite_dual_curved_region_native_001').resolve()
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')
ASSET_SHA = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
PLAN = '88be34a9ab7b94af8118c88bef72322dc34327fc:docs/M2_SOURCE_REGION_SHARED_NORMALIZATION_LIVE_001_PLAN.md'
HISTORY_GIT = 'eeae0719a'
INSTALL_RECEIPT_GIT = {'A': 'c5f987ef', 'B': 'b82afeee'}
INSTALLS = {
    'A': ('m2_source_region_normalization_triangle_list_001', '31e9b46a68e5f791df9a75a1bad11caa8a6e8410',
          '6aaa60003ebbb8d689b8d9858a74a247c6d4f0de13bacac0d5dcead019555d70',
          '4724ff9f97cd8eb108b38396fa5ea3a12c3daf0fa960dc62eedcfe10e8f34e14'),
    'B': ('m2_source_region_shared_normalization_001', 'ee385e9842b9ea413f9d63dea6b74e88c8a051da',
          'df09c607da2e1e1c17855474943ef536a0a8ecc145d92f409f7d8c72f1cd9eaa',
          'a3b46a29c4361318ab9adf7359951307717a8d0844fe53ed29e1ab39fc7eee63'),
}
REQUESTS = (('upper', False), ('lower', False), ('upper', True), ('upper', True))
ARGS_SOURCE = [HISTORY/'slots/P1/product_calls'/f'call_{i:03d}'/'REQUEST.json' for i in (1, 2)]
HISTORICAL_INITIAL = HISTORY/'slots/P1/initial_capture/TERMINAL_SOURCE.json'
LIMITS = {'Blender_starts': 2, 'observations_per_slot': 4, 'optional_image_reads_per_slot': 1,
          'rasters_per_slot': 1, 'models': 0, 'replacement_slots': 0}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as out:
        json.dump(value, out, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')


def append(path, value):
    with path.open('a', encoding='utf8', newline='\n') as out:
        out.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
        out.flush()
        os.fsync(out.fileno())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as source:
        return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': file_digest(source, 'sha256').hexdigest()}


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def binding_for(label):
    return V/INSTALLS[label][0]/'install/PRODUCT_RUN_BINDING.json'


def installed_sources(label):
    path = binding_for(label)
    identity = read(path)
    _, commit, source_sha, wheel_sha = INSTALLS[label]
    receipt = f'{INSTALL_RECEIPT_GIT[label]}:{path.relative_to(REPO).as_posix()}'
    require(path.read_bytes() == git('show', receipt),
            'installed_identity_receipt_not_the_preceding_accepted_Git_blob/' + label)
    require((identity['preparation_git'], identity['source_sha256'], identity['wheel_sha256'],
             len(identity['source_manifest'])) == (commit, source_sha, wheel_sha, 143),
            'installed_arm_identity_differs/' + label)
    wheel = pin(identity['wheel_path'])
    require(wheel['sha256'] == wheel_sha, 'installed_wheel_origin_changed/' + label)
    pins = [pin(path), wheel]
    for row in identity['source_manifest']:
        actual = pin(Path(identity['install_root'])/row['path'])
        require(actual['sha256'] == row['sha256'], 'installed_source_changed/' + row['path'])
        pins.append(actual)
    return pins


def historical_layout():
    manifest = V/'m4_yanyite_dual_curved_region_native_001/RESULT.json'
    require(manifest.read_bytes() == git('show', f'{HISTORY_GIT}:{manifest.relative_to(REPO).as_posix()}'),
            'preceding_live_result_not_frozen')
    index = HISTORY/'sealed/RAW_INDEX.json'
    if not index.exists():
        index = HISTORY/'sealed/ORIGINAL_RUNTIME_INDEX.json'
    bundle = HISTORY/'sealed/ORIGINAL_RUNTIME.zip'
    with zipfile.ZipFile(bundle) as raw:
        names = raw.namelist()
        for path in (*ARGS_SOURCE, HISTORICAL_INITIAL):
            suffix = '/'+path.relative_to(HISTORY).as_posix()
            found = [name for name in names if ('/'+name).endswith(suffix)]
            require(len(found) == 1 and raw.read(found[0]) == path.read_bytes(),
                    'preceding_raw_request_or_snapshot_not_its_sealed_member/' + path.name)
    # The archive checksum pins the historical requests even when the original manifest uses a different index name.
    archive = pin(bundle)
    require(archive['sha256'] == '6bf18e4d442b8507c42b1f60961e56dbf1bf3236e730fe84ffc007e8f6efd678',
            'preceding_Yanyite_archive_changed')
    return [manifest, bundle, *ARGS_SOURCE, HISTORICAL_INITIAL, *([index] if index.is_file() else [])]


def arguments(selection):
    old = {region: read(path)['params']['arguments'] for region, path in zip(('upper', 'lower'), ARGS_SOURCE, strict=True)}
    for region, source in old.items():
        query = source['query']
        require(source['include_image'] is False and query['mode'] == 'source_region'
                and query['reference'] == {'name': 'Cube'} and query['requested_facts'] == ['surface_proximity']
                and query['region']['source_triangle_indices'] == selection[region],
                'actual_current_ordered_selection_differs_from_P1/' + region)
    return [{**old[region], 'include_image': include} for region, include in REQUESTS]


def reply_packet(response):
    result = response['result']
    require(result['isError'] is False, 'actual_installed_product_call_rejected')
    text = [item for item in result['content'] if item['type'] == 'text']
    require(bool(text), 'actual_installed_product_returned_no_structured_body')
    return json.loads(text[0]['text'])


def verify_freeze():
    path = HERE/'FROZEN.json'
    frozen = read(path)
    require(frozen['plan'] == PLAN and frozen['limits'] == LIMITS and frozen['slots'] == list(INSTALLS)
            and all(pin(row['path']) == row for row in frozen['inputs']), 'frozen_live_inputs_changed')
    return pin(path)['sha256']


def preflight(label):
    from host import Slot, retained_sources
    from score import selection

    require(not (RUN/'slots').exists(), 'actual_slots_exist_before_startup_preflight')
    pins = installed_sources(label)
    known = selection(read(HISTORICAL_INITIAL))
    exact_requests = arguments(known)
    origin = PREFLIGHT_ROOT/label
    origin.mkdir(parents=True, exist_ok=False)
    slot = Slot(origin, label, binding_for(label), preflight=True)
    with slot:
        catalogue = slot.product_tools
        require(any(row['name'] == 'human_eye_scene_observe' for row in catalogue), 'actual_catalogue_missing_observe')
    close = slot.finish()
    require(close['status'] == 'completed' and not any(close['budget']['counts'].values()),
            'actual_preflight_close_or_zero_budget_not_confirmed')
    module_paths = sorted({Path(module.__file__).resolve() for module in tuple(sys.modules.values())
                           if getattr(module, '__file__', None) and Path(module.__file__).resolve().is_relative_to(V)})
    receipt = {'passed': True, 'label': label, 'normalization_replay': False, 'actual_Blender_started': False,
               'actual_tools': catalogue, 'closed': close, 'request_geometry_document_digest': sha256(
                   json.dumps(exact_requests, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
               'input_pins': [*pins, *[pin(path) for path in sorted(set(module_paths) | set(retained_sources()))]]}
    write(origin/'PREFLIGHT.json', receipt)
    return receipt


def freeze():
    require(not (RUN/'slots').exists(), 'actual_slots_exist_before_freeze')
    plan = HERE/'PLAN.md'
    require(plan.read_bytes() == git('show', PLAN), 'fixed_plan_not_identical_to_Git')
    asset = pin(ASSET)
    require(asset['bytes'] == 3_415_766 and asset['sha256'] == ASSET_SHA, 'original_Yanyite_bytes_changed')
    inputs = {item['path']: item for item in map(pin, [ASSET, BLENDER, sys.executable, *historical_layout(),
              *[path for path in HERE.iterdir() if path.suffix in ('.py', '.md')]])}
    arms = {}
    for label in INSTALLS:
        proof_path = PREFLIGHT_ROOT/label/'PREFLIGHT.json'
        proof = read(proof_path)
        require(proof['passed'] and proof['label'] == label and not proof['actual_Blender_started'],
                'actual_cold_preflight_not_established/' + label)
        report = pin(proof_path)
        inputs[report['path']] = report
        for row in proof['input_pins']:
            require(pin(row['path']) == row, 'preflight_inputs_changed_before_freeze')
            inputs[row['path']] = row
        arms[label] = proof
    require(arms['A']['actual_tools'] == arms['B']['actual_tools'] and
            arms['A']['request_geometry_document_digest'] == arms['B']['request_geometry_document_digest'],
            'catalogue_or_fixed_current_requests_differed_between_arms')
    write(HERE/'FROZEN.json', {'plan': PLAN, 'asset_sha256': ASSET_SHA, 'limits': LIMITS, 'slots': list(INSTALLS),
          'directions': REQUESTS, 'installs': INSTALLS, 'inputs': sorted(inputs.values(), key=lambda row: row['path'])})
    print('Frozen', verify_freeze(), len(inputs), 'inputs', flush=True)


def run_slot(label):
    import meter
    from host import Slot
    from score import selection

    digest = verify_freeze()
    journal = RUN/'FORMAL_SEQUENCE.jsonl'
    launches = [row for row in map(json.loads, journal.read_text(encoding='utf8').splitlines())
                if row['event'] == 'start']
    require([row['label'] for row in launches] == list(INSTALLS)[:list(INSTALLS).index(label) + 1]
            and all(row['freeze_sha256'] == digest for row in launches), 'actual_slot_was_not_admitted_in_order')
    record = {'label': label, 'status': 'failed', 'observations': [], 'freeze_sha256': digest}
    start = time.perf_counter_ns()
    slot = Slot(RUN, label, binding_for(label), start_ns=start)
    folder = RUN/'slots'/label
    try:
        with slot:
            initial = slot.source()
            if isinstance(initial, (str, Path)):
                initial = read(initial)
            chosen = selection(initial)
            record['selected_counts'] = {k: len(v) for k, v in chosen.items()}
            for (region, has_image), request in zip(REQUESTS, arguments(chosen), strict=True):
                response, entry = slot.observe(request)
                record['observations'].append({'region': region, 'include_image': has_image, 'host_record': entry})
                packet = reply_packet(response)
                if has_image:
                    latest_images = packet['images']
                    require(len(latest_images) == 1 and len([block for block in response['result']['content']
                            if block['type'] == 'image']) == 1, 'same_capture_upper_image_not_really_delivered')
            image, = latest_images
            if not image.get('local_image_path'):
                _, record['image_read'] = slot.read_images(image['image_ref'])
        record['closure'] = slot.finish()
        require(record['closure']['status'] == 'completed', 'actual_slot_closure_or_readonly_proof_failed')
        closed = time.perf_counter_ns()
        record['timing'] = meter.summarize(folder, window=(start, closed))
        record['status'] = 'completed'
    except Exception as exc:
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if folder.exists():
            try:
                record['closure'] = slot.finish()
            except Exception as close_error:
                record['closure_error'] = {'type': type(close_error).__name__, 'message': str(close_error)}
        raise
    finally:
        closed = time.perf_counter_ns()
        record['window'] = {'opened_ns': start, 'closed_ns': closed, 'wall_ns': closed - start}
        path = folder/'SLOT_RESULT.json'
        write(path, record)
        write(folder/'SLOT_PUBLICATION.json', {'label': label, 'status': record['status'],
                                              'freeze_sha256': digest, 'result_sha256': pin(path)['sha256']})


def formal():
    digest = verify_freeze()
    journal = RUN/'FORMAL_SEQUENCE.jsonl'
    require(not (RUN/'slots').exists(), 'no_replacement_formal_slots')
    journal.open('x').close()
    for label in INSTALLS:
        started = time.perf_counter_ns()
        append(journal, {'event': 'start', 'label': label, 'perf_ns': started, 'freeze_sha256': digest})
        process = subprocess.run([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), 'slot', label],
                                 cwd=REPO)
        closed = time.perf_counter_ns()
        publication = RUN/'slots'/label/'SLOT_PUBLICATION.json'
        row = {'event': 'exit', 'label': label, 'perf_ns': closed, 'controller_wall_ns': closed-started,
               'exit_code': process.returncode}
        if publication.is_file():
            row['publication'] = pin(publication)
            row['status'] = read(publication)['status']
        append(journal, row)
    return int(any(row['exit_code'] or row.get('status') != 'completed'
                   for row in map(json.loads, journal.read_text(encoding='utf8').splitlines()) if row['event'] == 'exit'))


def score():
    from score import verify_pair, verify_slot

    digest = verify_freeze()
    result = {'freeze_sha256': digest, 'arms': {}, 'pair': None, 'passed': False}
    for label in INSTALLS:
        folder = RUN/'slots'/label
        path = folder/'SLOT_RESULT.json'
        arm = {'label': label, 'actual_status': 'unrun', 'passed': False}
        result['arms'][label] = arm
        if not path.is_file():
            continue
        arm['result'] = pin(path)
        raw = read(path)
        arm['actual_status'] = raw['status']
        if raw['status'] != 'completed':
            arm['error'] = raw['error']
            continue
        try:
            arm['verification'] = verify_slot(folder, label)
            arm['passed'] = True
        except Exception as error:
            arm['error'] = {'type': type(error).__name__, 'message': str(error)}
    if all(arm['passed'] for arm in result['arms'].values()):
        try:
            result['pair'] = verify_pair(*(arm['verification'] for arm in result['arms'].values()))
            result['passed'] = True
        except Exception as error:
            result['pair_error'] = {'type': type(error).__name__, 'message': str(error)}
    write(RUN/'SCORE.json', result)
    return int(not result['passed'])


def archive():
    output = RUN/'sealed'
    output.mkdir(exist_ok=False)
    archive_path = output/'ORIGINAL_RUNTIME.zip'
    members = {}
    with zipfile.ZipFile(archive_path, 'x', zipfile.ZIP_DEFLATED, compresslevel=4) as z:
        for path in sorted(RUN.rglob('*')):
            if not path.is_file() or path.is_relative_to(output):
                continue
            name = path.relative_to(RUN).as_posix()
            info = pin(path)
            members[name] = {key: info[key] for key in ('bytes', 'sha256')}
            z.write(path, name)
    with zipfile.ZipFile(archive_path) as z:
        require(z.testzip() is None and set(z.namelist()) == set(members), 'raw_archive_members_or_crc_changed')
        for name, info in members.items():
            with z.open(name) as data:
                require(z.getinfo(name).file_size == info['bytes'] and file_digest(data, 'sha256').hexdigest() == info['sha256'],
                        'raw_archive_member_not_exact/' + name)
    write(output/'RAW_INDEX.json', {'archive': pin(archive_path), 'member_count': len(members), 'members': members})


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_flags_required')
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight', 'freeze', 'formal', 'slot', 'score', 'archive'))
    parser.add_argument('label', choices=INSTALLS, nargs='?')
    opt = parser.parse_args()
    require((opt.phase in ('preflight', 'slot')) == bool(opt.label), 'exactly_one_named_arm_required')
    if opt.phase in ('preflight', 'slot'):
        (preflight if opt.phase == 'preflight' else run_slot)(opt.label)
    else:
        raise SystemExit(globals()[opt.phase]())
