"""Same owned lifecycle, per-arm installation, and unmodified named requests."""

from copy import deepcopy
from pathlib import Path
from types import FunctionType
import time

from common import DUAL, HERE, NS, NARROW_TOOL, append, load_retained, product_for, read, save


previous = load_retained('_task_entry_retained_runtime', DUAL / 'harness/runtime.py')
transport = previous.previous.transport
correlate = previous.correlate


def arm_function(function, product):
    """Bind source/catalogue paths without editing retained lifecycle code."""
    scope = dict(function.__globals__, HERE=HERE, NS=NS,
                 PRODUCT_BINDING=product['binding'], PRODUCT_SCHEMA=product['schema'],
                 CATALOGUE=product['catalogue'], SOURCE_SHA=product['source_sha256'])
    return FunctionType(function.__code__, scope, function.__name__,
                        function.__defaults__, function.__closure__)


class Runtime(previous.Runtime):
    def start(self):
        self.product_spec = product_for(self.label)
        return arm_function(previous.Runtime.start, self.product_spec)(self)

    def _start_public_mcp(self, binding_path, binding):
        product = self.product_spec
        if (Path(binding_path).resolve() != product['binding'].resolve()
                or binding['source_sha256'] != product['source_sha256']):
            raise ValueError('task_entry_slot_install_binding_mismatch')
        return arm_function(previous.Runtime._start_public_mcp, product)(self, binding_path, binding)

    def public_request(self, arguments, *, name='human_eye_scene_observe'):
        self.check()
        allowed = {'human_eye_scene_observe'}
        if self.label in ('QB', 'B1'):
            allowed.add(NARROW_TOOL)
        if (self.group != 'P' or self.client is None or type(arguments) is not dict
                or name not in allowed or name not in {row['name'] for row in self.product_tools}):
            raise ValueError('installed_read_only_named_entry_required')

        index = len(self.public_requests) + 1
        folder = self.folder / 'product_calls' / f'call_{index:03d}'
        folder.mkdir(parents=True, exist_ok=False)
        request = {'jsonrpc': '2.0', 'id': f'observe-{index}', 'method': 'tools/call',
                   'params': {'name': name, 'arguments': deepcopy(arguments)}}
        save(folder / 'REQUEST.json', request)
        index_path = self.folder / 'product_full/INDEX.jsonl'
        before = index_path.read_bytes() if index_path.is_file() else b''
        (folder / 'ARCHIVE_BEFORE.bin').write_bytes(before)
        row = {'index': index, 'id': request['id'], 'request': request,
               'request_path': str(folder / 'REQUEST.json'), 'started_ns': time.perf_counter_ns()}
        try:
            self.client.deadline = self.task_deadline
            response = self.client.call(request)
            returned = time.perf_counter_ns()
            receipt = self.client.records[-1]
            row.update(response=response, receipt=receipt, client_returned_ns=returned)
            save(folder / 'RESPONSE.json', response)
            save(folder / 'RECEIPT.json', receipt)
            after = index_path.read_bytes() if index_path.is_file() else b''
            (folder / 'ARCHIVE_AFTER.bin').write_bytes(after)
            failed = 'error' in response or response.get('result', {}).get('isError') is True
            producer = correlate(before, after, row['started_ns'], returned, failed, self.folder / 'product_full')
            if producer is not None:
                row['producer_archive'] = producer
                result = read(producer['path'])
                if result.get('frames'):
                    self.device.adopt_product_result(result, producer)
            self.check()
            return response
        except Exception as error:
            row['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            self.client.deadline = self.task_deadline
            row['closed_ns'] = time.perf_counter_ns()
            self.public_requests.append(row)
            append(self.folder / 'PUBLIC_REQUESTS.jsonl', row)
