"""Connect each formal slot to its owned Blender and installed public MCP."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import time

from budget import Budget
from common import (ASSET, ASSET_SHA256, BLENDER, DISPLAY, EXTERNAL, HERE, NS, ROOT,
                    SOURCE_SHA, append, load, read, save, sha)


class Runtime:
    def __init__(self, folder, label, group, task_deadline, owned_deadline):
        self.folder = Path(folder).resolve()
        if self.folder != (EXTERNAL / 'slots' / label).resolve():
            raise ValueError('formal_slot_path_required')
        self.label, self.group = label, group
        self.task_deadline, self.owned_deadline = task_deadline, owned_deadline
        self.budget = Budget(EXTERNAL / 'budget')
        self.native = self.client = self.device = self.native_handle = self.mcp_handle = None
        self.claim = None
        self.public_requests = []
        self.native_calls = []
        self.proof = load('_live_owned_process_proof', DISPLAY / 'harness/reused/process_proof.py')

    def start(self):
        self.check()
        self.started = time.perf_counter_ns()
        binding_path = NS / 'PRODUCT_RUN_BINDING.json'
        binding = read(binding_path)
        if len(binding['source_manifest']) != 143 or binding['source_sha256'] != SOURCE_SHA:
            raise ValueError('fixed_B_source_required')
        sys.path.insert(0, binding['dependency_root'])
        self.product_root = binding['install_root']
        self.native_audit = load('_live_native_python_audit', ROOT /
            'verification/m4_target_task_consumption_001/native_consumer_audit.py')
        self.native_audit_installed = False
        bootstrap = load('_live_device_bootstrap', HERE / 'reused/verified_bootstrap.py')
        self.guard = bootstrap.bootstrap(binding)
        native_module = load('_live_owned_blender', HERE / 'owned_blender.py')
        self.claim = self.budget.reserve('Blender_start', self.label, 'formal')
        self.native = native_module.NativeSession.start(blender=BLENDER, asset=ASSET,
            workspace=self.folder / 'native', deadline_ns=self.owned_deadline, condition=self.group,
            expected_asset_sha256=ASSET_SHA256, max_calls=48, display_steps_enabled=False)
        self.native_handle = self._retain(self.native.process, 'NATIVE_RUNTIME_PROOF.json')
        self.camera_packet = read(NS / 'inputs/CAMERA.json')
        self.cameras = {'views': self.camera_packet['views'], 'pixel_convention': self.camera_packet['pixel_convention']}
        self.buffers = {}
        if self.group == 'P':
            self._start_public_mcp(binding_path, binding)
        self.check()
        save(self.folder / 'RUNTIME_READY.json', {'started_ns': self.started, 'ready_ns': time.perf_counter_ns(),
             'group': self.group, 'native_pid': self.native.process.pid,
             'product_PID': None if self.client is None else self.client.process.pid,
             'asset_copy_sha256': sha(self.native.workspace / 'input.blend'),
             'product_source_sha256': SOURCE_SHA, 'prior_task_captures': 0,
             'startup_scope': 'Owned file load, metadata-only readiness and protocol initialization. Full integrity guard is deferred to first authorized request.'})

    def prepare_device(self):
        from frame_device import FrameDevice

        self.device = FrameDevice(runroot=self.folder, camera=self.camera_packet,
            asset_sha256=ASSET_SHA256, group=self.group, label=self.label,
            native_call=self._native_call, terminal_call=self._terminal_call,
            budget=self.budget, phase='formal', check=self.check)
        self.device.buffers = self.buffers

    def scene_data(self, selectors=None):
        return self.device.scene_data(selectors=selectors)

    def render_views(self, names, fresh=False):
        return self.device.render_views(names, fresh=fresh)

    def image_specification(self, ref):
        return self.device.image_specification(ref)

    def _retain(self, process, output):
        proof, handle = self.proof._windows_runtime_proof(process, process.pid, self.owned_deadline)
        save(self.folder / output, proof)
        if proof.get('confirmed') is not True:
            raise RuntimeError('owned_child_identity_not_confirmed')
        return handle

    def check(self, *, terminal=False):
        deadline = self.owned_deadline if terminal else self.task_deadline
        if time.perf_counter_ns() >= deadline:
            raise TimeoutError('original_owned_deadline' if terminal else 'original_consumer_deadline')
        if self.native and (self.native.workspace / 'POISONED.json').exists():
            raise RuntimeError('owned_Blender_state_unconfirmed')

    def _start_public_mcp(self, binding_path, binding):
        path = self.folder / 'PRODUCT_CONFIG.json'
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': binding['install_root'], 'state_file': str(self.folder / 'product_state.json'),
                  'audit_file': str(self.folder / 'product_audit.jsonl'),
                  'expected_identity': {'source_sha256': SOURCE_SHA}, 'request_budget_s': 30,
                  'blender': {'host': self.native.host, 'port': self.native.port, 'timeout_s': 30}}
        save(path, config)
        transport = load('_live_stdio_client', DISPLAY / 'harness/reused/stdio_checks.py')
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'mcp_entry.py'),
                   '--binding', str(binding_path), '--config', str(path), '--ledger', str(self.budget.root),
                   '--evidence', str(self.folder / 'mcp_io'), '--phase', 'formal', '--label', self.label,
                   '--archive', str(self.folder / 'product_full')]
        self.client = transport.StdioClient(command, self.folder, self.folder / 'mcp', self.task_deadline)
        self.mcp_handle = self._retain(self.client.process, 'MCP_RUNTIME_PROOF.json')
        initial = self.client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'live-source-region-comparison', 'version': '001'}}})
        identity = initial['result']['_meta']['human_eye']
        if identity['source_sha256'] != SOURCE_SHA or identity['source_kind'] != 'installed_distribution':
            raise ValueError('public_product_identity_changed')
        self.client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listed = self.client.call({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'})
        self.product_tools = listed['result']['tools']
        observe = next(row for row in self.product_tools if row['name'] == 'human_eye_scene_observe')
        if observe != read(NS / 'inputs/PRODUCT_SCHEMA.json'):
            raise ValueError('actual_Human_Eye_schema_changed')
        save(self.folder / 'MCP_IDENTITY.json', identity)

    def _terminal_call(self, code, *, trusted=True, timeout_s=30):
        return self._native_call(code, trusted=trusted, timeout_s=timeout_s, terminal=True)

    def _native_call(self, code, *, trusted=True, timeout_s=30, terminal=False):
        self.check(terminal=terminal)
        started = time.perf_counter_ns()
        deadline = self.owned_deadline if terminal else self.task_deadline
        row = {'index': len(self.native_calls) + 1, 'started_ns': started, 'terminal': terminal, 'trusted': trusted,
               'code_bytes': len(code.encode()), 'code_sha256': hashlib.sha256(code.encode()).hexdigest()}
        try:
            reply = self.native.run(code, timeout_s=min(timeout_s, (deadline - started) / 1e9))
            response = reply['response']
            value = {'stdout': response.get('result', {}).get('result', response.get('stdout', '')),
                     'stderr': response.get('stderr', ''),
                     'error': None if response.get('status') == 'success' else response.get('error')}
            row['response_bytes'] = len(value['stdout'].encode())
            row['error'] = value['error']
            self.check(terminal=terminal)
            return value
        except Exception as error:
            row['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            row['closed_ns'] = time.perf_counter_ns()
            self.native_calls.append(row)
            append(self.folder / 'NATIVE_CALLS.jsonl', row)

    def native_run(self, code, timeout_s=30):
        if not self.native_audit_installed:
            scratch = self.native.workspace / 'consumer_scratch'
            scratch.mkdir(exist_ok=True)
            setup = self.native_audit.installation_script(scratch, self.native.workspace / 'input.blend', self.product_root)
            initialized = self._native_call(setup, timeout_s=timeout_s)
            if initialized['error'] is not None:
                raise RuntimeError('owned_native_Python_audit_setup_failed')
            self.native_audit_installed = True
        return self._native_call(self.native_audit.wrap(code), trusted=False, timeout_s=timeout_s)

    def public_request(self, arguments):
        self.check()
        if self.client is None or arguments.get('query', {}).get('mode') != 'source_region':
            raise ValueError('registered_source_region_public_query_required')
        index = len(self.public_requests) + 1
        folder = self.folder / 'product_calls' / f'call_{index:03d}'
        folder.mkdir(parents=True)
        request = {'jsonrpc': '2.0', 'id': 'observe-' + str(index), 'method': 'tools/call',
                   'params': {'name': 'human_eye_scene_observe', 'arguments': copy.deepcopy(arguments)}}
        save(folder / 'REQUEST.json', request)
        row = {'index': index, 'request': request, 'request_path': str(folder / 'REQUEST.json'),
               'started_ns': time.perf_counter_ns()}
        index_file = self.folder / 'product_full/INDEX.jsonl'
        before = index_file.read_bytes() if index_file.exists() else b''
        try:
            self.client.deadline = self.task_deadline
            response = self.client.call(request)
            row['response'] = response
            row['receipt'] = dict(self.client.records[-1])
            save(folder / 'RESPONSE.json', response)
            after = index_file.read_bytes() if index_file.exists() else b''
            if not after.startswith(before):
                raise RuntimeError('producer_archive_prefix_changed')
            additions = after[len(before):].splitlines()
            error = 'error' in response or response.get('result', {}).get('isError') is True
            if len(additions) > 1 or not error and len(additions) != 1:
                raise RuntimeError('one_original_producer_result_per_public_call_required')
            if additions:
                producer = json.loads(additions[0])
                source = Path(producer['path']).resolve()
                if (not source.is_relative_to((self.folder / 'product_full').resolve()) or
                        sha(source) != producer['sha256'] or not
                        row['started_ns'] <= producer['started_ns'] <= producer['producer_returned_ns'] <= time.perf_counter_ns()):
                    raise RuntimeError('fresh_producer_binding_mismatch')
                row['producer_archive'] = producer
                produced = read(source)
                if produced.get('frames'):
                    self.device.adopt_product_result(produced, producer)
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

    def close(self, outcome):
        began = time.perf_counter_ns()
        record = {'started_ns': began, 'errors': []}

        def capture(label, action):
            try:
                record[label] = action()
            except BaseException as error:
                record['errors'].append({'stage': label, 'type': type(error).__name__, 'message': str(error)})

        if self.client is not None:
            self.client.deadline = self.owned_deadline
            capture('public_MCP_close', self.client.finish)
        if self.mcp_handle is not None:
            capture('public_MCP_exit', lambda: self.proof._runtime_exit(self.mcp_handle))
        if self.native is not None:
            capture('Blender_close', self.native.close)
            capture('Blender_status', self.native.status)
        if self.native_handle is not None:
            capture('Blender_exit', lambda: self.proof._runtime_exit(self.native_handle))
        if hasattr(self, 'guard'):
            capture('installed_module_guard', self.guard.verify_loaded)
        if self.claim is not None:
            spawn_path = self.folder / 'native/SPAWN.json'
            spawned = read(spawn_path)['pid'] if spawn_path.is_file() else None
            capture('owned_budget_settlement', lambda: self.budget.settle_start(self.claim,
                pid=spawned, spawn_status='spawned' if spawned is not None else 'unknown',
                outcome='failed' if record['errors'] else outcome))
        record['closed_ns'] = time.perf_counter_ns()
        save(self.folder / 'RUNTIME_CLOSE.json', record)
        return record
