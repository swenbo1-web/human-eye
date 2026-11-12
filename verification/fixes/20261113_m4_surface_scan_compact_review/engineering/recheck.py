"""Independent offline review of five sealed COMPACT-FACTS-001 observations.

Uses stdlib only. Does not import candidate/author verifier, launch Blender, or call models.
Geometry oracle is reused, hash-bound prior exact qualification, cross-checked against
the prior root's independent rational recomputation. Surface witness checks below are new.
"""
from __future__ import annotations
import ast
import collections
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct
import subprocess
from fractions import Fraction

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT = Path(__file__).resolve().parent
BATCH = ROOT / 'verification/m4_surface_scan_compact_facts_001'
RUN = BATCH / 'engineering/run_01'
OLD = ROOT / 'verification/m4_surface_scan_001'
DELIVERY = '6ab4e53409e539c71a377f48708f2f8725db6dde'
PRODUCT = '452b44d2dcf231d6675bef54e568db0431a29261'
SOURCE = '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6'
CHECKS = []
INPUTS = {}

def ck(label, value, detail=None):
    CHECKS.append({'check': label, 'passed': bool(value), 'detail': detail})

def git_map(root, commit, paths):
    data = subprocess.check_output(['git', 'ls-tree', '-r', '-z', commit, '--', *paths], cwd=root)
    return {record.split(b'\t', 1)[1].decode(): record.split(b'\t', 1)[0].split()[2].decode()
            for record in data.split(b'\0') if record}

TREE = git_map(ROOT, DELIVERY, ['verification/m4_surface_scan_compact_facts_001',
                               'verification/m4_surface_scan_001',
                               'verification/m4_surface_scan_consumption_001/cells/P1/owner/tool_01/RESPONSE.json'])
MANIFEST = json.loads((BATCH/'DELIVERY_MANIFEST.json').read_text('utf-8-sig'))
MF = {x['path']: x for x in MANIFEST['files']}

def raw(path):
    path = Path(path)
    data = path.read_bytes()
    key = str(path)
    if key not in INPUTS:
        h = hashlib.sha256(data).hexdigest()
        record = {'sha256': h, 'bytes': len(data)}
        if path.is_relative_to(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            actual_blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            record.update(git_commit=DELIVERY, git_blob=TREE.get(relative), actual_blob=actual_blob)
            ck('git_binding:'+relative, actual_blob == TREE.get(relative))
        if path.is_relative_to(BATCH) and path != BATCH/'DELIVERY_MANIFEST.json':
            relative = path.relative_to(BATCH).as_posix()
            record['manifest'] = MF.get(relative)
            ck('manifest_binding:'+relative, relative in MF and MF[relative]['sha256']==h and MF[relative]['bytes']==len(data))
        INPUTS[key] = record
    return data

def read(path):
    return json.loads(raw(path).decode('utf-8-sig'))

def lines(path):
    return [json.loads(x) for x in raw(path).decode('utf-8-sig').splitlines() if x]

def bits(x):
    return struct.pack('>d', x).hex()

def bit_tree(x):
    if isinstance(x, float): return ('binary64', bits(x))
    if isinstance(x, list): return [bit_tree(y) for y in x]
    if isinstance(x, dict): return {k: bit_tree(v) for k,v in x.items()}
    return x

def equal(a,b):
    return bit_tree(a)==bit_tree(b)

def without(x, keys): return {k:v for k,v in x.items() if k not in keys}

def rational(x): return Fraction(int(x['numerator']), int(x['denominator']))

def vsub(a,b): return [x-y for x,y in zip(a,b)]
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def norm2(a): return dot(a,a)
def segment_d2(p,a,b):
    d = vsub(b,a)
    den = norm2(d)
    t = min(1.0,max(0.0,dot(vsub(p,a),d)/den)) if den else 0.0
    return norm2(vsub(p,[a[i]+t*d[i] for i in range(3)]))

def triangle_d2(p,a,b,c):
    """Independent point-to-triangle plane projection plus three segment minima."""
    u,v,w = vsub(b,a),vsub(c,a),vsub(p,a)
    uu,vv,uv,wu,wv = dot(u,u),dot(v,v),dot(u,v),dot(w,u),dot(w,v)
    den = uu*vv-uv*uv
    best = min(segment_d2(p,a,b),segment_d2(p,b,c),segment_d2(p,c,a))
    if den > 0:
        s,t = (wu*vv-wv*uv)/den,(wv*uu-wu*uv)/den
        if s >= 0 and t >= 0 and s+t <= 1:
            best = min(best,norm2(vsub(p,[a[i]+s*u[i]+t*v[i] for i in range(3)])))
    return best

def decode_compact(body, label):
    cols = body['match_columns']
    ck(label+':six_explicit_columns', cols == ['object_a','object_b','object_a_ref','object_b_ref','distance_m','distance_mm'])
    ck(label+':encoding_scope', body['display_encoding']=='surface-scan-task-table-v1' and body['object_table_scope']=='matched_endpoints_only')
    objs = body['objects']
    ck(label+':table_unique_ids', len({x['id'] for x in objs})==len(objs)==22)
    exceptions = {x['index']:x['fields'] for x in body['match_exceptions']}
    ck(label+':actual_no_row_exceptions', not exceptions)
    restored = []
    references = set()
    for i,row in enumerate(body['matches']):
        ck(f'{label}:row{i}:width',len(row)==len(cols))
        fields = dict(zip(cols,row))
        ar,br = fields['object_a_ref'],fields['object_b_ref']
        ck(f'{label}:row{i}:valid_indices',type(ar) is int and type(br) is int and 0<=ar<len(objs) and 0<=br<len(objs))
        ao,bo = objs[ar],objs[br]
        references.update((ar,br))
        ck(f'{label}:row{i}:readable_names',fields['object_a']==ao['name'] and fields['object_b']==bo['name'])
        d = fields['distance_m']
        ck(f'{label}:row{i}:mm_derived_no_rounding',bits(fields['distance_mm'])==bits(d*1000.0))
        restored.append(dict(body['match_metadata'],**exceptions.get(i,{}),objects=[ao,bo],distance_m=d))
    ck(label+':no_unused_table_entries', references==set(range(len(objs))))
    return restored

def main():
    raw(BATCH/'DELIVERY_MANIFEST.json')
    ck('manifest_candidate', MANIFEST['candidate_commit']==PRODUCT and MANIFEST['source_sha256']==SOURCE)
    root_oracle_path = Path('D:/hefe/verification/fixes/20261112_m4_surface_scan_initial_review/quality/ORACLE_RECOMPUTE.json')
    root_oracle = read(root_oracle_path)
    prior_root_commit='dd11f1aa97ad0bf8bb314a86cd91b32ff0123874'
    rel=root_oracle_path.relative_to(Path('D:/hefe')).as_posix()
    expected_blob=git_map(Path('D:/hefe'),prior_root_commit,[rel])[rel]
    rb=raw(root_oracle_path)
    ck('prior_independent_oracle_fixed_git', hashlib.sha1(b'blob '+str(len(rb)).encode()+b'\0'+rb).hexdigest()==expected_blob)
    INPUTS[str(root_oracle_path)].update(git_commit=prior_root_commit,git_blob=expected_blob)
    known_hashes={
        'BASE_SNAPSHOT.json':'f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b',
        'BASE_TRUTH.json':'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7',
        'EDIT_SNAPSHOT.json':'beb4e441b1898c6aedbe633828b1a93948f1d5be172ded9e1a884c8bdebffd80',
        'EDIT_TRUTH.json':'ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91'}
    truth, snapshots = {},{}
    for state in ['BASE','EDIT']:
        td=read(OLD/'qualification'/f'{state}_TRUTH.json')
        snap=read(OLD/'qualification'/f'{state}_SNAPSHOT.json')
        for suffix in ['TRUTH','SNAPSHOT']:
            p=OLD/'qualification'/f'{state}_{suffix}.json'
            ck(state+':frozen_'+suffix,INPUTS[str(p)]['sha256']==known_hashes[p.name])
        actual=read(RUN/f'{state.lower()}_ACTUAL_SNAPSHOT.json')
        ck(state+':actual_snapshot_matches_qualification',equal(without(actual,{'pid','blend_filepath'}),without(snap,{'pid','blend_filepath'})))
        snapshots[state]={o['name']:o for o in actual['objects']}
        ck(state+':geometry_denominators',actual['counts']=={'objects':24,'vertices':530,'triangles':978})
        truth[state]={tuple(sorted((p['object_a'],p['object_b']))):p for p in td['pairs']}
        earlier={tuple(x['pair']):rational(x['exact_squared']) for x in root_oracle[state.lower()]['pairs']}
        ck(state+':truth_276_unique_pairs',len(truth[state])==276 and set(truth[state])==set(itertools.combinations(sorted(snapshots[state]),2)))
        for pair,p in truth[state].items():
            sq=rational(p['exact_squared_distance_m2'])
            ck(state+':prior_exact:'+str(pair),earlier[pair]==sq)
            ck(state+':exact_predicate:'+str(pair),(sq<=Fraction.from_float(.002)**2)==p['matches_threshold'])
    audit=lines(RUN/'audit.jsonl')
    observed={x['trace_id']:x for x in audit if x['event']=='observe'}
    traces={x['trace_id']:x['trace'] for x in audit if x['event']=='request_trace'}
    ck('exact_five_observe_and_six_trace_events',len(observed)==5 and len(traces)==6 and len(audit)==11)
    result=read(RUN/'RESULTS.json')
    row_names=['base_default','base_brief','base_full','edit_default','edit_full']
    receipts={name:read(RUN/f'{name}_RESPONSE_RECEIPT.json') for name in row_names}
    idx=read(RUN/'native/WIRE/INDEX.json')
    wire={}
    for entry in idx:
        n=entry['sequence'];base=RUN/'native/WIRE'/f'{n:03d}'
        tx,rx=raw(base/'REQUEST.bin'),raw(base/'RESPONSE.bin')
        ck(f'host{n}:raw_byte_counts',len(tx)==entry['request_bytes'] and len(rx)==entry['response_attempted_bytes'] and len(tx)+len(rx)==entry['request_response_attempted_bytes'])
        ck(f'host{n}:sendall_completed',entry['response_sendall_completed'])
        wire[n]=(json.loads(tx),json.loads(rx))
    ck('exact_nine_host_rpc',sorted(wire)==list(range(1,10)))
    worker_events=lines(RUN/'native/WORKER_EVENTS.jsonl')
    worker={x['sequence']:x for x in worker_events}
    ck('nine_worker_events_including_generic_close_unknown',len(worker)==9 and sorted(worker)==list(range(1,10)) and worker[9]['status']=='unknown')
    ck('close_unknown_separate_protocol_response_closed',wire[9][0]=={'type':'close'} and wire[9][1]['status']=='closed')
    metrics=[]
    for n,(name,hostseq) in enumerate(zip(row_names,[2,3,4,7,8]),5):
        receipt=receipts[name];body=receipt['body'];state=receipt['truth_state'];full=receipts[state.lower()+'_full']['body']
        response=read(RUN/'product'/f'{n:03d}'/'RX.bin')
        request=read(RUN/'product'/f'{n:03d}'/'TX.bin')
        stdio=read(RUN/'product'/f'{n:03d}'/'RECEIPT.json')
        text=response['result']['content'][0]['text']
        ck(name+':wire_body_and_receipt',equal(json.loads(text),body) and response==receipt['response'] and request==receipt['request'])
        ck(name+':wire_request_separate_receipt',request==read(RUN/f'{name}_REQUEST.json'))
        ck(name+':wire_only_one_text',len(response['result']['content'])==1 and response['result']['content'][0]['type']=='text')
        ck(name+':no_tool_error',not response['result'].get('isError',False) and 'error'not in response and receipt['errors']==[])
        ck(name+':stdio_byte_counts',stdio['received_bytes']==len(raw(RUN/'product'/f'{n:03d}'/'RX.bin')) and stdio['sent_bytes']==len(raw(RUN/'product'/f'{n:03d}'/'TX.bin')) and stdio==receipt['stdio'])
        ck(name+':complete_client_ns',type(receipt['started_ns'])is int and type(receipt['ended_ns'])is int and receipt['ended_ns']-receipt['started_ns']==receipt['complete_client_request_ns'])
        ck(name+':stdio_contained_client',receipt['started_ns']<=stdio['started_ns']<=stdio['started_ns']+stdio['elapsed_ns']<=receipt['ended_ns'])
        ck(name+':actual_text_bytes',len(text.encode('utf-8'))==receipt['business_text_utf8_bytes'])
        if not name.endswith('_full'): ck(name+':10KiB',len(text.encode('utf-8'))<=10240)
        ck(name+':candidate_source',body['binding']['runtime_source_sha256']==SOURCE)
        ck(name+':same_state_full_binding',body['binding']==full['binding'])
        ck(name+':top_metadata_preserved',equal(without(full,{'matches','trace_id'}),{k:body[k] for k in full if k not in {'matches','trace_id'}}))
        ck(name+':unknown_not_hidden',body['coverage']['unknown']==0 and body['unresolved']==[] and body['unsupported_objects']==[] and body['scope_issues']==[] and body['execution_authority']is False)
        rows=decode_compact(body,name) if 'display_encoding'in body else body['matches']
        original_rows=[without(x,{'point_a_world','point_b_world'}) for x in full['matches']]
        ck(name+':all_rows_raw_bits_names_ids_metadata_order',equal(rows,original_rows) if 'display_encoding'in body else equal(rows,full['matches']))
        public_pairs={tuple(sorted(o['name']for o in row['objects'])) for row in rows}
        expected={p for p,t in truth[state].items() if t['matches_threshold']}
        ck(name+':match_set_no_FP_FN_or_duplicates',public_pairs==expected and len(rows)==len(public_pairs)==(71 if state=='BASE'else 72))
        tx,rx=wire[hostseq]
        code_ast=ast.parse(tx['params']['code'])
        assignment=next(x for x in code_ast.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name)and t.id=='_request'for t in x.targets))
        command=json.loads(ast.literal_eval(assignment.value.args[0]))
        packet=json.loads(rx['result']['result'].split('HUMAN_EYE_BLENDER_MCP:',1)[1])
        ck(name+':one_capture_command_and_matching_reply',command['command']=='capture_surface_scan' and command['params']['threshold_m']==.002 and packet['id']==command['id'])
        cap=packet['result']['capture'];id_names={x['object_id']:x['name']for x in cap['coverage']}
        ck(name+':complete_24_identity_directory',len(id_names)==24 and set(id_names.values())==set(snapshots[state]))
        ck(name+':host_binding',cap['binding']['directory_sha256']==body['binding']['directory_sha256'] and cap['binding']['host_identity']['document_epoch']==body['binding']['document_epoch'] and cap['binding']['host_source_sha256']==body['binding']['host_source_sha256'])
        for i,row in enumerate(rows):
            ck(f'{name}:row{i}:host_object_identity',all(id_names[o['id']]==o['name'] for o in row['objects']))
        obs=observed[body['trace_id']];trace=traces[body['trace_id']];work=obs['task_work'];dispositions=work['dispositions']
        dismap={tuple(sorted(id_names[x]for x in d['object_ids'])):d for d in dispositions}
        ck(name+':276_unique_dispositions',len(dismap)==len(dispositions)==276 and set(dismap)==set(truth[state]))
        hist=collections.Counter(d['status']for d in dispositions)
        maxerror=0.0
        for pair,t in truth[state].items():
            d=dismap[pair];sq=rational(t['exact_squared_distance_m2'])
            ck(name+':partition:'+str(pair),d['status']==('measured_match'if t['matches_threshold']else('measured_nonmatch'if t['api_AABB_Linf_retained']else'bound_excluded')))
            if 'distance_m'in d:
                err=abs(d['distance_m']-math.sqrt(float(sq)));maxerror=max(maxerror,err)
                ck(name+':distance:'+str(pair),err<=1e-10)
        for i,row in enumerate(rows):
            pair=tuple(sorted(o['name']for o in row['objects']))
            ck(f'{name}:row{i}:raw_bits_disposition',bits(row['distance_m'])==bits(dismap[pair]['distance_m']))
        ck(name+':public_partition_counts',all(body['coverage'][k]==v for k,v in hist.items()) and sum(hist.values())==body['coverage']['total_pairs']==276)
        pairwork=work.get('pairs',{})
        kernels=sum(x['surface_pair_count'] for x in pairwork.values())
        ck(name+':kernel_count_vs_pair_observations',kernels==work['kernel_calls']==[112,0,0,10,0][n-5])
        if not work['result_cache_hit']:
            before,after=work['measurement_cache_before'],work['measurement_cache_after']
            ck(name+':kernel_count_vs_cache_delta',after['measurement_computations']-before['measurement_computations']==kernels)
        spans=trace['spans'];byname=collections.defaultdict(list)
        for span in spans:
            byname[span['name']].append(span)
            ck(name+':span_in_trace:'+span['span_id'],isinstance(span['duration_ns'],int) and 0<=span['start_offset_ns']<=span['start_offset_ns']+span['duration_ns']<=trace['duration_ns'])
        ck(name+':one_capture_span',len(byname['host.capture'])==1)
        enc=byname['mcp.content_encode'][0];proj=byname['mcp.surface_scan_compact_projection']
        ck(name+':projection_count',len(proj)==(0 if name.endswith('_full')else 1))
        for p in proj:
            ck(name+':projection_nested_not_additive',p['parent_span_id']==enc['span_id'] and enc['start_offset_ns']<=p['start_offset_ns'] and p['start_offset_ns']+p['duration_ns']<=enc['start_offset_ns']+enc['duration_ns'])
        ck(name+':no_trace_errors_or_images',not trace['image_events'] and all(s['outcome']=='completed'and s['error_type']is None for s in spans))
        event=worker[hostseq]
        ck(name+':worker_completed',event['status']=='completed'and event['script_error']is None and event['stderr_bytes']==0)
        ck(name+':worker_script_bound',hashlib.sha256(tx['params']['code'].encode()).hexdigest()==event['script_sha256'])
        witness_count=0;max_witness_surface_error=0.0;max_witness_gap_error=0.0
        if name.endswith('_full'):
            for i,row in enumerate(rows):
                for side,key in enumerate(['point_a_world','point_b_world']):
                    ob=snapshots[state][row['objects'][side]['name']];p=row[key]
                    d2=min(triangle_d2(p,*(ob['vertices_world'][v]for v in tri))for tri in ob['triangles'])
                    error=math.sqrt(d2);max_witness_surface_error=max(max_witness_surface_error,error);witness_count+=1
                    ck(f'{name}:row{i}:surface_witness{side}',error<=1e-10)
                gap=math.dist(row['point_a_world'],row['point_b_world'])
                gaperr=abs(gap-row['distance_m']);max_witness_gap_error=max(max_witness_gap_error,gaperr)
                ck(f'{name}:row{i}:witness_gap',gaperr<=1e-10)
        metrics.append({'state':name,'matches':len(rows),'actual_text_utf8_bytes':len(text.encode()),'client_request_ns':receipt['complete_client_request_ns'],
            'projection_ns':sum(p['duration_ns']for p in proj)if proj else None,'inclusive_content_encode_ns':enc['duration_ns'],'trace_ns':trace['duration_ns'],
            'host_capture_ns':byname['host.capture'][0]['duration_ns'],'host_rpc':1,'kernel_calls':kernels,
            'host_request_bytes':idx[hostseq-1]['request_bytes'],'host_response_attempted_bytes':idx[hostseq-1]['response_attempted_bytes'],
            'stdio_request_bytes':stdio['sent_bytes'],'stdio_response_bytes':stdio['received_bytes'],'all_pairs_checked':len(dismap),
            'all_measured_distances_checked':sum('distance_m'in d for d in dispositions),'maximum_distance_error_m':maxerror,
            'witness_points_checked':witness_count,'maximum_witness_surface_error_m':max_witness_surface_error,'maximum_witness_gap_error_m':max_witness_gap_error,
            'new_resource_arrays':event['m2_work']['new_resource_arrays'],
            'measurement_cache_accounted_bytes':work.get('measurement_cache_after',{}).get('accounted_bytes')})
        author=result['business'][n-5]
        ck(name+':summary_matches_raw',author['state']==name and author['body']==body and author['complete_client_request_ns']==metrics[-1]['client_request_ns'] and author['bridge_request_bytes']==metrics[-1]['host_request_bytes'] and author['bridge_response_bytes']==metrics[-1]['host_response_attempted_bytes'])
    basebind=receipts['base_full']['body']['binding'];editbind=receipts['edit_full']['body']['binding']
    ck('pose_changed_only_expected_binding_keys',[k for k in basebind if basebind[k]!=editbind[k]]==['directory_sha256','scene_fingerprint','scene_revision'])
    ck('five_distinct_trace_ids',len({r['body']['trace_id']for r in receipts.values()})==5)
    old_base=read(ROOT/'verification/m4_surface_scan_consumption_001/cells/P1/owner/tool_01/RESPONSE.json')
    old_base=json.loads(old_base['result']['content'][0]['text'])
    old_edit=read(OLD/'engineering/run_01/sequence_01/edit_RESPONSE_RECEIPT.json')['body']
    for state,old in [('base',old_base),('edit',old_edit)]:
        now=receipts[state+'_full']['body']
        ck(state+':old_full_all_fields_raw_bits_except_binding_trace',equal(without(old,{'binding','trace_id'}),without(now,{'binding','trace_id'})))
    ft=read(RUN/'FINAL_TIMING.json');pub=read(RUN/'TIMING_PUBLICATION.json')
    ck('final_wall_subtraction',ft['business_receipts_closed_ns']-ft['started_ns']==ft['full_session_wall_ns']==4862992900)
    ck('full_clock_sequence_and_original_deadline',ft['started_ns']==result['started_ns'] and result['business_and_owned_cleanup_end_ns']<=ft['business_receipts_closed_ns']<=ft['original_deadline_ns']==result['deadline_ns'])
    ck('publication_separate_after_full_session',pub['started_ns']>=ft['business_receipts_closed_ns'] and pub['closed_ns']-pub['started_ns']==pub['publication_ns']==772400)
    ck('no_failed_or_hidden_business_attempts',result['execution_counts']=={'attempted':5,'completed':5,'failed':0,'not_attempted':0} and result['automatic_retries']==0 and result['errors']==[])
    ck('owned_cleanup_success',result['native_close']['process_reaped'] and result['product_close']['process_reaped'] and result['runtime_exit']['exit_code']==0)
    ck('fixed_sequence_is_complete', [x['state']for x in result['business']]==row_names)
    ib=read(RUN/'INPUT_BINDINGS.json')
    report={
      'review_kind':'independent offline reanalysis; no author code imported/executed; no new runtime/model',
      'product_commit':PRODUCT,'delivery_commit':DELIVERY,'source_sha256':SOURCE,
      'oracle_layers':'Qualification exact rational answers reused by fixed SHA; all 552 squared distances also compared to prior root independent recomputation fixed dd11f1aa. This run does not solve all triangle pairs again. New point-to-triangle witness checks use independent stdlib implementation.',
      'AL_scope':'Current child handle 2d52da22100d41b0bd4f17a0cee08411 reports stale assignment to prior parent task; explicit new parent assignment authorizes this review, no write to parent AL task; not represented as new AL binding.',
      'five_rows':metrics,'denominators':{'business_observations':5,'compact_observations':3,'full_observations':2,'match_rows_all':sum(x['matches']for x in metrics),'compact_rows_recovered':214,'full_rows':143,'object_pairs_checked':sum(x['all_pairs_checked']for x in metrics),'measured_distances_checked':sum(x['all_measured_distances_checked']for x in metrics),'full_witness_points_checked':sum(x['witness_points_checked']for x in metrics)},
      'byte_reductions':{'BASE':1-metrics[0]['actual_text_utf8_bytes']/metrics[2]['actual_text_utf8_bytes'],'EDIT':1-metrics[3]['actual_text_utf8_bytes']/metrics[4]['actual_text_utf8_bytes']},
      'cost_scope':{'full_session_ns':ft['full_session_wall_ns'],'timing_receipt_publication_ns':pub['publication_ns'],'publication_receipt_self_excluded':True,'all_requests_client_ns':sum(x['client_request_ns']for x in metrics),'business_host_request_bytes':sum(x['host_request_bytes']for x in metrics),'business_host_response_attempted_bytes':sum(x['host_response_attempted_bytes']for x in metrics),'all_nine_host_request_bytes':sum(x['request_bytes']for x in idx),'all_nine_host_response_attempted_bytes':sum(x['response_attempted_bytes']for x in idx),'isolated_build_install_ns_author_receipt':ib['ready']['elapsed_ns'],'pure_projection_is_nested_in_content_encode':True,'no_summed_inclusive_span_cost':True},
      'preserved_record_anomalies':['Worker event #9 (close) remains status=unknown in original generic event log. Its WIRE/009 protocol response is closed, and separate owner close/runtime wait/reap and FINAL_TIMING attest closure. This is not counted as a failed/unknown business observation.','Independent verifier attempt 01 incorrectly expected only 8 worker events. Its one failed assertion is retained in ATTEMPT_01_RESULTS/CHECKS.json, corrected to expect and separately classify all 9 actual events.'],
      'not_measured':['new consumer comprehension, task answer quality, final provider-visible input, actual model token counts or fees','counterbalanced latency delta or whole-task speedup against old product/native','nonempty unknown/partial/error semantics in these five actual rows (all complete); synthetic edge cases belong separate source/semantic subreview','all-triangle exact solver independently rerun during this review','fsync durability and process-external transient edits','general scenes beyond fixed 24-object 530-vertex 978-triangle source'],
      'checks':len(CHECKS),'failed_checks':[x for x in CHECKS if not x['passed']]}
    report['passed']=not report['failed_checks']
    for filename,data in [('RESULTS.json',report),('CHECKS.json',CHECKS),('INPUT_HASHES.json',INPUTS)]:
        (OUT/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'checks':len(CHECKS),'failed':report['failed_checks'],'denominators':report['denominators'],'cost_scope':report['cost_scope']},ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
