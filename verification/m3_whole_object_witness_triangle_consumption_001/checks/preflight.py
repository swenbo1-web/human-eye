"""Preflight the independent assessor on retained real arrays and both source routes."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys


NS = Path(__file__).resolve().parents[1]
V = NS.parent
E = run_path(str(NS/'checks/evidence.py'))
G = run_path(str(NS/'checks/score.py'))
build = run_path(str(NS/'fixture/selected.py'))['build_selected_capture']
T,D = E['T'],E['D']
read,require = T['read'],T['require']
HISTORIC = T['SOURCE']['PRIOR_RUN']
HISTORIC_BINDING = V/'m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
BINDING = V/'m3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json'


def reject(callback, reason):
    try:
        callback()
    except ValueError as err:
        require(str(err)==reason,'wrong_preflight_rejection/'+str(err))
        return reason
    raise ValueError('preflight_incorrectly_accepted/'+reason)


def historical_capture():
    oracle = run_path(str(V/'m4_cross_scale_discovery_001/oracle/check_saved.py'))
    captures,_ = oracle['decode_captures'](HISTORIC,read(HISTORIC_BINDING),oracle['Audit']())
    require(captures and len(captures[0]['meshes'])==21,'archived_f5469_current_whole_capture_missing')
    return captures[0]


def installed_pair(capture,reference,installation,*,include_new):
    from human_eye_plugin.auto_router import _validated_scene
    from human_eye_plugin.live_spatial_mcp import _tool_result
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.task_query import task_result

    ordered = (T['TARGET'],reference)
    query = {'mode':'task','objects':[{'name':name} for name in ordered],'requested_facts':['surface_proximity']}
    normal,meshes,digest = _validated_scene(capture,_task_capture=True)
    source = {'document_epoch':capture['host_identity']['document_epoch'],'capture_state':capture['capture_state']}
    producer = task_result(normal,meshes,digest,query,SpatialSceneCache(max_bytes=2*1024*1024),lambda _:None,
                           witness_capture=source if include_new else None)
    producer['binding']['runtime_source_sha256'] = installation['source_sha256']
    producer['trace_id'] = 'offline-verified-shape-only'
    return _tool_result(producer,is_error=False,response_detail='full'),producer


def formal_route(source, point_proofs, *, alternatives):
    reference_labels = list(T['REFERENCES'])
    answer = ['All distances are in metres and points are world coordinates.',
              'For 2.5 m M19 falls short, M14 qualifies, and M16 to M19 is closer.']
    claims = {'pairs':{},'units':{'distance_unit':'m','point_coordinate_frame':'world','quote':answer[0]},
              'threshold':{'metres':2.5,'M19_meets':False,'M14_meets':True,'closer_reference':'M19','quote':answer[1]}}
    for label in reference_labels:
        proved = point_proofs[label]
        expect = T['establish'](source,label)
        if alternatives:
            original = expect['alternative_point_pairs'][0]
            points_a,points_b=original['a'],original['b']
            indices = {side:row['exact_source_triangle_indices'] for side,row in original['memberships'].items()}
        else:
            points_a,points_b=proved['a'],proved['b']
            indices = {side:[row['source_triangle_index']] for side,row in proved['source_evidence']['ordered_endpoints'].items()}
        scope = f"M16 whole surface to {label} whole surface"
        distance = f"{label} {expect['distance_m']} {expect['direction_a_to_b']}"
        pair = f"{label} {points_a} {points_b} {indices}"
        answer.extend((scope,distance,pair))
        claims['pairs'][label] = {'target':'M16','reference':label,'scope':'whole_objects',
            'distance_m':expect['distance_m'],'direction_a_to_b':expect['direction_a_to_b'],'a':points_a,'b':points_b,
            'source_triangle_indices':indices,'quotes':{'scope':scope,'distance_direction':distance,
            'point_pair_and_faces':pair}}
    typed = '\n'.join(answer)
    scene = {'scene_unchanged':True,'owned_close_verified':True}
    correct = G['grade_claims'](typed,claims,source,read_only_proof=scene)
    require(correct['all_quality_passed'] and correct['score']==correct['planned']==7,
            'valid_equivalent_formal_source_route_preflight_failed')
    wrong = deepcopy(claims)
    wrong['pairs']['M19']['source_triangle_indices']['a'] = [0]
    rejected = G['grade_claims'](typed,wrong,source,read_only_proof=scene)
    require(not rejected['checks']['M19_actual_point_pair_and_triangle_membership']['passed'],
            'wrong_formal_source_face_accepted')
    return {'score':correct['score'],'wrong_face_rejected':True}


def main():
    installation = read(BINDING)
    sys.path[:0] = [installation['install_root'],installation['dependency_root']]
    current = read(T['SOURCE']['PRIOR_TERMINAL'])
    pair_captures = {name:build(historical_capture(),name) for name in T['REFERENCES']}
    proofs = {}
    for mode in (False,True):
        ordinary_pairs = {name:installed_pair(capture,name,installation,include_new=mode)
                          for name,capture in pair_captures.items()}
        passed = E['verify_qualification'](HISTORIC,
            {name:pair[0] for name,pair in ordinary_pairs.items()},
            {name:pair[1] for name,pair in ordinary_pairs.items()},pair_captures,binding=installation,
            require_source=mode,source=current)
        proofs['evidence' if mode else 'standard'] = passed
    candidate_reply,candidate_producer = ordinary_pairs['M19']
    capture = pair_captures['M19']
    reversed_order = deepcopy(candidate_producer)
    reversed_order['binding']['objects'].reverse()
    reply = deepcopy(candidate_reply)
    reply['content'][0]['text'] = D['wire_text'](reversed_order)
    wrong_order = reject(lambda:E['verify_pair']('M19',reply,reversed_order,capture,current,installation,require_source=True),
                         'public_whole_pair_scope_order_or_producer_identity_changed/M19')
    stale = deepcopy(capture)
    stale['capture_state']['revision'] += 1
    wrong_stale = reject(lambda:D['verify_witness'](stale,candidate_producer),
                         'triangle_source_reference_not_same_capture_generation_or_domain')
    changed = deepcopy(capture)
    changed['host_identity']['object_instances'][candidate_producer['binding']['objects'][0]['object_id']] += '-changed'
    wrong_instance = reject(lambda:D['verify_witness'](changed,candidate_producer),
                             'triangle_source_reference_not_same_current_ordered_object_instance/a')
    print(json.dumps({'passed':True,'qualification_shapes':proofs,'exact_offline_source':T['frozen_truth']()['assets'],
         'actual_new_blender':0,'actual_new_models':0,'actual_new_rasters':0,
         'scope':'installed archived task solver and formatter, derived exact selected capture shape only',
         'formal_grading_routes':{'direct_from_bound_installed_source_packet':formal_route(current,passed['pairs'],alternatives=False),
                                 'independent_equivalent_point_and_face_lookup':formal_route(current,passed['pairs'],alternatives=True)},
         'wrong_instance_reverse_and_stale_rejected':[wrong_instance,wrong_order,wrong_stale]},
         ensure_ascii=False,allow_nan=False,indent=2))


if __name__=='__main__':
    main()
