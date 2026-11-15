"""Independent read-only identity and cost reconstruction from sealed evidence."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import statistics
import subprocess
import zipfile

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = ROOT / 'verification/m4_target_acquisition_002'
RUN = Path('D:/he_m4_target_002')
OUT = Path(__file__).resolve().parent
FINAL = '71a505135ecf202c0e8572fb01bbe21c410342e2'
BASE = '4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6'
checks = 0


def check(condition, label):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


check(git('rev-parse', 'HEAD').decode().strip() == FINAL, 'fixed final commit')
check(not git('status', '--porcelain').strip(), 'author clean')
manifest = load(NS / 'CONTENT_MANIFEST.json')
members = manifest['files']
check(len(members) == 1949 == manifest['file_count'], 'manifest denominator')
paths = [row['path'] for row in members]
paths.append('verification/m4_target_acquisition_002/CONTENT_MANIFEST.json')
changed = git('diff', '--name-only', BASE, FINAL).decode().splitlines()
check(set(paths) == set(changed), 'manifest closes exact git changed paths')
queries = ''.join(FINAL + ':' + name + '\n' for name in paths).encode()
batch = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '--batch'],
                       input=queries, stdout=subprocess.PIPE, check=True).stdout
cursor = 0
for i, name in enumerate(paths):
    end = batch.index(b'\n', cursor)
    header = batch[cursor:end].split()
    check(header[1] == b'blob', 'git object type ' + name)
    size = int(header[2])
    blob = batch[end + 1:end + 1 + size]
    cursor = end + 2 + size
    actual = (ROOT / name).read_bytes()
    check(actual == blob, 'git/worktree exact ' + name)
    if i < len(members):
        check(len(actual) == members[i]['bytes'] and sha(actual) == members[i]['sha256'],
              'manifest bytes ' + name)
check(cursor == len(batch), 'git batch fully consumed')
archive = load(NS / 'RUNTIME_ARCHIVE.json')
for row in archive['files']:
    original = Path(row['original_path']).read_bytes()
    copied = (NS / row['archive_path']).read_bytes()
    check(original == copied and sha(original) == row['sha256'] and len(original) == row['bytes'],
          'runtime archive ' + row['relative_path'])
check(len(archive['files']) == 1822, 'runtime archive denominator')
prereg = load(NS / 'PREREGISTRATION.json')
gate = load(NS / 'FORMAL_GATE.json')
once = load(RUN / 'FORMAL_ONCE.json')
check(sha((NS / 'PREREGISTRATION.json').read_bytes()) == gate['preregistration_sha256'] == once['preregistration_sha256'], 'prereg identity')
check(sha((NS / 'FORMAL_GATE.json').read_bytes()) == once['qualification_sha256'], 'formal gate identity')
check(sha(Path('D:/hefe/docs/M4_TARGET_ACQUISITION_002_PLAN.md').read_bytes()) == prereg['plan_sha256'], 'root fixed plan')
check(sha(Path('D:/hefe/verification/fixes/20261115_m4_selective_002_plan/FROZEN_GEOMETRY.json').read_bytes()) == prereg['geometry_sha256'], 'root frozen input')
check(prereg['formal_schedule'] == once['formal_schedule'] and len(once['formal_schedule']) == 12, 'schedule same')
check(once['retries'] == 0 and once['replacement_samples'] == 0, 'formal no replacements')
for row in prereg['assets']:
    check(sha(Path(row['asset']).read_bytes()) == row['asset_sha256'], 'asset original identity ' + row['name'])

bindings = {'A': load(NS / 'A_RUN_BINDING.json'), 'B': load(NS / 'build_B/RUN_BINDING.json')}
wheel_paths = {
    'A': next((ROOT / 'verification/m4_target_camera_reliability_001/build').glob('*.whl')),
    'B': next((NS / 'build_B').glob('*.whl')),
}
sources = {}
for variant, binding in bindings.items():
    entries = binding['source_manifest']
    check(len(entries) == 141, 'source denominator ' + variant)
    payload = dict(base_version=binding['base_version'], implementation_revision=binding['implementation_revision'], files=entries)
    identity = sha(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check(identity == binding['source_sha256'] == once[variant + '_source_sha256'], 'source aggregate ' + variant)
    wheel = wheel_paths[variant]
    check(sha(wheel.read_bytes()) == binding['wheel_sha256'], 'wheel identity ' + variant)
    commit = binding['preparation_git'] if variant == 'A' else 'c309d7e4302518cd5f7d1c3966e7c7fa338ea128'
    with zipfile.ZipFile(wheel) as packed:
        for entry in entries:
            local = (Path(binding['install_root']) / entry['path']).read_bytes()
            check(sha(local) == entry['sha256'] and local == packed.read(entry['path']), 'wheel/install ' + variant + '/' + entry['path'])
            check(local == git('show', commit + ':' + entry['path']), 'source git ' + variant + '/' + entry['path'])
    sources[variant] = identity

records = []
clock_sampling_order = []
last_end = once['started_ns']
for slot in once['formal_schedule']:
    label, variant = slot['label'], slot['variant']
    folder = RUN / 'formal' / label
    result = load(folder / 'RESULT.json')
    check(result['label'] == label and result['variant'] == variant, 'slot identity ' + label)
    check(result['source_sha256'] == sources[variant], 'slot source ' + label)
    check(sha(Path(result['binding_file']).read_bytes()) == result['binding_sha256'] == once[variant + '_binding_sha256'], 'binding identity ' + label)
    check(result['started_ns'] >= last_end, 'fresh serial chronology ' + label)
    last_end = result['postrun_closed_ns']
    check(result['passed'] and result['errors'] == [] and result['model_calls'] == 0, 'slot completion ' + label)
    check(result['complete_session_ns'] == result['session_closed_ns'] - result['started_ns'] > 0, 'session duration ' + label)
    check(result['session_closed_ns'] <= result['postrun_closed_ns'] <= result['original_lifecycle_deadline_ns'], 'original deadline ' + label)
    check(result['stdio_close']['confirmed'] and result['stdio_close']['exit_code'] == 0 and not result['stdio_close']['forced_kill'], 'MCP closure ' + label)
    check(result['native_close']['process_reaped'] and result['native_close']['exit_code'] == 0, 'Blender closure ' + label)
    check(result['native_final']['source_file_unchanged'] and result['native_final']['protected_files_unchanged'], 'protected state ' + label)
    ios = [json.loads(line) for line in (folder / 'io_audit/MCP_IO.jsonl').read_text().splitlines()]
    ids = ['target_observation', 'after_active_ping', 'source_readback', 'after_readback_ping']
    check([r['id'] for r in result['requests']] == ids, 'four business calls ' + label)
    call_costs = []
    for index, req in enumerate(result['requests']):
        request = load(folder / ('REQUEST_' + str(index + 1).zfill(2) + '.json'))
        check(request == once['requests_per_input'][slot['input']][index], 'actual fixed request ' + label)
        io = next(row for row in ios if row['id'] == req['id'])
        receipt_dir = folder / 'stdio' / ('rpc_' + str(io['sequence']).zfill(2))
        receipt = load(receipt_dir / 'RECEIPT.json')
        rx = (receipt_dir / 'RX.bin').read_bytes()
        tx = (receipt_dir / 'TX.bin').read_bytes()
        check(receipt['RX_bytes'] == len(rx) == req['raw_RX_bytes'] and receipt['RX_sha256'] == sha(rx), 'RX raw bytes ' + label)
        check(receipt['TX_bytes'] == len(tx) and json.loads(tx) == request, 'TX raw bytes ' + label)
        check(receipt['error'] is None and json.loads(rx)['id'] == req['id'], 'actual response ' + label)
        server = io['reply_completed_ns'] - io['request_received_ns']
        transport = receipt['received_complete_ns'] - receipt['stdin_flushed_ns']
        outer = req['client_call_completed_ns'] - req['client_call_started_ns']
        check(server == io['request_to_reply_ns'] == req['server_request_to_reply_ns'] > 0, 'server clock ' + label)
        check(transport == req['client_flush_to_received_ns'] > 0, 'transport clock ' + label)
        check(outer == req['client_outer_including_recording_ns'] > 0, 'outer clock ' + label)
        check(req['client_call_started_ns'] <= receipt['started_ns'] <= receipt['stdin_flushed_ns'] <= receipt['received_complete_ns'] <= receipt['consumer_json_decoded_ns'] <= receipt['closed_ns'] <= req['client_call_completed_ns'], 'client clock containment ' + label)
        check(req['client_call_started_ns'] <= io['request_received_ns'] <= io['reply_completed_ns'] <= req['client_call_completed_ns'], 'server within complete call ' + label)
        if io['reply_completed_ns'] > receipt['received_complete_ns']:
            clock_sampling_order.append(dict(label=label, request=req['id'],
                server_marker_after_client_receive_ns=io['reply_completed_ns'] - receipt['received_complete_ns']))
        call_costs.append(dict(server=server, transport=transport, outer=outer, raw_bytes=len(rx)))
    audit = [json.loads(line) for line in (folder / 'audit.jsonl').read_text().splitlines()]
    render = [e for e in audit if e.get('event') == 'active_observation_render_attempt']
    check(len(render) == len(result['producer_frames']), 'actual renders ' + label)
    check(all(e['identity_check']['actual']['source_sha256'] == sources[variant] for e in render), 'runtime render identity ' + label)
    records.append(dict(label=label, input=slot['input'], variant=variant, pair=slot['pair'], started_ns=result['started_ns'], session_ns=result['complete_session_ns'], calls=call_costs, renders=len(render), postrun_validation_ns=result['postrun_validation_ns']))

ratios = {}
for scene in ('main', 'target_only'):
    pairs = []
    for pair in (1, 2, 3):
        a = next(row for row in records if row['input'] == scene and row['pair'] == pair and row['variant'] == 'A')
        b = next(row for row in records if row['input'] == scene and row['pair'] == pair and row['variant'] == 'B')
        pairs.append(dict(pair=pair, server=Fraction(b['calls'][0]['server'], a['calls'][0]['server']),
                          transport=Fraction(b['calls'][0]['transport'], a['calls'][0]['transport']),
                          outer=Fraction(b['calls'][0]['outer'], a['calls'][0]['outer']), session=Fraction(b['session_ns'], a['session_ns'])))
    medians = {key: statistics.median([p[key] for p in pairs]) for key in ('server', 'transport', 'outer', 'session')}
    ratios[scene] = dict(pairs=[{k: str(v) if isinstance(v, Fraction) else v for k,v in p.items()} for p in pairs], median_exact={k:str(v) for k,v in medians.items()}, median={k:float(v) for k,v in medians.items()}, faster=sum(p['server'] < 1 for p in pairs))
    published = load(NS / 'DECISION.json')['gates'][scene]
    check(medians['server'] == Fraction(published['business_ratio_median_exact']), 'published median server ' + scene)
    check(medians['session'] == Fraction(published['session_ratio_median_exact']), 'published median session ' + scene)
check(ratios['main']['median']['server'] <= .9 and ratios['main']['faster'] >= 2 and ratios['main']['median']['session'] <= 1, 'main frozen timing gate')
check(ratios['target_only']['median']['server'] <= 1.05, 'control frozen timing gate')

claims = sorted((RUN / 'budget/claims').glob('*.json'))
counts = dict(starts=0, raster_requests=0, formal_rasters=0, qualification_rasters=0, pending=0)
for path in claims:
    claim = load(path)
    settle_path = RUN / 'budget/settlements' / (claim['token'] + '.json')
    check(settle_path.exists(), 'claim settled ' + claim['token'])
    settlement = load(settle_path)
    check(settlement['claim_sha256'] == sha(path.read_bytes()), 'settlement binding ' + claim['token'])
    if claim['kind'] == 'Blender_start':
        counts['starts'] += 1
        check(settlement.get('pid') and settlement.get('spawn_status') != 'unknown', 'confirmed owned start')
    else:
        counts['raster_requests'] += 1
        actual = settlement['actual_attempts']
        check(type(actual) is int and 0 <= actual <= claim['reserved_upper_bound'], 'raster accounting')
        counts[claim['phase'] + '_rasters'] += actual
check(counts['starts'] == 19 and counts['raster_requests'] == 20 and counts['formal_rasters'] == 18 and counts['qualification_rasters'] == 10, 'ledger totals')
check(len([p for p in (RUN / 'formal').iterdir() if p.is_dir()]) == 12 and len(records) == 12, 'no extra formal directories')
summary = dict(status='passed_checked_scope', independent_checks=checks, sources=sources,
    git_manifest_files=1949, runtime_original_archive_pairs=1822, source_files_per_variant=141,
    formal_slots=12, per_input_pairs=3, requests=48, actual_formal_frames=sum(r['renders'] for r in records),
    ratios=ratios, ledger=counts, records=records, clock_sampling_order=clock_sampling_order,
    limits=['Saved evidence reconstruction, no fresh Blender timing', 'Background interference unquantified',
            'Tokens, paid cost and consumer task benefit not measured', 'postrun saved-data validation recorded separately from session'])
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'RESULTS.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps({key:summary[key] for key in ('status','independent_checks','ratios','ledger')}, indent=2))
