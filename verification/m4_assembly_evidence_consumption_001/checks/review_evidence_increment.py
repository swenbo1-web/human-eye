"""Bind a paired public tool increment review to sealed original records."""

import argparse
import ast
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re


NS = Path(__file__).resolve().parents[1]
RUNTIME = Path('D:/he_m4_assembly_evidence_consumption_001')
NAMES = ('N16', 'N13', 'N08', 'N28')
LABELS = ('A1', 'B1')
SUPPORT_LINE = re.compile(r'^(N16|N13) triangle (\d+)(?: polygon (\d+))? vertices (.*?) barycentric (\[[^\]]+\]) (.*)$')
POINT_LINE = re.compile(r'^(?:crossing point exact binary64 coordinates:|crossing_world) (\[[^\]]+\])$')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def original(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def read(path):
    return json.loads(path.read_bytes())


def exact_weights(triangle, point, axes):
    corners = [list(map(Fraction, row)) for row in triangle]
    probe = list(map(Fraction, point))
    a, b = axes
    u, v = [[corners[i][k] - corners[0][k] for k in range(3)] for i in (1, 2)]
    w = [probe[k] - corners[0][k] for k in range(3)]
    denominator = u[a] * v[b] - u[b] * v[a]
    beta = (w[a] * v[b] - w[b] * v[a]) / denominator
    gamma = (u[a] * w[b] - u[b] * w[a]) / denominator
    weights = [1 - beta - gamma, beta, gamma]
    require(all(x > 0 for x in weights) and
            [sum(weight * row[k] for weight, row in zip(weights, corners, strict=True))
             for k in range(3)] == probe, 'support point is not in the exact interiors')
    return list(map(float, weights))


def tool_records(slot):
    binding_path = slot / 'consumer/BUSINESS_SOURCE_BINDING.json'
    binding = read(binding_path)
    checks = {row['attempt']: row for row in binding['result_contracts']}
    require(list(checks) == [1, 2, 3, 4] and binding['binding_errors'] == [
        {'reason': 'first_business_attempt_not_registered_brief_assembly_query'}], 'unexpected first gate or attempt set')
    result = []
    for number, check in checks.items():
        folder = slot / 'owner' / f'tool_{number:02d}'
        request_path, reply_path = folder / 'REQUEST.json', folder / 'RESPONSE.json'
        request, reply = read(request_path), read(reply_path)
        rx, = [item for item in (slot / 'consumer/attachments').glob('bridge_*/*/RX.bin')
               if read(item.with_name('RECEIPT.json')).get('attempt') == number]
        tx = rx.with_name('TX.bin')
        require(check['matched'] and check['reason'] == 'content_and_envelope_match'
                and original(tx)['sha256'] == check['TX_sha256'] and original(rx)['sha256'] == check['RX_sha256']
                and read(tx) == request and read(rx) == reply and request['id'] == reply['id'], 'unbound public tool result')
        text, = [row['text'] for row in reply['result']['content'] if row['type'] == 'text']
        size = len(text.encode())
        require(size == check['source_text_UTF8_bytes'] == check['CLI_text_UTF8_bytes'] and check['CLI_images'] == 0,
                'tool evidence is clipped or contains images')
        result.append({'attempt': number, 'tool': request['params']['name'], 'request': original(request_path),
                       'response': original(reply_path), 'wire': {'request': original(tx), 'response': original(rx)},
                       'body_utf8_bytes': size, 'tool_error': reply['result']['isError'],
                       'arguments': request['params']['arguments'], 'text': text})
    return original(binding_path), result


def geometry_support(post, local, source):
    output = json.loads(post['text'])
    require(output['error'] is None and not output['stderr'], 'support computation failed')
    lines = output['stdout'].splitlines()
    point, = [ast.literal_eval(found[1]) for line in lines if (found := POINT_LINE.fullmatch(line))]
    require(point == local['point_world_m'], 'numeric corroboration did not reuse first point')
    support = []
    for line in lines:
        match = SUPPORT_LINE.fullmatch(line)
        if not match:
            continue
        name, index, polygon, vertices, barycentric, remainder = match.groups()
        index = int(index)
        mesh = source[name]
        ids = mesh['triangles'][index]
        vertices = ast.literal_eval(vertices)
        expected = local['triangle_vertices_world_m'][len(support)]
        weights = ast.literal_eval(barycentric)
        require(vertices == [mesh['vertices'][i] for i in ids] == expected
                and index == local['triangle_indices'][len(support)]
                and weights == exact_weights(vertices, point, (1, 2) if name == 'N16' else (0, 1)), 'crossing support changed')
        if polygon is not None:
            require(int(polygon) == mesh['triangle_polygons'][index], 'native polygon mismatch')
        support.append({'name': name, 'triangle_index': index, 'capture_vertex_indices': ids,
                        'native_polygon_index_printed': None if polygon is None else int(polygon),
                        'first_packet_coordinates_repeated_exactly': True, 'exact_barycentric_weights': weights,
                        'reported_numeric_detail': remainder})
    require([row['name'] for row in support] == ['N16', 'N13'], 'support triangles missing from public reply')
    return {'crossing_point_world_m': point, 'triangles': support, 'local_response_introduces_new_relation_or_gap': False}


def review_slot(label, seal):
    slot = RUNTIME / 'slots' / label
    binding, (initial, corrected, readback, computation) = tool_records(slot)
    first_request = initial['arguments']
    expected_request = {'query': {'mode': 'task', **read(NS / 'inputs/ASSEMBLY.json')},
                        'response_detail': 'brief', 'include_image': False}
    require(first_request == {**expected_request, 'response_detail': 'full',
            'query': {**expected_request['query'], 'requested_facts': ['closed_solid_relation', 'surface_proximity', 'spatial_relation']}}
            and initial['tool_error'] and 'first_call_requires_the_registered_brief_assembly_task_query' in initial['text']
            and not (slot / 'owner/tool_01/PRODUCT_REQUEST.json').exists(), 'first rejected request mismatch')
    packet = Path(seal['path'])
    producer = read(slot / 'product_calls/call_001/REQUEST.json')
    require(producer['params']['arguments'] == corrected['arguments'] == expected_request
            and not corrected['tool_error'] and seal['owner_tool'] == 'tool_02'
            and seal['sha256'] == original(packet)['sha256']
            and packet.read_bytes() == corrected['text'].encode(), 'sealed recovery packet not original')
    body = read(packet)
    local = body['pairs'][0]['facts']['closed_solid_relation']['local_evidence']
    raw_path = slot / 'raw_sources/live-source-001.json'
    raw = read(raw_path)
    source = {row['name']: row for row in raw['objects']}
    terminal = read(slot / 'TERMINAL_SOURCE.json')
    terminal_meshes = {row['name']: row for row in terminal['objects']}
    device_path = slot / 'DEVICE_EVIDENCE.json'
    device = read(device_path)
    capture, = [row for row in device['sources'] if not row['terminal']]
    native_path = slot / 'NATIVE_CALLS.jsonl'
    native, = [row for line in native_path.read_bytes().splitlines() if not (row := json.loads(line))['terminal']]
    require(capture['source_ref'] == 'live-source-001' and capture['sha256'] == original(raw_path)['sha256']
            and len(source) == len(terminal_meshes) == 28 and terminal['source'] == raw['source']
            and all(terminal_meshes[name]['mesh_sha256'] == row['mesh_sha256'] for name, row in source.items())
            and not readback['tool_error'] and 'scene_data([' in readback['arguments']['code']
            and all(source[name]['mesh_sha256'] in readback['text'] for name in NAMES)
            and 'scene_data(' not in computation['arguments']['code'] and not computation['tool_error']
            and read(slot / 'owner/tool_03/RECEIPT.json')['started_ns'] <= native['started_ns'] <= native['closed_ns']
            < read(slot / 'owner/tool_03/RECEIPT.json')['closed_ns'], 'host read or cache reuse cannot be bound')
    numeric = geometry_support(computation, local, source)
    numeric.update(independent_native_capture_tool=3, additional_native_reads=0,
                   source_ref=capture['source_ref'])
    zero_media = not device['frames'] and read(slot / 'SLOT_RESULT.json')['budget']['counts']['all_raster_upper'] == 0
    require(zero_media, 'unexpected frame or raster activity')
    summary = {'slot': label, 'wire_binding': binding, 'formal_first_business_attempt_compliant': False,
               'first_request': first_request, 'first_failure_forwarded_to_product': False,
               'recovered_first_installed_packet': {'attempt': 2, 'original': original(packet),
                    'capture_evidence_delivered': 'capture_evidence' in body, 'crossing': local,
                    'first_packet_fact_summary': body['summary']},
               'independent_host_read': {'attempt': 3, 'source_ref': capture['source_ref'], 'source': raw['source'],
                   'source_original': original(raw_path), 'evidence_original': original(device_path),
                   'native_request_log': original(native_path), 'native_capture_count': 1,
                   'native_captured_objects': len(source), 'native_captured_evaluated_counts': capture['evaluated_counts'],
                   'selected_objects': list(NAMES), 'selected_mesh_sha256': {name: source[name]['mesh_sha256'] for name in NAMES},
                   'geometry_reconfirmed_against_terminal': True},
               'local_numeric_corroboration': {'attempt': 4, **numeric},
               'attempts': [{k: v for k, v in row.items() if k not in ('text', 'arguments')} for row in (initial, corrected, readback, computation)],
               'image_blocks': 0, 'raster_attempts': 0}
    return summary


def run(answer_review, quality_path):
    proofs = read(NS / 'FIRST_PACKETS_SEALED.json')['first_packets']
    finals = read(NS / 'ANSWERS_SEALED.json')['answers']
    require([s['slot'] for s in proofs] == [s['slot'] for s in finals] == list(LABELS), 'original denominator changed')
    slots = [review_slot(label, seal) for label, seal in zip(LABELS, proofs, strict=True)]
    for output, answer in zip(slots, finals, strict=True):
        review = answer_review[output['slot']]
        require(review['answer_sha256'] == answer['sha256'] == original(Path(answer['path']))['sha256'],
                'adoption review belongs to a different answer')
        output['answer_adoption'] = review
    return {'schema': 'm4-assembly-evidence-consumption-increment-v1', 'slots': slots,
            'scorer_receipt': original(quality_path), 'decrease_in_related_followups_observed': False,
            'formal_pair_eligible': False,
            'scope': 'Closed original MCP public evidence and human review of sealed answer adoption. No private reasoning events or new requests.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--answer-review', type=Path, required=True)
    parser.add_argument('--quality', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(read(args.answer_review), args.quality)
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
