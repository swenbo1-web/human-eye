"""Supplement the frozen P3 audit for its real task-query-set-v2 reply."""

import ast
from fractions import Fraction
import json
from math import isclose
from pathlib import Path
import re
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
REVIEW = run_path(str(HERE / 'review.py'))
read, pin, require = (REVIEW[key] for key in ('read', 'pin', 'require'))
SLOT = REVIEW['RUN'] / 'slots/P3'
PILOT = REVIEW['OLD']['PILOT']
DECODER = HERE.parents[1] / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
MEMBERSHIP = HERE.parents[1] / 'm5_observe_measure_001/oracle.py'


def review():
    install = REVIEW['fixed_install']()
    costs_path = HERE.parent / 'consumer/COSTS.json'
    arm, = (row for row in read(costs_path)['slots'] if row['label'] == 'P3')
    attempt, = (row for row in arm['actual_requests'] if row['attempt'] == 5)
    require(attempt['CLI_binding'] == 'content_and_envelope_match', 'actual_fifth_CLI_result_unbound')
    owner = SLOT / 'owner/tool_05'
    product, product_tx = owner / 'PRODUCT_RESPONSE.json', owner / 'PRODUCT_REQUEST.json'
    response, req = read(product), read(product_tx)
    args = req['params']['arguments']
    query = {'mode': 'task', 'target': {'name': 'N15'}, 'candidates': [{'name': 'N23'}],
             'requested_facts': ['surface_proximity', 'spatial_relation']}
    require(args == {'include_image': False, 'query': query, 'response_detail': 'brief'} == attempt['arguments'],
            'actual_fifth_tool_call_not_registered_whole_target_request')
    pub = REVIEW['OLD']['response_body'](response['result'])
    producer_path = Path(attempt['product']['producer_archive']['path'])
    require(producer_path.is_relative_to(SLOT) and
            pin(producer_path)['sha256'] == attempt['product']['producer_archive']['sha256'] and
            read(producer_path) == pub, 'actual_whole_result_not_the_original_producer')
    owner_rx = owner / 'RESPONSE.json'
    cli_rx = Path(attempt['stdio_RX']['path'])
    require(cli_rx.is_relative_to(SLOT) and cli_rx.read_bytes() == owner_rx.read_bytes() and
            pin(cli_rx)['sha256'] == attempt['stdio_RX']['sha256'] and
            read(cli_rx)['result'] == response['result'], 'actual_consumer_whole_result_wire_changed')
    stdout = SLOT / 'consumer/stdout.raw.bin'
    items = [row['item'] for row in REVIEW['lines'](stdout)
             if row.get('type') == 'item.completed' and row.get('item', {}).get('type') == 'mcp_tool_call'
             and row['item'].get('arguments') == args]
    cli_item, = items
    require(cli_item['result']['content'] == response['result']['content'], 'raw_CLI_did_not_receive_whole_evidence')
    stdio = SLOT / 'mcp' / f"rpc_{read(owner / 'PRODUCT_RECEIPT.json')['receipt']['index']:02d}"
    require(read(stdio / 'TX.bin') == req and read(stdio / 'RX.bin')['result'] == response['result'],
            'actual_public_product_wire_did_not_carry_whole_result')
    outer, = [path for path in (SLOT / 'owner').glob('rpc_*/TCP_TX.bin')
              if read(path)['args'].get('attempt') == 5]
    outer_rx = outer.with_name('TCP_RX.bin')
    require(read(outer)['args']['message']['params']['arguments'] == args and
            read(outer_rx)['result'] == read(owner_rx), 'outer_attempt_five_not_same_whole_evidence')

    binding = pub['binding']
    packed = binding['objects']
    target, reference = packed
    pair, = pub['pairs']
    require((pub['result_kind'], pub['schema_version'], pub['scope'], pub['pair_order'], pub['unit'],
             pub['coordinate_frame'], pub['relation_fact']) == (
                'task_query', 'task-query-set-v2', 'explicit_target_candidates', 'target_to_candidate',
                'm', 'world', 'spatial_relation') and
            [target['name'], reference['name']] == ['N15', 'N23'] and
            pair['object_id'] == reference['object_id'] and pair['candidate_index'] == 0 and
            binding['capture_scope'] == 'selected_objects' and binding['selected_count'] == 2
            and binding['runtime_source_sha256'] == REVIEW['SOURCE'], 'whole_product_result_scope_changed')

    sys.path.insert(0, install['dependency_root'])
    decode = run_path(str(DECODER))
    audit = decode['Audit']()
    captures, commands = decode['decode_captures'](SLOT, install, audit)
    command, = (row for row in commands if row['command']['command'] == 'capture_task')
    selectors = [{'name': 'N15'}, {'name': 'N23'}]
    require(command['command']['params']['selectors'] == selectors, 'current_native_whole_selectors_changed')
    current, = (capture for capture in captures
                if capture['revision'] == binding['scene_revision'] and capture['capture_scope'] == 'selected_objects')
    parent, = (capture for capture in captures if capture.get('capture_scope', 'complete_scene_meshes') ==
               'complete_scene_meshes')
    native = SLOT / 'native/WIRE' / f"{command['wire_sequence']:03d}"
    native_stdout = read(native / 'RESPONSE.bin')['result']['result']
    native_packet, = (json.loads(line.split(':', 1)[1]) for line in native_stdout.splitlines()
                      if line.startswith('HUMAN_EYE_BLENDER_MCP:'))
    embedded = re.search(r'_request = _json.loads\((.+)\)\n', read(native / 'REQUEST.bin')['params']['code'])
    native_request = json.loads(ast.literal_eval(embedded.group(1)))
    require(native_request == command['command'] and native_packet['id'] == native_request['id'] and
            current['host_identity'] == binding['host_identity'] and
            all(current['capture_state'][key] == parent['capture_state'][key]
                for key in ('instance_id', 'epoch', 'revision')) and
            current['host_identity']['document_epoch'] == parent['host_identity']['document_epoch'],
            'current_selected_capture_not_same_generation_and_document')
    terminal_path = SLOT / 'TERMINAL_SOURCE.json'
    terminal = {row['name']: row for row in read(terminal_path)['objects']}
    native_by_name = {mesh['name']: mesh for mesh in parent['meshes']}
    source_rows = []
    meshes = []
    require([mesh['name'] for mesh in current['meshes']] == ['N15', 'N23'], 'actual_mesh_pair_order_changed')
    for pack, mesh in zip(packed, current['meshes'], strict=True):
        name = pack['name']
        orig = terminal[name]
        parent_mesh = native_by_name[name]
        geom = orig['evaluated']
        require(mesh['name'] == orig['name'] and mesh['object_id'] == parent_mesh['object_id'] ==
                orig['object_id'] == pack['object_id'] and
                current['host_identity']['object_instances'][mesh['object_id']] == orig['instance_id'] and
                mesh['vertices'] == parent_mesh['vertices'] == geom['vertices_world_m'] and
                mesh['faces'] == parent_mesh['faces'] == geom['triangles'],
                'whole_object_source_geometry_not_bound_to_current_full_capture/' + name)
        meshes.append({'name': name, 'vertices': [tuple(map(Fraction, p)) for p in mesh['vertices']],
                       'triangles': mesh['faces']})
        source_rows.append({'name': name, 'object_id': mesh['object_id'], 'instance_id': orig['instance_id'],
                            'ordered_source_triangle_range': [0, len(mesh['faces']) - 1],
                            'vertices': len(mesh['vertices'])})
    require([row['ordered_source_triangle_range'] for row in source_rows] == [[0, 31], [0, 11]],
            'whole_object_coverage_not_complete')
    oracle_path = PILOT / 'truth/oracle.py'
    truth = run_path(str(oracle_path))['independent_measurement'](meshes)
    fact = pair['facts']['surface_proximity']
    value = fact['value']
    witness = value['nearest_witness']

    def close(a, b):
        return isclose(a, b, rel_tol=0, abs_tol=1e-14)

    points = [tuple(map(Fraction, witness[end])) for end in ('a', 'b')]
    delta = [b - a for a, b in zip(*points, strict=True)]
    membership = run_path(str(MEMBERSHIP))['membership']
    checks = [membership(point, mesh['vertices'], mesh['triangles'])
              for point, mesh in zip(points, meshes, strict=True)]
    require(fact['status'] == 'measured' and
            pair['facts']['spatial_relation']['value'] == 'separated' and
            close(value['distance_m'], truth['distance_m']) and
            all(bool(check['within_publication_tolerance_source_triangle_indices']) for check in checks) and
            all(close(a, b) for a, b in zip(delta, map(Fraction, truth['displacement_exact_m']), strict=True)) and
            all(close(a, b) for a, b in zip(witness['direction_a_to_b'], truth['direction_a_to_b_world'], strict=True)),
            'whole_measurement_and_independent_true_source_result_differ')
    pins = [Path(__file__), costs_path, product, product_tx, producer_path, owner_rx, cli_rx, stdout, outer, outer_rx,
            stdio / 'TX.bin', stdio / 'RX.bin', SLOT / 'native/WIRE/005/REQUEST.bin',
            SLOT / 'native/WIRE/005/RESPONSE.bin', native / 'REQUEST.bin', native / 'RESPONSE.bin', terminal_path,
            DECODER, MEMBERSHIP, oracle_path]
    return {'passed': True, 'scope': 'whole_objects', 'actual_attempt': 5, 'schema_version': pub['schema_version'],
            'frozen_review_limitation': 'historical generic parser recognizes task-query-set-v1, not this task-query-set-v2 relation shape',
            'actual_query': query, 'raw_cli_item': cli_item['id'], 'source_rows': source_rows,
            'current_capture_state': current['capture_state'], 'current_document_epoch': binding['host_identity']['document_epoch'],
            'surface_proximity': fact, 'nearest_witness_membership': checks, 'independent_same_current_mesh_truth': truth,
            'source_pins': [pin(path) for path in pins]}


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_isolated_interpreter_required')
    path = HERE / 'WHOLE_SCOPE.json'
    value = review()
    with path.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write('\n')
    print(path, pin(path)['sha256'])
