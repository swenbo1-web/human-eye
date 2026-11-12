"""Actual ProcessHost cold/repeat/edit with a fixed QA-only worker wrapper."""
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
from common import HERE, ROOT, QUAL, WORKER, qualification_binding, bind_snapshot, body, encoded, events, load_module, request, save, sha
from verify_state import verify
from summarize import reuse_mapping

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
    qualification, promised = qualification_binding()
    ready = json.loads(args.ready.read_bytes())
    assert ready['commit'] == args.commit and ready['source_sha256'] == args.source_sha256
    files = {str(path.resolve()): sha(path) for path in [
        Path(__file__), HERE/'process_worker.py', HERE/'common.py', HERE/'verify_state.py',
        HERE/'summarize.py', args.ready, QUAL/'export_snapshot.py',
        ROOT/'verification/m4_grooved_rail_transfer_001/oracle/exact_geometry.py']}
    files.update(promised)
    save(output/'INPUT_BINDINGS.json', {'ready': ready, 'files': files,
        'scope': 'new candidate actual ProcessHost plus QA-only stdin wrapper, cold/repeat/edit',
        'main_five_pair_member': False, 'planned_business_states': ['cold','repeat','edit'],
        'worker_path_is_custom_QA_wrapper': True, 'product_calls_before_gate': 0})
    if not args.run:
        print(json.dumps({'prepared_only': True, 'product_calls': 0}))
        return 0
    result = {'errors': [], 'business': [], 'started_ns': time.perf_counter_ns(),
        'host_path': 'BlenderProcessHost', 'worker_path_is_custom_QA_wrapper': True,
        'timing_stages_ns': {}, 'RPC': []}
    host = None
    copied = output/'input.blend'
    shutil.copyfile(QUAL/'assembly.blend', copied)
    assert sha(copied) == qualification['asset_sha256']
    try:
        entry = load_module('_opt1_installed_process_entry', Path(ready['entry']))
        proof = entry.validate_binding(expected_python=sys.executable)
        sys.path.insert(0, proof['module_root'])
        identity, origins = entry.verify_imported_runtime(proof)
        assert identity['source_sha256'] == args.source_sha256
        save(output/'INSTALLED_PROOF.json', {'proof': proof, 'identity': identity, 'origins': origins})
        from human_eye_plugin.blender_process import BlenderProcessHost
        from human_eye_plugin.live_service import LiveSpatialService
        from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
        worker = output/'qa_worker.py'
        worker.write_bytes((HERE/'process_worker.py').read_bytes())
        source_hashes = {row['path']: row['sha256'] for row in identity['source_files']}
        save(worker.with_suffix('.json'), {'install_root': ready['install_root'],
            'asset': str(copied), 'asset_sha256': qualification['asset_sha256'],
            'wrapper_sha256': sha(worker), 'worker_sha256': source_hashes['human_eye_plugin/blender_worker.py'],
            'pose_helper': str(WORKER/'pose_native.py'), 'pose_helper_sha256': qualification['pose_helper_sha256'],
            'pose_patch': str(WORKER/'POSE_PATCH.json'), 'pose_patch_sha256': qualification['pose_patch_sha256'],
            'snapshot_exporter': str(QUAL/'export_snapshot.py'),
            'snapshot_exporter_sha256': sha(QUAL/'export_snapshot.py'),
            'deadline_ns': time.perf_counter_ns()+120*10**9})

        class MeteredProcessHost(BlenderProcessHost):
            def _read_stdout(self):
                self._process.stdout = PipeTape(self._process.stdout, output/'Blender_STDOUT_UTF8.bin')
                super()._read_stdout()

            def _read_stderr(self):
                self._process.stderr = PipeTape(self._process.stderr, output/'Blender_STDERR_UTF8.bin')
                super()._read_stderr()

            def _request(self, command, params, *, timeout=None):
                if not isinstance(self._process.stdin, PipeTape):
                    self._process.stdin = PipeTape(self._process.stdin, output/'Blender_STDIN_UTF8.bin')
                mark = time.perf_counter_ns()
                try:
                    return super()._request(command, params, timeout=timeout)
                finally:
                    result['RPC'].append({'command': command, 'started_ns': mark,
                        'ended_ns': time.perf_counter_ns()})

        mark = time.perf_counter_ns()
        host = MeteredProcessHost('D:/Tools/blender5.2/blender.exe', copied,
            timeout=30., startup_timeout=60., worker_path=worker)
        result['timing_stages_ns']['owned_Blender_start_and_capabilities'] = time.perf_counter_ns()-mark
        config = {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
            'project_root': ready['install_root'], 'state_file': str(output/'state.json'),
            'audit_file': str(output/'audit.jsonl'), 'request_budget_s': 30.,
            'expected_identity': {'source_sha256': args.source_sha256}}
        save(output/'config.json', config)
        service = LiveSpatialService(output/'config.json', host=host, production_mode=True)
        source = None

        class Output(io.StringIO):
            def write(self, value):
                written = super().write(value)
                response = json.loads(value)
                if result['business'] and response.get('id') == result['business'][-1]['state']:
                    row = result['business'][-1]
                    row['ended_ns'] = time.perf_counter_ns()
                    row['response'] = response
                    row['body'] = body(response)
                    row['complete_client_request_ns'] = row['ended_ns']-row['started_ns']
                return written

        class Input:
            def __init__(self):
                self.index = 0

            def readline(self, limit=-1):
                nonlocal source
                if self.index >= 3:
                    row = result['business'][-1]
                    audit = events(output/'audit.jsonl')
                    selected = [event for event in audit if event.get('event') == 'observe'
                        and event.get('trace_id') == row['body']['trace_id']]
                    assert len(selected) == 1
                    row['diagnostics'] = selected[0]['task_work']
                    state = 'EDIT' if row['state'] == 'edit' else 'BASE'
                    row['verification'] = verify(row['body'], row['diagnostics'],
                        json.loads((QUAL/(state+'_TRUTH.json')).read_bytes()), source, args.source_sha256)
                    row['actual_host_RPC'] = sum(part['command'] == 'capture_surface_scan'
                        and row['started_ns'] <= part['started_ns'] <= row['ended_ns'] for part in result['RPC'])
                if self.index == 0:
                    message = {'jsonrpc':'2.0','id':'init','method':'initialize','params':{
                        'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'opt1-process-QA','version':'1'}}}
                elif self.index == 1:
                    message = {'jsonrpc':'2.0','method':'notifications/initialized'}
                elif self.index <= 4:
                    state = ('cold','repeat','edit')[self.index-2]
                    if state in ('cold','edit'):
                        if state == 'edit':
                            save(output/'POSE_ADVANCE.json', host._request('qa_advance',
                                {'patch_sha256': qualification['pose_patch_sha256']}))
                        source = host._request('qa_snapshot', {'state':'edit' if state == 'edit' else 'base'})
                        reference = json.loads((QUAL/('EDIT_SNAPSHOT.json' if state == 'edit' else 'BASE_SNAPSHOT.json')).read_bytes())
                        save(output/(state+'_SOURCE_BINDING.json'), bind_snapshot(source, reference))
                        save(output/(state+'_ACTUAL_SNAPSHOT.json'), source)
                    message = request(state)
                    result['business'].append({'state': state, 'request': message,
                        'started_ns': time.perf_counter_ns(), 'errors': []})
                else:
                    return ''
                self.index += 1
                encoded_message = encoded(message).decode()+'\n'
                with (output/'MCP_TX.bin').open('ab') as stream:
                    stream.write(encoded_message.encode())
                return encoded_message

        outgoing = Output()
        run_stdio_mcp_server(service, input_stream=Input(), output_stream=outgoing)
        (output/'MCP_RX.bin').write_text(outgoing.getvalue(), encoding='utf8', newline='\n')
        result['audit'] = events(output/'audit.jsonl')
        result['reuse_mapping'] = reuse_mapping(result)
        entry.verify_imported_runtime(proof)
        result['installed_source_still_verified'] = True
    except BaseException as error:
        result['errors'].append({'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
    finally:
        if host is not None:
            try:
                host.close()
                result['close'] = {'process_reaped':host._process.poll() is not None,
                    'exit_code':host._process.poll(),'stdout_stopped':not host._stdout_thread.is_alive(),
                    'stderr_stopped':not host._stderr_thread.is_alive()}
                assert all(result['close'][key] for key in ('process_reaped','stdout_stopped','stderr_stopped'))
                assert result['close']['exit_code'] == 0
                closed = json.loads((output/'QA_CLOSED.json').read_bytes())
                result['qa_closed'] = closed
                assert closed['strict_sequence_finished'] and closed['qa_advanced_once']
                assert closed['asset_unchanged'] and closed['final_scene_fingerprint'] == closed['accepted_scene_fingerprint']
                assert closed['normal_commands'] == ['capabilities','capture_surface_scan','capture_surface_scan','capture_surface_scan','shutdown']
            except BaseException as error:
                result['errors'].append({'stage':'close','error':repr(error)})
        result['sources_unchanged'] = all(sha(Path(path)) == value for path,value in files.items())
        result['original_asset_unchanged'] = sha(QUAL/'assembly.blend') == qualification['asset_sha256']
        result['owned_copy_not_saved'] = sha(copied) == qualification['asset_sha256']
        result['ended_ns'] = time.perf_counter_ns()
        result['passed'] = (not result['errors'] and len(result['business']) == 3
            and all(row.get('verification',{}).get('passed') for row in result['business'])
            and result['sources_unchanged'] and result['original_asset_unchanged'] and result['owned_copy_not_saved'])
        save(output/'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'errors':result['errors']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

