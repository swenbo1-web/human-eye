"""Bind the reviewed global/local owner to the fixed current installation."""

import copy
from pathlib import Path
import sys
import time

from budget import Budget
from common import (ASSET, ASSET_SHA, BINDING, EXTERNAL, GLOBAL_HARNESS, HERE, SCHEMA, SLOT, SOURCE_SHA,
                    load, read, save, sha)


_previous = load('_cross_scale_previous_owned_runtime', GLOBAL_HARNESS / 'owned_runtime.py')
_previous.EXTERNAL, _previous.ASSET, _previous.ASSET_SHA256 = EXTERNAL, ASSET, ASSET_SHA
_reused = GLOBAL_HARNESS / 'reused'
transport = load('_cross_scale_stdio', _reused / 'stdio_checks.py')
proof = load('_cross_scale_process_proof', _reused / 'process_proof.py')


class Runtime(_previous.RootRuntime):
    def __init__(self, deadline_ns):
        self.started_ns, self.deadline_ns = time.perf_counter_ns(), deadline_ns
        self.consumer_deadline_ns = deadline_ns
        self.runroot = SLOT.resolve()
        self.phase, self.label, self.group = 'qualification', 'Q1', 'B'
        self.budget = Budget(EXTERNAL / 'budget')
        self.native = self.client = self.runtime_handle = self.claim = None
        self.native_handle = None
        self.stages, self.native_calls, self.public_requests, self.source_reads = [], [], [], []
        self.buffers, self.by_ref, self.by_view = {}, {}, {}
        self._scene_cache = None
        self._product_calls = 0
        self.errors = []
        self.poisoned = self.closed = False
        self.binding_path, self.binding = BINDING, read(BINDING)
        self.device = {'source': 'installed_product_whole_scene_and_local_scope_cameras',
                       'external_camera_override': False}
        self.proof_module = proof

    def start(self):
        self.check()
        if (self.binding['source_sha256'] != SOURCE_SHA or len(self.binding['source_manifest']) != 143
                or sha(ASSET) != ASSET_SHA):
            raise ValueError('fixed_143_source_install_or_owned_copy_asset_mismatch')
        bootstrap = load('_cross_scale_parent_verified_bootstrap', _reused / 'verified_bootstrap.py')
        self.guard = bootstrap.bootstrap(self.binding)
        sys.path.insert(0, self.binding['dependency_root'])
        self.np = __import__('numpy')
        native = load('_cross_scale_owned_blender', _reused / 'owned_native.py')
        self.claim = self.budget.reserve('Blender_start', self.label, self.phase, 1)
        self.native = native.NativeSession.start(blender='D:/Tools/blender5.2/blender.exe', asset=ASSET,
            workspace=self.runroot / 'native', deadline_ns=self.deadline_ns, condition='P',
            expected_asset_sha256=ASSET_SHA, max_calls=16)
        self.native_handle = self.retain(self.native.process, 'NATIVE_RUNTIME_PROOF.json')
        self.start_product()
        self.ready_ns = time.perf_counter_ns()
        save(self.runroot / 'RUNTIME_START.json', self.snapshot())

    def retain(self, process, name):
        row, handle = proof._windows_runtime_proof(process, process.pid, self.deadline_ns)
        save(self.runroot / name, row)
        if row.get('confirmed') is not True:
            raise ValueError('owned_retained_process_identity_failed/' + name)
        return handle

    def start_product(self):
        config = self.runroot / 'PRODUCT_CONFIG.json'
        save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                      'project_root': self.binding['install_root'],
                      'state_file': str(self.runroot / 'product_state.json'),
                      'audit_file': str(self.runroot / 'product_audit.jsonl'),
                      'expected_identity': {'source_sha256': SOURCE_SHA}, 'request_budget_s': 30,
                      'blender': {'host': self.native.host, 'port': self.native.port, 'timeout_s': 30}})
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'mcp_entry.py'),
                   '--binding', str(BINDING), '--config', str(config), '--ledger', str(self.budget.root),
                   '--evidence', str(self.runroot / 'mcp_io'), '--phase', self.phase, '--label', self.label,
                   '--archive', str(self.runroot / 'product_full')]
        self.client = transport.StdioClient(command, self.runroot, self.runroot / 'mcp', self.deadline_ns)
        self.runtime_handle = self.retain(self.client.process, 'MCP_RUNTIME_PROOF.json')
        response = self.client.call(initialize('init-product'))
        save(self.runroot / 'INITIALIZE.json', response)
        identity = response['result']['_meta']['human_eye']
        if identity['source_sha256'] != SOURCE_SHA or identity['source_kind'] != 'installed_distribution':
            raise ValueError('actual_installed_public_identity_changed')
        self.client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listing = self.client.call({'jsonrpc': '2.0', 'id': 'list-product', 'method': 'tools/list'})
        save(self.runroot / 'MCP_TOOLS.json', listing)
        self.product_tools = copy.deepcopy(listing['result']['tools'])
        actual = [tool for tool in self.product_tools if tool['name'] == 'human_eye_scene_observe']
        if actual != [read(SCHEMA)]:
            raise ValueError('actual_installed_public_schema_changed')


def initialize(rpc_id):
    return {'jsonrpc': '2.0', 'id': rpc_id, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-03-26', 'capabilities': {},
        'clientInfo': {'name': 'cross-scale-diagnostic-only', 'version': '1.0'}}}
