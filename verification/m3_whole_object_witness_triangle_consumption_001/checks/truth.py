"""Exact whole-object supports and independently verified equivalent point pairs."""

from fractions import Fraction as F
import json
from math import sqrt
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
OLD = run_path(str(V/'m1_source_region_no_image_native_transfer_001/checks/truth.py'))
SOURCE = OLD['PREVIOUS']
require,read,pin,vector,source_faces,member,objects,dot,support,witness,valid_witness,verify_source = (
    OLD[key] for key in ('require','read','pin','vector','source_faces','member','objects','dot','support',
                         'witness','valid_witness','verify_source'))
TARGET = 'M16'
REFERENCES = ('M19','M14')
THRESHOLD = F(5,2)
REPORT_METRES = F(1,20000)
REPORT_DIRECTION = 5e-5
ANCHORS = {'M19':(('99/4','-13/8','7/2'),('361/16','-13/8','7/2'),F(1225,256)),
           'M14':(('99/4','-3/4','3/2'),('89/4','1/4','3/2'),F(29,4))}


def establish(source,reference):
    require(reference in REFERENCES,'unregistered_reference_whole_object')
    starts,ends,expected_squared = ANCHORS[reference]
    a,b = vector(starts),vector(ends)
    selected,target = (source_faces(source,name) for name in (TARGET,reference))
    d = OLD['displacement'](a,b)
    gap_a,gap_b = support(selected,d,max),support(target,d,min)
    squared = dot(d,d)
    # Checked vertices are the actual source triangle vertices in both entire objects.
    # The convex combination on every triangle preserves each extreme-plane bound.
    require(gap_a==dot(d,a) and gap_b==dot(d,b) and gap_b-gap_a==squared==expected_squared,
            'true_triangle_support_plane_gap_changed/'+reference)
    original = witness(a,b,selected,target)
    require(valid_witness(original),'certified_distances_are_not_attained_on_both_current_surfaces/'+reference)
    alternatives = []
    for delta in (F(1,8),F(-1,8),F(1,4),F(-1,4)):
        shifted = witness((a[0],a[1],a[2]+delta),(b[0],b[1],b[2]+delta),selected,target)
        if valid_witness(shifted):
            alternatives.append(shifted)
    require(alternatives,'same_distance_true_equivalent_surface_point_pair_missing/'+reference)
    distance = sqrt(squared)
    return {'ordered_objects':[TARGET,reference],'scope':'whole_objects','threshold_m':float(THRESHOLD),
            'distance_squared_m2':str(squared),'distance_m':distance,'direction_a_to_b':[float(x)/distance for x in d],
            'meets_threshold':squared>=THRESHOLD*THRESHOLD,'attaining_point_pair':original,
            'alternative_point_pairs':alternatives,
            'support_proof':{'normal_B_minus_A':list(map(str,d)),'max_target_projection':str(gap_a),
                'min_reference_projection':str(gap_b),'projection_gap':str(gap_b-gap_a),
                'checked_target_triangles':len(selected[2]),'checked_reference_triangles':len(target[2]),
                'support_uses_real_world_triangle_vertices':True}}


def measured(source,reference,item,*,exact=False):
    proof = establish(source,reference)
    a,b = vector(item['a']),vector(item['b'])
    length_sq = dot(OLD['displacement'](a,b),OLD['displacement'](a,b))
    vector_report = vector(item['direction_a_to_b'])
    calculated_len = sqrt(length_sq)
    distance = float(F(item['distance_m']))
    position_tol = F(0) if exact else REPORT_METRES
    length_tol = 1e-12 if exact else float(REPORT_METRES)
    direction_tol = 1e-12 if exact else REPORT_DIRECTION
    memberships = {side:member(point,source_faces(source,name),position_tol)
                   for side,point,name in (('a',a,TARGET),('b',b,reference))}
    faces = item.get('source_triangle_indices',{})
    stated = all(type(faces.get(side)) is list and faces[side]
                 and all(type(n) is int for n in faces[side]) and len(set(faces[side]))==len(faces[side])
                 and set(faces[side])<=set(truth['source_triangle_indices_within_tolerance'])
                 for side,truth in memberships.items())
    return {'distance_correct':abs(distance-proof['distance_m'])<=length_tol,
            'direction_correct':all(abs(float(v)-w)<=direction_tol
                 for v,w in zip(vector_report,proof['direction_a_to_b'],strict=True)),
            'actual_attaining_pair':abs(calculated_len-proof['distance_m'])<=2*length_tol
                and (not exact or length_sq==F(proof['distance_squared_m2']))
                and all(m['source_triangle_indices_within_tolerance'] for m in memberships.values()),
            'claimed_source_triangle_indices_are_current':stated,'memberships':memberships,
            'pair_distance_m':calculated_len,'expected':proof}


def frozen_truth():
    original = pin(SOURCE['PRIOR_TERMINAL'],SOURCE['PRIOR_TERMINAL_SHA'])
    source = read(SOURCE['PRIOR_TERMINAL'])
    facts = {ref:establish(source,ref) for ref in REFERENCES}
    require(not facts['M19']['meets_threshold'] and facts['M14']['meets_threshold']
            and F(facts['M19']['distance_squared_m2'])<F(facts['M14']['distance_squared_m2']),
            'independent_frozen_threshold_or_closest_pair_changed')
    return {'schema':'m3-whole-object-consumption-independent-v1',
            'assets':{'blend':pin(SOURCE['ASSET'],SOURCE['ASSET_SHA']),
                      'reopened':pin(SOURCE['REOPENED'],SOURCE['REOPENED_SHA']),
                      'current_sealed_source':original},'source':verify_source(source),
            'order':list(REFERENCES),'threshold_m':float(THRESHOLD),'closer_reference':'M19','facts':facts,
            'human_report_tolerances':{'metres':str(REPORT_METRES),'direction_component':REPORT_DIRECTION},
            'actual_new_Blender':0,'actual_new_models':0}


if __name__=='__main__':
    print(json.dumps(frozen_truth(),ensure_ascii=False,allow_nan=False,indent=2))
