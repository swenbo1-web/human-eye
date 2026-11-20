"""Audit the one dense brief v2 qualification against current source and original raster evidence."""

import argparse
import json
from pathlib import Path
import runpy
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_m4_dense_region_brief_001')
PRIOR_NS = V / 'm4_dense_panel_sweep_001'
TRUTH = PRIOR_NS / 'truth/CURRENT_TRUTH.json'
TRUTH_SHA = 'd4d05b3ffb713331c4348852335b9d17ebfe9690c7013062d39b82bb8087700a'
BASE_RECEIPT = PRIOR_NS / 'checks/QUALIFICATION_QP.json'
BASE_RECEIPT_SHA = 'a5f81128ed502163b141f730a199e7645e34a9e41cd0c65493f1c2b3fe533903'
BASE_BINDING = V / 'm4_cross_scale_projected_bounds_001/install/PRODUCT_RUN_BINDING.json'
BASE_SOURCE = '6f2fc9762f9410f968c4768545c14077ca944f75416fb04aa9d14145a4c630d8'
BASE_COMMIT = '3cbf240562b61cff18c2818c6d134904259b36b7'
BINDING = NS / 'install/PRODUCT_RUN_BINDING.json'
MAX_BODY_BYTES = 10_800
V2 = 'active-observation-region-task-brief-v2'


original = runpy.run_path(str(PRIOR_NS / 'checks/qualify_product.py'))
read, require, verified, write, digest, rows, ms, stage_ms = (original[name] for name in (
    'read', 'require', 'verified', 'write', 'digest', 'rows', 'ms', 'stage_ms'))
capture_check = original['capture_check']
region_key, region_label = original['region_key'], original['region_label']


def check_cli(result, images, output):
    helpers, limits = original['POLICY']['budget_helpers']()
    require((limits['MCP_bytes'], limits['history_approximate_tokens']) == (12000, 3000),
            'fixed_CLI_limits_changed')
    output.mkdir(parents=True, exist_ok=True)
    stages = []
    for seconds, header in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        raw = helpers['model_items'](result, seconds)
        require(len(raw[0]['text'].encode()) == header, 'fixed_CLI_header_shape_changed')
        mcp = helpers['truncate_items'](raw, limits['MCP_bytes'])
        history = helpers['truncate_items'](mcp, limits['history_approximate_tokens'], token_mode=True)
        stage = {'sample_wall_seconds': seconds, 'header_bytes': header}
        for name, observed in (('MCP', mcp), ('history', history)):
            text_items = [item['text'] for item in observed if item['type'] == 'input_text']
            image_items = [item for item in observed if item['type'] == 'input_image']
            image_exact = image_items == [item for item in raw if item['type'] == 'input_image']
            text_exact = text_items == [item['text'] for item in raw if item['type'] == 'input_text']
            hashes = [
                digest(original['PIXEL']['typed']['DECODE']({
                    'mimeType': item['image_url'].split(';', 1)[0][5:],
                    'data': item['image_url'].split(',', 1)[1],
                })) for item in image_items
            ]
            path = output / f'{seconds}_{name}.json'
            write(path, {'text_items': text_items, 'PNG_sha256': hashes})
            stage[name] = {'text_exact': text_exact, 'images_exact': image_exact,
                           'body_UTF8_bytes': len(text_items[1].encode()) if len(text_items) > 1 else 0,
                           'retained_PNG_sha256': hashes, 'retained_representation_sha256': digest(path.read_bytes())}
        stages.append(stage)
    expected = [item['PNG_sha256'] for item, _ in images]
    return {'limits': limits, 'stages': stages,
            'passed': all(stage[name]['text_exact'] and stage[name]['images_exact'] and
                          stage[name]['retained_PNG_sha256'] == expected
                          for stage in stages for name in ('MCP', 'history')),
            'live_model_or_provider_input_observed': False}


def installed_binding(slot, frozen, result):
    baseline = read(BASE_BINDING)
    candidate = read(BINDING)
    commit = candidate['preparation_git']
    source = candidate['source_sha256']
    require(baseline['preparation_git'] == BASE_COMMIT and baseline['source_sha256'] == BASE_SOURCE and
            candidate['historical_preparation_git'] == BASE_COMMIT and
            candidate['historical_source_sha256'] == BASE_SOURCE and
            candidate['changed_product_sources'] == ['human_eye_plugin/live_spatial_mcp.py'] and
            frozen['product'] == {'commit': commit, 'source_sha256': source} and
            result['product_source_sha256'] == source and
            result['product_binding_sha256'] == digest(BINDING.read_bytes()) and source != BASE_SOURCE,
            'frozen_product_and_slot_candidate_do_not_agree')
    baseline_manifest = {row['path']: row['sha256'] for row in baseline['source_manifest']}
    candidate_manifest = {row['path']: row['sha256'] for row in candidate['source_manifest']}
    require(len(candidate_manifest) == len(candidate['source_manifest']) == len(baseline_manifest) == 143 and
            baseline_manifest.keys() == candidate_manifest.keys() and
            {name for name in baseline_manifest if baseline_manifest[name] != candidate_manifest[name]} ==
            {'human_eye_plugin/live_spatial_mcp.py'}, 'candidate_is_not_one_actual_installed_source_change')
    install = Path(candidate['install_root'])
    for name, sha in candidate_manifest.items():
        verified(install / name, sha, install)
    require(digest(Path(candidate['wheel_path']).read_bytes()) == candidate['wheel_sha256'],
            'registered_candidate_wheel_changed')
    identity = read(slot / 'MCP_IDENTITY.json')
    ready = read(slot / 'RUNTIME_READY.json')
    identity_keys = ('distribution_version', 'source_sha256', 'build_id', 'base_version',
                     'implementation_revision', 'protocol_version')
    require(identity['source_kind'] == 'installed_distribution' and identity['source_file_count'] == 143 and
            identity['identity_check']['compatible'] is True and
            all(identity[k] == candidate[k] for k in identity_keys) and
            ready['product_source_sha256'] == source and
            read(slot / 'INSTALLED_TOOLS.json') == read(BASE_BINDING.with_name('TOOLS_SCHEMA.json')),
            'actual_candidate_process_or_fixed_tool_schema_changed')
    return candidate


def capture_and_rows(slot, installed, terminal, truth, producer, public):
    binding, task = producer['binding'], producer['facts']['region_task']
    require(public['read_only'] is producer['read_only'] is True and
            public['execution_authority'] is producer['execution_authority'] is False and
            public['status'] == producer['status'] == 'complete' and
            public['observation_status'] == producer['observation_status'] == 'region_task_observed' and
            public['session_id'] == producer['session_id'] and public['binding'] ==
            {key: item for key, item in binding.items()
             if key not in ('schema', 'objects', 'camera_policy', 'camera_specification')} and
            public.get('task_result') == producer.get('task_result'),
            'public_body_lost_current_read_only_producer_binding')
    source_audit = capture_check['Audit']()
    captures, _ = capture_check['decode_captures'](slot, installed, source_audit)
    capture = capture_check['current_capture'](captures, binding, source_audit)
    capture_check['source_binding_checks'](capture, binding, installed, source_audit)
    terminal_by_name = {row['name']: row for row in terminal['objects']}
    require(len(capture['meshes']) == len(terminal_by_name) and
            {mesh['name'] for mesh in capture['meshes']} == set(terminal_by_name), 'product_capture_roster_differs')
    for mesh in capture['meshes']:
        before = terminal_by_name[mesh['name']]
        require(mesh['object_id'] == before['object_id'] and
                capture['host_identity']['object_instances'][mesh['object_id']] == before['instance_id'] and
                mesh['faces'] == before['evaluated']['triangles'] and
                mesh['vertices'] == before['evaluated']['vertices_world_m'], 'product_source_not_current/' + mesh['name'])
    original_rows = task['rows']
    public_rows = public['region_task']['rows']
    true_rows = truth['eligible']
    by_key = [{region_key(row): row for row in group} for group in (original_rows, public_rows, true_rows)]
    require(all(len(group) == len(mapping) == 13 for group, mapping in
                zip((original_rows, public_rows, true_rows), by_key, strict=True)) and
            list(by_key[0]) == list(by_key[1]) and set(by_key[0]) == set(by_key[2]) and
            public['region_task']['summary'] == task['summary'] and
            public['region_task']['conditions'] == task['conditions'] == original['REQUEST']['query']['region_task'],
            'exact_region_set_or_producer_order_changed')
    objects = public['objects']
    require([dict(zip(objects['columns'], row, strict=True)) for row in objects['rows']] == binding['objects'],
            'public_object_sources_do_not_match_current_binding')
    scopes = producer['scopes']
    require(public['scopes']['rows'] == [
        [scope['scope_id'], scope['binding']['camera_identity'], scope['binding']['binding_sha256'],
         len(scope['frame_refs']), len(scope['facts']['coverage']['covered_roi_ids'])] for scope in scopes],
        'public_scope_table_does_not_match_producer')
    observations = {row['frame_identity']: row for scope in scopes for row in scope['facts']['observations']}
    expected = []
    for row in original_rows:
        witness = row['complete_witness']
        if witness is None:
            continue
        observation = observations[witness['frame_identity']]
        pixel = observation['pixel_rows'][witness['pixel_row_index']]
        expected.append([witness['scope_id'], witness['frame_identity'], row['roi_id'],
                         pixel['visible_surface_pixels'], pixel['contrasting_boundary_pixels'],
                         pixel['visible_pixel_bounds'], pixel['visible_pixel_anchor']])
    require(public['witness_pixels']['rows'] == expected, 'public_witness_pixels_or_location_changed')
    return capture, source_audit, by_key


def inspect_product(slot, reply, event, meter, installed, terminal, truth, baseline, outcome):
    sys.path.insert(0, str(HERE))
    from brief_schema import verify_brief

    response = reply['result']
    body = response['content'][0]['text']
    body_raw = body.encode()
    archive = event['producer_archive']
    raw = verified(archive['path'], archive['sha256'], slot)
    require(archive['index'] == 1 and archive['new_observations_for_archive'] == 0,
            'producer_archive_not_same_request')
    producer = json.loads(raw)
    audit = rows(slot / 'product_audit.jsonl')
    trace, = [row for row in audit if row['event'] == 'request_trace' and
              row['trace']['annotations'].get('mcp_request_id') == event['request']['id']]
    relevant = [row for row in audit if row.get('request_id') == trace['request_id']]
    formatter, = [row['image_delivery'] for row in relevant if row['event'] == 'active_observation_mcp_content']
    attempts = [row for row in relevant if row['event'] == 'active_observation_render_attempt']
    frames, selected = producer['constructed_frames'], producer['frames']
    outcome['wire'].update(body_UTF8_bytes=len(body_raw), body_sha256=digest(body_raw),
                           producer_archive_bytes=len(raw), producer_archive_sha256=digest(raw),
                           PNG_bytes=formatter['PNG_bytes'])
    outcome['timing'].update(archive_producer_snapshot_ms=ms(archive['producer_returned_ns'], archive['saved_ns']),
                             formatting_ms=stage_ms(formatter),
                             producer_stages_ms={key: stage_ms(value) for key, value in producer['stages'].items()})
    outcome['work'] = producer['work']
    require(len(attempts) == len(frames) == len(selected) == meter['raster_actual'] == 2 and
            formatter['projection_status'] == 'brief' and len(body_raw) == formatter['public_text_bytes'] and
            formatter['native_blocks_constructed'] == 2 and
            all(row['identity_check']['compatible'] is True for row in relevant),
            'actual_v2_brief_or_two_raster_producer_audit_changed')
    require(json.loads(body)['schema'] == V2, 'product_did_not_publish_v2_brief')
    outcome['body_cap_passed'] = len(body_raw) <= MAX_BODY_BYTES
    public, images = verify_brief(response)
    require(formatter['PNG_bytes'] == sum(len(data) for _, data in images) and len(images) == 2,
            'native_image_blocks_or_bytes_differ_from_producer')
    outcome['images'] = [item for item, _ in images]
    outcome['CLI'] = check_cli(response, images, outcome['cli_path'])
    capture, source_audit, by_key = capture_and_rows(slot, installed, terminal, truth, producer, public)
    outcome['raw_roster'] = {name: [region_label(key) for key in mapping] for name, mapping in
                            zip(('producer', 'brief', 'truth'), by_key, strict=True)}
    binding = producer['binding']
    original['measure_evidence'](slot, truth, selected, frames, images, binding, source_audit,
                                 producer['scopes'], *by_key, terminal, capture, outcome)
    require(len(outcome['original_regions']) == 13 and outcome['proven_geometric_unknowns'] == 2 and
            sum(bool(row['complete_witness']) for row in outcome['original_regions'].values()) == 11,
            'live_13_regions_11_witnesses_2_unknowns_required')
    frame_fields = ('scope_id', 'view', 'image_sha256', 'NPZ_sha256', 'png_bytes', 'npz_bytes',
                    'declared_array_payload_bytes', 'independent_pixels')
    require(all(c[k] == old[k] for c, old in zip(outcome['frames'], baseline['frames'], strict=True)
                for k in frame_fields), 'live_PNG_NPZ_pixels_or_frame_order_differ_from_immutable_base')
    require({k: v for k, v in producer['work'].items() if k != 'frustum_proof_ns'} ==
            {k: v for k, v in baseline['work'].items() if k != 'frustum_proof_ns'},
            'new_projection_changed_geometry_capture_or_raster_work')
    outcome['same_baseline_original_frames_and_work'] = True
    if not outcome['body_cap_passed']:
        outcome['issues'].append('brief_body_exceeds_10800_bytes')
    if not outcome['CLI']['passed']:
        outcome['issues'].append('fixed_CLI_two_stage_replay_lost_original_text_or_images')


def qualify(runtime, freeze_path, outcome):
    truth = json.loads(verified(TRUTH, TRUTH_SHA, PRIOR_NS))
    baseline = json.loads(verified(BASE_RECEIPT, BASE_RECEIPT_SHA, PRIOR_NS))
    require(baseline['passed'] is False and baseline['runtime_source_sha256'] == BASE_SOURCE and
            baseline['reason'] == 'fixed_CLI_replay_lost_required_facts_or_original_images' and
            read(NS / 'inputs/REQUEST.json') == original['REQUEST'] and
            truth['asset_sha256'] == original['ASSET_SHA'], 'registered_truth_base_or_request_changed')
    slot = runtime / 'slots/QP'
    result_path = slot / 'SLOT_RESULT.json'
    publication_path = slot / 'SLOT_PUBLICATION.json'
    result = read(result_path)
    published = read(publication_path)
    started = read(slot / 'SLOT_STARTED.json')
    freeze = digest(freeze_path.read_bytes())
    frozen = read(freeze_path)
    counts = (result.get('budget') or {}).get('counts', {})
    outcome.update(freeze_sha256=freeze, independent_truth_sha256=TRUTH_SHA,
                   baseline_qualification_sha256=BASE_RECEIPT_SHA,
                   slot_result_sha256=digest(result_path.read_bytes()),
                   publication_sha256=digest(publication_path.read_bytes()),
                   owned_slot_status=published['status'], original_slot_errors=result.get('errors', []),
                   runtime_source_sha256=result['product_source_sha256'], denominator=counts,
                   body_cap_bytes=MAX_BODY_BYTES)
    require(all(item['label'] == 'QP' for item in (started, result, published)) and
            published['result_sha256'] == outcome['slot_result_sha256'] and
            started['freeze_sha256'] == result['freeze_sha256'] == freeze and
            result['asset_sha256'] == original['ASSET_SHA'] and result['model_consumers'] == result['paid_API_calls'] == 0,
            'sole_original_qualification_binding_invalid')
    if published['status'] != 'completed':
        outcome['issues'].append('owned_product_slot_failed_before_qualification')
        if (slot / 'product_calls/call_001/RESPONSE.json').is_file():
            reply, _, _, outcome['wire'], outcome['timing'] = original['audit_wire'](slot, started, result, published)
            returned = reply.get('result', {})
            texts = [block['text'] for block in returned.get('content', []) if block.get('type') == 'text']
            outcome['actual_error_response'] = {'isError': returned.get('isError'),
                'JSON_RPC_error': reply.get('error'), 'text_blocks': [
                    {'bytes': len(text.encode()), 'sha256': digest(text.encode()), 'prefix': text[:300]}
                    for text in texts]}
        return
    require(result['status'] == 'completed' and not result['errors'] and published['owned_budget_passed'] is True and
            counts['Blender_start_attempts'] == counts['business_admissions'] == 1 and
            counts['consumer_admissions'] == counts['pending_raster_reservations'] == 0 and
            counts['all_raster_actual'] == counts['all_raster_upper'] == counts['qualification_raster_actual'] == 2,
            'owned_slot_close_without_exact_registered_denominator')
    closed = read(slot / 'RUNTIME_CLOSE.json')
    exit_ = closed['public_MCP_exit']
    require(not closed['errors'] and exit_['exited'] and exit_['confirmed'] and exit_['handle_closed'] and
            exit_['exit_code'] == 0, 'actual_MCP_exit_unconfirmed')
    installed = installed_binding(slot, frozen, result)
    outcome['installed_product'] = {'commit': installed['preparation_git'], 'source_sha256': installed['source_sha256'],
                                    'wheel_sha256': installed['wheel_sha256'], 'runtime_sources_verified': 143}
    sys.path.insert(0, installed['dependency_root'])
    terminal, outcome['current_source'] = original['current_source'](slot, result)
    reply, event, meter, outcome['wire'], outcome['timing'] = original['audit_wire'](slot, started, result, published)
    inspect_product(slot, reply, event, meter, installed, terminal, truth, baseline, outcome)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path, default=HERE / 'LIVE_REVIEW.json')
    args = parser.parse_args()
    started = time.perf_counter_ns()
    outcome = {'schema': 'm4-dense-region-brief-QP-live-review-v1', 'label': 'QP', 'issues': [],
               'cli_path': args.runtime / 'preflight/product_cli'}
    try:
        qualify(args.runtime, args.freeze, outcome)
    except Exception as error:
        outcome['issues'].append('product_or_qualification_semantic_evidence_failed')
        outcome['error'] = {'type': type(error).__name__, 'message': str(error)}
    outcome['cli_path'] = str(outcome['cli_path'])
    outcome['passed'] = not outcome['issues']
    outcome['reason'] = 'qualified' if outcome['passed'] else outcome['issues'][0]
    outcome['assessment_ms'] = ms(started, time.perf_counter_ns())
    write(args.output, outcome)
    print(json.dumps({key: outcome.get(key) for key in ('passed', 'reason', 'issues', 'error', 'wire', 'denominator',
                     'independent_actual_positive_axes')}, ensure_ascii=False))
    return 0 if outcome['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
