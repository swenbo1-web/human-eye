"""Qualify exact request registration using two sealed requests and the real installed MCP."""
import copy
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
OLD_CODE = HERE.parent / 'm4_reference_only_intent_holdout_001'
sys.path[:0] = [str(HERE), str(OLD_CODE)]
from registration import encode, fingerprint, registration_scope
import diagnostic_replay as old

need, read, save, pin = old.need, old.read, old.save, old.pin
BATCH = 'M4-NEAREST-SURFACE-FIRST-FOCUS-001'
ORIGIN = 'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
ADMIN = 'ea305a98b776be98781d877484a72c3b9baf3799852d7721903d97d461e23f9a'
REVIEW = '8f8fd55397469128804593617c6819a3bb398560'
IMPLEMENTATION = 'fe94a6644'
REVIEW_PATH = 'verification/m4_reference_only_intent_holdout_001/INDEPENDENT_REVIEW.md'
REVIEW_HASH = '0432765b555329a6b996041d00bd5e812904c76310b93094bc0374bd25ee49e8'
ZIP_HASH = '956d479d4d7d7a4516e3a9bea0f9f480f1cbce22bb4ab4cf3fea430fd08500a4'
INDEX_HASH = '174f15c8378e811157158fbaa8e335807a0d88abef5598fa57c54bad78ba24c4'
MEMBERS = ('preflight/FROZEN_EXECUTION.json', 'preflight/fixture/TARGET_TRUTH.json',
           'preflight/fixture/EVALUATED_SOURCE.json', 'DIAGNOSTIC_EXECUTION.json',
           *(f'slots/DIAGNOSTIC/{name}' for name in ('REGISTERED.json', 'ledger.json', 'closed.json', 'post_capture.json',
              '01-init.tx', '02-tools.tx', '03-K.tx', '04-T.tx', '03-K.rx', '04-T.rx')))


def source_custody(root):
    need(root.name == BATCH and pin(root / 'preflight/ADMIN_PLAN.md')['sha256'] == ADMIN,
         'incorrect_new_registration_administration')
    checkout = HERE.parents[1]

    def git(*args):
        return subprocess.check_output(['git', '-C', str(checkout), *args])

    head, parent = git('rev-list', '--parents', '-n', '1', REVIEW).decode().split()
    proof = git('show', f'{REVIEW}:{REVIEW_PATH}')
    need(head == REVIEW and parent.startswith(IMPLEMENTATION)
         and sha256(proof).hexdigest() == REVIEW_HASH and ZIP_HASH.encode() in proof,
         'unverified_old_independent_review')
    source = root.parent / ORIGIN
    index = pin(source / 'sealed/RAW_INDEX.json')
    archive = pin(source / 'sealed/ORIGINAL_RUNTIME.zip')
    manifest = read(index['path'])
    need(index['sha256'] == INDEX_HASH and archive['sha256'] == ZIP_HASH
         and manifest['archive'] == {'bytes': archive['bytes'], 'sha256': archive['sha256']}
         and manifest['member_count'] == len(manifest['members']) == 265, 'old_archive_identity')
    extracted = {}
    with ZipFile(archive['path']) as bundle:
        names = bundle.namelist()
        need(bundle.testzip() is None and len(names) == len(set(names)) == 265
             and set(names) == set(manifest['members']), 'old_archive_inventory_changed')
        for name in MEMBERS:
            raw = bundle.read(name)
            observed = {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}
            need(manifest['members'][name] == observed and (source / name).read_bytes() == raw,
                 'old_member_mismatch/' + name)
            extracted[name] = {**observed, 'path': str((source / name).resolve(strict=True))}
    freeze, truth, scene, domain, planned = old.inputs(source)
    return source, freeze, scene, planned, {'independent_review': REVIEW, 'review_sha256': REVIEW_HASH,
           'archive': archive, 'index': index, 'members': extracted}


def prepare(root, folder):
    source, freeze, scene, expected, custody = source_custody(root)
    job = old.diagnostic.frozen(source)['jobs']['DIAGNOSTIC']
    original = source / 'slots/DIAGNOSTIC'
    planned = [{'label': t['label'], 'request': read(original / f"{t['id']:02d}-{t['label']}.tx")}
               for t in expected]
    need([r['label'] for r in planned] == ['K', 'T'], 'unexpected_registration_order')
    k, t = (r['request'] for r in planned)
    need(k['params']['arguments']['query']['objects'] == t['params']['arguments']['query']['objects'],
         'missing_same_object_control')

    def variant(req, **changes):
        value = copy.deepcopy(req)
        value.update(changes)
        return value

    parameter = copy.deepcopy(k)
    parameter['params']['arguments']['include_image'] = False
    detail = copy.deepcopy(t)
    detail['params']['arguments']['response_detail'] = 'brief'
    sequence = [
        ('initialize', (original / '01-init.tx').read_bytes(), None),
        ('tools', (original / '02-tools.tx').read_bytes(), None),
        ('swap_t_to_k', encode(variant(t, id=k['id'])) + b'\n', 'registered_request_mismatch'),
        ('swap_k_to_t', encode(variant(k, id=t['id'])) + b'\n', 'registered_request_mismatch'),
        ('wrong_image', encode(parameter) + b'\n', 'registered_request_mismatch'),
        ('wrong_detail', encode(detail) + b'\n', 'registered_request_mismatch'),
        ('wrong_id', encode(variant(k, id=53)) + b'\n', 'unregistered_request_id'),
        ('K', (original / '03-K.tx').read_bytes(), None),
        ('duplicate_k', (original / '03-K.tx').read_bytes(), 'registered_request_already_dispatched'),
        ('T', (original / '04-T.tx').read_bytes(), None),
        ('duplicate_t', (original / '04-T.tx').read_bytes(), 'registered_request_already_dispatched'),
    ]
    folder.mkdir(parents=True, exist_ok=False)
    records = []
    for order, (name, wire, reject) in enumerate(sequence, 1):
        dest = folder / f'{order:02d}-{name}.tx'
        dest.write_bytes(wire)
        records.append({'name': name, 'tx': pin(dest), 'expected_rejection': reject})
    specification = {'batch': BATCH, 'old_custody': custody, 'product': freeze['product'],
                     'job': job, 'planned': planned, 'sequence': records,
                     'evidence_scripts': [pin(Path(__file__)), pin(HERE / 'registration.py')],
                     'limits': {'product_dispatch': 2, 'controls': 7, 'raster_per_call': 2, 'Blender': 0, 'models': 0}}
    save(folder / 'REGISTRATION_FREEZE.json', specification)
    return specification


def serve(root, folder):
    specification = read(folder / 'REGISTRATION_FREEZE.json')
    source, freeze, scene, _, custody = source_custody(root)
    need(specification['old_custody'] == custody and specification['product'] == freeze['product']
         and all(old.diagnostic.confirm(v) for v in specification['evidence_scripts']),
         'registration_freeze_drift')
    job = specification['job']
    sys.path.insert(0, job['candidate_site'])
    from human_eye_plugin import active_observation_images, live_spatial_mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    need(identity['source_kind'] == 'installed_distribution'
         and identity['source_sha256'] == job['candidate_source_sha256'] == freeze['product']['runtime_sha256']
         and identity['source_files'] == job['runtime_sources'], 'old_replayed_install_drift')
    config = folder / 'config.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'project_root': str(folder),
                  'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'request_budget_s': 30,
                  'expected_identity': {'source_sha256': identity['source_sha256']}})
    active = None
    captures = []
    product_calls = []
    raster_calls = []

    class FrozenCapture:
        def capture_scene(self):
            permit = active.active if active is not None else None
            need(permit is not None and len(captures) < 2, 'capture_before_registration_or_after_budget')
            captures.append(permit['label'])
            active.service_event('captured_sealed_terminal', path=custody['members']['slots/DIAGNOSTIC/post_capture.json'])
            return copy.deepcopy(scene)

    service = LiveSpatialService(config, host=FrozenCapture(), production_mode=True)
    original = service._observe_active_observation
    rasterize = active_observation_images.rasterize_attention

    def guarded_raster(*args, **kwargs):
        permit = active.active
        need(permit is not None and raster_calls.count(permit['label']) < 2, 'registered_raster_limit')
        raster_calls.append(permit['label'])
        active.service_event('real_software_raster', occurrence=raster_calls.count(permit['label']))
        return rasterize(*args, **kwargs)

    def observed(*args, **kwargs):
        permit = active.active
        need(permit is not None and permit['label'] not in product_calls, 'not_unique_registered_service_call')
        parameters = next(r['request']['params']['arguments'] for r in specification['planned']
                          if r['label'] == permit['label'])
        query = parameters['query']
        need(kwargs['selector'] == query['objects'][0] and kwargs['focus'] == query['focus']
             and kwargs['include_image'] is parameters['include_image'], 'normalized_service_arguments_changed')
        product_calls.append(permit['label'])
        active.service_event('product_service_started', selector=kwargs['selector'], focus=kwargs['focus'])
        value = original(*args, **kwargs)
        save(folder / f"producer_{permit['label']}.json", value)
        active.service_event('product_service_returned', producer=pin(folder / f"producer_{permit['label']}.json"))
        return value

    service._observe_active_observation = observed
    active_observation_images.rasterize_attention = guarded_raster
    try:
        with registration_scope(live_spatial_mcp, folder / 'ATTEMPTS.jsonl', specification['planned']) as active:
            live_spatial_mcp.run_stdio_mcp_server(service)
    finally:
        active_observation_images.rasterize_attention = rasterize
        save(folder / 'SERVICE_CLOSE.json', {'captures': captures, 'product_service_calls': product_calls,
             'software_rasters': raster_calls, 'product_source_sha256': identity['source_sha256'],
             'actual_Blender': 0, 'actual_models': 0, 'closed_ns': time.perf_counter_ns()})


def run(root):
    folder = root / 'preflight/registration'
    spec = prepare(root, folder)
    channel = folder / 'STDIN.bin'
    channel.write_bytes(b''.join(Path(s['tx']['path']).read_bytes() for s in spec['sequence']))
    args = [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__)), str(root), 'worker']
    before = time.perf_counter_ns()
    with channel.open('rb') as stdin, (folder / 'STDOUT.bin').open('xb') as stdout, (folder / 'STDERR.bin').open('xb') as stderr:
        process = subprocess.run(args, stdin=stdin, stdout=stdout, stderr=stderr,
                                 cwd=folder, env=old.prior.process_env(),
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=50)
    ended = time.perf_counter_ns()
    process.check_returncode()
    output = (folder / 'STDOUT.bin').read_bytes().splitlines(keepends=True)
    need(len(output) == len(spec['sequence']), 'registration_stdout_terminal_count')
    events = [json.loads(line) for line in (folder / 'ATTEMPTS.jsonl').read_bytes().splitlines()]
    attempts = [row for row in events if row['phase'] == 'attempt_registered']
    baseline = read(folder / 'SERVICE_CLOSE.json')
    expected = ['K', 'T']
    for phase in ('product_dispatch_started', 'product_service_started', 'product_service_returned', 'product_dispatch_returned'):
        need([e['label'] for e in events if e['phase'] == phase] == expected, 'wrong_recorded_product_progress/' + phase)
    need(baseline['captures'] == baseline['product_service_calls'] == expected
         and all(baseline['software_rasters'].count(label) <= 2 for label in expected)
         and baseline['actual_Blender'] == baseline['actual_models'] == 0 and len(attempts) == 9,
         'unexpected_registration_work')
    checked = []
    for number, (row, out) in enumerate(zip(spec['sequence'], output, strict=True), 1):
        tx = read(row['tx']['path'])
        reply = json.loads(out)
        need(reply['id'] == tx['id'] and reply['jsonrpc'] == '2.0', 'registration_outer_binding')
        if number > 2:
            attempt = attempts[number - 3]
            need(attempt['request_id'] == tx['id'] and attempt['request_sha256'] == fingerprint(tx)
                 and attempt['reason'] == row['expected_rejection'], 'registration_attempt_not_bound')
            result = reply['result']
            need(bool(result.get('isError')) == bool(attempt['reason']), 'registration_reply_wrong_outcome')
            related = [event for event in events if event.get('attempt') == attempt['attempt']]
            if attempt['reason']:
                need(len(related) == 1 and json.loads(result['content'][0]['text'])['error'] == attempt['reason'],
                     'rejected_control_had_product_side_effect')
            else:
                returned = related[-1]
                need(returned['phase'] == 'product_dispatch_returned' and not returned['product_is_error']
                     and returned['product_reply_sha256'] == fingerprint(reply)
                     and any(block['type'] == 'image' for block in result['content']), 'completed_reply_not_delivered')
        dest = folder / f"{number:02d}-{row['name']}.rx"
        dest.write_bytes(out)
        checked.append({**row, 'rx': pin(dest)})
    save(folder / 'RESULT.json', {'passed': True, 'old_formal_product_dispatch': '0/2',
         'registered_attempts': len(attempts), 'product_dispatch_started': 2, 'product_completed_and_delivered': 2,
         'rejected_controls_without_product_dispatch': 7, 'measured_software_rasters': baseline['software_rasters'],
         'formal_Blender': 0, 'models': 0, 'stdio_exit': process.returncode, 'wall_ns': ended - before,
         'freeze': pin(folder / 'REGISTRATION_FREEZE.json'), 'attempts': pin(folder / 'ATTEMPTS.jsonl'),
         'identity': pin(folder / 'SERVICE_CLOSE.json'), 'wires': checked})
    print('Registration 9 attempts, 2 completed product requests, 7 zero-dispatch controls.')


if __name__ == '__main__':
    batch = Path(sys.argv[1]).resolve(strict=True)
    if len(sys.argv) == 3 and sys.argv[2] == 'worker':
        serve(batch, batch / 'preflight/registration')
    else:
        run(batch)
