"""Collect the exact public qualification sequence while its owned tools are online."""

from pathlib import Path
from runpy import run_path
import sys
import time


NS = Path(__file__).resolve().parents[1]
PRIOR = NS.parent / 'perf050_dense_micro_surface_holdout_001/qualification'
PRODUCT = run_path(str(PRIOR / 'product_qa.py'))
TOOL = PRODUCT['TOOL']
INVALID = {'direction': 'TOP', 'view_span_m': 0}


def plan_public_calls(call):
    invalid = call('render_local', INVALID)
    if invalid.get('isError') is not True:
        raise ValueError('invalid_common_argument_was_accepted')
    discovered = call(TOOL, PRODUCT['DISCOVER'])
    body = PRODUCT['body'](discovered)
    decode = run_path(str(NS.parent / 'm4_dense_region_brief_001/checks/brief_schema.py'))['decode_body']
    rows = decode(body, len(discovered['content']))['region_task']['rows']
    by_name = {row['object_name']: row for row in rows}
    images = {}
    for target in ('S021', 'S055'):
        witness = by_name[target]['complete_witness']
        if witness is None or type(witness.get('image_ref')) is not str or not witness['image_ref']:
            raise ValueError('required_live_witness_ref_missing/' + target)
        ref = witness['image_ref']
        delivered = call('read_images', {'refs': [ref]})
        if delivered.get('isError') is not False:
            raise ValueError('same_slot_image_read_failed/' + target)
        images[target] = ref
    if len(set(images.values())) != 2:
        raise ValueError('current_two_local_frame_references_required')
    measured = call(TOOL, PRODUCT['MEASURE'])
    PRODUCT['body'](measured)
    return {'passed': False, 'phase': 'public_calls_completed_pending_owned_close', 'read_refs': images}


def run_diagnostic(folder, endpoint, deadline, group, owner, result):
    from common import save, sha
    from runtime import previous

    if group != 'P':
        raise ValueError('only_product_qualification_may_be_replayed')
    root = folder / 'client'
    client = previous.transport.StdioClient(
        [sys.executable, '-IB', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
         '--endpoint', str(endpoint), '--audit', str(root / 'attachments')],
        folder, root / 'transport', deadline)

    def call(name, arguments):
        ordinal = len(result['diagnostic_calls']) + 1
        directory = root / f'call_{ordinal:02d}'
        directory.mkdir()
        request = {'jsonrpc': '2.0', 'id': f'qualification-{ordinal}', 'method': 'tools/call',
                   'params': {'name': name, 'arguments': arguments}}
        save(directory / 'REQUEST.json', request)
        row = {'index': ordinal, 'name': name, 'request_sha256': sha(directory / 'REQUEST.json'),
               'started_ns': time.perf_counter_ns()}
        result['diagnostic_calls'].append(row)
        response = client.call(request)
        row['returned_ns'] = time.perf_counter_ns()
        save(directory / 'RESPONSE.json', response)
        save(directory / 'RECEIPT.json', client.records[-1])
        row['response_sha256'] = sha(directory / 'RESPONSE.json')
        body = response.get('result')
        if not isinstance(body, dict) or response.get('id') != request['id'] or 'error' in response:
            raise ValueError(f'qualification_RPC_error/{ordinal}/{name}')
        return body

    try:
        init = client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'dense-micro-surface-qualification', 'version': '1'}}})
        save(root / 'INITIALIZE.json', init)
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = client.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})
        save(root / 'TOOLS.json', tools)
        if tools['result']['tools'] != owner.tools:
            raise ValueError('qualification_stdio_catalogue_changed')
        pending = plan_public_calls(call)
    finally:
        result['diagnostic_close'] = close = client.finish()
        if not close['confirmed'] or close['exit_code'] != 0:
            raise ValueError('qualification_stdio_close_unconfirmed')
    save(folder / 'QUALIFICATION_PENDING.json', pending)
    result['qualification_pending'] = pending
