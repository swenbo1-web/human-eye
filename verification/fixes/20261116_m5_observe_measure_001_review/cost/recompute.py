"""Independent saved-evidence identity and engineering-cost reconstruction."""
import hashlib
import ast
import base64
import json
from pathlib import Path
import statistics
import subprocess
import zipfile
import zlib
from fractions import Fraction

REPO = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = REPO / 'verification/m5_observe_measure_001'
RUN = Path('D:/he_m5_observe_measure_001')
OUT = Path(__file__).resolve().parent
HEAD = '14c8c6b8206dcaecc373bc9aa895cda1d622eee3'
BASE = 'bc177d231329dac630b4d02a161076b2b9fb50e3'
FROZEN = '31124af898a35dee84504d3101003629bd185ec1'
checks = 0


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(condition, label):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(label)


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], check=True, capture_output=True).stdout


def blobs(refs):
    unique = list(dict.fromkeys(refs))
    result = subprocess.run(['git', '-C', str(REPO), 'cat-file', '--batch'],
                            input=('\n'.join(unique) + '\n').encode(), capture_output=True, check=True).stdout
    values = {}
    cursor = 0
    for ref in unique:
        end = result.index(b'\n', cursor)
        header = result[cursor:end].split()
        check(len(header) == 3 and header[1] == b'blob', 'Git blob exists ' + ref)
        length = int(header[2])
        start = end + 1
        values[ref] = result[start:start + length]
        check(result[start + length:start + length + 1] == b'\n', 'Git framing ' + ref)
        cursor = start + length + 1
    check(cursor == len(result), 'all Git batch output consumed')
    return values


check(git('rev-parse', 'HEAD').decode().strip() == HEAD, 'author final HEAD')
check(not git('status', '--porcelain'), 'author worktree clean')
manifest = read(NS / 'CONTENT_MANIFEST.json')
archive = read(NS / 'RUNTIME_ARCHIVE.json')
freeze = read(NS / 'FORMAL_FROZEN.json')
bindings = {
    'A': read(NS / 'A_RUN_BINDING.json'),
    'initial': read(NS / 'build_initial/RUN_BINDING.json'),
    'B': read(NS / 'build_final/RUN_BINDING.json'),
}
manifest_rel = (NS / 'CONTENT_MANIFEST.json').relative_to(REPO).as_posix()
paths = [r['path'] for r in manifest['files']]
diff_paths = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
check(len(paths) == 1563 == manifest['file_count'], '1563 manifest members')
check(len(diff_paths) == 1564 and set(diff_paths) == set(paths + [manifest_rel]), 'Git change paths close exactly')
refs = [HEAD + ':' + p for p in paths + [manifest_rel]]
refs.extend(binding['preparation_git'] + ':' + r['path']
            for binding in bindings.values() for r in binding['source_manifest'])
refs.extend(FROZEN + ':' + Path(r['path']).relative_to(REPO).as_posix() for r in freeze['files'])
data = blobs(refs)
for row in manifest['files']:
    current = (REPO / row['path']).read_bytes()
    check(len(current) == row['bytes'] and digest(current) == row['sha256'], 'sealed member ' + row['path'])
    check(current == data[HEAD + ':' + row['path']], 'sealed Git bytes ' + row['path'])
check((NS / 'CONTENT_MANIFEST.json').read_bytes() == data[HEAD + ':' + manifest_rel], 'manifest Git byte equality')
for row in archive['files']:
    original = Path(row['original_path']).read_bytes()
    saved = (NS / row['archive_path']).read_bytes()
    check(original == saved and len(saved) == row['bytes'] and digest(saved) == row['sha256'], 'runtime original/archive ' + row['relative_path'])
check(len(archive['files']) == 1288 and sum(r['bytes'] for r in archive['files']) == 30355846, 'runtime archive denominator')
check(len(freeze['files']) == 205, '205 formal pins')
for row in freeze['files']:
    raw = Path(row['path']).read_bytes()
    rel = Path(row['path']).relative_to(REPO).as_posix()
    check(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'formal pin identity ' + rel)
    check(raw == data[FROZEN + ':' + rel], 'formal pin Git snapshot ' + rel)
for path, expected in read(NS / 'BASELINE.json')['protected_old_pins'].items():
    check(digest(Path(path).read_bytes()) == expected, 'protected historical pin ' + path)

sources = {}
for name, binding in bindings.items():
    if name == 'A':
        wheel = next((REPO / 'verification/m4_target_acquisition_002/build_B').glob('*.whl'))
    else:
        folder = 'build_initial' if name == 'initial' else 'build_final'
        wheel = next((NS / folder).glob('*.whl'))
    check(digest(wheel.read_bytes()) == binding['wheel_sha256'], name + ' wheel digest')
    check(len(binding['source_manifest']) == 141, name + ' source file denominator')
    with zipfile.ZipFile(wheel) as zipped:
        for row in binding['source_manifest']:
            installed = (Path(binding['install_root']) / row['path']).read_bytes()
            check(digest(installed) == row['sha256'], name + ' installed source ' + row['path'])
            check(zipped.read(row['path']) == installed, name + ' wheel source bytes ' + row['path'])
            check(data[binding['preparation_git'] + ':' + row['path']] == installed, name + ' Git source bytes ' + row['path'])
    payload = {k: binding[k] for k in ('base_version', 'implementation_revision')}
    payload['files'] = binding['source_manifest']
    actual = digest(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check(actual == binding['source_sha256'], name + ' aggregate source identity')
    sources[name] = actual

once = read(RUN / 'FORMAL_ONCE.json')
order = ['A1', 'B1', 'B2', 'A2', 'A3', 'B3', 'A_task_only', 'B_task_only']
check(once['main_order'] + once['task_only_controls'] == order, 'formal sequence frozen')
check(once['retries'] == once['replacement_samples'] == once['model_consumers'] == once['paid_API_calls'] == 0, 'no retries or consumers')
check(sorted(p.name for p in (RUN / 'formal').iterdir() if p.is_dir()) == sorted(order), 'exact formal directories')
records = []
previous_end = 0
for label in order:
    folder = RUN / 'formal' / label
    result = read(folder / 'RESULT.json')
    publication = read(folder / 'PUBLICATION.json')
    check(publication['result_sha256'] == digest((folder / 'RESULT.json').read_bytes()), 'published RESULT ' + label)
    check(publication['complete_session_ns'] == publication['result_published_ns'] - result['started_ns'] > 0, 'complete session clock ' + label)
    check(previous_end <= result['started_ns'] < result['setup_closed_ns'] < result['cleanup_started_ns'] <= result['owned_closed_ns'] <= result['saved_validation_closed_ns'] <= publication['result_published_ns'] <= result['original_owned_deadline_ns'], 'whole slot ordering/deadline ' + label)
    previous_end = publication['result_published_ns']
    check(result['original_owned_deadline_ns'] - result['started_ns'] == 600_000_000_000, 'original owned duration ' + label)
    check(result['public_request_budget_s'] == result['blender_timeout_s'] == 30, 'original public timeouts ' + label)
    check(result['errors'] == [] and result['passed_before_publication'] and publication['passed_transport_scope'], 'successful saved status ' + label)
    variant = label[0]
    check(result['source_sha256'] == sources[variant], 'actual source variant ' + label)
    check(digest(Path(result['binding_path']).read_bytes()) == result['binding_sha256'], 'actual binding file ' + label)
    initialized = read(folder / 'INITIALIZE.json')['result']['_meta']['human_eye']
    check(initialized['source_sha256'] == sources[variant] and initialized['source_kind'] == 'installed_distribution', 'actual initialize identity ' + label)
    requests = result['requests']
    expected_ids = ['measure'] if label.endswith('task_only') else (['observe', 'measure'] if variant == 'A' else ['observe_measure'])
    check([q['id'] for q in requests] == expected_ids, 'business request identities ' + label)
    io = [json.loads(line) for line in (folder / 'io_audit/MCP_IO.jsonl').read_bytes().splitlines()]
    text_bytes = raw_bytes = images = 0
    for q in requests:
        entry = next(e for e in io if e['id'] == q['id'])
        rpc = folder / 'stdio' / ('rpc_' + str(entry['sequence']).zfill(2))
        receipt = read(rpc / 'RECEIPT.json')
        tx, rx = (rpc / 'TX.bin').read_bytes(), (rpc / 'RX.bin').read_bytes()
        response = json.loads(rx)
        check(receipt['RX_sha256'] == digest(rx) and receipt['RX_bytes'] == len(rx), 'raw response receipt ' + label + q['id'])
        check(json.loads(tx) == q['request'] and response == q['response'], 'actual request/response ' + label + q['id'])
        check(q['started_ns'] <= receipt['started_ns'] <= receipt['stdin_flushed_ns'] <= receipt['received_complete_ns'] <= receipt['consumer_json_decoded_ns'] <= receipt['closed_ns'] <= q['completed_ns'], 'client interval ' + label + q['id'])
        check(q['started_ns'] <= entry['request_received_ns'] <= entry['reply_completed_ns'] <= q['completed_ns'], 'server independently contained ' + label + q['id'])
        check(q['complete_client_call_ns'] == q['completed_ns'] - q['started_ns'], 'outer call duration ' + label + q['id'])
        check(q['client_flush_to_received_ns'] == receipt['received_complete_ns'] - receipt['stdin_flushed_ns'], 'transport duration ' + label + q['id'])
        check(entry['request_to_reply_ns'] == entry['reply_completed_ns'] - entry['request_received_ns'], 'server duration ' + label + q['id'])
        blocks = response['result']['content']
        measured_text = sum(len(b['text'].encode()) for b in blocks if b['type'] == 'text')
        measured_images = sum(b['type'] == 'image' for b in blocks)
        check(measured_text == q['public_text_UTF8_bytes'] and measured_images == q['image_blocks'], 'public payload costs ' + label + q['id'])
        text_bytes += measured_text
        raw_bytes += len(rx)
        images += measured_images
    window = result['business_windows'][0]
    duration = requests[-1]['completed_ns'] - requests[0]['started_ns']
    check(window['continuous_business_ns'] == duration and window['public_business_calls'] == len(requests), 'continuous workflow clock ' + label)
    wire = read(folder / 'SAVED_WIRE.json')
    forwarded = [step for step in wire['steps'] if 'resources_forwarded' in step]
    for step in forwarded:
        check(digest(Path(step['request']).read_bytes()) == step['request_sha256'] and digest(Path(step['response']).read_bytes()) == step['response_sha256'], 'original TCP bytes ' + label)
    if not label.endswith('task_only') and variant == 'A':
        check(len(forwarded) == 2 and [forwarded[1][k] for k in ('resources_forwarded','resource_vertices_forwarded','resource_faces_forwarded')] == [0,0,0], 'A second call forwards zero arrays ' + label)
        second = result['worker_events'][1]['m2_work']
        before, after = second['before'][0]['work'], second['after'][0]['work']
        check(all(after[k] == before[k] for k in ('to_mesh','triangulations','world_transforms','world_vertices_transformed','resource_vertices_read')), 'A second call resident work reused ' + label)
    cleanup = result['cleanup']
    stdio = cleanup['stdio']
    check(stdio['confirmed'] and stdio['exit_code'] == 0 and not stdio['forced_kill'] and stdio['reader_stopped'] and stdio['process_handle_closed'] and all(stdio['pipes_closed'].values()), 'MCP real close ' + label)
    held = cleanup['MCP_retained']
    check(held['confirmed'] and held['exited'] and held['exit_code'] == 0 and held['handle_closed'], 'MCP held handle close ' + label)
    native = cleanup['native']
    check(native['process_reaped'] and native['exit_code'] == 0 and native['error'] is None and native['response']['status'] == 'closed', 'Blender close ' + label)
    records.append(dict(label=label, started_ns=result['started_ns'], business_ns=duration, complete_ns=publication['complete_session_ns'], calls=len(requests), text_bytes=text_bytes, raw_RX_bytes=raw_bytes, image_blocks=images,
                        resources_forwarded=sum(s['resources_forwarded'] for s in forwarded), vertices_forwarded=sum(s['resource_vertices_forwarded'] for s in forwarded), faces_forwarded=sum(s['resource_faces_forwarded'] for s in forwarded)))

pairs = []
for index in (1,2,3):
    a = next(r for r in records if r['label'] == 'A' + str(index))
    b = next(r for r in records if r['label'] == 'B' + str(index))
    pairs.append(dict(pair=index, business=Fraction(b['business_ns'],a['business_ns']), complete=Fraction(b['complete_ns'],a['complete_ns'])))
business = statistics.median(p['business'] for p in pairs)
complete = statistics.median(p['complete'] for p in pairs)
decision = read(NS / 'DECISION.json')
check(float(business) == decision['median_business_B_over_A'] and float(complete) == decision['median_complete_session_B_over_A'], 'published cost medians')
check(business <= Fraction(105,100) and complete <= Fraction(105,100) and sum(p['business'] < 1 for p in pairs) >= 2, 'fixed engineering gates')
totals = {variant:{key:sum(row[key] for row in records if row['label'][0] == variant and not row['label'].endswith('task_only')) for key in ('calls','text_bytes','raw_RX_bytes','image_blocks','resources_forwarded','vertices_forwarded','faces_forwarded')} for variant in ('A','B')}
check(totals['A']['calls'] == 6 and totals['B']['calls'] == 3, 'calls 6 to3')
check(totals['A']['text_bytes'] == 23136 and totals['B']['text_bytes'] == 27138, 'text totals')
check(totals['A']['raw_RX_bytes'] == 42366 and totals['B']['raw_RX_bytes'] == 46314, 'stdio totals')
claims = sorted((RUN / 'budget/claims').glob('*.json'))
starts = raster_count = unknown = 0
qualification_rasters = formal_rasters = 0
for path in claims:
    claim = read(path)
    settlement = read(RUN / 'budget/settlements' / path.name)
    check(settlement['claim_sha256'] == digest(path.read_bytes()) and settlement['token'] == claim['token'], 'budget settlement ' + path.name)
    if claim['kind'] == 'Blender_start':
        starts += 1
        unknown += settlement['spawn_status'] == 'unknown'
    else:
        attempts = settlement['actual_attempts']
        check(attempts == settlement['confirmed_attempts_lower_bound'] == len(settlement['evidence']['render_attempt_events']), 'actual settled raster ' + path.name)
        raster_count += attempts
        if claim['phase'] == 'formal':
            formal_rasters += attempts
        else:
            qualification_rasters += attempts
check((starts,raster_count,formal_rasters,qualification_rasters,unknown) == (12,13,6,7,0), 'batch owned/raster denominators')
all_sessions = list((RUN / 'formal').glob('*/RESULT.json')) + list((RUN / 'qualification').glob('*/RESULT.json')) + list((RUN / 'control').glob('*/RESULT.json'))
check(len(all_sessions) == 12, 'all 12 saved session closures')
unknown_worker_closes = 0
embedded_source_payloads = 0
for path in all_sessions:
    r = read(path)
    check(r['cleanup']['native']['process_reaped'] and r['cleanup']['native']['exit_code'] == 0, 'all session Blender exit ' + str(path.parent))
    stdio = r['cleanup']['stdio']
    held = r['cleanup']['MCP_retained']
    check(stdio['confirmed'] and stdio['exit_code'] == 0 and not stdio['forced_kill'] and stdio['reader_stopped'] and stdio['process_handle_closed'] and all(stdio['pipes_closed'].values()), 'all session MCP stdio exit ' + str(path.parent))
    check(held['confirmed'] and held['exited'] and held['exit_code'] == 0 and held['handle_closed'], 'all session MCP held exit ' + str(path.parent))
    check(r['cleanup']['native']['response']['status'] == 'closed', 'actual native close reply ' + str(path.parent))
    unknown_worker_closes += sum(e['status'] == 'unknown' for e in r['worker_events'])
    binding = read(r['binding_path'])
    known_sources = {row['sha256']: row['path'] for row in binding['source_manifest']}
    first_request = json.loads((path.parent/'native/WIRE/001/REQUEST.bin').read_bytes())
    tree = ast.parse(first_request['params']['code'])
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'decompress'):
            continue
        inner = node.args[0]
        if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == 'b64decode'):
            continue
        if not isinstance(inner.args[0], ast.Constant):
            continue
        raw = zlib.decompress(base64.b64decode(ast.literal_eval(inner.args[0]), validate=True))
        sha = digest(raw)
        check(sha in known_sources, 'actual compiled source matches manifest ' + str(path.parent))
        source_path = known_sources[sha]
        check(raw == (Path(binding['install_root'])/source_path).read_bytes(), 'actual compiled source equals install ' + source_path)
        found.append(source_path)
        embedded_source_payloads += 1
    check(sorted(found) == ['human_eye_plugin/blender_host.py','human_eye_plugin/scene_residency.py'], 'two actual embedded host modules ' + str(path.parent))
check(unknown_worker_closes == 12, 'generic worker close unknown separately preserved')
result = dict(status='passed', independent_checks=checks, fixed_git=HEAD, formal_slots=8, formal_pairs=3, formal_business_requests=sum(r['calls'] for r in records),
              sealed_members=1563, git_changed_paths=1564, runtime_archive_files=1288, formal_pins=205, sources=sources,
              records=records, pairs=[{'pair':p['pair'],'business_ratio_exact':str(p['business']),'complete_ratio_exact':str(p['complete'])} for p in pairs],
              median_business_ratio=float(business), median_complete_ratio=float(complete), totals=totals,
              ledger=dict(starts=starts,rasters=raster_count,formal_rasters=formal_rasters,qualification_rasters=qualification_rasters,unknown=unknown),
              closed_sessions=12,generic_worker_close_unknown=unknown_worker_closes,embedded_source_payloads=embedded_source_payloads,new_Blender=0,new_raster=0,new_model=0)
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ('status','independent_checks','median_business_ratio','median_complete_ratio','ledger')}))
