"""Exact-solver and public service controls over independent small geometry."""

import argparse
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from math import isclose, sqrt
from pathlib import Path
import sys
from unittest.mock import patch


DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
BASE_TRIANGLE = [(0, 0, 0), (0.5, 0, 0), (0, 0.5, 0)]
REFERENCE_FACT = ['surface_proximity']
AB = [{'name': 'A'}, {'name': 'B'}]


def check(condition, reason):
    if not condition:
        raise AssertionError(reason)


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')


def make_mesh(name, triangles, *, label=None):
    import numpy as np
    from human_eye_module1_operators import MeshEntity3D

    points = np.array([point for triangle in triangles for point in triangle], dtype=float)
    return MeshEntity3D(name, '#'+name, label or name, points,
                        np.arange(len(points), dtype=np.int64).reshape(-1, 3),
                        None, (100, 140, 180), False, local_axes=np.eye(3), pivot_world=np.zeros(3),
                        axes_source='host', axes_confidence='explicit', axes_reason='analytic_fixture')


def translate(vertices, vector):
    return [tuple(a+b for a,b in zip(point, vector, strict=True)) for point in vertices]


def subtract(a, b):
    return tuple(x-y for x,y in zip(a,b,strict=True))


def dot(a, b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def belongs(point, triangle):
    """Independent exact binary64 closed point/segment/triangle membership."""
    p, a, b, c = (tuple(F(float(v)) for v in row) for row in (point, *triangle))
    ab, ac, ap = subtract(b, a), subtract(c, a), subtract(p, a)
    aa, cc, bc = dot(ab, ab), dot(ac, ac), dot(ab, ac)
    determinant = aa*cc-bc*bc
    if determinant == 0:
        for left, right in ((a,b), (b,c), (c,a)):
            edge, delta = subtract(right, left), subtract(p, left)
            square, projection = dot(edge,edge), dot(delta,edge)
            if p == left or square and 0 <= projection <= square and all(
                    x*square == y*projection for x,y in zip(delta,edge,strict=True)):
                return True
        return False
    abp, acp = dot(ab, ap), dot(ac, ap)
    u, v = (abp*cc-acp*bc)/determinant, (acp*aa-abp*bc)/determinant
    return 0 <= u and 0 <= v and u+v <= 1 and all(
        r == u*x+v*y for r,x,y in zip(ap,ab,ac,strict=True))


def verify_indices(result, pair, expected=None):
    indices = result.get('witness_triangle_indices')
    check(type(indices) is list and len(indices) == 2 and all(type(i) is int for i in indices),
          'expected_one_ordered_source_triangle_per_endpoint')
    if expected is not None:
        check(indices == expected, 'incorrect_chosen_tie_or_nonwinning_pair')
    for name, mesh, index in zip(('point_a_world','point_b_world'),pair,indices,strict=True):
        check(0 <= index < len(mesh.faces) and belongs(result[name], mesh.vertices[mesh.faces[index]]),
              'independent_endpoint_outside_published_triangle/' + name)


def kernel_cases():
    a = make_mesh('A', [BASE_TRIANGLE])
    down, up = (translate(BASE_TRIANGLE, (0,0,z)) for z in (-2,2))
    loser = [(-10,40,0),(40,-10,0),(40,40,0)]
    centers = [90, *range(0,80,5)]
    tree_a = [translate(BASE_TRIANGLE, (x,0,0)) for x in centers]
    tree_b = [translate(BASE_TRIANGLE, (x,0,2)) for x in centers]
    tilted_a = [(1,0,0.25),(2,0,0.25),(1,1,0.25)]
    tilted_b = [(-8,8,0),(8,0,-8),(0,-8,8)]
    large = (2**40,)*3
    return {
        'linear_later_nonimprovement_not_AABB_pruned': ((a, make_mesh('B',[down,loser])), 2, [0,0]),
        'linear_later_exact_tie_keeps_first': ((a, make_mesh('B',[down,loser,up])), 2, [0,0]),
        'linear_reverse_keeps_order_and_direction': ((make_mesh('B',[loser,down]),a), 2, [1,0]),
        'tree_many_equal_pairs_select_original_lowest': ((make_mesh('A',tree_a),make_mesh('B',tree_b)),2,[0,0]),
        'tree_reverse_order_and_direction': ((make_mesh('B',tree_b),make_mesh('A',tree_a)),2,[0,0]),
        'zero_real_vertex_contact': ((a,make_mesh('B',[translate(BASE_TRIANGLE,(0.5,0,0))])),0,[0,0]),
        'zero_collinear_face_contact': ((a,make_mesh('B',[[(0,0,0),(.125,0,0),(.25,0,0)]])),0,[0,0]),
        'degenerate_point_face_has_bound_witness': ((a,make_mesh('B',[[(0,0,2)]*3])),2,[0,0]),
        'non_dyadic_published_point_outside_exact_plane': (
            (make_mesh('A',[tilted_a]), make_mesh('B',[tilted_b])), 1.25/sqrt(3), None),
        'translation_causes_original_display_precision_refusal': (
            (make_mesh('A',[translate(tilted_a,large)]), make_mesh('B',[translate(tilted_b,large)])),1.25/sqrt(3),None),
    }


def core_controls(candidate):
    from human_eye_plugin import surface_proximity as surface

    rows = {}
    for label, (pair, distance, indices) in kernel_cases().items():
        legacy = surface.measure_surface_proximity(*pair, lambda _: None)
        check(legacy['measurement_valid'] and isclose(legacy['distance_m'],distance,rel_tol=0,abs_tol=1e-14),
              'independent_distance_control_failed/' + label)
        check('witness_triangle_indices' not in legacy and 'witness_triangle_checks' not in legacy['work'],
              'default_measurement_shape_changed/' + label)
        if label.startswith('tree'):
            check(legacy['work']['tree_builds'] == 2 and legacy['work']['narrow_phase_pairs'] >= 17,
                  'tree_tie_did_not_visit_real_equidistant_leaves')
            check(legacy['point_a_world'][0] == 90, 'old_tree_lexicographic_pair_changed')
        if label.startswith('linear_later'):
            check(legacy['work']['narrow_phase_pairs'] == len(pair[1].faces),
                  'linear_no_improvement_or_tie_did_not_reach_narrow_phase')
        if label.startswith('zero'):
            check(legacy['direction_a_to_b'] is None and legacy['point_a_world'] == legacy['point_b_world']
                  and legacy['direction_status'] == 'not_applicable', 'zero_contact_semantics_changed')
        if label.startswith('non_dyadic'):
            check(legacy['witness_status'] == 'measured'
                  and not belongs(legacy['point_b_world'], pair[1].vertices[pair[1].faces[0]]),
                  'fixture_did_not_produce_a_rendered_off_plane_point')
        if label.startswith('translation'):
            check(legacy['witness_status'] == 'unknown' and legacy['point_a_world'] is None
                  and legacy['reason' if 'reason' in legacy else 'witness_reason'] == 'original_surface_witness_precision_exceeded',
                  'fixture_did_not_refuse_rounded_world_witness')
        row = {'legacy': legacy}
        if candidate:
            opt = surface.measure_surface_proximity(*pair, lambda _: None, retain_witness_triangles=True)
            check({k:v for k,v in opt.items() if k not in ('work','witness_triangle_indices')} ==
                  {k:v for k,v in legacy.items() if k!='work'}, 'opt_in_changed_existing_metric/' + label)
            check(all(opt['work'][x] == legacy['work'][x] for x in
                      ('triangle_pairs','narrow_phase_pairs','intersection_tests','tree_builds','validated_faces'))
                  and 0 <= opt['work'].get('witness_triangle_checks',0) <= 2, 'opt_in_reran_solver_or_unbounded_checks')
            if indices is not None:
                verify_indices(opt,pair,indices)
            else:
                check('witness_triangle_indices' not in opt, 'rounded_or_unpublished_point_claimed_source_triangle')
            row['candidate'] = opt
        rows[label] = row
    left, right = kernel_cases()['zero_real_vertex_contact'][0]
    holder = {}
    initial = surface.measure_surface_proximity(left,right,lambda _:None,_prepared_holder=holder)
    shared = holder['pair']
    contact = {'pair': shared, 'triangles': (0,0), 'point': holder['witness_points'][0]}
    options = {'retain_witness_triangles':True} if candidate else {}
    result = surface.measure_surface_proximity(left,right,lambda _:None,_prepared_pair=shared,_boundary_contact=contact,**options)
    check(result['work']['zero_witness_reused'] is True and result['work']['narrow_phase_pairs']==0
          and result['distance_m']==initial['distance_m']==0, 'same_bound_zero_witness_reuse_failed')
    if candidate:
        verify_indices(result,(left,right),[0,0])
    bad_contact = {**contact, 'triangles': (0,1)}
    fallback = surface.measure_surface_proximity(left,right,lambda _:None,
                         _prepared_pair=shared,_boundary_contact=bad_contact,**options)
    check(not fallback['work'].get('zero_witness_reused') and fallback['work']['narrow_phase_pairs']==1
          and fallback['distance_m']==0,'wrong_boundary_membership_reused_instead_of_actual_solve')
    if candidate:
        verify_indices(fallback,(left,right),[0,0])
    rows['bound_zero_reuse_and_bad_contact'] = {'valid_reuse':result, 'invalid_fallback':fallback}
    with patch.object(surface,'MAX_NARROW_PHASE_PAIRS',0):
        failed = surface.measure_surface_proximity(left,right,lambda _:None,**options)
    check(not failed['measurement_valid'] and failed['reason']=='surface_pair_budget'
          and 'witness_triangle_indices' not in failed, 'kernel_budget_exhaustion_published_source_indices')
    good = surface.measure_surface_proximity(left,right,lambda _:None,**options)
    check(good['distance_m']==0 and good['witness_status']=='measured', 'kernel_did_not_recover')
    rows['kernel_budget_and_recovery'] = {'exhausted':failed,'recovered':good}
    if candidate:
        pair, _, _ = kernel_cases()['linear_later_exact_tie_keeps_first']
        allowed = rows['linear_later_exact_tie_keeps_first']['legacy']['work']['work_units']
        with patch.object(surface, 'MAX_WORK_UNITS', allowed+1):
            reduced = surface.measure_surface_proximity(*pair,lambda _:None,retain_witness_triangles=True)
        check(reduced['measurement_valid'] and reduced['witness_status']=='measured'
              and reduced['work']['witness_triangle_checks']==1 and 'witness_triangle_indices' not in reduced,
              'partial_provenance_budget_published_or_changed_existing_witness')
        rows['two_side_provenance_budget_omits_partial_evidence'] = {'candidate':reduced}
    return rows


class TestHost:
    def __init__(self):
        self.meshes = [make_mesh('a',[BASE_TRIANGLE],label='A').to_dict(),
            make_mesh('b',[translate(BASE_TRIANGLE,(0,0,2)),
                           translate(BASE_TRIANGLE,(20,0,0))],label='B').to_dict()]
        self.instances = {'a':'101','b':'102'}
        self.generation = 1
        self.versioned = True
        self.selected_calls = []

    def capture_task_scene(self, selectors):
        from human_eye_plugin.task_query import bind_objects
        from human_eye_plugin.read_context import query_key

        self.selected_calls.append(deepcopy(selectors))
        found, rows, reason = bind_objects({'meshes':self.meshes},selectors)
        selected = {item['object_id']:item for item in found if item is not None}
        selection = sha256(query_key(selectors).encode()).hexdigest()
        packet = {'revision':f'analytic-generation-{self.generation}-{selection}', 'unit':'m', 'coordinate_frame':'world',
                'source':'blender', 'capture_scope':'selected_objects',
                'capture_state':{'instance_id':'owned-synthetic','epoch':1,'revision':self.generation,'selection_key':selection},
                'meshes':[deepcopy(selected[name]) for name in sorted(selected)],
                'task_selection':{'selectors':deepcopy(selectors),'bindings':rows,'pair_reason':reason,
                                  'candidate_count':len(self.meshes)},
                'host_identity':{'schema_version':'1.0','capture_scope':'selected_objects','document_epoch':'test-document',
                                 'object_instances':{key:self.instances[key] for key in selected}}}
        if not self.versioned:
            del packet['capture_state']
        return packet

    def capture_scene(self):
        raise AssertionError('whole_task_must_not_make_a_second_or_full_capture')


def service_controls(candidate, folder, project):
    from human_eye_plugin import task_query
    from human_eye_plugin.live_service import LiveSpatialService, RequestBudgetError
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer

    host = TestHost()
    config = folder/'CONFIG.json'
    save(config, {'schema_version':'1.0','enabled':True,'observe_on_prompt':False,'project_root':str(project),
                  'state_file':str(folder/'state.json'),'audit_file':str(folder/'audit.jsonl'),'request_budget_s':30})
    service = LiveSpatialService(config, host=host)
    default = LiveSpatialMCPServer(service, 'engine-control')
    evidence = LiveSpatialMCPServer(service, 'engine-control', region_task_evidence=True)
    observations = {}

    def query(label, server=evidence, *, objects=None, facts=None, flags=None):
        args = {'include_image':False,
                'query':{'mode':'task','objects':AB if objects is None else objects,
                         'requested_facts':REFERENCE_FACT if facts is None else facts}}
        args.update(flags or {})
        response = server.handle_jsonrpc_message({'jsonrpc':'2.0','id':label,'method':'tools/call','params':{
            'name':'human_eye_scene_observe','arguments':args}})
        result = response['result']
        check(len(result['content'])==1 and result['content'][0]['type']=='text','unrequested_image_or_content')
        body = json.loads(result['content'][0]['text'])
        observations[label] = {'body':body,'is_error':result['isError'],'captures_after':len(host.selected_calls)}
        return body

    def mapping(body):
        fact = body['facts']['surface_proximity']
        value = fact.get('value')
        return None if not value else value['nearest_witness'].get('source_triangles')

    def source(body, expect_indices, expect_ids):
        actual = mapping(body)
        if not candidate:
            check(actual is None, 'ordinary_history_unexpectedly_has_new_source_mapping')
            return
        if expect_indices is None:
            check(actual is None, 'ineligible_standard_or_failed_operation_has_source_mapping')
            return
        check(actual is not None and actual['index_domain']==DOMAIN and actual['document_epoch']=='test-document'
              and actual['capture_state']['revision']==host.generation
              and actual['scope'], 'eligible_source_not_bound_to_current_capture_and_index_domain')
        for key,index,ident in zip(('a','b'),expect_indices,expect_ids,strict=True):
            check(actual[key]['source_triangle_index']==index and actual[key]['instance_id']==host.instances[ident],
                  'source_faces_or_instances_crossed_cache_selection_boundary/'+key)

    def one_capture(label):
        captures = observations[label]['captures_after']
        prev = list(observations)[-2]
        check(captures-observations[prev]['captures_after']==1, 'request_made_additional_capture/'+label)

    with patch.object(task_query,'measure_surface_proximity',wraps=task_query.measure_surface_proximity) as call:
        source(query('standard_cold',default),None,None)
        source(query('evidence_cold'),[0,0],('a','b'))
        source(query('standard_hot',default),None,None)
        source(query('evidence_hot'),[0,0],('a','b'))
        check(call.call_count == (2 if candidate else 1), 'output_modes_crossed_or_hot_result_resolved')
        for label in ('evidence_cold','standard_hot','evidence_hot'):
            labels = list(observations)
            idx = labels.index(label)
            check(observations[label]['captures_after']-observations[labels[idx-1]]['captures_after']==1,
                  'cold_or_warm_call_did_not_use_exactly_one_new_host_read')
        reversed_result = query('reversed',objects=list(reversed(AB)))
        one_capture('reversed')
        source(reversed_result,[0,0],('b','a'))
        check(reversed_result['facts']['surface_proximity']['value']['nearest_witness']['direction_a_to_b']==[0,0,-1],
              'reverse_measurement_direction_not_bound_to_current_order')
        host.meshes[1]['faces'].reverse()
        host.generation += 1
        changed = query('same_name_same_metric_new_face_order')
        one_capture('same_name_same_metric_new_face_order')
        source(changed,[0,1],('a','b'))
        check(changed['facts']['surface_proximity']['value']['distance_m']==2, 'face_permutation_changed_distance')
        replacement = make_mesh('a-replaced',[BASE_TRIANGLE],label='A').to_dict()
        host.meshes[0] = replacement
        host.instances['a-replaced'] = '501'
        host.generation += 1
        current = query('same_name_replaced_instance')
        source(current,[0,1],('a-replaced','b'))
        check(current['binding']['objects'][0]['object_id']=='a-replaced', 'same_name_cached_wrong_current_object')
        source(query('mixed_facts_stays_original',facts=['aabb','surface_proximity']),None,None)
        geometry_request = {'mode':'task','target':AB[0],'candidates':[AB[1]],
                            'requested_facts':['closed_solid_relation','surface_proximity'],
                            'geometry':{'objects':[AB[0]],'include_triangles':True}}
        geometry = query('task_set_and_geometry_stay_original',flags={'query':geometry_request})
        check(not observations['task_set_and_geometry_stay_original']['is_error']
              and 'geometry' in geometry and '"source_triangles"' not in json.dumps(geometry),
              'set_or_geometry_route_leaked_candidate_source_format')
        source(query('same_object_pair_unknown',objects=[AB[0],AB[0]]),None,None)
        host.meshes.append(make_mesh('a-other',[BASE_TRIANGLE],label='A').to_dict())
        host.instances['a-other'] = '501-shadow'
        host.generation += 1
        ambiguous = query('ambiguous_same_name')
        source(ambiguous,None,None)
        check(ambiguous['binding']['objects'][0]['reason']=='object_name_ambiguous','same_name_ambiguity_hidden_by_cache')
        source(query('exact_ID_after_name_ambiguity',objects=[{'id':'a-replaced'},AB[1]]),[0,1],('a-replaced','b'))
        before = len(host.selected_calls)
        query('image_flag_rejected',flags={'include_image':True})
        check(observations['image_flag_rejected']['is_error'] and len(host.selected_calls)==before,
              'inadmissible_image_query_entered_geometry')
        host.meshes.pop()
        host.generation += 1
        checkpoint = service._check_request_budget

        def expire(stage, **flags):
            if stage == 'surface_proximity_publish':
                raise RequestBudgetError('expired',stage)
            return checkpoint(stage,**flags)

        before = call.call_count
        with patch.object(service,'_check_request_budget',side_effect=expire):
            failed = query('expired_after_search')
        check(observations['expired_after_search']['is_error'] and failed['budget_stage']=='surface_proximity_publish'
              and call.call_count==before+1 and 'facts' not in failed,'expired_search_published_Evidence')
        source(query('recovery_after_expiry'),[0,1],('a-replaced','b'))
        check(call.call_count==before+2,'request_expiry_poisoned_or_cached_incomplete_pair')
        host.versioned = False
        no_version = query('absent_capture_version')
        source(no_version,None,None)
        check(no_version['facts']['surface_proximity']['value']['distance_m']==2,
              'versions_gate_changed_existing_metric')
        host.versioned = True
        source(query('restored_bound_capture_version'),[0,1],('a-replaced','b'))
        before = len(host.selected_calls)
        query('private_opt_in_is_not_a_public_argument',default,flags={'_include_witness_triangles':True})
        check(observations['private_opt_in_is_not_a_public_argument']['is_error'] and len(host.selected_calls)==before,
              'unexpected_public_opt_in_field_reached_geometry')
    for server,name in ((default,'standard'),(evidence,'evidence')):
        catalogue = server.handle_jsonrpc_message({'jsonrpc':'2.0','id':name,'method':'tools/list'})
        check('result' in catalogue and isinstance(catalogue['result']['tools'],list),'missing_tools_catalogue')
        save(folder/('TOOLS_'+name.upper()+'.json'),catalogue['result']['tools'])
    return {'calls':observations,'calls_to_exact_solver':call.call_count,'host_reads':len(host.selected_calls)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',type=Path,required=True)
    parser.add_argument('--dependencies',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate',action='store_true')
    opts = parser.parse_args()
    install = opts.install.resolve(strict=True)
    sys.path[:0] = [str(install),str(opts.dependencies.resolve(strict=True))]
    from human_eye_plugin import surface_proximity as surface
    check(sys.flags.isolated and sys.dont_write_bytecode and Path(surface.__file__).is_relative_to(install),
          'unexpected_candidate_import_or_python_flags')
    opts.output.mkdir(parents=True)
    core = core_controls(opts.candidate)
    save(opts.output/'KERNEL_CONTROLS.json', core)
    services = service_controls(opts.candidate,opts.output.resolve(),install)
    save(opts.output/'SERVICE_CONTROLS.json', services)
    print(json.dumps({'passed':True,'candidate':opts.candidate,'kernel_cases':len(core),
                      'service_cases':len(services['calls']),'solver_calls':services['calls_to_exact_solver']}))


if __name__ == '__main__':
    main()
