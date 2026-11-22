"""Exercise the frozen scorer on retained Blender source without opening a new scene."""

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


def rejects(call, reason):
    try:
        call()
    except ValueError as error:
        require(str(error)==reason,'different_control_rejection/'+str(error))
        return reason
    raise ValueError('control_was_not_rejected/'+reason)


def retained_capture():
    oracle = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    historical = read(V/'m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json')
    captures,_ = oracle['decode_captures'](T['PRIOR_RUN'],historical,oracle['Audit']())
    require(captures and len(captures[0]['meshes'])==21,'frozen_whole_scene_host_packet_missing')
    return captures[0]


def raw_product_shapes(capture, installed):
    """Use the installed solves and display formatter with no open Blender dependency."""
    from human_eye_plugin.auto_router import _validated_scene
    from human_eye_plugin.live_spatial_mcp import _tool_result
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.source_region import measure_region,observe_region,prepare_region
    from human_eye_plugin.task_query import task_result

    selected_query = read(NS/'inputs/QUALIFICATION_SELECTED.json')['query']
    whole_query = read(NS/'inputs/QUALIFICATION_WHOLE.json')['query']
    prep = prepare_region(capture,selected_query)
    producer = observe_region(prep,None,include_image=False)
    producer['binding'].update(runtime_source_sha256=installed['source_sha256'],
        source_status='loaded_generation',disk_status='disk_not_checked',source_check_scope='bound_generation_identity')
    producer['task_result'] = measure_region(prep,selected_query['reference'],None)
    producer['task_result']['binding'] = deepcopy(producer['binding'])
    producer['session_id'] = 'offline-archived-checker-preflight'
    selected = {detail:_tool_result(producer,is_error=False,response_detail=detail,observation_task_query=selected_query)
                for detail in ('full','brief')}

    # The selected-object capture is explicitly a derived replay of the same two
    # intact object rows. The live qualification has its own actual host packet.
    by_name = {row['name']:row for row in capture['meshes']}
    target_meshes = [by_name[name] for name in ('M15','M14')]
    ids = {row['object_id'] for row in target_meshes}
    subset = {**deepcopy(capture),'meshes':target_meshes,'capture_scope':'selected_objects',
              'host_identity':{**capture['host_identity'],'capture_scope':'selected_objects',
                 'object_instances':{key:value for key,value in capture['host_identity']['object_instances'].items()
                                     if key in ids}},
              'task_selection':{'selectors':whole_query['objects'],'bindings':[
                  {'object_id':row['object_id'],'name':row['name']} for row in target_meshes],
                  'pair_reason':None,'candidate_count':len(by_name)}}
    normal,meshes,digest = _validated_scene(subset,_task_capture=True)
    whole = task_result(normal,meshes,digest,whole_query,SpatialSceneCache(max_bytes=2*1024*1024),lambda _:None)
    whole['binding']['runtime_source_sha256'] = installed['source_sha256']
    whole_reply = _tool_result(whole,is_error=False,response_detail='brief')
    return producer,selected,subset,whole,whole_reply


def formal_shapes(source):
    answer = ('M15 selected 6,7 to all of M14, sqrt(153)/4 metres, direction -4/sqrt(17),0,-1/sqrt(17)\n'
              'M15 whole to M14 whole, sqrt(13)/4 metres, direction -2/sqrt(13),0,-3/sqrt(13)\n'
              'The selected passes 2 metres and the whole fails 2 metres.')
    variants = []
    for n in range(2):
        text = answer
        claims = {'measurements':{},'threshold':{'metres':2,'selected_meets':True,'whole_meets':False,
                  'quote':answer.splitlines()[2]}}
        for row,(scope,domain) in enumerate((('selected','selected_source_triangle_union'),('whole','whole_objects'))):
            proof = T['establish'](source,scope)
            chosen = proof['equivalent_attaining_pairs'][n]
            claimed_members = {side:membership['exact_source_triangle_indices']
                               for side,membership in chosen['source_memberships'].items()}
            point_quote = ' '.join(str(value) for value in (chosen['a'],chosen['b'],claimed_members))
            text += '\n'+point_quote
            claims['measurements'][scope] = {'target':'M15','reference':'M14','scope':domain,
                'reference_scope':'whole_object','selected_faces':[6,7] if scope=='selected' else None,
                'distance_m':proof['distance_m'],'direction_a_to_b':proof['unit_direction_A_to_B'],
                'a':chosen['a'],'b':chosen['b'],'source_triangle_indices':claimed_members,
                'quotes':{'scope':answer.splitlines()[row],'distance_direction':answer.splitlines()[row],
                          'point_pair_and_faces':point_quote}}
        close = {'scene_unchanged':True,'owned_close_verified':True}
        good = G['grade_claims'](text,claims,source,read_only_proof=close)
        require(good['all_quality_passed'] and good['score']==7,'formal_equivalent_point_pair_was_rejected')
        wrong = deepcopy(claims)
        wrong['measurements']['selected']['reference'] = 'M15'
        rejected = G['grade_claims'](text,wrong,source,read_only_proof=close)
        require(not rejected['checks']['ordered_selected_and_whole_scope']['passed']
                and not rejected['all_quality_passed'],'formal_wrong_same_name_not_rejected')
        wrong = deepcopy(claims)
        wrong['measurements']['selected']['scope'] = 'whole_objects'
        rejected = G['grade_claims'](text,wrong,source,read_only_proof=close)
        require(not rejected['checks']['ordered_selected_and_whole_scope']['passed']
                and not rejected['all_quality_passed'],'formal_wrong_scope_not_rejected')
        wrong = deepcopy(claims)
        wrong['measurements']['selected']['source_triangle_indices']['a'] = [0]
        rejected = G['grade_claims'](text,wrong,source,read_only_proof=close)
        require(not rejected['checks']['selected_actual_point_pair_and_triangle_membership']['passed']
                and rejected['checks']['selected_distance_and_world_direction']['passed'],
                'formal_scope_separate_source_membership_control_failed')
        variants.append({'y':claims['measurements']['selected']['a'][1],
                         'check_count':good['planned'],'passed':good['score']})
    return {'accepted_two_independent_equivalent_witnesses':variants,
            'wrong_reference_scope_and_face_rejected':True}


def main():
    source = read(T['PRIOR_TERMINAL'])
    installed = read(V/'m1_region_task_witness_image_path_001/install/PRODUCT_RUN_BINDING.json')
    sys.path[:0] = [installed['install_root'],installed['dependency_root']]
    capture = retained_capture()
    selection,forms,subset,whole,whole_reply = raw_product_shapes(capture,installed)
    accepted = {detail:E['verify_qualification'](T['PRIOR_RUN'],reply,selection,whole_reply,whole,
            binding=installed,require_compact=detail=='brief',source=source,selected_capture=capture,whole_capture=subset)
            for detail,reply in forms.items()}
    same_name = deepcopy(whole)
    same_name['binding']['objects'][1] = deepcopy(same_name['binding']['objects'][0])
    raw = deepcopy(whole_reply)
    raw['content'][0]['text'] = json.dumps(same_name)
    wrong = rejects(lambda:E['validate_whole'](raw,same_name,source,installed,capture=subset),
                    'whole_pair_does_not_use_complete_current_objects_in_request_order')
    print(json.dumps({'passed':True,'actual_new_Blender':0,'actual_new_models':0,'actual_new_images':0,
                      'mode':'offline_installed_solver_and_serializer_from_archived_world_arrays',
                      'accepted':accepted,'same_name_wrong_reference_rejected':wrong,'formal':formal_shapes(source)},
                     ensure_ascii=False,allow_nan=False,indent=2))


if __name__=='__main__':
    main()
