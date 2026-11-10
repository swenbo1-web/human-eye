import ast, hashlib, io, json, subprocess
from collections import Counter
from pathlib import Path

WT = Path(r'C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe')
REL = 'verification/m1_task_entry_001'
R = WT / REL
OUT = Path(r'D:\hefe\verification\fixes\20261110_m1_task_entry_review\SOURCE_REVIEW.json')
COMMIT = 'b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3'
PARENT = 'd341bb68a4747d1076d5e332789bee1d5f217cd7'
BASE = 'df016079b0265ee327f884c90dd4815c392016b6'
sha = lambda b: hashlib.sha256(b).hexdigest()
H = lambda p: sha(Path(p).read_bytes())
J = lambda p: json.loads(Path(p).read_text(encoding='utf-8-sig'))
L = lambda p: J(R / p)
G = lambda *a: subprocess.check_output(['git', '-C', str(WT), *a])
errors, counts = [], Counter()

def check(ok, name, path=None):
    counts[name] += 1
    if not ok:
        errors.append({'check': name, 'path': str(path) if path else None})

def git_blobs(commit, paths):
    result = subprocess.run(['git', '-C', str(WT), 'cat-file', '--batch'],
        input=''.join(commit+':'+p+'\n' for p in paths).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    stream, values = io.BytesIO(result.stdout), {}
    for path in paths:
        header = stream.readline().split()
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError('Missing Git blob ' + path)
        values[path] = stream.read(int(header[2]))
        assert stream.read(1) == b'\n'
    return values

index, seal = L('ARTIFACT_INDEX.json'), L('CANDIDATE_SEAL.json')
manifest = L('blender_equivalence_01/SOURCE_MANIFEST.json')
initial = L('blender_equivalence_01/EXECUTION_IDENTITY_INITIAL.json')
final = L('blender_equivalence_01/EXECUTION_IDENTITY_FINAL.json')
digest = seal['candidate_source_sha256']
head, worktree_status = G('rev-parse', 'HEAD').decode().strip(), G('status', '--porcelain').decode()
check(head == COMMIT and not worktree_status, 'clean_fixed_HEAD')
check(G('rev-parse', COMMIT+'^').decode().strip() == PARENT == seal['parent_commit'], 'parent_commit')
check(H(R/'ARTIFACT_INDEX.json') == 'f7ab0e8c524491df19163845c242d336269dd92b80f78fc88d39b7c618da39c8', 'requested_index_pin')
check(H(R/'CANDIDATE_SEAL.json') == 'ab79463fe3648f30dd988524c27821ae344e8f6378f0d741b4d5103651706094', 'requested_seal_pin')
artifact_paths = [x['path'] for x in index['files']] + [REL+'/ARTIFACT_INDEX.json', REL+'/CANDIDATE_SEAL.json']
artifact_blobs = git_blobs(COMMIT, artifact_paths)
total_bytes = 0
for row in index['files']:
    raw = (WT/row['path']).read_bytes()
    total_bytes += len(raw)
    check(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'artifact_hash_and_bytes', row['path'])
for path, raw in artifact_blobs.items():
    check((WT/path).read_bytes() == raw, 'artifact_Git_blob_bytes', path)
tracked = set(G('ls-tree', '-r', '--name-only', COMMIT, '--', REL).decode().splitlines())
check(tracked == set(artifact_paths), 'all_committed_members_indexed')
check(len(index['files']) == index['file_count'] == seal['artifact_count'] == 225 and total_bytes == index['bytes'] == 5102648, 'artifact_denominator_bytes')
check(seal['artifact_index_sha256'] == H(R/'ARTIFACT_INDEX.json') and seal['report_sha256'] == H(R/'REPORT.md') and seal['source_manifest_sha256'] == H(WT/seal['source_manifest_path']), 'seal_internal_pins')

paths = [x['path'] for x in manifest['files']]
candidate, baseline, parent = [git_blobs(commit, paths) for commit in (COMMIT, BASE, PARENT)]
check(len(paths) == len(set(paths)) == 137 == manifest['source_file_count'] == seal['source_files'], 'source_137_denominator')
for row in manifest['files']:
    p = row['path']
    check(sha(candidate[p]) == row['sha256'] and (WT/p).read_bytes() == candidate[p], 'candidate_manifest_and_checkout', p)
    check(parent[p] == baseline[p], 'parent_matches_product_baseline', p)
changed = [p for p in paths if candidate[p] != baseline[p]]
check(changed == ['human_eye_plugin/live_spatial_mcp.py', 'human_eye_plugin/production_server.py'], 'only_two_product_changes')
diff = [{'path': p, 'old_sha256': sha(baseline[p]), 'new_sha256': sha(candidate[p])} for p in changed]
check(diff == manifest['runtime_diff'] == seal['product_diff'], 'declared_product_diff')
version, revision = initial['identity']['base_version'], initial['identity']['implementation_revision']
def canonical(data):
    value = {'base_version': version, 'implementation_revision': revision,
             'files': [{'path': p, 'sha256': sha(data[p])} for p in paths]}
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
check(canonical(candidate) == digest == manifest['candidate_source_sha256'], 'candidate_canonical')
check(canonical(baseline) == manifest['baseline_source_sha256'] == '3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd', 'baseline_canonical')
copy_roots = ['offline_02/engine', 'offline_03/engine', 'blender_equivalence_01/runtime']
for rel in copy_roots:
    root = R/rel
    check({p.relative_to(root).as_posix() for p in root.rglob('*.py')} == set(paths), 'snapshot_source_membership', rel)
    for p in paths:
        check((root/p).read_bytes() == candidate[p], 'physical_engine_runtime_bytes', rel+'/'+p)
check(H(WT/'pyproject.toml') == manifest['pyproject_sha256'] and (R/'blender_equivalence_01/runtime/pyproject.toml').read_bytes() == (WT/'pyproject.toml').read_bytes(), 'Blender_pyproject_marker')
check(all(not (R/rel/'pyproject.toml').exists() for rel in copy_roots[:2]), 'offline_uninstalled_marker_absent')
expected_exclusions = {rel+'/'+p for rel in copy_roots for p in paths} | {'blender_equivalence_01/runtime/pyproject.toml', 'blender_equivalence_01/assembly/native/input.blend', 'blender_equivalence_01/D48/native/input.blend'}
check(set(index['excluded_local_duplicate_files']) == expected_exclusions and len(expected_exclusions) == 414, 'excluded_copy_scope')
check(all((R/p).is_file() and REL+'/'+p not in tracked for p in expected_exclusions), 'excluded_copies_exist_untracked')
refs = manifest['reference_files']
ref_blobs = git_blobs(PARENT, [r['path'] for r in refs])
for row in refs:
    check(H(WT/row['path']) == row['sha256'] == sha(ref_blobs[row['path']]), 'historical_reference_Git_and_disk', row['path'])
check(H(R/'run_blender_equivalence.py') == manifest['runner_sha256'], 'Blender_runner_hash')
check(initial['guard_verify_loaded'] is True and final['guard_verify_loaded'] is True, 'recorded_guard_verification')
check(initial['identity'] == final['identity'] and initial['identity']['source_sha256'] == digest and initial['identity']['source_files'] == manifest['files'] == final['runtime_manifest'], 'Blender_initial_final_identity')
check(initial['identity']['source_kind'] == 'source_checkout' and final['source_file_count'] == 137 and initial['root'] == manifest['runtime_root'], 'recorded_Blender_runtime_root')
for module, p in final['loaded_product_witnesses'].items():
    check(p in paths, 'Blender_module_witness_manifest', module)
modified_modules = {'human_eye_plugin.live_spatial_mcp'}
production_ast = ast.parse(candidate['human_eye_plugin/production_server.py'])
help_replacements = 0
for node in ast.walk(production_ast):
    if isinstance(node, ast.Constant) and node.value == 'Expose only live read-only spatial relations and global surface-nearest tasks':
        node.value = 'Expose only the live read-only spatial relations task'
        help_replacements += 1
production_help_only = help_replacements == 1 and ast.dump(production_ast) == ast.dump(ast.parse(baseline['human_eye_plugin/production_server.py']))
check(production_help_only, 'production_server_only_help_literal_changed')
check(modified_modules <= set(final['loaded_product_witnesses']), 'Blender_modified_modules_executed_record')
helper_pin = next(x['sha256'] for x in refs if x['path'].endswith('accepted_native.py'))
check(initial['helper_sha256'] == helper_pin, 'native_helper_source_pin')

publication_count = 0
for p in R.rglob('*.publication.json'):
    doc = J(p); target = Path(doc['path']); publication_count += 1
    check(H(target) == doc['sha256'] and target.stat().st_size == doc['bytes'], 'publication_bytes', p.relative_to(R))
    check(doc['valid_current_evidence'] and all(doc[k]['source_ok'] and doc[k]['deadline_ok'] and doc[k]['errors'] == [] for k in ('before', 'after')), 'publication_source_deadline_records', p.relative_to(R))
summary = L('blender_equivalence_01/SUMMARY.json')
check(summary['passed'] and summary['errors'] == [] and len(summary['cases']) == 2, 'stored_two_case_summary')
case_rows, pids = [], []
for case, fixture in [('assembly', 'verification/native_plugin_complex_003/private/author_mesh_snapshots.json'), ('D48', 'verification/scale_diag_001/fixtures/D48.json')]:
    folder = R/'blender_equivalence_01'/case
    result, contract = J(folder/'RESULT.json'), J(folder/'CONTRACT.json')
    ini, fin = J(folder/'INITIAL_SNAPSHOT.json'), J(folder/'FINAL_SNAPSHOT.json')
    expected = J(WT/fixture); expected = expected.get('initial', expected)
    normalized = {'unit_scale_m': expected['unit_scale_m'], 'objects': [{'name': o['name'], 'vertices_local': o['vertices_local'], 'matrix_world': o['matrix_world'], 'faces': o.get('faces', o.get('triangles'))} for o in expected['objects']]}
    check(ini == fin == normalized, 'complete_geometry_initial_final_fixture', case)
    for name, mesh in [('INITIAL', ini), ('FINAL', fin)]:
        receipt = J(folder/(name+'_SNAPSHOT_RECEIPT.json')); response = receipt['response']
        check(receipt['source_file_unchanged'] and receipt['protected_files_unchanged'] and response['status'] == 'success' and response['result']['executed'] is True and json.loads(response['result']['result']) == mesh, 'snapshot_receipt_exact', case+'/'+name)
    check(J(folder/'ACTION_STATE_BEFORE.json') == J(folder/'ACTION_STATE_AFTER.json'), 'action_state_unchanged_record', case)
    config, session, ready, closed = [J(folder/'native'/f) for f in ['CONFIG.json', 'SESSION.json', 'READY.json', 'WORKER_CLOSED.json']]
    status, close = J(folder/'NATIVE_FINAL_STATUS.json'), result['native_close']
    check(config['asset_sha256'] == session['asset_sha256'] == contract['asset_sha256'] == H(WT/contract['asset']) == H(config['asset_copy']), 'original_asset_and_copy_hash', case)
    check(session['helper_sha256'] == ready['helper_sha256'] == initial['helper_sha256'] and session['blender_sha256'] == initial['blender_sha256'], 'worker_helper_and_binary_record', case)
    check(session['pid'] == ready['pid'] == closed['pid'] == close['pid'], 'worker_PID_binding', case)
    check(session['deadline_ns'] == ready['deadline_ns'] == closed['original_deadline_ns'] == close['original_deadline_ns'] == result['original_deadline_ns'], 'worker_original_deadline_binding', case)
    check(ready['initial_fingerprint'] == closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint'] and closed['poisoned'] is False, 'worker_geometry_fingerprint', case)
    check(status['closed'] == closed and status['ready'] == ready and status['source_file_unchanged'] and status['protected_files_unchanged'], 'worker_final_status_binding', case)
    check(close['exit_code'] == 0 and close['process_reaped'] and close['error'] is None and close['source_file_unchanged'] and close['protected_files_unchanged'] and close['response']['status'] == 'closed', 'worker_normal_close_receipt', case)
    check(close in [J(p) for p in (folder/'native').glob('CLOSE_*.json')], 'saved_worker_close_binding', case)
    check(J(folder/'PRODUCT_HOST_CLOSE.json')['closed'] is True, 'recorded_product_host_close', case)
    check(J(folder/'native_rpc/003_RESPONSE.json')['response'] == close['response'] and J(folder/'native_rpc/003_REQUEST.json')['request'] == {'type': 'close'}, 'raw_close_RPC_binding', case)
    accounting = J(folder/'RPC_ACCOUNTING.json')
    events = [json.loads(line) for line in (folder/'native/WORKER_EVENTS.jsonl').read_bytes().splitlines() if line]
    check(events == accounting['worker_events'] and len(events) == 5 and all(e['status'] == 'completed' and e['terminal_geometry_and_file_checks_passed'] and e['script_error'] is None for e in events[:4]), 'four_script_worker_event_records', case)
    check(events[-1]['status'] == 'unknown' and 'script_sha256' not in events[-1], 'close_control_unknown_preserved', case)
    scripts = sorted((folder/'native').glob('call_*/SCRIPT.py'))
    check(len(scripts) == accounting['script_count'] == 4, 'worker_script_denominator', case)
    for script, event in zip(scripts, events):
        check(sha(script.read_text(encoding='utf-8').encode('utf-8')) == event['script_sha256'], 'worker_executed_text_hash', script.relative_to(R))
    for row in accounting['worker_artifacts']:
        check(H(R/'blender_equivalence_01'/row['path']) == row['sha256'], 'worker_secondary_artifact_hash', row['path'])
    check(accounting['new_images'] == accounting['product_save_commands'] == accounting['product_setter_commands'] == 0, 'recorded_zero_save_setter_images', case)
    check(result['passed'] and result['errors'] == [] and result in summary['cases'], 'case_summary_binding', case)
    pids.append(session['pid'])
    case_rows.append({'case': case, 'full_snapshot_matches_fixed_fixture': True, 'asset_sha256': contract['asset_sha256'], 'worker_exit_code': close['exit_code'], 'worker_recorded_reaped': close['process_reaped'], 'completed_script_events': 4, 'close_control_event': 'unknown preserved; separate raw close response=closed and exit receipt=0/reaped', 'semantic_oracle_recomputed': False})
cleanup = L('OWNED_WORKER_CLEANUP.json')
check({x['pid'] for x in cleanup['workers']} == set(pids) and cleanup['all_owned_workers_absent'] and all(x['present'] is False for x in cleanup['workers']), 'historical_owned_worker_absence_snapshot')

offline = []
for attempt in ['offline_02', 'offline_03']:
    ident, result = L(attempt+'/EXECUTION_IDENTITY.json'), L(attempt+'/RESULTS.json')
    check(ident['runtime_source_sha256'] == result['runtime_source_sha256'] == digest and ident['source_count'] == result['source_count'] == 137 and ident['manifest'] == manifest['files'], 'offline_same_candidate_bytes', attempt)
    check(ident['guard_verify_loaded'] and ident['product_files_unchanged'] and ident['sealed_original_files_unchanged'], 'offline_guard_and_preservation_records', attempt)
    check(modified_modules <= set(ident['loaded_product_witnesses']), 'offline_modified_module_witnesses', attempt)
    for module, p in ident['loaded_product_witnesses'].items():
        check(p in paths, 'offline_module_manifest_witness', attempt+'/'+module)
    check(H(R/'run_offline.py') == ident['runner_sha256'], 'offline_runner_pin', attempt)
    for name, expected in {**ident['fixture_sha256'], **ident['sealed_original_files_sha256']}.items():
        check(H(WT/name) == expected, 'preserved_fixture_hash', name)
    if attempt == 'offline_03':
        test = ident['test']
        check(H(WT/test['path']) == test['sha256'] and (WT/test['path']).stat().st_size == test['bytes'] and test['unchanged'], 'final_test_exact_bytes')
        check(result['tests'] == 14 and result['successful'] and not result['failures'] and not result['errors'] and not result['skipped'], 'recorded_final_14_pass')
    else:
        check(result['tests'] == 14 and not result['successful'] and len(result['failures']) == 2 and len(result['errors']) == 1, 'recorded_early_failures_retained')
    offline.append({'attempt': attempt, 'tests': result['tests'], 'failures': len(result['failures']), 'errors': len(result['errors']), 'skipped': len(result['skipped']), 'successful': result['successful'], 'test_sha256_recorded': ident['test']['sha256'], 'source_digest_matches': True, 'loaded_product_witnesses': len(ident['loaded_product_witnesses'])})
check((R/'offline_01/BOOTSTRAP_FAILURE.txt').stat().st_size > 0, 'bootstrap_failure_retained')
report = {
    'schema_version': 1, 'status': 'passed' if not errors else 'requires_review',
    'scope': 'Independent byte/Git/source and stored execution-record binding review; no product import, product process, Blender, model or test replay.',
    'candidate_commit': COMMIT, 'parent_commit': PARENT, 'product_baseline_commit': BASE,
    'worktree_HEAD': head, 'worktree_clean': not worktree_status,
    'seal_filename_note': 'The actual file is CANDIDATE_SEAL.json; its SHA matches the requested SEAL pin.',
    'artifact_index': {'path': str(R/'ARTIFACT_INDEX.json'), 'sha256': H(R/'ARTIFACT_INDEX.json'), 'members': 225, 'member_bytes': total_bytes, 'Git_blob_members_including_index_and_seal': len(tracked), 'excluded_reconstructable_local_copies': len(expected_exclusions)},
    'seal': {'path': str(R/'CANDIDATE_SEAL.json'), 'sha256': H(R/'CANDIDATE_SEAL.json')},
    'source': {'count': 137, 'candidate_canonical': canonical(candidate), 'baseline_canonical': canonical(baseline), 'changed_sources': changed, 'unchanged_sources': 137-len(changed), 'snapshot_roots_checked': copy_roots, 'snapshot_sources_checked': 137*3, 'historical_reference_Git_blobs': len(refs)},
    'execution_records': {'Blender_source_kind': initial['identity']['source_kind'], 'Blender_loaded_product_witnesses': len(final['loaded_product_witnesses']), 'offline': offline, 'Blender_cases': case_rows, 'publication_receipts': publication_count, 'stored_worker_absence_records': len(cleanup['workers']), 'changed_behavior_module_witnessed': 'human_eye_plugin.live_spatial_mcp', 'production_server_witnessed': False, 'production_server_only_help_literal_changed': production_help_only, 'identity_scope': 'Physical copies, manifest and guarded-loaded witness records agree. They are archived execution records, not a newly observed independent execution. Offline records contain source digest/manifests but not a complete distribution-identity object; no installed-version qualification is inferred. production_server has only a help-text literal change; its CLI was not executed by these records.'},
    'history_preserved': ['offline_01 bootstrap rejection', 'offline_02 two failures and one error', 'close-control worker event status unknown, separate closed response and exit=0/reaped receipts'],
    'checks_performed': dict(counts), 'errors': errors,
    'not_independently_run': ['14-case offline suite', 'Two Blender regression scenes', 'production_server CLI invocation', 'Geometric oracle recalculation', 'Performance/model/quality/cost qualification', 'Installation or current default-entry qualification', 'Fresh PID presence scan'],
    'reviewer_harness_note': 'Initial read used SEAL.json shorthand and an artifact path twice-prefixed with the directory; corrected to actual CANDIDATE_SEAL.json and repository-relative index paths before this completed audit. No project file was changed.',
    'product_execution_count': 0, 'Blender_execution_count': 0, 'model_execution_count': 0, 'worktree_or_product_writes': 0,
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'status': report['status'], 'artifact_members': 225, 'artifact_bytes': total_bytes, 'Git_blobs': len(tracked), 'source_count': 137, 'unchanged_sources': 137-len(changed), 'publication_receipts': publication_count, 'errors': errors, 'output': str(OUT)}, ensure_ascii=False))
