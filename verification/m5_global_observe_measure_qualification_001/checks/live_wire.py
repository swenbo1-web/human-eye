"""Check raw synchronous transport and replay the fixed two-stage Codex output policy."""

import base64
import json
from pathlib import Path
import re
import runpy
import zipfile

from live_observation import read, require, digest, verified


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
POLICY_PATH = V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'
POLICY = runpy.run_path(str(POLICY_PATH))
HELPERS, LIMITS = POLICY['budget_helpers']()
MEASURE_LOSS_ROOTS = {'binding', 'unit', 'coordinate_frame', 'pair_order', 'facts', 'execution_authority'}
OBSERVATION_LOSS_ROOTS = {'binding', 'objects', 'scopes', 'region_task', 'pixel_requirements', 'frames',
                          'witnesses', 'pixel_shortfalls', 'blocker_evidence', 'task_result'}


def json_lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def elapsed(start, end):
    require(type(start) is int and type(end) is int and start <= end, 'out_of_order_measured_clocks')
    return (end - start) / 1e6


def raw_wire(slot, event, meter, expected, archive_reader=None):
    receipt, request = event['receipt'], event['request']
    ordinal = event.get('index', event.get('internal_public_call_index'))
    ident = request['id']
    require(request['method'] == 'tools/call' and request['params'] == {
            'name': 'human_eye_scene_observe', 'arguments': expected} and
            ident == receipt['id'] == meter['id'] == meter['response_id'] and receipt['error'] is None,
            'public_request_or_meter_not_bound_to_exact_registered_call')
    rpc = slot / 'mcp' / f"rpc_{receipt['index']:02d}"
    call = slot / 'product_calls' / f'call_{ordinal:03d}'
    tx_path, rx_path = rpc / 'TX.bin', rpc / 'RX.bin'
    tx, rx = tx_path.read_bytes(), rx_path.read_bytes()
    parsed = json.loads(rx)
    normalized = rx.replace(b'\r\n', b'\n')
    require(digest(tx) == meter['TX_sha256'] and len(tx) == meter['TX_bytes'] == receipt['TX_bytes']
            and json.loads(tx) == request == read(call / 'REQUEST.json')
            and digest(rx) == receipt['RX_sha256'] and len(rx) == receipt['RX_bytes']
            and digest(normalized) == meter['RX_text_UTF8_LF_sha256']
            and len(normalized) == meter['RX_text_UTF8_LF_bytes']
            and read(rpc / 'RECEIPT.json') == receipt
            and parsed == event['response'] == read(call / 'RESPONSE.json')
            and parsed['id'] == ident and parsed['result']['isError'] is False
            and meter['raster_actual'] == (3 if expected.get('include_image') else 0),
            'raw_client_and_server_wires_or_raster_accounting_mismatch')
    record = event['producer_archive']
    producer_path = Path(record['path'])
    require(producer_path.resolve() == (slot / 'product_full' / f"call_{record['index']:03d}" /
            'SERVICE_RESULT.json').resolve() and record['new_observations_for_archive'] == 0
            and (event.get('producer_archive_index') or ordinal) == record['index'], 'producer_cross_request_path')
    producer_raw = verified(producer_path, record['sha256'], slot)
    context_path = Path(record['read_context']).resolve()
    require(context_path.is_relative_to(producer_path.parent.resolve()), 'context_cross_request_path')
    context = read(context_path)
    paths = [tx_path, rx_path, producer_path, context_path, call / 'REQUEST.json', call / 'RESPONSE.json', rpc / 'RECEIPT.json']
    before_path, after_path = (call / 'ARCHIVE_BEFORE.bin', call / 'ARCHIVE_AFTER.bin')
    if before_path.is_file() or after_path.is_file():
        before, after = before_path.read_bytes(), after_path.read_bytes()
        require(after.startswith(before) and len(after.splitlines()) == len(before.splitlines()) + 1
                and json.loads(after.splitlines()[-1]) == record, 'single_synchronous_producer_archive_append_not_proven')
        paths.extend([before_path, after_path])
    if archive_reader:
        for path in paths:
            archive_reader(path)
    producer = json.loads(producer_raw)
    render_stages = {name: elapsed(value['started_ns'], value['closed_ns'])
                    for name, value in producer.get('stages', {}).items()}
    started, closed = event['started_ns'], event['closed_ns']
    require(started <= meter['request_received_ns'] <= record['producer_returned_ns']
            <= meter['reply_completed_ns'] <= closed, 'producer_not_inside_actual_mcp_rpc')
    body, *images = parsed['result']['content']
    return {'result': parsed['result'], 'producer': producer, 'context': context, 'paths': paths,
            'wire': {'TX_bytes': len(tx), 'RX_bytes': len(rx), 'TX_sha256': digest(tx), 'RX_sha256': digest(rx),
                     'body_UTF8_bytes': len(body['text'].encode()), 'PNG_bytes': sum(len(base64.b64decode(item['data']))
                        for item in images if item['type'] == 'image'), 'producer_sha256': record['sha256']},
            'timing': {'request_window_ms': elapsed(started, closed),
                       'server_rpc_ms': elapsed(meter['request_received_ns'], meter['reply_completed_ns']),
                       'client_rpc_ms': elapsed(receipt['started_ns'], receipt['closed_ns']),
                       'producer_stages_ms': render_stages}}


def leaves(text):
    """Map compact JSON leaf values to exact character spans to audit a middle cut."""
    decoder = json.JSONDecoder()

    def no_space(idx):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        return idx

    def visit(idx, path):
        idx = no_space(idx)
        char = text[idx]
        if char in '{[':
            stop, mapping = ('}', True) if char == '{' else (']', False)
            idx, number = no_space(idx + 1), 0
            if text[idx] == stop:
                yield path, (idx - 1, idx + 1)
                return idx + 1
            while True:
                if mapping:
                    key, idx = decoder.raw_decode(text, idx)
                    idx = no_space(idx)
                    require(text[idx] == ':', 'expected_JSON_path_separator')
                    idx += 1
                else:
                    key = number
                idx = no_space((yield from visit(idx, (*path, key))))
                if text[idx] == stop:
                    return idx + 1
                require(text[idx] == ',', 'expected_JSON_collection_separator')
                idx, number = no_space(idx + 1), number + 1
        _, end = decoder.raw_decode(text, idx)
        yield path, (idx, end)
        return end

    return dict(visit(0, ()))


TRUNCATED = re.compile(r'…\d+ (?:chars|tokens) truncated…')


def omitted_paths(full, retained):
    """Determine exact lost stable value tokens for the known middle-cut policy."""
    if full == retained:
        return []
    spans = leaves(full)
    match = TRUNCATED.search(retained)
    if match:
        prefix, suffix = retained[:match.start()], retained[match.end():]
        if full.startswith(prefix) and full.endswith(suffix):
            cut_left, cut_right = len(prefix), len(full) - len(suffix)
            return [path for path, (start, end) in spans.items() if start < cut_right and end > cut_left]
    return list(spans)


def image_hashes(items):
    found = []
    for item in items:
        if item['type'] == 'input_image':
            prefix, payload = item['image_url'].split(',', 1)
            require(prefix == 'data:image/png;base64', 'unexpected_CLI_image_encoding')
            found.append(digest(base64.b64decode(payload, validate=True)))
    return found


def cli_replay(result, output, label, *, note_only=False):
    require((LIMITS['MCP_bytes'], LIMITS['history_approximate_tokens']) == (12000, 3000),
            'fixed_original_CLI_budget_changed')
    text, = [item['text'] for item in result['content'] if item.get('type') == 'text']
    stages = []
    output.mkdir(parents=True, exist_ok=True)
    for seconds, header in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        original = HELPERS['model_items'](result, seconds)
        require(len(original[0]['text'].encode()) == header, 'fixed_CLI_header_shape_changed')
        mcp = HELPERS['truncate_items'](original, LIMITS['MCP_bytes'])
        history = HELPERS['truncate_items'](mcp, LIMITS['history_approximate_tokens'], token_mode=True)
        original_images = image_hashes(original)
        row = {'sample_seconds': seconds, 'header_bytes': header}
        for name, items in (('MCP', mcp), ('history', history)):
            words = [item['text'] for item in items if item['type'] == 'input_text']
            retained = words[1] if len(words) > 1 else ''
            same = original == items
            lost = omitted_paths(text, retained) if retained != text and not note_only else []
            roots = MEASURE_LOSS_ROOTS if label == 'measure' else OBSERVATION_LOSS_ROOTS
            png = image_hashes(items)
            record = {'text_items': words, 'PNG_sha256': png}
            path = output / f'{seconds}_{name}.json'
            evidence = json.dumps(record, ensure_ascii=False, indent=2).encode() + b'\n'
            path.write_bytes(evidence)
            row[name] = {'exact': same, 'PNG_exact': png == original_images, 'PNG_sha256': png,
                         'body_UTF8_bytes': len(retained.encode()), 'replay_sha256': digest(evidence),
                         'lost_value_count': len(lost), 'lost_critical_paths': [list(path) for path in lost if path[0] in roots],
                         'truncation_detected': retained != text}
        stages.append(row)
    return {'passed': all(stage[name]['exact'] for stage in stages for name in ('MCP', 'history')),
            'body_UTF8_bytes': len(text.encode()), 'limits': LIMITS, 'stages': stages,
            'actual_model_or_provider_input': None}


def frozen_archive(index, run, expected):
    index = read(index)
    raw_path = Path(index['archive']['path'])
    require(raw_path.resolve() == (run / 'ORIGINAL_RUNTIME.zip').resolve()
            and digest(raw_path.read_bytes()) == index['archive']['sha256'] == expected, 'reference_archive_drift')
    pins = {row['path']: row for row in index['files']}
    require(len(pins) == index['count'], 'reference_archive_duplicate_members')
    result = {}

    def archive_reader(path):
        path = Path(path).resolve()
        key = path.relative_to(run.resolve()).as_posix()
        pin = pins[key]
        raw = verified(path, pin['sha256'], run)
        with zipfile.ZipFile(raw_path) as package:
            require(raw == package.read(key), 'reference_disk_bytes_differ_from_archived_member/' + key)
        require(len(raw) == pin['bytes'], 'reference_member_size_changed/' + key)
        result[str(path)] = {'path': str(path), 'sha256': pin['sha256'], 'bytes': len(raw)}
        return raw

    return archive_reader, result
