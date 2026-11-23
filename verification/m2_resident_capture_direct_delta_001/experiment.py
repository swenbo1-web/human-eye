"""Freeze and run the one allowed live comparison after offline admission."""

import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build import BASE, CANDIDATE, PYTHON_SHA
from host import ASSET, ASSET_SHA256, BINDINGS, BLENDER, PREVIOUS, RUN, Slot, binding_identity, retained_sources


spec = importlib.util.spec_from_file_location('_resident_delta_previous_controller', PREVIOUS/'experiment.py')
retained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retained)
read, write, append, pin, git, require = (getattr(retained, key) for key in ('read', 'write', 'append', 'pin', 'git', 'require'))
PLAN = '57c5170c53b96c4665eed46c8cd275890a041cd2:docs/M2_RESIDENT_CAPTURE_DIRECT_DELTA_001_PLAN.md'
PREP = RUN/'preflight/fixed_entry'
CHECK = RUN/'checks'
ORIGINAL = Path('D:/he_m2_source_region_shared_normalization_live_001').resolve()
OLD_SEAL = ORIGINAL/'sealed/ORIGINAL_RUNTIME.zip'
OLD_SHA = '534a0d0a584a0c29544d11acac1475dfa30adb952f8bb0215944c92253506960'
CONTROLS = CHECK/'controls/RESULT.json'
RECHECK = CHECK/'PRIOR_LIVE_GATE.json'
LIMITS = retained.LIMITS


def startup(label, root):
    require(not (RUN/'slots').exists(), 'no_live_slots_before_preflight')
    binding = binding_identity(label, BINDINGS[label])
    root.mkdir(parents=True, exist_ok=False)
    slot = Slot(root, label, BINDINGS[label], preflight=True)
    with slot:
        catalogue = slot.product_tools
        require(any(tool['name'] == 'human_eye_scene_observe' for tool in catalogue), 'observe_missing_from_actual_catalogue')
        invalid = {'jsonrpc': '2.0', 'id': 'reject-invalid-image-flag', 'method': 'tools/call', 'params': {
            'name': 'human_eye_scene_observe', 'arguments': {'include_image': 'invalid'}}}
        rejected = slot.client.call(invalid)
        error = rejected.get('result', {})
        require(error.get('isError') is True and rejected['id'] == invalid['id'], 'invalid_arguments_not_rejected')
        listing = slot.client.call({'jsonrpc': '2.0', 'id': 'recover-valid-catalogue', 'method': 'tools/list'})
        require(listing['id'] == 'recover-valid-catalogue' and listing['result']['tools'] == catalogue,
                'real_installed_service_did_not_recover_after_rejection')
    close = slot.finish()
    require(close['status'] == 'completed' and not any(close['budget']['counts'].values()), 'startup_close_or_budget')
    worker = read(slot.folder/'mcp_io/REAL_HOST_STAGES.json')
    require(worker['requests'] == [] and worker['gc_after'] == worker['gc_before'], 'preflight_touched_live_host_or_GC')
    module_files = {Path(module.__file__).resolve() for module in tuple(sys.modules.values())
                    if getattr(module, '__file__', None) and Path(module.__file__).resolve().is_relative_to(HERE.parent)}
    paths = {*retained_sources(), *module_files, *[Path(binding['install_root'])/row['path']
             for row in binding['source_manifest']], Path(binding['wheel_path'])}
    write(root/'PREFLIGHT.json', {'passed': True, 'label': label, 'actual_tools': catalogue,
          'rejected_then_recovered': True, 'source_sha256': binding['source_sha256'], 'closed': close,
          'input_pins': [pin(path) for path in sorted(paths)]})


def freeze():
    from live_checks import retained_sources as retained_score_sources

    require(not (RUN/'slots').exists(), 'cannot_freeze_after_live_start')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN), 'frozen_planning_source_changed')
    require(pin(ASSET)['sha256'] == ASSET_SHA256 and pin(sys.executable)['sha256'] == PYTHON_SHA and
            pin(OLD_SEAL)['sha256'] == OLD_SHA, 'fixed_Git_asset_interpreter_or_previous_originals_changed')
    controls, recheck = read(CONTROLS), read(RECHECK)
    require(controls['passed'] and recheck['passed'] and set(controls['samples']) == set(BINDINGS) and
            all(len(rows) >= 8 for rows in controls['samples'].values()) and controls['reduction'] >= .80,
            'offline_capture_or_previous_rejections_not_passed')
    paths = {ASSET, BLENDER, Path(sys.executable), *retained.historical_layout(), OLD_SEAL,
             ORIGINAL/'sealed/RAW_INDEX.json', ORIGINAL/'SCORE.json', CONTROLS, RECHECK,
             HERE/'install/BUILD_INSTALL.json', *retained_score_sources(),
             *[p for p in HERE.iterdir() if p.suffix in ('.py', '.md')]}
    for row in recheck['input_pins']:
        require(pin(row['path']) == row, 'prior_failure_recheck_source_changed')
        paths.add(Path(row['path']))
    units = [CHECK/f'UNIT_{arm}.json' for arm in BINDINGS]
    for test, label in zip(units, BINDINGS, strict=True):
        unit = read(test)
        require(unit['arm'] == label and unit['tested'] == 26 and not (unit['errors'] or unit['failures']),
                'fixed_contract_units_did_not_pass')
        paths.add(test)
    identity, catalogues = {}, []
    for label, binding in BINDINGS.items():
        build = binding_identity(label, binding)
        require(build['preparation_git'] == {'A': BASE, 'B': CANDIDATE}[label], 'frozen_product_Git_differs')
        identity[label] = {k: build[k] for k in ('preparation_git', 'source_sha256', 'wheel_sha256')}
        output = PREP/label/'PREFLIGHT.json'
        proof = read(output)
        require(proof['passed'] and proof['label'] == label and proof['rejected_then_recovered'] and
                proof['source_sha256'] == build['source_sha256'] and
                all(pin(row['path']) == row for row in proof['input_pins']), 'real_cold_startup_preflight_not_fixed')
        catalogues.append(proof['actual_tools'])
        paths.update((binding, output, *(Path(row['path']) for row in proof['input_pins'])))
    require(catalogues[0] == catalogues[1], 'actual_product_catalogue_changed')
    source = {row['path']: row for row in map(pin, paths)}
    write(HERE/'FROZEN.json', {'plan': PLAN, 'asset_sha256': ASSET_SHA256, 'slots': list(BINDINGS),
          'limits': LIMITS, 'request_order': retained.REQUESTS, 'installs': identity,
          'inputs': sorted(source.values(), key=lambda row: row['path'])})
    print('Frozen', verify_freeze(), len(source), 'inputs', flush=True)


def verify_freeze():
    path = HERE/'FROZEN.json'
    f = read(path)
    require(f['plan'] == PLAN and f['slots'] == list(BINDINGS) and f['limits'] == LIMITS and
            all(pin(row['path']) == row for row in f['inputs']), 'fixed_live_inputs_changed')
    return pin(path)['sha256']


def live_slot(label):
    from live_checks import selection, summarize

    frozen = verify_freeze()
    rows = map(json.loads, (RUN/'FORMAL_SEQUENCE.jsonl').read_bytes().splitlines())
    starts = [row for row in rows if row['event'] == 'start']
    require([row['label'] for row in starts] == list(BINDINGS)[:list(BINDINGS).index(label) + 1] and
            all(row['freeze_sha256'] == frozen for row in starts), 'actual_slot_not_admitted_in_order')
    start = time.perf_counter_ns()
    slot = Slot(RUN, label, BINDINGS[label], start_ns=start)
    record = {'label': label, 'status': 'failed', 'observations': [], 'freeze_sha256': frozen}
    try:
        with slot:
            rows = selection(read(slot.source()))
            for (region, include), request in zip(retained.REQUESTS, retained.arguments(rows), strict=True):
                response, proof = slot.observe(request)
                record['observations'].append({'region': region, 'include_image': include, 'host_record': proof})
                packet = retained.reply_packet(response)
                if include:
                    image, = packet['images']
                    require(sum(block['type'] == 'image' for block in response['result']['content']) == 1,
                            'same_capture_upper_image_not_really_delivered')
            if not image.get('local_image_path'):
                _, record['image_read'] = slot.read_images(image['image_ref'])
        record['closure'] = slot.finish()
        require(record['closure']['status'] == 'completed', 'actual_slot_closure_or_readonly_proof_failed')
        closed = time.perf_counter_ns()
        record['timing'] = summarize(slot.folder, window=(start, closed))
        record['status'] = 'completed'
    except Exception as exc:
        record['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        if slot.folder.exists():
            try:
                record['closure'] = slot.finish()
            except Exception as close_error:
                record['closure_error'] = {'type': type(close_error).__name__, 'message': str(close_error)}
        raise
    finally:
        closed = time.perf_counter_ns()
        record['window'] = {'opened_ns': start, 'closed_ns': closed, 'wall_ns': closed - start}
        result = slot.folder/'SLOT_RESULT.json'
        write(result, record)
        write(slot.folder/'SLOT_PUBLICATION.json', {'label': label, 'status': record['status'],
              'freeze_sha256': frozen, 'result_sha256': pin(result)['sha256']})


def formal():
    frozen = verify_freeze()
    journal = RUN/'FORMAL_SEQUENCE.jsonl'
    require(not (RUN/'slots').exists(), 'no_replacement_formal_slots')
    journal.open('x').close()
    failed = False
    for label in BINDINGS:
        started = time.perf_counter_ns()
        append(journal, {'event': 'start', 'label': label, 'perf_ns': started, 'freeze_sha256': frozen})
        process = subprocess.run([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), 'slot', label], cwd=retained.REPO)
        closed = time.perf_counter_ns()
        path = RUN/'slots'/label/'SLOT_PUBLICATION.json'
        status = read(path)['status'] if path.is_file() else 'missing'
        append(journal, {'event': 'exit', 'label': label, 'perf_ns': closed, 'controller_wall_ns': closed-started,
                        'exit_code': process.returncode, 'status': status, 'publication': pin(path) if path.is_file() else None})
        failed |= bool(process.returncode or status != 'completed')
    return int(failed)


def verify_pair():
    import live_checks

    outcome = {'freeze_sha256': verify_freeze(), 'arms': {}, 'pair': None, 'passed': False}
    for label in BINDINGS:
        folder = RUN/'slots'/label
        row = {'label': label, 'actual_status': 'unrun', 'passed': False}
        outcome['arms'][label] = row
        path = folder/'SLOT_RESULT.json'
        if not path.exists():
            continue
        raw = read(path)
        row.update(actual_status=raw['status'], result=pin(path))
        if raw['status'] != 'completed':
            row['error'] = raw['error']
            continue
        try:
            row['verification'] = live_checks.verify_slot(folder, label)
            row['passed'] = True
        except Exception as exc:
            row['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    if all(row['passed'] for row in outcome['arms'].values()):
        try:
            outcome['pair'] = live_checks.verify_pair(*(entry['verification'] for entry in outcome['arms'].values()))
            outcome['passed'] = True
        except Exception as exc:
            outcome['pair_error'] = {'type': type(exc).__name__, 'message': str(exc)}
    write(RUN/'SCORE.json', outcome)
    return int(not outcome['passed'])


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_flags_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight', 'verify-old', 'freeze', 'formal', 'slot', 'score', 'archive'))
    parser.add_argument('label', choices=BINDINGS, nargs='?')
    parser.add_argument('--startup-root', type=Path)
    option = parser.parse_args()
    require((option.phase in ('preflight', 'slot')) == bool(option.label) and
            (option.startup_root is None or option.phase == 'preflight'), 'exactly_one_named_arm_where_required')
    if option.phase == 'preflight':
        startup(option.label, (option.startup_root or PREP)/option.label)
    elif option.phase == 'verify-old':
        from live_checks import preflight

        preflight(RECHECK)
    elif option.phase == 'slot':
        live_slot(option.label)
    elif option.phase == 'score':
        raise SystemExit(verify_pair())
    elif option.phase == 'archive':
        retained.RUN = RUN
        retained.archive()
    else:
        raise SystemExit(globals()[option.phase]())
