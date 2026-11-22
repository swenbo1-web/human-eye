"""Owned live runtime using the actual standard or evidence production endpoint."""

from pathlib import Path
import queue
import sys

from common import (CATALOGUE, EXTERNAL, HERE, NS, PRODUCT_SCHEMA, SOURCE_SHA,
                    catalogue_for, evidence_enabled, load_retained, read, save, sha)


previous = load_retained('_region_task_working_dense_runtime',
                         NS.parent / 'perf050_dense_micro_surface_holdout_recovery_001/harness/runtime.py')
transport = previous.previous.transport


class ProductionStdioClient(transport.StdioClient):
    """Retain the original held-process close and separately bind real EOF."""

    def __init__(self, command, cwd, output, deadline_ns, *, worker_evidence):
        self.worker_evidence = Path(worker_evidence)
        self._production_close = None
        super().__init__(command, cwd, output, deadline_ns)

    def finish(self):
        if self._production_close is not None:
            return self._production_close
        original = super().finish()
        record = dict(original)
        record['errors'] = list(original.get('errors', []))
        eof_seen, remaining_replies = False, 0
        reader_errors = []
        while True:
            try:
                kind, value, observed_ns = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'eof':
                eof_seen = True
                record['stdout_eof_observed_ns'] = observed_ns
            elif kind == 'reply':
                remaining_replies += 1
            elif kind == 'error':
                reader_errors.append(value)
        # A call that consumed EOF has already recorded the exact reader event
        # as its generated stdio_eof error; do not require a second EOF event.
        eof_in_call = any((row.get('error') or {}).get('message') == 'stdio_eof:None'
                          for row in self.records)
        record.update(stdout_eof_seen=eof_seen or eof_in_call,
                      stdout_eof_consumed_by_call=eof_in_call,
                      unconsumed_response_lines=remaining_replies, reader_errors=reader_errors,
                      original_close_path=str(self.output / 'CLOSE.json'))
        evidence_valid = False
        try:
            eof_path = self.worker_evidence / 'EOF.json'
            exit_path = self.worker_evidence / 'WORKER_EXIT.json'
            eof, exited = read(eof_path), read(exit_path)
            evidence_valid = (
                eof['pid'] == exited['pid'] == self.process.pid
                and eof['source_sha256'] == exited['source_sha256'] == SOURCE_SHA
                and eof['closed'] is True and eof['host_close_called'] is True
                and eof['input_eof_observed'] is True and exited['input_eof_observed'] is True
                and exited['production_returned'] is True and exited['production_return_code'] == 0
                and exited['service_constructed'] is True and exited['installed_source_verified'] is True
                and 'error' not in eof and 'error' not in exited
            )
            record.update(worker_eof={'path': str(eof_path), 'sha256': sha(eof_path)},
                          worker_exit={'path': str(exit_path), 'sha256': sha(exit_path)})
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            record['worker_evidence_error'] = {'type': type(error).__name__, 'message': str(error)}
        record['production_eof_and_exit_verified'] = evidence_valid
        record['confirmed'] = (
            original.get('confirmed') is True and record['stdout_eof_seen']
            and remaining_replies == 0 and not reader_errors and evidence_valid
        )
        self._production_close = record
        save(self.output / 'HELD_CLOSE.json', record)
        return record


class Runtime(previous.Runtime):
    def _start_public_mcp(self, binding_path, binding):
        path = self.folder / 'PRODUCT_CONFIG.json'
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': binding['install_root'], 'state_file': str(self.folder / 'product_state.json'),
                  'audit_file': str(self.folder / 'product_audit.jsonl'),
                  'expected_identity': {'source_sha256': SOURCE_SHA}, 'request_budget_s': 30,
                  'blender': {'host': self.native.host, 'port': self.native.port, 'timeout_s': 30}}
        save(path, config)
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'mcp_entry.py'),
                   '--binding', str(binding_path), '--config', str(path), '--ledger', str(self.budget.root),
                   '--evidence', str(self.folder / 'mcp_io'), '--phase', self.phase, '--label', self.label,
                   '--archive', str(self.folder / 'product_full')]
        if evidence_enabled(self.label):
            command.append('--region-task-evidence')
        self.client = ProductionStdioClient(command, self.folder, self.folder / 'mcp', self.task_deadline,
                                            worker_evidence=self.folder / 'mcp_io')
        self.mcp_handle = self._retain(self.client.process, 'MCP_RUNTIME_PROOF.json')
        initial = self.client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'region-task-first-packet-holdout', 'version': '001'}}})
        identity = initial['result']['_meta']['human_eye']
        if identity['source_sha256'] != SOURCE_SHA or identity['source_kind'] != 'installed_distribution':
            raise ValueError('actual_production_product_identity_changed')
        self.client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listed = self.client.call({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'})
        self.product_tools = listed['result']['tools']
        if self.product_tools != read(catalogue_for(self.label)):
            raise ValueError('actual_production_arm_catalogue_changed')
        observes = [row for row in self.product_tools if row['name'] == 'human_eye_scene_observe']
        schema = read(PRODUCT_SCHEMA)
        expected = schema.get('inputSchema', schema)
        if len(observes) != 1 or observes[0]['inputSchema'] != expected:
            raise ValueError('actual_production_observe_input_schema_changed')
        save(self.folder / 'MCP_IDENTITY.json', identity)
