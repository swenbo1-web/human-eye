"""Run installed MCP stdio with the fixed synthetic capture at the host boundary."""
import argparse
from copy import deepcopy
import os
from pathlib import Path
from runpy import run_path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import EXTERNAL, LABELS, V, append, fixture, pin, read, require, save


def run(root, binding_path, label, evidence):
    root = root.resolve()
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'new_static_relation_worker_required')
    root.mkdir(exist_ok=False)
    frozen = fixture(label)
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    helper = V / 'm4_live_source_region_task_003/harness/reused/verified_bootstrap.py'
    guard = run_path(str(helper))['bootstrap'](binding)
    from human_eye_plugin import live_service, production_server
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity(mode='live')
    require(identity['source_sha256'] == binding['source_sha256']
            and identity['source_kind'] == 'installed_distribution', 'pinned_install_required')
    save(root / 'STATIC_CAPTURE.json', frozen['capture'])
    original_capture = pin(root / 'STATIC_CAPTURE.json')
    protected = (V.resolve(), Path(binding['install_root']).resolve())
    counts = dict(host_requests=0, observe_calls=0, network_attempts=0,
                  old_write_attempts=0, PNG_open_attempts=0, raster_attempt_events=0)

    def audit(event, args):
        if event in ('socket.connect', 'subprocess.Popen'):
            counts['network_attempts'] += 1
            raise AssertionError('external_host_requests_forbidden')
        if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(ch in mode for ch in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and (path.suffix.lower() == '.blend' or path == root / 'STATIC_CAPTURE.json'
                        or any(path.is_relative_to(p) for p in protected)):
            counts['old_write_attempts'] += 1
            raise AssertionError('protected_source_write_forbidden')
        if path.suffix.lower() == '.png':
            counts['PNG_open_attempts'] += 1
            raise AssertionError('unexpected_image_io')

    sys.addaudithook(audit)

    class Host(BlenderMCPHost):
        def _request(self, command, params):
            expected = {'selectors': frozen['request']['params']['arguments']['query']['objects']}
            require(command == 'capture_task' and params == expected, 'static_selected_capture_task_only')
            self._ensure_live()
            started = time.perf_counter_ns()
            result = self._scene_decoder.apply(deepcopy(frozen['capture']))
            self._record_observation_document(result)
            counts['host_requests'] += 1
            output = root / f"CAPTURE_{counts['host_requests']:02d}.json"
            save(output, result)
            append(root / 'HOST_CALLS.jsonl', {'command': command, 'params': params,
                                               'started_ns': started, 'ended_ns': time.perf_counter_ns(),
                                               'capture': pin(output)})
            return result

    host = Host(binding['install_root'])
    original_service = live_service.LiveSpatialService
    incoming, outgoing = sys.stdin, sys.stdout

    class Streams:
        def __init__(self):
            self.buffer = self
            self.eof = False

        def readline(self, size=-1):
            raw = incoming.buffer.readline(size)
            if not raw:
                self.eof = True
            return raw

        def write(self, value):
            return outgoing.write(value)

        def flush(self):
            return outgoing.flush()

    stream = Streams()
    holder = {}

    class Service(original_service):
        def __init__(self, *args, **kwargs):
            require(not holder and 'host' not in kwargs, 'one_installed_service')
            super().__init__(*args, host=host, **kwargs)
            holder['service'] = self

        def observe(self, *args, **kwargs):
            counts['observe_calls'] += 1
            folder = root / f"call_{counts['observe_calls']:02d}"
            folder.mkdir()
            began = time.perf_counter_ns()
            value = super().observe(*args, **kwargs)
            elapsed = time.perf_counter_ns() - began
            save(folder / 'SERVICE_RESULT.json', value)
            save(folder / 'RECEIPT.json', {'service_elapsed_ns': elapsed})
            return value

        def record_event(self, event, **fields):
            if event in ('active_observation_render_attempt', 'source_region_render_attempt'):
                counts['raster_attempt_events'] += 1
                raise AssertionError('unexpected_render_attempt')
            append(root / 'PRODUCT_EVENTS.jsonl', {'event': event, **fields})
            return super().record_event(event, **fields)

        def close(self):
            if not host.is_alive:
                return
            close = getattr(super(), 'close', None)
            if callable(close):
                close()
            else:
                host.close()
            save(root / 'EOF.json', {'closed': not host.is_alive, 'pid': os.getpid(),
                 'input_eof_observed': stream.eof, 'old_inputs_unchanged': pin(root / 'STATIC_CAPTURE.json') == original_capture,
                 **counts})

    config = root / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': binding['install_root'], 'state_file': str(root / 'product_state.json'),
                  'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': 30,
                  'expected_identity': {'source_sha256': binding['source_sha256']}})
    argv = ['--config', str(config)] + (['--region-task-evidence'] if evidence else [])
    save(root / 'INPUTS.json', {'capture': original_capture, 'binding': pin(binding_path), 'identity': identity,
                                'bootstrap': pin(helper), 'production_argv': argv, 'fixture': frozen['capture_kind'],
                                'geometry_algorithm_substitutions': 0, 'producer_result_substitutions': 0})
    exited = {'pid': os.getpid(), 'source_sha256': binding['source_sha256'], 'production_returned': False}
    try:
        live_service.LiveSpatialService = Service
        sys.stdin = sys.stdout = stream
        code = production_server.main(argv)
        exited.update(production_returned=True, production_return_code=code)
        return code
    except BaseException as error:
        exited['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        live_service.LiveSpatialService = original_service
        sys.stdin, sys.stdout = incoming, outgoing
        if holder.get('service') is not None:
            holder['service'].close()
        else:
            host.close()
        guard.verify_loaded()
        exited.update(input_eof_observed=stream.eof, installed_source_verified=True,
                      closed_ns=time.perf_counter_ns())
        save(root / 'WORKER_EXIT.json', exited)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_no_bytecode_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--case', choices=LABELS, required=True)
    parser.add_argument('--region-task-evidence', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(args.worker, args.binding, args.case, args.region_task_evidence))
