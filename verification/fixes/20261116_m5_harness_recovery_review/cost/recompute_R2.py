"""Independent fixed-artifact identity, timing, budget and closure checks."""
from pathlib import Path
import ast
import base64
import hashlib
import io
import json
import subprocess
import zipfile
import zlib

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = ROOT / 'verification/m5_harness_recovery_001'
RUN = Path('D:/he_m5_harness_recovery_001')
OUT = Path(__file__).resolve().parent
FINAL = 'c041d4f038f72215aa4107a26fcbfd36aa53dd31'
FROZEN = '046e1772959af7c3c297ac2678ac3845ae27abc5'
CHECKS = 0


def check(value, label):
    global CHECKS
    CHECKS += 1
    if not value:
        raise AssertionError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def rows(path):
    return [json.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True).stdout


def blobs(specs):
    raw = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT,
                         input=('\n'.join(specs) + '\n').encode(), capture_output=True, check=True).stdout
    result = []
    offset = 0
    for spec in specs:
        end = raw.index(b'\n', offset)
        header = raw[offset:end].split()
        check(len(header) == 3 and header[1] == b'blob', 'git blob header ' + spec)
        length = int(header[2])
        begin = end + 1
        data = raw[begin:begin+length]
        check(len(data) == length and raw[begin+length:begin+length+1] == b'\n', 'git blob length')
        result.append(data)
        offset = begin + length + 1
    check(offset == len(raw), 'git batch exhausted')
    return result


check(git('rev-parse', 'HEAD').decode().strip() == FINAL, 'fixed final checkout')
check(git('status', '--porcelain') == b'', 'author tracked clean')
manifest = load(NS / 'CONTENT_MANIFEST.json')
members = manifest['files']
check(len(members) == 567 == manifest['file_count'], '567 manifest members')
paths = [row['path'] for row in members]
manifest_path = 'verification/m5_harness_recovery_001/CONTENT_MANIFEST.json'
changed = git('diff', '--name-only', manifest['baseline_git'], FINAL).decode().splitlines()
check(set(paths + [manifest_path]) == set(changed) and len(changed) == 568, '568 Git changed paths closed')
check(all(p.startswith('verification/m5_harness_recovery_001/') for p in changed), 'only own namespace')
check(git('diff', manifest['baseline_git'], FINAL, '--', 'human_eye_plugin') == b'', 'product diff empty')
for row, data in zip(members, blobs([FINAL + ':' + path for path in paths])):
    source = (ROOT / row['path']).read_bytes()
    check(source == data, 'manifest Git exact ' + row['path'])
    check(len(data) == row['bytes'] and sha(data) == row['sha256'], 'manifest SHA/length')
check((ROOT / manifest_path).read_bytes() == blobs([FINAL + ':' + manifest_path])[0], 'manifest itself Git exact')

archive = load(NS / 'RUNTIME_ARCHIVE.json')
check(len(archive['files']) == archive['file_count'] == 384, '384 runtime archive files')
total = 0
for row in archive['files']:
    source = Path(row['original_path'])
    check(source.resolve().is_relative_to(RUN.resolve()), 'runtime source boundary')
    original = source.read_bytes()
    copied = (NS / row['archive_path']).read_bytes()
    check(original == copied, 'runtime archive exact')
    check(len(original) == row['bytes'] and sha(original) == row['sha256'], 'runtime SHA/length')
    total += len(original)
check(total == archive['bytes'] == 4645843, 'runtime archive bytes')

freeze = load(NS / 'FROZEN.json')
check(len(freeze['files']) == 68, '68 frozen inputs')
local_freeze = []
for row in freeze['files']:
    path = Path(row['path'])
    data = path.read_bytes()
    check(len(data) == row['bytes'] and sha(data) == row['sha256'], 'frozen input exact')
    if path.resolve().is_relative_to(NS.resolve()):
        local_freeze.append((path, data))
for (path, data), old in zip(local_freeze, blobs([FROZEN + ':' + p.relative_to(ROOT).as_posix() for p, _ in local_freeze])):
    check(data == old, 'preexecution frozen Git exact ' + path.name)
baseline = load(NS / 'BASELINE.json')
for row in baseline['protected_direct_seals']:
    data = Path(row['path']).read_bytes()
    check(sha(data) == row['sha256'] and len(data) == row['bytes'], 'direct old seal')
check(len(baseline['protected_direct_seals']) == 5, 'five direct historical seals')
check(sha(Path(baseline['candidate']['path']).read_bytes()) == baseline['candidate']['sha256'], 'old candidate unchanged')
check(sha(Path(baseline['asset']['path']).read_bytes()) == baseline['asset']['sha256'], 'asset unchanged')

wheel_paths = {
    'A': ROOT / 'verification/m4_target_acquisition_002/build_B/human_eye_spatial_plugin-9.7.2+m4.target.acquisition.002.r1-py3-none-any.whl',
    'B': ROOT / 'verification/m5_observe_measure_001/build_final/human_eye_spatial_plugin-9.7.2+m5.observe.measure.001.r1-py3-none-any.whl',
}
sources = {}
install_roots = {}
for label in ('A', 'B'):
    binding = load(NS / (label + '_RUN_BINDING.json'))
    files = binding['source_manifest']
    check(len(files) == 141, '141 source files ' + label)
    install_roots[label] = Path(binding['install_root'])
    identity = {'base_version': binding['base_version'], 'implementation_revision': binding['implementation_revision'], 'files': files}
    computed = sha(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check(computed == binding['source_sha256'], 'source aggregate ' + label)
    sources[label] = computed
    wheel = wheel_paths[label].read_bytes()
    check(sha(wheel) == binding['wheel_sha256'], 'wheel identity ' + label)
    old_files = blobs([binding['preparation_git'] + ':' + row['path'] for row in files])
    with zipfile.ZipFile(io.BytesIO(wheel)) as z:
        for row, old in zip(files, old_files):
            installed = (install_roots[label] / row['path']).read_bytes()
            check(sha(installed) == row['sha256'], 'installed source SHA')
            check(installed == old == z.read(row['path']), 'source install Git wheel exact')

sessions = []
inner_count = outer_count = embedded_count = 0
for label in ('A', 'B'):
    folder = RUN / 'sessions' / label
    result = load(folder / 'SLOT_RESULT.json')
    pub = load(folder / 'SLOT_PUBLICATION.json')
    close = load(folder / 'RUNTIME_CLOSE.json')
    actor = load(folder / 'ACTOR_CLOSE.json')
    config = load(folder / 'PRODUCT_CONFIG.json')
    clocks = result['clocks']
    check(result['group'] == label and result['status'] == 'completed' and result['errors'] == [], 'successful slot')
    check(result['model_consumers'] == 0 and result['paid_API_calls'] == 0, 'zero models/API')
    check(result['consumer_record'] is None and result['consumer_path'] is None, 'no consumer process data')
    check(clocks['owned_deadline_ns'] == clocks['worker_deadline_ns'] == clocks['slot_started_ns'] + 600_000_000_000, '600 second root deadline')
    complete = pub['slot_result_published_ns'] - pub['slot_started_ns']
    check(complete == pub['complete_slot_ns'] and pub['slot_started_ns'] == clocks['slot_started_ns'], 'root complete slot clock')
    check(clocks['cleanup_closed_ns'] <= pub['slot_result_published_ns'] <= clocks['owned_deadline_ns'], 'closure publication inside deadline')
    check(sha((folder / 'SLOT_RESULT.json').read_bytes()) == pub['result_sha256'], 'published result identity')
    check(config['request_budget_s'] == config['blender']['timeout_s'] == 30, '30 second product/host budget')
    check(config['expected_identity']['source_sha256'] == sources[label], 'configured product source')
    init = load(folder / 'INITIALIZE.json')['result']['_meta']['human_eye']
    check(init['source_sha256'] == sources[label] and init['source_kind'] == 'installed_distribution', 'actual MCP installed identity')
    tools = load(folder / 'owner/TOOLS.json')
    check(tools['calls'] == len(tools['tools']) == 4, 'four outer tools')
    outer_count += tools['calls']
    reqs = rows(folder / 'PUBLIC_REQUESTS.jsonl')
    check(len(reqs) == 5 and [r['internal_public_call_index'] for r in reqs] == [1, 2, 3, 4, 5], 'five actual public calls')
    check([r['producer_archive_index'] for r in reqs] == [1, None, 2, 3, 4], 'independent archive indices')
    check([r['response']['result']['isError'] for r in reqs] == [False, True, False, False, False], 'original error statuses')
    for row in reqs:
        inner_count += 1
        tx = Path(row['actual_TX_path']).read_bytes()
        rx = Path(row['actual_RX_path']).read_bytes()
        check(sha(tx) == row['actual_TX_sha256'] and sha(rx) == row['actual_RX_sha256'], 'original RPC wire hashes')
        check(json.loads(tx) == row['request'] and json.loads(rx) == row['response'], 'original RPC bodies')
        check(clocks['slot_started_ns'] <= row['started_ns'] <= row['closed_ns'] <= clocks['business_closed_ns'], 'public call inside root business window')
        check(row['closed_ns'] - row['started_ns'] == row['complete_client_call_ns'], 'complete call clock')
        check(row['receipt']['error'] is None, 'stdio no failure')
    for name in ('mcp', 'native'):
        proof = load(folder / ('ROOT_' + ('MCP' if name == 'mcp' else 'NATIVE') + '_PROOF.json'))
        held = result['cleanup'][name]
        check(proof['confirmed'] and proof['before_stdin'], 'owned ancestry retained')
        check(held['confirmed'] and held['exited'] and held['exit_code'] == 0 and held['handle_closed'] and not held['forced_by_root'], 'owned process exit')
    check(result['cleanup']['actor_exit_code'] == 0 and result['cleanup']['actor_process_handle_closed'], 'actor exit and handle')
    stdio = close['MCP_stdio_close']
    check(stdio['confirmed'] and stdio['exit_code'] == 0 and not stdio['forced_kill'], 'MCP stdio close')
    check(stdio['reader_stopped'] and stdio['pipes_closed'] and stdio['process_handle_closed'] and stdio['errors'] == [], 'MCP pipe reader handle closure')
    check(close['MCP_retained_exit']['exit_code'] == 0 and close['MCP_retained_exit']['handle_closed'], 'MCP actual retained exit')
    native = close['Blender_close']
    check(native['exit_code'] == 0 and native['process_reaped'] and native['error'] is None, 'Blender wait/reap')
    check(native['source_file_unchanged'] and native['protected_files_unchanged'], 'Blender protected state')
    state = close['Blender_status']['closed']
    check(state['initial_geometry_fingerprint'] == state['final_geometry_fingerprint'] and not state['poisoned'], 'initial final geometry unchanged')
    check(actor['bridge']['confirmed'] and actor['bridge']['errors'] == [] and actor['errors'] == [], 'Owner/listener close')
    # The executed native script is bound through both original transport and worker event.
    script = folder / 'native/call_2/SCRIPT.py'
    text = script.read_text(encoding='utf-8')
    request = load(folder / 'native/WIRE/002/REQUEST.bin')
    check(request['params']['code'] == text, 'native original transport code exact')
    events = rows(folder / 'native/WORKER_EVENTS.jsonl')
    event = next(e for e in events if e['sequence'] == 2)
    check(event['script_sha256'] == sha(text.encode('utf-8')) and event['status'] == 'completed' and event['script_error'] is None, 'actual native script completed')
    expected_sources = {(install_roots[label] / p).read_bytes() for p in ('human_eye_plugin/blender_host.py', 'human_eye_plugin/scene_residency.py')}
    extracted = []
    for node in ast.walk(ast.parse(text)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'b64decode' and node.args and isinstance(node.args[0], ast.Constant)):
            continue
        data = base64.b64decode(node.args[0].value)
        try:
            data = zlib.decompress(data)
        except zlib.error:
            pass
        extracted.append(data)
    check(len(extracted) == 2 and set(extracted) == expected_sources, 'actual two compiled host sources match installation')
    embedded_count += len(extracted)
    sessions.append({'label': label, 'complete_ns': complete, 'complete_ms': complete / 1e6,
                     'public_calls': len(reqs), 'outer_tools': tools['calls'], 'source_sha256': sources[label]})

check(outer_count == 8 and inner_count == 10 and embedded_count == 4, 'total actual operations')
claim_paths = sorted((RUN / 'budget/claims').glob('*.json'))
starts = rasters = consumer_claims = business_admissions = 0
pending_operation_claims = 0
for path in claim_paths:
    claim = load(path)
    if claim['kind'] == 'business_tool':
        business_admissions += 1
        continue
    pending_operation_claims += 1
    settle = load(RUN / 'budget/settlements' / (claim['token'] + '.json'))
    check(settle['token'] == claim['token'] and settle['claim_sha256'] == sha(path.read_bytes()), 'settled budget binding')
    if claim['kind'] == 'Blender_start':
        starts += 1
        check(settle['spawn_status'] == 'spawned' and settle['outcome'] == 'completed' and isinstance(settle['pid'], int), 'actual successful owned start')
    elif claim['kind'] == 'raster_attempt':
        rasters += settle['actual_attempts']
        evidence = settle['evidence']
        original = Path(evidence['audit_path']).read_bytes()[evidence['tail_start_bytes']:]
        check(len(original) == evidence['tail_bytes'] and sha(original) == evidence['tail_sha256'], 'actual raster audit tail')
        event = [json.loads(s) for s in original.splitlines() if s.strip()]
        check(sum(e.get('event') == 'active_observation_render_attempt' for e in event) == settle['actual_attempts'], 'actual producer raster event')
    elif claim['kind'] == 'consumer_task':
        consumer_claims += 1
    else:
        check(False, 'unexpected operation kind ' + claim['kind'])
check(starts == 2 and rasters == 2 and consumer_claims == 0, '2 owned 2 rasters 0 consumers')
check(business_admissions == 8, 'eight immediate business admissions')
check(len(list((RUN / 'budget/settlements').glob('*.json'))) == pending_operation_claims, 'all operation claims settled')
ledger = load(NS / 'QUALIFICATION_LEDGER.json')
check(ledger['active_work_ns'] is None and ledger['interruption_and_idle_ns'] is None, 'active/idle unmeasured')
check(ledger['registered_wall_elapsed_ns'] == ledger['audit_closed_ns'] - ledger['registered_started_ns'], 'registered wall accounting')
decision = load(NS / 'DECISION.json')
check(decision['accepted_harness_recovery'] is True and decision['product_or_model_benefit_claim'] is False, 'scope-limited recovery acceptance')
registration_to_decision = decision['closed_ns'] - baseline['started_ns']
check(registration_to_decision > 10_000_000_000_000, 'wall span includes prolonged interruption')

OUT.mkdir(parents=True, exist_ok=True)
result = {'status': 'passed_checked_scope', 'checks': CHECKS, 'fixed_git': FINAL,
          'manifest_members': len(members), 'git_paths': len(changed), 'archive_files': archive['file_count'],
          'archive_bytes': total, 'frozen_inputs': len(freeze['files']), 'source_files_per_version': 141,
          'actual_host_sources': embedded_count, 'sessions': sessions,
          'budget': {'owned': starts, 'rasters': rasters, 'model_consumers': consumer_claims,
                     'business_admissions': business_admissions, 'pending_operations': 0},
          'registration_to_decision_wall_ns': registration_to_decision,
          'registered_to_seal_wall_ns': ledger['registered_wall_elapsed_ns'],
          'performance_comparison': 'not_performed_recovery_sequence_only',
          'new_Blender': 0, 'new_raster': 0, 'new_CLI_models': 0, 'new_API_calls': 0}
(OUT / 'RESULT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
