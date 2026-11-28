"""Bind a controlled MCP experiment to complete JSON-RPC request envelopes."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True,
                      allow_nan=False).encode('utf8')


def fingerprint(value):
    return hashlib.sha256(encode(value)).hexdigest()


@dataclass(frozen=True)
class Registered:
    label: str
    request_id: int
    message: bytes


class RegisteredCalls:
    def __init__(self, path, planned):
        self.path = Path(path)
        self.by_id = {}
        labels = set()
        for entry in planned:
            request = entry['request']
            request_id, label = request['id'], entry['label']
            if (type(request_id) is not int or request_id in self.by_id or label in labels
                    or request['method'] != 'tools/call'):
                raise ValueError('registered_business_identity_collision')
            self.by_id[request_id] = Registered(label, request_id, encode(request))
            labels.add(label)
        self.seen = set()
        self.attempt = 0
        self.active = None
        self.log = self.path.open('x', encoding='utf8', newline='\n')

    def event(self, phase, **details):
        stamp = {'phase': phase, 'clock_ns': time.perf_counter_ns(), **details}
        self.log.write(encode(stamp).decode('utf8') + '\n')
        self.log.flush()

    def dispatch(self, request, dispatch, refusal):
        if self.active is not None:
            raise ValueError('registered_business_recursion')
        self.attempt += 1
        request_id = request.get('id')
        expected = self.by_id.get(request_id) if type(request_id) is int else None
        message = encode(request)
        reason = ('unregistered_request_id' if expected is None else
                  'registered_request_mismatch' if message != expected.message else
                  'registered_request_already_dispatched' if request_id in self.seen else None)
        row = {'attempt': self.attempt, 'request_id': request_id, 'label': expected.label if expected else None,
               'request_sha256': hashlib.sha256(message).hexdigest(),
               'expected_sha256': hashlib.sha256(expected.message).hexdigest() if expected else None,
               'registered': reason is None, 'reason': reason}
        self.event('attempt_registered', **row)
        if reason is not None:
            return refusal(reason)
        self.seen.add(request_id)
        self.active = row
        self.event('product_dispatch_started', **row)
        try:
            reply = dispatch()
            self.event('product_dispatch_returned', **row, has_reply=reply is not None,
                       product_is_error=bool(reply and ('error' in reply or reply.get('result', {}).get('isError'))),
                       product_reply_sha256=fingerprint(reply))
            return reply
        except BaseException as error:
            self.event('product_dispatch_raised', **row, error=type(error).__name__)
            raise
        finally:
            self.active = None

    def service_event(self, phase, **details):
        if self.active is None:
            raise ValueError('product_service_without_registered_request')
        self.event(phase, **self.active, **details)


@contextmanager
def registration_scope(module, receipt, planned):
    """For an owned experiment child only. Keep the real parser, handlers and publisher."""
    recorder = RegisteredCalls(receipt, planned)
    base = module.LiveSpatialMCPServer

    class RecordingServer(base):
        def handle_jsonrpc_message(self, request):
            actual = super().handle_jsonrpc_message
            if request.get('method') != 'tools/call':
                return actual(request)

            def refuse(reason):
                return {'jsonrpc': '2.0', 'id': request.get('id'),
                        'result': self._error_result(ValueError(reason))}

            return recorder.dispatch(request, lambda: actual(request), refuse)

    module.LiveSpatialMCPServer = RecordingServer
    try:
        yield recorder
    finally:
        module.LiveSpatialMCPServer = base
        recorder.log.close()
