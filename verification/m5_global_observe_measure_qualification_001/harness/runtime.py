"""Retain generic owned startup, with the recovered public-packet association."""

import copy
from pathlib import Path
from types import FunctionType
import time

from common import (FORMAL, HERE, NS, SEAL, SLOT_REQUESTS, REQUESTS,
                    append, load_retained, read, save, sha)


previous = load_retained('_m5_global_owned_runtime', FORMAL / 'harness/runtime.py')
recovery = load_retained('_m5_global_recovered_association', SEAL / 'harness/owned_runtime.py')
original = previous.Runtime._start_public_mcp
entry_globals = dict(original.__globals__, HERE=HERE, NS=NS)


class Runtime(previous.Runtime):
    _start_public_mcp = FunctionType(original.__code__, entry_globals)

    def __init__(self, folder, label, task_deadline, owned_deadline, business_calls):
        super().__init__(folder, label, task_deadline, owned_deadline)
        self.business_calls = business_calls

    def public_request(self, arguments):
        self.check()
        index = len(self.public_requests) + 1
        order = SLOT_REQUESTS[self.label]
        if self.client is None or index > len(order):
            raise ValueError('registered_public_request_count_exceeded')
        kind = order[index - 1]
        path = REQUESTS[kind]
        if arguments != read(path):
            raise ValueError('qualification_original_public_arguments_changed')
        claim = self.budget.admit_business(self.label, self.phase)
        call = {'kind': kind, 'claim': claim, 'started_ns': time.perf_counter_ns(), 'arguments_sha256': sha(path)}
        self.business_calls.append(call)
        folder = self.folder / 'product_calls' / f'call_{index:03d}'
        folder.mkdir(parents=True)
        request = {'jsonrpc': '2.0', 'id': 'observe-' + str(index), 'method': 'tools/call',
                   'params': {'name': 'human_eye_scene_observe', 'arguments': copy.deepcopy(arguments)}}
        save(folder / 'REQUEST.json', request)
        index_file = self.folder / 'product_full/INDEX.jsonl'
        before = index_file.read_bytes() if index_file.exists() else b''
        (folder / 'ARCHIVE_BEFORE.bin').write_bytes(before)
        row = {'index': index, 'id': request['id'], 'kind': kind, 'request': request,
               'request_path': str(folder / 'REQUEST.json'), 'started_ns': time.perf_counter_ns()}
        try:
            self.client.deadline = self.task_deadline
            response = self.client.call(request)
            returned = time.perf_counter_ns()
            receipt = self.client.records[-1]
            row.update(response=response, receipt=receipt, client_returned_ns=returned)
            save(folder / 'RESPONSE.json', response)
            save(folder / 'RECEIPT.json', receipt)
            after = index_file.read_bytes() if index_file.exists() else b''
            (folder / 'ARCHIVE_AFTER.bin').write_bytes(after)
            error = 'error' in response or response.get('result', {}).get('isError') is True
            entry = recovery.correlate_archive(before, after, row['started_ns'], returned,
                                              error, self.folder / 'product_full')
            if entry is not None:
                row['producer_archive'] = entry
                produced = read(entry['path'])
                if produced.get('frames'):
                    self.device.adopt_product_result(produced, entry)
            self.check()
            call.update(status='failed' if error else 'completed', producer_archive_index=None if entry is None else entry['index'])
            return response
        except Exception as problem:
            row['error'] = {'type': type(problem).__name__, 'message': str(problem)}
            call['status'] = 'failed'
            raise
        finally:
            self.client.deadline = self.task_deadline
            row['closed_ns'] = call['closed_ns'] = time.perf_counter_ns()
            self.public_requests.append(row)
            append(self.folder / 'PUBLIC_REQUESTS.jsonl', row)
