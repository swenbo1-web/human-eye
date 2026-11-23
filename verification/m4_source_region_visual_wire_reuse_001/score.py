"""Validate scoped wire receipts independently and reuse the registered image scorer."""
import ast
from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import inspect
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
LEGACY = HERE.parent/'m4_source_region_selective_visual_capture_001/score.py'
SPEC = importlib.util.spec_from_file_location('_previous_visual_quality', LEGACY)
old = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(old)
ORDER, ASSET, need, pin, reference_inputs = (getattr(old, name) for name in
    ('ORDER', 'ASSET', 'need', 'pin', 'reference_inputs'))
SCHEMA = 'human-eye-source-region-visual-wire-v1'
META = ('directory', 'display_snapshot', 'source_frame')
SH = re.compile(r'[0-9a-f]{64}')
RESPONSE_LIMIT = 64 * 1024 * 1024


def is_digest(value):
    return type(value) is str and SH.fullmatch(value) is not None


def digest(value):
    return old.fingerprint([value])


def ack(proof):
    if proof is None or proof['generation'] is None:
        return {}
    return {'generation': proof['generation'], 'receipt_sha256': digest(proof)}


def camera_from_source(packet):
    from human_eye_plugin.blender_host import _observation_target_cameras

    directory, kept = (packet[key] for key in ('directory', 'retained_ordinals'))
    query = packet['query']
    selector = query['target']
    field = 'name' if 'name' in selector else 'object_id'
    target, = [i for i, row in enumerate(directory) if row[field] == next(iter(selector.values()))]
    mesh = packet['meshes'][kept.index(target)]
    points, triangles = mesh['vertices'], mesh['faces']
    box = query['world_box_m']
    within = [all(a <= c <= b for a,c,b in zip(box['min'],v,box['max'],strict=True)) for v in points]
    selected = [i for i,f in enumerate(triangles) if all(within[j] for j in f)]
    need(selected and selected == packet['source_triangle_indices'], 'wire_independent_camera_wrong_region')
    indices = sorted({j for i in selected for j in triangles[i]})
    plan = _observation_target_cameras([points[j] for j in indices], [row['world_bounds_m'] for row in directory])
    plan.update(schema='active-coverage-source-region-cameras-v1',
                scope='source_region_fitted_XY_whole_scene_conservative_depth')
    plan['margin']['square_fit'] = 'selected source triangle world vertices about one common center'
    return plan


class ScopedTranscript:
    """Restore exactly what an authenticated receiver could possess in wire order."""
    def __init__(self):
        self.last = None
        self.receipts = []

    def materialize(self, sent, raw):
        need(set(raw)=={'schema','proof','camera_sha256','capture'} and raw['schema']==SCHEMA,
             'wire_expected_private_compact_envelope')
        proof, capture = raw['proof'], dict(raw['capture'])
        need(type(proof) is dict and set(proof)=={'generation','metadata_sha256','mesh_sha256'}
             and (proof['generation'] is None or is_digest(proof['generation']))
             and is_digest(proof['metadata_sha256']) and type(proof['mesh_sha256']) is list
             and all(is_digest(x) for x in proof['mesh_sha256'])
             and is_digest(raw['camera_sha256']) and 'camera_plan' not in capture,
             'wire_bad_proof_shape')
        need(sent['command']=='capture_source_region_visual'
             and sent['params']['known']==ack(self.last['proof'] if self.last else None)
             and old.same_bits(sent['params']['query'],capture['query']), 'wire_request_ack_or_query_unbound')
        prior = self.last
        same_generation = (prior is not None and ack(prior['proof']) and
                           proof['generation']==prior['proof']['generation'])
        present = [key for key in META if key in capture]
        need(len(present) in (0,len(META)), 'wire_partial_metadata_admission')
        if not present:
            need(same_generation and proof['metadata_sha256']==prior['proof']['metadata_sha256'],
                 'wire_unproven_prior_metadata')
            capture.update(prior['metadata'])
        metadata = {key:capture[key] for key in META}
        need(digest(metadata)==proof['metadata_sha256'], 'wire_metadata_digest_changed')
        kept, original_mesh = capture['retained_ordinals'], capture['meshes']
        need(len(original_mesh)==len(kept)==len(proof['mesh_sha256']) and
             kept==sorted(set(kept)) and all(type(i) is int and 0 <= i < len(metadata['directory']) for i in kept),
             'wire_original_ordinals_or_mesh_hashes_changed')
        meshes, slots, refs = [], {}, []
        for i, value, wanted in zip(kept, original_mesh, proof['mesh_sha256'], strict=True):
            if type(value) is str:
                hit = prior['meshes'].get(i) if same_generation else None
                need(hit is not None and hit[0]==value==wanted and
                     old.same_bits(metadata['directory'][i],prior['metadata']['directory'][i]),
                     'wire_missing_or_wrong_instance_resource_reference')
                value = hit[1]
                refs.append(i)
            need(type(value) is dict and digest(value)==wanted and
                 metadata['directory'][i]['object_id']==value['object_id'],
                 'wire_current_mesh_digest_or_object_differs')
            slots[i] = (wanted, value)
            meshes.append(value)
        capture['meshes'] = meshes
        plan = camera_from_source(capture)
        need(digest(plan)==raw['camera_sha256'], 'wire_camera_digest_not_current_box')
        capture['camera_plan'] = plan
        unsigned = {k:v for k,v in capture.items() if k!='sha256'}
        source = {k:v for k,v in unsigned.items() if k not in ('revision','work')}
        need(digest(unsigned)==capture['sha256'] and capture['revision']=='source-region-visual:'+digest(source),
             'wire_materialized_original_contract_changed')
        restored_bytes = len(json.dumps(capture,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode())
        limit = sent['params']['max_response_bytes']
        need(type(limit) is int and 0 < restored_bytes <= limit <= RESPONSE_LIMIT,'wire_materialized_over_original_ceiling')
        self.last = {'proof':proof,'metadata':metadata,'meshes':slots}
        entry = {'metadata_referenced':not present, 'generation':proof['generation'],
            'restored_capture_bytes':restored_bytes, 'camera_sha256':raw['camera_sha256'],
            'referenced_original_ordinals':refs, 'referenced_meshes':[metadata['directory'][i]['name'] for i in refs],
            'sent_original_ordinals':[i for i in kept if i not in refs],
            'sent_vertices':sum(len(m['vertices']) for m in original_mesh if type(m) is dict),
            'sent_triangles':sum(len(m['faces']) for m in original_mesh if type(m) is dict),
            'kept_meshes':len(kept),
            'host_work':deepcopy(capture['work'])}
        self.receipts.append(entry)
        return capture

    def exchange(self, tx, rx):
        sent, body = HOST_EXCHANGE(tx, rx)
        if sent['command'] != 'capture_source_region_visual':
            return sent, body
        limit = sent['params']['max_response_bytes']
        need(type(limit) is int and len(rx) <= limit, 'wire_over_original_transport_ceiling')
        value = self.materialize(sent, body)
        self.receipts[-1].update(tcp_tx_bytes=len(tx),tcp_rx_bytes=len(rx))
        return sent, value


HOST_EXCHANGE = old.host_exchange


def previous_geometry_check():
    # Retain the prior independently accepted source/display/geometry checks.
    # The new cache-aware accounting replaces only the prior physical-work tail.
    path = str(LEGACY)
    definition, = ast.parse(inspect.getsource(old.verify_b_host)).body
    cuts = [i for i,node in enumerate(definition.body) if isinstance(node,ast.Assign)
            and [ast.unparse(t) for t in node.targets]==['transmitted_vertices']]
    cut, = cuts
    need(definition.name=='verify_b_host' and cut>0 and
         isinstance(definition.body[-1],ast.Return),'prior_scorer_accounting_anchor_changed')
    definition.body = definition.body[:cut] + ast.parse('return True').body
    namespace = dict(vars(old))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[definition],type_ignores=[])),path,'exec'),namespace)
    return namespace['verify_b_host']


GEOMETRY = previous_geometry_check()


def verify_scoped_work(raw, entry):
    work = raw['work']
    meshes = raw['meshes']
    expanded_v = sum(len(m['vertices']) for i,m in zip(raw['retained_ordinals'],meshes,strict=True)
                     if i in entry['sent_original_ordinals'])
    expanded_f = sum(len(m['faces']) for i,m in zip(raw['retained_ordinals'],meshes,strict=True)
                     if i in entry['sent_original_ordinals'])
    selected_v = sum(len(m['vertices']) for m in meshes)
    selected_f = sum(len(m['faces']) for m in meshes)
    count = raw['directory']
    expected = {
        'depsgraph_fetches':1,'source_objects':len(count),
        'source_vertices':sum(x['vertex_count'] for x in count),
        'source_triangles':sum(x['triangle_count'] for x in count),
        'retained_objects': entry['kept_meshes'],
        'omitted_objects':len(count)-entry['kept_meshes'],
        'omitted_vertices_checked':sum(x['vertex_count'] for x in count)-selected_v,
        'omitted_polygons_checked':sum(x['triangle_count'] for x in count)-selected_f,
        'omitted_loop_indices_checked':3*(sum(x['triangle_count'] for x in count)-selected_f),
        'to_mesh':len(entry['sent_original_ordinals']),'triangulations':len(entry['sent_original_ordinals']),
        'to_mesh_clear':len(entry['sent_original_ordinals']),
        'expanded_vertices':expanded_v,'expanded_triangles':expanded_f,
        'world_vertices_transformed':expanded_v,
        'sent_vertices':entry['sent_vertices'],'sent_triangles':entry['sent_triangles'],
    }
    need(all(work[key]==value for key,value in expected.items()),'wire_current_physical_resource_work_counts_changed')
    return {**work, 'transmitted_objects':len(entry['sent_original_ordinals']),
            'transmitted_vertices':entry['sent_vertices'],'transmitted_triangles':entry['sent_triangles']}


@contextmanager
def bound_scoring():
    sequence = ScopedTranscript()
    previous = old.verify_b_host

    def checked(sent, result, *args):
        GEOMETRY(sent,result,*args)
        return verify_scoped_work(result,sequence.receipts[-1])

    old.host_exchange, old.verify_b_host = sequence.exchange, checked
    try:
        yield sequence
    finally:
        old.host_exchange, old.verify_b_host = HOST_EXCHANGE, previous


def verify_pair(slot_a, slot_b, reference=None):
    with bound_scoring() as recovered:
        result = old.verify_pair(slot_a, slot_b, reference)
    first, second = recovered.receipts
    need(not first['metadata_referenced'] and not first['referenced_meshes']
         and second['metadata_referenced'] and first['generation'] is not None
         and first['generation']==second['generation'] and set(second['referenced_meshes'])=={'M10','M11'}
         and first['camera_sha256']!=second['camera_sha256'],
         'paired_wire_metadata_shared_resource_or_new_camera_control_failed')
    result['private_wire_receipts'] = dict(zip(ORDER,recovered.receipts,strict=True))
    return result
