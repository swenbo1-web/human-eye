"""Independently validate both ordered current whole-object qualification pairs."""

from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
T = run_path(str(NS/'checks/truth.py'))
D = run_path(str(V/'m3_whole_object_witness_triangle_001/checks/delivery.py'))
E = D['E']
public,fixed_cli,prove_capture,edge_counts = (E[key] for key in ('public','fixed_cli','prove_capture','edge_counts'))
require,read,pin,TARGET,REFERENCES = (T[key] for key in ('require','read','pin','TARGET','REFERENCES'))
FACT = 'surface_proximity'


def verify_pair(reference, reply, producer, capture, source, installed, *, require_source):
    """Prove metadata, scope and geometry against the exact decoded producer capture."""
    if not isinstance(installed,dict):
        installed = read(installed)
    content,text,packet = public(reply)
    bound = packet['binding']
    names = [TARGET, reference]
    rows = T['objects'](source)
    expected = [{'object_id':rows[name]['object_id'],'name':name} for name in names]
    require(reference in REFERENCES and packet==producer
            and packet['result_kind']=='task_query' and packet['schema_version']=='task-query-v3'
            and packet['status']=='observed' and packet['execution_authority'] is False
            and packet['pair_order']=='A_to_B' and packet['unit']=='m'
            and packet['coordinate_frame']=='world' and packet['facts'].keys()=={FACT}
            and 'region_ref' not in packet and 'region_source' not in bound
            and bound['objects']==expected and bound['capture_scope']=='selected_objects'
            and bound['selected_count']==2 and bound['candidate_count']==21
            and bound['runtime_source_sha256']==installed['source_sha256'],
            'public_whole_pair_scope_order_or_producer_identity_changed/'+reference)
    if capture is None:
        raise ValueError('actual_qualification_source_capture_required')
    require(capture['task_selection']['bindings']==expected,'actual_current_capture_bound_wrong_ordered_objects')
    current = prove_capture(capture,source,names,revision=bound['scene_revision'],scope='selected_objects')
    fact = packet['facts'][FACT]
    value = fact['value']
    point = value['nearest_witness']
    require(fact['status']==fact['direction_status']==fact['witness_status']=='measured'
            and fact['semantics']=='current_evaluated_triangle_surfaces_world_metres'
            and value['topology']==[edge_counts(rows[name]['evaluated']['triangles']) for name in names],
            'unmeasured_world_facts_or_wrong_actual_whole_surface_topology/'+reference)
    verified = T['measured'](source,reference,{'distance_m':value['distance_m'],**point},exact=True)
    require(all(verified[key] for key in ('distance_correct','direction_correct','actual_attaining_pair')),
            'actual_points_or_direction_do_not_attain_current_exact_supported_minimum/'+reference)
    closure = None
    if require_source:
        require('source_triangles' in point and len(text.encode())<=2048,
                'candidate_missing_bound_source_triangles_or_exceeds_2048_bytes/'+reference)
        closure = D['verify_witness'](capture,packet,expected_names=names)
        require(all(row['source_triangle_index'] in verified['memberships'][side]['exact_source_triangle_indices']
                    for side,row in closure['ordered_endpoints'].items()),
                'candidate_face_not_equivalent_actual_current_surface_membership/'+reference)
    else:
        require('source_triangles' not in point,'old_endpoint_unexpected_source_field')
    return {'passed':True,'ordered_objects':names,'scope':'whole_objects','actual_body_utf8_bytes':len(text.encode()),
            'current_capture':current,'source_evidence':closure,'distance_m':value['distance_m'],
            'a':point['a'],'b':point['b'],'direction_a_to_b':point['direction_a_to_b'],
            'exact_source_memberships':verified['memberships'],'support_proof':verified['expected']['support_proof'],
            'meets_2_5m':verified['expected']['meets_threshold'],
            'fixed_CLI':fixed_cli(content,must_preserve=True),'actual_image_blocks':0}


def verify_qualification(slot, replies, producers, captures, *, binding, require_source, source=None):
    slot = Path(slot).resolve(strict=True)
    first = read(slot/'initial_capture/TERMINAL_SOURCE.json')
    source = read(slot/'TERMINAL_SOURCE.json') if source is None else source
    installed = binding if isinstance(binding,dict) else read(binding)
    require(all(tuple(groups)==REFERENCES for groups in (replies,producers,captures)),
            'actual_qualification_pair_sequence_must_be_M19_then_M14')
    geometry = T['verify_source'](source,first)
    pairs = {ref:verify_pair(ref,replies[ref],producers[ref],captures[ref],source,installed,require_source=require_source)
             for ref in REFERENCES}
    first_capture,last_capture = (captures[ref] for ref in REFERENCES)
    a,b = first_capture['capture_state'],last_capture['capture_state']
    require(all(a[field]==b[field] for field in ('instance_id','epoch','revision'))
            and a['selection_key']!=b['selection_key']
            and first_capture['host_identity']['document_epoch']==last_capture['host_identity']['document_epoch']
            and not pairs['M19']['meets_2_5m'] and pairs['M14']['meets_2_5m']
            and pairs['M19']['distance_m']<pairs['M14']['distance_m'],
            'actual_two_current_pairs_or_threshold_order_detached')
    return {'passed':True,'pairs':pairs,'source':geometry,'threshold_m':2.5,'closer_reference':'M19',
            'actual_image_blocks':0,'qualified_same_scene_generation':{key:a[key] for key in ('instance_id','epoch','revision')}}
