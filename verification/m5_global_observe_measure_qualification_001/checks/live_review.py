"""Validate both real zero-model global observation and whole-object measurement slots."""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from live_observation import (BLOCKER_PATH, BRIEF_PATH, PIXEL_PATH, PROOF_PATH, checker, digest, pixel, prior,
                              read, require, verified, verify_observation, verify_frames)
from live_wire import POLICY_PATH, cli_replay, elapsed, frozen_archive, json_lines, raw_wire


NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_m5_global_observe_measure_qualification_001')
OLD = Path('D:/he_m4_cross_scale_pixel_evidence_001')
OLD_NAMESPACE = V / 'm4_cross_scale_pixel_evidence_001'
OLD_ARCHIVE_SHA = '583456c1838a6fd200104fcfaf72dfa279beaf928901a5b42164b99f60415bae'
GEOMETRY = OLD / 'slots/P1/TERMINAL_SOURCE.json'
GEOMETRY_SHA = 'a550a7018e07fc8e18204ffe77231b254d93a9558b2114036d2113898120a52b'
TRUTH = pixel['TRUTH']
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
SOURCE = '301caf777d446938497b53d5d49d67279cdcdb4ba2ee03e8aeb7e737c66076b6'
PRODUCT = '9552d5c7103d9d8a08799adde96534990c6815f9'
WHEEL = '289cd77e16eb56bbcee3442db5e882b7ce3650732420c0a1e081ee737f3bf177'
BINDING = V / 'm4_dense_raster_cross_001/install/PRODUCT_RUN_BINDING.json'

sys.path.insert(0, str(NS / 'truth'))
from measurement import verify_measurement


def pin(path):
    path = path.resolve()
    return {'path': str(path), 'sha256': digest(path.read_bytes()), 'bytes': path.stat().st_size}


def truth():
    return json.loads(verified(TRUTH, pixel['TRUTH_SHA'], TRUTH.parent))


def old_archive():
    return frozen_archive(OLD_NAMESPACE / 'RUNTIME_INDEX.json', OLD, OLD_ARCHIVE_SHA)


def observed_request(kind):
    return read(NS / 'inputs' / f'{kind.upper()}.json')


def install_proof():
    data = read(BINDING)
    require(data['preparation_git'] == PRODUCT and data['source_sha256'] == SOURCE
            and digest(Path(data['wheel_path']).read_bytes()) == data['wheel_sha256'] == WHEEL
            and len(data['source_manifest']) == 143, 'current_frozen_143_source_install_required')
    root = Path(data['install_root'])
    for row in data['source_manifest']:
        verified(root / row['path'], row['sha256'], root)
    if data['dependency_root'] not in sys.path:
        sys.path.insert(0, data['dependency_root'])
    return data


def public_task_equal(task, producer):
    require(task == producer and task['binding']['runtime_source_sha256'] == SOURCE,
            'actual_public_and_producer_measurement_disagree')


def closed_slot(slot, freeze, installed, count):
    raw, published, started = (read(slot / name) for name in
                              ('SLOT_RESULT.json', 'SLOT_PUBLICATION.json', 'SLOT_STARTED.json'))
    require(raw['status'] == published['status'] == 'completed' and not raw['errors']
            and published['result_sha256'] == digest((slot / 'SLOT_RESULT.json').read_bytes())
            and all(row['label'] == slot.name for row in (raw, published, started))
            and published['owned_budget_passed'] is True
            and all(row['freeze_sha256'] == freeze and row['arm'] == slot.name
                    and row['phase'] == 'qualification' for row in (raw, started))
            and raw['model_consumers'] == raw['paid_API_calls'] == 0
            and raw['product_source_sha256'] == SOURCE and raw['asset_sha256'] == ASSET_SHA,
            'slot_result_did_not_close_as_registered_zero_model_qualification')
    identity = read(slot / 'MCP_IDENTITY.json')
    require(identity['source_kind'] == 'installed_distribution' and identity['source_file_count'] == 143
            and identity['identity_check']['compatible'] is True
            and all(identity[key] == installed[key] for key in ('distribution_version', 'source_sha256',
                 'build_id', 'base_version', 'implementation_revision', 'protocol_version'))
            and read(slot / 'INSTALLED_TOOLS.json') == read(BINDING.with_name('TOOLS_SCHEMA.json')),
            'actual_process_or_tool_catalogue_outside_frozen_install')
    terminal, closure = pixel['score']['bound_terminal'](slot, raw, ASSET_SHA)
    runtime_close = read(slot / 'RUNTIME_CLOSE.json')
    public_exit = runtime_close['public_MCP_exit']
    require(not runtime_close['errors'] and public_exit['exited'] and public_exit['confirmed']
            and public_exit['handle_closed'] and public_exit['exit_code'] == 0, 'original_product_process_unclean_close')
    saved = json.loads(verified(GEOMETRY, GEOMETRY_SHA, OLD))
    fields = ('name', 'mesh_name', 'evaluated', 'native', 'parent', 'matrix_world', 'native_matrix_world',
              'display', 'visible_get', 'modifiers')
    actual = {row['name']: row for row in terminal['objects']}
    require(len(actual) == len(terminal['objects']) == len(saved['objects']) == 28
            and all(all(actual[row['name']][key] == row[key] for key in fields) for row in saved['objects'])
            and sum(len(row['evaluated']['vertices_world_m']) for row in actual.values()) == 416
            and sum(len(row['evaluated']['triangles']) for row in actual.values()) == 744,
            'current_terminal_does_not_match_latest_fixed_evaluated_and_native_sources')
    claims = raw['budget']['records']
    local = [row['claim']['kind'] for row in claims if row['claim']['label'] == slot.name]
    require(local.count('Blender_start') == 1 and local.count('business_tool') == count
            and local.count('raster_attempt') == 3 and local.count('consumer_task') == 0
            and raw['budget']['counts']['pending_raster_reservations'] == 0, 'actual_owned_ledger_mismatch')
    return raw, published, terminal, closure


def host_trace(slot, call, audit, wire):
    request_id = call['request']['id']
    trace, = [row for row in audit if row['event'] == 'request_trace'
              and row['trace']['annotations'].get('mcp_request_id') == request_id]
    spans = trace['trace']['spans']
    selected = [row for row in audit if row.get('request_id') == trace['request_id']]
    obs, = [row for row in selected if row['event'] == 'observe']
    require(all(row['identity_check']['compatible'] is True for row in selected), 'request_bound_to_wrong_source')
    frames = [row for row in selected if row['event'] == 'active_observation_render_attempt']
    image = call['request']['params']['arguments']['include_image']
    require([row['view_name'] for row in frames] == (['SCENE', 'TOP', 'TOP'] if image else []),
            'not_the_actual_expected_constructed_views')
    if image:
        fmt, = [row['image_delivery'] for row in selected if row['event'] == 'active_observation_mcp_content']
        require(fmt['projection_status'] == 'brief' and fmt['public_text_bytes'] == wire['wire']['body_UTF8_bytes']
                and fmt['native_blocks_constructed'] == 1 and fmt['PNG_bytes'] == wire['wire']['PNG_bytes'],
                'public_mixed_packet_not_the_original_producer_format')
    return {'producer_work': obs['task_work'], 'trace_spans': spans, 'measured_view_count': len(frames)}


def outer(slot, kinds, status, wires, events):
    path = slot / 'batch/rpc_03'
    tx_path, rx_path = path / 'TCP_TX.bin', path / 'TCP_RX.bin'
    tx, rx = tx_path.read_bytes(), rx_path.read_bytes()
    receipt = read(path / 'RECEIPT.json')
    request, response = json.loads(tx), json.loads(rx)
    require(status['ready_ns'] <= receipt['started_ns'] <= receipt['received_complete_ns'] <=
            receipt['closed_ns'] <= status['cleanup_started_ns'], 'batch_outside_actual_ready_window')
    require(digest(tx) == receipt['TX_sha256'] and digest(rx) == receipt['RX_sha256']
            and len(tx) == receipt['TX_bytes'] and len(rx) == receipt['RX_bytes']
            and request['operation'] == 'attached_mcp' and response['ok'] is True
            and response['request_id'] == request['request_id'] and response['result'] == receipt['response']
            and response['result']['result']['isError'] is False
            and request['args']['message']['params']['name'] == 'execute_python',
            'original_outer_batch_transport_changed')
    raw = response['result']['result']
    text, *images = raw['content']
    batch = read(slot / 'batch/QUALIFICATION_BATCH.json')
    expected_stdout = ''.join(f"M5_GLOBAL_{kind.upper()}:{wire['result']['content'][0]['text']}\n"
                              for kind, wire in zip(kinds, wires, strict=True))
    value = json.loads(text['text'])
    require(value['error'] is None and not value['stderr'] and value['stdout'] == expected_stdout
            and images == [block for wire in wires for block in wire['result']['content'][1:]]
            and batch == status['outer_batch'] and batch['outer_business_count'] == 1
            and batch['inner_public_count'] == len(wires)
            and batch['internal_public_request_ids'] == [entry['request']['id'] for entry in events]
            and all(batch[key] == receipt[key] for key in ('TX_bytes', 'RX_bytes', 'TX_sha256', 'RX_sha256')),
            'actual_outer_batch_public_packets_or_internal_ids_changed')
    from live_wire import image_hashes, HELPERS
    listed = image_hashes(HELPERS['model_items'](raw, '0.0000'))
    expected_images = [digest(verified(img['path'], img['sha256'], slot)) for img in receipt['images']]
    require(len(expected_images) == 1 and listed == expected_images, 'outer_batch_lost_or_changed_N22_original_PNG')
    # Host output has one textual result and the original PNG. This replay is diagnostic.
    diagnostic = cli_replay(raw, slot / 'batch/CLI_REPLAY', 'outer', note_only=True)
    return {'actual_CLI_envelope': diagnostic, 'request_sha256': digest(tx), 'response_sha256': digest(rx),
            'TX_bytes': len(tx), 'RX_bytes': len(rx), 'public_requests': len(kinds),
            'outer_business_batch_count': 1, 'elapsed_ms': elapsed(receipt['started_ns'], receipt['closed_ns'])}


def compare_frames(frames):
    keys = ('view', 'object_name', 'image_sha256', 'NPZ_sha256', 'png_bytes', 'npz_bytes', 'independent_pixels')
    return [{key: row[key] for key in keys} for row in frames]


def review_slot(runtime, label, freeze, installed, fixed_truth, archived_frames, result):
    kinds = ('observe', 'measure') if label == 'A' else ('joint',)
    slot = runtime / 'slots' / label
    result['status'] = 'failed' if slot.exists() else 'unrun'
    if not slot.exists():
        return result
    raw, published, terminal, closure = closed_slot(slot, freeze, installed, len(kinds))
    events = json_lines(slot / 'PUBLIC_REQUESTS.jsonl')
    meters = [row for row in json_lines(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call']
    audit = json_lines(slot / 'product_audit.jsonl')
    require(len(events) == len(meters) == len(kinds), 'actual_public_request_count_drift')
    wires, public, kinds_to_results = [], [], {}
    for kind, event, meter in zip(kinds, events, meters, strict=True):
        expected = observed_request(kind)
        wire = raw_wire(slot, event, meter, expected)
        public.append(json.loads(wire['result']['content'][0]['text']))
        wire['audit'] = host_trace(slot, event, audit, wire)
        wires.append(wire)
        kinds_to_results[kind] = {'original_wire': wire['wire'], 'timing': wire['timing'], 'audit': wire['audit'],
            'CLI': cli_replay(wire['result'], slot / 'batch/CLI_REPLAY' / kind, kind), 'context': wire['context']}
    result.update(calls=kinds_to_results, current_source=closure, raw_runtime_status=raw['status'],
                  outer_batch=outer(slot, kinds, raw, wires, events),
                  owned_window_ms=elapsed(raw['started_ns'], published['published_ns']),
                  startup_ms=elapsed(raw['started_ns'], raw['ready_ns']),
                  cleanup_ms=elapsed(raw['cleanup_started_ns'], published['published_ns']))
    producer = wires[0]['producer']
    observation = verify_observation(slot, wires[0]['result'], producer, terminal, installed, fixed_truth)
    require(compare_frames(observation['frames']) == compare_frames(archived_frames),
            'current_images_NPZ_and_independent_pixels_differ_from_installed_asset_originals')
    result['observation'] = observation
    checker_audit = checker['Audit']()
    captures, commands = checker['decode_captures'](slot, installed, checker_audit)
    parent = checker['current_capture'](captures, producer['binding'], checker_audit)
    selected = [row for row in captures if row.get('capture_scope') == 'selected_objects']
    if label == 'A':
        require('task_result' not in public[0] and len(selected) == 1 and len(wires[1]['result']['content']) == 1,
                'separate_observation_and_current_selected_object_result_required')
        task = public[1]
        public_task_equal(task, wires[1]['producer'])
        extra = {'selection_capture': selected[0], 'parent_capture': parent}
    else:
        require(not selected, 'joint_path_must_not_capture_any_supplemental_object')
        task = public[0]['task_result']
        public_task_equal(task, producer['task_result'])
        work = producer['work']['task_query']
        require(work['reused_observation_objects'] == work['geometry_alias_reuses'] == 2
                and work['supplemental_objects'] == 0 and work.get('supplemental_capture_calls', 0) == 0,
                'joint_capture_reuse_or_geometry_identity_not_attested')
        extra = {'parent_binding': producer['binding'], 'parent_capture': parent}
    value = verify_measurement(task, terminal, **extra)
    require(value['bindings']['independent_capture_binding_checked'] is True,
            'whole_object_measurement_source_not_independently_bound')
    result.update(measurement=value, original_capture_generations=[row['capture_state'] for row in captures],
                  host_wire_command_count=len(commands), host_commands=[row['command']['type'] if 'type' in row['command']
                      else sorted(row['command']) for row in commands],
                  passed=all(row['CLI']['passed'] for row in kinds_to_results.values()),
                  status='completed', reference_frame_equivalence=True)
    return result


def historical():
    slot = OLD / 'slots/P1'
    archive_reader, members = old_archive()
    old_bind = OLD_NAMESPACE / 'install/PRODUCT_RUN_BINDING.json'
    installed = read(old_bind)
    if installed['dependency_root'] not in sys.path:
        sys.path.insert(0, installed['dependency_root'])
    for path in (slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json', GEOMETRY,
                 slot / 'PUBLIC_REQUESTS.jsonl', slot / 'mcp_io/MCP_IO.jsonl'):
        archive_reader(path)
    event = json_lines(slot / 'PUBLIC_REQUESTS.jsonl')[0]
    meter = next(row for row in json_lines(slot / 'mcp_io/MCP_IO.jsonl') if row['method'] == 'tools/call')
    request = read(OLD_NAMESPACE / 'inputs/REQUEST.json')
    wire = raw_wire(slot, event, meter, request, archive_reader)
    product = wire['producer']
    terminal = json.loads(verified(GEOMETRY, GEOMETRY_SHA, OLD))
    fixed_truth = truth()
    task, audit = pixel['current_geometry'](slot, product, terminal, installed, fixed_truth)
    _, _, images = pixel['typed']['verify_content']({'result': wire['result']}, contract='active_region_task')
    frames, _ = verify_frames(slot, product, terminal, fixed_truth, images, audit)
    for frame in product['constructed_frames']:
        archive_reader(Path(frame['image_path']))
        archive_reader(Path(frame['arrays_path']))
    target = task['N11']
    eligible = next(item['finite_direction_proofs'] for item in fixed_truth['eligible'] if item['object_name'] == 'N11')
    require(all(not value['whole_region_clear'] and value['positive_area_occluders'] for value in eligible.values())
            and len(eligible) == 6 and target['reason'] == 'positive_area_occlusion_all_front_views',
            'historical_six_view_region_geometry_drift')
    return wire, frames, members


def preflight():
    install_proof()
    wire, frames, members = historical()
    folder = HERE / 'historical_CLI_REPLAY'
    replay = cli_replay(wire['result'], folder / 'real', 'observe')
    require(replay['passed'], 'real_historical_originals_fail_frozen_CLI_replay')
    mutated = json.loads(json.dumps(wire['result']))
    body = json.loads(mutated['content'][0]['text'])
    body = {'padding_control': 'P' * 15000, **body}
    mutated['content'][0]['text'] = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    rejected = cli_replay(mutated, folder / 'oversize_control', 'observe')
    require(not rejected['passed'] and all(row[stage]['PNG_exact'] and row[stage]['truncation_detected']
            for row in rejected['stages'] for stage in ('MCP', 'history')), 'fixed_budget_failed_oversize_negative_control')
    files = [Path(__file__), HERE / 'live_observation.py', HERE / 'live_wire.py',
             PIXEL_PATH, BRIEF_PATH, BLOCKER_PATH, PROOF_PATH, POLICY_PATH, TRUTH, BINDING,
             BINDING.with_name('TOOLS_SCHEMA.json'), OLD_NAMESPACE / 'RUNTIME_INDEX.json',
             OLD_NAMESPACE / 'inputs/REQUEST.json', OLD_NAMESPACE / 'install/PRODUCT_RUN_BINDING.json',
             OLD / 'ORIGINAL_RUNTIME.zip',
             NS / 'truth/measurement.py', NS / 'truth/MEASUREMENT_TRUTH.json',
             V / 'm4_cross_scale_assembly_transfer_001/scoring/score_live.py',
             V / 'm4_cross_scale_assembly_transfer_001/scoring/score.py',
             V / 'm4_cross_scale_local_first_view_001/checks/assess_pairs.py',
             V / 'm4_cross_scale_discovery_001/oracle/check_saved.py']
    pins = {**members, **{str(path.resolve()): pin(path) for path in files}}
    return {'passed': True, 'real_28_object_archive_sha256': OLD_ARCHIVE_SHA,
            'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
            'original_wire': wire['wire'], 'three_archived_frames': frames,
            'historical_CLI_replay': replay, 'negative_oversize_CLI_rejected': True,
            'source_pins': [pins[key] for key in sorted(pins)]}


def review(runtime, freeze_path):
    freeze = digest(freeze_path.read_bytes())
    installed = install_proof()
    _, frames, _ = historical()
    slots = []
    for label in ('A', 'B'):
        row = {'label': label, 'passed': False}
        try:
            review_slot(runtime, label, freeze, installed, truth(), frames, row)
        except Exception as error:
            row.update(status='failed', error_type=type(error).__name__, error=str(error))
        slots.append(row)
    visual = semantic = False
    if all(slot.get('observation') for slot in slots):
        visual = all(slots[0]['observation'][key] == slots[1]['observation'][key] for key in (
                     'blockers', 'public_states', 'selected_png_sha256'))
    if all(slot.get('measurement') for slot in slots):
        semantic = all(slot['measurement']['bindings']['independent_capture_binding_checked'] for slot in slots)
    return {'schema': 'm5-global-observe-measure-live-review-v1', 'passed': visual and semantic and
            all(slot['passed'] for slot in slots), 'freeze_sha256': freeze, 'candidate_source_sha256': SOURCE,
            'product_commit': PRODUCT, 'fixed_asset_sha256': ASSET_SHA, 'slots': slots,
            'split_joint_observation_equivalent': visual, 'split_joint_measurement_equivalent': semantic,
            'passed_slot_count': sum(slot['passed'] for slot in slots),
            'denominators': {'registered_owned': 2, 'owned_slot_directories': sum((runtime / 'slots' / name).is_dir()
                 for name in ('A', 'B')), 'original_public_requests': sum(len(slot.get('calls', {})) for slot in slots),
                 'original_outer_batches': sum('outer_batch' in slot for slot in slots),
                 'proven_actual_frames': sum(len(slot.get('observation', {}).get('frames', [])) for slot in slots),
                 'model_consumers': 0}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    data = preflight() if args.preflight else review(args.runtime, args.freeze)
    path = args.output or HERE / ('LIVE_PREFLIGHT.json' if args.preflight else 'LIVE_REVIEW.json')
    with path.open('xb') as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False, default=str).encode() + b'\n')
    print(json.dumps({key: data[key] for key in ('passed', 'passed_slot_count', 'denominators') if key in data}))
    return 0 if data['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
