"""Audit the original paired slot receipts without interpreting consumer answers."""

import argparse
import base64
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import time


NS = Path(__file__).resolve().parents[1]
EXTERNAL = Path('D:/he_m4_live_source_region_task_002')
PROFILE = ['0.152.1', 'gpt-6.1-sol', 'medium', 'default']
PRODUCT = 'human_eye_scene_observe'
SCHEMA = 'source-region-brief-v2'
SLOTS = ('N1', 'P1')
HANDSHAKE = {'initialize', 'notifications/initialized', 'tools/list', 'ping'}
RESOURCE_METHODS = {'resources/list', 'resources/templates/list'}
TOOL_EVENT = re.compile(rb'"type"\s*:\s*"mcp_tool_call"')
TURN_EVENT = re.compile(rb'"event"\s*:\s*\{\s*"type"\s*:\s*"turn.completed"')
RESULT_CONTRACT = NS.parent / 'm1_source_region_facts_first_001/harness/reused/result_contract.py'
SPEC = importlib.util.spec_from_file_location('original_result_contract', RESULT_CONTRACT)
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def read(path, default=None):
    return json.loads(path.read_bytes()) if path.is_file() else default


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.is_file() else []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def match_file(path, digest, size):
    return path.is_file() and path.stat().st_size == size and file_sha(path) == digest


def inside_file(folder, path):
    return bool(path) and Path(path).resolve().is_relative_to(folder.resolve()) and Path(path).is_file()


def elapsed(start, end):
    return end - start if start is not None and end is not None else None


def clock_order(*clocks):
    return all(type(value) is int for value in clocks) and list(clocks) == sorted(clocks)


def select(record, keys):
    return {key: record.get(key) for key in keys}


def size(path):
    return path.stat().st_size if path.is_file() else None


def report_sections(row, sections):
    for label, action in sections.items():
        try:
            row[label] = action()
        except (KeyError, IndexError, ValueError, TypeError, OSError, AttributeError, ImportError) as exc:
            row['audit_errors'][label] = type(exc).__name__


def cli_events(folder):
    tool_events, usage, completion_times = [], [], []
    event_log = folder / 'consumer/events.jsonl'
    if event_log.is_file():
        with event_log.open('rb') as stream:
            for line in stream:
                if TURN_EVENT.search(line):
                    row = json.loads(line)
                    usage.append(row['event'].get('usage'))
                    completion_times.append(row['perf_ns'])
                elif TOOL_EVENT.search(line):
                    row = json.loads(line)
                    event = row['event']
                    if event.get('item', {}).get('type') == 'mcp_tool_call':
                        tool_events.append({'type': event['type'], 'perf_ns': row['perf_ns'], 'item': event['item']})
    return tool_events, usage, completion_times


def content_metrics(response):
    blocks = (response or {}).get('result', {}).get('content', [])
    text_bytes, images = 0, []
    for block in blocks:
        if block['type'] == 'text':
            text_bytes += len(block['text'].encode('utf-8'))
        elif block['type'] == 'image':
            raw = base64.b64decode(block['data'], validate=True)
            images.append({'sha256': sha(raw), 'bytes': len(raw), 'base64_bytes': len(block['data']),
                           'mime_type': block.get('mimeType'), 'PNG_header_valid': raw[:8] == b'\x89PNG\r\n\x1a\n'})
    return text_bytes, images


def result_bodies(result):
    for block in result.get('content', []):
        if block['type'] != 'text':
            continue
        try:
            value = json.loads(block['text'])
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            yield value


def cli_truncation(result, cli_result):
    original = result.get('content', [])
    nested = next(result_bodies(cli_result), {})
    observed = nested.get('content', [])
    if (len(original) != 1 or len(observed) != 1 or nested.get('isError') != result.get('isError')
            or original[0].get('type') != 'text' or observed[0].get('type') != 'text'):
        return None
    full, clipped = original[0]['text'], observed[0]['text']
    marker = re.search(r'…(\d+) chars truncated…', clipped)
    if not marker:
        return None
    prefix, suffix = clipped[:marker.start()], clipped[marker.end():]
    removed = int(marker.group(1))
    return {'explicit_removal_marker': True, 'removed_characters': removed,
            'original_prefix_UTF8_bytes': len(prefix.encode('utf-8')), 'original_suffix_UTF8_bytes': len(suffix.encode('utf-8')),
            'exact_original_head_and_tail': full.startswith(prefix) and full.endswith(suffix) and
                len(full) == len(prefix) + removed + len(suffix)}


def wire_audit(folder, consumer, events):
    owner = read(folder / 'owner/BRIDGE_RESULT.json', {})
    schema = read(folder / 'owner/TOOLS_SCHEMA.json', [])
    owner_tools = {row['attempt']: row for row in owner.get('calls', [])}
    registered = {row['name'] for row in schema}
    business_events = [event for event in events if event['item'].get('server') == 'arm_engine'
                       and event['item'].get('tool') in registered]
    completed = [event for event in business_events if event['type'] == 'item.completed']
    started = [event for event in business_events if event['type'] == 'item.started']
    owner_protocol = {}
    for row in owner.get('protocol', []):
        wire = folder / 'owner' / f'rpc_{row["sequence"]:03d}'
        tx, rx = wire / 'TCP_TX.bin', wire / 'TCP_RX.bin'
        message = read(tx, {}).get('args', {}).get('message', {})
        result = read(rx, {}).get('result')
        owner_protocol[(row.get('method'), row.get('RPC_id'))] = (row, message, result,
            size(tx) == row.get('request_bytes') and size(rx) == row.get('response_bytes'))

    business, controls, protocol, total_tx, total_rx = [], [], Counter(), 0, 0
    for tx in sorted((folder / 'consumer/attachments').glob('bridge_*/*/TX.bin')):
        rx = tx.with_name('RX.bin')
        receipt = read(tx.with_name('RECEIPT.json'), {})
        request, response = read(tx), read(rx)
        method = request.get('method')
        protocol[method] += 1
        tx_bytes, rx_bytes = size(tx), size(rx)
        total_tx += tx_bytes
        total_rx += rx_bytes or 0
        owner_rpc = owner_protocol.get((method, request.get('id')))
        owner_wire_ok = None if not receipt.get('owner_TCP_attempted') else bool(owner_rpc and
            owner_rpc[0]['send_confirmed'] and owner_rpc[1] == request and owner_rpc[2] == response and owner_rpc[3])
        row = {'method': method, 'RPC_id': request.get('id'), 'request_bytes': tx_bytes, 'response_bytes': rx_bytes,
               'request_SHA256': file_sha(tx), 'response_SHA256': file_sha(rx) if rx.exists() else None,
               'received_ns': receipt.get('received_ns'), 'flushed_ns': receipt.get('flush_completed_ns'),
               'origin': receipt.get('origin'), 'owner_TCP_verified': owner_wire_ok,
               'stdio_receipt_verified': receipt.get('request_bytes') == tx_bytes and
                   receipt.get('response_bytes') == rx_bytes and receipt.get('method') == method and
                   receipt.get('RPC_id') == request.get('id')}
        if method != 'tools/call':
            if method in RESOURCE_METHODS:
                key = 'resources' if method == 'resources/list' else 'resourceTemplates'
                row['empty_enumeration_verified'] = bool(response and response.get('result') == {key: []})
            if method == 'initialize':
                instruction = (response or {}).get('result', {}).get('instructions', '')
                row['first_P_default_instruction'] = PRODUCT in instruction and 'omit' in instruction and 'response_detail' in instruction
            if method == 'tools/list':
                row['actual_tools_match_owner_schema'] = bool(schema and response and response.get('result', {}).get('tools') == schema)
            controls.append(row)
            continue

        attempt = len(business) + 1
        name = request.get('params', {}).get('name')
        cli = completed[attempt - 1] if attempt <= len(completed) else None
        item = cli['item'] if cli else {}
        tool_folder = folder / 'owner' / f'tool_{attempt:02d}'
        owner_row = owner_tools.get(attempt, {})
        text_bytes, images = content_metrics(response)
        cli_result = item.get('result') or {}
        cli_text_bytes, cli_images = content_metrics({'result': cli_result})
        result = (response or {}).get('result', {})
        cli_bind = CONTRACT.bind_tool_result(response, item)
        request_ok = item.get('tool') == name and item.get('arguments', {}) == request.get('params', {}).get('arguments', {})
        metadata = request.get('params', {}).get('_meta')
        metadata_checks = []
        if isinstance(metadata, dict):
            for key, cli_names in {'callId': ('callId', 'call_id'), 'itemId': ('itemId', 'item_id'),
                                   'threadId': ('threadId', 'thread_id')}.items():
                metadata_checks.extend(item[alias] == metadata[key] for alias in cli_names if alias in item and key in metadata)
        success = result.get('isError') is False
        meaningful = bool(images or text_bytes)
        if name in ('execute_python', 'execute_blender_code') and text_bytes and success and not images:
            body = next(result_bodies(result), {})
            meaningful = bool(body.get('stdout', '').strip())
        observed = item.get('status') == 'completed' and (bool(cli_images) or meaningful and cli_text_bytes > 0)
        frame_text = [ref for block in cli_result.get('content', []) if block.get('type') == 'text'
                      for ref in re.findall(r'(?:native-image|image|frame):[\w-]+', block['text'])]
        owner_files_ok = None if receipt.get('origin') != 'owner' else bool(owner_row and
              read(tool_folder / 'REQUEST.json') == request and read(tool_folder / 'RESPONSE.json') == response)
        row.update(attempt=attempt, tool=name, returned_tool_error=result.get('isError'), text_UTF8_bytes=text_bytes,
                   images=images, CLI_received_ns=cli['perf_ns'] if cli else None,
                   CLI_text_UTF8_bytes=cli_text_bytes, CLI_images=cli_images, CLI_frame_reference_candidates=sorted(set(frame_text)),
                   CLI_binding=cli_bind, CLI_request_verified=request_ok and all(metadata_checks),
                   request_meta_type=type(metadata).__name__, exposed_CLI_caller_ids_checked=len(metadata_checks),
                   owner_files_verified=owner_files_ok, owner_attempt_present=bool(owner_row),
                   attempt_receipt_verified=receipt.get('attempt') == attempt,
                   successful_evidence=success and meaningful and cli_bind['matched'] and request_ok,
                   CLI_successful_evidence_observed=bool(observed and request_ok))
        if cli and not cli_bind['matched']:
            row['CLI_truncation'] = cli_truncation(result, cli_result)
        business.append(row)

    archive = read(folder / 'consumer/BUSINESS_SOURCE_BINDING.json', {})
    actual_images = [image for row in business if row['CLI_binding']['matched'] for image in row['images']]
    emitted_images = [image for row in business for image in row['CLI_images']]
    cli_images = consumer.get('image_deliveries', [])
    emitted = [(row.get('PNG_sha256'), row.get('PNG_bytes')) for row in cli_images]
    text_total = sum(row['text_UTF8_bytes'] for row in business if row['CLI_binding']['matched'])
    files = [row for row in business if row['origin'] == 'owner']
    charged_control = sum(count for method, count in protocol.items() if method not in HANDSHAKE | {'tools/call'})
    observed_business_start_ids = {event['item'].get('id') for event in started}
    completed_business_ids = {event['item'].get('id') for event in completed}
    return {
        'attempts': business, 'protocol': controls, 'method_counts': dict(protocol),
        'business_attempts': len(business), 'control_attempts_beyond_handshake': charged_control,
        'business_and_control_attempts': len(business) + charged_control,
        'business_errors': sum(row['returned_tool_error'] is True for row in business),
        'owner_attempts': len(owner_tools), 'CLI_completed_business_items': len(completed), 'CLI_started_business_items': len(started),
        'CLI_open_business_items': len(observed_business_start_ids - completed_business_ids),
        'stdio_TX_bytes': total_tx, 'stdio_RX_bytes': total_rx, 'matched_business_text_UTF8_bytes': text_total,
        'owner_business_text_UTF8_bytes': sum(row['text_UTF8_bytes'] for row in business),
        'CLI_business_event_text_UTF8_bytes': sum(row['CLI_text_UTF8_bytes'] for row in business),
        'CLI_business_event_PNG_blocks': len(emitted_images), 'CLI_business_event_PNG_bytes': sum(row['bytes'] for row in emitted_images),
        'matched_PNG_blocks': len(actual_images), 'matched_PNG_bytes': sum(row['bytes'] for row in actual_images),
        'matched_PNG_base64_bytes': sum(row['base64_bytes'] for row in actual_images),
        'first_successful_CLI_evidence_ns': next((b['CLI_received_ns'] for b in business if b['successful_evidence']), None),
        'first_observed_CLI_evidence_ns': next((b['CLI_received_ns'] for b in business if b['CLI_successful_evidence_observed']), None),
        'last_bound_CLI_tool_result_ns': next((b['CLI_received_ns'] for b in reversed(business) if b['CLI_binding']['matched']), None),
        'tool_schema_sha256': file_sha(folder / 'owner/TOOLS_SCHEMA.json') if schema else None,
        'checks': {
            'wire_receipts': bool(protocol) and all(row['stdio_receipt_verified'] for row in business + controls),
            'business_attempts_to_CLI': bool(consumer) and len(business) == len(completed) and not (observed_business_start_ids - completed_business_ids),
            'all_business_content_bound': bool(business) and all(row['CLI_binding']['matched'] and row['CLI_request_verified']
                and row['attempt_receipt_verified'] for row in business),
            'owner_wire_and_files': bool(owner) and len(files) == len(owner_tools) and
                all(row['owner_files_verified'] and row['owner_TCP_verified'] for row in files) and
                all(row['owner_TCP_verified'] is not False for row in controls),
            'actual_tool_inventory': any(row.get('actual_tools_match_owner_schema') is True for row in controls),
            'business_and_control_limit': len(business) + charged_control <= 12,
            'text_and_image_totals': bool(consumer) and text_total == consumer.get('bridge_public_text_bytes') and
                emitted == [(row['sha256'], row['bytes']) for row in actual_images] and
                len(actual_images) == consumer.get('public_image_count') and
                sum(row['bytes'] for row in actual_images) == consumer.get('public_image_bytes'),
            'stdio_totals': bool(consumer) and total_tx == consumer.get('MCP_stdio_TX_bytes') and total_rx == consumer.get('MCP_stdio_RX_bytes'),
            'adapter_corroboration': bool(archive) and not archive.get('binding_errors') and
                archive.get('protocol_RPC_method_counts') == dict(protocol) and archive.get('stdio_attempts') == len(business),
        },
    }


def product_audit(folder, wire, selection, source_digest):
    calls = lines(folder / 'PUBLIC_REQUESTS.jsonl')
    meter = lines(folder / 'mcp_io/MCP_IO.jsonl')
    rpc = {row['id']: row for row in meter}
    recorded = {}
    for packet in sorted((folder / 'owner').glob('tool_*/PRODUCT_ARGUMENTS.json')):
        attempt = int(packet.parent.name.split('_')[-1])
        recorded[attempt] = packet.parent
    items = []
    for wire_row in wire.get('attempts', []):
        if wire_row['tool'] != PRODUCT:
            continue
        attempt = wire_row['attempt']
        if attempt not in recorded:
            items.append({'attempt': attempt, 'status': 'no_forwarded_product_reply'})
            continue
        tool = recorded[attempt]
        upstream = read(tool / 'REQUEST.json')['params']['arguments']
        forwarded = read(tool / 'PRODUCT_ARGUMENTS.json')
        request, response = read(tool / 'PRODUCT_REQUEST.json', {}), read(tool / 'PRODUCT_RESPONSE.json', {})
        receipt = read(tool / 'PRODUCT_RECEIPT.json', {})
        detail = read(tool / 'PRODUCT_DETAIL.json', {})
        call = next((row for row in calls if row['request'] == request), {})
        product_meter = rpc.get(request.get('id'), {})
        client = receipt.get('receipt') or {}
        client_index = client.get('index')
        product_wire = folder / 'mcp' / f'rpc_{client_index:02d}' if type(client_index) is int else None
        tx, rx = (product_wire / 'TX.bin', product_wire / 'RX.bin') if product_wire else (None, None)
        product_wire_ok = bool(tx and rx and tx.is_file() and rx.is_file() and
            match_file(tx, product_meter.get('TX_sha256'), product_meter.get('TX_bytes')) and
            match_file(rx, client.get('RX_sha256'), client.get('RX_bytes')) and read(tx) == request and read(rx) == response)
        if product_wire_ok:
            platform_normalized = rx.read_bytes().replace(b'\r\n', b'\n')
            product_wire_ok = len(platform_normalized) == product_meter.get('RX_text_UTF8_LF_bytes') and \
                sha(platform_normalized) == product_meter.get('RX_text_UTF8_LF_sha256')
        expected = deepcopy(upstream)
        query_region = expected.get('query', {}).get('region', {})
        if query_region.get('source_triangle_indices') == [0]:
            query_region['source_triangle_indices'] = selection['source_triangle_ids']
        result = response.get('result', {})
        body = next(result_bodies(result), {})
        text_bytes, images = content_metrics(response)
        producer = call.get('producer_archive', {})
        producer_path = producer.get('path')
        producer_bound = inside_file(folder / 'product_full', producer_path) and file_sha(producer_path) == producer.get('sha256')
        full = read(Path(producer_path), {}) if producer_bound else {}
        work = full.get('work', {})
        same_projection = result == read(tool / 'RESPONSE.json', {}).get('result') and wire_row['owner_files_verified']
        request_path, index = call.get('request_path'), call.get('index')
        independently_bound = bool(call and product_meter and product_wire_ok and request.get('method') == 'tools/call' and
            request.get('params') == {'name': PRODUCT, 'arguments': forwarded} and index == receipt.get('index') and
            request == read(folder / 'product_calls' / f'call_{index:03d}' / 'REQUEST.json') and
            response == call.get('response') == read(folder / 'product_calls' / f'call_{index:03d}' / 'RESPONSE.json') and
            inside_file(folder / 'product_calls', request_path) and product_meter.get('response_id') == request.get('id'))
        items.append({
            'attempt': attempt, 'status': body.get('status'), 'upstream_detail_present': 'response_detail' in upstream,
            'upstream_response_detail': upstream.get('response_detail'), 'downstream_detail_present': 'response_detail' in forwarded,
            'downstream_response_detail': forwarded.get('response_detail'), 'upstream_include_image': upstream.get('include_image'),
            'actual_schema': body.get('schema'), 'actual_result_kind': body.get('result_kind'), 'result_is_error': result.get('isError'),
            'raw_product_response_and_CLI_bound': bool(independently_bound and same_projection and
                wire_row['CLI_binding']['matched'] and wire_row['CLI_request_verified']),
            'only_bound_selection_expanded': upstream.get('query', {}).get('mode') == 'source_region' and forwarded == expected,
            'standard_first_selection_and_reference': (forwarded.get('query', {}).get('mode') == 'source_region' and
                forwarded.get('query', {}).get('reference') == selection['reference'] and
                forwarded.get('query', {}).get('requested_facts') == ['surface_proximity'] and
                forwarded.get('query', {}).get('region') == {'object': selection['object'],
                    'source_triangle_indices': selection['source_triangle_ids']}),
            'returned_selection_unchanged': body.get('region_ref', {}).get('source_triangle_indices') == sorted(selection['source_triangle_ids']),
            'text_UTF8_bytes': text_bytes, 'images': images, 'product_RPC': product_meter,
            'client_product_wire_receipt': client or None, 'actual_product_wire_verified': product_wire_ok,
            'detail_sidecar': detail or None,
            'producer_capture': {'archive_verified': producer_bound, 'receipt': producer or None,
                'work': work, 'stages': full.get('stages'),
                'frames': [select(frame, ('image_ref', 'image_sha256', 'PNG_bytes', 'compressed_array_file_bytes',
                                           'stages')) for frame in full.get('frames', [])]},
        })
    first = items[0] if items else {}
    first_default = bool(first and first.get('attempt') == 1 and first.get('upstream_detail_present') is False and
        first.get('downstream_detail_present') is False and first.get('upstream_include_image') is True and
        first.get('actual_schema') == SCHEMA and first.get('actual_result_kind') == 'source_region' and
        first.get('status') == 'complete' and first.get('result_is_error') is False and first.get('images') and
        first['only_bound_selection_expanded'] and first['standard_first_selection_and_reference'] and
        first['returned_selection_unchanged'] and first['raw_product_response_and_CLI_bound'])
    identity = read(folder / 'MCP_IDENTITY.json', {})
    return {'calls': items, 'first_default_v2_delivered': first_default,
            'first_default_instruction_delivered': any(row.get('first_P_default_instruction') for row in wire.get('protocol', [])),
            'installed_source_verified': (identity.get('source_sha256') == source_digest and
                                          identity.get('source_kind') == 'installed_distribution'),
            'product_identity': identity or None, 'product_RPC_method_counts': dict(Counter(row['method'] for row in meter)),
            'all_metered_TX_bytes': sum(row.get('TX_bytes', 0) for row in meter),
            'all_metered_RX_UTF8_LF_bytes': sum(row.get('RX_text_UTF8_LF_bytes') or 0 for row in meter),
            'product_actual_raster_attempts': sum(row.get('raster_actual') or 0 for row in meter),
            'product_process_stdout_bytes': size(folder / 'mcp/stdout.raw.bin'),
            'product_process_stderr_bytes': size(folder / 'mcp/stderr.raw.bin')}


def frame_audit(folder, device, wire, evidence):
    import numpy as np
    from PIL import Image

    scene_frames = [frame for frame in device.get('frames', []) if frame.get('view_name') == 'SCENE']
    frames = []
    for frame in scene_frames:
        row = {'frame_ref': frame['ref'], 'origin': frame['origin'], 'checks': {}}
        frames.append(row)
        png, npz = Path(frame['PNG']), Path(frame['NPZ'])
        row['checks']['original_archive_hash_and_size'] = (inside_file(folder, png) and inside_file(folder, npz) and
            match_file(png, frame['PNG_sha256'], frame['PNG_bytes']) and match_file(npz, frame['NPZ_sha256'], frame['NPZ_bytes']))
        if not row['checks']['original_archive_hash_and_size']:
            continue
        png_raw = png.read_bytes()
        with np.load(npz, allow_pickle=False) as arrays:
            color, owners, triangles = arrays['color'], arrays['owners'], arrays['triangle_ids']
            offsets = arrays['face_patch_offsets'].tolist()
            mask = arrays['display_object_mask'].tolist()
        with Image.open(io.BytesIO(png_raw)) as image:
            shape = tuple(reversed(frame['size_px']))
            row['checks']['PNG_rgb_equals_retained_color'] = (image.format == 'PNG' and list(image.size) == frame['size_px'] and
                color.shape == (*shape, 3) and color.dtype == np.dtype('uint8') and np.array_equal(np.asarray(image.convert('RGB')), color))
        row.update(PNG_sha256=frame['PNG_sha256'], NPZ_sha256=frame['NPZ_sha256'], size_px=frame['size_px'],
                   rgb_SHA256=sha(color.tobytes(order='C')), object_owner_SHA256=sha(owners.astype('<i4', copy=False).tobytes(order='C')),
                   source_triangle_owner_SHA256=sha(triangles.astype('<i4', copy=False).tobytes(order='C')),
                   view_matrix=frame['pose']['view_matrix'], projection_matrix=frame['pose']['projection_matrix'],
                   display_object_mask=mask, source_face_offsets=offsets, object_names=frame['object_names'])
        oracle = next((item for item in evidence.get('frames', []) if item.get('frame_ref') == frame['ref']), {})
        row['checks']['source_mapped_owner_oracle'] = bool(oracle and not oracle.get('error') and
            oracle.get('triangle_owner_sha256_le_i32') == row['source_triangle_owner_SHA256'] and
            oracle.get('object_owner_sha256_le_i32') == row['object_owner_SHA256'])
        row['source_and_capture'] = oracle.get('capture')
        delivered, referenced = [], []
        for attempt in wire.get('attempts', []):
            if not attempt['CLI_successful_evidence_observed']:
                continue
            if any(img['sha256'] == frame['PNG_sha256'] for img in attempt['CLI_images']):
                delivered.append(attempt['attempt'])
            response = read(folder / 'owner' / f'tool_{attempt["attempt"]:02d}' / 'RESPONSE.json', {})
            text_blocks = [block['text'] for block in response.get('result', {}).get('content', []) if block['type'] == 'text']
            if frame['ref'] in attempt['CLI_frame_reference_candidates'] or (attempt['successful_evidence'] and
                    any(frame['ref'] in block for block in text_blocks)):
                referenced.append(attempt['attempt'])
        row.update(PNG_delivered_attempts=delivered, explicit_frame_reference_attempts=referenced,
                   first_actual_CLI_evidence_attempt=min(delivered + referenced, default=None), stages=frame.get('stages'))
    first = min((frame for frame in frames if frame.get('first_actual_CLI_evidence_attempt') is not None),
                key=lambda frame: frame['first_actual_CLI_evidence_attempt'], default=None)
    return {'first_constructed_SCENE': frames[0]['frame_ref'] if frames else None,
            'first_consumer_bound_SCENE': first, 'all_SCENE_archives': frames}


def lifecycle(folder, result, publication, sealed, consumer, settings, wire, device, usage, turn_times, freeze_sha, prompt):
    runtime = read(folder / 'RUNTIME_CLOSE.json', {})
    owner = read(folder / 'owner/CLOSE.json', {})
    startup = read(folder / 'RUNTIME_READY.json', {})
    native = runtime.get('Blender_close', {})
    native_exit = runtime.get('Blender_exit', {})
    native_proof = read(folder / 'NATIVE_RUNTIME_PROOF.json', {})
    worker = runtime.get('Blender_status', {}).get('closed') or {}
    product = runtime.get('public_MCP_close', {})
    product_exit = runtime.get('public_MCP_exit', {})
    product_proof = read(folder / 'MCP_RUNTIME_PROOF.json', {})
    thin_binding = read(folder / 'consumer/RUNTIME_BINDING.json', {})
    consumer_started = read(folder / 'consumer/CONSUMER_STARTED.json', {})
    thin = consumer.get('bridge_cleanup') or {}
    thin_exit = consumer.get('runtime_exit') or {}
    terminal = device.get('terminal_source') or {}
    seal_path = Path(sealed['path']) if sealed.get('path') else None
    original_final = folder / 'consumer/PUBLIC_FINAL.txt'
    answer = result.get('answer') or {}
    answer_bound = (bool(match_file(seal_path, sealed['sha256'], sealed['bytes']) and
        match_file(original_final, sealed['sha256'], sealed['bytes']) and
        answer.get('sha256') == sealed['sha256'] and answer.get('bytes') == sealed['bytes'])
        if seal_path else not original_final.is_file() and not answer)
    clocks = select(result, ('started_ns', 'ready_ns', 'consumer_returned_ns', 'task_deadline_ns', 'owned_deadline_ns', 'closed_ns'))
    clocks.update(select(consumer, ('popen_ns', 'prompt_write_started_ns', 'prompt_submitted_ns', 'final_received_ns',
                                    'turn_completed_ns', 'process_exit_ns', 'cleanup_end_ns')))
    clocks.update(slot_publication_ns=publication.get('published_ns'),
                  first_successful_evidence_ns=wire.get('first_successful_CLI_evidence_ns'),
                  first_observed_CLI_evidence_ns=wire.get('first_observed_CLI_evidence_ns'),
                  last_CLI_tool_result_ns=wire.get('last_bound_CLI_tool_result_ns'),
                  terminal_export_started_ns=(terminal.get('parent_read') or {}).get('started_ns'),
                  terminal_export_ended_ns=(terminal.get('parent_read') or {}).get('closed_ns'),
                  runtime_close_started_ns=runtime.get('started_ns'), runtime_close_ended_ns=runtime.get('closed_ns'),
                  owner_close_ended_ns=owner.get('closed_ns'))
    begin, end = clocks['started_ns'], clocks['slot_publication_ns']
    task_deadline, owned_deadline = clocks['task_deadline_ns'], clocks['owned_deadline_ns']
    final = clocks['final_received_ns']
    spans = {
        'slot_start_to_answer_ns': elapsed(begin, final),
        'slot_start_to_model_popen_ns': elapsed(begin, clocks['popen_ns']),
        'full_owned_window_through_publication_ns': elapsed(begin, end),
        'prompt_to_answer_ns': elapsed(clocks['prompt_submitted_ns'], final),
        'first_successful_evidence_to_answer_ns': elapsed(clocks['first_successful_evidence_ns'], final),
        'first_observed_CLI_evidence_to_answer_ns': elapsed(clocks['first_observed_CLI_evidence_ns'], final),
        'last_CLI_tool_result_to_answer_ns': elapsed(clocks['last_CLI_tool_result_ns'], final),
        'answer_to_publication_ns': elapsed(final, end),
        'terminal_export_ns': elapsed(clocks['terminal_export_started_ns'], clocks['terminal_export_ended_ns']),
        'runtime_close_ns': elapsed(clocks['runtime_close_started_ns'], clocks['runtime_close_ended_ns']),
    }
    original_prefix = ('started_ns', 'task_deadline_ns', 'owned_deadline_ns')
    start_receipt = read(folder / 'SLOT_STARTED.json', {})
    terminal_worker = terminal.get('worker') or {}
    terminal_path = Path(terminal['worker_path']) if terminal.get('worker_path') else None
    terminal_ok = bool(terminal_path and inside_file(folder, terminal_path) and
        match_file(terminal_path, terminal.get('sha256'), terminal.get('bytes')) and
        match_file(folder / 'TERMINAL_SOURCE.json', terminal.get('sha256'), terminal.get('bytes')) and
        result.get('terminal_source') == terminal and terminal.get('status') == 'complete' and
        (terminal_worker.get('sha256'), terminal_worker.get('bytes'), terminal_worker.get('pid')) ==
        (terminal.get('sha256'), terminal.get('bytes'), startup.get('native_pid')))
    args = settings.get('requested_cli_overrides_and_argv') or []
    configured = [settings.get('requested_model'), settings.get('requested_effort'), settings.get('requested_service_tier')]
    started_cli = bool(consumer.get('popen_ns') or consumer_started.get('consumer_pid'))
    prompt_hash = file_sha(prompt)
    envelope = read(folder / 'CONSUMER_ENVELOPE.json', {})
    usage_verified = bool(usage) and usage == consumer.get('raw_usage_events') == result.get('consumer', {}).get('raw_usage_events')
    final_bytes = consumer.get('output_text_bytes')
    return {
        'clocks_ns': clocks, 'spans_ns': spans, 'answer': select(sealed, ('status', 'bytes', 'sha256')),
        'actual_model_admitted': result.get('actual_model_admitted'), 'CLI_started': started_cli,
        'Blender_PID': startup.get('native_pid'), 'CLI_PID': consumer.get('consumer_pid', consumer_started.get('consumer_pid')),
        'thin_stdio_PID': thin_binding.get('runtime_pid'), 'installed_product_PID': startup.get('product_PID'),
        'fresh_thread_id': consumer.get('thread_id'), 'requested_CLI_profile': [PROFILE[0], *configured] if args else None,
        'actual_model_metadata': settings.get('actual_meta'), 'fallback_observation': settings.get('fallback_state'),
        'fallback_diagnostic_count': len(settings.get('fallback_diagnostics', [])),
        'raw_usage_events': usage, 'raw_usage_receipt_events': consumer.get('raw_usage_events'),
        'usage_turn_completed_ns': turn_times, 'usage_semantics': consumer.get('usage_semantics'),
        'provider_retry_observations': len(consumer.get('provider_retry_observations', [])),
        'prompt_UTF8_bytes': consumer.get('input_text_bytes'), 'public_answer_UTF8_bytes': final_bytes,
        'CLI_stdout_bytes': size(folder / 'consumer/stdout.raw.bin'), 'CLI_stderr_bytes': size(folder / 'consumer/stderr.raw.bin'),
        'consumer_archive_bytes': size(folder / 'consumer.raw.zip'),
        'Blender_closure': select(native, ('exit_code', 'process_reaped', 'source_file_unchanged', 'protected_files_unchanged')),
        'Blender_handle_result': select(native_exit, ('exited', 'handle_closed', 'exit_code')),
        'Blender_worker_final_state': select(worker, ('display_restored', 'poisoned', 'initial_geometry_fingerprint',
                                                    'final_geometry_fingerprint', 'product_setters')),
        'CLI_cleanup': select(consumer, ('process_reaped', 'readers_stopped', 'exit_code', 'deadline_timer_fired')),
        'thin_stdio_cleanup': select(thin, ('confirmed', 'receipt_status', 'missing_exit_count')),
        'thin_stdio_handle_result': select(thin_exit, ('confirmed', 'exited', 'handle_closed', 'exit_code', 'elapsed_ns')),
        'product_cleanup': select(product, ('confirmed', 'exit_code', 'elapsed_ns', 'forced_kill', 'pipes_closed')),
        'product_handle_result': select(product_exit, ('exited', 'handle_closed', 'exit_code')),
        'terminal_source': terminal or None,
        'checks': {
            'publication_and_answer_seal': bool(sealed) and answer_bound and publication.get('slot') == result.get('slot') == sealed.get('slot') and
                publication.get('status') == result.get('status') == sealed.get('status') and publication.get('published_ns') == sealed.get('published_ns') and
                publication.get('result_sha256') == file_sha(folder / 'SLOT_RESULT.json') == sealed.get('slot_result_sha256'),
            'single_shared_freeze': result.get('freeze_sha256') == freeze_sha,
            'original_deadlines_and_publication': bool(start_receipt and select(start_receipt, original_prefix) == select(result, original_prefix) and
                publication.get('started_ns') == begin and elapsed(begin, task_deadline) == 450_000_000_000 and
                elapsed(begin, owned_deadline) == 600_000_000_000 and clock_order(begin, clocks['closed_ns'], end, owned_deadline)),
            'fresh_Blender_PID': bool(native_proof.get('confirmed') and startup.get('native_pid') == native_proof.get('runtime_pid')),
            'fresh_terminal_source': terminal_ok,
            'owned_Blender_cleanup': bool(native.get('exit_code') == 0 and native.get('process_reaped') and
                native.get('source_file_unchanged') and native.get('protected_files_unchanged') and native_exit.get('exited') and
                native_exit.get('handle_closed') and worker.get('display_restored') and worker.get('poisoned') is False and
                worker.get('initial_geometry_fingerprint') is not None and
                worker.get('initial_geometry_fingerprint') == worker.get('final_geometry_fingerprint')),
            'owner_listener_closed': owner.get('confirmed') if owner else None,
            'installed_public_MCP_cleanup': (bool(product.get('confirmed') and product_exit.get('exited') and
                product_exit.get('handle_closed') and product_proof.get('confirmed') and
                startup.get('product_PID') == product_proof.get('runtime_pid')) if result.get('group') == 'P' else None),
            'CLI_profile_and_fresh_thread': bool(args and PROFILE[0] in str(args[0]) and configured == PROFILE[1:] and args[1] == 'exec' and
                '--ephemeral' in args and '--ignore-user-config' in args and args[-1] == '-' and
                not set(args).intersection({'resume', 'fork', '--last', '--all'}) and consumer.get('expected_thread_id') is None and
                consumer.get('thread_id')),
            'identical_common_prompt': (consumer.get('input_sha256') == prompt_hash == envelope.get('prompt_sha256') and
                consumer.get('input_text_bytes') == prompt.stat().st_size),
            'raw_usage_matches_original_turn_events': usage_verified,
            'answer_by_original_deadline': bool(clock_order(begin, clocks['popen_ns'], clocks['prompt_submitted_ns'],
                final, clocks['turn_completed_ns'], clocks['process_exit_ns'], clocks['cleanup_end_ns'], clocks['consumer_returned_ns']) and
                clocks['consumer_returned_ns'] < task_deadline and sealed.get('bytes') == final_bytes),
            'CLI_and_thin_stdio_cleanup': bool(consumer.get('process_reaped') and consumer.get('readers_stopped') and
                thin_exit.get('confirmed') and thin_exit.get('exited') and thin_exit.get('handle_closed') and thin_binding.get('confirmed')),
        },
    }


def capture_audit(folder, device):
    native_wire = read(folder / 'native/WIRE/INDEX.json', [])
    native_wire_bound = []
    for row in native_wire:
        base = folder / 'native/WIRE' / f'{row["sequence"]:03d}'
        native_wire_bound.append({**row, 'wire_sizes_verified':
            size(base / 'REQUEST.bin') == row['request_bytes'] and size(base / 'RESPONSE.bin') == row['response_attempted_bytes']})
    workers = lines(folder / 'native/WORKER_EVENTS.jsonl')
    captures = [{key: row.get(key) for key in ('status', 'source_ref', 'terminal', 'bytes', 'sha256', 'parent_read', 'worker')}
                 for row in device.get('sources', [])]
    events = device.get('events', [])
    native_calls = lines(folder / 'NATIVE_CALLS.jsonl')
    return {'native_device_captures': captures, 'device_stage_and_cache_events': events,
            'device_event_counts': dict(Counter(row['event'] for row in events)),
            'native_raster_attempts': sum(row['event'] == 'native_raster_attempt' for row in events),
            'native_work': [select(row, ('sequence', 'status', 'started_ns', 'elapsed_ns', 'stdout_bytes', 'stderr_bytes',
                                        'm2_work', 'render_events_before', 'render_events_after')) for row in workers],
            'operator_render_counter_unchanged': all(row.get('render_events_before') == row['render_events_after']
                for row in workers if 'render_events_after' in row) if workers else None,
            'native_calls': [select(row, ('index', 'terminal', 'trusted', 'code_bytes', 'code_sha256', 'response_bytes',
                                          'started_ns', 'closed_ns')) | {'error_recorded': bool(row.get('error'))} for row in native_calls],
            'native_Blender_wire': native_wire_bound,
            'native_Blender_TX_bytes': sum(row['request_bytes'] for row in native_wire_bound),
            'native_Blender_RX_attempted_bytes': sum(row['response_attempted_bytes'] for row in native_wire_bound),
            'native_Blender_RX_confirmed_bytes': sum(row['response_attempted_bytes'] for row in native_wire_bound if row['response_sendall_completed'])}


def budget_audit(folder, slots, results):
    limits = read(folder / 'LIMITS.json', {})
    claims = {path.stem: (path, read(path)) for path in (folder / 'claims').glob('*.json')}
    settlements = {path.stem: read(path) for path in (folder / 'settlements').glob('*.json')}
    kinds = {'Blender_start', 'consumer_task', 'business_tool', 'raster_attempt'}
    by_slot = {label: {'Blender_start_attempts': 0, 'Blender_spawned': 0, 'consumer_admissions': 0,
                       'business_admissions': 0, 'raster_actual_lower_bound': 0, 'raster_reserved_upper_bound': 0,
                       'unknown_raster_settlements': 0} for label in SLOTS}
    errors, records = [], []
    for token, (path, claim) in sorted(claims.items()):
        settlement = settlements.get(token)
        label, kind = claim['label'], claim['kind']
        records.append({'claim': claim, 'settlement': settlement})
        if label not in by_slot or kind not in kinds or claim['phase'] != 'formal' or claim['token'] != token or claim['reserved_upper_bound'] != 1:
            errors.append({'token': token, 'reason': 'out_of_scope_claim'})
            continue
        summary = by_slot[label]
        if settlement and (settlement.get('claim_sha256') != file_sha(path) or settlement.get('token') != token or
                           not clock_order(claim['claimed_ns'], settlement.get('settled_ns'))):
            errors.append({'token': token, 'reason': 'settlement_not_bound_to_claim'})
        if kind == 'raster_attempt':
            actual = (settlement or {}).get('actual_attempts')
            lower = (settlement or {}).get('confirmed_attempts_lower_bound', 0)
            summary['raster_actual_lower_bound'] += lower if actual is None else actual
            summary['raster_reserved_upper_bound'] += claim['reserved_upper_bound'] if actual is None else actual
            summary['unknown_raster_settlements'] += actual is None
        elif kind == 'Blender_start':
            summary['Blender_start_attempts'] += 1
            summary['Blender_spawned'] += bool(settlement and settlement.get('pid'))
        elif kind == 'consumer_task':
            summary['consumer_admissions'] += 1
        elif kind == 'business_tool':
            summary['business_admissions'] += 1

    expected = {'Blender_start_attempts': 2, 'all_rasters': 8, 'consumer_tasks': 2,
                'tools_per_slot': 12, 'rasters_by_slot': {'N1': 4, 'P1': 4}}
    raw_counts = {key: sum(row[key] for row in by_slot.values()) for key in next(iter(by_slot.values()))}
    final_counts = (results['P1'].get('budget') or {}).get('counts', {})
    snapshots_bound = True
    for label, slot in slots.items():
        work = by_slot[label]
        wire, lifecycle = slot.get('wire', {}), slot.get('lifecycle', {})
        capture, product = slot.get('capture', {}), slot.get('product', {})
        actual = capture.get('native_raster_attempts', 0) + product.get('product_actual_raster_attempts', 0)
        work.update(native_device_rasters=capture.get('native_raster_attempts'), product_device_rasters=product.get('product_actual_raster_attempts'),
                    observed_rasters=actual, wire_business_attempts=wire.get('business_attempts'),
                    CLI_started=lifecycle.get('CLI_started'))
        work['raster_receipts_agree'] = (work['raster_actual_lower_bound'] <= actual <= work['raster_reserved_upper_bound'])
        work['business_admissions_match_owner'] = work['business_admissions'] == wire.get('owner_attempts')
        reported = results[label].get('budget', {}).get('slots', {}).get(label, {})
        snapshots_bound &= (reported.get('business_admissions', 0), reported.get('raster_actual', 0), reported.get('raster_upper', 0)) == (
            work['business_admissions'], work['raster_actual_lower_bound'], work['raster_reserved_upper_bound'])
    snapshots_bound &= all(final_counts.get(name) == raw_counts[total] for name, total in (
        ('Blender_start_attempts', 'Blender_start_attempts'), ('Blender_spawned_confirmed', 'Blender_spawned'),
        ('consumer_admissions', 'consumer_admissions'), ('business_admissions', 'business_admissions'),
        ('all_raster_actual', 'raster_actual_lower_bound'), ('all_raster_upper', 'raster_reserved_upper_bound')))
    return {'limits': limits, 'cumulative_counts': raw_counts, 'slots': by_slot, 'records': records,
            'violations': errors, 'orphan_settlements': sorted(set(settlements) - set(claims)),
            'checks': {'original_limits_verified': limits == expected, 'published_budget_snapshots_agree': snapshots_bound,
                'within_original_limits': limits == expected and raw_counts['Blender_start_attempts'] <= expected['Blender_start_attempts'] and
                    raw_counts['consumer_admissions'] <= expected['consumer_tasks'] and raw_counts['raster_reserved_upper_bound'] <= expected['all_rasters'] and
                    all(row['raster_reserved_upper_bound'] <= 4 and row['business_admissions'] <= 12 and
                        row['Blender_start_attempts'] <= 1 and row['consumer_admissions'] <= 1 for row in by_slot.values()),
                'all_formal_claims_and_settlements_bound': not errors and not (set(settlements) - set(claims)),
                'qualification_Blender_or_raster_claims': sum(claim['phase'] == 'qualification' for _, claim in claims.values())}}


def pair_frames(slots, evidence):
    native, product = [slots[label].get('frame', {}).get('first_consumer_bound_SCENE') for label in SLOTS]
    retained = [slots[label].get('frame', {}).get('first_constructed_SCENE') for label in SLOTS]
    checks = {'scoring_first_frame_same_device': evidence.get('same_device_pair_eligible'),
              'first_consumer_bound_frames_exist': bool(native and product)}
    if native and product:
        for key in ('rgb_SHA256', 'size_px', 'object_owner_SHA256', 'source_triangle_owner_SHA256', 'view_matrix',
                    'projection_matrix', 'display_object_mask', 'source_face_offsets', 'object_names'):
            # Geometry and owner namespaces have already been checked separately against both fresh source captures.
            checks['identical_' + key] = native[key] == product[key]
        checks['expected_native_and_product_origins'] = [native['origin'], product['origin']] == ['common_native', 'product']
        checks['each_retained_frame_is_verified'] = all(all(frame['checks'].values()) for frame in (native, product))
        checks['first_constructed_frames_used'] = [native['frame_ref'], product['frame_ref']] == retained
        checks['P_first_product_PNG_delivered'] = 1 in product['PNG_delivered_attempts']
    return {'checks': checks, 'paired_same_device_consumer_SCENE_frames': all(check is True for check in checks.values())}


def main():
    began = time.perf_counter_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', type=Path, default=NS)
    parser.add_argument('--external', type=Path, default=EXTERNAL)
    parser.add_argument('--freeze', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    namespace, external = args.namespace, args.external
    freeze_path = args.freeze or namespace / 'FROZEN.json'
    output = args.output or namespace / 'checks/RUNTIME_REVIEW.json'
    specs = read(freeze_path)
    binding = read(namespace / 'PRODUCT_RUN_BINDING.json')
    preflight_path = namespace / 'STARTUP_PREFLIGHT.json'
    preflight = read(preflight_path, {})
    seal_path, evidence_path = namespace / 'ANSWERS_SEALED.json', namespace / 'scoring/EVIDENCE_VERDICT.json'
    seal, evidence = read(seal_path), read(evidence_path)
    if not seal or not evidence or [row['slot'] for row in seal['answers']] != list(SLOTS):
        raise ValueError('The paired seal and score evidence must exist before runtime audit')
    folders = {label: external / 'slots' / label for label in SLOTS}
    results = {label: read(folder / 'SLOT_RESULT.json', {}) for label, folder in folders.items()}
    publications = {label: read(folder / 'SLOT_PUBLICATION.json', {}) for label, folder in folders.items()}
    if not all(publications.values()):
        raise ValueError('Both original slot publications must exist before runtime audit')
    sys.path[:0] = [binding['dependency_root'], specs['shared_dependency_root']]
    freeze_sha = file_sha(freeze_path)
    prompt = namespace / 'inputs/PROMPT.txt'
    selection = read(namespace / 'inputs/REGION.json')
    slots = {}
    for sealed in seal['answers']:
        label = sealed['slot']
        folder, result, published = folders[label], results[label], publications[label]
        slot = {'status': result.get('status'), 'audit_errors': {},
                'slot_errors': [select(error, ('stage', 'type')) for error in result.get('errors', [])]}
        slots[label] = slot
        report_sections(slot, {'wire_data': lambda: cli_events(folder)})
        events, usage, turn_times = slot.pop('wire_data', ([], [], []))
        consumer = read(folder / 'consumer/CONSUMER.json', {})
        settings = read(folder / 'consumer/ACTUAL_CONFIGURATION.json', {})
        device = read(folder / 'DEVICE_EVIDENCE.json', {})
        report_sections(slot, {'wire': lambda: wire_audit(folder, consumer, events),
                               'capture': lambda: capture_audit(folder, device)})
        wire = slot.get('wire', {})
        report_sections(slot, {
            'lifecycle': lambda: lifecycle(folder, result, published, sealed, consumer, settings, wire, device,
                                           usage, turn_times, freeze_sha, prompt),
            'frame': lambda: frame_audit(folder, device, wire, evidence.get('slots', {}).get(label, {})),
        })
        if label == 'P1':
            report_sections(slot, {'product': lambda: product_audit(folder, wire, selection, binding['source_sha256'])})
    pinned_changes = [row['path'] for row in specs['direct_inputs'] if not match_file(Path(row['path']), row['sha256'], row['bytes'])]
    lifecycles = [slots[label].get('lifecycle', {}) for label in SLOTS]
    threads = [row.get('fresh_thread_id') for row in lifecycles]
    frames = pair_frames(slots, evidence)
    report = {
        'schema': 'm4-live-source-region-task-002-runtime-review-v1', 'slots': slots,
        'audit_errors': {}, 'frame_comparison': frames,
        'checks': {
            'strict_serial_original_owned_windows': clock_order(results['N1'].get('started_ns'), publications['N1'].get('published_ns'),
                                                                 results['P1'].get('started_ns'), publications['P1'].get('published_ns')),
            'both_slots_used_same_final_freeze': specs.get('applies_to') == list(SLOTS) and
                all(results[label].get('freeze_sha256') == freeze_sha for label in SLOTS),
            'final_frozen_inputs_unchanged': not pinned_changes,
            'both_dependency_preflights_passed': preflight.get('passed') is True and
                [row['slot'] for row in preflight.get('slots', [])] == list(SLOTS),
            'distinct_fresh_cli_threads': all(threads) and len(set(threads)) == len(SLOTS),
            'answers_sealed_before_evidence_scoring': seal['sealed_ns'] >= max(row['published_ns'] for row in publications.values()) and
                evidence.get('seal_sha256') == file_sha(seal_path),
        },
        'common_bindings': {'final_freeze_sha256': freeze_sha, 'current_frozen_input_changes': pinned_changes,
            'common_prompt_sha256': file_sha(prompt), 'preflight_sha256': file_sha(preflight_path) if preflight else None,
            'evidence_verdict_sha256': file_sha(evidence_path), 'answer_seal_sha256': file_sha(seal_path)},
        'unmeasured': {'provider_requests': None, 'cash_fees': None, 'image_tokens': None, 'reasoning_content': None},
        'cost_scope': ('Raw usage events preserve the reported scope. Execution stages can overlap, and the complete slot window '
                       'includes owner closure, terminal source export, process cleanup and slot publication. Wire payload sizes '
                       'and CLI-emitted result sizes are distinct measurements.'),
    }
    report_sections(report, {'budget': lambda: budget_audit(external / 'budget', slots, results)})
    report['audit_started_ns'] = began
    report['audit_finished_ns'] = time.perf_counter_ns()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'slots': {label: row['status'] for label, row in slots.items()},
                      'paired_SCENE_frames': frames['paired_same_device_consumer_SCENE_frames'],
                      'P_first_default_v2_delivered': slots['P1'].get('product', {}).get('first_default_v2_delivered'),
                      'audit_errors': {label: row['audit_errors'] for label, row in slots.items()}}))


if __name__ == '__main__':
    main()
