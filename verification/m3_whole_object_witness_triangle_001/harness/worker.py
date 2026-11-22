"""Installed production stdio; only the original capture RPC is replayed."""

import argparse
from copy import deepcopy
import os
from pathlib import Path
from runpy import run_path
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fixtures import EXTERNAL, LABELS, ORIGINAL_ROOT, V, append, fixture, pin, read, require, save


def worker(root, binding_path, label, evidence):
    root = root.resolve()
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'new_isolated_replay_root_required')
    root.mkdir(parents=True, exist_ok=False)
    original = fixture(label)
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    helper_path = V / 'm4_live_source_region_task_003/harness/reused/verified_bootstrap.py'
    guard = run_path(str(helper_path))['bootstrap'](binding)
    from human_eye_plugin import live_service, production_server
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost
    from human_eye_plugin.runtime_identity import runtime_identity
    metadata = run_path(str(V / 'm4_live_source_region_task_003/harness/mcp_entry.py'))['read_context_metadata']

    identity = runtime_identity(mode='live')
    require(identity['source_sha256'] == binding['source_sha256']
            and identity['source_kind'] == 'installed_distribution', 'actual_pinned_install_required')
    counts = {'host_requests': 0, 'observe_calls': 0, 'network_attempts': 0,
              'old_write_attempts': 0, 'PNG_open_attempts': 0, 'raster_attempt_events': 0}

    def audit(event, args):
        if event == 'socket.connect':
            counts['network_attempts'] += 1
            raise AssertionError('no_live_network_allowed')
        if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        mode, flags = args[1:3]
        writing = (isinstance(mode, str) and any(ch in mode for ch in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and path.is_relative_to(ORIGINAL_ROOT.resolve()):
            counts['old_write_attempts'] += 1
            raise AssertionError('original_evidence_write_forbidden')
        if path.suffix.lower() == '.png':
            counts['PNG_open_attempts'] += 1
            raise AssertionError('no_image_IO_in_whole_task_replay')

    sys.addaudithook(audit)

    class Host(BlenderMCPHost):
        def _request(self, command, params):
            expected = {'selectors': original['request']['params']['arguments']['query']['objects']}
            require(command == 'capture_task' and params == expected,
                    'only_exact_original_ordered_capture_task_allowed')
            self._ensure_live()
            began = time.perf_counter_ns()
            value = self._scene_decoder.apply(deepcopy(original['task_delta']))
            self._record_observation_document(value)
            counts['host_requests'] += 1
            ordinal = counts['host_requests']
            path = root / ('CAPTURE_' + str(ordinal).zfill(2) + '.json')
            save(path, value)
            append(root / 'HOST_CALLS.jsonl', {'index': ordinal, 'command': command, 'params': params,
                'started_ns': began, 'closed_ns': time.perf_counter_ns(), 'capture': pin(path),
                'scope': 'original selected capture via normal SceneDeltaDecoder; no Blender'})
            return value

    host = Host(binding['install_root'])
    primed = host._scene_decoder.apply(deepcopy(original['prime_delta']))
    save(root / 'RESOURCE_PRIME.json', {'source_pins': original['pins'],
        'resources': len(original['prime_delta']['resources']), 'decoded_full_meshes': len(primed['meshes']),
        'actual_host_requests': 0, 'scope': 'original transport resource cache initialization only; not a service capture or solver call'})
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

    streams = Streams()
    holder = {}

    class Service(original_service):
        def __init__(self, *args, **kwargs):
            require(not holder and 'host' not in kwargs, 'one_actual_service_required')
            super().__init__(*args, host=host, **kwargs)
            holder['service'] = self

        def observe(self, *args, **kwargs):
            counts['observe_calls'] += 1
            folder = root / ('call_' + str(counts['observe_calls']).zfill(2))
            folder.mkdir()
            before = metadata(self)
            began = time.perf_counter_ns()
            value = super().observe(*args, **kwargs)
            returned = time.perf_counter_ns()
            save(folder / 'SERVICE_RESULT.json', value)
            save(folder / 'READ_CONTEXT.json', {'before': before, 'after': metadata(self)})
            save(folder / 'RECEIPT.json', {'started_ns': began, 'returned_ns': returned,
                'elapsed_ns': returned - began, 'original_returned_object': True,
                'scope': 'normal actual service and solver; passive metadata outside elapsed boundary'})
            return value

        def record_event(self, event, **fields):
            if event in ('active_observation_render_attempt', 'source_region_render_attempt'):
                counts['raster_attempt_events'] += 1
                raise AssertionError('unexpected_render_attempt')
            append(root / 'PRODUCT_EVENTS.jsonl', {'event': event, **fields})
            return super().record_event(event, **fields)

        def close(self):
            if hasattr(self, '_replay_closed'):
                return
            close = getattr(super(), 'close', None)
            if callable(close):
                close()
            else:
                host.close()
            self._replay_closed = True
            save(root / 'EOF.json', {'closed': not host.is_alive, 'pid': os.getpid(),
                'input_eof_observed': streams.eof, 'source_sha256': binding['source_sha256'], **counts,
                'old_inputs_unchanged': all(pin(row['path']) == row for row in original['pins']),
                'actual_Blender_starts': 0, 'actual_models': 0, 'actual_rasters': 0,
                'geometry_algorithm_substitutions': 0, 'producer_result_substitutions': 0})

    config = root / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': binding['install_root'], 'state_file': str(root / 'product_state.json'),
        'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': 30,
        'expected_identity': {'source_sha256': binding['source_sha256']}})
    argv = ['--config', str(config)] + (['--region-task-evidence'] if evidence else [])
    save(root / 'INPUTS.json', {'binding': pin(binding_path), 'identity': identity,
        'source_pins': original['pins'], 'bootstrap': pin(helper_path), 'production_argv': argv,
        'original_slot': label, 'original_request': original['request'],
        'original_failed_task_preserved': label == 'P2',
        'overrides': ['capture_task RPC receives exact original selected delta'],
        'geometry_algorithm_substitutions': 0, 'producer_result_substitutions': 0})
    for name, value in (('ORIGINAL_REQUEST', original['request']), ('ORIGINAL_RESPONSE', original['response']),
                        ('ORIGINAL_PRODUCER', original['producer']), ('ORIGINAL_SUPPLEMENT', original['supplement'])):
        save(root / (name + '.json'), value)
    exited = {'pid': os.getpid(), 'source_sha256': binding['source_sha256'], 'production_returned': False}
    try:
        live_service.LiveSpatialService = Service
        sys.stdin = sys.stdout = streams
        code = production_server.main(argv)
        exited.update(production_returned=True, production_return_code=code)
        return code
    except BaseException as error:
        exited['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        live_service.LiveSpatialService = original_service
        sys.stdin, sys.stdout = incoming, outgoing
        service = holder.get('service')
        if service is not None:
            service.close()
        else:
            host.close()
        guard.verify_loaded()
        exited.update(input_eof_observed=streams.eof, installed_source_verified=True,
                      service_constructed=service is not None, closed_ns=time.perf_counter_ns())
        save(root / 'WORKER_EXIT.json', exited)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_no_bytecode_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--case', choices=LABELS, required=True)
    parser.add_argument('--region-task-evidence', action='store_true')
    args = parser.parse_args()
    raise SystemExit(worker(args.worker, args.binding, args.case, args.region_task_evidence))
