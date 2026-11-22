"""Check real rounded-witness certificates without a product geometry dependency."""

from copy import deepcopy
from math import sqrt
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
G = run_path(str(NS/'checks/geometry.py'))
F = run_path(str(NS/'checks/fixtures.py'))
OLD = run_path(str(V/'m3_whole_object_witness_triangle_001/checks/delivery.py'))
require,read,pin = (F[key] for key in ('require','read','pin'))
BASE_SHA = 'd39b0da9913dc31f55944a10b0299c15acc265a2d4d33d77a39e4798c65cb8c7'
EXACT = 'exact_source_triangles'
STRICT = 'source_triangles'
SIDES = ('a','b')
CERT_LIMIT = 1024
WORLD_POINTS = ('point_a_world','point_b_world')
LIMITS = {'linear':2304,'tree':3072,'success':2048}


def differences(points,distance,direction):
    a,b = points
    d = tuple(q-p for p,q in zip(a,b,strict=True))
    length = sqrt(sum(v*v for v in d))
    require(abs(length-distance)<1e-11,'certificate_exact_points_and_reported_distance_disagree')
    if direction is not None:
        require(length>0 and len(direction)==3
                and all(abs(float(v)/length-q)<1e-11 for v,q in zip(d,direction,strict=True)),
                'certificate_exact_points_and_reported_world_direction_disagree')


def verify_kernel(mesh_a,mesh_b, baseline,candidate, *, expect_exact=None,expected_indices=None,prove_global=False):
    """Verify a cold installed result, preserving original public numeric fields exactly."""
    omitted = {'work','exact_witness_triangles'}
    old = {key:value for key,value in baseline.items() if key not in omitted}
    new = {key:value for key,value in candidate.items() if key not in omitted}
    require(G['canonical'](old)==G['canonical'](new),'original_kernel_display_facts_or_strict_winners_changed')
    added = candidate.get('exact_witness_triangles')
    strict = candidate.get('witness_triangle_indices')
    if expect_exact is not None:
        require((added is not None) is expect_exact,'kernel_exact_certificate_presence_not_expected')
    require(not added or strict is None,'strict_and_exact_kernel_witness_must_be_exclusive')
    if added is None and strict is None:
        require(expected_indices is None and not prove_global,'required_actual_current_winner_not_published')
        return {'passed':True,'variant':None,'original_display_unchanged':True}
    meshes = [G['surface'](item) for item in (mesh_a,mesh_b)]
    shown = [candidate[key] for key in WORLD_POINTS]
    if added is not None:
        require(type(added) is dict and added.keys()=={'indices','points_m'},'kernel_exact_certificate_shape_changed')
        indices,reported = added['indices'],added['points_m']
    else:
        indices,reported = list(strict),shown
    require(expected_indices is None or list(expected_indices)==indices,'actual_original_winner_indices_changed')
    points,proof = G['checked_points'](meshes,indices,reported,shown,expect_exact=added is not None)
    differences(points,candidate['distance_m'],candidate['direction_a_to_b'])
    global_proof = G['prove_global'](meshes,*points) if prove_global else None
    return {'passed':True,'variant':'exact' if added is not None else 'strict','indices':indices,'points':proof,
            'independent_global_distance':global_proof,'original_display_unchanged':True}


def verify_certificate(capture,packet,*,expect_exact,expected_order=None,prove_global=False,label=None):
    """Bind rational points to the captured face rows and the original displayed pair."""
    point = OLD['witnesses'](packet)
    if not expect_exact:
        require(EXACT not in point,'old_strict_witness_must_not_gain_new_exact_extension')
        return {'variant':'strict','source':OLD['verify_witness'](capture,packet,expected_names=expected_order)}
    require(STRICT not in point and EXACT in point,'rounded_pair_must_emit_only_independent_exact_witness')
    ext = point[EXACT]
    require(type(ext) is dict and ext.keys()=={'scope','index_domain','document_epoch','capture_state','a','b'}
            and len(G['encode']({EXACT:ext}).encode())<=CERT_LIMIT,
            'exact_public_source_certificate_schema_or_1024_byte_bound_changed')
    bound = packet['binding']
    listed = bound['objects']
    roster = {mesh['object_id']:mesh for mesh in capture['meshes']}
    host = capture['host_identity']
    require(packet['pair_order']=='A_to_B' and packet['unit']==capture['unit']=='m'
            and packet['coordinate_frame']==capture['coordinate_frame']=='world'
            and bound['scene_revision']==capture['revision'] and bound['source']==capture['source']=='blender'
            and bound['capture_scope']==host['capture_scope']=='selected_objects'
            and bound['selected_count']==len(listed)==len(capture['meshes'])==len(roster)==2
            and {row['object_id'] for row in listed}==roster.keys()==host['object_instances'].keys()
            and (expected_order is None or [row['name'] for row in listed]==list(expected_order)),
            'exact_public_proof_order_scope_or_actual_capture_detached')
    require(ext['scope']==OLD['PROOF_SCOPE'] and ext['index_domain']==OLD['DOMAIN']
            and ext['capture_state']==capture['capture_state'] and ext['document_epoch']==host['document_epoch'],
            'exact_public_proof_does_not_bind_current_capture_generation')
    surfaces,indices,quoted = [],[],[]
    for side,row in zip(SIDES,listed,strict=True):
        mesh = roster[row['object_id']]
        item = ext[side]
        require(item.keys()=={'instance_id','source_triangle_index','point_m'} and mesh['name']==row['name']
                and item['instance_id']==host['object_instances'][row['object_id']],
                'exact_public_proof_current_instance_or_order_changed/'+side)
        surfaces.append(G['surface'](mesh))
        indices.append(item['source_triangle_index'])
        quoted.append(item['point_m'])
    points,proof = G['checked_points'](surfaces,indices,quoted,[point[k] for k in SIDES],expect_exact=True)
    differences(points,packet['facts']['surface_proximity']['value']['distance_m'],point['direction_a_to_b'])
    optimum = G['prove_global'](surfaces,*points) if prove_global else None
    if label is not None and optimum is not None:
        G['verify_registered'](label,indices,points,optimum)
    return {'variant':'exact','indices':indices,'certificate_UTF8_bytes':len(G['encode']({EXACT:ext}).encode()),
            'generation':ext['capture_state'],'exact_points':proof,
            'independent_global_distance':optimum}


def comparable(text,body,*,source_sha,drop_exact=False,drop_strict=False):
    require(G['encode'](body)==text and body['binding']['runtime_source_sha256']==source_sha
            and type(body['trace_id']) is str and body['trace_id'],'real_public_JSON_shape_or_attestation_changed')
    stable = deepcopy(body)
    stable['binding']['runtime_source_sha256']='<registered_source_sha256>'
    stable['trace_id']='<dynamic_request_trace>'
    if drop_exact:
        del OLD['witnesses'](stable)[EXACT]
    if drop_strict:
        del OLD['witnesses'](stable)[STRICT]
    return G['encode'](stable)


def verify_delivery(label,baseline,candidate,*,capture,identity,evidence=True):
    frozen = F['fixture'](label)
    source_sha = identity['source_sha256']
    _,old_text,old = OLD['E']['public'](baseline)
    result,text,body = OLD['E']['public'](candidate)
    expected_exact = frozen['family']!='success' and evidence
    require(capture==frozen['capture'] and body['binding']['scene_revision']==capture['revision']
            and body['pair_order']=='A_to_B' and body['unit']=='m' and body['coordinate_frame']=='world'
            and body['status']=='observed' and body['execution_authority'] is False
            and body['facts'].keys()=={'surface_proximity'}
            and [row['name'] for row in body['binding']['objects']]==list(frozen['names']),
            'actual_replay_not_current_registered_ordered_whole_capture')
    original = comparable(old_text,old,source_sha=BASE_SHA,drop_exact=False)
    normalized = comparable(text,body,source_sha=source_sha,drop_exact=expected_exact)
    require(normalized==original,'stable_original_public_geometry_facts_order_or_binding_changed')
    records = None
    if evidence:
        records = verify_certificate(capture,body,expect_exact=expected_exact,expected_order=frozen['names'],
                                     prove_global=expected_exact,label=label)
    else:
        require(EXACT not in OLD['witnesses'](body) and STRICT not in OLD['witnesses'](body),
                'unqualified_standard_route_leaked_opt_in_source_extension')
    if frozen['historical_reply'] is not None:
        _,prior_text,prior = OLD['E']['public'](frozen['historical_reply'])
        require(original==comparable(prior_text,prior,source_sha=BASE_SHA,drop_strict=not evidence),
                'actual_previous_success_raw_fields_or_order_no_longer_match')
    limit = LIMITS[frozen['family']]
    require(len(text.encode())<=limit,'actual_public_rounded_body_over_registered_CLI_budget')
    cli = OLD['E']['fixed_cli'](result,must_preserve=True)
    return {'passed':True,'case':label,'public_UTF8_bytes':len(text.encode()),'baseline_UTF8_bytes':len(old_text.encode()),
            'body_limit':limit,'original_stable_public_bytes_unchanged':True,'proof':records,'fixed_CLI':cli,
            'allowed_dynamic_fields':['trace_id','binding.runtime_source_sha256'],'actual_image_blocks':0}
