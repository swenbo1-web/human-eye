"""Read-only checks for this fixture's baseline/candidate owned QA evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

PREFIX=b'HUMAN_EYE_RPC:'

def load(path): return json.loads(Path(path).read_text(encoding='utf8'))
def rows(path): return [json.loads(line) for line in Path(path).read_text(encoding='utf8').splitlines() if line]
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def number(calls,suffix): return sum(v for k,v in calls.items() if k.endswith(':'+suffix))

def audit(folder):
    record=load(folder/'RESULTS.json')
    assert record['passed']
    assert load(folder/'identity_before.json')==load(folder/'identity_after.json')
    for case in record['cases']:
        path=folder/case['label']
        assert case['passed'] and case['worker_closed'] and case['worker_returncode']==0
        assert sha(path/'fixture.blend')==case['fixture_sha256_before']==case['fixture_sha256_after']
        for name,n in case['whole_host_transport_bytes'].items(): assert (path/name).stat().st_size==n,(path,name)
        tx=[json.loads(line) for line in (path/'owned_tx.bin').read_bytes().splitlines() if line]
        rx=[json.loads(line[len(PREFIX):]) for line in (path/'owned_rx.bin').read_bytes().splitlines() if line.startswith(PREFIX)]
        assert len(tx)==len(rx)
        tx_by_id={r['id']:r for r in tx};rx_by_id={r['id']:r for r in rx}
        assert tx_by_id.keys()==rx_by_id.keys()
        for row in rows(path/'host_requests.jsonl'):
            request=tx_by_id[row['rpc_id']]
            assert request['command']==row['command'] and request['params']==row['params']
            if 'result' in row: assert rx_by_id[row['rpc_id']]['result']==row['result']
        assert tx[-1]['command']=='shutdown' and rx[-1]['result']['closed'] is True
        for key in ('focal_z_translation_m','gap_m','target_m','error_m'):
            assert type(case['native_check'][key]) in (int,float)
        assert case['native_check']['other_objects_unchanged']==3
        assert number(case['calls'],'LiveSpatialService._save')==case['save_events']
    return record

def metrics(case):
    calls=case['calls'];commands=case['loop_host_commands']
    return {'capture_requests':sum(commands.get(k,0) for k in ('capture','capture_evidence','capture_task','capture_nearest_candidates')),
        'host_capture_entries':case['loop_worker_calls'].get('_capture',0),
        'host_resident_capture_entries':case['loop_worker_calls'].get('_resident_capture',0),
        'normalize':number(calls,'_validated_scene'),
        'mesh_from_dict':number(calls,'MeshEntity3D.from_dict'),
        'mesh_constructor':number(calls,'MeshEntity3D.__init__'),
        'strict_measure':number(calls,'measure_pair_geometry'),
        'save':number(calls,'LiveSpatialService._save'),
        'loop_ms':case['loop_ms'],'lifecycle_ms':case['lifecycle_ms'],
        'loop_transport_bytes':case['loop_transport_bytes']}

def completion_snapshots(folder,label):
    seen=set();found=[]
    for index,event in enumerate(rows(folder/label/'save_events.jsonl')):
        for entry in (event['segments'] or {}).get('records',{}).values():
            for step in entry['steps']:
                if step['state']=='complete' and step['step_id'] not in seen:
                    seen.add(step['step_id'])
                    found.append({'save_event_index':index,'step_index':step['step_index'],
                        'save_returned_normally':event['committed'],
                        'inflight_cleared':event['inflight'] is None,
                        'actual_translation_present':'actual_translation_m' in step,
                        'end_revision_matches_step':entry['end_revision']==step['result'].get('actual_scene_revision'),
                        'segment_status':entry['status']})
    return found

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    old,new=audit(args.baseline),audit(args.candidate)
    assert len(old['cases'])==len(new['cases'])==3
    result={'passed':False,'baseline_source_sha256':old['source_sha256'],
        'candidate_source_sha256':new['source_sha256'],'cases':[],
        'scope':'same generated fixture bytes; direct real function entry counts; times include unquantified observer overhead',
        'save_metric':'save means actual _save function entry count; raw committed=True means normal return only; _observation_baseline may skip atomic write',
        'full_loop_atomic_write_count':None}
    for left,right in zip(old['cases'],new['cases']):
        assert left['label']==right['label']
        assert left['fixture_sha256_before']==right['fixture_sha256_before']
        assert left['setter_count']==right['setter_count']
        assert left['receipt']['status']==right['receipt']['status']=='completed'
        for field in ('gap_m','focal_z_translation_m'):
            assert abs(left['native_check'][field]-right['native_check'][field])<=1e-7,(left['label'],field)
        before,after=metrics(left),metrics(right)
        old_completions=completion_snapshots(args.baseline,left['label'])
        new_completions=completion_snapshots(args.candidate,right['label'])
        assert len(old_completions)==len(new_completions)==right['setter_count']
        for snapshot in new_completions:
            assert snapshot['save_returned_normally'] and snapshot['inflight_cleared']
            assert snapshot['actual_translation_present'] and snapshot['end_revision_matches_step']
        if new_completions: assert new_completions[-1]['segment_status']=='satisfied'
        final_entries=load(args.candidate/right['label']/'state.json')['goal_segments']['records']
        assert len(final_entries)==1
        final_entry=next(iter(final_entries.values()))
        assert final_entry['status']=='satisfied' and len(final_entry['steps'])==right['setter_count']
        assert all(s['state']=='complete' and 'actual_translation_m' in s for s in final_entry['steps'])
        reduction={key:before[key]-after[key] for key in ('capture_requests','host_capture_entries','normalize','mesh_from_dict','mesh_constructor','strict_measure','save')}
        result['cases'].append({'label':left['label'],'setter_count':left['setter_count'],
            'baseline':before,'candidate':after,'fewer_calls':reduction,
            'baseline_first_complete_snapshots':old_completions,
            'candidate_first_complete_snapshots':new_completions,
            'native_goal_error_m':right['native_check']['error_m']})
    result['passed']=True
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
