"""Independent stdlib-only saved-byte review; no product modules or hosts executed."""
import base64
import hashlib
import io
import json
import pathlib
import subprocess
import time
import zipfile

OUT = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-target-001/hefe')
NS = ROOT / 'verification/m4_target_acquisition_001'
FINAL = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
BASE = 'fde0e9ab21fb6eaee1750befd64ad1bebdde2961'
SOURCE_COMMIT = 'cbbbd2611031f3c2d469280a71bcd410fb47447a'
INSTALL = pathlib.Path('D:/he_m4_target_001/A/product')
SOURCE_SHA = 'b7868c46119b2f5dcb3ca426e78a2ac9bb45b51167a01d323516c7707eb81e76'
checks, inputs, details = [], {}, {}

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read(p):
    p = pathlib.Path(p)
    b = p.read_bytes()
    inputs[str(p)] = {'bytes': len(b), 'sha256': sha(b)}
    return b

def js(p):
    return json.loads(read(p))

def check(name, condition, **evidence):
    checks.append({'name': name, 'passed': bool(condition), **evidence})

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def git_blobs(commit, paths):
    specs = [commit + ':' + p for p in paths]
    data = git('cat-file', '--batch') if not specs else subprocess.check_output(
        ['git', 'cat-file', '--batch'], input=('\n'.join(specs)+'\n').encode(), cwd=ROOT)
    stream, result = io.BytesIO(data), {}
    for p in paths:
        header = stream.readline().decode().strip().split()
        assert len(header) == 3 and header[1] == 'blob', (p, header)
        result[p] = stream.read(int(header[2]))
        assert stream.read(1) == b'\n'
    assert not stream.read()
    return result

def main():
    check('fixed HEAD', git('rev-parse', 'HEAD').decode().strip() == FINAL)
    status = git('status', '--porcelain', '--untracked-files=normal').decode()
    check('worktree status clean', not status.strip(), status=status)
    changed = git('diff', '--name-only', BASE, FINAL).decode().splitlines()
    manifest = js(NS/'CONTENT_MANIFEST.json')
    listed = [f['path'] for f in manifest['files']]
    check('diff346 equals manifest345 plus self', len(changed) == 346 and
          set(changed) == set(listed) | {'verification/m4_target_acquisition_001/CONTENT_MANIFEST.json'})
    product = [p for p in changed if not p.startswith('verification/m4_target_acquisition_001/')]
    check('product7 and namespace339', len(product) == 7 and len(changed)-len(product) == 339, product=product)
    final_blobs = git_blobs(FINAL, changed)
    for f in manifest['files']:
        b = read(ROOT/f['path'])
        check('manifest '+f['path'], sha(b) == f['sha256'] and len(b) == f['bytes'] and b == final_blobs[f['path']])
    check('manifest total', manifest['file_count'] == 345 and manifest['bytes'] == sum(f['bytes'] for f in manifest['files']))
    check('manifest self git exact', read(NS/'CONTENT_MANIFEST.json') == final_blobs['verification/m4_target_acquisition_001/CONTENT_MANIFEST.json'])

    binding, freeze, parity = [js(NS/p) for p in ('build_A/RUN_BINDING.json', 'SOURCE_FREEZE_A.json', 'A_GIT_SOURCE_PARITY.json')]
    sources = binding['source_manifest']
    check('141 sources agree between three records', len(sources) == 141 and sources == freeze['runtime_manifest'] and
          sources == [{'path': f['path'], 'sha256': f['sha256']} for f in parity['files']])
    computed_sha = sha(json.dumps({'base_version':'9.7.2', 'implementation_revision':freeze['implementation_revision'], 'files':sources},
                                 sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    check('canonical aggregate source identity', computed_sha == SOURCE_SHA == binding['source_sha256'] == parity['source_sha256'])
    check('freeze binding digest', sha(read(NS/'SOURCE_FREEZE_A.json')) == binding['source_freeze_sha256'])
    names = [f['path'] for f in sources]
    source_blobs = git_blobs(SOURCE_COMMIT, names)
    source_final_blobs = git_blobs(FINAL, names)
    wheel_path = next((NS/'build_A').glob('*.whl'))
    wheel_bytes = read(wheel_path)
    check('wheel pin', sha(wheel_bytes) == binding['wheel_sha256'])
    wheel = zipfile.ZipFile(io.BytesIO(wheel_bytes))
    for f in sources:
        n = f['path']
        variants = [source_blobs[n], source_final_blobs[n], read(ROOT/n), read(INSTALL/n), wheel.read(n)]
        check('source five-way '+n, all(b == variants[0] and sha(b) == f['sha256'] for b in variants))
    packages = ('human_eye_plugin', 'human_eye_module1_operators')
    top = {n for n in names if '/' not in n}
    for label, root in [('worktree', ROOT), ('install', INSTALL)]:
        enumerated = top | {pkg+'/'+p.name for pkg in packages for p in (root/pkg).glob('*.py')}
        check(label+' source enumeration', enumerated == set(names))
    wheel_names = top | {n for n in wheel.namelist() if n.endswith('.py') and n.count('/') == 1 and n.split('/')[0] in packages}
    check('wheel source enumeration', wheel_names == set(names))

    baseline = js(NS/'BASELINE.json')
    for p, h in baseline['protected_old_pins'].items():
        check('old pin '+p, sha(read(p)) == h)
    archive = js(NS/'RUNTIME_ARCHIVE.json')
    by_relative = {f['relative_path']: f for f in archive['files']}
    for f in archive['files']:
        a, o = read(NS/f['archive_path']), read(f['original_path'])
        check('runtime archive '+f['relative_path'], a == o and len(a) == f['bytes'] and sha(a) == f['sha256'])
    check('runtime archive272 bytes', len(archive['files']) == archive['file_count'] == 272 and
          sum(f['bytes'] for f in archive['files']) == archive['bytes'] == 8507203)

    def raw(relative):
        return read(NS/by_relative[relative]['archive_path'])
    def rjs(relative):
        return json.loads(raw(relative))

    cost, ledger = js(NS/'COST_A_QUALIFICATION.json'), js(NS/'QUALIFICATION_LEDGER.json')
    builder = rjs('assets_01/PREPARATION.json')
    a1 = rjs('qualification/A_peripheral_01/RESULT.json')
    a2 = rjs('qualification/A_peripheral_02/RESULT.json')
    check('builder timer', builder['closed_ns']-builder['started_ns'] == builder['elapsed_ns'] == cost['all_attempts']['builder_elapsed_ns'])
    for label, a in [('A01',a1),('A02',a2)]:
        check(label+' session timer', a['session_closed_ns']-a['started_ns'] == a['complete_session_ns'])
        check(label+' validation timer', a['postrun_closed_ns']-a['session_closed_ns'] == a['postrun_validation_ns'])
        check(label+' no model calls', a['model_calls'] == 0)
        check(label+' original deadline', a['original_lifecycle_deadline_ns'] == a['native_close']['original_deadline_ns'] ==
              a['native_final']['closed']['original_deadline_ns'])
        check(label+' worker close and unchanged scene', a['native_close']['exit_code'] == 0 and a['native_close']['process_reaped'] and
              a['native_final']['closed']['initial_geometry_fingerprint'] == a['native_final']['closed']['final_geometry_fingerprint'])
    check('A01 failure retained with runtime exit unknown', not a1['passed'] and bool(a1['errors']) and a1['MCP_runtime_exit']['confirmed'] is None and
          a1['complete_session_ns'] == cost['all_attempts']['first_failed_session_ns'])
    check('A02 runtime exit confirmed', a2['MCP_runtime_exit']['confirmed'] is True and a2['MCP_runtime_exit']['exit_code'] == 0)
    io_audit = next(r for r in a2['io_audit'] if r['id'] == 'target_observation')
    request = a2['requests'][0]
    check('A02 business timer', io_audit['reply_completed_ns']-io_audit['request_received_ns'] == io_audit['request_to_reply_ns'] == cost['complete_business_ns'])
    check('A02 outer timer', request['client_call_completed_ns']-request['client_call_started_ns'] == request['client_outer_including_recording_ns'] == cost['client_outer_ns'])
    check('A02 lifecycle and validation cost', a2['complete_session_ns'] == cost['complete_session_ns'] and a2['postrun_validation_ns'] == cost['postrun_saved_validation_ns'])
    check('registration clock', ledger['audit_closed_ns']-ledger['registered_analysis_started_ns'] == ledger['registered_analysis_elapsed_ns'])
    for stage, data in cost['acquisition_work']['stages'].items():
        check('acquisition timer '+stage, data['closed_ns']-data['started_ns'] == data['elapsed_ns'])

    rx = raw('qualification/A_peripheral_02/stdio/rpc_05/RX.bin')
    tx = raw('qualification/A_peripheral_02/stdio/rpc_05/TX.bin')
    reply, sent = json.loads(rx), json.loads(tx)
    check('stdio raw byte and digest pins', len(rx) == cost['raw_stdio']['RX_bytes'] == 12139 and sha(rx) == cost['raw_stdio']['RX_sha256'] and
          len(tx) == cost['raw_stdio']['TX_bytes'] == 257 and sha(tx) == io_audit['TX_sha256'])
    lf = rx.replace(b'\r\n',b'\n')
    check('stdio LF audit reconciles one-byte difference', len(lf) == io_audit['RX_bytes'] == 12138 and sha(lf) == io_audit['RX_sha256'] and rx.endswith(b'\r\n'))
    check('MCP saved response same object as raw wire', reply == rjs('qualification/A_peripheral_02/RESPONSE_01.json'))
    content = reply['result']['content']
    texts = [c['text'] for c in content if c['type'] == 'text']
    images = [c for c in content if c['type'] == 'image']
    check('public UTF8 actual', sum(len(t.encode()) for t in texts) == cost['public_delivery']['text_UTF8_bytes'] == 7088)
    check('public PNG and base64 actual', len(images) == 1 and sum(len(base64.b64decode(c['data'],validate=True)) for c in images) == cost['public_delivery']['PNG_bytes'] == 3223 and
          sum(len(c['data']) for c in images) == cost['public_delivery']['base64_chars'] == 4300)
    public = json.loads(texts[0])
    check('public runtime source pin', public['binding']['runtime_source_sha256'] == SOURCE_SHA)
    wirefiles = sorted(f['relative_path'] for f in archive['files'] if f['relative_path'].startswith('qualification/A_peripheral_02/native/') and f['relative_path'].endswith('/REQUEST.bin'))
    for f, entry in zip(wirefiles, a2['host_wire_index'], strict=True):
        rq, rs = raw(f), raw(f.replace('/REQUEST.bin','/RESPONSE.bin'))
        check('host wire '+str(entry['sequence']), len(rq) == entry['request_bytes'] and len(rs) == entry['response_attempted_bytes'] and
              len(rq)+len(rs) == entry['request_response_attempted_bytes'] and entry['response_sendall_completed'])
    check('host TCP cost copy matches raw-backed index', cost['host_TCP'] == a2['host_wire_index'])

    claims = [rjs(f) for f in by_relative if f.startswith('budget/claims/')]
    settlements = {s['token']:s for s in [rjs(f) for f in by_relative if f.startswith('budget/settlements/')]}
    for c in claims:
        s = settlements[c['token']]
        check('claim immutable pin '+c['token'], s['claim_sha256'] == sha(raw('budget/claims/'+c['token']+'.json')))
    starts = [c for c in claims if c['kind'] == 'Blender_start']
    rasters = [c for c in claims if c['kind'] == 'raster_request']
    check('3 starts all retained including A01 failed', len(starts) == 3 and all(settlements[c['token']]['spawn_status'] == 'spawned' for c in starts) and
          {settlements[c['token']]['outcome'] for c in starts} == {'passed','failed','completed'})
    events = [json.loads(line) for line in raw('qualification/A_peripheral_02/audit.jsonl').splitlines()]
    renders = [e for e in events if e['event'] == 'active_observation_render_attempt']
    observe = next(e for e in events if e['event'] == 'observe')
    check('one constructed raster crosschecks raw event', len(rasters) == 1 and len(renders) == 1 and renders[0]['view_name'] == 'SCENE' and observe['task_work']['raster_attempts'] == observe['task_work']['raster_completed'] == 1)
    for c in rasters:
        s = settlements[c['token']]
        check('no constructed charge refunded', c['reserved_upper_bound'] == 6 and s['actual_attempts'] == s['confirmed_attempts_lower_bound'] == 1 and
              s['released_proven_unconstructed_reservation'] == 5 and c['reserved_upper_bound']-s['released_proven_unconstructed_reservation'] == s['actual_attempts'])
    check('cost acquisition same raw event', cost['acquisition_work'] == observe['task_work']['target_acquisition'])
    counts = a2['budget_snapshot']['counts']
    check('final budget actual and upper same', counts['Blender_start_attempts'] == counts['Blender_spawned_confirmed'] == 3 and counts['qualification_raster_actual'] == counts['qualification_raster_upper'] == 1 and
          counts['formal_raster_actual'] == counts['formal_raster_upper'] == counts['pending_raster_reservations'] == 0)
    check('no B or formal denominator inflation', ledger['A_variants'] == 1 and ledger['B_variants'] == ledger['formal_slots'] == ledger['actual_formal_rasters'] == 0 and
          ledger['actual_owned_Blender_starts'] == 3 and ledger['actual_qualification_rasters'] == 1 and ledger['disposition'] == 'not_realized')
    check('model price and B benefit unavailable retained', cost['experimental_model_consumers'] == 0 and cost['experimental_tokens_and_cost'] == 'not_run' and cost['unknowns']['cash'] is None and cost['unknowns']['B_comparison'] is None)
    details.update({'manifest_files':345,'manifest_bytes':manifest['bytes'],'git_diff_files':346,'source_files_five_way':141,
                    'old_pins':len(baseline['protected_old_pins']),'runtime_archived_files':272,'source_sha256':computed_sha,
                    'A02_business_ms':cost['complete_business_ns']/1e6,'A02_client_ms':cost['client_outer_ns']/1e6,
                    'A02_session_ms':cost['complete_session_ns']/1e6,'A02_validation_ms':a2['postrun_validation_ns']/1e6,
                    'A01_failed_session_ms':a1['complete_session_ns']/1e6,'A01_validation_ms':a1['postrun_validation_ns']/1e6,
                    'builder_ms':builder['elapsed_ns']/1e6,'registration_wall_seconds':ledger['registered_analysis_elapsed_ns']/1e9,
                    'no_new_product_model_blender_raster_calls':True,'constructed_rasters':1,'owned_starts':3,
                    'author_runtime_review_checks_not_reexecuted':358,'author_product_checks_not_reexecuted':38,
                    'cleanup_unknown':'A01 actual MCP runtime handle unavailable; wrapper exit 0 is separate; no new process killing or cleanup attempted',
                    'scope':'Rehash fixed saved artifacts and independently recompute clocks/bytes/counts; no broader nested old manifest traversal or dynamic product regression.'})

if __name__ == '__main__':
    started = time.time()
    try:
        main()
    except Exception as e:
        import traceback
        checks.append({'name':'review checker exception','passed':False,'exception':str(e),'traceback':traceback.format_exc()})
    result = {'schema':'independent-m4-target-identity-cost-review-v1','final_git':FINAL,'source_git':SOURCE_COMMIT,
              'base_git':BASE,'reviewer':'/root/target001_identity_cost','AL_assignment':'e5d54595-8858-4234-ab59-509afd896bad',
              'passed':all(c['passed'] for c in checks),'checks_passed':sum(c['passed'] for c in checks),'checks_total':len(checks),
              'details':details,'checks':checks,'inputs':inputs,'review_seconds':time.time()-started,
              'prior_inspection_error':'Read-only rg first used nonexistent harness/build_install.py; exit1 retained here; corrected discovery is namespace/build_install.py. No product or artifact changed.'}
    dest = OUT/'RESULT.json'
    if dest.exists():
        dest = OUT/('RESULT_'+str(time.time_ns())+'.json')
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'path':str(dest),'passed':result['passed'],'passed_checks':result['checks_passed'],'total_checks':len(checks),'failures':[c for c in checks if not c['passed']],'details':details},ensure_ascii=False))
