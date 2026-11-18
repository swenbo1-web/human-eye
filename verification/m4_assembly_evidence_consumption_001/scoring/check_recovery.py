"""Check later installed facts without replacing the failed first business attempts."""

import argparse
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify import ARMS, NAMES, PRODUCTS, fixed, read, require, sha


def recover(row, slot, product, expected_extension, case):
    missed = read(slot / 'owner/tool_01/REQUEST.json')['params']['arguments']
    require('spatial_relation' in missed['query']['requested_facts'] and row['owner_tool'] == 'tool_02',
            'recovery does not match original failed first-attempt record')
    owner = slot / 'owner' / row['owner_tool']
    receipt = read(owner / 'PRODUCT_RECEIPT.json')
    require(receipt == row['original_rpc_receipt'], 'recovery receipt differs from sealed wrapper')
    wire = receipt['receipt']
    wire_response = (slot / 'mcp' / f"rpc_{wire['index']:02d}" / 'RX.bin').read_bytes()
    require(len(wire_response) == wire['RX_bytes'] and sha(wire_response) == wire['RX_sha256'], 'recovery stdio changed')
    packet = Path(row['path']).read_bytes()
    installed = Path(row['original_product_response_path']).read_bytes()
    owner_bytes = (owner / 'RESPONSE.json').read_bytes()
    result = json.loads(installed)['result']
    require(len(packet) == row['bytes'] and sha(packet) == row['sha256']
            and sha(installed) == row['original_product_response_sha256'] and sha(owner_bytes) == row['owner_response_sha256']
            and json.loads(installed) == json.loads(wire_response) and result == json.loads(owner_bytes)['result']
            and result['content'] == [{'type': 'text', 'text': packet.decode('utf-8')}] and not result['isError'],
            'recovered packet is not exact owner and installed output')
    arguments = read(owner / 'PRODUCT_REQUEST.json')['params']['arguments']
    require(arguments['include_image'] is False and arguments['response_detail'] == 'brief'
            and arguments['query']['requested_facts'] == ['closed_solid_relation', 'surface_proximity'], 'recovery scope changed')
    body = json.loads(packet)
    binding, operands, pairs, nearest = fixed.view(body)
    terminal = read(slot / 'TERMINAL_SOURCE.json')
    producer_wire = read(slot / 'native/WIRE/001/RESPONSE.bin')
    payload = json.loads(producer_wire['result']['result'].removeprefix('HUMAN_EYE_BLENDER_MCP:'))['result']
    capture = payload['capture']
    producer = receipt['producer_archive']
    archived = Path(producer['path']).read_bytes()
    context = read(Path(producer['read_context']))['after']
    require(sha(archived) == producer['sha256'] and json.loads(archived)['binding'] == binding
            and binding['runtime_source_sha256'] == product and binding['host_identity'] == capture['host_identity']
            and binding['scene_revision'] == capture['revision']
            and any(s['fingerprint'] == binding['scene_fingerprint'] and s['normalized'] for s in context['selections'])
            and [v['name'] for v in operands] == list(NAMES) and operands == capture['task_selection']['bindings'],
            'recovered product binding differs from selected live producer')
    current = {m['name']: m for m in terminal['objects']}
    resources = {r['id']: r for r in payload['resources']}
    meshes = {}
    for m in capture['meshes']:
        name, oid, ref = m['name'], m['object_id'], m['_scene_resource']
        saved, resource = current[name], resources[ref['id']]
        evaluated = saved['evaluated']
        require(oid == saved['object_id'] and binding['host_identity']['object_instances'][oid] == saved['instance_id']
                and ref['revision'] == resource['revision'] and ref['matrix'] == saved['matrix_world'] and ref['scale'] == 1.0
                and resource['vertices_local'] == evaluated['vertices'] and resource['faces'] == evaluated['triangles'],
                'later recovered capture differs from terminal mesh/' + name)
        meshes[oid] = {'name': name, 'vertices': evaluated['vertices_world_m'], 'faces': evaluated['triangles']}
    require({m['name'] for m in meshes.values()} == set(NAMES), 'recovery missing operands')
    target = meshes[operands[0]['object_id']]
    supports, facts = {}, {}
    for pair in pairs:
        candidate = meshes[pair['object_id']]
        name = candidate['name']
        closure = pair['facts']['closed_solid_relation']
        expected = case['outcomes'][name]
        require(closure['value'] == expected['relation'] and closure['relation_tolerance_m'] == 0.0,
                'recovered relation fails independent truth/' + name)
        if expected['relation'] == 'penetrating':
            supports[pair['candidate_index']] = fixed.crossing_fact(closure['local_evidence'], (target, candidate))
        else:
            distance = pair['separation_gap']['value']
            proximity = pair['facts']['surface_proximity']['value']
            witness = proximity['nearest_witness']
            a, b = map(fixed.point, (witness['a'], witness['b']))
            require(abs(distance - expected['minimum_gap_m']) <= 1e-9 and distance == proximity['distance_m']
                    and max(float(fixed.mesh_surface_error(a, target)), float(fixed.mesh_surface_error(b, candidate))) <= 1e-18
                    and abs(float(fixed.distance_squared(a, b)) ** .5 - distance) <= 1e-9,
                    'later recovered separated evidence differs/' + name)
        facts[name] = expected['relation']
    require(nearest[0] and nearest[1] == [next(o['object_id'] for o in operands if o['name'] == case['nearest'])],
            'later recovered ranking differs')
    extension = fixed.check_extensions(body, meshes, supports, expected_extension)
    return {'verified': True, 'scope': 'later recovered installed response; first gate remains failed',
            'tool': row['owner_tool'], 'body_sha256': row['sha256'], 'body_bytes': row['bytes'],
            'source_sha256': product, 'scene_fingerprint': binding['scene_fingerprint'],
            'scene_revision': binding['scene_revision'], 'facts': facts, 'extension': extension, 'crossings': supports,
            'first_attempt_facts': missed['query']['requested_facts']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    case = fixed.fixed_inputs()['second_assembly']
    sealed = read(HERE.parent / 'FIRST_PACKETS_SEALED.json')['first_packets']
    verdict = {}
    for index, arm in enumerate(ARMS):
        require(sealed[index]['slot'] == arm, 'recovery slot mismatch')
        verdict[arm] = recover(sealed[index], args.runtime / 'slots' / arm, PRODUCTS[index], index == 1, case)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(verdict, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
