"""Send the same request twice through the real direct product bridge."""

from copy import deepcopy
import json
import time
from types import FunctionType

from common import ORDER, PILOT, PRODUCT_SCHEMA, REQUEST, SEAL, SLOTS, arguments, load_retained, read, save, sha


bridge = load_retained('_m4_active_view_pilot_bridge', PILOT / 'harness/bridge.py')
driver = load_retained('_m4_active_view_original_tcp_driver', SEAL / 'harness/qual_driver.py')


def outer_message(label, kind='cold'):
    if label not in ORDER or kind not in ('cold', 'hot'):
        raise ValueError('registered_source_region_slot_and_step_required')
    return {'jsonrpc': '2.0', 'id': 'source-region-' + kind, 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe', 'arguments': deepcopy(arguments())}}


def rpc(endpoint, message, directory, deadline, attempt=None):
    if attempt is None:
        return driver.rpc(endpoint, message, directory, deadline)

    def encode_attempt(envelope):
        return driver.encoded({**envelope, 'args': {**envelope['args'], 'attempt': attempt}})

    through_owner = FunctionType(driver.rpc.__code__, dict(driver.rpc.__globals__, encoded=encode_attempt))
    return through_owner(endpoint, message, directory, deadline)


def owner_for(runtime, label, folder, deadline):
    group, phase = SLOTS[label]
    return bridge.Owner(runtime, {'group': group, 'label': label, 'phase': phase,
        'worker_deadline_ns': deadline, 'output': str(folder / 'owner')}, budget=runtime.budget)


def match(original, public):
    outer = original['response']
    inner = public.get('response') or {}
    if (outer.get('result') != inner.get('result') or outer.get('error') != inner.get('error')
            or outer.get('result', {}).get('isError') is not False):
        raise ValueError('direct_source_region_tool_did_not_preserve_successful_original_reply')
    if len(original['images']) != 1:
        raise ValueError('source_region_public_contract_requires_one_actual_PNG_per_request')
    body = json.loads(outer['result']['content'][0]['text'])
    return {key: body[key] for key in ('binding', 'region_ref', 'visibility', 'observation_status')}


def execute(owner, label, folder, endpoint, deadline):
    root = folder / 'batch'
    root.mkdir()
    opening = driver.rpc(endpoint, {'jsonrpc': '2.0', 'id': 'active-view-initialize', 'method': 'initialize',
        'params': {'protocolVersion': '2025-03-26', 'capabilities': {}}}, root / 'rpc_01', deadline)
    tools = driver.rpc(endpoint, {'jsonrpc': '2.0', 'id': 'active-view-tools', 'method': 'tools/list'},
                       root / 'rpc_02', deadline)
    actual = tools['response']['result']['tools']
    registered = [row for row in actual if row['name'] == 'human_eye_scene_observe']
    if registered != [read(PRODUCT_SCHEMA)] or opening['response']['result']['protocolVersion'] != '2025-03-26':
        raise ValueError('direct_source_region_wrapper_handshake_incomplete')
    calls = []
    first_identity = None
    for index, kind in enumerate(('cold', 'hot'), 3):
        row = {'kind': kind, 'started_ns': time.perf_counter_ns(), 'original_request_sha256': sha(REQUEST)}
        owner.runtime.business_calls.append(row)
        step = root / f'rpc_{index:02d}'
        counts = owner.runtime.budget.snapshot()['slots'].get(label, {})
        try:
            reply = rpc(endpoint, outer_message(label, kind), step, deadline, attempt=index - 2)
            public = owner.runtime.public_requests
            if len(public) != index - 2:
                raise ValueError('each_outer_request_must_yield_one_public_request')
            identity = match(reply, public[-1])
            after = owner.runtime.budget.snapshot()['slots'][label]
            rasters = after['raster_actual'] - counts.get('raster_actual', 0)
            entry = {'kind': kind, 'actual_new_raster_attempts': rasters, 'public_id': public[-1]['id'],
                     'receipt_path': str(step / 'RECEIPT.json'), 'images': reply['images'],
                     **{k: reply[k] for k in ('started_ns', 'received_complete_ns', 'closed_ns',
                      'client_socket_ns', 'TX_bytes', 'RX_bytes', 'TX_sha256', 'RX_sha256')}}
            calls.append(entry)
            if kind == 'cold':
                first_identity = identity
            elif (rasters != 0 or identity != first_identity
                    or entry['images'][0]['sha256'] != calls[0]['images'][0]['sha256']):
                raise ValueError('hot_source_region_built_or_changed_its_bound_observation')
            row.update(status='completed', public_id=entry['public_id'], new_raster_attempts=rasters)
        except Exception:
            row['status'] = 'failed'
            raise
        finally:
            row['closed_ns'] = time.perf_counter_ns()
    record = {'outer_business_count': len(calls), 'inner_public_count': len(owner.runtime.public_requests),
              'internal_public_request_ids': [row['public_id'] for row in calls], 'calls': calls,
              'started_ns': calls[0]['started_ns'], 'closed_ns': calls[-1]['closed_ns'],
              'public_request_same_session': True, 'hot_binding_equals_cold': True, 'model_calls': 0}
    save(root / 'QUALIFICATION_BATCH.json', record)
    return record
