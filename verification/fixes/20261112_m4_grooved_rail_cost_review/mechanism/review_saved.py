"""Independent offline audit. Stdlib only; no product imports or business execution.

Only reads the fixed evidence tree/Git objects and writes beside this script.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import subprocess

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = ROOT / 'verification/m4_grooved_rail_consumption_001'
OUT = Path(__file__).resolve().parent
PRODUCT = 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
ORIGINAL = '4a90bbe95ef46c6666050ef1a1096fc6719c3b97'
HEAD = 'ea70339772159e5f0279784ebe18b1bf16e70439'
seen = {}

def raw(path, role='parsed_evidence'):
    path = Path(path)
    data = path.read_bytes()
    key = path.as_posix()
    entry = seen.setdefault(key, {'path': key, 'bytes': len(data),
        'sha256': hashlib.sha256(data).hexdigest(), 'roles': []})
    if role not in entry['roles']:
        entry['roles'].append(role)
    return data

def text(path, role='parsed_evidence'):
    return raw(path, role).decode('utf-8-sig')

def js(path, role='parsed_evidence'):
    return json.loads(text(path, role))

def lines(path):
    return [json.loads(line) for line in text(path).splitlines() if line.strip()]

def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

def git(*args, input=None):
    return subprocess.run(['git', '--no-optional-locks', '-C', str(ROOT), *args],
        input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout

def batch_objects(specs):
    data = git('cat-file', '--batch', input=('\n'.join(specs)+'\n').encode())
    at = 0
    blobs = []
    for spec in specs:
        end = data.index(b'\n', at)
        hdr = data[at:end].decode().split()
        assert hdr[1] == 'blob', (spec, hdr)
        length = int(hdr[2]); at = end+1
        blobs.append((hdr[0], data[at:at+length])); at += length+1
    assert at == len(data)
    return blobs

plan = js(BATCH/'PLAN.json')
sequence = js(BATCH/'SEQUENCE.json')['sequence']
contract = js(BATCH/'MECHANISM_CLASSIFICATION.json')
prompt = raw(BATCH/'input/PROMPT.txt')
binding = js(BATCH/'preflight/SOURCE_BINDING.json')
original_index = js(BATCH/'cost_review_01/ORIGINAL_DATA_INDEX.json')
assert git('rev-parse', 'HEAD').decode().strip() == HEAD

# Full 137-file identity verification; semantic review is separately scoped.
source_records = []
specs = [PRODUCT+':'+r['path'] for r in binding['source_manifest']]
for expected, (blob_id, blob) in zip(binding['source_manifest'], batch_objects(specs)):
    data = raw(ROOT/expected['path'], 'product_source_identity_only')
    actual = hashlib.sha256(data).hexdigest()
    source_records.append({'path': expected['path'], 'sha256': actual,
        'expected_sha256': expected['sha256'], 'git_blob': blob_id,
        'matches_manifest': actual == expected['sha256'], 'matches_fixed_product_blob': data == blob})
assert len(source_records) == 137 and all(x['matches_manifest'] and x['matches_fixed_product_blob'] for x in source_records)

semantic_sources = ['human_eye_plugin/task_query.py', 'human_eye_plugin/surface_proximity.py',
    'human_eye_plugin/surface_geometry.py',
    'verification/m4_grooved_rail_consumption_001/runtime/actor.py',
    'verification/m4_grooved_rail_consumption_001/runtime/consumer_transport.py',
    'verification/native_plugin_complex_003/reused/accepted_native.py']
for rel in semantic_sources:
    text(ROOT/rel, 'source_semantic_review')
for rel in ['schemas/P_CONSUMER_TOOLS.json','schemas/P_PUBLIC_TOOLS.json','schemas/N_CONSUMER_TOOLS.json']:
    js(BATCH/rel)

steps, cells, pair_rows, trace_rows, worker_rows = [], [], [], [], []
for slot in sequence:
    cell = slot['cell']; group = slot['group']; folder = BATCH/'cells'/cell
    consumer = js(folder/'CONSUMER.json')
    final = text(folder/'PUBLIC_FINAL.txt')
    owner_tools = js(folder/'owner/TOOLS.json')
    close = js(folder/'owner/CLOSE.json')
    assert close['native_close']['response']['status'] == 'closed'
    worker = lines(folder/'owner/native/WORKER_EVENTS.jsonl')
    worker_rows.extend(dict(cell=cell, **row) for row in worker)
    assert consumer['input_sha256'] == hashlib.sha256(prompt).hexdigest()
    assert consumer['final'] == final
    tool_dirs = sorted((folder/'owner').glob('tool_*'))
    assert len(tool_dirs) == len(consumer['tool_calls']) == owner_tools['attempts']
    audit = lines(folder/'owner/audit.jsonl') if group == 'P' else []
    rpc = js(folder/'owner/plugin/RPC.json') if group == 'P' else None
    for ev in audit:
        if ev.get('event') == 'request_trace':
            trace_rows.append(dict(cell=cell, trace=ev['trace']))
    cell_steps = []
    for n, (directory, call) in enumerate(zip(tool_dirs, consumer['tool_calls']), 1):
        request = js(directory/'REQUEST.json')
        response = js(directory/'RESPONSE.json')
        attempt = js(directory/'ATTEMPT.json')
        args = request['params']['arguments']
        assert call['item']['arguments'] == args
        assert call['item']['tool'] == request['params']['name']
        assert call['item']['result']['content'] == response['result']['content']
        blocks = [json.loads(x['text']) for x in response['result']['content'] if x.get('type') == 'text']
        assert len(blocks) == 1
        body = blocks[0]
        assert len(compact(response))+1 == attempt['response_bytes']
        hosts = [w for w in worker if 'script_sha256' in w and
            attempt['started_ns'] <= w['started_ns'] < attempt['started_ns']+attempt['elapsed_ns']]
        primary = 'directory_or_identity' if group == 'N' and n == 1 else 'new_information_attempt'
        refined = ('contract_rejection_no_geometry_executed' if body.get('executed') is False else
            'directory_or_identity' if primary == 'directory_or_identity' else
            'new_geometry_or_first_solve')
        row = {'cell': cell, 'step': n, 'group': group, 'tool': request['params']['name'],
            'request_path': (directory/'REQUEST.json').as_posix(),
            'response_path': (directory/'RESPONSE.json').as_posix(),
            'arguments': args, 'business_response': body,
            'classification_attempt_intent': primary, 'classification_observed_result': refined,
            'handler_ns': attempt['elapsed_ns'], 'response_wire_bytes': attempt['response_bytes'],
            'host_execution_count': len(hosts), 'host_executions': hosts,
            'source_consumer_call_matched': True}
        steps.append(row); cell_steps.append(row)
        if group == 'P' and body.get('status') == 'observed':
            observations = [e for e in audit if e.get('event') == 'observe' and 'task_work' in e]
            assert len(observations) == 1
            work = observations[0]['task_work']
            names = {v['object_id']:v['name'] for v in body['binding']['objects']}
            for result, measure in zip(body['pairs'], work['pairs']):
                assert result['object_id'] == measure['object_id']
                name = names[result['object_id']]
                facts = result['facts']; proximity = facts['surface_proximity']
                witness = proximity['value']['nearest_witness']
                required_tokens = [format(proximity['value']['distance_m']*1000,'.6f')]
                required_tokens += [format(v,'.9f') for side in ('a','b') for v in witness[side]]
                assert all(token in final for token in required_tokens)
                assert all(facts[f]['status']=='measured' for f in ('spatial_relation','surface_proximity','closed_solid_relation'))
                assert facts['spatial_relation']['value'] == facts['closed_solid_relation']['value'] == 'separated'
                pair_rows.append({'cell': cell,'candidate': name,'facts': facts,
                    'work': measure,'final_numeric_tokens_found':required_tokens,
                    'closed_purpose':'necessary_spatial_fallback' if facts['spatial_relation']['method']=='bounded_exact_closed_shell_v1'
                        else 'additional_explicit_closed_classification'})
            assert all(not v for k,v in work.items() if 'cache_hit' in k)
    cells.append({'cell':cell,'group':group,'attempts':len(cell_steps),
        'consumer_native_calls':sum(s['tool']=='execute_blender_code' for s in cell_steps),
        'input_matches_frozen_prompt':True,'final_matches_consumer':True,
        'public_messages':consumer['all_public_messages'],'final':final,
        'worker_event_count':len(worker),'host_script_execution_count':sum('script_sha256' in w for w in worker),
        'nonexecution_worker_events':[w for w in worker if 'script_sha256' not in w]})

assert len(steps)==13 and len(pair_rows)==9
extra=[r for r in pair_rows if r['closed_purpose']=='additional_explicit_closed_classification']
needed=[r for r in pair_rows if r['closed_purpose']=='necessary_spatial_fallback']
aggregate=lambda rows,field:sum(r['work']['closed_solid_work'][field] for r in rows)
assert len(extra)==6 and aggregate(extra,'work_units')==15276 and aggregate(extra,'world_tree_builds')==12
assert aggregate(needed,'work_units')==7854 and aggregate(needed,'world_tree_builds')==6
assert all(r['work']['closed_solid_pair_count']==1 and
           r['work']['closed_solid_work']['prepared_pair_reused'] and
           not r['work']['closed_solid_work']['prepared_trees_reused'] and
           r['work']['surface_work']['tree_builds']==0 for r in pair_rows)

invalid=next(s for s in steps if s['cell']=='grc03' and s['step']==1)
assert invalid['business_response']['tool_outcome']=='unknown'
assert invalid['business_response']['execution_status']=='not_executed'
assert invalid['host_execution_count']==0
invalid_attempt=js(BATCH/'cells/grc03/owner/tool_01/ATTEMPT.json')
corrected_attempt=js(BATCH/'cells/grc03/owner/tool_02/ATTEMPT.json')
invalid_gap_ns=corrected_attempt['started_ns']-invalid_attempt['started_ns']-invalid_attempt['elapsed_ns']

# Read stored host scripts as text only; tie transcript code and native stdout to the saved record.
native_files=0
for slot in sequence:
    for p in sorted((BATCH/'cells'/slot['cell']/'owner/native').glob('call_*/*')):
        if p.name in ('SCRIPT.py','stdout.txt','stderr.txt'):
            text(p, 'saved_native_text_no_execution'); native_files+=1

# Compare sampled original evidence directly with its immutable original Git blobs.
index_by_path={r['path']:r for r in original_index['original_batch_files']}
selected=[]
for record in list(seen.values()):
    p=Path(record['path'])
    try:rel=p.relative_to(ROOT).as_posix()
    except ValueError:continue
    if rel in index_by_path: selected.append((rel,record))
checked_original=[]
for (rel,record),(oid,data) in zip(selected,batch_objects([ORIGINAL+':'+rel for rel,_ in selected])):
    expected=index_by_path[rel]
    checked_original.append({'path':rel,'sha256':record['sha256'],'git_blob':oid,
        'matches_index':record['sha256']==expected['sha256'],
        'matches_original_blob':record['sha256']==hashlib.sha256(data).hexdigest()})
assert all(r['matches_index'] and r['matches_original_blob'] for r in checked_original)

# Author's post-seal conclusions are comparison targets, never inputs to calculation.
author=js(BATCH/'cost_review_01/mechanism/RESULTS.json','author_comparison_only')
text(BATCH/'cost_review_01/mechanism/REPORT.md','author_comparison_only')

result={
 'schema':'independent-saved-mechanism-review-v1',
 'scope':'No product imports, consumer runs, Blender runs, API calls, Git writes, or implementation-tree writes.',
 'identity':{'head':HEAD,'original_evidence_commit':ORIGINAL,'product_commit':PRODUCT,
    'runtime_source_sha256':binding['source_sha256'],'source_count':len(source_records)},
 'denominator':{'cells':len(cells),'consumer_requests_and_responses':len(steps),
    'P_successful_task_requests':3,'P_rejected_requests':1,'P_fact_pairs':len(pair_rows),
    'P_audit_files':3,'P_request_traces_including_startup':len(trace_rows),
    'native_script_stdout_stderr_files_read':native_files,'source_files_identity_checked':len(source_records),
    'source_files_semantically_read':semantic_sources,'original_selected_files_git_verified':len(checked_original),
    'original_total_inventory':len(index_by_path),'all_914_semantically_read':False},
 'source_identity':source_records,'selected_original_identity':checked_original,
 'steps':steps,'cells':cells,'P_pair_mechanisms':pair_rows,'request_traces':trace_rows,
 'classification':{'attempt_intent_counts':dict(Counter(s['classification_attempt_intent'] for s in steps)),
    'observed_result_counts':dict(Counter(s['classification_observed_result'] for s in steps)),
    'already_complete_facts_native_recompute':0,'standalone_unknown_geometry_verification':0,
    'author_counts':author['classification_counts_primary'],
    'qualification':'3 directory + 10 new-information is defensible as attempt purpose only; observed geometry-success count is 9 plus one contract rejection. Zero native recompute does not imply zero redundant internal work.'},
 'aggregates':{'extra_BC_closed_calls':len(extra),'extra_BC_closed_work_units':aggregate(extra,'work_units'),
    'extra_BC_world_tree_builds':aggregate(extra,'world_tree_builds'),
    'required_A_closed_calls':len(needed),'required_A_closed_work_units':aggregate(needed,'work_units'),
    'required_A_world_tree_builds':aggregate(needed,'world_tree_builds'),
    'all_closed_work_units':aggregate(pair_rows,'work_units'),
    'surface_work_units_including_support':sum(r['work']['surface_work']['work_units'] for r in pair_rows),
    'support_work_units_already_in_surface':sum(r['work']['support_work']['work_units_after']-r['work']['support_work']['work_units_before'] for r in pair_rows),
    'P_consumer_native_calls':0,'business_host_executions':sum(s['host_execution_count'] for s in steps),
    'all_saved_host_script_executions':sum('script_sha256' in r for r in worker_rows),
    'qa_host_script_executions':sum('script_sha256' in r for r in worker_rows)-sum(s['host_execution_count'] for s in steps),
    'worker_close_events_not_script_executions':sum('script_sha256' not in r for r in worker_rows)},
 'invalid_nearest_witness':{'cell':'grc03','step':1,'response':invalid['business_response'],
    'handler_ns':invalid['handler_ns'],'response_wire_bytes':invalid['response_wire_bytes'],
    'host_executions':0,'gap_until_corrected_request_ns':invalid_gap_ns,
    'gap_causal_attribution':'unmeasured'},
 'precision_refresh':{'cell':'grc04','step':3,'meshes_reread':4,'vertices_reread':26,'triangles_reread':36,
    'occurs_before_first_distance_answer':True,'prior_complete_geometry_answer':False,
    'unmeasured':['necessity for frozen precision','isolated reread latency','effect of deleting old acquisition']},
 'findings':[
    'P 3/3 naturally selected spatial_relation and surface_proximity under the ordinary schema and frozen task; all requested explicit closed_solid_relation too.',
    'Natural selection is scoped to the ordinary interface: its description explicitly recommends spatial_relation plus surface_proximity, while its example uses closed_solid_relation plus surface_proximity. This is not unguided field discovery.',
    'nearest_witness appears in the general requested_facts enum but is excluded by task-set validation; the failed request is an interface-contract mistake, not unknown geometry evidence.',
    'Final numeric facts match delivered engine facts; identical spatial/closed values prevent identifying which relation field the model used.',
    'A support proposal fails strict all-vertex separation; bounded closed-shell fallback is required for this implementation, and explicit closed output reuses bundle.closed.',
    'B/C support certificates are already sufficient for requested separation; explicit closed adds six classifications. Removing that fact has a statically identifiable skip path, not measured task savings.',
    'Prepared pair reuse concerns query-local geometry preparation; surface linear loop at 24*4=96<=256 creates no distance trees. Closed classifier builds two world trees each; cache hits are all false/zero.',
    'Work-unit aggregates reproduce recorded counters, not independent rerun arithmetic, CPU instruction counts, or monetary cost.',
    'Request tracing has inclusive task_facts spans but no isolated closed duration. Do not add nested spans or estimate closed latency from work-unit share.',
    'Stop tuning this fixed three-pair question. Next evidence should test discovery without preselected objects, coverage and stopping, unknown handling, and complete costs.'
 ],
 'limitations':['No ablation or new geometry execution was authorized or performed.',
    'Full quality assessment remains the already sealed review and is not reissued here.',
    'Only this one four-object, 26-vertex, 36-triangle scene and its three supplied candidates support these mechanism observations.',
    'No proof of which equal relation field was attended to, of token attribution, or of causal latency/cost savings from omitting fields.'],
 'new_runs':{'product':0,'Blender':0,'consumer':0,'API':0},
}
result['denominator']['unique_input_files_read']=len(seen)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'SOURCES.json').write_text(json.dumps({'scope':'Actual reads; identity-only source reads distinguished from semantic reads',
    'files':sorted(seen.values(),key=lambda r:r['path']),
    'review_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'denominator':result['denominator'],'aggregates':result['aggregates'],
    'classification':result['classification'],'invalid_gap_ns':invalid_gap_ns},ensure_ascii=False,indent=2))
