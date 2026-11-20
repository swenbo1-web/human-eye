"""One actual recovered loopback outer call per arm, with retained original inner packets."""

import copy
import json
import time

from common import PRODUCT_SCHEMA, REQUESTS, SEAL, SLOT_REQUESTS, load_retained, read, save


bridge = load_retained('_m5_global_actual_outer_bridge', SEAL / 'bridge.py')
driver = load_retained('_m5_global_actual_outer_rpc', SEAL / 'harness/qual_driver.py')
MARKERS = {'OBSERVE': 'M5_GLOBAL_OBSERVE:', 'MEASURE': 'M5_GLOBAL_MEASURE:', 'JOINT': 'M5_GLOBAL_JOINT:'}


class Session(bridge.COMMON.OrdinarySession):
    def observe(self, query=None, include_image=True):
        if type(query) is not dict or type(include_image) is not bool:
            raise ValueError('fixed_public_observe_argument_types')
        arguments = {'query': copy.deepcopy(query), 'include_image': include_image, 'response_detail': 'brief'}
        _, value = self.public_request(arguments, queue_images=True)
        return value


class OuterBudget:
    """Count the single external wrapper separately from actual installed public admissions."""

    def __init__(self, label):
        self.label = label
        self.count = 0

    def reserve(self, kind, label, phase, upper):
        if (kind, label, phase, upper) != ('business_tool', self.label, 'qualification', 1) or self.count:
            raise ValueError('one_fixed_outer_qualification_message')
        self.count += 1


bridge.COMMON.OrdinarySession = Session


def tools(label):
    if label not in SLOT_REQUESTS:
        raise ValueError('fixed_outer_qualification_arm')
    published = copy.deepcopy(bridge.TOOLS[0])
    published['description'] = 'Run the fixed observe/task qualification batch over the installed public API.'
    return [published, read(PRODUCT_SCHEMA)]


bridge.public_tools = tools


def outer_message(label):
    code = []
    for kind in SLOT_REQUESTS[label]:
        arguments = read(REQUESTS[kind])
        query = repr(arguments['query'])
        if kind == 'MEASURE':
            call, text = 'task(' + query + ')', 'last_task_json'
        else:
            call, text = 'observe(query=' + query + ', include_image=True)', 'last_observation_json'
        code.extend((call, 'print(' + repr(MARKERS[kind]) + ' + ' + text + ')'))
    return {'jsonrpc': '2.0', 'id': 'qualification-batch-' + label, 'method': 'tools/call',
            'params': {'name': 'execute_python', 'arguments': {'code': '\n'.join(code) + '\n'}}}


def owner_for(runtime, label, folder, deadline):
    budget = OuterBudget(label)
    return bridge.Owner(runtime, {'group': label, 'label': label, 'phase': 'qualification',
               'worker_deadline_ns': deadline, 'output': str(folder / 'owner')}, budget=budget)


def execute(owner, label, folder, endpoint, deadline):
    messages = [
        {'jsonrpc': '2.0', 'id': 'qualification-initialize', 'method': 'initialize',
         'params': {'protocolVersion': '2025-03-26', 'capabilities': {}}},
        {'jsonrpc': '2.0', 'id': 'qualification-tools', 'method': 'tools/list'},
        outer_message(label),
    ]
    root = folder / 'batch'
    root.mkdir()
    replies = [driver.rpc(endpoint, message, root / f'rpc_{index:02d}', deadline)
               for index, message in enumerate(messages, 1)]
    response = replies[-1]['response']['result']
    public = owner.runtime.public_requests
    if (owner.budget.count != 1 or response['isError'] is not False
            or len(public) != len(SLOT_REQUESTS[label]) or any(row['response']['result']['isError'] is not False for row in public)):
        raise ValueError('original_public_qualification_batch_did_not_complete')
    value = json.loads(response['content'][0]['text'])
    if value['error'] is not None or value['stderr']:
        raise ValueError('outer_qualification_driver_reported_error')
    expected = [MARKERS[kind] + row['response']['result']['content'][0]['text']
                for kind, row in zip(SLOT_REQUESTS[label], public, strict=True)]
    if value['stdout'] != ''.join(line + '\n' for line in expected):
        raise ValueError('outer_body_did_not_retain_original_inner_text')
    inner_images = [block for row in public for block in row['response']['result']['content'] if block['type'] == 'image']
    if response['content'][1:] != inner_images:
        raise ValueError('outer_body_did_not_retain_original_inner_images')
    batch = replies[-1]
    record = {'outer_business_count': owner.budget.count, 'inner_public_count': len(public),
              'internal_public_request_ids': [item['id'] for item in public],
              'started_ns': batch['started_ns'], 'closed_ns': batch['closed_ns'],
              'client_socket_ns': batch['client_socket_ns'], 'TX_bytes': batch['TX_bytes'],
              'RX_bytes': batch['RX_bytes'], 'TX_sha256': batch['TX_sha256'], 'RX_sha256': batch['RX_sha256'],
              'images': batch['images'], 'receipt_path': str(root / 'rpc_03/RECEIPT.json')}
    save(root / 'QUALIFICATION_BATCH.json', record)
    return record
