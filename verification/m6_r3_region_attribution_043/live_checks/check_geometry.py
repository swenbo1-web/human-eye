"""Independent reconstruction checks on actual functional source-region readbacks."""
from fractions import Fraction as Q
import hashlib
import json
import struct


def need(value,reason):
    if not value:raise ValueError(reason)


def bits(rows):return b''.join(struct.pack('<d',float(x))for row in rows for x in row)


def region(capture,frozen_case,public,*,reference_shift=Q(0)):
    left,right=frozen_case['left'],frozen_case['right'];got=capture['region'];ref=capture['reference']
    need(got['source_triangle_indices']==left['native_triangle_rows'] and got['source_vertex_indices']==left['native_vertex_rows'],'actual_complete_native_maps')
    need(got['faces']==left['faces'] and bits(got['vertices'])==bits(left['vertices_world']),'actual_complete_source_geometry_bits')
    need(got['source_triangle_vertices']==[[left['native_vertex_rows'][v]for v in face]for face in left['faces']],'actual_triangle_source_vertices')
    expected=[[v[0],v[1],float(Q(v[2])+reference_shift)]for v in right['vertices_world']]
    need(ref['faces']==right['faces'] and bits(ref['vertices'])==bits(expected),'actual_complete_reference_geometry_bits')
    # Known reference is the independently certified closed Cube from the
    # frozen holdout. Translation preserves all six covered square faces.
    source=[tuple(map(Q,p))for p in got['vertices']]
    cube=[tuple(map(Q,p))for p in ref['vertices']]
    lo=tuple(min(p[k]for p in cube)for k in range(3));hi=tuple(max(p[k]for p in cube)for k in range(3))
    need(all(all(lo[k]<p[k]<hi[k]for k in range(3))for p in source),'actual_root_strict_containment')
    lower=min(min(min(p[k]-lo[k],hi[k]-p[k])for k in range(3))for p in source)
    truth=frozen_case['independent_truth'];expected_distance=Q(truth['distance_exact_m'])+reference_shift
    need(lower==expected_distance,'actual_independent_six_plane_lower_bound')
    pa=tuple(map(Q,truth['point_a_exact']));pb=(pa[0],pa[1],hi[2])
    need(pa in source and pb[2]-pa[2]==lower,'actual_frozen_point_attains_bound')
    need(public['status']=='complete' and public['selected_triangle_count']==len(left['faces']),'actual_complete_public_scope')
    need(public['distance_m'].hex()==float(lower).hex(),'actual_public_independent_distance')
    need(bits([public['point_a_m'],public['point_b_m']])==bits([list(map(float,pa)),list(map(float,pb))]),'actual_public_original_points')
    need([public['source_triangle_a'],public['source_triangle_b']]==truth['canonical_native_pair'],'actual_public_canonical_native_rows')
    need(public['direction_a_to_b']==[0.,0.,1.],'actual_public_frozen_direction')
    need(public['region_object']==capture['binding']['target'] and public['reference_object']==capture['binding']['reference'],
         'actual_public_capture_object_identity')
    need(capture['binding']['source_frame']['frame']==1 and capture['binding']['source_frame']['subframe']==0 and capture['binding']['source_frame']['scale_length']==1,'actual_fixed_frame_units')
    return {'status':'pass','selected_triangles':len(left['faces']),'distance_exact_m':str(lower),
        'canonical_native_pair':truth['canonical_native_pair'],'complete_world_geometry_binary64_exact':True,
        'reference_shift_exact_m':str(reference_shift),'current_reference_bounds_exact':[[str(x)for x in lo],[str(x)for x in hi]]}


def leases(materialized):
    need(len(materialized)==4,'four_actual_same_service_capture_returns')
    caps=[x['capture']for x in materialized];sha=[c['payload_sha256']for c in caps]
    reused=[c['work'].get('connector_reused_payload')for c in caps]
    modes=[c['work'].get('mode')for c in caps]
    need(sha[0]==sha[1] and sha[2]==sha[3] and sha[0]!=sha[2],'actual_payload_changes_after_edit')
    need(reused==[False,True,False,True],'actual_lease_invalidated_and_reestablished')
    reply=[x['residency_reply']for x in materialized]
    need(reply[1]['capture']is None and reply[3]['capture']is None and reply[2]['capture']is not None,'actual_native_full_vs_ack_replies')
    need(reply[0]['lease']==reply[1]['lease'] and reply[2]['lease']==reply[3]['lease'] and reply[0]['lease']!=reply[2]['lease'],'actual_native_lease_token_changes')
    return {'status':'pass','payload_sha256':sha,'connector_reused_payload':reused,'mode':modes,
        'basis':'actual native residency replies and actual original connector return values; not inferred from timing'}
