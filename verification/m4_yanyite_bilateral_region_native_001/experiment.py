"""Run one held-out bilateral task through the existing Codex consumer and owned Blender."""

import argparse
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
import zipfile


HERE = Path(__file__).resolve().parent
V = HERE.parent
sys.path.insert(0, str(HERE))
BASE = run_path(str(V/'m2_source_region_shared_normalization_live_001/experiment.py'))
read, write, append, pin, git, require = (BASE[key] for key in ('read', 'write', 'append', 'pin', 'git', 'require'))
RUN = Path('D:/he_m4_yanyite_bilateral_region_native_001').resolve()
PLAN = 'f6f80b34c3034f4b22368b4318e98e4f49f1eea5:docs/M4_YANYITE_BILATERAL_REGION_NATIVE_001_PLAN.md'
INSTALL_EVIDENCE = '48899b41f592fc60b266b4b278bd7e4b9d5c8daa'
PRODUCT = {'commit': '4104add44251b03a1eafc5af69502aa2575b632c',
           'source_sha256': '5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9',
           'wheel_sha256': '40a3aab846f9213eeb536f8828bc20ef42f5ba09f2430a2438baad2275882807'}
SLOTS = ('N1', 'P1')
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
PROMPT = HERE/'inputs/PROMPT.txt'
FROZEN = HERE/'FROZEN.json'
TRUTH = RUN/'preflight/BILATERAL_SOURCE_TRUTH.json'
DATA = RUN/'preflight/data/DATA_PREFLIGHT.json'
ENTRY = RUN/'preflight/RUNTIME_PREFLIGHT.json'
JOURNAL = RUN/'FORMAL_SEQUENCE.jsonl'
LIMITS = {'Blender_starts': 2, 'consumers': 2, 'business_per_slot': 12,
          'rasters_per_slot': 12, 'task_seconds': 450, 'owned_seconds': 600, 'replacements': 0}


def freeze():
    import host
    from costs import CURVED, PILOT

    require(not (RUN/'slots').exists() and not JOURNAL.exists(), 'one_freeze_prior_to_formal_slots')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN) and pin(sys.executable)['sha256'] == PYTHON_SHA,
            'fixed_planning_or_runtime_identity_changed')
    asset = pin(host.ASSET)
    require(asset['sha256'] == host.ASSET_SHA256 and asset['bytes'] == 3_415_766, 'original_asset_changed')
    binding_path = host.PRODUCT_BINDING
    relative_binding = binding_path.relative_to(HERE.parents[1]).as_posix()
    require(binding_path.read_bytes() == git('show', INSTALL_EVIDENCE + ':' + relative_binding),
            'accepted_installed_binding_mismatch')
    binding = read(binding_path)
    require((binding['preparation_git'], binding['source_sha256'], binding['wheel_sha256']) == tuple(PRODUCT.values())
            and len(binding['source_manifest']) == 143, 'fixed_product_identity_changed')
    wheel = Path(binding['wheel_path'])
    require(pin(wheel)['sha256'] == PRODUCT['wheel_sha256'], 'existing_wheel_mismatch')
    paths = {binding_path, wheel, host.ASSET, host.BLENDER, Path(sys.executable), PILOT, CURVED,
             V/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py',
             RUN/'preflight/STARTUP_FIRST_FAILURE.json',
             *host.retained_sources(), *[p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py', '.md', '.txt')]}
    with zipfile.ZipFile(wheel) as pack:
        for row in binding['source_manifest']:
            path = Path(binding['install_root'])/row['path']
            require(pin(path)['sha256'] == row['sha256'] and path.read_bytes() == pack.read(row['path']),
                    'installed_python_source_changed/'+row['path'])
            paths.add(path)
    for receipt in (TRUTH, DATA, ENTRY):
        proof = read(receipt)
        require(proof['passed'] is True, 'fixed_preflight_failed/'+receipt.name)
        paths.add(receipt)
        for item in proof.get('source_pins', proof.get('input_pins', [])):
            actual = pin(item['path'])
            require(all(actual[key] == item[key] for key in ('bytes', 'sha256')), 'preflight_source_changed/'+item['path'])
            paths.add(Path(item['path']))
    pins = {row['path']: row for row in map(pin, paths)}
    write(FROZEN, {'plan': PLAN, 'product': PRODUCT, 'asset_sha256': asset['sha256'], 'slots': list(SLOTS),
                   'prompt': pin(PROMPT), 'limits': LIMITS, 'passed_offline_preflight': True,
                   'request_configuration': ['0.152.1', 'gpt-6.1-sol', 'medium', 'default'],
                   'inputs': sorted(pins.values(), key=lambda row: row['path'])})
    print('Frozen', verify_freeze(FROZEN), len(pins), 'inputs', flush=True)


def verify_freeze(path):
    require(Path(path).resolve(strict=True) == FROZEN, 'current_freeze_only')
    f = read(path)
    require(f['plan'] == PLAN and f['product'] == PRODUCT and f['slots'] == list(SLOTS) and f['limits'] == LIMITS
            and f['passed_offline_preflight'] is True and f['prompt'] == pin(PROMPT)
            and all(pin(row['path']) == row for row in f['inputs']), 'fixed_live_inputs_changed')
    return pin(path)['sha256']


def publication(label, digest):
    directory = RUN/'slots'/label
    path = directory/'SLOT_RESULT.json'
    result = read(path)
    receipt = read(directory/'SLOT_PUBLICATION.json')
    require(result['label'] == receipt['label'] == label and result['freeze_sha256'] == digest
            and receipt['result_sha256'] == pin(path)['sha256'] and result['status'] == receipt['status'],
            'current_original_slot_publication_binding_failed/'+label)
    return result, receipt


def safe_to_continue(result, receipt):
    closure, owner = (result.get(key) or {} for key in ('closure_verification', 'owner_close'))
    budget = (result.get('budget') or {}).get('counts') or {}
    consumer = result.get('consumer') or {}
    return (receipt['owned_budget_passed'] is True and result['paid_API_calls'] == 0
            and closure.get('passed') is True and closure.get('status') == 'ready_closed'
            and owner.get('confirmed') is True and not owner.get('errors') and not owner.get('transport_errors')
            and (result.get('independent_before_after') or {}).get('passed') is True
            and budget.get('Blender_spawned_unknown') == budget.get('pending_raster_reservations') == 0
            and (not result.get('actual_model_admitted') or consumer.get('safe_to_continue') is True))


def admit(label, path):
    require(label in SLOTS, 'unregistered_formal_slot')
    digest = verify_freeze(path)
    existing = set(p.name for p in (RUN/'slots').iterdir()) if (RUN/'slots').exists() else set()
    preceding = SLOTS[:SLOTS.index(label)]
    require(existing == set(preceding) and all(safe_to_continue(*publication(key, digest)) for key in preceding),
            'wrong_live_order_or_previous_slot_unconfirmed')
    starts = [row for row in map(json.loads, JOURNAL.read_bytes().splitlines()) if row['event'] == 'start']
    require([row['label'] for row in starts] == [*preceding, label]
            and all(row['freeze_sha256'] == digest for row in starts), 'slot_not_reserved_in_controller_order')
    return {'freeze_sha256': digest, 'qualification_gate_sha256': pin(ENTRY)['sha256']}


def formal():
    digest = verify_freeze(FROZEN)
    require(not (RUN/'slots').exists(), 'no_substitute_formal_slots')
    JOURNAL.open('x').close()
    for index, label in enumerate(SLOTS):
        started = time.perf_counter_ns()
        append(JOURNAL, {'event': 'start', 'label': label, 'perf_ns': started, 'freeze_sha256': digest})
        process = subprocess.run([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), 'slot', label],
                                 cwd=HERE.parents[1])
        finished = time.perf_counter_ns()
        folder = RUN/'slots'/label
        pub = folder/'SLOT_PUBLICATION.json'
        row = {'event': 'exit', 'label': label, 'perf_ns': finished, 'controller_wall_ns': finished - started,
               'exit_code': process.returncode, 'status': 'missing', 'safe_to_continue': False}
        if pub.is_file():
            result, receipt = publication(label, digest)
            row.update(status=result['status'], publication=pin(pub), safe_to_continue=safe_to_continue(result, receipt))
        append(JOURNAL, row)
        if not row['safe_to_continue'] and index+1 < len(SLOTS):
            append(JOURNAL, {'event': 'blocked', 'label': label, 'unrun': list(SLOTS[index+1:]),
                            'reason': 'previous_owned_runtime_or_consumer_cleanup_not_confirmed'})
            break


def costs():
    from costs import summarize

    digest = verify_freeze(FROZEN)
    entries = {label: summarize(RUN/'slots'/label, digest) for label in SLOTS}
    same_prompt = all(row.get('initial_prompt_sha256') == pin(PROMPT)['sha256']
                      for row in entries.values() if row.get('model_consumers_launched'))
    write(RUN/'COSTS.json', {'freeze_sha256': digest, 'arms': entries, 'same_original_prompt': same_prompt,
          'provider_internal_time': None, 'provider_billing': None,
          'clock_scope': 'Observable nested owned Blender, Owner wire, product, and public CLI event intervals.'})


def archive():
    scanner = V/'perf050_dense_micro_surface_holdout_recovery_001/archive_evidence.py'
    check = run_path(str(scanner))['check_named_bytes']
    for path in RUN.rglob('*'):
        if path.is_file():
            check(path.relative_to(RUN).as_posix(), path.read_bytes())
    seal = BASE['archive']
    seal.__globals__['RUN'] = RUN
    seal()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('runtime-preflight', 'truth', 'freeze', 'formal', 'slot', 'costs', 'archive'))
    parser.add_argument('label', choices=SLOTS, nargs='?')
    args = parser.parse_args()
    require((args.phase == 'slot') == bool(args.label), 'named_formal_slot_required')
    if args.phase == 'slot':
        from host import run_slot

        raise SystemExit(run_slot(args.label, admit))
    if args.phase == 'runtime-preflight':
        from host import preflight

        preflight(ENTRY)
    elif args.phase == 'truth':
        from score import preflight

        preflight(TRUTH)
    else:
        globals()[args.phase]()
