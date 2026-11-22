"""Replay six installed solves and exercise the independent assessor offline."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys


NS = Path(__file__).resolve().parents[1]
V = NS.parent
E = run_path(str(NS/'checks/evidence.py'))
G = run_path(str(NS/'checks/score.py'))
T = E['T']
read,require = T['read'],T['require']
HISTORIC = T['PREVIOUS']['PRIOR_RUN']
HISTORIC_BINDING = V/'m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
BINDING = V/'m1_source_region_no_image_measurement_packet_001/install/PRODUCT_RUN_BINDING.json'


def rejects(call,reason):
    try:
        call()
    except ValueError as error:
        require(str(error)==reason,'wrong_control_rejection/'+str(error))
        return reason
    raise ValueError('control_unexpectedly_accepted/'+reason)


def retained_capture():
    oracle = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    captures,_ = oracle['decode_captures'](HISTORIC,read(HISTORIC_BINDING),oracle['Audit']())
    require(captures and len(captures[0]['meshes'])==21,'original_complete_scene_capture_required')
    return captures[0]


def installed_case(case, requests, capture, installed):
    from human_eye_plugin.auto_router import _validated_scene
    from human_eye_plugin.live_spatial_mcp import _tool_result
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.source_region import measure_region,observe_region,prepare_region
    from human_eye_plugin.task_query import task_result

    selected_query,whole_query = (requests[field]['query'] for field in ('qa_selected','qa_whole'))
    prep = prepare_region(capture,selected_query)
    producer = observe_region(prep,None,include_image=False)
    producer['binding'].update(runtime_source_sha256=installed['source_sha256'],
        source_status='loaded_generation',disk_status='disk_not_checked',source_check_scope='bound_generation_identity')
    producer['task_result'] = measure_region(prep,selected_query['reference'],None)
    producer['task_result']['binding'] = deepcopy(producer['binding'])
    producer['session_id'] = 'offline-case-'+case
    selected = _tool_result(producer,is_error=False,response_detail='brief',observation_task_query=selected_query)
    by_name = {row['name']:row for row in capture['meshes']}
    objects = [by_name[item['name']] for item in whole_query['objects']]
    ids = {row['object_id'] for row in objects}
    subset = {**deepcopy(capture),'meshes':objects,'capture_scope':'selected_objects',
              'host_identity':{**capture['host_identity'],'capture_scope':'selected_objects',
                'object_instances':{key:value for key,value in capture['host_identity']['object_instances'].items()
                                    if key in ids}},
              'task_selection':{'selectors':whole_query['objects'],'bindings':[
                  {'object_id':row['object_id'],'name':row['name']} for row in objects],
                  'pair_reason':None,'candidate_count':len(by_name)}}
    normal,meshes,digest = _validated_scene(subset,_task_capture=True)
    whole_producer = task_result(normal,meshes,digest,whole_query,SpatialSceneCache(max_bytes=2*1024*1024),lambda _:None)
    whole_producer['binding']['runtime_source_sha256'] = installed['source_sha256']
    whole = _tool_result(whole_producer,is_error=False,response_detail='brief')
    return selected,producer,whole,whole_producer,subset


def native_evidence(source, expected, *, alternative=False):
    payload = {'meshes':{},'measurements':{},'unit':'m','coordinate_frame':'world'}
    for case, config in T['SCENARIOS'].items():
        payload['measurements'][case] = {}
        for name in (config['target'],config['reference']):
            item = T['objects'](source)[name]['evaluated']
            payload['meshes'][name] = {'vertices':item['vertices_world_m'],'faces':item['triangles']}
        for scope in T['SCOPES']:
            result = expected[case][scope]
            options = result['other_verified_attaining_pairs']
            witness = options[0] if alternative and options else result['attaining_point_pair']
            payload['measurements'][case][scope] = {'distance_m':result['distance_m'],
                'direction_a_to_b':result['direction_a_to_b'],'a':witness['a'],'b':witness['b'],
                'source_triangle_indices':{side:proof['exact_source_triangle_indices']
                                           for side,proof in witness['memberships'].items()}}
    return payload


def exercise_formal(source, payload):
    verified = {}
    for case, config in T['SCENARIOS'].items():
        # These clearly labelled artificial answer strings exercise only the
        # grading adapter. No runtime model observation is being used.
        selected = f"{config['target']} selected {config['selected']} to {config['reference']} complete surface."
        whole = f"{config['target']} whole to {config['reference']} whole."
        units = 'All distances are in metres and points are world coordinates.'
        threshold = f"At {config['threshold_m']} m, selected qualifies and whole is below the threshold."
        answer = [selected,whole,units,threshold]
        claims = {'units':{'distance_unit':'m','point_coordinate_frame':'world','quote':units},
                  'threshold':{'metres':config['threshold_m'],'selected_meets':True,'whole_meets':False,
                               'quote':threshold},'measurements':{}}
        for scope,route in (('selected',selected),('whole',whole)):
            item = payload['measurements'][case][scope]
            dist = f"{scope} {item['distance_m']} {item['direction_a_to_b']}"
            points = f"{scope} {item['a']} {item['b']} {item['source_triangle_indices']}"
            answer.extend((dist,points))
            claims['measurements'][scope] = {**item,
                'target':config['target'],'reference':config['reference'],
                'scope':'selected_source_triangle_union' if scope=='selected' else 'whole_objects',
                'reference_scope':'whole_object','selected_faces':config['selected'] if scope=='selected' else None,
                'quotes':{'scope':route,'distance_direction':dist,'point_pair_and_faces':points}}
        proof = {'scene_unchanged':True,'owned_close_verified':True}
        final = '\n'.join(answer)
        accepted = G['grade_claims'](case,final,claims,source,read_only_proof=proof)
        require(accepted['score']==accepted['planned']==7 and accepted['all_quality_passed'],
                'valid_formal_scope_or_real_alternative_witness_rejected/'+case)
        scope_bad = deepcopy(claims)
        scope_bad['measurements']['selected']['scope']='whole_objects'
        rejected = G['grade_claims'](case,final,scope_bad,source,read_only_proof=proof)
        require(not rejected['checks']['ordered_selected_and_whole_scope']['passed'],
                'wrong_formal_scope_accepted/'+case)
        verified[case] = {'quality':'7/7','wrong_scope_rejected':True}
    return verified


def main():
    installed = read(BINDING)
    sys.path[:0] = [installed['install_root'],installed['dependency_root']]
    source = read(T['PREVIOUS']['PRIOR_TERMINAL'])
    actual = retained_capture()
    expected = read(NS/'fixture/TRUTH.json')['measurements']
    certified = {}
    for values in read(NS/'inputs/CASES.json'):
        case = str(values['id'])
        p,prod,w,whole,subset = installed_case(case,values,actual,installed)
        certified[case] = E['verify_product_case'](case,HISTORIC,p,prod,w,whole,binding=installed,
                               source=source,selected_capture=actual,whole_capture=subset)
    own = native_evidence(source,expected)
    other = native_evidence(source,expected,alternative=True)
    native = {case:E['verify_native_case'](case,source,own) for case in T['SCENARIOS']}
    alternate = {case:E['verify_native_case'](case,source,other) for case in T['SCENARIOS']}
    name_bad = deepcopy(own)
    name_bad['meshes'].pop('M19')
    wrong_name = rejects(lambda:E['verify_native_case']('2',source,name_bad),'native_declared_wrong_name_scope_unit_or_reference')
    face_bad = deepcopy(own)
    face_bad['measurements']['2']['selected']['source_triangle_indices']['a']=[0]
    wrong_face = rejects(lambda:E['verify_native_case']('2',source,face_bad),
                         'native_current_surface_pair_or_report_not_independently_attained/selected')
    scope_bad = deepcopy(own)
    scope_bad['measurements']['2']['selected']=scope_bad['measurements']['2']['whole']
    wrong_scope = rejects(lambda:E['verify_native_case']('2',source,scope_bad),
                          'native_current_surface_pair_or_report_not_independently_attained/selected')
    print(json.dumps({'passed':True,'product':certified,'independent_native_shape':native,
                      'independent_alternate_witnesses':alternate,'actual_models':0,'actual_new_Blender':0,
                      'actual_new_rasters':0,'formal_scorer':exercise_formal(source,other),
                      'wrong_name_wrong_face_wrong_scope':[wrong_name,wrong_face,wrong_scope],
                      'offline_source_scope':'selected object captures derived from intact actual archived evaluated arrays'},
                      ensure_ascii=False,allow_nan=False,indent=2))


if __name__=='__main__':
    main()
