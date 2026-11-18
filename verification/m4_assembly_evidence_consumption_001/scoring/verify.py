"""Independently replay the frozen truth and audit sealed consumption originals."""

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat


HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
ARMS = ('A1', 'B1')
NAMES = ('N16', 'N13', 'N08', 'N28')
PRODUCTS = ('0d75c8f7f3522c4c7f2a5807f51f86fc4f2bec49efa9a215bf090775787ab91b',
            '99d9b5e93ae10294309df2258b0582405861c0189ab15d659ae9b9e26df6ec9a')
GATES = ('R13', 'R08', 'R28', 'G08', 'G28', 'W08', 'W28', 'N1', 'P13', 'S1')
EPS = 2.9103830456733704e-11


def read(path):
    return json.loads(path.read_bytes())


def sha(value):
    return hashlib.sha256(value).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pinned_module(name, relative, digest):
    path = BASE / relative
    require(sha(path.read_bytes()) == digest, 'frozen scorer changed/' + relative)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixed = pinned_module('frozen_exact_assembly_oracle', 'm4_assembly_evidence_first_001/scoring/verify.py',
                      '214c0672131ed2d2f4b237adb9fe663e88f77bb72c841cbabe5b136594b58082')
geometry = pinned_module('frozen_answer_geometry', 'm4_live_assembly_relation_task_001/scoring/verify_evidence.py',
                         '28705e4566ff8d61c99b92959bee96375c9674bdeed7ace0ce63b67bb37701f1')


def expected():
    case = fixed.fixed_inputs()['second_assembly']
    require(case['names'] == NAMES, 'unexpected fixed operands')
    truth = read(fixed.TRUTH)
    witness = next(row['strict_interior_witness']['world_m'] for row in truth['relations'] if row['neighbor_id'] == 'N13')
    strict = geometry.shared_interior_check(case['meshes']['N16'], case['meshes']['N13'], list(map(str, witness)))
    require(strict['pass'], 'independent shared interior witness did not replay')
    return {
        'input_sha256': {p.relative_to(BASE).as_posix(): value for p, value in fixed.PINS.items()},
        'operands': NAMES, 'zero_geometric_tolerance': True, 'world_arithmetic_bound_m': EPS,
        'gates': GATES, 'outcomes': case['outcomes'], 'nearest_separated': case['nearest'],
        'independent_strict_interior_certificate': strict,
        'saved_scene_meshes': len(case['meshes']),
        'selected_mesh_counts': {name: {'vertices': len(case['meshes'][name]['vertices']),
                                        'triangles': len(case['meshes'][name]['faces'])} for name in NAMES},
    }


def oriented_edges(rows):
    edges = Counter((a, b) for row in rows for a, b in zip(row, row[1:] + row[:1]))
    return {edge: number - edges[tuple(reversed(edge))] for edge, number in edges.items()
            if number > edges[tuple(reversed(edge))]}


def same_surface(name, observed, ref):
    if fixed.face_set(observed['triangles']) == fixed.face_set(ref['faces']):
        return 'same_oriented_triangles_exact_order' if observed['triangles'] == ref['faces'] else 'oriented_triangle_rows_reordered'
    require(len(observed['triangles']) == len(observed['triangle_polygons']), 'face-to-polygon row count mismatch/' + name)
    points = tuple(fixed.point(v) for v in observed['vertices'])
    polygons = ref['polygons']
    groups = [[] for _ in polygons]
    for triangle, polygon in zip(observed['triangles'], observed['triangle_polygons']):
        require(type(polygon) is int and 0 <= polygon < len(polygons) and len(set(triangle)) == 3
                and set(triangle) <= set(polygons[polygon]), 'evaluated triangle differs from its native polygon/' + name)
        groups[polygon].append(triangle)
    for polygon, group in zip(polygons, groups):
        normal = tuple(sum(parts) for parts in zip(*(fixed.cross(points[a], points[b])
                      for a, b in zip(polygon, polygon[1:] + polygon[:1]))))
        origin = points[polygon[0]]
        require(any(normal) and all(fixed.dot(normal, fixed.sub(points[i], origin)) == 0 for i in polygon)
                and len(group) == len(polygon) - 2 and oriented_edges(group) == oriented_edges([polygon]),
                'retriangulation does not cover same planar polygon/' + name)
        for a, b, c in group:
            require(fixed.dot(normal, fixed.cross(fixed.sub(points[b], points[a]), fixed.sub(points[c], points[a]))) > 0,
                    'retriangulation reverses or degenerates polygon/' + name)
    return 'independently_verified_planar_retessellation'


def terminal(slot, frozen):
    path = slot / 'TERMINAL_SOURCE.json'
    data, device = read(path), read(slot / 'DEVICE_EVIDENCE.json')
    receipt = device['terminal_source']
    closed = read(slot / 'native/WORKER_CLOSED.json')
    result_path = slot / 'SLOT_RESULT.json'
    result, publication = read(result_path), read(slot / 'SLOT_PUBLICATION.json')
    state, source = closed['full_final_state'], data['source']
    asset = Path(source['asset_copy']).resolve()
    asset_sha = fixed.PINS[fixed.ASSET]
    require(data['schema'] == 'm4-live-assembly-terminal-source-v1'
            and source['kind'] == 'actual_owned_Blender_evaluated_mesh'
            and source['source_index_domain'] == 'zero_based_object_local_current_evaluated_capture_triangle_rows'
            and source['scale_length'] == 1.0, 'unexpected terminal source domain')
    require(receipt in device['sources'] and receipt == result['terminal_source']
            and result['slot'] == publication['slot'] == device['label'] == slot.name
            and sha(result_path.read_bytes()) == publication['result_sha256']
            and receipt['status'] == 'complete' and receipt['terminal'] is True
            and Path(receipt['path']).resolve() == path.resolve() and receipt['bytes'] == path.stat().st_size
            and receipt['sha256'] == sha(path.read_bytes()), 'terminal receipt mismatch')
    parent, worker = receipt['parent_read'], receipt['worker']
    worker_path = Path(receipt['worker_path']).resolve()
    require(worker_path.is_relative_to(slot / 'terminal_sources') and worker_path.read_bytes() == path.read_bytes()
            and source['pid'] == worker['pid'] == closed['pid']
            and worker['sha256'] == receipt['sha256'] and worker['bytes'] == receipt['bytes']
            and parent['started_ns'] <= data['started_ns'] == worker['started_ns']
            <= data['geometry_read_closed_ns'] == worker['geometry_read_closed_ns'] <= worker['file_closed_ns']
            <= parent['closed_ns'] <= closed['closed_ns'] <= closed['original_deadline_ns'] == result['owned_deadline_ns'],
            'terminal snapshot not bound to owned process and deadline')
    require(asset.is_relative_to(slot) and asset.suffix == '.blend'
            and asset_sha == device['asset_sha256'] == source['asset_sha256'] == sha(asset.read_bytes()),
            'asset identity mismatch')
    if os.name == 'nt':
        require(asset.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY, 'owned asset copy is writable')
    guard = sha((json.dumps(state, sort_keys=True, ensure_ascii=True, allow_nan=False) + '\n').encode('ascii'))
    require(guard == closed['initial_geometry_fingerprint'] == closed['final_geometry_fingerprint']
            and closed['full_initial_state'] == state and closed['scene_unchanged'] is True
            and closed['protected_files_unchanged'] is True and not closed['poisoned'] and not closed['prohibited_events']
            and all(source[k] == state[k] for k in ('frame', 'subframe', 'scene', 'view_layer', 'view_layer_id', 'scale_length', 'asset_copy')),
            'unchanged-scene guard mismatch')
    by_name = {m['name']: m for m in data['objects']}
    guarded = {m['name']: m for m in state['objects'] if m['type'] == 'MESH'}
    require(len(by_name) == len(data['objects']) == 28 and by_name.keys() == guarded.keys() == frozen.keys(),
            'owned mesh coverage mismatch')
    require(len({m['object_id'] for m in by_name.values()}) == len({m['instance_id'] for m in by_name.values()}) == 28,
            'owned source identity alias')
    readings = {}
    for name, mesh in by_name.items():
        reference, before = frozen[name], guarded[name]
        evaluated, native = mesh['evaluated'], mesh['native']
        require(mesh['instance_id'] == before['instance_id'] and mesh['native_matrix_world'] == before['matrix_world']
                and native['vertices'] == before['vertices'] == reference['local_vertices']
                and native['polygons'] == before['polygons'] == reference['polygons']
                and evaluated['vertices'] == reference['local_vertices']
                and mesh['matrix_world'] == reference['matrix_world'], 'current array or transform drift/' + name)
        world = [geometry.transform(p, mesh['matrix_world'], 1) for p in evaluated['vertices']]
        deviations = [max(math.dist(a, b), math.dist(a, c))
                      for a, b, c in zip(world, evaluated['vertices_world_m'], reference['world_vertices'])]
        require(len(deviations) == len(world) == len(evaluated['vertices_world_m']) == len(reference['world_vertices'])
                and max(deviations) <= EPS, 'current world coordinates differ/' + name)
        digest = sha(fixed.canonical({'matrix_world': mesh['matrix_world'], 'scale_length': 1.0, 'evaluated': evaluated}) + b'\n')
        require(mesh['mesh_sha256'] == receipt['mesh_sha256'][name] == digest, 'evaluated mesh digest mismatch/' + name)
        readings[name] = {'mesh_sha256': digest, 'object_id': mesh['object_id'], 'instance_id': mesh['instance_id'],
                          'face_comparison': same_surface(name, evaluated, reference), 'max_world_error_m': max(deviations)}
    return by_name, {'passed': True, 'asset_copy': str(asset), 'asset_sha256': asset_sha, 'source': source,
                     'receipt_sha256': receipt['sha256'], 'mesh_count': len(by_name), 'meshes': readings,
                     'current_slots_identified': True, 'ordinary_source_ref': receipt.get('ordinary_source_ref')}


def verify_answer_seal(row, slot):
    result_path = slot / 'SLOT_RESULT.json'
    result = read(result_path)
    require(row['slot'] == result['slot'] == slot.name and row['status'] == result['status']
            and row['slot_result_sha256'] == sha(result_path.read_bytes()), 'answer status not anchored to published slot')
    if row['sha256'] is None:
        require(row['path'] is None and row['original_path'] is None and not result.get('answer'), 'missing-answer seal has a final')
        return None
    original = Path(row['original_path']).resolve()
    require(original == (slot / 'consumer/PUBLIC_FINAL.txt').resolve(), 'unexpected original final path')
    copied = Path(row['path']).read_bytes()
    require(len(copied) == row['bytes'] and sha(copied) == row['sha256'] and original.read_bytes() == copied,
            'answer seal bytes differ from the original')
    return row['sha256']


def check_packet(row, slot, runtime_source, meshes, extension):
    if row.get('path') is None:
        return {'passed': False, 'status': row['status'], 'reason': 'no_sealed_first_packet'}
    raw = Path(row['path']).read_bytes()
    require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'first packet seal hash mismatch')
    product_response = Path(row['original_product_response_path']).resolve()
    require(product_response.is_relative_to(slot) and sha(product_response.read_bytes()) == row['original_product_response_sha256'],
            'first packet product receipt mismatch')
    receipt = read(slot / 'owner/tool_01/PRODUCT_RECEIPT.json')
    request = read(Path(receipt['request_path']))
    require(receipt['receipt'] == row['original_rpc_receipt'], 'first packet RPC receipt mismatch')
    index = receipt['receipt']['index']
    stdio = (slot / 'mcp' / f'rpc_{index:02d}' / 'RX.bin').read_bytes()
    require(sha(stdio) == receipt['receipt']['RX_sha256'] and len(stdio) == receipt['receipt']['RX_bytes']
            and json.loads(stdio) == read(product_response), 'first installed stdio original mismatch')
    result = json.loads(stdio)['result']
    owner_path = slot / 'owner/tool_01/RESPONSE.json'
    require(sha(owner_path.read_bytes()) == row['owner_response_sha256'] and read(owner_path)['result'] == result,
            'first packet differs from exact owner return')
    require(not result['isError'] and [block['type'] for block in result['content']] == ['text']
            and result['content'][0]['text'].encode('utf-8') == raw, 'sealed first packet differs from live installed result')
    params = request['params']
    args, query = params['arguments'], params['arguments']['query']
    require(params['name'] == 'human_eye_scene_observe' and request['method'] == 'tools/call'
            and args['include_image'] is False and args['response_detail'] == 'brief'
            and query == {'mode': 'task', 'target': {'name': NAMES[0]}, 'candidates': [{'name': n} for n in NAMES[1:]],
                          'requested_facts': ['closed_solid_relation', 'surface_proximity']}, 'original first request differs from common entry')
    wire = read(slot / 'native/WIRE/001/RESPONSE.bin')
    host = json.loads(wire['result']['result'].removeprefix('HUMAN_EYE_BLENDER_MCP:'))['result']
    require(wire['status'] == 'success' and wire['result']['executed'] and host['schema'] == 'human-eye-scene-delta-v1',
            'live host transport capture mismatch')
    capture, body = host['capture'], json.loads(raw)
    binding, operands, pairs, _ = fixed.view(body)
    producer = receipt['producer_archive']
    service_path, context_path = (Path(producer[key]).resolve() for key in ('path', 'read_context'))
    require(service_path.parent == context_path.parent == slot / 'product_full/call_001'
            and sha(service_path.read_bytes()) == producer['sha256'] and producer['new_observations_for_archive'] == 0,
            'first packet producer archive does not bind the original observation')
    service = read(service_path)
    selections = read(context_path)['after']['selections']
    states = [s for s in selections if s['fingerprint'] == binding['scene_fingerprint']]
    require(binding == service['binding'] and len(states) == 1 and states[0]['normalized']
            and body['status'] == 'observed' and binding['runtime_source_sha256'] == runtime_source
            and binding['scene_revision'] == capture['revision'] and binding['source'] == capture['source'] == 'blender'
            and binding['selected_count'] == 4 and binding['candidate_count'] == 28
            and binding['host_identity'] == capture['host_identity'] and binding['capture_scope'] == 'selected_objects'
            and [o['name'] for o in operands] == list(NAMES) and operands == capture['task_selection']['bindings'],
            'first packet is not the exact loaded current selection')
    resources = {resource['id']: resource for resource in host['resources']}
    current = {}
    for entry in capture['meshes']:
        name, oid, ref = entry['name'], entry['object_id'], entry['_scene_resource']
        live, terminal_mesh = resources[ref['id']], meshes[name]
        evaluated = terminal_mesh['evaluated']
        require(live['revision'] == ref['revision'] and ref['scale'] == 1.0 and ref['matrix'] == terminal_mesh['matrix_world']
                and live['vertices_local'] == evaluated['vertices'] and live['faces'] == evaluated['triangles']
                and oid == terminal_mesh['object_id'] and binding['host_identity']['object_instances'][oid] == terminal_mesh['instance_id'],
                'producer capture differs from owned terminal mesh/' + name)
        current[oid] = {'name': name, 'vertices': evaluated['vertices_world_m'], 'faces': evaluated['triangles']}
    require({m['name'] for m in current.values()} == set(NAMES), 'current capture did not include all four operands')
    supports = {}
    for pair in pairs:
        relation = pair['facts']['closed_solid_relation']
        if relation.get('certificate') == 'transverse_boundary_interiors':
            supports[pair['candidate_index']] = fixed.crossing_fact(relation['local_evidence'],
                 (current[operands[0]['object_id']], current[pair['object_id']]))
    extra = fixed.check_extensions(body, current, supports, extension)
    return {'passed': True, 'path': row['path'], 'sha256': row['sha256'], 'bytes': row['bytes'],
            'runtime_source_sha256': runtime_source, 'binding': binding, 'capture_evidence': extra,
            'verified_crossing_supports': supports, 'source_scope': 'bound same capture verified against independent terminal readback'}


def inspect(runtime, seals, frozen):
    answers, packets = read(seals / 'ANSWERS_SEALED.json'), read(seals / 'FIRST_PACKETS_SEALED.json')
    require(answers['replacement_consumers'] == 0 and tuple(r['slot'] for r in answers['answers']) == ARMS
            and tuple(r['slot'] for r in packets['first_packets']) == ARMS, 'original paired denominator changed')
    slots = {}
    for i, label in enumerate(ARMS):
        slot = (runtime / 'slots' / label).resolve()
        arm = slots[label] = {'sealed_answer_sha256': verify_answer_seal(answers['answers'][i], slot)}
        try:
            meshes, arm['terminal'] = terminal(slot, frozen)
        except (OSError, ValueError, KeyError, TypeError) as error:
            arm['terminal'] = {'passed': False, 'reason': str(error)}
            continue
        try:
            arm['first_packet'] = check_packet(packets['first_packets'][i], slot, PRODUCTS[i], meshes, i == 1)
        except (OSError, ValueError, KeyError, TypeError) as error:
            arm['first_packet'] = {'passed': False, 'reason': str(error)}
    a, b = (slots[label]['terminal'] for label in ARMS)
    pair = all(row['passed'] for row in (a, b)) and a['source']['pid'] != b['source']['pid'] \
        and not os.path.samefile(a['asset_copy'], b['asset_copy']) \
        and all(a['source'][key] == b['source'][key] for key in ('frame', 'subframe', 'view_layer', 'scene', 'scale_length'))
    return {'slots': slots, 'distinct_owned_copies_and_same_fixed_geometry': pair,
            'independent_truth': expected(), 'denominator_per_slot': len(GATES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--seals', type=Path, default=HERE.parent)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    if options.runtime:
        result = inspect(options.runtime, options.seals, fixed.fixed_inputs()['second_assembly']['meshes'])
    else:
        result = expected()
    with options.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
