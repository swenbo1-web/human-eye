"""Independent offline audit; never imports product or author execution modules."""
import collections
import hashlib
import json
import pathlib
import subprocess
import tomllib

ROOT = pathlib.Path('C:/Users/Administrator/.codex/worktrees/m4-view-reuse-001/hefe')
NS = ROOT / 'verification/m4_occluded_scene_transfer_001'
OUT = pathlib.Path(__file__).resolve().parent
RUN = pathlib.Path('D:/he_occluded_transfer_001')
FINAL = '1f3db153d4a46363ed3e64103d495bbc5ee65864'
BASE = 'b0e2fcfe90b7b535105e24dff9c34b36c27a26af'
checks = []
hashes = {}

def read(p):
    return json.loads(pathlib.Path(p).read_bytes())

def sha(p):
    p = pathlib.Path(p)
    key = str(p.resolve()).casefold()
    if key not in hashes:
        hashes[key] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes[key]

def check(label, condition, detail=None):
    checks.append(dict(label=label, passed=bool(condition), detail=detail))

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

check('final_HEAD', git('rev-parse', 'HEAD').decode().strip() == FINAL)
check('clean_author_tree', not git('status', '--porcelain'))
refstate = {}
for ref in ['refs/heads/codex/architecture-arm-correction', 'refs/remotes/origin/codex/architecture-arm-correction']:
    refstate[ref] = git('rev-parse', ref).decode().strip()
check('remote_tracking_final', refstate['refs/remotes/origin/codex/architecture-arm-correction'] == FINAL)

manifest = read(NS / 'CONTENT_MANIFEST.json')
expected_paths = {r['path'] for r in manifest['files']} | {'verification/m4_occluded_scene_transfer_001/CONTENT_MANIFEST.json'}
changed = {p for p in git('diff', '--name-only', '-z', BASE, FINAL).decode().split('\0') if p}
check('only_1125_expected_new_paths', len(expected_paths) == 1125 and changed == expected_paths)
for row in manifest['files']:
    path = ROOT / row['path']
    check('manifest:' + row['path'], path.stat().st_size == row['bytes'] and sha(path) == row['sha256'])
tree = {}
for entry in git('ls-tree', '-r', '-z', FINAL, '--', 'verification/m4_occluded_scene_transfer_001').split(b'\0'):
    if entry:
        fields, path = entry.split(b'\t', 1)
        tree[path.decode()] = fields.split()[2].decode()
check('git_tree_exact_paths', set(tree) == expected_paths)
for name, oid in tree.items():
    raw = (ROOT / name).read_bytes()
    check('git_blob:' + name, hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == oid)

fixed_groups = {}
for name, key in [('FROZEN.json', 'files_sha256'), ('admin/QUALIFICATION_SEAL.json', 'files_sha256'), ('admin/QUALITY_SEAL.json', 'inputs')]:
    data = read(NS / name)[key]
    pairs = list(data.items()) if isinstance(data, dict) else [(r['path'], r['sha256']) for r in data]
    fixed_groups[name] = len(pairs)
    for path, digest in pairs:
        check('seal:' + name + ':' + path, sha(path) == digest)
for path, digest in read(NS / 'BASELINE.json')['protected_manifests'].items():
    check('protected_manifest:' + path, sha(path) == digest)
for path, digest in read(NS / 'FINAL_AUDIT.json')['artifacts_sha256'].items():
    check('final_artifact:' + path, sha(NS / path) == digest)
archive = read(NS / 'RUNTIME_ARCHIVE.json')
for row in archive['files']:
    original, copy = pathlib.Path(row['original_path']), NS / row['archive_path']
    check('archive:' + row['relative_path'], original.stat().st_size == copy.stat().st_size == row['bytes'] and sha(original) == sha(copy) == row['sha256'])

binding = read(ROOT / 'verification/m4_view_reuse_001/build/RUN_BINDING.json')
product_tree = {}
for entry in git('ls-tree', '-r', '-z', 'd12c7ab248452ff253452007d0635f2d662f0191').split(b'\0'):
    if entry:
        fields, path = entry.split(b'\t', 1)
        product_tree[path.decode()] = fields.split()[2].decode()
check('141_product_binding', len(binding['source_manifest']) == 141 and binding['source_sha256'] == 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02')
for row in binding['source_manifest']:
    path = pathlib.Path(binding['install_root']) / row['path']
    raw = path.read_bytes()
    check('product_install_git:' + row['path'], sha(path) == row['sha256'] and hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == product_tree[row['path']])

plan = read(NS / 'PLAN.json')
suffix = (NS / 'inputs/PROMPT_SUFFIX.txt').read_bytes()
check('root_plan_exact', (NS / 'ADMINISTRATOR_PLAN.md').read_bytes() == pathlib.Path('D:/hefe/docs/M4_OCCLUDED_SCENE_TRANSFER_001_PLAN.md').read_bytes())
check('common_suffix_hash', hashlib.sha256(suffix).hexdigest() == plan['expected_suffix_sha256'])
for group in ['N', 'P']:
    prefix = (NS / ('inputs/PREFIX_' + group + '.txt')).read_bytes()
    prompt = NS / ('inputs/PROMPT_' + group + '.txt')
    check('prompt_composition_' + group, prompt.read_bytes() == prefix + b'\n\n' + suffix and sha(prompt) == plan['expected_prompt_sha256'][group])

sequence = ['N1', 'P1', 'P2', 'N2', 'N3', 'P3']
formal = RUN / 'formal'
run = read(formal / 'RUN_RESULT.json')
qual = read(RUN / 'preparation/QUALIFICATION_RUN.json')
check('six_fresh_slots', [r['slot'] for r in run['records']] == sequence and run['actual_routes'] == run['actual_CLI_processes'] == 6 and len(set(run['observed_fresh_threads'])) == 6 and run['outer_retries'] == 0)
check('only_six_slot_directories', {p.name for p in formal.iterdir() if p.is_dir()} == set(sequence) | {'slot_records'})
check('qual_model_free', qual['actual_model_calls'] == 0 and qual['actual_product_calls'] == 1 and qual['actual_rasters'] == 9)
qstart = read(NS / 'QUALIFICATION_STARTED.json')
fstart = read(NS / 'FORMAL_STARTED.json')
qseal = read(NS / 'admin/QUALIFICATION_SEAL.json')
freeze = read(NS / 'FROZEN.json')
check('temporal_freeze_qual_formal', freeze['before_publication_ns'] < qstart['started_ns'] < qseal['before_publication_ns'] < fstart['started_ns'])
common_names = {'scene_data', 'execute_python', 'render_views', 'read_images'}
schemas = []
common_configs = []
slot_summaries = []
for slot in sequence:
    group = slot[0]
    p = formal / slot
    config = read(p / 'ACTOR_CONFIG.json')
    consumer = read(p / 'c/CONSUMER.json')
    identity = read(p / 'o/IDENTITY.json')
    dep = read(p / 'o/DEPENDENCIES.json')
    metrics = read(p / 'o/METRICS.json')
    result = read(formal / ('slot_records/' + slot + '/SLOT_RESULT.json'))
    route = result['route']
    timing = read(formal / ('slot_records/' + slot + '/SLOT_TIMING.json'))
    schema = {r['name']: r for r in read(p / 'o/TOOLS_SCHEMA.json')}
    schemas.append({name:schema[name] for name in sorted(common_names)})
    check(slot + ':tools', set(schema) == common_names | ({'active_observation'} if group == 'P' else set()))
    check(slot + ':constant_caps', config['max_render_attempts'] == 6 and config['max_tool_calls'] == 12 and config['phase_render_cap'] == 36 and config['whole_render_cap'] == 48)
    check(slot + ':same_original_deadline', config['worker_deadline_ns'] == identity['worker_deadline_ns'] == route['deadline_ns'] == consumer['deadline_ns'] and route['deadline_ns'] - route['started_ns'] == 450_000_000_000)
    check(slot + ':prompt_hash', consumer['input_sha256'] == plan['expected_prompt_sha256'][group])
    check(slot + ':product_binding', config['runtime_binding']['binding']['sha256'] == sha(ROOT / 'verification/m4_view_reuse_001/build/RUN_BINDING.json') and dep['product_source_sha256'] == plan['product_source_sha256'])
    check(slot + ':shared_deps', config['runtime_binding']['shared_dependency'] == plan['shared_dependency'])
    check(slot + ':completed_unmutated', route['execution_state'] == 'completed' and result['source_unchanged'] and route['input_readback_unchanged'] and not result['terminal_errors'])
    check(slot + ':raw_tools_within_budget', metrics['tool_attempts'] <= 12 and metrics['common']['render_attempts'] <= 6)
    audit = metrics['common']['audit']
    check(slot + ':private_no_access_attempts', audit['forbidden_old_evidence_reads'] == 0 and audit['forbidden_old_writes'] == 0 and not audit['forbidden_product_calls'])
    check(slot + ':owner_terminal', route['owner_process_cleanup']['confirmed'] and route['owner_process_cleanup']['reaped'] and route['owner_process_cleanup']['process_handle_closed'] and route['owner_close_confirmed'])
    check(slot + ':CLI_terminal', route['consumer_process_cleanup']['confirmed'] and route['consumer_process_cleanup']['reaped'] and route['consumer_process_cleanup']['process_handle_closed'])
    check(slot + ':thin_terminal', route['runtime_binding']['confirmed'] and route['runtime_exit']['confirmed'] and route['runtime_exit']['handle_closed'] and route['runtime_exit']['exited'])
    check(slot + ':same_complete_clock', timing['elapsed_ns'] == timing['SLOT_RESULT_closed_ns'] - timing['started_ns'] and timing['started_ns'] == result['started_ns'] and timing['started_ns'] <= route['started_ns'] < route['owner_process_cleanup']['closed_ns'] < timing['SLOT_RESULT_closed_ns'])
    check(slot + ':fact_check_outside_slot', read(formal / ('slot_records/' + slot + '/FACT_CHECK.json'))['started_ns'] >= timing['SLOT_RESULT_closed_ns'])
    argv = consumer['argv']
    check(slot + ':frozen_argv', argv == consumer['frozen_cli_argv'])
    cfg = {}
    for i, item in enumerate(argv):
        if item == '-c':
            cfg.update(tomllib.loads(argv[i+1]))
    servers = cfg.pop('mcp_servers')
    server = servers['arm_engine']
    check(slot + ':tool_approval_parity', set(server['tools']) == set(schema) and all(x['approval_mode'] == 'approve' for x in server['tools'].values()))
    common_configs.append(cfg)
    check(slot + ':isolation_flags', all(x in argv for x in ['--ignore-user-config','--ignore-rules','--strict-config']) and cfg['features']['hooks'] is False and cfg['features']['apps'] is False and cfg['features']['memories'] is False and cfg['skills']['include_instructions'] is False and cfg['project_doc_max_bytes'] == 0 and cfg['features']['shell_tool'] is False and cfg['features']['view_image'] is False)
    check(slot + ':model_request', cfg['model'] == 'gpt-6.1-sol' and cfg['model_reasoning_effort'] == 'medium' and cfg['service_tier'] == 'default')
    check(slot + ':no_initial_answer_attachment', consumer['input_image_count'] == 0 and consumer['turn_index'] == 1 and consumer['expected_thread_id'] is None)
    slot_summaries.append(dict(slot=slot, thread=consumer['thread_id'], owner_pid=identity['actor_pid'], cli_pid=consumer['consumer_pid'], thin_pid=route['runtime_binding']['runtime_pid'], thin_exit=route['runtime_exit']['exit_code'], business_calls=metrics['tool_attempts'], rasters=metrics['common']['render_attempts'], complete_clock_ns=timing['elapsed_ns'], resolved_effort=consumer['resolved_effort']))
check('common_schemas_identical', all(s==schemas[0] for s in schemas))
check('common_CLI_configs_identical', all(s==common_configs[0] for s in common_configs))
intents = [read(p) for p in sorted((RUN / 'raster_budget').glob('attempt_*/INTENT.json'))]
check('exact_39_construct_attempts', len(intents) == 39 and [r['global_attempt'] for r in intents] == list(range(1,40)))
check('qualification_formal_phases', [r['phase'] for r in intents] == ['preparation']*9+['formal']*30)
report = dict(schema='root-independent-occluded-identity-v1', author_commit=FINAL,
              passed=all(r['passed'] for r in checks), checks=len(checks), failures=[r for r in checks if not r['passed']],
              read_scope='Saved bytes and original receipts; no product/model/Blender/raster invoked. Author generators not executed.',
              git_refs=refstate, author_worktree='detached HEAD at final; local named branch remains attached to old frozen worktree',
              hash_files_read_once=len(hashes), seals=fixed_groups, archived_files=len(archive['files']),
              product_sources=len(binding['source_manifest']), slots=slot_summaries,
              no_new_calls=dict(product=0,model=0,Blender=0,raster=0), detailed_checks=checks)
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='detailed_checks'},ensure_ascii=False,indent=2))
