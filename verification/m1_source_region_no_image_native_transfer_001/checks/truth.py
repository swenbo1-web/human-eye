"""Prove six surface distances with exact separating support planes."""

from fractions import Fraction as F
import json
from math import sqrt
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
PREVIOUS = run_path(str(V/'m1_source_region_no_image_measurement_consumption_001/checks/truth.py'))
require,read,pin,vector,member,verify_source = (PREVIOUS[k] for k in
    ('require','read','pin','vector','member','verify_source'))
ASSET_SHA,DOMAIN = (PREVIOUS[key] for key in ('ASSET_SHA','DOMAIN'))
SCOPES = ('selected','whole')
ORDER = ('N1','P1','P2','N2','N3','P3')
SCENARIOS = {
    '1': {'target':'M12','reference':'M17','selected':[10,11],'threshold_m':'1',
          'anchor_a': [('17','-21/4','3/2'),('18','-21/4','3/2')],
          'anchor_b': ('37/2','-21/4','3/2'),'expected_squared':['9/4','1/4']},
    '2': {'target':'M19','reference':'M15','selected':[10,11],'threshold_m':'3',
          'anchor_a': [('327/16','-19/8','4'),('345/16','-7/8','4')],
          'anchor_b': ('91/4','1','4'),'expected_squared':['4285/256','1261/256']},
    '3': {'target':'M08','reference':'M02','selected':[4,5],'threshold_m':'9/2',
          'anchor_a': [('3','-4','1'),('3','-3','1')],
          'anchor_b': ('1/16','-1/16','1'),'expected_squared':['3089/128','2209/128']},
}
REPORT_METRES = F(1,20000)
REPORT_DIRECTION = 5e-5


def scenario(case):
    key = str(case)
    if key in ORDER:
        key = key[-1]
    require(key in SCENARIOS,'unknown_frozen_source_pair_case')
    return key,SCENARIOS[key]


def objects(source):
    return {row['name']:row for row in source['objects']}


def source_faces(source, name, indices=None):
    raw = objects(source)[name]['evaluated']
    vertices = tuple(vector(p) for p in raw['vertices_world_m'])
    triangles = tuple(tuple(face) for face in raw['triangles'])
    ids = tuple(range(len(triangles))) if indices is None else tuple(indices)
    require(ids and len(ids)==len(set(ids)) and all(type(i) is int and 0<=i<len(triangles) for i in ids),
            'invalid_object_local_evaluated_triangles/'+name)
    return vertices,triangles,ids


def pair_surfaces(source, config, scope):
    return source_faces(source,config['target'],config['selected'] if scope=='selected' else None), \
           source_faces(source,config['reference'])


def dot(a,b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def displacement(a,b):
    return tuple(y-x for x,y in zip(a,b,strict=True))


def support(surface, normal, extreme):
    vertices,triangles,indices = surface
    return extreme(dot(normal,vertices[j]) for i in indices for j in triangles[i])


def witness(a,b,sa,sb):
    ma,mb = member(a,sa),member(b,sb)
    return {'a':list(map(str,a)),'b':list(map(str,b)),'memberships':{'a':ma,'b':mb}}


def valid_witness(issued):
    return all(row['exact_source_triangle_indices'] for row in issued['memberships'].values())


def establish(source, case, scope):
    """Certify the minimum over the two actual triangle unions, without a product solver."""
    case,config = scenario(case)
    a = vector(config['anchor_a'][SCOPES.index(scope)])
    b = vector(config['anchor_b'])
    sa,sb = pair_surfaces(source,config,scope)
    d = displacement(a,b)
    d2 = dot(d,d)
    max_a = support(sa,d,max)
    min_b = support(sb,d,min)
    # Every triangle point is a convex combination of these checked vertices.
    # Cauchy–Schwarz then gives ||b'-a'|| >= (min_b - max_a) / ||d||.
    require(max_a==dot(a,d) and min_b==dot(b,d) and min_b-max_a==d2
            and d2==F(config['expected_squared'][SCOPES.index(scope)]),
            'actual_triangle_support_bounds_do_not_certify_declared_distance/'+case+'/'+scope)
    initial = witness(a,b,sa,sb)
    require(valid_witness(initial),'support_planes_are_not_attained_on_current_actual_triangles')
    alternatives = []
    for axis in range(3):
        for displacement_metres in (F(1,8),-F(1,8)):
            shifted_a = tuple(p+(displacement_metres if i==axis else 0) for i,p in enumerate(a))
            shifted_b = tuple(p+(displacement_metres if i==axis else 0) for i,p in enumerate(b))
            possible = witness(shifted_a,shifted_b,sa,sb)
            if valid_witness(possible):
                alternatives.append(possible)
    distance = sqrt(d2)
    return {'case':case,'scope':scope,'target':config['target'],'reference':config['reference'],
            'target_source_triangles':list(sa[2]),'reference_source_triangles':list(sb[2]),
            'distance_squared_m2':str(d2),'distance_m':distance,
            'direction_a_to_b':[float(p)/distance for p in d],
            'threshold_m':config['threshold_m'],'meets_threshold':d2>=F(config['threshold_m'])**2,
            'support_proof':{'normal_B_minus_A':list(map(str,d)),'max_target_vertex_projection':str(max_a),
                'min_reference_vertex_projection':str(min_b),'gap':str(min_b-max_a),
                'target_checked_triangles':len(sa[2]),'reference_checked_triangles':len(sb[2])},
            'attaining_point_pair':initial,'other_verified_attaining_pairs':alternatives}


def measured(source, case, scope, item, *, exact=False):
    _,config = scenario(case)
    independent = establish(source,case,scope)
    a,b = (vector(item[key]) for key in ('a','b'))
    direction = vector(item['direction_a_to_b'])
    squared = dot(displacement(a,b),displacement(a,b))
    length = sqrt(squared)
    distance = float(F(item['distance_m']))
    target,reference = pair_surfaces(source,config,scope)
    maximum_error = F(0) if exact else REPORT_METRES
    published_tolerance = 1e-12 if exact else float(REPORT_METRES)
    direction_tolerance = 1e-12 if exact else REPORT_DIRECTION
    memberships = {side:member(point,surface,maximum_error)
                   for side,point,surface in (('a',a,target),('b',b,reference))}
    sources = item.get('source_triangle_indices',{})
    stated = all(type(sources.get(side)) is list and sources[side]
                 and all(type(i) is int for i in sources[side])
                 and len(sources[side])==len(set(sources[side]))
                 and set(sources[side])<=set(proven['source_triangle_indices_within_tolerance'])
                 for side,proven in memberships.items())
    return {'distance_correct':abs(distance-independent['distance_m'])<=published_tolerance,
            'direction_correct':all(abs(float(p)-q)<=direction_tolerance
                                    for p,q in zip(direction,independent['direction_a_to_b'],strict=True)),
            'pair_attains':all(row['source_triangle_indices_within_tolerance'] for row in memberships.values())
                and abs(length-independent['distance_m'])<=2*published_tolerance
                and (not exact or squared==F(independent['distance_squared_m2'])),
            'stated_source_memberships_correct':stated,'actual_memberships':memberships,
            'pair_distance_m':length,'independent':independent}


def frozen_truth():
    original, reopen, asset = (PREVIOUS[key] for key in ('PRIOR_TERMINAL','REOPENED','ASSET'))
    pins = {name:pin(path,PREVIOUS[key]) for name,path,key in (
        ('saved_blend',asset,'ASSET_SHA'),('reopened_source',reopen,'REOPENED_SHA'),
        ('historical_current_source',original,'PRIOR_TERMINAL_SHA'))}
    source = read(original)
    declared = {case:{scope:establish(source,case,scope) for scope in SCOPES} for case in SCENARIOS}
    require(all(rows['selected']['meets_threshold'] and not rows['whole']['meets_threshold']
                for rows in declared.values()),'frozen_three_threshold_reversals_changed')
    require(all(declared['2'][scope]['other_verified_attaining_pairs'] for scope in SCOPES),
            'rotated_surface_alternative_point_pair_not_proven')
    return {'schema':'cross-scale-three-surface-transfer-independent-v1','source_pins':pins,
            'source':verify_source(source),'measurements':declared,
            'tolerances':{'distance_and_point_metres':str(REPORT_METRES),
                          'direction_component':REPORT_DIRECTION},
            'actual_new_Blender':0,'actual_new_models':0}


if __name__=='__main__':
    print(json.dumps(frozen_truth(),ensure_ascii=False,allow_nan=False,indent=2))
