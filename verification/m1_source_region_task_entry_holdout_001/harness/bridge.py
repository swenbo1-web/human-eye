"""Common ordinary tools plus the actual per-arm installed read-only entries."""

import copy
import json
from pathlib import Path
import threading

from common import FORMAL, NARROW_TOOL, SLOTS, load, load_retained


bridge = load_retained('_task_entry_dense_common_bridge', FORMAL / 'bridge.py')
if bridge.SLOTS is not SLOTS:
    raise ValueError('task_entry_bridge_loaded_wrong_slots')
DISCOVERY, TOOL_LIMIT, MAX_FRAME, PRODUCT_TOOL = (
    bridge.DISCOVERY, bridge.TOOL_LIMIT, bridge.MAX_FRAME, bridge.PRODUCT_TOOL,
)
TOOLS, VIEWS, SOURCE_REGION = bridge.TOOLS, bridge.VIEWS, bridge.SOURCE_REGION
encoded, save, remaining, error_result = bridge.encoded, bridge.save, bridge.remaining, bridge.error_result
IMAGES = bridge._prior.IMAGES


def tool_names(label):
    if label not in SLOTS:
        raise ValueError('registered_task_entry_slot_required')
    return frozenset(row['name'] for row in TOOLS) | {PRODUCT_TOOL} | (
        {NARROW_TOOL} if label in ('QB', 'B1') else set())


# Retained group-only callers can inspect the union, but actual approval must
# bind tool_names(label). Owner dispatch always checks its actual per-slot table.
TOOL_NAMES = {'N': frozenset(row['name'] for row in TOOLS), 'P': tool_names('B1')}


def public_tools(runtime):
    tools = copy.deepcopy(TOOLS)
    names = [PRODUCT_TOOL] + ([NARROW_TOOL] if runtime.label in ('QB', 'B1') else [])
    for name in names:
        matches = [row for row in runtime.product_tools if row['name'] == name]
        if len(matches) != 1:
            raise ValueError('task_entry_actual_installed_tool_missing_or_duplicate/' + name)
        tools.append(copy.deepcopy(matches[0]))
    if frozenset(row['name'] for row in tools) != tool_names(runtime.label):
        raise ValueError('task_entry_actual_public_directory_mismatch')
    return tools


class Owner(bridge.Owner):
    def __init__(self, runtime, config, budget=None):
        self.runtime, self.config, self.budget = runtime, config, budget
        self.group, self.label, self.phase = config['group'], config['label'], config['phase']
        if (SLOTS.get(self.label) != (self.group, self.phase)
                or runtime.label != self.label or self.group != 'P'):
            raise ValueError('registered_task_entry_slot_required')
        self.deadline_ns = config['worker_deadline_ns']
        self.output = Path(config['output']).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.session = bridge.Session(runtime, config)
        self.tools = public_tools(runtime)
        self.available_tools = frozenset(row['name'] for row in self.tools)
        self.rows, self.protocol, self.protocol_errors, self.transport_errors = [], [], [], []
        self.listener = self.thread = None
        self.stop = threading.Event()
        save(self.output / 'TOOLS_SCHEMA.json', self.tools)
        self.publish()

    def handle(self, request, attempt=None):
        reply = super().handle(request, attempt)
        if request.get('method') == 'initialize' and reply is not None:
            reply['result']['serverInfo']['name'] = 'm1-source-region-task-entry-001'
        return reply

    def dispatch(self, name, arguments, row, folder):
        if name not in self.available_tools:
            raise ValueError('tool_unavailable_in_this_slot')
        if name == NARROW_TOOL:
            return self.product(arguments, folder, name=name)
        return super().dispatch(name, arguments, row, folder)

    def product(self, arguments, folder, *, name=PRODUCT_TOOL):
        save(folder / 'PRODUCT_ARGUMENTS.json', arguments)
        before = len(self.runtime.public_requests)
        try:
            response = self.runtime.public_request(copy.deepcopy(arguments), name=name)
            save(folder / 'PRODUCT_RESPONSE.json', response)
        finally:
            for record in self.runtime.public_requests[before:]:
                if 'request' in record:
                    save(folder / 'PRODUCT_REQUEST.json', record['request'])
                if 'response' in record:
                    save(folder / 'PRODUCT_RESPONSE.json', record['response'])
                save(folder / 'PRODUCT_RECEIPT.json', {key: value for key, value in record.items()
                     if key not in ('request', 'response')})
        if response.get('error') is not None:
            raise RuntimeError(f'Installed product RPC error: {response["error"]}')
        return response['result']

    def images(self, refs, row):
        result = []
        for ref in refs:
            spec, directory = self.runtime.image_specification(ref)
            slot = self.runtime.folder.resolve(strict=True)
            declared = Path(directory) / spec['file']
            path = declared.resolve(strict=True)
            if (not declared.is_absolute() or path != declared or not path.is_relative_to(slot)
                    or path.suffix.lower() != '.png'):
                raise ValueError('current_slot_original_png_path_required')
            try:
                image, receipt = IMAGES.image_content(spec, directory, self.deadline_ns)
            except IMAGES.ImageContentError as error:
                row['image_attachments'].append(error.receipt)
                raise
            row['image_attachments'].append(receipt)
            delivery = {'local_image_path': path.as_posix(), 'image_sha256': receipt['PNG_sha256']}
            row.setdefault('local_image_delivery', []).append({'ref': ref, **delivery})
            caption = f'{ref} ({spec["width"]}x{spec["height"]}, image/png)\n'
            result.extend([{'type': 'text', 'text': caption + json.dumps(delivery, ensure_ascii=False)}, image])
        return result
