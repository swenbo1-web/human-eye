"""Deterministic receive-boundary regressions against the actual MCP host."""
from collections import deque
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from human_eye_plugin import blender_mcp_host as module
from verification.test_blender_mcp_host import _reply, _request_from_code

ROOT = Path(__file__).resolve().parents[1]


class Connection:
    def __init__(self, chunks=(), *, response=None, clock=None, delay=0):
        self.chunks = deque(chunks)
        self.response, self.clock, self.delay = response, clock, delay
        self.sent, self.received, self.timeouts = [], [], []
        self.closed = False
        self.recv_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def sendall(self, payload):
        self.sent.append(payload)
        if self.response is not None:
            self.chunks.extend(self.response(payload))

    def recv(self, size):
        self.recv_calls += 1
        if self.clock is not None:
            self.clock.now += self.delay
        if not self.chunks:
            return b''
        value = self.chunks.popleft()
        if len(value) > size:
            self.chunks.appendleft(value[size:])
            value = value[:size]
        self.received.append(value)
        return value


def chunks(raw, width):
    return [raw[start:start+width] for start in range(0, len(raw), width)]


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def bare_host(connection, timeout=15):
    host = object.__new__(module.BlenderMCPHost)
    host.timeout_s, host._observation_depth = timeout, 0
    host._connect = lambda deadline: connection
    return host


@contextmanager
def operation_counts():
    counts = {'decode_calls': 0, 'decode_bytes': 0, 'loads_calls': 0,
              'loads_chars': 0, 'feed_bytes': 0, 'feed_chunks': [],
              'regex_span_bytes': 0, 'events': 0}
    original_loads = module._loads
    original_boundary = module._JSONObjectBoundary
    context = SimpleNamespace(chunk=None, cursor=0)

    class Buffer(bytearray):
        def decode(self, *args, **kwargs):
            counts['decode_calls'] += 1
            counts['decode_bytes'] += len(self)
            return super().decode(*args, **kwargs)

    class Boundary(original_boundary):
        def feed(self, chunk):
            counts['feed_bytes'] += len(chunk)
            counts['feed_chunks'].append(chunk)
            context.chunk, context.cursor = chunk, 0
            return super().feed(chunk)

    class Pattern:
        def __init__(self, actual):
            self.actual = actual

        def search(self, data, pos):
            if data is not context.chunk or pos < context.cursor:
                raise AssertionError('scanner revisited a previous prefix')
            match = self.actual.search(data, pos)
            end = len(data) if match is None else match.end()
            counts['regex_span_bytes'] += end-pos
            context.cursor = end
            counts['events'] += int(match is not None)
            return match

    def loads(value):
        counts['loads_calls'] += 1
        counts['loads_chars'] += len(value)
        return original_loads(value)

    with patch.object(module, 'bytearray', Buffer, create=True), \
            patch.object(module, '_loads', loads), \
            patch.object(module, '_JSONObjectBoundary', Boundary), \
            patch.object(module, '_JSON_STRING_EVENT', Pattern(module._JSON_STRING_EVENT)), \
            patch.object(module, '_JSON_CONTAINER_EVENT', Pattern(module._JSON_CONTAINER_EVENT)):
        yield counts


class IncrementalReceiveTests(unittest.TestCase):
    def test_valid_values_keep_full_bytes_and_parse_once_across_key_cuts(self):
        values = [
            {},
            {'nested': [{}, [1, {'s': '{}[]'}]], 'negative_zero': -0.0, 'tiny': 1e-300,
             'large_integer': 2**53+1},
            *[{'s': '场景😀' + '\\'*n + '"[]{}\\尾', 'value': n} for n in range(5)],
        ]
        for value in values:
            raw = encoded(value)
            cuts = {i for i in range(1, len(raw))
                    if raw[i-1] in b'"\\{}[]' or raw[i] >= 128 or raw[i-1] >= 128}
            cases = [chunks(raw, size) for size in (1, 2, 3, 7, 65536)]
            cases += [[raw[:cut], raw[cut:]] for cut in sorted(cuts)]
            for pieces in cases:
                with self.subTest(value=value, lengths=[len(p) for p in pieces]):
                    connection = Connection(pieces)
                    with operation_counts() as count:
                        result = bare_host(connection)._exchange(b'request')
                    self.assertEqual(encoded(result), encoded(value))
                    self.assertEqual((count['decode_calls'], count['loads_calls']), (1, 1))
                    self.assertEqual(count['decode_bytes'], len(raw))
                    self.assertEqual(count['feed_chunks'], connection.received)
                    self.assertEqual(count['feed_bytes'], len(raw))
                    self.assertLessEqual(count['regex_span_bytes'], len(raw))
                    self.assertEqual(connection.sent, [b'request'])
                    self.assertTrue(connection.closed)

    def test_leading_whitespace_and_complete_same_chunk_tail_are_strict(self):
        value = {'x': [1, 'braces {}[]']}
        raw = b' \t\r\n' + encoded(value) + b' \t\r\n'
        for pieces in ([raw], chunks(raw, 1), [b' \t', raw[2:]]):
            with self.subTest(lengths=[len(p) for p in pieces]):
                self.assertEqual(bare_host(Connection(pieces))._exchange(b'q'), value)
        for raw in (b'{}{}', b'{} garbage', b'{}\x00', b'{}\xff'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, UnicodeError)):
                bare_host(Connection([raw]))._exchange(b'q')

    def test_invalid_and_incomplete_objects_never_retry_full_prefix_parsing(self):
        values = [b'[]', b'null', b'123', b'banner{}', b'{bad}', b'{]',
                  b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}',
                  b'{"x":1,"x":2}', b'{"x":"\\q"}', b'{"x":"\xff"}',
                  b'{"x":[1,2}', b'{"x":"unterminated}', b'{']
        for raw in values:
            for size in (1, 2, 3, len(raw)):
                with self.subTest(raw=raw, size=size):
                    connection = Connection(chunks(raw, size))
                    with operation_counts() as count, self.assertRaises((ValueError, UnicodeError)):
                        bare_host(connection)._exchange(b'q')
                    self.assertLessEqual(count['decode_calls'], 1)
                    self.assertLessEqual(count['loads_calls'], 1)
                    self.assertEqual(connection.sent, [b'q'])
                    self.assertTrue(connection.closed)

    def test_incomplete_prefixes_do_not_decode_or_parse(self):
        connection = Connection(chunks(b'{"value":"still incomplete', 1))
        with operation_counts() as count, self.assertRaises(ValueError):
            bare_host(connection)._exchange(b'q')
        self.assertEqual((count['decode_calls'], count['loads_calls']), (0, 0))

    def test_one_original_deadline_includes_all_receives(self):
        clock = SimpleNamespace(now=0.)
        connection = Connection([b'{', b'"x":', b'1}'], clock=clock, delay=.3)
        with patch.object(module.time, 'monotonic', lambda: clock.now), \
                self.assertRaises(TimeoutError), operation_counts() as count:
            bare_host(connection, timeout=.5)._exchange(b'q')
        self.assertEqual(connection.recv_calls, 2)
        self.assertTrue(all(0 < value <= .5 for value in connection.timeouts))
        self.assertEqual(connection.sent, [b'q'])
        self.assertEqual(count['decode_calls'], 0)
        self.assertTrue(connection.closed)

    def test_original_byte_budget_is_checked_before_decode(self):
        self.assertEqual(module._MAX_RESPONSE_BYTES, 64*1024*1024)
        with patch.object(module, '_MAX_RESPONSE_BYTES', 64):
            valid = b'{"x":"' + b'x'*56 + b'"}'
            self.assertEqual(len(valid), 64)
            self.assertEqual(bare_host(Connection([valid]))._exchange(b'q'), {'x': 'x'*56})
            connection = Connection([valid[:-2] + b'x'*20 + b'"}'])
            with operation_counts() as count, self.assertRaisesRegex(ValueError, 'size limit'):
                bare_host(connection)._exchange(b'q')
            self.assertEqual(count['decode_calls'], 0)
            self.assertEqual(sum(map(len, connection.received)), 65)

    def test_public_capture_keeps_inner_parse_separate(self):
        expected = {'revision': 'r1', 'name': '局部😀', 'value': -0.0}

        def respond(payload):
            request = _request_from_code(json.loads(payload))
            return chunks(encoded(_reply(request, expected)), 3)

        connection = Connection(response=respond)
        host = module.BlenderMCPHost(ROOT)
        host._connect = lambda deadline: connection
        with operation_counts() as count:
            self.assertEqual(encoded(host.capture_scene()), encoded(expected))
        self.assertEqual((count['decode_calls'], count['loads_calls']), (1, 2))
        self.assertEqual(len(connection.sent), 1)
        self.assertTrue(host.is_alive)

    def test_unknown_apply_is_not_resent_and_later_packet_boundary_is_preserved(self):
        connection = Connection([b'{"status":'])
        host = module.BlenderMCPHost(ROOT)
        host._connect = lambda deadline: connection
        with self.assertRaises(module.HostTransportError):
            host.apply_transform({'focal_id': 'cube', 'translation': [1, 0, 0]}, 'r1')
        with self.assertRaises(module.HostTransportError):
            host.capture_scene()
        self.assertEqual(len(connection.sent), 1)
        self.assertFalse(host.is_alive)
        connection = Connection([b'{"x":1}', b'{"later":2}'])
        self.assertEqual(bare_host(connection)._exchange(b'q'), {'x': 1})
        self.assertEqual(connection.recv_calls, 1)
        self.assertEqual(list(connection.chunks), [b'{"later":2}'])


if __name__ == '__main__':
    unittest.main()
