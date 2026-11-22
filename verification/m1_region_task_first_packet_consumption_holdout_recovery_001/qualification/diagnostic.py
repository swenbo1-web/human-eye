"""Exercise the same five model-facing calls in both real zero-model slots."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parents[1]
TOOL = 'human_eye_scene_observe'
CONDITIONS = {'area_min_m2': 19 / 4096, 'area_max_m2': 21 / 4096, 'normal_z_min': 0.75}
DISCOVER = {'query': {'mode': 'active_observation', 'region_task': CONDITIONS}, 'include_image': True}
MEASURE = {'query': {'mode': 'source_region',
                     'region': {'object': {'name': 'Component_417'}, 'source_triangle_indices': [0, 1]},
                     'reference': {'name': 'M4_Far_00'}, 'requested_facts': ['surface_proximity']}, 'include_image': False}
INVALID = {'direction': 'TOP', 'view_span_m': 0}
ORDER = ('render_local', TOOL, 'read_images', TOOL, TOOL)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def body(reply):
    require(reply.get('isError') is False and reply['content'][0]['type'] == 'text',
            'qualification_expected_success/' + str(reply)[:550])
    return json.loads(reply['content'][0]['text'])


def frame_rows(packet, content):
    frames = packet['frames']
    if isinstance(frames, list):
        rows = frames
    else:
        scopes = packet['scopes']
        scope_id = scopes['columns'].index('scope_id')
        rows = [dict(zip(frames['columns'], row, strict=True)) for row in frames['rows']]
        rows = [{**row, 'scope_id': scopes['rows'][row['scope_index']][scope_id]} for row in rows]
    require(len(rows) == sum(block['type'] == 'image' for block in content) and len(rows) >= 3,
            'live_discovery_missing_original_pngs')
    require(len(rows) == len({row['image_ref'] for row in rows}) == len({row['frame_identity'] for row in rows}),
            'ambiguous_discovery_original_image_references')
    same_name = {}
    for row in rows:
        same_name.setdefault(row['view_name'], set()).add(row['scope_id'])
    require(any(len(scopes) > 1 for scopes in same_name.values()), 'same_view_name_across_current_scopes_required')
    return [{'view': row['view_name'], 'scope': row['scope_id'], 'ref': row['image_ref'],
             'frame_identity': row['frame_identity'], 'image_sha256': row['image_sha256']} for row in rows]


def run_calls(call, *, discover=DISCOVER, measure=MEASURE):
    bad = call('render_local', INVALID)
    require(bad.get('isError') is True, 'invalid_common_argument_was_accepted')
    first = call(TOOL, {**discover, 'response_detail': 'full'})
    frames = frame_rows(body(first), first['content'])
    images = call('read_images', {'refs': [row['ref'] for row in frames]})
    require(images.get('isError') is False, 'same_slot_public_image_read_failed/' + str(images)[:550])
    short = call(TOOL, {**discover, 'response_detail': 'brief'})
    require(frame_rows(body(short), short['content']) == frames, 'same_capture_delivery_changed_with_response_detail')
    measured = call(TOOL, measure)
    body(measured)
    return {'passed': False, 'phase': 'public_calls_completed_pending_owned_close', 'frames': frames}


def _run_transport_plan(folder, endpoint, deadline, group, owner, result, *, plan=run_calls):
    from common import save

    root = Path(folder) / 'client'
    transport = run_path(str(NS.parent/'m4_source_region_display_001/harness/reused/stdio_checks.py'))
    client = transport['StdioClient'](
        [sys.executable, '-IB', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
         '--endpoint', str(endpoint), '--audit', str(root / 'attachments')],
        folder, root / 'transport', deadline)

    def call(name, arguments):
        ordinal = len(result['diagnostic_calls']) + 1
        require(ordinal <= len(ORDER) and name == ORDER[ordinal - 1], 'qualification_public_call_order_changed')
        directory = root / f'call_{ordinal:02d}'
        directory.mkdir()
        request = {'jsonrpc': '2.0', 'id': f'qualification-{ordinal}', 'method': 'tools/call',
                   'params': {'name': name, 'arguments': arguments}}
        save(directory / 'REQUEST.json', request)
        row = {'index': ordinal, 'name': name, 'request_sha256': sha256((directory / 'REQUEST.json').read_bytes()).hexdigest(),
               'started_ns': time.perf_counter_ns()}
        result['diagnostic_calls'].append(row)
        response = client.call(request)
        row['returned_ns'] = time.perf_counter_ns()
        save(directory / 'RESPONSE.json', response)
        save(directory / 'RECEIPT.json', client.records[-1])
        row['response_sha256'] = sha256((directory / 'RESPONSE.json').read_bytes()).hexdigest()
        require(isinstance(response.get('result'), dict) and response['id'] == request['id'] and 'error' not in response,
                'qualification_public_RPC_failed/' + name)
        return response['result']

    try:
        init = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
                            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                       'clientInfo': {'name': 'region-task-first-packet-qualification', 'version': '1'}}})
        save(root / 'INITIALIZE.json', init)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = client.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})
        save(root / 'TOOLS.json', tools)
        require(tools['result']['tools'] == owner.tools, 'qualification_actual_catalogue_changed')
        pending = plan(call)
    finally:
        result['diagnostic_close'] = close = client.finish()
        require(close['confirmed'] and close['exit_code'] == 0 and close['process_handle_closed'],
                'qualification_stdio_close_unconfirmed')
    save(Path(folder) / 'QUALIFICATION_PENDING.json', pending)
    result['qualification_pending'] = pending


def run_diagnostic(folder, endpoint, deadline, group, owner, result, *, plan=run_calls):
    require(group == 'P' and result['label'] == 'QB', 'recovery_qualification_only_QB')
    return _run_transport_plan(folder, endpoint, deadline, group, owner, result, plan=plan)
