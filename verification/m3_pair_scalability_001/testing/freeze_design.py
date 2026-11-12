"""Freeze finite inputs and admission rules before any candidate source edit."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (HERE/name).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=True,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def box(center, levels=0):
    points = [[center[0]+x,center[1]+y,center[2]+z] for x,y,z in
        ((-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1))]
    faces = [[0,2,3],[0,3,1],[4,5,7],[4,7,6],[0,1,5],[0,5,4],
        [2,6,7],[2,7,3],[0,4,6],[0,6,2],[1,3,7],[1,7,5]]
    for unused in range(levels):
        lookup = {tuple(point):i for i,point in enumerate(points)}
        def midpoint(a,b):
            point = tuple((points[a][k]+points[b][k])/2 for k in range(3))
            if point not in lookup:
                lookup[point] = len(points)
                points.append(list(point))
            return lookup[point]
        next_faces = []
        for a,b,c in faces:
            ab,bc,ca = midpoint(a,b),midpoint(b,c),midpoint(c,a)
            next_faces.extend(([a,ab,ca],[ab,b,bc],[ca,bc,c],[ab,bc,ca]))
        faces = next_faces
    return {'vertices':points,'faces':faces}


def main():
    baseline = json.loads((HERE/'baseline/MANIFEST.json').read_bytes())
    qual = ROOT/'verification/spatial_task_qualification_001'
    source_paths = [qual/'entry/run_01/ACTUAL_SNAPSHOT.json',qual/'oracle/formal_replay_01/ORACLE.json',
        ROOT/'verification/scale_diag_001/fixtures/G60_D12.json',
        ROOT/'verification/scale_diag_001/ORACLE.json']
    fixtures = {str(path.relative_to(ROOT)):sha(path) for path in source_paths}
    cube12 = [box((10.,0.,0.)),box((13.,0.,0.))]
    cube192 = [box((10.,0.,0.),2),box((13.,0.,0.),2)]
    assert [len(row['faces']) for row in cube12] == [12,12]
    assert [len(row['faces']) for row in cube192] == [192,192]
    base_triangle = [[0.,0.,0.],[2.,0.,0.],[0.,2.,0.]]
    plane_cases = [
        {'id':'plane_equal','other_z':[2,2,2],'normal':[0,0,1],'best_squared':[4,1],'prune':False},
        {'id':'plane_above','other_z':[3,3,3],'normal':[0,0,1],'best_squared':[4,1],'prune':True},
        {'id':'plane_negative_side','other_z':[-3,-3,-3],'normal':[0,0,1],'best_squared':[4,1],'prune':True},
        {'id':'plane_crossing','other_z':[-3,3,3],'normal':[0,0,1],'best_squared':[4,1],'prune':False},
        {'id':'plane_degenerate','other_z':[3,3,3],'normal':[0,0,0],'best_squared':[4,1],'prune':False},
        {'id':'plane_bit_equal','projection_gap':str(1<<2047),'normal_squared':str(1<<4094),'best_squared':[1,1],'prune':False},
        {'id':'plane_bit_above','projection_gap':str((1<<2047)+1),'normal_squared':str(1<<4094),'best_squared':[1,1],'prune':True},
    ]
    simplex = [
        {'id':'shared_edge_noncoplanar','vertices':base_triangle+[[0.,0.,2.]],'faces':[[0,1,2],[1,0,3]],'legal_contact':True},
        {'id':'shared_edge_opposite_coplanar','vertices':base_triangle+[[0.,-2.,0.]],'faces':[[0,1,2],[1,0,3]],'legal_contact':True},
        {'id':'shared_edge_same_side_overlap','vertices':base_triangle+[[1.,1.,0.]],'faces':[[0,1,2],[1,0,3]],'legal_contact':False},
        {'id':'shared_vertex_only','vertices':base_triangle+[[-2.,0.,0.],[0.,-2.,0.]],'faces':[[0,1,2],[0,3,4]],'legal_contact':True},
        {'id':'shared_vertex_elsewhere_crossing','vertices':base_triangle+[[1.,1.,-1.],[1.,1.,1.]],'faces':[[0,1,2],[0,3,4]],'legal_contact':False},
        {'id':'no_shared_index_crossing','vertices':[[-1.,-1.,0.],[1.,-1.,0.],[0.,1.,0.],[0.,-.5,-1.],[0.,-.5,1.],[0.,.5,1.]],
            'faces':[[0,1,2],[3,4,5]],'legal_contact':False},
    ]
    cases = {'schema':'m3-pair-scalability-designed-cases-v1','frozen_before_candidate':True,
        'source_files':fixtures,'old_six_test_files':baseline['tests'],
        'cube12':cube12,'cube192_same_world_boundary':cube192,
        'cube_oracle':{'distance_m':1.,'relation':'separated','support_witnesses':[[11.,0.,0.],[12.,0.,0.]],
            'proof':'identical cube boundary under dyadic midpoint subdivision; exact X support at 11 and 12'},
        'g508':{'snapshot':str(source_paths[0].relative_to(ROOT)),'target':'Target',
            'candidates':['Peer_000','Competing_001','Near_003'],'minimum_gap_m':.004,
            'truth':str(source_paths[1].relative_to(ROOT)),'tolerance_m':1e-6},
        'g60':{'fixture':str(source_paths[2].relative_to(ROOT)),'target_id':'target','candidates':['peer','competitor','distractor_003'],
            'truth_fixture_id':'G60_D12','truth':str(source_paths[3].relative_to(ROOT))},
        'plane_bound_cases':plane_cases,'shared_simplex_cases':simplex,
        'high_product_prunable':{'left_count':129,'right_count':128,'triangle_template':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],
            'left_translation_recipe':[10,0,0],'right_translation_recipe':[10,0,1],
            'definition':'triangle i translated (10*i,0,z), z=0 left and z=1 right','distance_m':1.,
            'old_expected':'surface_geometry_work_limit before expansion','candidate_expected':'complete surface distance, closed unknown because open components'},
        'static_face_limit':{'face_lengths':[4096,1],'expected':'surface_geometry_work_limit before expanding face rows'},
        'pair_frame_independence':{'target_vertices':base_triangle,'candidate_z':[1.,2.**-40],
            'faces':[[0,1,2]],'expected_distances':[1.,2.**-40],'expected':'different pair factors and no cross-pair prepared-tree reuse'},
        'numeric_and_shape_controls':{'existing_six_tests':'all original cases preserved, including face/edge interior, zero, coplanar, containment, open/degenerate surfaces, bit guards, large translation and dyadic transforms',
            'new_tests_must_not_reinterpret_unknown_as_complete':True},
        'work_boundaries':{'surface_total':[1179647,1179648,1179649],'surface_complete_leaf':[16383,16384,16385],
            'closed_total':[262143,262144,262145],'closed_pair':[16383,16384,16385],'closed_ray':[16383,16384,16385],
            'expectation':'last admissible unit succeeds; next actual unit refuses, without successful complete report'},
        'interruptions':{'cancel_stages':['tree_build','node_visit','narrow_phase','closed_self','closed_cross','closed_ray'],
            'deadline':'checkpoint raises original deadline exception at the fixed selected stage; propagate without caching unknown or success'},
        'reuse_cases':['same_pair_closed_then_surface_single_integer_prepare_and_tree_set',
            'surface_only','closed_cached_surface_cold','surface_exact_rank','same_source_cold_warm',
            'revision_only_change','geometry_change','pose_change','different_candidate_pair_factor'],
    }
    save('DESIGNED_CASES.json',cases)
    timing = [{'iteration':i,'order':['reference','candidate'] if i%2 else ['candidate','reference']} for i in range(1,6)]
    save('FROZEN.json',{'schema':'m3-pair-scalability-preimplementation-freeze-v1',
        'source_sha256':baseline['source_sha256'],'baseline_manifest_sha256':sha(HERE/'baseline/MANIFEST.json'),
        'designed_cases_sha256':sha(HERE/'DESIGNED_CASES.json'),'freeze_script_sha256':sha(Path(__file__)),
        'plan_sha256':sha(Path('D:/hefe/docs/M3_PAIR_SCALABILITY_001_PLAN.md')),
        'surface_budget':{'max_work_units':1179648,'max_full_narrow_phase_pairs':16384,'linear_pair_limit':256,
            'units':'each actual validation/preparation/tree/node/leaf/queue/plane/AABB/feature/predicate unit is counted; no raw face-product admission'},
        'closed_budget_unchanged':{'max_work_units':262144,'max_self_plus_cross_pairs':16384,'max_ray_tests':16384},
        'precision_unchanged':{'max_bits':4096,'max_scratch_bits':8193,'publication_tolerance_m':1e-9},
        'reference':{'diagnostic_only':True,'per_case_deadline_seconds':30,'surface_original_nearest_AABB_early_out_retained':True,
            'overrides':{'surface_proximity.MAX_TRIANGLE_PAIRS':{'from':16384,'to':1000000000},
                'surface_geometry.CLOSED_SOLID_MAX_PAIR_TESTS':{'from':16384,'to':1000000000},
                'surface_geometry.CLOSED_SOLID_MAX_WORK':{'from':262144,'to':1000000000}},
            'unchanged':'original 137 source bytes, geometry, leaf arithmetic, bit/scratch guards, original callback deadlines, original ray cap',
            'peer_full_cartesian_pairs':258064,'peer_expensive_intersection_entry_denominator':18791,
            'peer_candidate_max_expensive_pairs':9395,'reference_denominator_source':'baseline/diagnostics/ADMISSION_DIAGNOSTIC.json'},
        'timing':{'cases':['G508/Peer_000','G508/Competing_001','G508/Near_003','cube12/control'],
            'repetitions_per_role_per_case':5,'fixed_order':timing,'no_retries_or_best_selection':True,
            'cold':'fresh function call with new diagnostics/holder per role, no across-call measurement memo',
            'shared_within_call':'closed then surface share that call original/candidate query-local holder only',
            'window':'same complete facts from preparation entry through closed and surface results; raw serialization and imports separate',
            'deadline_seconds_per_role_case':30,'g508_total_rule':'candidate total time no greater than same-fact diagnostic reference',
            'simple_control_median_rule':'candidate minus reference <= max(1000000 ns, reference median * .05)',
            'report':'all five values, median and range, incomplete/timeouts retained without speed ratio'},
        'status':'FROZEN; helper-spy names and runner adapters may be completed without changing fixtures, budgets, thresholds or repetitions'})


if __name__=='__main__':
    main()
