"""Local socket owner fixture, using the unchanged real thin-client framing."""

import copy
import json
import os
from pathlib import Path
import socket
import threading
import time


class FakeOwner:
    def __init__(self, folder, episode_id, group, deadline_ns, scenario='normal'):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True)
        self.episode_id, self.group, self.deadline_ns = episode_id, group, deadline_ns
        self.calls = 0
        self.turns, self.events, self.finish_calls = [], [], 0
        self.active, self.pose, self.edits = None, 0, 0
        self.stopped = threading.Event()
        self.errors = []
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(3)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.endpoint = self.folder / 'ENDPOINT.json'
        self.save(self.endpoint, {'host': '127.0.0.1', 'port': self.port,
                                 'chain_deadline_ns': deadline_ns, 'actor_pid': os.getpid(),
                                 'synthetic_scenario': scenario})
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    @staticmethod
    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf8', newline='\n')

    def status(self):
        return {'episode_id': self.episode_id, 'owner_pid': os.getpid(), 'native_pid': os.getpid(),
                'native_host': '127.0.0.1', 'native_port': self.port, 'native_workspace': str(self.folder),
                'product_launcher_pid': None, 'product_runtime_proof': None, 'session_id': 'synthetic-session',
                'worker_deadline_ns': self.deadline_ns, 'active_turn': copy.deepcopy(self.active),
                'completed_turns': copy.deepcopy(self.turns), 'business_attempts': self.calls,
                'owner_close_called': self.finish_calls > 0, 'synthetic_fixture': True}

    def control(self, operation, **params):
        if time.perf_counter_ns() >= self.deadline_ns:
            raise TimeoutError('synthetic_owner_original_deadline')
        self.events.append({'operation': operation, 'params': params, 'at_ns': time.perf_counter_ns(),
                            'finish_calls': self.finish_calls})
        if operation == 'begin_turn':
            assert self.active is None
            assert params['turn_id'] == ('BASE', 'REPEAT', 'EDIT')[len(self.turns)]
            assert params['deadline_ns'] <= self.deadline_ns
            assert params['turn_id'] != 'EDIT' or self.edits == 1
            self.active = {'turn_id': params['turn_id'], 'first_business_attempt': self.calls + 1}
        elif operation == 'end_turn':
            assert self.active and self.active['turn_id'] == params['turn_id']
            self.turns.append({**self.active, 'last_business_attempt': self.calls})
            self.active = None
        elif operation == 'qa_advance':
            assert [row['turn_id'] for row in self.turns] == ['BASE', 'REPEAT']
            assert self.active is None and self.edits == 0
            self.edits += 1
            self.pose = 1
        elif operation != 'status':
            raise ValueError('synthetic_owner_unknown_operation')
        return self.status()

    def handle(self, message):
        method, rid = message['method'], message.get('id')
        if method == 'initialize':
            result = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'synthetic-owner', 'version': '001'}}
        elif method == 'tools/list':
            names = ['execute_blender_code'] + (['human_eye_scene_observe'] if self.group == 'C' else [])
            result = {'tools': [{'name': name, 'description': 'synthetic fixture', 'inputSchema': {'type': 'object'}} for name in names]}
        elif method == 'tools/call':
            assert self.active is not None and self.finish_calls == 0
            self.calls += 1
            folder = self.folder / ('tool_' + str(self.calls).zfill(2))
            folder.mkdir()
            result = {'content': [{'type': 'text', 'text': json.dumps({'synthetic': True,
                'pose': self.pose, 'group': self.group, 'id': 'business-payload', 'perf_ns': 'semantic-data-kept'})}], 'isError': False}
            response = {'jsonrpc': '2.0', 'id': rid, 'result': result}
            self.save(folder / 'REQUEST.json', message)
            self.save(folder / 'RESPONSE.json', response)
            self.save(folder / 'ATTEMPT.json', {'attempt': self.calls, 'is_error': False, 'exception': None})
            self.save(self.folder / 'TOOLS.json', {'attempts': self.calls, 'calls': self.calls,
                                                 'tools': [{'attempt': number} for number in range(1, self.calls + 1)]})
            self.events.append({'operation': 'business', 'number': self.calls, 'pose': self.pose,
                                'finish_calls': self.finish_calls, 'at_ns': time.perf_counter_ns()})
            return response
        else:
            raise ValueError('synthetic_owner_unknown_RPC')
        return {'jsonrpc': '2.0', 'id': rid, 'result': result}

    def serve(self):
        while not self.stopped.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                with conn:
                    data = bytearray()
                    conn.settimeout(5)
                    while True:
                        raw = conn.recv(65536)
                        if not raw:
                            break
                        data.extend(raw)
                    request = json.loads(data)
                    result = self.handle(request['args']['message'])
                    reply = {'request_id': request['request_id'], 'ok': True, 'result': result}
                    conn.sendall((json.dumps(reply) + '\n').encode())
            except BaseException as error:
                self.errors.append(repr(error))

    def finish(self):
        self.finish_calls += 1
        assert self.finish_calls == 1
        self.stopped.set()
        self.listener.close()
        self.thread.join(timeout=2)
        result = {'confirmed': not self.thread.is_alive() and not self.errors,
                  'finish_calls': self.finish_calls, 'synthetic_fixture': True,
                  'business_attempts': self.calls, 'registered_edits': self.edits,
                  'active_turn': copy.deepcopy(self.active), 'errors': self.errors}
        self.save(self.folder / 'CLOSE.json', result)
        self.save(self.folder / 'CONTROL_EVENTS.json', self.events)
        return result
