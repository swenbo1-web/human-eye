"""Separate directed installed SDK injection through the ordinary MCP router."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, QUAL, ROOT, body, encoded, events, load_module, request, save, sha
from verify_state import verify


class PipeTape:
    """Observe the existing text pipe unchanged, retaining its exact UTF-8 text."""
    def __init__(self, pipe, output):
        self.pipe = pipe
        self.output = output

    def __getattr__(self, name):
        return getattr(self.pipe, name)

    def write(self, value):
        result = self.pipe.write(value)
        with self.output.open('ab') as stream:
            stream.write(value.encode('utf8'))
        return result

    def readline(self, count=-1):
        value = self.pipe.readline(count)
        with self.output.open('ab') as stream:
            stream.write(value.encode('utf8'))
        return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ready', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(HERE)
    output.mkdir(parents=True, exist_ok=False)
    ready = json.loads(args.ready.read_bytes())
    assert ready['commit'] == args.commit and ready['source_sha256'] == args.source_sha256
    qualification = json.loads((QUAL / 'QUALIFICATION_READY.json').read_bytes())
    assert sha(QUAL / 'assembly.blend') == qualification['asset_sha256']
    save(output / 'INPUT_BINDINGS.json', {'ready': ready, 'ready_sha256': sha(args.ready),
         'source_sha256': args.source_sha256, 'script_sha256': sha(Path(__file__)),
         'common_sha256': sha(HERE / 'common.py'), 'verifier_sha256': sha(HERE / 'verify_state.py'),
         'asset_sha256': qualification['asset_sha256'], 'main_five_sequence_member': False,
         'scope': 'base-only directed actual BlenderProcessHost plus installed SDK and ordinary MCP router',
         'product_calls_before_explicit_run': 0})
    if not args.run:
        print(json.dumps({'prepared_only': True, 'product_calls': 0}))
        return 0
    result = {'host_path': 'BlenderProcessHost', 'main_five_sequence_member': False,
              'errors': [], 'started_ns': time.perf_counter_ns(), 'timing_stages_ns': {}}
    host = None
    original_asset_hash = sha(QUAL / 'assembly.blend')
    copied = output / 'input.blend'
    shutil.copyfile(QUAL / 'assembly.blend', copied)
    assert sha(copied) == original_asset_hash
    try:
        entry = load_module('_scan_installed_sdk_bootstrap', Path(ready['entry']))
        proof = entry.validate_binding(expected_python=sys.executable)
        sys.path.insert(0, proof['module_root'])
        identity, origins = entry.verify_imported_runtime(proof)
        assert identity['source_sha256'] == args.source_sha256
        save(output / 'INSTALLED_PROOF.json', {'proof': proof, 'identity': identity, 'origins': origins})
        from human_eye_plugin.blender_process import BlenderProcessHost
        from human_eye_plugin.live_service import LiveSpatialService
        from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server

        class MeteredProcessHost(BlenderProcessHost):
            def _read_stdout(self):
                self._process.stdout = PipeTape(self._process.stdout, output / 'Blender_STDOUT_UTF8.bin')
                super()._read_stdout()

            def _read_stderr(self):
                self._process.stderr = PipeTape(self._process.stderr, output / 'Blender_STDERR_UTF8.bin')
                super()._read_stderr()

            def _request(self, command, params, *, timeout=None):
                if not isinstance(self._process.stdin, PipeTape):
                    self._process.stdin = PipeTape(self._process.stdin, output / 'Blender_STDIN_UTF8.bin')
                return super()._request(command, params, timeout=timeout)

        mark = time.perf_counter_ns()
        host = MeteredProcessHost('D:/Tools/blender5.2/blender.exe', copied, timeout=30., startup_timeout=60.)
        result['timing_stages_ns']['owned_Blender_start_and_capabilities'] = time.perf_counter_ns() - mark
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': ready['install_root'], 'state_file': str(output / 'state.json'),
                  'audit_file': str(output / 'audit.jsonl'), 'request_budget_s': 30.,
                  'expected_identity': {'source_sha256': args.source_sha256}}
        save(output / 'config.json', config)
        service = LiveSpatialService(output / 'config.json', host=host, production_mode=True)
        messages = [{'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'surface-scan-Process-directed', 'version': '001'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, request('process_base')]
        raw_input = b''.join(encoded(message) + b'\n' for message in messages)
        (output / 'MCP_TX.bin').write_bytes(raw_input)
        incoming = io.StringIO(raw_input.decode('utf8'))
        outgoing = io.StringIO()
        mark = time.perf_counter_ns()
        run_stdio_mcp_server(service, input_stream=incoming, output_stream=outgoing)
        result['timing_stages_ns']['MCP_metadata_base_scan_and_close'] = time.perf_counter_ns() - mark
        raw_output = outgoing.getvalue().encode('utf8')
        (output / 'MCP_RX.bin').write_bytes(raw_output)
        responses = [json.loads(line) for line in raw_output.splitlines()]
        response = next(row for row in responses if row['id'] == 'process_base')
        result['body'] = body(response)
        audits = events(output / 'audit.jsonl')
        private = [row for row in audits if row.get('event') == 'observe'
                   and row.get('trace_id') == result['body']['trace_id']]
        assert len(private) == 1
        result['diagnostics'] = private[0]['task_work']
        result['verification'] = verify(result['body'], result['diagnostics'],
            json.loads((QUAL / 'BASE_TRUTH.json').read_bytes()),
            json.loads((QUAL / 'BASE_SNAPSHOT.json').read_bytes()), args.source_sha256)
        commands = [json.loads(line) for line in (output / 'Blender_STDIN_UTF8.bin').read_bytes().splitlines()]
        result['actual_commands'] = [row['command'] for row in commands]
        assert result['actual_commands'] == ['capabilities', 'capture_surface_scan', 'shutdown']
        result['audit'] = audits
        result['no_product_setters_or_save_commands'] = True
        identity, origins = entry.verify_imported_runtime(proof)
        result['installed_source_still_verified'] = True
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error),
                                 'traceback': traceback.format_exc()})
    finally:
        if host is not None:
            try:
                host.close()
                result['close'] = {'process_reaped': host._process.poll() is not None,
                    'exit_code': host._process.poll(), 'stdout_stopped': not host._stdout_thread.is_alive(),
                    'stderr_stopped': not host._stderr_thread.is_alive(), 'diagnostics': host.diagnostics}
                assert result['close']['process_reaped'] and result['close']['exit_code'] == 0
                assert result['close']['stdout_stopped'] and result['close']['stderr_stopped']
            except BaseException as error:
                result['errors'].append({'stage': 'close', 'error': repr(error)})
        result['original_asset_unchanged'] = sha(QUAL / 'assembly.blend') == original_asset_hash
        result['owned_copy_not_saved'] = sha(copied) == original_asset_hash
        result['ended_ns'] = time.perf_counter_ns()
        result['passed'] = (not result['errors'] and result.get('verification', {}).get('passed')
                            and result['original_asset_unchanged'] and result['owned_copy_not_saved'])
        save(output / 'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'errors': result['errors']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
