"""Untimed actual installed-library holdouts and shared-call cache controls."""
from collections import Counter
from contextlib import contextmanager
from fractions import Fraction as Q
from pathlib import Path
import argparse
import json
import sys
import traceback

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import RAW,dump,installation,need,pin,read,verify


@contextmanager
def observe_tree(evidence):
    """Observe existing function locals only; never change an evaluator option."""
    counts=Counter()
    def callback(frame,event,arg):
        if event!='return' or frame.f_globals.get('__name__')!='human_eye_plugin.surface_proximity':return
        name=frame.f_code.co_name;v=frame.f_locals
        if name=='push_pair' and 'secondary'in v:
            counts['actual_enqueue_returns']+=1
            if v.get('contained_zero_fifo') and v.get('key')==0:
                counts['fifo_zero_key_enqueues']+=1
                if v.get('cdist')!=0:counts['changed_secondary_enqueues']+=1
                need(v['secondary']==0,'actual_candidate_FIFO_secondary')
        if name=='_nearest_tree' and 'roots'in v:
            roots=v['roots'];bounds=[[list(root[0]),list(root[1])] for root in roots]
            strict=any(all(bounds[a][0][k]<bounds[b][0][k] and bounds[b][1][k]<bounds[a][1][k] for k in range(3)) for a,b in ((0,1),(1,0)))
            evidence.append({'integer_root_bounds':bounds,'shift':v.get('shift'),
                'strict_containment_independent':strict,'eligible_independent':strict and v.get('shift')==0,
                'actual_C_guard':v.get('contained_zero_fifo'),'best_pair':v.get('best_pair')})
    previous=sys.getprofile();sys.setprofile(callback)
    try:yield counts
    finally:sys.setprofile(previous)


def main(plan_path,arm,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    plan=read(plan_path);result={'status':'failed','arm':arm,'plan':pin(plan_path),'cases':[],
        'performance_samples':False,'Blender':0,'models':0,'native_calls':0}
    try:
        for ref in plan['sources'].values():verify(ref)
        install=installation(arm);need(install==plan['arms'][arm],'frozen_installation')
        sys.path.insert(0,install['site'])
        from human_eye_plugin import surface_proximity as kernel
        from human_eye_plugin import task_query
        from human_eye_plugin.active_observation_images import _meshes_from_objects
        from human_eye_plugin.scene_cache import SpatialSceneCache
        from human_eye_plugin.live_service import LiveSpatialService
        from human_eye_plugin.runtime_identity import runtime_identity
        identity=runtime_identity(mode='live');need(identity['source_sha256']==install['identity']['source_sha256'],'actual_loaded_identity')
        result.update(installation=install,loaded_identity=identity,
            module_origins={m.__name__:str(Path(m.__file__).resolve()) for m in (kernel,task_query)})
        config={'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':install['site'],
            'state_file':str(output/'STATE.json'),'audit_file':str(output/'AUDIT.jsonl'),'request_budget_s':30.0,
            'expected_identity':{'source_sha256':identity['source_sha256']}}
        dump(output/'CONFIG.json',config);service=LiveSpatialService(output/'CONFIG.json',host=object())
        def stats(cache):return {k:v for k,v in cache.stats().items() if k not in ('estimated_compute_ms_avoided','savings_basis')}
        def meshes(case,changed=False):
            objects=[]
            for side in ('left','right'):
                mesh=case[side];vertices=mesh['vertices_world']
                if changed and side=='right':vertices=[[v[0],v[1],v[2]+1/64] for v in vertices]
                objects.append((vertices,mesh['faces'],(case['case_id'],side),mesh['name']))
            return _meshes_from_objects(objects)
        for case_id in plan['case_order']:
            ref=plan['cases'][case_id];verify(ref);case=read(ref['path']);left,right=meshes(case)
            row={'case_id':case_id,'input':ref,'truth_kind':'independent exact analytic' if case.get('independent_truth') else '041 formal cross-reference only',
                 'direct':{},'routes':[]}
            tree=[];holder={};work={}
            with service._request_budget(),observe_tree(tree) as enqueue:
                value=kernel.measure_surface_proximity(left,right,service._check_request_budget,
                    diagnostics=work,retain_witness_triangles=True,_prepared_holder=holder)
            dump(output/(case_id+'_DIRECT_RAW.json'),{'value':value,'work':work,'tree_evidence':tree,'enqueue_observation':dict(enqueue)})
            need(value.get('measurement_valid') is True,'direct_surface_success')
            exact=value.get('exact_witness_triangles')
            winner=value['witness_triangle_indices'] if exact is None else exact['indices']
            native=[case['left']['native_triangle_rows'][winner[0]],case['right']['native_triangle_rows'][winner[1]]]
            row['direct']={'value':value,'work':work,'native_pair':native,'tree_evidence':tree,'enqueue_observation':dict(enqueue)}
            dump(output/(case_id+'_DIRECT.json'),row['direct'])
            wanted=case.get('independent_truth') or case['expected_surface']
            distance=float(Q(wanted['distance_exact_m'])) if 'distance_exact_m'in wanted else wanted['distance_m']
            need(value['distance_m'].hex()==distance.hex(),'direct_fixed_distance')
            for key,field in (('point_a_m','point_a_world'),('point_b_m','point_b_world'),('direction_a_to_b','direction_a_to_b')):
                if key in wanted:need(value[field]==wanted[key],'direct_frozen_'+key)
            if 'canonical_native_pair'in wanted:need(native==wanted['canonical_native_pair'],'direct_canonical_native_pair')
            if arm=='C':
                need(all(t['actual_C_guard']==t['eligible_independent'] for t in tree),'candidate_actual_guard_matches_integer_roots')
            for requested in (['spatial_relation','closed_solid_relation','surface_proximity'],['closed_solid_relation','surface_proximity']):
                cache=SpatialSceneCache();calls=[];source={'case_id':case_id,'input_sha256':ref['sha256']}
                for label in ('first','repeat'):
                    diagnostics={}
                    with service._request_budget():
                        facts,surface=task_query._closed_surface_facts(left,right,set(requested),cache,service._check_request_budget,source,diagnostics)
                    need(facts['surface_proximity']['status']=='measured','compound_surface_success')
                    need(facts['surface_proximity']['value']['distance_m'].hex()==distance.hex(),'compound_fixed_distance')
                    calls.append({'label':label,'facts':facts,'surface':surface,'diagnostics':diagnostics,'cache_stats':stats(cache)})
                need(calls[0]['facts']==calls[1]['facts'],'repeat_detached_public_facts')
                if 'spatial_relation'in requested and calls[0]['facts']['spatial_relation']['status']=='unknown':
                    need(calls[1]['diagnostics']['spatial_pair_cache_hit'] is False,'unknown_spatial_bundle_not_cached')
                if 'spatial_relation'not in requested and calls[0]['facts']['closed_solid_relation']['status']=='unknown':
                    need(calls[1]['diagnostics']['closed_solid_pair_cache_hit'] is False,'unknown_closed_result_not_cached')
                    need(calls[1]['diagnostics']['surface_pair_cache_hit'] is True,'independent_valid_surface_subresult_reused')
                if case_id=='control_closed_nested_cubes':
                    need(calls[0]['facts']['closed_solid_relation']['status']=='measured' and calls[0]['facts']['closed_solid_relation']['value']=='penetrating','analytic_positive_volume_containment')
                    hitkey='spatial_pair_cache_hit' if 'spatial_relation'in requested else 'surface_pair_cache_hit'
                    need(calls[1]['diagnostics'][hitkey] is True,'successful_compound_surface_reuse')
                # Keep the actual first/repeat unknowns and which subresults are
                # memoized. Never require a failed spatial bundle to be cached.
                detached=calls[1]['facts'];detached['surface_proximity']['value']['distance_m']=-123.0
                diagnostics={}
                with service._request_budget():
                    facts,surface=task_query._closed_surface_facts(left,right,set(requested),cache,service._check_request_budget,source,diagnostics)
                need(facts['surface_proximity']['value']['distance_m'].hex()==distance.hex(),'returned_fact_mutation_cannot_change_memo')
                calls[1]['facts']=facts
                calls.append({'label':'detached_result_mutation_probe','facts':facts,'surface':surface,
                              'diagnostics':diagnostics,'cache_stats':stats(cache)})
                if case_id in ('Yanyite_high','control_closed_nested_cubes'):
                    moved_left,moved_right=meshes(case,True);diagnostics={}
                    with service._request_budget():
                        changed,changed_surface=task_query._closed_surface_facts(moved_left,moved_right,set(requested),cache,service._check_request_budget,source,diagnostics)
                    expected=distance+1/64 if case_id=='Yanyite_high' else None
                    if expected is not None:need(changed['surface_proximity']['value']['distance_m'].hex()==expected.hex(),'exact_geometry_change_invalidation_answer')
                    hitkey='spatial_pair_cache_hit' if 'spatial_relation'in requested else 'surface_pair_cache_hit'
                    need(diagnostics[hitkey] is False,'geometry_change_must_miss')
                    calls.append({'label':'control_only_reference_translation_1_64','facts':changed,'surface':changed_surface,'diagnostics':diagnostics,'cache_stats':stats(cache)})
                row['routes'].append({'requested_facts':requested,'calls':calls,'detached_cache_proof':True})
            result['cases'].append(row);dump(output/(case_id+'.json'),row)
        result['status']='pass'
    except BaseException:
        result['error']=traceback.format_exc()
        if 'row'in locals():result['partial_case']=row
    dump(output/'RESULT.json',result);print(json.dumps({'status':result['status'],'result':pin(output/'RESULT.json')}),flush=True)
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--plan',default=str(RAW/'PLAN.json'));parser.add_argument('--arm',choices=('A','B','C'),required=True);parser.add_argument('--output',required=True)
    a=parser.parse_args();raise SystemExit(main(a.plan,a.arm,a.output))
