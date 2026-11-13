"""Independent, offline lifecycle evidence audit; never imports author programs."""
from pathlib import Path
import hashlib
import json

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_003')
OUT = Path(__file__).resolve().parent
INPUTS = {}
CHECKS = []

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data

def read(path):
    return json.loads(raw(path))

def digest(path):
    return hashlib.sha256(raw(path)).hexdigest()

def need(label, value):
    CHECKS.append({'check': label, 'passed': bool(value)})
    if not value:
        raise AssertionError(label)

def trace(path):
    return [json.loads(line) for line in raw(path).splitlines()]

def norm(path):
    return str(Path(path).resolve()).casefold()

frozen = read(AUTHOR/'FROZEN.json')
q = read(AUTHOR/'qualification/RESULTS.json')
result = read(AUTHOR/'RESULTS.json')
prereg = read(AUTHOR/'PREREGISTRATION.json')
contract = frozen['launch_contract']
sources = {norm(k): v for k, v in frozen['runtime_sources'].items()}
need('qualification exact same frozen source map', q['source_files_sha256'] == frozen['runtime_sources'])
need('qualification freeze digest', q['source_freeze_sha256'] == digest(AUTHOR/'FROZEN.json'))
need('formal qualification and freeze digests', result['qualification_result_sha256'] == digest(AUTHOR/'qualification/RESULTS.json') and result['freeze_sha256'] == digest(AUTHOR/'FROZEN.json'))

source_names = ['launch.py', 'bootstrap.py', 'qualify.py', 'probe.py', 'runtime.py', 'runner.py', 'validate.py']
for name in source_names:
    need('current frozen code: '+name, digest(AUTHOR/name) == sources[norm(AUTHOR/name)])
need('actual base exe frozen', digest(contract['base_executable']) == contract['base_executable_sha256'] == sources[norm(contract['base_executable'])])
for name, lib in contract['expected_dependencies'].items():
    need('fixed dependency init: '+name, digest(lib['path']) == lib['init_sha256'] == sources[norm(lib['path'])])

def command_checks(command, entry, folder, label):
    expected = [contract['base_executable'], '-I', '-B', '-X', 'utf8', contract['bootstrap_path'], str((AUTHOR/entry).resolve())]
    need(label+' direct base/bootstrap command', command[:7] == expected)
    need(label+' absolute current output', norm(command[command.index('--output')+1]) == norm(folder))

def environment_checks(env, pid, label):
    need(label+' actual base process', env['process_id'] == pid and norm(env['python_executable']) == norm(contract['base_executable']))
    need(label+' four actual prefixes are base', all(norm(env[key]) == norm(Path(contract['base_executable']).parent) for key in ['sys_prefix','sys_base_prefix','sys_exec_prefix','sys_base_exec_prefix']))
    for key in ['base_executable', 'base_executable_sha256', 'bootstrap_path', 'bootstrap_sha256', 'explicit_site_packages', 'product_install_root', 'dependency_manifest_path', 'dependency_manifest_sha256']:
        need(label+' fixed environment '+key, env[key] == contract[key])
    for key, value in contract['expected_dependencies'].items():
        need(label+' actual library '+key, env[key] == value)
    need(label+' frozen loader', sources[norm(env['launch_path'])] == env['launch_sha256'])
    need(label+' baseline source hashes', all(sources[norm(k)] == v for k,v in env['baseline_sources_sha256'].items()))
    product = env['product_binding']
    need(label+' fixed product digest/count', product['source_count']==138 and product['source_sha256']=='4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6')
    need(label+' product source map frozen', all(sources[norm(k)] == v for k,v in product['installed_sources_sha256'].items()))
    need(label+' actual product modules in install', all(Path(v['path']).resolve().is_relative_to(Path(contract['product_install_root']).resolve()) for v in product['loaded_product_modules'].values()))

def cleanup_checks(clean, pid, label):
    need(label+' cleanup actual handle pid', clean['pid'] == pid)
    need(label+' bounded wait/reap/handle close', clean['wait_timeout_s']==5 and clean['reaped'] and clean['process_handle_closed'] and clean['exit_code'] is not None and not clean['errors'])
    need(label+' streams and cleanup duration', all(clean['pipes_closed'].values()) and clean['closed_ns'] >= clean['started_ns'] and clean['elapsed_ns']==clean['closed_ns']-clean['started_ns'])

def trace_checks(events, pid, start, close, label):
    need(label+' trace sequences', [v['sequence'] for v in events] == list(range(1,len(events)+1)))
    need(label+' single actual trace pid', {v['process_id'] for v in events} == {pid})
    times = [v['monotonic_ns'] for v in events]
    need(label+' monotonic within actual process', times == sorted(times) and start <= times[0] <= times[-1] <= close)
    need(label+' no forbidden old evidence trace', not any(v['event'] in ['forbidden_old_evidence_read','forbidden_old_write'] for v in events))

qsumm=[]
need('four exact qualification directories', sorted(p.name for p in (AUTHOR/'qualification').iterdir() if p.is_dir()) == ['nonzero','normal','receipt_failure','timeout'])
for aggregate in q['cases']:
    name = aggregate['scenario']
    folder=AUTHOR/'qualification'/name
    row=read(folder/'CASE.json')
    start=read(folder/'PARENT_START.json')
    env=read(folder/'ENVIRONMENT.json')
    handshake=read(folder/'HANDSHAKE.json')
    state=read(folder/'STATE.json')
    timing=read(folder/'FINAL_TIMING.json')
    events=trace(folder/'TRACE.jsonl')
    pid=start['Popen_pid']
    need(name+' aggregate equals case artifact', aggregate == row)
    need(name+' all identity sources agree', pid == row['Popen_pid'] == row['actual_pid'] == handshake['process_id'] == state['process_id'])
    need(name+' handshake actual environment bytes', handshake['environment_sha256'] == digest(folder/'ENVIRONMENT.json'))
    need(name+' exact run/folder binding', all(v['run_id']==row['run_id'] and norm(v['output_directory'])==norm(folder) for v in [handshake,state]))
    need(name+' per-case raw file hashes', all(digest(folder/k)==v for k,v in row['files_sha256'].items()))
    need(name+' single probe start', sum(e['event']=='probe_started' for e in events)==1)
    need(name+' no raster artifacts/events', not list(folder.rglob('*.png')) and not list(folder.rglob('*.npz')) and not any(e['event'].startswith('render_') for e in events))
    need(name+' handshake/cleanup/publication ordering', row['started_ns'] <= row['before_Popen_ns'] <= row['Popen_returned_ns'] <= row['handshake_confirmed_ns'] <= row['wait_boundary_ns'] <= row['cleanup']['started_ns'] <= row['cleanup']['closed_ns'] <= row['streams_closed_ns'] <= row['readback_closed_ns'] <= timing['closed_ns'])
    need(name+' parent redirected file handles closed', row['parent_files_closed'])
    need(name+' case total elapsed', timing['started_ns']==row['started_ns'] and timing['elapsed_ns']==timing['closed_ns']-timing['started_ns'])
    command_checks(row['command'],'probe.py',folder,name)
    environment_checks(env,pid,name)
    cleanup_checks(row['cleanup'],pid,name)
    trace_checks(events,pid,row['before_Popen_ns'],row['cleanup']['closed_ns'],name)
    receipt_path=folder/'RECEIPT.json'
    marker_events=[e for e in events if e['event']=='marker_written']
    if name=='normal':
        receipt=read(receipt_path)
        need('normal actual completed receipt/exit', row['cleanup']['exit_code']==0 and state['phase']=='completed' and receipt['status']=='completed' and receipt['process_id']==pid and receipt['environment_sha256']==handshake['environment_sha256'])
    elif name=='nonzero':
        need('nonzero real error/state/stderr/exit', row['cleanup']['exit_code']==1 and state['type']=='RegisteredProbeFailure' and 'RegisteredProbeFailure' in raw(folder/'stderr.bin').decode() and events[-1]['event']=='probe_failed' and not receipt_path.exists())
    elif name=='timeout':
        waiting=[e for e in events if e['event']=='waiting']
        need('timeout dependencies ready and waiting before deadline', len(waiting)==1 and handshake['phase']=='waiting' and state['phase']=='waiting' and waiting[0]['monotonic_ns'] <= row['handshake_confirmed_ns'] and row['registered_wait_deadline_ns']-row['handshake_confirmed_ns']==250000000)
        need('timeout expires then kills same held process', row['registered_wait_deadline_ns'] <= row['wait_boundary_ns'] <= row['cleanup']['started_ns'] and row['cleanup']['kill_requested'] and row['cleanup']['exit_code']==1 and not receipt_path.exists())
    else:
        marker=read(folder/'MARKER.json')
        need('action once actual marker/event/hash', marker['action_count']==1 and marker['process_id']==pid and marker['run_id']==row['run_id'] and len(marker_events)==1 and digest(folder/'MARKER.json')==marker_events[0]['marker_sha256'])
        need('marker precedes missing receipt rejection without action retry', marker['executed_ns'] <= marker_events[0]['monotonic_ns'] <= row['wait_boundary_ns'] and not receipt_path.exists() and row['cleanup']['exit_code']==0 and state['phase']=='action_executed_receipt_omitted' and row['receipt_validation']['passed'] is False and row['action_state']=='executed_once_verified')
    if name!='receipt_failure':
        need(name+' no unintended action', not marker_events and not (folder/'MARKER.json').exists())
    qsumm.append({'scenario':name,'pid':pid,'exit':row['cleanup']['exit_code'],'receipt_valid':row['receipt_validation']['passed'],'kill':row['cleanup']['kill_requested'],'cleanup_ms':row['cleanup']['elapsed_ns']/1e6,'actual_elapsed_ms':timing['elapsed_ns']/1e6,'passed_independent_evidence_checks':True})

qtime=read(AUTHOR/'qualification/FINAL_TIMING.json')
batch=read(AUTHOR/'BATCH_STARTED.json')
need('qualification finished before formal batch', qtime['closed_ns'] < result['batch_started_ns'] <= batch['started_ns'])
rows=result['rows']+result['controls']
need('formal exactly preregistered 14 ids/order', [r['id'] for r in rows]==[r['id'] for r in prereg['main']+prereg['control']] and len(rows)==14)
need('formal exactly 14 output directories', sorted(p.name for p in (AUTHOR/'runs').iterdir() if p.is_dir()) == sorted(r['id'] for r in rows))
fsumm=[]
previous= batch['started_ns']
for row in rows:
    name=row['id']; folder=AUTHOR/'runs'/name
    child=read(folder/'RESULT.json'); pub=read(folder/'RESULT_PUBLICATION.json'); events=trace(folder/'TRACE.jsonl')
    pid=row['process_id']
    command_checks(row['command'],'runtime.py',folder,name)
    environment_checks(child['launch_environment'],pid,name)
    cleanup_checks(row['cleanup'],pid,name)
    need(name+' PID actual runtime equals held Popen', child['process_id']==pid and row['facts']['launch_environment']==child['launch_environment'])
    need(name+' only exact requested slot', child['arm']==row['arm'] and child['scenario']==row['scenario'] and norm(child['output_directory'])==norm(folder))
    need(name+' success independently raw exit/publication/trace', row['returncode']==row['cleanup']['exit_code']==0 and child['status']=='completed' and not child['exceptions'] and events[0]['event']=='runtime_start' and events[-1]['event']=='process_complete')
    need(name+' publication content hash', pub['RESULT_sha256']==digest(folder/'RESULT.json')==events[-1]['RESULT_sha256'] and pub['RESULT_bytes']==len(raw(folder/'RESULT.json')))
    need(name+' exact timing ordering across parent/child/cleanup', previous <= row['started_ns'] <= child['started_ns'] <= child['work_closed_ns'] <= pub['started_ns'] <= pub['closed_ns'] <= events[-1]['monotonic_ns'] <= row['process_exited_ns'] <= row['cleanup']['started_ns'] <= row['cleanup']['closed_ns'] <= row['cleanup_exited_ns'] <= row['closed_ns'])
    need(name+' elapsed accounting and no kill', row['elapsed_ns']==row['closed_ns']-row['started_ns'] and not row['cleanup']['kill_requested'])
    trace_checks(events,pid,child['started_ns'],row['process_exited_ns'],name)
    need(name+' stdout stderr exact hashes/length', all(digest(folder/file)==row[field+'_sha256'] and len(raw(folder/file))==row[field+'_bytes'] for file,field in [('STDOUT.bin','stdout'),('STDERR.bin','stderr')]))
    need(name+' child used frozen input hashes', all(sources[norm(k)]==v for k,v in child['inputs_sha256'].items()))
    need(name+' actual dependency binding frozen', child['dependencies']==read(AUTHOR/'inputs/DEPENDENCIES.json'))
    fsumm.append({'id':name,'actual_pid':pid,'exit':row['returncode'],'cleanup_ms':row['cleanup']['elapsed_ns']/1e6,'raw_trace_events':len(events),'passed_independent_evidence_checks':True})
    previous=row['closed_ns']

old=read(AUTHOR.parent/'m4_active_coverage_002/RESULTS.json')
old_entered=[r for r in old['rows'] if r['status']!='not_run']
need('old 002 failure remains', len(old_entered)==1 and old_entered[0]['status']=='failed' and sum(r['status']=='not_run' for r in old['rows'])==11)
oldchild=read(Path(old_entered[0]['output_directory'])/'RESULT.json')
need('old mismatched Popen/runtime PID remains observable', old_entered[0]['process_id']==23456 and oldchild['process_id']==20368)

summary={'review_kind':'independent offline raw-evidence and source semantics audit; no author code import/run', 'author_commit':'f2b9dc01621d5b7adb330c096b6460eb3be9c552', 'all_checks_passed':all(c['passed'] for c in CHECKS), 'checks':CHECKS,'qualification':qsumm,'formal':fsumm,'new_probe_engine_raster_Blender_model_API_runs':0,'historical_002':{'status':'failed preserved','Popen_pid':23456,'runtime_pid':20368,'historical_parent_child_lineage':'unmeasured; not retrospectively repaired'},'limits':['No independent execution of probes or formal workload in this review.','Current evidence proves the frozen launch graph and observed same-process identity for these 18 invocations; not arbitrary subprocess trees.','No OS-level independent historical handle telemetry; cleanup conclusion combines stored runtime records with inspected Popen wait/kill/Close code.','Dependency submodule/native extension byte attestation and runtime bytecode cache adversarial tests were not part of this launch qualification.']}
(OUT/'RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUTS_SHA256.json').write_text(json.dumps(INPUTS,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'all_checks_passed':summary['all_checks_passed'],'checks':len(CHECKS),'qualification':qsumm,'formal_runs':len(fsumm),'read_files':len(INPUTS),'new_runs':0},ensure_ascii=False))
