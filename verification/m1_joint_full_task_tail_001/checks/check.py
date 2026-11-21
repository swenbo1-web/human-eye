"""Replay two actual archived target/full joint replies on isolated installed products."""

import argparse
import base64
from copy import deepcopy
from functools import lru_cache
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
from runpy import run_path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
BASE = 'm1_pair_distance_entry_001/install/PRODUCT_RUN_BINDING.json'
BASE_SOURCE = '0e85052a0a4dec4ee42f8f9f62729a416b57445783224b303723b515ada0a147'
CANDIDATE_SOURCE = '5da861b7'
ARCHIVES = 'perf050_target_observation_first_image_p2/harness/archives.py'
SERIALIZER = 'm1_source_region_final_image_001/checks/serializer.py'
BUDGET = 'm4_cross_scale_live_qualification_001/checks/delivery.py'
SPANS = 'm4_dense_panel_sweep_001/checks/qualify_product.py'
MEMBERSHIP = 'm5_observe_measure_001/oracle.py'
REGION_FIELDS = ('regions', 'observations', 'region_evidence')
ORIGINALS = {
    'Far00': {'run': 'perf050_dense_pair_transfer_001', 'label': 'P1', 'files': 340,
              'archive': 'caa5872d496c90eae77dd2a6fd2ac062200802bb184d086babc4924fd20b5477',
              'producer': '43958b61e20f30a458d767f9b42e837b358ad17d21dc2a120922d7578b8054b0',
              'names': ['M4_Far_00', 'M4_Focal'], 'body_bytes': 30121, 'terminal_object_count': 14,
              'distance_m': 1.0, 'direction': [-1., 0., 0.], 'witness_view': 'SCENE', 'image_count': 1},
    'M09': {'run': 'perf050_target_observation_first_image_p2', 'label': 'P2', 'files': 210,
            'archive': 'f675d00775e16397d1802339f9b994a44d39a5e34048dd678e3a952872e439ce',
            'producer': '23bc236dffc870a412bf1f62cc0bb0c1b2ea8afd39d9b65512126546c161a7ec',
            'names': ['M09', 'M03'], 'body_bytes': 28679, 'terminal_object_count': 21,
            'distance_m': .234375, 'direction': [0., 0., 1.], 'witness_view': 'LEFT', 'image_count': 2},
}
ORDERS = {
    'A_original': 'historic packet from actual closed slot',
    'A_replayed': 'baseline installed MCP serializer',
    'A_original_prepend': 'only task_result prepended inside original packet',
    'A_replayed_prepend': 'only task_result prepended inside baseline replay',
    'B_tail': 'candidate installed MCP serializer',
}
TRUNCATED = re.compile(r'…\d+ (?:chars|tokens) truncated…')
FIELD_PATHS = ('image_path', 'image_ref', 'image_sha256')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def read(path):
    return json.loads(Path(path).read_bytes())


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')


def emit(path, data):
    with path.open('xb') as out:
        out.write(data)
    return pin(path)


def mcp_bytes(packet):
    return (json.dumps(packet, ensure_ascii=False, allow_nan=False) + '\r\n').encode('utf8')


def images(reply):
    return [base64.b64decode(item['data'], validate=True)
            for item in reply['content'] if item['type'] == 'image' and item['mimeType'] == 'image/png']


def body(reply):
    require(reply['content'][0]['type'] == 'text' and not reply['isError'], 'registered_joint_not_successful')
    return json.loads(reply['content'][0]['text'])


def checks_for_joint(doc, reply):
    """Return exact required member addresses and the public image/witness graph."""
    facts = doc['facts']
    members = facts['observations']
    refs = [row['image_ref'] for row in members]
    frames = doc['frames']
    require(len(refs) == len(set(refs)) == len(frames) == len(images(reply)),
            'image_content_observation_frame_count_changed')
    require(refs == [frame['image_ref'] for frame in frames], 'old_frame_and_observation_order_changed')
    raw = images(reply)
    graph = []
    for i, (item, frame, png) in enumerate(zip(members, frames, raw, strict=True)):
        require(item['view_name'] == frame['view_name'] and
                all(item[name] == frame[name] for name in FIELD_PATHS)
                and digest(png) == frame['image_sha256'] and len(png) == frame['PNG_bytes'],
                'actual_frame_not_bound_to_native_PNG_or_observation')
        graph.append({'image_index': i, 'MCP_content_block_index': i+1, 'view': frame['view_name'],
                      'path': item['image_path'], 'ref': item['image_ref'], 'sha256': digest(png),
                      'image_bytes': len(png), 'frame_identity': frame['frame_identity']})
    by_view = {row['view_name']: row for row in members}
    by_roi = {row['roi_id']: row for row in facts['regions']}
    require(len(by_view) == len(members) and len(by_roi) == len(facts['regions']), 'ambiguous_region_or_view')
    selected, unknown = set(), []
    for item in facts['region_evidence']:
        roi = by_roi[item['roi_id']]
        witness = item['complete_witness']
        if witness is None:
            require(roi['status'] != 'covered' and item['unobserved_reason'], 'unknown_region_scope_changed')
            unknown.append({'roi': roi['roi_id'], 'status': roi['status'], 'reason': item['unobserved_reason']})
            continue
        obs = by_view[witness['view_name']]
        index = witness['pixel_row_index']
        require(type(index) is int and 0 <= index < len(obs['pixel_rows'])
                and obs['pixel_rows'][index]['roi_id'] == roi['roi_id']
                and obs['pixel_rows'][index]['readable'] is True
                and obs['pixel_rows'][index]['front_facing'] is True
                and roi['status'] == 'covered', 'complete_witness_is_not_bound_to_same_region_readable_pixels')
        selected.add(refs.index(obs['image_ref']))
    controls = [('task_result',), *[('facts', key) for key in REGION_FIELDS], *[('frames', i) for i in sorted(selected)]]
    return controls, graph, unknown, selected


def original(repo, key, pins):
    case = ORIGINALS[key]
    v = repo / 'verification'
    archive_module = run_path(str(v / ARCHIVES))
    root = Path('D:/he_' + case['run'])
    stem = 'slots/' + case['label']
    slot = root / stem
    index = v / case['run'] / 'RUNTIME_INDEX.json'
    with archive_module['Archive'](root, index, case['archive'], case['files']) as arc:
        result = arc.json(slot / 'SLOT_RESULT.json')
        pub = arc.json(slot / 'SLOT_PUBLICATION.json')
        initial = arc.json(slot / 'initial_capture/TERMINAL_SOURCE.json')
        close = arc.json(slot / 'TERMINAL_SOURCE.json')
        require(result['status'] == pub['status'] == 'completed' and result['model_consumers'] == 1
                and result['closure_verification']['passed'] and result['independent_before_after']['passed']
                and pub['result_sha256'] == pin(slot / 'SLOT_RESULT.json')['sha256']
                and initial['objects'] == close['objects']
                and len(close['objects']) == case['terminal_object_count'], 'wrong_closed_actual_original')
        outer_contract = arc.json(slot / 'consumer/BUSINESS_SOURCE_BINDING.json')['result_contracts']
        stdout = archive_module['rows'](arc.member(slot / 'consumer/stdout.raw.bin'))
        outer_tx, outer_rx, proof = archive_module['outer_packet'](arc, stem, 1, outer_contract, stdout)
        owner = arc.json(slot / 'owner/tool_01/PRODUCT_RECEIPT.json')
        public = slot / 'mcp' / f"rpc_{owner['receipt']['index']:02}"
        tx_path, rx_path = public / 'TX.bin', public / 'RX.bin'
        tx, rx = arc.json(tx_path), arc.json(rx_path)
        rx_wire = arc.member(rx_path)
        require(digest(rx_wire) == owner['receipt']['RX_sha256']
                and tx == arc.json(slot / 'product_calls/call_001/REQUEST.json')
                and rx == arc.json(slot / 'product_calls/call_001/RESPONSE.json')
                and rx['result'] == outer_rx['result']
                and tx['params'] == {k: outer_tx['params'][k] for k in ('name', 'arguments')},
                'first_call_live_inner_outer_and_CLI_wires_not_identical')
        record = owner['producer_archive']
        source = Path(record['path'])
        original_producer = arc.member(source)
        producer = json.loads(original_producer)
        expected_source = slot / 'product_full/call_001/SERVICE_RESULT.json'
        require(source == expected_source and digest(original_producer) == case['producer'] == record['sha256']
                and record['new_observations_for_archive'] == 0
                and producer['binding']['capture_scope'] == 'target_observation_meshes',
                'first_call_original_same_request_producer_unbound')
        objects = [{'name': name} for name in case['names']]
        require(tx['params']['arguments'] == {'include_image': True, 'response_detail': 'full',
                        'query': {'mode': 'active_observation', 'objects': objects[:1], 'task_query': {
                         'mode': 'task', 'objects': objects, 'requested_facts': ['surface_proximity']}}},
                'selected_joint_public_real_arguments_changed')
        doc = body(rx['result'])
        geometry = {x['name']: x for x in close['objects']}
        task = doc['task_result']
        task_binding = task['binding']
        provenance = task_binding['observation_source']
        value = task['facts']['surface_proximity']
        require(task == producer['task_result'] and task['schema_version'] == 'task-query-v3'
                and task['pair_order'] == 'A_to_B' and task['unit'] == 'm' and task['coordinate_frame'] == 'world'
                and task['status'] == 'observed' and task['execution_authority'] is False
                and [r['name'] for r in task_binding['objects']] == case['names']
                and provenance['measurement_scope'] == 'whole_objects'
                and provenance['parent_binding_sha256'] == doc['binding']['binding_sha256']
                and provenance['parent_source_binding_sha256'] == doc['binding']['source_binding_sha256']
                and provenance['capture_scope'] == 'observation_task_objects'
                and provenance['parent_capture_scope'] == 'target_observation_meshes'
                and all(provenance['capture_state'][k] == doc['binding']['capture_state'][k]
                        for k in ('instance_id','epoch','revision')),
                'actual_whole_source_parent_scope_changed')
        sources = {row['object_id']: row for row in provenance['objects']}
        require(len(sources) == len(provenance['objects']) == 2, 'source_object_entries_duplicated')
        for bound, name in zip(task_binding['objects'], case['names'], strict=True):
            geo = geometry[name]
            row = sources[bound['object_id']]
            vertices = geo['evaluated']['vertices_world_m']
            faces = geo['evaluated']['triangles']
            ordered = digest(json.dumps({'vertices': vertices, 'faces': faces}, sort_keys=True, separators=(',', ':'),
                ensure_ascii=True, allow_nan=False).encode('utf8'))
            parent = doc['binding']['objects'][row['observation_object_index']]
            require(row['object_id'] == bound['object_id'] == geo['object_id'] == parent['host_id']
                    and row['instance_id'] == geo['instance_id'] == parent['instance_id']
                    and row['source_triangle_count'] == len(faces) and
                    row['source_triangle_index_ranges'] == [[0, len(faces)-1]]
                    and row['ordered_geometry_sha256'] == ordered,
                    'joint_actual_source_not_the_whole_ordered_current_object')
        witness = value['value']['nearest_witness']
        points = [tuple(map(Fraction, witness[end])) for end in ('a', 'b')]
        delta = [b-a for a, b in zip(*points, strict=True)]
        membership_path = v / MEMBERSHIP
        point_membership = run_path(str(membership_path))['membership']
        witnesses = [point_membership(point, geometry[name]['evaluated']['vertices_world_m'],
                                      geometry[name]['evaluated']['triangles'])
                     for point, name in zip(points, case['names'], strict=True)]
        require(value['status'] == value['witness_status'] == value['direction_status'] == 'measured'
                and value['value']['distance_m'] == case['distance_m']
                and witness['direction_a_to_b'] == case['direction']
                and delta == [Fraction(case['distance_m'])*Fraction(component) for component in case['direction']]
                and all(w['exact_source_triangle_indices'] for w in witnesses),
                'actual_ordered_measurement_value_or_current_point_membership_changed')
        pins.append(pin(membership_path))
        required, graph, unknown, selected = checks_for_joint(doc, rx['result'])
        require([graph[i]['view'] for i in sorted(selected)] == [case['witness_view']]
                and len(graph) == case['image_count']
                and len(rx['result']['content'][0]['text'].encode()) == case['body_bytes'],
                'actual_joint_archive_sizes_or_witness_frame_changed')
        for frame, image in zip(producer['frames'], graph, strict=True):
            p = Path(frame['image_path'])
            png = arc.member(p)
            require(Path(image['path']) == p and p.resolve(strict=True) == p and p.is_relative_to(slot)
                    and image['ref'] == frame['image_ref'] and image['frame_identity'] == frame['frame_identity']
                    and digest(png) == frame['image_sha256'] == image['sha256'],
                    'original_disk_PNG_or_canonical_current_path_changed')
        standalone = None
        if key == 'Far00':
            followup = slot / 'product_calls/call_002'
            follow_tx, follow_rx = (arc.json(followup / f'{name}.json') for name in ('REQUEST','RESPONSE'))
            follow_producer = arc.json(slot / 'product_full/call_002/SERVICE_RESULT.json')
            follow_outer, follow_cli, follow_proof = archive_module['outer_packet'](arc, stem, 2, outer_contract, stdout)
            require(follow_rx['result'] == follow_cli['result'] and body(follow_rx['result']) == follow_producer
                    and follow_tx['params']['arguments'] == {'include_image': False, 'response_detail': 'brief',
                            'query': tx['params']['arguments']['query']['task_query']}
                    and {k: follow_outer['params'][k] for k in ('name','arguments')} == follow_tx['params']
                    and 'task_result' not in follow_producer and not images(follow_rx['result']),
                    'sealed_independent_second_measurement_request_or_reply_changed')
            standalone = {'request': follow_tx, 'reply': follow_rx, 'producer': follow_producer, 'wire': follow_proof}
        pins.extend(arc.pins.values())
    return {'slot': slot, 'request': tx, 'reply': rx, 'actual_inner_wire': rx_wire, 'producer': producer,
            'whole_witness_membership': witnesses, 'standalone': standalone,
            'source_hash': record['sha256'], 'outer_wire': proof, 'known_whole_result': task,
            'historical_full_body_bytes': case['body_bytes'], 'images': graph, 'historical_unknown': unknown}


def serialized(server, service, req, producer, state):
    fixture = service(producer, req['params']['arguments'], state)
    mcp = server(fixture, default_session_id=producer.get('session_id','archived-task-pair'))
    started = perf_counter_ns()
    reply = mcp.handle_jsonrpc_message(deepcopy(req))
    elapsed = perf_counter_ns() - started
    require(reply['id'] == req['id'] and reply['jsonrpc'] == '2.0' and fixture.observations == 1,
            'actual_joint_request_did_not_traverse_installed_MCP_handler')
    return reply, elapsed


def worker(repo, binding_path, output):
    binding = read(binding_path)
    require(len(binding['source_manifest']) == 143, 'registered_143_runtime_sources_changed')
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_sha256'] == binding['source_sha256']
            and identity['source_kind'] == 'installed_distribution'
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'replay_did_not_import_actual_bound_install')
    comp = run_path(str(repo / 'verification' / SERIALIZER))
    originals, pins = {}, []
    for key in ORIGINALS:
        data = original(repo, key, pins)
        archival = data['reply']
        state = data['slot'] / 'product_state.json'
        req, value = data['request'], data['producer']
        elapsed = []
        packet = None
        for _ in range(21):
            actual, span = serialized(mcp.LiveSpatialMCPServer, comp['SavedProducer'], req, value, state)
            require(packet is None or actual == packet, 'same_archival_actual_serializer_reply_is_not_stable')
            packet = actual
            elapsed.append(span)
        require(body(archival['result']) == body(packet['result'])
                and len(packet['result']['content'][0]['text'].encode()) == data['historical_full_body_bytes']
                and packet['result']['content'][1:] == archival['result']['content'][1:],
                'archived_and_replayed_wire_semantic_body_or_native_PNG_changed')
        probe = mcp.LiveSpatialMCPServer(comp['SavedProducer'](value, req['params']['arguments'], state),
                                        default_session_id=value['session_id'])
        listing = probe.handle_jsonrpc_message({'jsonrpc': '2.0', 'id':'tools', 'method':'tools/list'})
        require(len(listing['result']['tools']) == 5, 'actual_observe_tool_catalogue_changed')
        old_raw = emit(output / (key + '_HISTORIC_INNER_RX.bin'), data['actual_inner_wire'])
        now_raw = emit(output / (key + '_INSTALLED_REPLAY_RX.bin'), mcp_bytes(packet))
        standalone = None
        if data['standalone'] is not None:
            follow = data['standalone']

            class ArchivedPair(comp['SavedProducer']):
                def observe(self, session, **arguments):
                    self.observations += 1
                    require(self.observations == 1 and session == 'archived-task-pair'
                            and arguments['query'] == self.arguments['query']
                            and arguments['include_image'] is False,
                            'standalone_replay_host_did_not_receive_exact_text_only_request')
                    return deepcopy(self.producer)

            result, _ = serialized(mcp.LiveSpatialMCPServer, ArchivedPair, follow['request'],
                                   follow['producer'], state)
            require(body(result['result']) == follow['producer']
                    and result['result']['content'][1:] == [],
                    'standalone_second_measurement_changed_on_installed_serializer')
            standalone = {'original_caller': follow['wire'], 'reply': result,
                          'raw_MCP': emit(output / (key+'_STANDALONE_RX.bin'), mcp_bytes(result))}
        originals[key] = {'archived': archival, 'replayed': packet, 'historical_packet': old_raw,
                          'standalone': standalone, 'current_witness_membership': data['whole_witness_membership'],
                          'replayed_packet': now_raw, 'outer': data['outer_wire'], 'task_truth': data['known_whole_result'],
                          'whole_producer_sha256': data['source_hash'], 'original_images': data['images'],
                          'historical_unknown': data['historical_unknown'], 'catalogue': listing,
                          'serialized_elapsed_ns_median': median(elapsed), 'serializer_replay_trials': 21}
    collection = {'source_sha256': identity['source_sha256'], 'cases': originals,
                  'source_pins': list({row['path']: row for row in pins}.values())}
    sys.stdout.buffer.write(compact(collection))


def run_worker(repo, binding, output):
    output.mkdir()
    cmd = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--repo', str(repo),
           '--worker', str(binding), '--wire-dir', str(output)]
    return json.loads(subprocess.check_output(cmd, timeout=120))


@lru_cache(maxsize=2)
def cli_constants(repo):
    v = Path(repo) / 'verification'
    helper, policy = run_path(str(v / BUDGET))['budget_helpers']()
    spans = run_path(str(v / SPANS))['spans']
    require((policy['MCP_bytes'], policy['history_approximate_tokens']) == (12000, 3000),
            'fixed_cli_browser_surrogate_limits_changed')
    return helper, policy, spans


def selected_spans(overall, retained):
    if retained == overall:
        return None
    match = TRUNCATED.search(retained)
    require(match is not None, 'CLI_budget_nonexact_output_missing_its_original_truncation_marker')
    left, right = retained[:match.start()], retained[match.end():]
    require(overall.startswith(left) and overall.endswith(right) and len(left) + len(right) < len(overall),
            'CLI_budget_retained_text_is_not_original_exact_prefix_and_suffix')
    return len(left), len(overall) - len(right)


def omitted(span, cut):
    return cut is not None and span[0] < cut[1] and span[1] > cut[0]


def cli_checks(repo, reply, raw_dir=None, stem='case'):
    """Exact 33/34/35 header x MCP/history required groups and full selected frames."""
    helper, policy, spans = cli_constants(str(Path(repo).resolve()))
    payload = reply['content'][0]['text']
    doc = body(reply)
    required, graph, unknown, selected = checks_for_joint(doc, reply)
    extents = spans(payload)
    checks = []
    for sec, width in zip(('0.0000','10.0000','100.0000'), (33, 34, 35), strict=True):
        original = helper['model_items'](reply, sec)
        require(len(original[0]['text'].encode()) == width, 'unexpected_pinned_cli_header')
        mcp = helper['truncate_items'](original, policy['MCP_bytes'])
        history = helper['truncate_items'](mcp, policy['history_approximate_tokens'], token_mode=True)
        for name, stage in (('MCP', mcp), ('history', history)):
            groups = [it['text'] for it in stage if it['type'] == 'input_text']
            require(len(groups) == 2 and groups[0] == original[0]['text'], 'actual_tool_header_or_body_disappeared')
            stage_body = groups[1]
            bounds = selected_spans(payload, stage_body)
            lost = [list(key) for key in required if omitted(extents[key], bounds)]
            frame_losses = []
            image_paths_ok = True
            for link in graph:
                i = link['image_index']
                observation_prefix = ('facts', 'observations', i)
                require(all(extents[observation_prefix + (field,)] for field in FIELD_PATHS),
                        'archived_image_observation_is_incomplete')
                copied_fields = [field for field in FIELD_PATHS if omitted(extents[('frames', i, field)], bounds)]
                identity = {field: not omitted(extents[observation_prefix + (field,)], bounds) for field in FIELD_PATHS}
                unique = [field for field in doc['frames'][i] if field not in (*FIELD_PATHS, 'view_name')
                          and omitted(extents[('frames', i, field)], bounds)]
                image_paths_ok = image_paths_ok and all(identity.values())
                frame_losses.append({'index': i, 'view': link['view'], 'complete_witness_selected': i in selected,
                                     'copy_losses_in_frames': copied_fields,
                                     'unique_frame_fields_not_fully_retained': unique,
                                     'same_path_ref_sha_survive_on_existing_observation': identity})
            rendered = [row for row in stage if row['type'] == 'input_image']
            original_images = [row for row in original if row['type'] == 'input_image']
            preserves_png = rendered == original_images and len(rendered) == len(graph)
            evidence = {'header_bytes': width, 'stage': name, 'retained_body_utf8_bytes': len(stage_body.encode()),
                        'exact_original_body_sha256': digest(payload.encode()),
                        'exact_stage_items_sha256': digest(compact(stage)),
                        'cut_original_character_offsets': bounds, 'required_groups_incomplete': lost,
                        'frame_identity_coverage': frame_losses,
                        'same_original_native_block_order_count_and_PNG_bytes': preserves_png,
                        'same_observation_paths_refs_digests': image_paths_ok,
                        'all_required': not lost and preserves_png and image_paths_ok}
            if raw_dir:
                # Save actual separate tool header, truncated text and original media items.
                filename = raw_dir / f'{stem}_{width}_{name}.json'
                evidence['actual_replay_stage'] = emit(filename, compact(stage) + b'\n')
            checks.append(evidence)
    return checks, graph, unknown


def prepend(packet):
    rep = deepcopy(packet)
    doc = body(rep['result'])
    saved = doc.pop('task_result')
    require(saved, 'negative_prepend_must_move_existing_task_result_only')
    rep['result']['content'][0]['text'] = compact({'task_result': saved, **doc}).decode('utf8')
    require(body(rep['result']) == body(packet['result']), 'negative_prepend_dropped_existing_member')
    return rep


def adjudicate(repo, a, b, wire_dir):
    stages = wire_dir / 'stages'
    stages.mkdir()
    evidence = {}
    for fixture in ORIGINALS:
        aa, bb = a['cases'][fixture], b['cases'][fixture]
        require(aa['catalogue'] == bb['catalogue']
                and aa['archived'] == bb['archived']
                and aa['whole_producer_sha256'] == bb['whole_producer_sha256'],
                'tools_list_or_archived_fixture_semantic_input_changed')
        before, after = aa['replayed'], bb['replayed']
        old_body, new_body = body(before['result']), body(after['result'])
        require(list(new_body)[-1] == 'task_result' and list(old_body)[-1] != 'task_result'
                and old_body == new_body and compact({k:v for k,v in old_body.items() if k != 'task_result'})
                    == compact({k:v for k,v in new_body.items() if k != 'task_result'})
                and before['result']['content'][1:] == after['result']['content'][1:]
                and len(mcp_bytes(before)) == len(mcp_bytes(after)),
                'candidate_changed_a_field_value_order_body_size_or_image_instead_of_only_tail')
        variants = {
            'A_original': aa['archived'], 'A_replayed': before, 'A_original_prepend': prepend(aa['archived']),
            'A_replayed_prepend': prepend(before), 'B_tail': after,
        }
        notes = {}
        for key, packet in variants.items():
            replay, graph, unknown = cli_checks(repo, packet['result'], stages, fixture + '_' + key)
            exact_conditions = (all(stage['all_required'] for stage in replay) if key == 'B_tail' else
                all(not stage['all_required'] and expected_loss(key, stage['required_groups_incomplete'])
                    for stage in replay))
            require(all(stage['same_original_native_block_order_count_and_PNG_bytes'] for stage in replay),
                    'fixed_CLI_budget_changed_actual_PNG_bytes_or_order')
            notes[key] = {'kind': ORDERS[key], 'stages': replay, 'original_images': graph, 'unknown_regions': unknown,
                          'correct_mandatory_fields_gate_for_this_variant': exact_conditions}
            if key.endswith('prepend'):
                notes[key]['deliberately_reordered_RX'] = emit(stages / (fixture + '_' + key + '_RX.bin'), mcp_bytes(packet))
        require(all(row['unknown_regions'] == notes['B_tail']['unknown_regions'] for row in notes.values()),
                'intentional_or_product_reorder_changed_unknown_region')
        standalone = None
        if aa['standalone'] is not None:
            require(mcp_bytes(aa['standalone']['reply']) == mcp_bytes(bb['standalone']['reply']),
                    'standalone_second_measurement_output_not_byte_identical')
            standalone = {'historic': aa['standalone']['original_caller'], 'A': aa['standalone']['raw_MCP'],
                          'B': bb['standalone']['raw_MCP'], 'exact_serialized_bytes_unchanged': True}
        evidence[fixture] = {'all_cases_passed': all(item['correct_mandatory_fields_gate_for_this_variant'] for item in notes.values()),
                             'standalone_followup': standalone, 'ordered_witness_membership': aa['current_witness_membership'],
                             'historical_saved_raw_A': aa['historical_packet'], 'actual_A_replay': aa['replayed_packet'],
                             'actual_B_replay': bb['replayed_packet'], 'whole_current_source': aa['task_truth'],
                             'historical_real_CLI_packet': aa['outer'], 'same_body_byte_count': ORIGINALS[fixture]['body_bytes'],
                             'relative_order_and_Native_PNG_exact': True, 'variants': notes,
                             'serializer_median_ns': {'A': aa['serialized_elapsed_ns_median'],
                                                      'B': bb['serialized_elapsed_ns_median']}}
    return evidence


def expected_loss(key, missing):
    if key == 'A_original_prepend':
        return ['facts', 'region_evidence'] in missing
    if key == 'A_replayed_prepend':
        # The saved producer uses sorted nested keys. This additional negative
        # still requires lost observation evidence, but the specific field can differ.
        return any(['facts', fact] in missing for fact in REGION_FIELDS)
    return ['task_result'] in missing


def main(repo, baseline, candidate, output, wire_dir):
    require(not wire_dir.exists() and not output.exists(), 'fresh_isolated_replay_path_required')
    wire_dir.mkdir(parents=True)
    aa = run_worker(repo, baseline, wire_dir / 'A')
    bb = run_worker(repo, candidate, wire_dir / 'B')
    require(aa['source_sha256'] == BASE_SOURCE and bb['source_sha256'].startswith(CANDIDATE_SOURCE)
            and aa['source_pins'] == bb['source_pins'], 'registered_candidate_or_original_fixture_identity_changed')
    comparisons = adjudicate(repo, aa, bb, wire_dir)
    passed = all(row['all_cases_passed'] for row in comparisons.values())
    v = repo / 'verification'
    checks = [ARCHIVES, SERIALIZER, SPANS, BUDGET,
              'm1_source_region_facts_first_001/checks/client_budget_replay.py',
              'm1_source_region_facts_first_001/checks/CLIENT_BUDGET_REVIEW.json']
    report = {'schema': 'm1-joint-full-task-tail-installed-MCP-replay-v1',
              'baseline': pin(baseline), 'candidate': pin(candidate),
              'replay_source_pins': aa['source_pins'] + [pin(Path(__file__)), *[pin(v / path) for path in checks]],
              'passed': passed, 'fixtures': comparisons, 'identical_actual_tools_list': True,
              'actual_case_count': len(comparisons), 'actual_new_rasters': 0, 'actual_Blender_launches': 0,
              'model_runs': 0, 'new_live_qualification_or_paid_API_calls': 0,
              'actual_provider_truncation_or_followup_savings': 'unmeasured'}
    emit(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n')
    print(pin(output), 'passed', passed)
    return 0 if passed else 1


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_Python_requires_-I_-B')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--repo', type=Path, required=True)
    cli.add_argument('--baseline', type=Path)
    cli.add_argument('--candidate', type=Path)
    cli.add_argument('--worker', type=Path)
    cli.add_argument('--wire-dir', type=Path, required=True)
    cli.add_argument('--output', type=Path)
    args = cli.parse_args()
    root = args.repo.resolve(strict=True)
    if args.worker:
        worker(root, args.worker, args.wire_dir)
    else:
        if not args.candidate or not args.output:
            cli.error('--candidate and --output required')
        baseline = args.baseline or root / 'verification' / BASE
        raise SystemExit(main(root, baseline, args.candidate, args.output, args.wire_dir))
