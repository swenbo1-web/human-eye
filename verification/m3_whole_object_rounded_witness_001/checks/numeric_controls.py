"""Focused original-publication and bounded rational-witness controls."""

import argparse
from copy import deepcopy
from math import isclose
from pathlib import Path
from runpy import run_path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
K = run_path(str(HERE/'kernel_batch.py'))
V = HERE.parents[1]
P = run_path(str(V/'m3_whole_object_witness_triangle_001/checks/controls.py'))
check,read,write = (K[key] for key in ('require','read','write'))


def measure(surface,pair):
    return surface.measure_surface_proximity(*pair, lambda _:None, retain_witness_triangles=True)


def cases():
    a = [(0,0,0),(-1,0,0),(0,-1,0)]
    b = [(1,0,0),(0,1,0),(0,0,1)]
    slant = (P['make_mesh']('A',[a]),P['make_mesh']('B',[b]))
    a2 = [(-2,2,0),(-6,-4,10),(2,-4,2)]
    b2 = [(-1,-5,9),(-5,1,7),(3,1,-1)]
    both = (P['make_mesh']('A',[a2]),P['make_mesh']('B',[b2]))
    return slant, both


def case_record(surface, pair, expected_square, points, displayed_members, candidate):
    result,winner,clock=K['original_winner_measure'](surface,pair)
    check(winner==[0,0] and 'witness_triangle_indices' not in result
          and isclose(result['distance_m']**2,float(K['F'](expected_square)),rel_tol=0,abs_tol=1e-14),
          'analytic_support_plane_distance_or_original_winner_changed')
    rounded=[result['point_a_world'],result['point_b_world']]
    check([K['contains'](point,mesh.vertices[mesh.faces[0]])
           for mesh,point in zip(pair,rounded,strict=True)]==displayed_members,
           'registered_single_or_both_side_display_miss_unreproduced')
    proof=K['candidate_extension'](result)
    if candidate:
        check(proof=={'indices':[0,0],'points':points}
              and K['packet_checks'](pair,result,winner,proof)==expected_square,
              'exact_analytic_source_triangle_certificate_or_points_changed')
    else:
        check(proof is None,'original_kernel_unexpected_rational_field')
    return {'result':result,'winner':winner,'verified_exact_m2':expected_square,'duration_ns':clock}


def synthetic_controls(surface,candidate):
    slant,both=cases()
    known=[
        ('one_third_forward',slant,'1/3',[['0','0','0'],['1/3','1/3','1/3']],[True,False]),
        ('one_third_reverse',slant[::-1],'1/3',[['1/3','1/3','1/3'],['0','0','0']],[False,True]),
        ('both_endpoints_round_outside',both,'3',[['-14/3','-2','20/3'],['-11/3','-1','23/3']],[False,False]),
    ]
    report={lab:case_record(surface,pair,square,points,flags,candidate)
            for lab,pair,square,points,flags in known}
    old=P['kernel_cases']()
    for lab in ('linear_later_nonimprovement_not_AABB_pruned','linear_later_exact_tie_keeps_first',
                'tree_many_equal_pairs_select_original_lowest','tree_reverse_order_and_direction',
                'zero_real_vertex_contact','zero_collinear_face_contact','degenerate_point_face_has_bound_witness'):
        pair,metric,indices=old[lab]
        result,winner,elapsed=K['original_winner_measure'](surface,pair)
        check(result['distance_m']==metric and winner==indices and result['witness_triangle_indices']==indices
              and K['candidate_extension'](result) is None,'strict_candidate_scope_changed/'+lab)
        K['packet_checks'](pair,result,winner,None)
        if lab.startswith('tree'):
            check(result['work']['tree_builds']==2 and result['work']['node_pair_visits']>1,'tree_control_not_reached')
        report[lab]={'result':result,'winner':winner,'duration_ns':elapsed}
    original_precision=measure(surface,old['translation_causes_original_display_precision_refusal'][0])
    check(original_precision['measurement_valid'] and original_precision['witness_status']=='unknown'
          and original_precision['witness_reason']=='original_surface_witness_precision_exceeded'
          and not any(x in original_precision for x in ('witness_triangle_indices','exact_witness_triangles')),
          'old_world_point_precision_failure_now_released_source')
    report['old_world_point_precision_failure']={'result':original_precision}
    with patch.object(surface,'MAX_NARROW_PHASE_PAIRS',0):
        exhausted=measure(surface,slant)
    check(not exhausted['measurement_valid'] and exhausted['reason']=='surface_pair_budget'
          and 'exact_witness_triangles' not in exhausted,'original_search_budget_failure_now_released_exact_source')
    report['original_search_budget']={'result':exhausted}
    if candidate:
        opt=report['one_third_forward']['result']
        without_exact=opt['work']['work_units']-opt['work']['exact_witness_triangle_checks']
        with patch.object(surface,'MAX_WORK_UNITS',without_exact+1):
            low=measure(surface,slant)
        check(low['measurement_valid'] and low['witness_status']=='measured' and low['distance_m']==opt['distance_m']
              and low['work']['exact_witness_triangle_checks']==1 and 'exact_witness_triangles' not in low,
              'exact_provenance_partial_budget_published_or_changed_original_measurement')
        report['exact_provenance_half_budget']={'result':low}
        with patch.object(surface,'MAX_EXACT_SOURCE_BYTES',12):
            exact_fit=measure(surface,slant)
        with patch.object(surface,'MAX_EXACT_SOURCE_BYTES',11):
            small=measure(surface,slant)
        check(K['candidate_extension'](exact_fit) is not None and small['measurement_valid'] and small['witness_status']=='measured'
              and K['candidate_extension'](small) is None and 'witness_triangle_indices' not in small,
              'truncated_or_oversize_exact_certificate_published')
        report['exact_provenance_size_cap']={'fitting_result':exact_fit,'result':small,'refusal_limit_coordinate_bytes':11}
    return report


def bvh_holdout(surface,candidate):
    source=Path('D:/he_m4_cross_scale_assembly_transfer_001/slots/P1/TERMINAL_SOURCE.json')
    pin=K['pin'](source,'d0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90')
    packet=read(source)
    mesh=K['meshes']({row['name']:{'vertices_world':row['evaluated']['vertices_world_m'],
                                         'triangles':row['evaluated']['triangles']}
                      for row in packet['objects'] if row['name'] in ('N02','N03')})
    pair=mesh['N02'],mesh['N03']
    check(tuple(len(x.faces) for x in pair)==(44,12),'fixed_BVH_holdout_size_changed')
    result,winner,timing=K['original_winner_measure'](surface,pair)
    proof=K['candidate_extension'](result)
    square=K['packet_checks'](pair,result,winner,proof)
    check(bool(proof)==candidate and winner==[38,3] and result['distance_m']==0.21368990032710758
          and result['work']['node_pair_visits']==99 and result['work']['tree_builds']==2,
          'BVH_holdout_winner_distance_branch_or_proofs_changed')
    return {'names':['N02','N03'],'result':result,'winner':winner,'exact_world_distance_squared_m2':square,
            'installed_kernel_with_winner_receipt_ns':timing,'source':pin}


def service_controls(candidate,out,project):
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer

    class TestHost(P['TestHost']):
        def capture_scene(self):
            scoped = self.capture_task_scene(P['AB'])
            scoped['capture_scope']='complete_scene_meshes'
            scoped['host_identity']['capture_scope']='complete_scene_meshes'
            scoped['host_identity']['document_epoch']='1'*64
            scoped['revision']='complete-analytic-capture'
            scoped.pop('task_selection')
            return scoped

    host=TestHost()
    slant,_=cases()
    host.meshes=[P['make_mesh'](name,[list(map(tuple,mesh.vertices))],label=label).to_dict()
                 for name,label,mesh in zip(('a','b'),('A','B'),slant,strict=True)]
    config=out/'CONTROL_CONFIG.json'
    write(config,{'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':str(project),
                  'state_file':str(out/'state.json'),'audit_file':str(out/'audit.jsonl'),'request_budget_s':30})
    service=LiveSpatialService(config,host=host)
    standard=LiveSpatialMCPServer(service,'rational-proof')
    evidence=LiveSpatialMCPServer(service,'rational-proof',region_task_evidence=True)
    pair={'mode':'task','objects':P['AB'],'requested_facts':['surface_proximity']}
    selection={'mode':'source_region','region':{'object':{'name':'A'},'source_triangle_indices':[0]},
               'reference':{'name':'B'},'requested_facts':['surface_proximity']}
    rows={}

    def probe(label, server=evidence, query=pair, *, exact=False, error=False, image=False):
        import json
        req={'jsonrpc':'2.0','id':label,'method':'tools/call','params':{'name':'human_eye_scene_observe',
              'arguments':{'include_image':image,'query':deepcopy(query)}}}
        response=server.handle_jsonrpc_message(req)['result']
        check(response['isError'] is error and len(response['content'])==1 and response['content'][0]['type']=='text',
              'wrong_public_gate_or_unrequested_image/'+label)
        body=json.loads(response['content'][0]['text'])
        call=body.get('task_result',body)
        fact=call.get('facts',{}).get('surface_proximity',{})
        witness=(fact.get('value') or {}).get('nearest_witness',{})
        result=witness.get('exact_source_triangles')
        check(bool(result)==(candidate and exact) and 'source_triangles' not in witness,
              'exact_fallback_crossed_existing_mode_or_strict_scope/'+label)
        if result is not None:
            check(result['a']['point_m']==['0','0','0'] and result['b']['point_m']==['1/3','1/3','1/3']
                  and result['a']['source_triangle_index']==result['b']['source_triangle_index']==0
                  and (result['a']['instance_id'],result['b']['instance_id'])==('101','102')
                  and result['capture_state']['revision']==host.generation,'wrong_exact_public_generation_or_endpoints')
        rows[label]={'body':body,'captures':len(host.selected_calls),'JSON_UTF8_bytes':len(response['content'][0]['text'].encode())}

    probe('standard_before_evidence',standard)
    probe('opt_in_cold',exact=True)
    probe('opt_in_warm',exact=True)
    probe('standard_after_evidence',standard)
    probe('source_selection_is_not_whole',evidence,selection)
    probe('unrequested_image_is_rejected',evidence,pair,error=True,image=True)
    check(rows['unrequested_image_is_rejected']['captures']==rows['source_selection_is_not_whole']['captures'],
          'image_rejection_used_host')
    host.generation+=1
    probe('next_generation_is_checked',exact=True)
    host.versioned=False
    probe('unbound_capture_does_not_publish')
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path,default=K['REFERENCE'])
    parser.add_argument('--candidate',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    check(sys.flags.isolated and sys.dont_write_bytecode,'use_frozen_interpreter_I_B')
    surface,identity=K['installed'](args.binding)
    out=args.output.resolve()
    out.mkdir(parents=True)
    synthetic=synthetic_controls(surface,args.candidate)
    write(out/'KERNEL.json',{'identity':identity,'synthetic':synthetic,'actual_BVH_holdout':bvh_holdout(surface,args.candidate)})
    service=service_controls(args.candidate,out,Path(read(args.binding)['install_root']))
    write(out/'SERVICE.json',service)
    print(f'{len(synthetic)} numerical controls plus actual BVH, {len(service)} service controls passed')


if __name__=='__main__':
    main()
