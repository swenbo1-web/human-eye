"""Offline checks of the sole candidate's five frozen real states."""
import hashlib
import json
from pathlib import Path

FOLDER=Path(__file__).resolve().parent
OUT=FOLDER/'run_01'


def load(path):
    return json.loads(Path(path).read_bytes(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    plan,freeze,results=[load(OUT/name) for name in ('PLAN.json','FREEZE.json','RESULTS.json')]
    assert sha(OUT/'PLAN.json')==freeze['plan_sha256']
    for row in freeze['scripts']+freeze['controllers']:assert sha(row['path'])==row['sha256'],row['path']
    assert results['owned_sessions_attempted']==1 and results['transport_attempts']==6 and len(results['states'])==5
    assert results['primary_error'] is None and not results['product_source_drift']
    closed=load(OUT/'owned/WORKER_CLOSED.json')
    assert not closed['poisoned'] and closed['initial_geometry_fingerprint']==closed['final_geometry_fingerprint']
    assert results['cleanup']['process_reaped'] and results['cleanup']['exit_code']==0 and results['cleanup']['error'] is None
    events=[json.loads(line) for line in (OUT/'owned/WORKER_EVENTS.jsonl').read_text().splitlines()]
    assert [row['sequence'] for row in events]==[1,2,3,4,5,6]
    observations=[]
    for state in range(1,6):
        code=(OUT/('STATE_'+str(state)+'.py')).read_bytes()
        tx=load(OUT/('rpc_'+str(state))/'TX.bin');rx=load(OUT/('rpc_'+str(state))/'RX.bin')
        assert tx['params']['code'].encode()==code
        assert events[state-1]['script_sha256']==hashlib.sha256(code).hexdigest()
        assert events[state-1]['status']=='completed' and events[state-1]['terminal_geometry_and_file_checks_passed']
        assert events[state-1]['script_error'] is None and rx['status']=='success'
        assert (OUT/'owned'/('call_'+str(state))/'SCRIPT.py').read_text(encoding='utf-8').encode()==code
        folder=OUT/'owned'/('state_'+str(state));record=load(folder/'STATE_RESULT.json')
        assert json.loads(rx['result']['result'].split('BOUND_SOURCE_FIX_RESULT:',1)[1])==record
        assert record['primary_error'] is None and record['restored'] and record['capture_called']
        assert record['same_native_state_before_after_capture']
        before,after=load(folder/'ORACLE_BEFORE.json'),load(folder/'ORACLE_AFTER.json')
        assert before==after
        assert record['source_bytes_compiled']['host_sha256']==plan['host_sha256'] and record['source_bytes_compiled']['guard_verified']
        far=next(row for row in before['rows'] if row['name']=='M4_Far_00')
        cap=record['capture']
        result=dict(state=state,role='focal' if state==5 else 'far_nonfocal',capture_status=cap['status'],restored=True,
                    same_tagged_native_state=True,graph_pointer=before['graph_pointer'])
        if state<=2:
            assert cap['status']=='returned'
            packet=cap['packet'];row=next(x for x in packet['coverage'] if x['object_id']==far['object_id'])
            assert packet['result_kind']=='acquisition_only_not_nearest_result' and not packet['M3_qualification_performed']
            assert row['disposition']==('excluded_strict_bound' if state==1 else 'retained')
            assert packet['work']['expanded_objects']==(2 if state==1 else 3)
            # Compare old successful states as geometry only, never old epoch/time.
            old=load(FOLDER.parent/'bound_source_qa_001/run_01/owned'/('state_'+str(state))/'CAPTURE.json')
            geometry=lambda p:{m['object_id']:(m['vertices'],m['faces']) for m in p['capture']['meshes']}
            assert geometry(packet)==geometry(old)
            result.update(far_disposition=row['disposition'],expanded_objects=packet['work']['expanded_objects'],normal_geometry_equal_old_QA=True)
        else:
            assert cap['status']=='refused' and cap['error']['type']=='BlenderHostError'
            expected='acquisition_nonfinite_referenced_vertex:' if state==3 else 'acquisition_invalid_triangle_indices:'
            assert cap['error']['message']==expected+far['object_id']
            assert 'in _acquisition_validate_triangles' in cap['error']['traceback']
            assert 'in _capture\n' not in cap['error']['traceback']
            assert not (folder/'CAPTURE.json').exists()
            if state==3:assert far['referenced_nonfinite_indices']==[3]
            else:assert far['invalid_face_indices']==[dict(face=1,corner=0,index=13)]
            if state==5:assert record['capture_focal_name']=='M4_Far_00'
            result.update(controlled_source_error=cap['error']['message'],successful_bad_source_packet=False)
        observations.append(result)
    totals=dict(send_attempted_bytes=0,send_completed_bytes=0,received_bytes=0)
    for name in ['rpc_'+str(i) for i in range(1,6)]+['rpc_close']:
        folder=OUT/name;counts=load(folder/'TRANSPORT.json')
        assert (folder/'TX.bin').stat().st_size==counts['send_attempted_bytes']==counts['send_completed_bytes']
        assert (folder/'RX.bin').stat().st_size==counts['received_bytes']
        for key in totals:totals[key]+=counts[key]
    assert load(OUT/'rpc_close/RX.bin')['status']=='closed'
    baseline=load(OUT/'owned/state_1/STATE_RESULT.json')
    assert baseline['build']['build_hash']=='9e2066aef7ef'
    report=dict(status='five_states_passed_not_nearest_admission',candidate_commit=plan['candidate_commit'],
                source_sha256=plan['source_sha256'],host_sha256=plan['host_sha256'],observations=observations,
                successful_normal_captures=2,controlled_source_refusals=3,state_RPC=5,close_RPC=1,owned_sessions=1,
                build=baseline['build'],transport_totals=totals,cleanup=results['cleanup'],
                controller_wall_ns=results['whole_controller_ns'],no_performance_conclusion=True,all_checks_passed=True)
    (OUT/'ANALYSIS.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({k:v for k,v in report.items() if k not in ('observations','cleanup')},indent=2))


if __name__=='__main__':main()
