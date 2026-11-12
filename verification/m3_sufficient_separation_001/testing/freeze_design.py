"""Generate static fixed cases and timing rules without importing product code."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = ROOT/'verification/m3_pair_scalability_001/testing'
QUALIFICATION = ROOT/'verification/spatial_task_qualification_001'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name,value):
    with (HERE/name).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=True,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def box(name,center=(0.,0.,0.),size=(2.,2.,2.)):
    signs = ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
    vertices = [[center[k]+sign[k]*size[k]/2 for k in range(3)] for sign in signs]
    faces = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
        [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]]
    return {'name':name,'vertices_world':vertices,'triangles':faces}


def triangle(name,vertices):
    return {'name':name,'vertices_world':vertices,'triangles':[[0,1,2]]}


def transformed(raw,matrix,name):
    return {'name':name,'vertices_world':[[sum(matrix[r][c]*p[c] for c in range(3))+matrix[r][3]
        for r in range(3)] for p in raw['vertices_world']], 'triangles':raw['triangles']}


def annular_prism():
    outer = [(-2.,-2.),(2.,-2.),(2.,2.),(-2.,2.)]
    inner = [(-1.,-1.),(1.,-1.),(1.,1.),(-1.,1.)]
    vertices = [[x,y,z] for z in (-.5,.5) for x,y in outer+inner]
    quads = []
    for i in range(4):
        j = (i+1)%4
        quads.extend(((8+i,8+j,12+j,12+i),(i,4+i,4+j,j),
            (i,j,8+j,8+i),(4+j,4+i,12+i,12+j)))
    return {'name':'annular_prism','vertices_world':vertices,
        'triangles':[list(face) for a,b,c,d in quads for face in ((a,b,c),(a,c,d))]}


def pair(case_id,left,right,truth,mechanism):
    return {'id':case_id,'left':left,'right':right,'independent_truth':truth,'mechanism':mechanism}


def main():
    plan = Path('D:/hefe/docs/M3_SUFFICIENT_SEPARATION_001_PLAN.md')
    assert sha(plan)=='2011d38aade474a7f862d324a2fa883ac701064976cc2a87059f01d249b30f10'
    source = QUALIFICATION/'entry/run_01/ACTUAL_SNAPSHOT.json'
    truth = QUALIFICATION/'oracle/formal_replay_01/ORACLE.json'
    assert sha(source)=='29dfdccd839170b70ec03339925323d433b5e4221d1caac6649b2060fefa453c'
    assert sha(truth)=='a0211b6669ac05c88f1db0582b78247648cde30da9d1744c1c8a46ad12a62e57'
    baseline = json.loads((PREVIOUS/'baseline/MANIFEST.json').read_bytes())
    starting = json.loads((PREVIOUS/'final_candidate_01/MANIFEST.json').read_bytes())
    assert baseline['product_commit']=='fac9b4373575d653cc96f39f1dcb225300cd5977'
    assert baseline['source_sha256']=='6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb'
    assert starting['source_sha256']=='0770602e875c819dd424639fd7c750aaad4bca3bbe506aaf747ba337e5991139'
    for root,manifest in ((PREVIOUS/'baseline/product',baseline['source_manifest']),
                          (PREVIOUS/'final_candidate_01/product',starting['manifest'])):
        assert len(manifest)==137
        for row in manifest:
            assert sha(root/row['path'])==row['sha256']
    snapshot = json.loads(source.read_bytes())
    objects = {row['name']:row for row in snapshot['objects']}
    complete_truth = json.loads(truth.read_bytes())
    analytic = []
    rotated = [[1.,1.,0.,0.],[1.,-1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    analytic.append(pair('rotated_overlapping_world_aabbs',transformed(box('a',size=(2.,.5,.5)),rotated,'rotated_a'),
        transformed(box('b',center=(0.,.75,0.),size=(2.,.5,.5)),rotated,'rotated_b'),
        {'relation':'separated','distance_squared_rational':[1,8],
         'attaining_points':[[.25,-.25,0.],[.5,-.5,0.]],'support_normal':[1,-1,0],
         'proof':'exact dyadic transform of two boxes; local Y gap 1/4, transformed norm sqrt(2); world AABBs overlap'},
        'positive surface distance with overlapping world boxes'))
    for name,translation,scale in (('large_translation',(2.**50,-2.**50,2.**49),1.),
                                   ('small_scale',(0.,0.,0.),2.**-400)):
        matrix = [[scale,0.,0.,translation[0]],[0.,scale,0.,translation[1]],
            [0.,0.,scale,translation[2]],[0.,0.,0.,1.]]
        analytic.append(pair(name,transformed(box('a'),matrix,'a'),transformed(box('b',center=(3.,0.,0.)),matrix,'b'),
            {'relation':'separated','distance_m':scale,'proof':'axis support and explicit facing-corner witness on stored binary64 coordinates'},
            'represented coordinate magnitude, original bit and publication limits'))
    epsilon = 2.**-40
    for name,center,relation,distance in (('strict_tiny_gap',2.+epsilon,'separated',epsilon),
            ('exact_touch',2.,'touching',0.),('strict_tiny_overlap',2.-epsilon,'penetrating',0.)):
        analytic.append(pair(name,box('a'),box('b',center=(center,0.,0.)),
            {'relation':relation,'distance_m':distance,'proof':'exact dyadic axis interval gap or positive open-box intersection'},
            'strict sign, zero proposal and closed fallback'))
    open_a = triangle('open_a',[[-2.,-2.,0.],[2.,-2.,0.],[0.,2.,0.]])
    open_b = triangle('open_b',[[-1.,-1.,1.],[1.,-1.,1.],[0.,1.,1.]])
    analytic.append(pair('open_separated',open_a,open_b,
        {'relation':'separated','distance_m':1.,'explicit_closed':'unknown',
         'proof':'all source vertices on parallel planes z=0 and z=1, overlapping XY interiors'},
        'new hull scope without embedded-shell qualification'))
    selfcross = box('self_crossing')
    selfcross['vertices_world'][6] = [-2.,-2.,-2.]
    analytic.append(pair('self_crossing_separated',selfcross,box('far',center=(20.,-1.,0.),size=(1.,1.,1.)),
        {'relation':'separated','distance_m':18.5,'explicit_closed':'unknown',
         'attaining_points':[[1.,-1.,0.],[19.5,-1.,0.]],
         'proof':'all left x<=1 and right x>=19.5; attaining point on original edge (1,5), frozen old self-crossing-box recipe'},
        'combinatorial closed input with invalid embedding may still have disjoint hulls'))
    remote = dict(open_a,name='remote_referenced',vertices_world=open_a['vertices_world']+[[100.,0.,2.],[101.,0.,2.],[100.,1.,2.]],
        triangles=[[0,1,2],[3,4,5]])
    analytic.append(pair('remote_referenced_vertex_refutes_only_direction',remote,open_b,
        {'relation_truth':'separated','distance_m':1.,'new_expected':'unknown','fallback_closed':'unknown',
         'proposal_direction':[0,0,1],'projection_extrema':{'left_max':2,'right_min':1},
         'proof':'near pair separated by z=1; remote component has x>=100, but its referenced z=2 defeats the sole z proposal'},
        'nearest-only sampling must fail; no alternate axis search'))
    orphan = box('orphan_a')
    orphan['vertices_world'].append([3.,0.,0.])
    analytic.append(pair('unreferenced_point_excluded_from_scope',orphan,box('b',center=(3.,0.,0.)),
        {'relation':'separated','distance_m':1.,'explicit_closed':'unknown',
         'referenced_counts':[8,8],'raw_vertex_counts':[9,8],
         'proof':'referenced box hulls have x-gap 1; unused source vertex lies inside B and is outside new fact scope'},
        'referenced triangle unions, no false all-raw-vertex assertion'))
    analytic.append(pair('collapsed_middle_source_vertex_retained',
        triangle('line_a',[[0.,0.,0.],[1.,0.,0.],[.5,0.,0.]]),
        triangle('line_b',[[0.,0.,1.],[1.,0.,1.],[.5,0.,1.]]),
        {'relation':'separated','distance_m':1.,'explicit_closed':'unknown','referenced_counts':[3,3],
         'proof':'parallel segments distance 1; interior collinear source indices remain referenced'},
        'complete integer coordinate dictionaries, including reduced-hull omissions'))
    analytic.append(pair('intersecting_hulls_separated_nonconvex_shells',annular_prism(),
        box('hole_probe',size=(.5,.5,.5)),
        {'relation':'separated','distance_m':.75,'support_expected':False,'fallback_expected':'separated',
         'attaining_points':[[1.,0.,0.],[.25,0.,0.]],
         'proof':'annular material has max(abs(x),abs(y))>=1 while probe <=1/4; probe is inside annular convex hull'},
        'one-direction failure cannot be interpreted as collision'))
    crossing = pair('fallback_intersecting_bars',box('x_bar',size=(4.,.5,.5)),box('y_bar',size=(.5,4.,.5)),
        {'relation':'penetrating','distance_m':0.,'common_strict_interior_point':[0.,0.,0.],
         'attaining_points':[[.25,.25,0.],[.25,.25,0.]],'proof':'shared open cube (-1/4,1/4)^3 and crossing boundary lines'},
        'zero direction and original closed fallback')
    containing = pair('fallback_full_containment',box('outer',size=(4.,4.,4.)),box('inner',size=(1.,1.,1.)),
        {'relation':'penetrating','distance_m':1.5,'common_strict_interior_point':[0.,0.,0.],
         'proof':'strict concentric-box containment; surface gap is 3/2, not evidence of disjoint solids'},
        'positive surface distance but strict support cannot prove separation')
    analytic.extend((crossing,containing))
    known = box('known',center=(3.,0.,0.))
    mirrored = box('equal_known',center=(-3.,0.,0.))
    unknown = triangle('unknown_inside',[[0.,0.,0.],[.5,0.,0.],[0.,.5,0.]])
    save('DESIGNED_CASES.json',{'schema':'m3-sufficient-separation-fixed-cases-v1',
        'g508':{'snapshot':str(source.relative_to(ROOT)),'snapshot_sha256':sha(source),
            'truth':str(truth.relative_to(ROOT)),'truth_sha256':sha(truth),'target':'Target',
            'candidates':['Peer_000','Competing_001','Near_003'],'minimum_gap_m':.004,
            'distance_tolerance_m':1e-6,'position_tolerance_m':1e-9,
            'truth_intervals':[{k:row[k] for k in ('candidate_name','distance_lower_m','distance_upper_m','minimum_4mm')}
                for row in complete_truth['pairs']], 'support_referenced_counts':[[256,256],[256,32],[256,32]]},
        'simple_control':{'left':objects['Control_A'],'right':objects['Control_B'],
            'independent_truth':{'relation':'separated','distance_m':1.,'support_referenced_counts':[8,8]}},
        'analytic_pairs':analytic,
        'sets':{'target':box('set_target'),'known':known,'equal_known':mirrored,'unknown':unknown,
            'ties':{'candidates':['known','equal_known'],'complete':True,'nearest':['known','equal_known'],'distance_m':1.},
            'unknown_candidate':{'candidates':['known','equal_known','unknown'],'complete':False,
                'unknown_reason':'open contained triangle cannot qualify fallback; positive distance does not classify it'}},
        'metamorphic':{'support_extremum_indices':'reverse vertex order and remap all faces for every analytic source',
            'swap_pair':'A/B swap with freshly computed B-A proposal, reverse source binding and preserve relation/distance',
            'candidate_order':['forward','reverse'],
            'pose_change_matrix':[[0,-1,0,5],[1,0,0,7],[0,0,1,9],[0,0,0,1]],
            'geometry_change':'translate the simple right box +1/4 on X; gap changes 1 to 5/4',
            'same_name_replacement':'same source name and geometry but new object-instance identity',
            'unit_frame_revision':'reuse existing bound-source fixtures with changed unit/frame/subframe/revision; current bindings required'},
        'requests':{'new_set':['surface_proximity','spatial_relation'],
            'old_set':['surface_proximity','closed_solid_relation'],
            'mixed':['surface_proximity','spatial_relation','closed_solid_relation'],
            'single_pair':['spatial_relation'],'versions':{'new_set':'task-query-set-v2','old_set':'task-query-set-v1','single_pair':'task-query-v3'},
            'mixed_rules':['support success does not satisfy explicit closed','unknown explicit closed makes overall partial',
                'legal fallback executes closed once and reuses it for mixed','budget_stopped suppresses any new mixed closed execution'],
            'compact_tools':'schemas, parameters, defaults and result behavior retain the prior contract'},
        'guards':{'original_surface_work_limit':1179648,'original_full_leaf_limit':16384,
            'support_work_increment':'2*V+3 for a completed pass, V counts all unique referenced source indices',
            'support_steps':['direction conversion','source enumeration/extremum','exact vertex dot'],
            'budget_boundary':'preserve spent surface units; last admissible unit accepted, next actual unit yields budget_stopped; no fallback or mixed closed',
            'optional_exact_bit_failure':'support arithmetic DomainError permits at most one original closed fallback without relaxing 4096/8193 bits',
            'cancel_deadline':'same original exception object propagates during support and closed fallback; never treated as fallback reason',
            'unsupported_or_zero_proposal':'one original closed fallback at most, continuous deadline',
            'cache':'bundle memo only with surface and spatial both valid; unknown/exception not cached; old v1 memo versions unchanged'},
        'independence':'analytic support/interval and attaining triangle points, original exact support certificates, or fixed small-mesh independent enumeration; no candidate output is an expected answer'})
    timing_cases = ['G508/Peer_000','G508/Competing_001','G508/Near_003','simple_control',crossing['id'],containing['id']]
    schedule = []
    for case in timing_cases:
        for iteration in range(1,6):
            order = ('reference','candidate') if iteration%2 else ('candidate','reference')
            for position,arm in enumerate(order,1):
                schedule.append({'sequence':len(schedule)+1,'case':case,'iteration':iteration,'position':position,'arm':arm})
    assert len(schedule)==60
    save('TIMING_SEQUENCE.json',{'schema':'m3-sufficient-separation-sixty-calls-v1','calls':schedule,
        'main_calls':40,'fallback_calls':20,'no_retries_or_replacement':True})
    save('SOURCE_PINS.json',{'plan':{'path':str(plan),'sha256':sha(plan)},
        'root_contract':{'path':'verification/m3_sufficient_separation_001/CONTRACT.md','sha256':sha(HERE.parent/'CONTRACT.md')},
        'starting_evidence_commit':'743a484f16f1dadff8dedcf1abad8d0a14398d17',
        'starting_product_commit':'3beb3f809674658b086e50af194adaa16e226111','starting_source_sha256':starting['source_sha256'],
        'starting_137_manifest':{'path':str((PREVIOUS/'final_candidate_01/MANIFEST.json').relative_to(ROOT)),
            'sha256':sha(PREVIOUS/'final_candidate_01/MANIFEST.json')},
        'reference_product_commit':baseline['product_commit'],'reference_source_sha256':baseline['source_sha256'],
        'reference_137_manifest':{'path':str((PREVIOUS/'baseline/MANIFEST.json').relative_to(ROOT)),
            'sha256':sha(PREVIOUS/'baseline/MANIFEST.json')},
        'independent_oracle':{'path':'verification/scale_diag_001/oracle.py','sha256':sha(ROOT/'verification/scale_diag_001/oracle.py')},
        'public_witness_oracle':{'path':str((PREVIOUS/'witness_oracle.py').relative_to(ROOT)),'sha256':sha(PREVIOUS/'witness_oracle.py')},
        'old_failed_report':{'path':str((PREVIOUS/'REPORT.md').relative_to(ROOT)),'sha256':sha(PREVIOUS/'REPORT.md')},
        'root_feasibility':{'path':'D:/hefe/verification/fixes/20261112_m3_pair_scalability_review/architecture/SUPPORT_FEASIBILITY.json',
            'sha256':sha(Path('D:/hefe/verification/fixes/20261112_m3_pair_scalability_review/architecture/SUPPORT_FEASIBILITY.json'))}})
    save('FROZEN.json',{'schema':'m3-sufficient-separation-preimplementation-qa-freeze-v1',
        'status':'static design frozen, no product or performance executed',
        'designed_cases_sha256':sha(HERE/'DESIGNED_CASES.json'),'sequence_sha256':sha(HERE/'TIMING_SEQUENCE.json'),
        'source_pins_sha256':sha(HERE/'SOURCE_PINS.json'),'generator_sha256':sha(Path(__file__)),
        'reference_quantity_overrides':{'surface_proximity.MAX_TRIANGLE_PAIRS':{'from':16384,'to':1000000000},
            'surface_geometry.CLOSED_SOLID_MAX_PAIR_TESTS':{'from':16384,'to':1000000000},
            'surface_geometry.CLOSED_SOLID_MAX_WORK':{'from':262144,'to':1000000000}},
        'reference_unchanged':'original fac9 leaf/AABB/geometry/4096-bit/8193-scratch/ray/deadline semantics, diagnostic-only quantity overrides',
        'proposal':'exact Fraction difference of the first finite public surface nearest points B-A; common dyadic integer/gcd; one direction without search',
        'budget':{'surface_and_support_total':1179648,'complete_leaf_limit':16384,
            'support_completed_increment':'2*all_referenced_source_indices+3','closed_fallback_total':262144,
            'closed_fallback_pair_limit':16384,'closed_fallback_ray_limit':16384,'deadline_seconds':30,
            'whole_pair_budget_stop':'unknown, no fallback, no mixed explicit closed work, no counter reset'},
        'timing':{'calls':60,'source_loading':'one batch-level measured phase per source namespace, separate from per-call medians',
            'input_preparation':'fresh mesh arrays from frozen inputs, starts the complete-call clock and original deadline',
            'query_preparation':'fresh holder/diagnostics and fixed demand/options construction; no integer geometry work moved here',
            'solving':'reference original closed then surface sharing one holder; candidate surface then support and at most one original closed fallback',
            'serialization':'full returned semantic bundle and product counts encoded once, ending the complete-call clock',
            'deadline':'earliest input-preparation start +30 seconds through serialization; never reset for support/fallback',
            'primary_instrumentation':'only real product counters and original perf_counter deadline callback; no function spy or per-checkpoint dictionary',
            'cross_call_cache':'none; each arm gets fresh inputs/holder, no service cache',
            'QA_certification':'saved-only outside primary timing; no expected answer supplied to the solver',
            'non_timing_work_observation':'one fixed candidate-only pass over the same six cases, six calls; actual function spies allowed and clearly excluded from sixty timing samples',
            'full_batch_scope':'source loading, input read/hash, all samples and evidence publication also recorded separately'},
        'performance_gates':{'g508':'sum of three complete-business medians <=80% reference and each pair median <=reference',
            'simple_control':'candidate median-reference median <=max(1000000ns,reference median*0.05)',
            'fallback_each':'candidate median-reference median <=max(2000000ns,reference median*0.10)',
            'eligibility':'all common business facts independently correct for the compared samples; reference incomplete stays unmeasured, no rejection denominator',
            'semantics_disclosure':'candidate hull-separation scope and reference embedded-shell guarantee differ; only common task cost is compared'},
        'product_calls':0,'performance_calls':0,'Blender_sessions':0,'model_consumers':0,
        'authorship':'QA agent static design before root implementation-freeze commit; no claim of Agent Learning registration'})


if __name__=='__main__':
    main()
