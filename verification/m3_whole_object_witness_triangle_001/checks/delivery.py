"""Verify the new two-triangle evidence against the exact replayed original."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
H = run_path(str(NS/'checks/historical.py'))
E,T = H['E'],H['T']
require,read,pin = (H[key] for key in ('require','read','pin'))
historical = H['historical']
BASE_SHA = '338f4841654335fb6b567ae3ccba214bf370717925c6abe5592984c23b2905ac'
PROOF_SCOPE = 'one_current_triangle_per_endpoint_non_exhaustive'
DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
SIDES = ('a','b')


def wire_text(body):
    return json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def witnesses(body):
    return body['facts']['surface_proximity']['value']['nearest_witness']


def comparable(text,body,*,runtime_source_sha256,remove_extension=False):
    """Preserve exact public JSON ordering and whitespace outside declared fields."""
    require(wire_text(body)==text,'actual_public_text_not_exact_installed_compact_JSON')
    require(body['binding']['runtime_source_sha256']==runtime_source_sha256
            and type(body['trace_id']) is str and body['trace_id'],'replay_execution_attestation_not_registered')
    stable = deepcopy(body)
    stable['trace_id'] = '<actual_request_trace>'
    stable['binding']['runtime_source_sha256'] = '<actual_installed_source>'
    if remove_extension:
        del witnesses(stable)['source_triangles']
    return wire_text(stable)


def verify_witness(capture, packet, *, expected_names=None):
    """Independently verify current A and B, exact point membership and one face per side."""
    bound = packet['binding']
    listed = bound['objects']
    host = capture['host_identity']
    roster = {mesh['object_id']:mesh for mesh in capture['meshes']}
    state = capture['capture_state']
    require(packet['pair_order']=='A_to_B' and packet['unit']==capture['unit']=='m'
            and packet['coordinate_frame']==capture['coordinate_frame']=='world'
            and bound['scene_revision']==capture['revision']
            and bound['source']==capture['source']=='blender'
            and bound['capture_scope']==host['capture_scope']=='selected_objects'
            and bound['selected_count']==len(listed)==len(roster)==len(capture['meshes'])==2
            and len({row['object_id'] for row in listed})==2
            and {row['object_id'] for row in listed}==roster.keys()==host['object_instances'].keys()
            and (expected_names is None or [r['name'] for r in listed]==list(expected_names)),
            'native_current_ordered_pair_capture_or_scope_mismatch')
    closest = witnesses(packet)
    proof = closest['source_triangles']
    require(proof.keys()=={'scope','index_domain','document_epoch','capture_state','a','b'}
            and proof['scope']==PROOF_SCOPE and proof['index_domain']==DOMAIN
            and proof['document_epoch']==host['document_epoch'] and proof['capture_state']==state,
            'triangle_source_reference_not_same_capture_generation_or_domain')
    verified = {}
    for side,row in zip(SIDES,listed,strict=True):
        mesh = roster[row['object_id']]
        item = proof[side]
        require(item.keys()=={'instance_id','source_triangle_index'} and mesh['name']==row['name']
                and item['instance_id']==host['object_instances'][row['object_id']],
                'triangle_source_reference_not_same_current_ordered_object_instance/'+side)
        idx = item['source_triangle_index']
        faces = tuple(tuple(face) for face in mesh['faces'])
        vertices = tuple(T['vector'](point) for point in mesh['vertices'])
        require(type(idx) is int and 0<=idx<len(faces),'output_triangle_is_not_current_object_local_index/'+side)
        independent = T['member'](T['vector'](closest[side]),(vertices,faces,(idx,)))
        require(independent['exact_source_triangle_indices']==[idx],
                'reported_world_point_does_not_lie_on_claimed_current_triangle/'+side)
        verified[side] = {'object_id':row['object_id'],'name':row['name'],'instance_id':item['instance_id'],
                          'source_triangle_index':idx,'exact_triangle_vertex_indices':list(faces[idx]),
                          'point_m':closest[side],'minimum_squared_source_distance_m2':'0'}
    return {'scope':proof['scope'],'index_domain':proof['index_domain'],'capture_state':state,
            'document_epoch':proof['document_epoch'],'ordered_endpoints':verified}


def verify_delivery(label, baseline, candidate, *, capture, identity, require_source=True):
    original = historical(label)
    if isinstance(identity,(Path,str)):
        identity = read(identity)
    installed_source = identity['source_sha256']
    _,old_text,old = E['public'](baseline)
    candidate_result,new_text,new = E['public'](candidate)
    archived_text = comparable(original['text'],E['public'](original['reply'])[2],runtime_source_sha256=BASE_SHA)
    standard_text = comparable(old_text,old,runtime_source_sha256=BASE_SHA)
    candidate_text = comparable(new_text,new,runtime_source_sha256=installed_source,remove_extension=require_source)
    require(archived_text==standard_text==candidate_text,
            'original_stable_public_full_bytes_changed_outside_triangle_extension_and_attestation')
    capture_proof = E['prove_capture'](capture,original['source'],original['names'],
                      revision=new['binding']['scene_revision'],scope='selected_objects',
                      generation=original['capture']['capture_state'],
                      epoch=original['capture']['host_identity']['document_epoch'])
    require(new['status']=='observed' and new['execution_authority'] is False
            and new['facts'].keys()=={'surface_proximity'} and capture_proof is not None,
            'actual_registered_read_only_whole_task_capture_not_observed')
    proof = cli = None
    if require_source:
        proof = verify_witness(capture,new,expected_names=original['names'])
        require(all(item['source_triangle_index'] in original['membership'][side]
                    for side,item in proof['ordered_endpoints'].items()),
                'new_winner_triangle_not_in_original_exact_full_selection_corroboration')
        require(len(new_text.encode())<=2048,'actual_new_witness_body_exceeds_2048_bytes')
        cli = E['fixed_cli'](candidate_result,must_preserve=True)
    else:
        require('source_triangles' not in witnesses(new),'standard_endpoint_emitted_opt_in_triangle_evidence')
    return {'passed':True,'label':label,'new_source_extension':require_source,
            'original_formal_status':original['historical_status'],'actual_text_UTF8_bytes':len(new_text.encode()),
            'baseline_text_UTF8_bytes':len(old_text.encode()),'actual_text_sha256':H['digest'](new_text.encode()),
            'stable_original_public_bytes_equal':True,
            'declared_dynamic_fields':['trace_id','binding.runtime_source_sha256'],
            'original_point_pair_unchanged':True,'original_reference_membership':original['membership'],
            'actual_native_capture':capture_proof,'new_triangle_evidence':proof,'fixed_CLI':cli}


def verify_reverse(forward, reverse, *, capture):
    """Order may change ties, but reversing the ordered input must preserve distance."""
    _,_,f = E['public'](forward)
    _,_,r = E['public'](reverse)
    expected = [row['name'] for row in reversed(f['binding']['objects'])]
    proof = verify_witness(capture,r,expected_names=expected)
    fw,rv = (body['facts']['surface_proximity']['value'] for body in (f,r))
    require(fw['distance_m']==rv['distance_m']
            and all(a==-b for a,b in zip(fw['nearest_witness']['direction_a_to_b'],
                                         rv['nearest_witness']['direction_a_to_b'],strict=True)),
            'reversed_current_distance_or_world_direction_changed')
    return {'passed':True,'witness_is_same_physical_points_swapped':
            fw['nearest_witness']['a']==rv['nearest_witness']['b']
            and fw['nearest_witness']['b']==rv['nearest_witness']['a'],'proof':proof}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--label',required=True,choices=H['LABELS'])
    cli.add_argument('--baseline',type=Path,required=True)
    cli.add_argument('--candidate',type=Path,required=True)
    cli.add_argument('--capture',type=Path,required=True)
    cli.add_argument('--identity',type=Path,required=True)
    cli.add_argument('--standard',action='store_true')
    cli.add_argument('--output',type=Path)
    args = cli.parse_args()
    data = verify_delivery(args.label,read(args.baseline),read(args.candidate),capture=read(args.capture),
                           identity=args.identity,require_source=not args.standard)
    data['receipts'] = {name:pin(getattr(args,name)) for name in ('baseline','candidate','capture','identity')}
    text = json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf8',newline='\n') as sink:
            sink.write(text)
    else:
        print(text,end='')
