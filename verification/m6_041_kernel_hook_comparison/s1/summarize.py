"""Postprocess preserved S1 attempts after all owned hosts exit."""
import json,pathlib,sys,collections,statistics
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import s1,audit
full=[]; all_cost=[]; held=[]
for label in ('slots','slots_recovery_01','slots_recovery_02'):
    for slot in sorted((ROOT/label).iterdir()):
        item=s1.read(slot/'SLOT.json');name=item['scenario'];arm=item['arm']
        product=s1.read(slot/'client/CLOSE.json');gui=s1.read(slot/'native/TERMINAL_OWNERSHIP.json')
        st=s1.read(slot/'client/STARTUP.json')
        note=dict(attempt=label,arm=arm,scenario=name,pid_GUI=gui['pid'],pid_MCP=st['actual_pid'],
           fresh_source=(slot/'native/input.blend').exists(),arm_source=st['startup_trace']['identity_check']['actual']['source_sha256'],
           process_lifecycle_ms=(item['end_ns']-item['started_ns'])/1e6,GUI_start_ms=(item['host_ready_ns']-item['started_ns'])/1e6,
           stdio_ready_relative_ms=(item['stdio_ready_ns']-item['started_ns'])/1e6,
           GUI_close_ms=gui['elapsed_ns']/1e6,stdio_close_ms=product['wall_ns']/1e6,
           errors=item['errors'],closed=gui['status']=='pass' and gui['released_port']['owned_listener'] is False and product['exit_code']==0 and product['method']=='eof',
           rows=[])
        for row in item['rows']:
            b=row['value']; au=row.get('audit') or s1.brief_trace(SimpleNamespace(source=note['arm_source'],server_pid=st['actual_pid'],audit=slot/'client/AUDIT.jsonl'),{'result':b,'timing':row['timing']})
            stat={}
            for role,final in row['os_after'].items():
                before=row['os_before'][role]
                stat[role]={"CPU_delta_ms":(final['cpu_s']-before['cpu_s'])*1000,"end_process_lifetime_peak_working_bytes":final['peak_working_set_bytes'],
                    "end_working_bytes":final['current_working_set_bytes'],"begin_working_bytes":before['current_working_set_bytes']}
            timing=row['timing'];wk=au['work'][0] if len(au['work'])==1 else {}
            note['rows'].append(dict(query=row['label'],response_ms=row['business_ns']/1e6,
                wire_wait_ms=timing['wire_wait_ns']/1e6,cli_decode_ms=timing['client_decode_ns']/1e6,
                audit_after_response_ms=au.get('post_response_verify_and_wait_ns',0)/1e6 if label=='slots_recovery_02' else None,
                tx=timing['tx_bytes'],rx=timing['rx_bytes'],nested_ms={n:sum(t for key,t in au['spans'] if key==n)/1e6 for n,t in au['spans']},
                status=b.get('status'),unresolved=b.get('unresolved'),coverage=b.get('coverage'),
                kernel_calls=wk.get('kernel_calls'),pair_calls=wk.get('pair_calls'),cache_hits=wk.get('cache_hits'),result_cache_hit=wk.get('result_cache_hit'),
                root_trace_ms=au['duration_ns']/1e6,OS=stat))
            if label=='slots_recovery_01' and name=='Yanyite':
                ref=s1.read(s1.INPUTS['Yanyite'])['regions']['high']
                held.append(dict(arm=arm,response_ms=row['business_ns']/1e6,source_matches=au['source']==note['arm_source'],truth_check=
                    b['point_a_m']==ref['source_point_world_m'] and b['point_b_m']==ref['reference_point_world_m'] and
                    b['source_triangle_a']==min(ref['source_witness_triangle_ids']) and b['source_triangle_b']==min(ref['cube_witness_triangle_ids'])))
        all_cost.append(note)
        if item['completed']:full.append(note)
summary=s1.read(ROOT/'AUDIT_2.json')
counts={'owned_slots':len(all_cost),'full_workflow_slots':len(full),'all_business_requests':sum(len(x['rows']) for x in all_cost),
        'requests_in_complete_sequences':sum(len(x['rows']) for x in full),'closed_slots':sum(x['closed'] for x in all_cost),
        'first_attempt_partial_slots':5,'asynchronous_audit_partial_slots':2,'paired_request_positions':len(summary['cross']),
        'paired_public_geometry_equal':sum(v['geometry_equal'] for v in summary['cross'].values()),
        'paired_equivalent_after_verified_host_scope':sum(v['equal'] for v in summary['cross'].values()),
        'paired_same_except_trace_build':sum(v['equal_except_trace_build'] for v in summary['cross'].values())}
s1.dump(ROOT/'COSTS.json',dict(summary=counts,attempts=all_cost,
    scope='Wall times cover original stdio request through complete decoded reply. Root trace and host/solver/encode/write spans overlap; no additive attribution. OS CPU and working set are per known actual Blender/MCP PID, sampled at request boundaries; per-process lifetime peaks cannot be summed into a concurrent process-tree peak. Neither Python allocation peaks nor isolated exact-kernel CPU are claimed.'))
s1.dump(ROOT/'RESULTS.json',dict(scope="S1 hosted kernel comparison only",decision="RESTRICTED",summary=counts,
    external_plan=s1.pin(s1.PLAN),initial_plan=s1.pin(ROOT/'PLAN.json'),audit=s1.pin(ROOT/'AUDIT_2.json'),
    retained_first_high_yanyite=held,first_attempt_G60=s1.pin(ROOT/'FIRST_ATTEMPT_OFFLINE.json'),
    notes=['G508 closed-solid relation is partial with closed_solid_work_budget in both arms; surface pair valid.',
           'All completed response geometries matched across installed arms. Independent source rows checked for D48, B02 and Yanyite. G508 scan independently checks 11 target pairs and checks all delivered results across arms.',
           'Negative-control and partial outcomes included. No tail estimate; each complete source/workload has one observation.',
           'No Hook invocation in S1. Source-region measurement used the normal installed optional flag. No model calls.']))
print(counts)

