"""Fixed statistics over the single saved matrix, without any host calls."""
import argparse
import ast
import base64
import hashlib
import json
import math
from pathlib import Path
import statistics
import zlib


def distribution(values):
    if not values:
        return {'n':0,'raw':[],'median':None,'p95_nearest_rank':None}
    ordered = sorted(values)
    return {'n':len(values),'raw':values,'median':statistics.median(values),
            'p95_nearest_rank':ordered[math.ceil(.95*len(ordered))-1]}


def bootstrap(path):
    wire = json.loads(path.read_bytes())
    code = wire.get('params',{}).get('code','')
    tree = ast.parse(code)
    literals = [node.args[0].value for node in ast.walk(tree) if isinstance(node,ast.Call)
        and isinstance(node.func,ast.Attribute) and node.func.attr=='b64decode'
        and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)]
    return {'compressed_source_literal_UTF8_bytes':sum(len(value.encode('utf8')) for value in literals),
            'decoded_source_bytes':sum(len(zlib.decompress(base64.b64decode(value))) for value in literals),
            'source_literal_count':len(literals),
            'scope':'identified actual compressed-source literals only; enclosing bytes remain in full bridge request'}


def work(row):
    events = row['work_events']
    counters = {}
    arrays = {'vertices':0,'faces':0,'edges':0}
    native = []
    for event in events:
        value = event['m2_work']
        for key,count in value['new_resource_arrays'].items():
            arrays[key] += count
        for side,multiplier in (('before',-1),('after',1)):
            for host in value[side]:
                for key,count in host['work'].items():
                    if type(count) is int:
                        counters[key] = counters.get(key,0)+multiplier*count
        if value['native_work'] is not None:
            native.append(value['native_work'])
    return {'host_cumulative_counter_delta':counters,'new_resource_arrays':arrays,
            'directory_vertex_forward_operations':counters.get('directory_vertices'),
            'legacy_resource_pose_object_world_transforms':counters.get('world_transforms'),
            'world_counter_scope':'directory_vertices counts directory vertex forwards; legacy world_transforms counts full-resource pose rebuilds; native counters are separate',
            'native_per_call_counters':native,'total_uninstrumented_loop_visits':None}


def analyze(folder):
    matrix = json.loads((folder/'RESULTS.json').read_bytes())
    bindings = json.loads((folder/'INPUT_BINDINGS.json').read_bytes())
    source_unchanged = all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==expected
                           for path,expected in bindings['source_files'].items())
    sessions = []
    case_rows = {}
    for item in matrix['cases']:
        path = Path(item['result'])
        value = json.loads(path.read_bytes())
        session = {'case':item['case'],'passed':value['passed'],'errors':value['errors'],
            'session_wall_ns':value['session_wall_ns'],'timing_stages_ns':value['timing_stages_ns'],
            'continuous_request_window_ns':value.get('continuous_request_window_ns'),
            'continuous_with_checks_and_recording_ns':value.get('continuous_business_with_checks_and_recording_ns'),
            'all_actual_host_RPC_including_close':len(value.get('wire',[])),
            'all_actual_bridge_request_bytes_including_close':sum(row['request_bytes'] for row in value.get('wire',[])),
            'all_actual_bridge_response_bytes_including_close':sum(row['response_attempted_bytes'] for row in value.get('wire',[])),
            'product_runtime_proof':value.get('product_runtime_proof'),
            'product_runtime_exit':value.get('product_runtime_exit'),
            'native_close':value.get('native_close'),'rows':[]}
        for row in value['rows']:
            if not all(key in row for key in ('host_RPC','wire','work_events')):
                session['rows'].append({'index':row['index'],'incomplete':True})
                continue
            request_bytes = sum(part['request_bytes'] for part in row['wire'])
            response_bytes = sum(part['response_attempted_bytes'] for part in row['wire'])
            metrics = {'index':row['index'],'phase':row['phase'],'tool_ns':row['tool_ns'],
                'tool_scope':row['tool_scope'],'host_RPC':row['host_RPC'],
                'bridge_request_bytes':request_bytes,'bridge_response_bytes':response_bytes,
                'bridge_sum_bytes':request_bytes+response_bytes,
                'visible_text_UTF8_bytes':row['visible_text_UTF8_bytes'],
                'stdio':row.get('stdio'),'work':work(row),
                'service_trace_ns':[event['trace']['duration_ns'] for event in row['service_traces']],
                'service_spans':[event['trace']['spans'] for event in row['service_traces']],
                'product_process_lifetime_peak_bytes':[event['trace']['peak_rss']['bytes']
                    for event in row['service_traces'] if event['trace'].get('peak_rss')],
                'native_peak_bytes':None,'verification_ns':row.get('verification_ns')}
            if row['index']==0:
                metrics['compressed_source_establishment'] = [bootstrap(path.parent/'native/WIRE'/str(part['sequence']).zfill(3)/'REQUEST.bin')
                    for part in row['wire']]
                metrics['native_first_execute_code_UTF8_bytes'] = row.get('code_UTF8_bytes') if item['case']['lane']=='native' else None
            session['rows'].append(metrics)
        sessions.append(session)
        case_rows[item['case']['case_id']] = value
    groups = {}
    for asset in ('simple_boxes','peripheral','rotated_asymmetric'):
        groups[asset] = {}
        for lane in ('old','new','native'):
            matching = [value for value in sessions if value['case']['asset']==asset
                        and value['case']['lane']==lane and not value['case']['two_step']]
            groups[asset][lane] = {}
            for phase in ('cold','warm'):
                selected = [row for value in matching for row in value['rows'] if row.get('phase')==phase]
                groups[asset][lane][phase] = {key:distribution([row[key] for row in selected])
                    for key in ('tool_ns','bridge_request_bytes','bridge_response_bytes','bridge_sum_bytes','visible_text_UTF8_bytes','host_RPC')}
    gate = {'all_36_sessions_passed':len(sessions)==36 and all(value['passed'] for value in sessions),
            'source_files_unchanged':source_unchanged,'peripheral_cold_response_reduction_50_percent':None,
            'peripheral_cold_median_time_reduction_10_percent':None,'simple_warm_p95_within_frozen_limit':None}
    peripheral_old = groups['peripheral']['old']['cold']
    peripheral_new = groups['peripheral']['new']['cold']
    simple_old = groups['simple_boxes']['old']['warm']['tool_ns']
    simple_new = groups['simple_boxes']['new']['warm']['tool_ns']
    if peripheral_old['tool_ns']['n']==peripheral_new['tool_ns']['n']==3:
        # Response-byte gate uses each of the three fixed paired cold samples.
        before = peripheral_old['bridge_response_bytes']['raw']
        after = peripheral_new['bridge_response_bytes']['raw']
        gate['peripheral_cold_response_reduction_50_percent'] = all(b<=a*.5 for a,b in zip(before,after))
        gate['peripheral_cold_median_time_reduction_10_percent'] = peripheral_new['tool_ns']['median']<=peripheral_old['tool_ns']['median']*.9
    if simple_old['n']==simple_new['n']==30:
        gate['simple_warm_p95_limit_ns'] = max(1_000_000,simple_old['p95_nearest_rank']*.05)
        gate['simple_warm_p95_increase_ns'] = simple_new['p95_nearest_rank']-simple_old['p95_nearest_rank']
        gate['simple_warm_p95_within_frozen_limit'] = gate['simple_warm_p95_increase_ns']<=gate['simple_warm_p95_limit_ns']
    facts_equal = True
    selected_equal = True
    selected_independent = True
    selected_bindings = True
    selected_checks = []
    for asset in groups:
        values = [value for value in case_rows.values() if value['asset']==asset]
        facts = [sorted(row['directory_facts'],key=lambda obj:obj['object_id'])
                 for value in values for row in value['rows'] if 'directory_facts' in row]
        facts_equal &= bool(facts) and all(value==facts[0] for value in facts)
        task_rows = [row['body'] for value in values if value['two_step'] for row in value['rows'] if row['phase']=='selected']
        selected_equal &= len(task_rows)==3 and all(
            {key:value[key] for key in ('result_kind','schema_version','status','unit','coordinate_frame','pair_order','facts','execution_authority')}
            =={key:task_rows[0][key] for key in ('result_kind','schema_version','status','unit','coordinate_frame','pair_order','facts','execution_authority')}
            for value in task_rows)
        selected_equal &= all(value['binding']['objects']==task_rows[0]['binding']['objects'] for value in task_rows)
        oracle = next(value for value in bindings['assets'] if value['name']==asset)
        selected_oracle = [next(row for row in oracle['oracle'] if row['name']==name)
                           for name in ('M4_Focal','M4_Near')]
        a,b = selected_oracle
        expected_aabb = [{'status':'measured','value':{
            'min':row['bbox_min'],'max':row['bbox_max'],
            'dimensions':[high-low for low,high in zip(row['bbox_min'],row['bbox_max'])]}}
            for row in selected_oracle]
        expected_gaps = [max(0.,b['bbox_min'][axis]-a['bbox_max'][axis],a['bbox_min'][axis]-b['bbox_max'][axis])
                         for axis in range(3)]
        for value in values:
            if not value['two_step']:
                continue
            for row in value['rows']:
                if row['phase']!='selected':
                    continue
                body = row['body']
                facts = body['facts']
                aabb_ok = facts['aabb']==expected_aabb
                gap_ok = facts['axis_gap']['status']=='measured' and facts['axis_gap']['value']==expected_gaps
                expected_source = bindings['new' if value['lane']=='new' else 'old']['source_sha256']
                binding = body['binding']
                binding_ok = (binding['runtime_source_sha256']==expected_source and binding['source']=='blender'
                    and binding['capture_scope']=='selected_objects' and binding['candidate_count']==oracle['object_count']
                    and binding['selected_count']==2 and [entry['name'] for entry in binding['objects']]==['M4_Focal','M4_Near']
                    and isinstance(binding['scene_revision'],str) and bool(binding['scene_revision'])
                    and isinstance(binding['scene_fingerprint'],str) and len(binding['scene_fingerprint'])==64)
                selected_independent &= aabb_ok and gap_ok
                selected_bindings &= binding_ok
                selected_checks.append({'asset':asset,'lane':value['lane'],'independent_aabb':aabb_ok,
                    'independent_axis_gap':gap_ok,'actual_binding':binding_ok,
                    'surface_proximity':facts['surface_proximity'],
                    'surface_check_scope':'three-lane same-input complete fact/status/reason equality; no added geometry solver'})
    gate['all_common_directory_facts_equal'] = facts_equal
    gate['two_step_selected_public_facts_equal'] = selected_equal
    gate['two_step_selected_aabb_axis_gap_independently_correct'] = selected_independent
    gate['two_step_selected_bindings_valid'] = selected_bindings
    directory_rows = [row for value in sessions if value['case']['lane']=='new'
                      for row in value['rows'] if row.get('phase') in ('cold','warm')]
    gate['new_directory_no_materialized_mesh_arrays_or_triangulations'] = bool(directory_rows) and all(
        row['work']['new_resource_arrays']=={'vertices':0,'faces':0,'edges':0}
        and row['work']['host_cumulative_counter_delta'].get('triangulations')==0 for row in directory_rows)
    native_comparison = []
    for asset,lanes in groups.items():
        for phase in ('cold','warm'):
            native = lanes['native'][phase]['tool_ns']['median']
            for lane in ('old','new'):
                plugin = lanes[lane][phase]['tool_ns']['median']
                native_comparison.append({'asset':asset,'phase':phase,'plugin':lane,
                    'native_median_ns':native,'plugin_median_ns':plugin,
                    'native_faster':None if native is None or plugin is None else native<plugin,
                    'scope':'complete respective entry calls; native execute and plugin MCP outer transports differ'})
    gate['performance_and_sample_gates_passed'] = all(value is True for key,value in gate.items()
        if key not in ('simple_warm_p95_limit_ns','simple_warm_p95_increase_ns','performance_and_sample_gates_passed'))
    return {'summary_scope':'saved工程measurements; no model calls, tokens, quality or complete-task benefit measured',
            'gates':gate,'groups':groups,'native_comparison':native_comparison,'sessions':sessions,
            'selected_independent_checks':selected_checks,
            'worker_counter_scope':'existing residency plus actually materialized arrays; native explicit per-call counters; other loops unmeasured',
            'two_step_binding_scope':'complete original bindings retained in raw; cross-session semantic equality compares named objects and public facts',
            'matrix':matrix}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = analyze(args.run.resolve())
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'summary':str(args.output),'gates':result['gates']}))


if __name__=='__main__':
    main()
