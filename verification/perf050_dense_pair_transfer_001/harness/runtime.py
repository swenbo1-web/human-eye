"""Reuse the owned device, canonical MCP startup, and exact producer correlation."""

from copy import deepcopy
from types import FunctionType
import time

from common import FORMAL, HERE, RECOVERY, SEAL, CATALOGUE, PRODUCT_SCHEMA, SOURCE_SHA, append, load_retained, read, save


previous = load_retained('_perf050_dense_runtime', FORMAL / 'harness/runtime.py')
startup = load_retained('_perf050_recovery_runtime', RECOVERY / 'harness/runtime.py').Runtime._start_public_mcp
correlate = load_retained('_perf050_sealed_correlation', SEAL / 'harness/owned_runtime.py').correlate_archive


class Runtime(previous.Runtime):
    _start_public_mcp = FunctionType(startup.__code__, dict(startup.__globals__, HERE=HERE, SOURCE_SHA=SOURCE_SHA, PRODUCT_SCHEMA=PRODUCT_SCHEMA, CATALOGUE=CATALOGUE))

    def public_request(self, arguments):
        self.check()
        if self.group != 'P' or self.client is None or type(arguments) is not dict:
            raise ValueError('installed_read_only_observe_entry_required')

        index = len(self.public_requests) + 1
        folder = self.folder / 'product_calls' / f'call_{index:03d}'
        folder.mkdir(parents=True, exist_ok=False)
        request = {'jsonrpc': '2.0', 'id': f'observe-{index}', 'method': 'tools/call',
                   'params': {'name': 'human_eye_scene_observe', 'arguments': deepcopy(arguments)}}
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
