"""Offline independent checks of frozen requests, native facts and cleanup."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
OUT = FOLDER / 'run_01'


def load(path):
    return json.loads(Path(path).read_bytes(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonstandard_json_'+value)))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    freeze, plan, results = [load(OUT/name) for name in ('FREEZE.json','PLAN.json','RESULTS.json')]
    assert sha(OUT/'PLAN.json') == freeze['plan_sha256']
    for row in freeze['scripts'] + freeze['controllers']:
        assert sha(row['path']) == row['sha256'], row['path']
    assert len(results['states']) == 4 and results['owned_sessions_attempted'] == 1 and results['transport_attempts'] == 5
    assert results['primary_error'] is None and not results['product_source_drift']
    assert results['asset_sha256_after'] == plan['asset_sha256'] and results['helper_sha256_after'] == plan['helper_sha256']
    closed = load(OUT/'owned/WORKER_CLOSED.json')
    assert not closed['poisoned'] and closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint']
    assert results['cleanup']['process_reaped'] and results['cleanup']['exit_code'] == 0 and results['cleanup']['error'] is None
    events = [json.loads(line) for line in (OUT/'owned/WORKER_EVENTS.jsonl').read_text().splitlines()]
    assert [row['sequence'] for row in events] == [1,2,3,4,5]
    observations = []
    transport = {'send_attempted_bytes':0,'send_completed_bytes':0,'received_bytes':0}
    for state in range(1,5):
        row = next(row for row in freeze['scripts'] if row['state']==state)
        code = Path(row['path']).read_bytes()
        tx = load(OUT/('rpc_'+str(state))/'TX.bin')
        rx = load(OUT/('rpc_'+str(state))/'RX.bin')
        assert tx['params']['code'].encode() == code
        assert events[state-1]['script_sha256'] == hashlib.sha256(code).hexdigest()
        assert events[state-1]['status']=='completed' and events[state-1]['terminal_geometry_and_file_checks_passed']
        assert events[state-1]['script_error'] is None and rx['status']=='success'
        assert (OUT/'owned'/('call_'+str(state))/'SCRIPT.py').read_text(encoding='utf-8').encode()==code
        record = load(OUT/'owned'/('state_'+str(state))/'STATE_RESULT.json')
        parsed = json.loads(rx['result']['result'].split('BOUND_SOURCE_QA_RESULT:',1)[1])
        assert parsed == record
        assert record['primary_error'] is None and record['restored'] and record['capture_called']
        assert record['source_bytes_compiled']['host_sha256']==plan['host_sha256'] and record['source_bytes_compiled']['guard_verified']
        before = load(OUT/'owned'/('state_'+str(state))/'ORACLE_BEFORE.json')
        after = load(OUT/'owned'/('state_'+str(state))/'ORACLE_AFTER.json')
        assert before == after, 'tagged same-state evidence changed'
        assert before['graph_pointer']==after['graph_pointer'] and before['scale_length']==1.0
        native = next(row for row in before['rows'] if row['name']=='M4_Far_00')
        packet = record['capture']['packet']
        coverage = next(row for row in packet['coverage'] if row['object_id']==native['object_id'])
        assert packet['M3_qualification_performed'] is False
        assert packet['result_kind']=='acquisition_only_not_nearest_result'
        assert coverage['bounds_status']=='enclosed' and coverage['witness'] is not None
        if state in (1,2):
            assert not native['referenced_nonfinite_indices'] and not native['invalid_face_indices']
            assert native['all_vertices_enclosed_by_api_box']
            for point in native['coordinates_world_m']:
                for k in range(3):
                    assert Fraction(coverage['bounds_world_m'][0][k]) <= Fraction(point[k]) <= Fraction(coverage['bounds_world_m'][1][k])
        if state==2:
            assert native['coordinates_local'][3]==[.25,.25,.25]
            assert coverage['disposition']=='retained'
            old_far=next(row for row in record['before_mutation']['rows'] if row['name']=='M4_Far_00')
            assert min(point[0] for point in old_far['bound_box_local'])==100.0
            assert min(point[0] for point in native['bound_box_local'])==.25
        else:
            assert coverage['disposition']=='excluded_strict_bound'
            assert coverage['lower_bound_m']>packet['witness_upper_bound_m']
        if state==3:
            assert native['coordinates_local'][3][0]=={'nonfinite':'nan'}
            assert native['referenced_nonfinite_indices']==[3]
        if state==4:
            assert native['loop_vertex_indices']==[0,1,2,13,4,5]
            assert native['invalid_face_indices']==[{'face':1,'corner':0,'index':13}]
        observations.append(dict(state=state, setter_or_update_rejected=False if state>1 else None,
                 capture_status=record['capture']['status'], far_disposition=coverage['disposition'],
                 far_bounds_status=coverage['bounds_status'], far_lower_m=coverage['lower_bound_m'], upper_m=packet['witness_upper_bound_m'],
                 referenced_nonfinite_indices=native['referenced_nonfinite_indices'], invalid_face_indices=native['invalid_face_indices'],
                 tagged_native_oracles_equal=True, raw_python_equality_flag=record['same_native_state_before_after_capture'],
                 restored=True, compiled_host_sha256=record['source_bytes_compiled']['host_sha256']))
    for name in ['rpc_'+str(i) for i in range(1,5)]+['rpc_close']:
        d=load(OUT/name/'TRANSPORT.json')
        for key in transport: transport[key]+=d[key]
        assert (OUT/name/'TX.bin').stat().st_size==d['send_attempted_bytes']==d['send_completed_bytes']
        assert (OUT/name/'RX.bin').stat().st_size==d['received_bytes']
    assert load(OUT/'rpc_close/TX.bin')=={'type':'close'}
    assert load(OUT/'rpc_close/RX.bin')['status']=='closed'
    baseline=load(OUT/'owned/state_1/STATE_RESULT.json')
    build=baseline['build']
    official=load(FOLDER.parent/'nearest_contract_m2_001/OFFICIAL_TAG.json')['body']['object']['sha']
    assert official.startswith(build['build_hash']) and build['version']==[5,2,1]
    assert sum('build' in load(OUT/'owned'/('state_'+str(i))/'STATE_RESULT.json') for i in range(1,5))==1
    report=dict(status='complete_bounded_source_QA_not_product_admission',observations=observations,
                build=build, official_tag_commit=official, self_reported_build_hash_prefix_matches_tag=True,
                binary_sha256=plan['blender_sha256'], reproducible_binary_build_proof=False,
                transport_totals=transport, state_RPC=4, close_RPC=1, product_capture_calls=4,
                owned_sessions=1, owned_pid=closed['pid'], cleanup=results['cleanup'],
                controller_wall_ns=results['whole_controller_ns'], controller_wall_is_not_full_turn_or_performance_sample=True,
                nan_equality_note='Frozen worker used raw Python equality; NaN != NaN makes state3 flag false. Independent comparison of explicit nonfinite-tag JSON before/after is equal, including graph and data identities. Original false flag preserved.',
                helper_close_event_note='Event5 retains helper initial status unknown on close break; raw close response and owner wait/exit separately prove successful closure.',
                all_checks_passed=True)
    (OUT/'ANALYSIS.json').write_bytes((json.dumps(report,indent=2,allow_nan=False)+'\n').encode())
    print(json.dumps({k:v for k,v in report.items() if k not in ('observations','cleanup')},indent=2))


if __name__=='__main__':main()
