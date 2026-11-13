"""Bounded independent reader probes; AST functions only, no whole author checker."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TREE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
BATCH = TREE / 'verification/m4_surface_scan_continuity_001_fix1'
CELL = BATCH / 'episodes/C'
PRIOR = TREE / 'verification/m4_surface_scan_compact_facts_001/engineering/run_01'
HOST_SHA = '9a63545aec488cead3be508f97afefc9fa7135beb82e85cff10ca7ad4d3b59e9'
inputs, checks = {}, []
def digest(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()
def require(condition, reason):
    if not condition: raise AssertionError(reason)
def read(path):
    raw = path.read_bytes()
    inputs[str(path)] = {'sha256': digest(raw), 'bytes': len(raw)}
    return raw
def load(path): return json.loads(read(path))
def extracted(path, names, namespace):
    nodes = [n for n in ast.parse(read(path).decode('utf-8-sig')).body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace
def check(label, ok, **details): checks.append({'label': label, 'passed': bool(ok), **details})

base = {'json': json, 'Path': Path, 'require': require, 'canonical': canonical, 'digest': digest, 'HOST_SOURCE_SHA': HOST_SHA}
old = extracted(BATCH / 'qualification/verify_continuity.py', {'read_capture'}, dict(base))['read_capture']
newns = extracted(BATCH / 'postrun/capture_phase/read_capture_candidate.py', {'logical_bytes', 'read_capture'},
    {**base, 'qualification': SimpleNamespace(require=require, canonical=canonical, digest=digest, HOST_SOURCE_SHA=HOST_SHA)})
new, logical = newns['read_capture'], newns['logical_bytes']
runner = extracted(BATCH / 'engineering/run_candidate.py', {'verify_business'}, {'json': json})['verify_business']
read(BATCH / 'postrun/capture_phase/MINIMAL_READER.diff')
worker = TREE / 'verification/m4_surface_scan_001_opt1/engineering/pose_native_metered.py'
worker_source = read(worker).decode('utf8')
read(worker.with_name('wire_meter.py'))
config = load(CELL / 'owner/native/CONFIG.json')
check('actual_fixed_worker_source', digest(worker_source.encode()) == config['helper_sha256'])
order_tokens = ["call/'SCRIPT.py'", "call/'stdout.txt'", 'event.update(script_sha256', "event['elapsed_ns']=", 'connection.sendall(wire)', 'meter.flush(workspace)']
order = {token: next(i for i,line in enumerate(worker_source.splitlines(),1) if token in line) for token in order_tokens}
check('worker_publish_order', list(order.values()) == sorted(order.values()), line_numbers=order)

fixrow = load(CELL / 'TURN_BASE.json')
prior_rows = load(PRIOR / 'RESULTS.json')['business']
cases = [('FIX1_BASE', CELL / 'owner/native', fixrow, load(CELL / 'owner/INITIAL.json'))]
for label, state in [('base_brief','base'), ('edit_default','edit')]:
    row = next(r for r in prior_rows if r['state'] == label)
    cases.append(('HISTORICAL_' + label, PRIOR / 'native', row, load(PRIOR / (state + '_ACTUAL_SNAPSHOT.json'))))

summaries = []
for label, workspace, row, source in cases:
    all_events = [json.loads(line) for line in read(workspace / 'WORKER_EVENTS.jsonl').splitlines()]
    relevant = [e for e in all_events if row['started_ns'] <= e.get('started_ns', -1) <= row['ended_ns']]
    assert len(relevant) == 1
    event, target = relevant[0], relevant[0]['sequence']
    event_prefix = b''.join(canonical(e) + b'\n' for e in all_events if type(e.get('sequence')) is int and e['sequence'] <= target)
    available = {workspace / 'WORKER_EVENTS.jsonl': event_prefix}
    for e in all_events:
        if type(e.get('sequence')) is int and e['sequence'] <= target and 'script_sha256' in e:
            for name in ['SCRIPT.py','stdout.txt','stderr.txt']:
                p = workspace / ('call_' + str(e['sequence'])) / name
                available[p] = read(p)
    accessed, denied = [], []
    def restricted(path):
        accessed.append(str(path))
        if path not in available:
            denied.append(str(path))
            raise FileNotFoundError('not published in this phase: ' + str(path))
        return available[path]
    with patch.object(Path, 'read_bytes', restricted):
        captured = new(workspace, event)
        try:
            old(workspace, event)
            old_failed = False
        except FileNotFoundError:
            old_failed = True
    check(label + ':candidate_no_future_or_terminal_inputs', all('WIRE' not in p and 'FINAL' not in p and 'CLOSED' not in p for p in accessed[:-1]) and len(denied) == 1)
    check(label + ':old_online_reader_requires_unpublished_WIRE', old_failed and denied[0].endswith('INDEX.json'))
    retained = {(r['id'], r['revision']):r for r in captured['retained_resources']}
    projected = []
    for mesh in captured['delta']['capture']['capture']['meshes']:
        ref = mesh['_scene_resource']; resource = retained[(ref['id'],ref['revision'])]
        projected.append({'name':mesh['name'], 'vertices_local':resource['vertices_local'], 'faces':resource['faces'], 'matrix_world':ref['matrix']})
    check(label + ':current_pose_and_prior_resources_match_source', canonical({'unit_scale_m':captured['delta']['capture']['binding']['scale_length'], 'objects':sorted(projected,key=lambda r:r['name'])}) == canonical({'unit_scale_m':source['unit_scale_m'],'objects':[{k:r[k] for k in ['name','vertices_local','faces','matrix_world']} for r in source['objects']]}))
    # Separate post-close read. Only prefix wire files are opened by the old reader.
    index = load(workspace / 'WIRE/INDEX.json')
    closed_files = {workspace / 'WIRE/INDEX.json': canonical(index)}
    for item in index:
        if item['sequence'] <= target:
            for name in ['REQUEST.bin','RESPONSE.bin']:
                path = workspace / 'WIRE' / str(item['sequence']).zfill(3) / name
                closed_files[path] = read(path)
    closed_access = []
    def closed_read(path):
        closed_access.append(str(path))
        return closed_files[path]
    with patch.object(Path,'read_bytes',closed_read): archived = old(workspace,event)
    check(label + ':postclose_original_reader_equivalent', all(canonical(archived[k]) == canonical(captured[k]) for k in ['sequence','script_sha256','delta','retained_resources','resource_origins']))
    check(label + ':postclose_no_future_WIRE_file', all(p in [str(k) for k in closed_files] for p in closed_access))
    summaries.append({'label':label, 'sequence':target, 'current_resources':len(captured['delta']['resources']), 'retained_resources':len(captured['retained_resources']), 'origins':sorted({r['sequence'] for r in captured['resource_origins']})})
    if label == 'FIX1_BASE':
        audit_path = CELL / 'owner/audit.jsonl'
        available[audit_path] = read(audit_path)
        seen = []
        def independent_callback(body,audit,host,snapshot,turn,request,*,capture):
            seen.append(capture)
            require(canonical(capture)==canonical(captured),'same_actual_runner_capture')
            require(snapshot==source and turn=='BASE','actual_runner_source_and_turn')
            binding=capture['delta']['capture']['binding']
            require(binding['host_source_sha256']==body['binding']['host_source_sha256']==HOST_SHA,'host_origin')
            require(binding['directory_sha256']==body['binding']['directory_sha256'],'directory_binding')
            require(binding['host_identity']['document_epoch']==body['binding']['document_epoch'],'document_binding')
            return {'plumbing_and_binding':True}
        with patch.object(Path,'read_bytes',restricted):
            output=runner(copy.deepcopy(row),CELL,source,SimpleNamespace(read_capture=new,verify_c_turn=independent_callback))
        check('actual_runner_online_path_uses_candidate_with_no_terminal_inputs', output=={'plumbing_and_binding':True} and len(seen)==1)
        # Diagnose a late audit suffix separately; not a state present in the sequential runner.
        original_prefix=available[workspace/'WORKER_EVENTS.jsonl']
        available[workspace/'WORKER_EVENTS.jsonl']=original_prefix+b'{"sequence":999'
        with patch.object(Path,'read_bytes',restricted):
            try: new(workspace,event); future_error=False
            except json.JSONDecodeError: future_error=True
        check('candidate_parses_future_incomplete_event_suffix', future_error, interpretation='Known suffix dependency in retrospective/concurrent use; sequential current runner has no future writer during qualification.')

lf=b'one\ntwo\n'; crlf=b'one\r\ntwo\r\n'
check('logical_exact_CRLF_reconstruction', logical(crlf,expected_size=len(lf))==lf)
check('logical_exact_script_SHA_reconstruction', logical(crlf,expected_sha=digest(lf))==lf)
for label,raw,size in [('no_trim',b'one\n ',4),('no_lone_CR_conversion',b'one\r',3),('missing_size_match',crlf,999)]:
    try: logical(raw,expected_size=size); rejected=False
    except AssertionError: rejected=True
    check(label,rejected)
check('length_is_not_content_authentication', logical(b'two\n',expected_size=4)==b'two\n', interpretation='Only newline/size reconstruction; source facts and final transport evidence remain separate checks.')
original=load(CELL/'RESULTS.json')
check('original_failure_counts_unchanged',original['execution_counts']=={'planned':3,'attempted':1,'completed':0,'failed':1,'not_run':2} and original['passed_before_publication'] is False)
results={'scope':'AST-only candidate/old reader and actual runner glue; independent source projection/binding probes, not full author quality checks or live acceptance.',
 'parent_task':'68dc02bb-4913-406a-bf20-63b873071fac','parent_revision':1,'parent_write':622,
 'own_AL_assignment':'old child assignment remains stale; no parent handle borrowed',
 'summary':{'checks':len(checks),'passed':sum(r['passed'] for r in checks),'failed':sum(not r['passed'] for r in checks)},
 'cases':summaries,'checks':checks}
(OUT/'RESULTS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUT_SHA256.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(results['summary']))
for item in checks:
    if not item['passed']: print(json.dumps(item))
