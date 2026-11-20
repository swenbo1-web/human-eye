"""Qualification admission gate for the existing image-capable MCP Owner."""

import copy
from pathlib import Path
import threading

from common import IMAGE_BRIDGE, load


_bridge = load('_cross_scale_original_image_bridge', IMAGE_BRIDGE / 'bridge.py')
_bridge.TOOL_LIMIT = TOOL_LIMIT = 2
MAX_FRAME = _bridge.MAX_FRAME
encoded = _bridge.encoded
save = _bridge.save
remaining = _bridge.remaining
error_result = _bridge.error_result
PRODUCT_TOOL = _bridge.PRODUCT_TOOL
ARGUMENTS = {'query': {'mode': 'active_observation', 'region_task': {
    'area_min_m2': 0.0078125, 'area_max_m2': 0.03125, 'normal_z_min': 0.75}}, 'include_image': True}


class Owner(_bridge.Owner):
    def __init__(self, runtime, config, budget=None):
        self.runtime, self.config, self.budget = runtime, config, budget
        self.group, self.label, self.phase = 'P', config['label'], config['phase']
        if (self.label, self.phase) != ('Q1', 'qualification'):
            raise ValueError('registered_cross_scale_slot_required')
        self.deadline_ns = config['worker_deadline_ns']
        self.output = Path(config['output']).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.tools = [copy.deepcopy(next(row for row in runtime.product_tools if row['name'] == PRODUCT_TOOL))]
        self.rows, self.protocol, self.protocol_errors, self.transport_errors = [], [], [], []
        self.listener = self.thread = None
        self.stop = threading.Event()
        save(self.output / 'TOOLS_SCHEMA.json', self.tools)
        self.publish()

    def handle(self, request, attempt=None):
        response = super().handle(request, attempt)
        if request.get('method') == 'initialize' and response is not None:
            response['result'].pop('instructions', None)
        return response

    def publish(self):
        last = self.rows[-1]['attempt'] if self.rows else 0
        save(self.output / 'TOOLS.json', {'calls': last, 'attempts': last, 'tools': self.rows})
        save(self.output / 'BRIDGE_RESULT.json', {'calls': self.rows, 'protocol': self.protocol,
            'protocol_errors': self.protocol_errors, 'transport_errors': self.transport_errors,
            'public_text_bytes': sum(row.get('content_metrics', {}).get('text_UTF8_bytes', 0) for row in self.rows)})

    def dispatch(self, name, arguments, row, folder):
        if name != PRODUCT_TOOL or arguments != ARGUMENTS:
            raise ValueError('fixed_global_active_observation_arguments_required')
        save(folder / 'PRODUCT_ARGUMENTS.json', arguments)
        before = len(getattr(self.runtime, 'public_requests', ()))
        try:
            response = self.runtime.public_request(arguments)
            save(folder / 'PRODUCT_RESPONSE.json', response)
        finally:
            for record in getattr(self.runtime, 'public_requests', ())[before:]:
                if 'request' in record:
                    save(folder / 'PRODUCT_REQUEST.json', record['request'])
                save(folder / 'PRODUCT_RECEIPT.json', {key: value for key, value in record.items()
                                                     if key not in ('request', 'response')})
        if response.get('error') is not None:
            raise ValueError('installed_public_RPC_failed')
        return response['result']
