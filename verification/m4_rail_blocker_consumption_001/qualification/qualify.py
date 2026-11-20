"""Review actual mixed MCP content, current geometry and the original local PNGs."""

from fractions import Fraction
import json
from pathlib import Path
import runpy
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
sys.path[:0] = [str(NS / 'harness'), str(HERE)]

from admission import host_clean, publication, verify_freeze
from common import EXTERNAL, TRUTH, product_for, read, save, sha

from diagnostic import BRIEF, diagnostic_plan


DENSE = runpy.run_path(str(V / 'm4_dense_panel_sweep_formal_001/scoring/score.py'))
HELPERS = DENSE['original']
BRIEF_SCHEMA = runpy.run_path(str(BRIEF))
BRIEF_REVIEW = runpy.run_path(str(V / 'm4_dense_region_brief_001/checks/live_review.py'))
TYPED = runpy.run_path(str(V / 'm4_cross_scale_live_task_formal_001/checks/typed_diagnostic.py'))
REVIEW = runpy.run_path(str(NS / 'scoring/score.py'))
require = HELPERS['require']
rows = HELPERS['rows']
verified = HELPERS['verified']
region_key, region_label = DENSE['region_key'], DENSE['region_label']


def wire(slot, logged, expected):
    ordinal, index = logged['ordinal'], logged['transport_index']
    call = slot / 'client' / f'call_{ordinal:02d}'
    owner = slot / 'owner' / f'tool_{ordinal:02d}'
    transport = slot / 'client/transport' / f'rpc_{index:02d}'
    relay, = (slot / 'client/attachments').glob(f'bridge_*/{index:03d}')
    request_path, response_path = call / 'REQUEST.json', call / 'RESPONSE.json'
    request, reply = read(request_path), read(response_path)
    require(request['params'] == expected and request['id'] == reply['id'] and logged['tool_error'] is False
            and sha(request_path) == logged['request_sha256'] and sha(response_path) == logged['response_sha256']
            and sha(call / 'delivered/READBACK.json') == logged['readback_sha256'], 'diagnostic_receipt_changed')
    for kind, path, value in (('TX', 'REQUEST.json', request), ('RX', 'RESPONSE.json', reply)):
        raw = (transport / f'{kind}.bin').read_bytes()
        require(raw == (relay / f'{kind}.bin').read_bytes() == (owner / path).read_bytes()
                and json.loads(raw) == value, 'original_diagnostic_stdin_stdout_differ/' + kind)
    meter, bridge, owned = (read(p / 'RECEIPT.json') for p in (transport, relay, owner))
    require(meter == read(call / 'RECEIPT.json') and meter['error'] is None and owned['is_error'] is False
            and bridge['origin'] == 'owner' and owned['status'] == 'returned'
            and meter['id'] == request['id'] == bridge['RPC_id'] == owned['RPC_id']
            and meter['RX_bytes'] == bridge['response_bytes'] == owned['response_bytes']
            and meter['TX_bytes'] == bridge['request_bytes'], 'diagnostic_meter_disagreement')
    return reply['result'], {'wire': {name: meter[name] for name in ('TX_bytes', 'RX_bytes', 'TX_sha256', 'RX_sha256')},
                             'owner_ms': (owned['closed_ns'] - owned['started_ns']) / 1e6,
                             'stdio_ms': (meter['closed_ns'] - meter['started_ns']) / 1e6}


def ordinary(slot, raw, truth, terminal):
    fact, _, images = TYPED['verify_content']({'result': raw}, contract='ordinary', fact_index=0)
    require(not images and fact.get('error') is None, 'ordinary_geometry_diagnostic_not_read_only_text')
    proof = json.loads(fact['stdout'])
    expected = {}
    for target in truth['eligible']:
        if target['unit_normal'] != [-1, 0, 0]:
            continue
        eligible = target['finite_direction_proofs']['LEFT']
        expected[region_key(target)] = sorted([hit['object_name'], hit['source_triangle_index'],
             hit['projected_target_plane_area_m2_exact']] for hit in eligible['positive_area_occluders'])
    matched = {(row['target'][0], tuple(row['target'][1])): row['hits'] for row in proof['targets']}
    device = read(slot / 'DEVICE_EVIDENCE.json')
    source, = [row for row in device['sources'] if not row['terminal']]
    captured = json.loads(verified(source['path'], source['sha256'], slot))
    require(source['status'] == 'complete' and source['worker']['pid'] == terminal['source']['pid']
            and source['worker']['sha256'] == source['sha256'], 'actual_ordinary_source_receipt_mismatch')
    live = {part['name']: part for part in terminal['objects']}
    meshes = {mesh['name']: mesh for mesh in captured['objects']}
    require(len(captured['objects']) == len(meshes) == len(live) and meshes.keys() == live.keys() and
            all(mesh['object_id'] == live[name]['object_id'] and mesh['instance_id'] == live[name]['instance_id']
                and mesh['vertices'] == live[name]['evaluated']['vertices_world_m']
                and mesh['triangles'] == live[name]['evaluated']['triangles']
                and mesh['visible_get'] == live[name]['visible_get'] for name, mesh in meshes.items()),
            'actual_ordinary_source_is_not_same_evaluated_geometry')
    require(proof['counts'] == {'objects': 21, 'vertices': 148, 'triangles': 184} and
            proof['source_ref'] == source['source_ref'] and len(matched) == len(proof['targets']) == 2 and
            matched == expected and all(row['view'] == 'LEFT' for row in proof['targets']),
            'ordinary_actual_source_does_not_replay_exact_occlusion_truth')
    return proof


def inspect_product(slot, raw, truth, terminal, installed, arm, outcome):
    event, = rows(slot / 'PUBLIC_REQUESTS.jsonl')
    request = event['request']
    require(request['params'] == diagnostic_plan()[0] and event['response']['result'] == raw and
            read(slot / 'owner/tool_01/PRODUCT_RESPONSE.json') == event['response'],
            'installed_stdio_and_consumed_public_result_disagree')
    rpc = slot / 'mcp' / f"rpc_{event['receipt']['index']:02d}"
    require(json.loads((rpc / 'TX.bin').read_bytes()) == request
            and json.loads((rpc / 'RX.bin').read_bytes()) == event['response'],
            'installed_product_original_bytes_differ')
    archive = event['producer_archive']
    producer = json.loads(verified(archive['path'], archive['sha256'], slot))
    require(archive['new_observations_for_archive'] == 0, 'qualification_archive_rerender')
    body = json.loads(raw['content'][0]['text'])
    legacy, images = BRIEF_SCHEMA['verify_brief'](raw)
    outcome.update(body_UTF8_bytes=len(raw['content'][0]['text'].encode()), PNG_bytes=sum(len(image) for _, image in images),
                   PNG=[metadata for metadata, _ in images], producer_archive_sha256=archive['sha256'],
                   installed_RX_bytes=(rpc / 'RX.bin').stat().st_size, producer_stages=producer['stages'])
    outcome['CLI'] = BRIEF_REVIEW['check_cli'](raw, images, slot / 'client/CLI_REPLAY')
    require(outcome['CLI']['passed'], 'fixed_CLI_cut_qualification_brief_or_original_PNG')

    oracle = {region_key(row): row for row in truth['eligible']}
    audit = DENSE['capture_check']['Audit']()
    captures, _ = DENSE['capture_check']['decode_captures'](slot, installed, audit)
    truths = DENSE['validated_rows'](slot, installed, terminal, oracle, legacy, legacy['region_task']['rows'],
                                     producer, captures)
    require(len(truths) == len(legacy['region_task']['rows']) == len(oracle) == 4
            and producer['read_only'] is legacy['read_only'] is True and
            producer['execution_authority'] is legacy['execution_authority'] is False,
            'brief_not_exactly_the_current_four_source_regions')
    binding = producer['binding']
    scopes = {scope['scope_id']: scope for scope in producer['scopes']}
    all_frames = {f['image_ref']: f for f in producer['constructed_frames']}
    selected = {f['image_ref']: f for f in producer['frames']}
    require(len(all_frames) == len(producer['constructed_frames']) <= 6 and
            len(selected) == len(images) == len(producer['frames']) and
            [metadata['ref'] for metadata, _ in images] == list(selected),
            'qualification_frame_count_or_wire_order_invalid')
    by_ref = {metadata['ref']: (metadata, blob) for metadata, blob in images}
    outcome['constructed_frames'] = []
    checked = {}
    for ref, frame in all_frames.items():
        scope = scopes[frame['scope_id']]
        probe = DENSE['product_probe'](frame, {name: value['binding'] for name, value in scopes.items()}, binding, slot)
        view = DENSE['inspect_frame'](slot, probe, terminal, truth)
        if ref in by_ref:
            metadata, png = by_ref[ref]
            require(verified(probe['PNG'], probe['PNG_sha256'], slot) == png and
                    metadata['frame_identity'] == frame['frame_identity'] and selected[ref] == frame,
                    'actual_png_not_the_original_bound_frame')
        require(frame['frame_identity'] in scope['frame_refs'], 'frame_outside_published_scope')
        checked[ref] = view
        outcome['constructed_frames'].append({'ref': ref, 'delivered': ref in by_ref, **view})

    case = outcome['cases'] = []
    for row in legacy['region_task']['rows']:
        key = region_key(row)
        target = oracle[key]
        tag = region_label(key)
        witness = row['complete_witness']
        if target['unit_normal'][0] == 1:
            require(witness is not None and row['status'] == 'covered' and row['reason'] == 'observed_readable',
                    'missing_local_SCENE_original/' + tag)
            ref = witness['image_ref']
            actual = checked[ref]
            scoped = scopes[actual['scope']]['binding']
            same = [r for r in producer['facts']['region_task']['rows'] if region_key(r) == key]
            require(actual['scope'] != 'global' and actual['view'] == 'SCENE' and ref in by_ref and
                    actual['frame_identity'] == witness['frame_identity'] and actual['scope'] == witness['scope_id'] and
                    witness['native_content_block_index'] == by_ref[ref][0]['content_index'] and
                    actual['witnesses'][tag]['qualifies'] and len(same) == 1,
                    'local_SCENE_projection_pixel_or_delivery_contract/' + tag)
            DENSE['capture_check']['local_binding_checks'](scopes[actual['scope']], binding, same[0]['source'], audit)
            observation, = [item for item in scopes[actual['scope']]['facts']['observations']
                            if item['frame_identity'] == witness['frame_identity']]
            pixel = observation['pixel_rows'][witness['pixel_row_index']]
            measured = actual['witnesses'][tag]
            require(pixel['roi_id'] == row['roi_id'] and pixel['visible_surface_pixels'] == measured['surface_pixels']
                    and pixel['contrasting_boundary_pixels'] == measured['contrasting_boundary_pixels']
                    and scoped['region_source']['source_triangle_indices'] == list(key[1]),
                    'actual_witness_disagrees_with_pixels_or_local_source/' + tag)
            case.append({'region': tag, 'view': 'SCENE', 'scope': actual['scope'],
                         'visible_surface_pixels': measured['surface_pixels'],
                         'contrasting_boundary_pixels': measured['contrasting_boundary_pixels'], 'ref': ref})
        else:
            require(witness is None and row['status'] == 'unknown' and
                    row['reason'] == 'positive_area_occlusion_all_front_views' and
                    row['view_reasons']['positive_area_occlusion'] == ['LEFT'] and
                    not target['eligible_complete_views'], 'all_front_positive_area_occlusion_not_retained/' + tag)
            case.append({'region': tag, 'view': 'LEFT', 'reason': row['reason']})
    if arm == 'A':
        require('blocker_evidence' not in body, 'baseline_suddenly_contains_candidate_blocker_field')
        outcome['blocker_evidence'] = []
    else:
        outcome['blocker_evidence'] = REVIEW['verify_blockers'](body, producer, terminal, truth)
        require(len(outcome['blocker_evidence']) == 2, 'both_current_B_blocker_certificates_required')


def qualify(label, freeze):
    start = time.perf_counter_ns()
    slot = EXTERNAL / 'slots' / label
    result, pub = publication(label, freeze)
    arm = result['arm']
    outcome = {'label': label, 'arm': arm, 'freeze_sha256': freeze,
               'slot_result_sha256': pub['result_sha256'], 'publication_sha256': sha(slot / 'SLOT_PUBLICATION.json'),
               'truth_sha256': sha(TRUTH), 'passed': False, 'issues': [], 'started_ns': start}
    try:
        require(host_clean(result, pub) and result['status'] == 'completed' and result['model_consumers'] == 0
                and result['paid_API_calls'] == 0, 'actual_zero_model_host_or_diagnostic_not_completed')
        terminal, lifecycle = REVIEW['current_source'](slot, result)
        outcome['source_and_lifecycle'] = lifecycle
        truth = read(TRUTH)
        pair = [wire(slot, logged, expected) for logged, expected in
                zip(result['diagnostic_calls'], diagnostic_plan(), strict=True)]
        outcome['calls'] = [row[1] for row in pair]
        outcome['ordinary'] = ordinary(slot, pair[1][0], truth, terminal)
        outcome['ordinary_CLI'] = BRIEF_SCHEMA['cli_stages'](pair[1][0])
        _, installed = product_for(label)
        inspect_product(slot, pair[0][0], truth, terminal, installed, arm, outcome)
        outcome['passed'] = True
    except Exception as error:
        outcome['issues'].append({'type': type(error).__name__, 'detail': str(error), 'trace': traceback.format_exc()})
    outcome['completed_ns'] = time.perf_counter_ns()
    save(HERE / f'{label}_REVIEW.json', outcome)
    print(label, outcome['passed'], [e['detail'] for e in outcome['issues']], flush=True)
    return outcome


if __name__ == '__main__':
    label, = sys.argv[1:]
    raise SystemExit(not qualify(label, verify_freeze(NS / 'FROZEN.json'))['passed'])
