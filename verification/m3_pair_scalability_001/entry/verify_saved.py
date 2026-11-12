"""Independently check saved public facts against the bound qualification oracle."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
QUALIFICATION = ROOT/'verification/spatial_task_qualification_001'
ORACLE = QUALIFICATION/'oracle/formal_replay_01/ORACLE.json'
POSITION_TOLERANCE_M = 1e-9
DISTANCE_TOLERANCE_M = 1e-6


def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_pair(row,left,right,reference,witness):
    facts = row['facts']
    surface = facts['surface_proximity']
    solid = facts['closed_solid_relation']
    result = {'surface_fact':surface,'closed_fact':solid,'separation_gap':row['separation_gap'],
              'distance_passed':False,'closed_passed':False,'witness_passed':False,'gap_passed':False}
    result['closed_passed'] = solid['status']=='measured' and solid['value']==reference['solid_relation']=='separated'
    value = surface.get('value')
    if surface['status']=='measured' and isinstance(value,dict):
        distance = value.get('distance_m')
        finite = type(distance) in (int,float) and math.isfinite(distance) and distance>=0
        if finite:
            result['distance_passed'] = (reference['distance_lower_m']-DISTANCE_TOLERANCE_M<=distance
                                        <=reference['distance_upper_m']+DISTANCE_TOLERANCE_M)
            points = value.get('nearest_witness')
            if surface.get('witness_status')=='measured' and isinstance(points,dict):
                result['witness_certificate'] = witness.certify_pair(points['a'],points['b'],distance,left,right,
                    position_tolerance_m=POSITION_TOLERANCE_M,distance_tolerance_m=DISTANCE_TOLERANCE_M)
                result['witness_passed'] = result['witness_certificate']['passed']
            gap = row['separation_gap']
            result['gap_passed'] = (result['closed_passed'] and gap['status']=='measured'
                and type(gap['value']) in (int,float) and abs(gap['value']-distance)<=DISTANCE_TOLERANCE_M)
            result['minimum_4mm_from_measured_distance'] = ('not_satisfied' if distance+DISTANCE_TOLERANCE_M<.004 else
                'satisfied' if distance-DISTANCE_TOLERANCE_M>=.004 else 'unknown')
    if 'minimum_4mm' in reference:
        result['expected_minimum_4mm'] = reference['minimum_4mm']
        result['minimum_4mm_passed'] = (result['gap_passed']
            and result.get('minimum_4mm_from_measured_distance')==reference['minimum_4mm'])
    result['full_pass'] = (result['distance_passed'] and result['closed_passed']
        and result['witness_passed'] and result['gap_passed'] and result.get('minimum_4mm_passed',True))
    return result


def verify(folder):
    started = time.perf_counter_ns()
    bindings = json.loads((folder/'INPUT_BINDINGS.json').read_bytes())
    for path,expected in bindings['source_files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:
            raise ValueError('frozen_source_changed:'+path)
    snapshot = json.loads((folder/'ACTUAL_SNAPSHOT.json').read_bytes())
    binder = load('_m3_public_source_binding',QUALIFICATION/'oracle/verify_actual.py')
    binding = binder.bind_actual(snapshot)
    oracle = json.loads(ORACLE.read_bytes())
    witness = load('_m3_public_witness',BATCH/'testing/witness_oracle.py')
    entry = load('_m3_public_entry',HERE/'run_entry.py')
    execution = json.loads((folder/'RESULTS.json').read_bytes())
    bodies = {row['request']['id']:row.get('body') for row in execution['business']}
    names = entry.verify_directory(bodies['directory'],snapshot)
    raw = {row['name']:row for row in snapshot['objects']}
    checks = []
    for label,target,candidates,references in (
            ('assembly_task','Target',('Peer_000','Competing_001','Near_003'),oracle['pairs']),
            ('control_task','Control_A',('Control_B',),(oracle['control'],))):
        task = {'label':label,'pairs':[],'binding_passed':False,'nearest_passed':False,'errors':[]}
        body = bodies.get(label)
        try:
            if not isinstance(body,dict) or body.get('result_kind')!='task_query':
                raise ValueError('task_public_body_unavailable')
            selected = [target,*candidates]
            expected_ids = [names[name] for name in selected]
            public_binding = body['binding']
            task['binding_passed'] = (public_binding['runtime_source_sha256']==bindings['ready']['source_sha256']
                and [row['object_id'] for row in public_binding['objects']]==expected_ids
                and public_binding['capture_scope']=='selected_objects'
                and public_binding['candidate_count']==14 and public_binding['selected_count']==len(selected)
                and body['unit']=='m' and body['coordinate_frame']=='world')
            boxes = body['facts']['aabb']
            expected_boxes = []
            for name in selected:
                points = raw[name]['vertices_world']
                low = [min(point[axis] for point in points) for axis in range(3)]
                high = [max(point[axis] for point in points) for axis in range(3)]
                expected_boxes.append({'status':'measured','value':{'min':low,'max':high,
                    'dimensions':[b-a for a,b in zip(low,high)]}})
            task['aabb_passed'] = boxes==expected_boxes
            if len(body['pairs'])!=len(candidates):
                raise ValueError('public_pair_count_mismatch')
            for index,(candidate,reference,row) in enumerate(zip(candidates,references,body['pairs'])):
                pair = check_pair(row,raw[target],raw[candidate],reference,witness)
                pair.update(candidate=candidate,candidate_index=index,
                    selector_passed=row['candidate_index']==index and row['object_id']==names[candidate])
                pair['full_pass'] = pair['full_pass'] and pair['selector_passed']
                task['pairs'].append(pair)
            expected_nearest = 'Peer_000' if label=='assembly_task' else 'Control_B'
            summary = body['summary']
            task['public_summary'] = summary
            task['nearest_passed'] = (summary['nearest_separated_complete'] is True
                and summary['nearest_separated_ids']==[names[expected_nearest]])
            task['full_pass'] = (task['binding_passed'] and task['aabb_passed'] and task['nearest_passed']
                and len(task['pairs'])==len(candidates) and all(row['full_pass'] for row in task['pairs']))
        except (KeyError,TypeError,ValueError) as exc:
            task['errors'].append({'type':type(exc).__name__,'message':str(exc)})
            task['full_pass'] = False
        checks.append(task)
    return {'actual_source_binding':binding,'tasks':checks,'task_denominator':2,
        'assembly_pair_denominator':3,'control_pair_denominator':1,
        'execution_cleanup_complete':execution['harness_execution_complete'],
        'full_pass':execution['harness_execution_complete'] and all(row['full_pass'] for row in checks),
        'position_tolerance_m':POSITION_TOLERANCE_M,'distance_tolerance_m':DISTANCE_TOLERANCE_M,
        'oracle_path':str(ORACLE),'oracle_sha256':hashlib.sha256(ORACLE.read_bytes()).hexdigest(),
        'elapsed_ns':time.perf_counter_ns()-started,'product_calls':0,'model_calls':0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = verify(args.run.resolve())
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'full_pass':result['full_pass'],'tasks':[{'label':row['label'],'full_pass':row['full_pass']} for row in result['tasks']]}))


if __name__=='__main__':
    main()
