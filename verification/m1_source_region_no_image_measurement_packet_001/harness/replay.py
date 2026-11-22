"""Actual installed production stdio; only archived acquisition is substituted.

Source/ref validation, public argument rejection, formatting and PNG encoding
are the installed product. There is no model, Blender connection or renderer.
"""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
from runpy import run_path
import sys
import time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fixtures import archived, compact, dataset, pin, read, require

V = HERE.parent.parent
EXTERNAL = Path('D:/he_m1_source_region_no_image_measurement_packet_001')


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(compact(value) + b'\n')


def append(path, value):
    with Path(path).open('ab') as stream:
        stream.write(compact(value) + b'\n')


def worker(root, binding_path, name, evidence):
    root = Path(root).resolve()
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'isolated_new_output_required')
    root.mkdir(parents=True, exist_ok=False)
    data = dataset(name)
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    helper = run_path(str(V / 'm4_live_source_region_task_003/harness/reused/verified_bootstrap.py'))
    guard = helper['bootstrap'](binding)
    from human_eye_plugin import live_service, production_server
    from human_eye_plugin.query_policy import validate_query
    from human_eye_plugin.source_region import validate_region_ref
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity(mode='live')
    require(identity['source_sha256'] == binding['source_sha256'], 'actual_install_source_changed')
    records = data['records']
    expected = validate_query(records[0]['request']['query'])
    captured = data.get('capture')
    if expected['mode'] == 'source_region' and captured is None:
        rec = records[0]
        terminal, tp = archived(rec['batch'], 'slots/' + rec['slot'] + '/TERMINAL_SOURCE.json')
        objects = {row['object_id']: row for row in terminal['objects']}
        captured = {'meshes': [{'faces': objects[row['host_id']]['evaluated']['triangles']}
                   for row in rec['producer']['binding']['objects']]}
        data['pins'] = [*data['pins'], tp]
    counters = {'service_calls': 0, 'dispatches': 0, 'host_attempts': 0, 'socket_attempts': 0,
                'blocked_old_writes': 0, 'actual_new_rasters': 0, 'actual_models': 0}
    phase = {'value': 'startup'}
    old_roots = [Path('D:/he_' + row['batch']).resolve() for row in records]

    def audit(event, args):
        if event == 'socket.connect':
            counters['socket_attempts'] += 1
            raise AssertionError('replay_network_forbidden')
        if event != 'open' or not args or not isinstance(args[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and any(path.is_relative_to(old) for old in old_roots):
            counters['blocked_old_writes'] += 1
            raise AssertionError('archived_runtime_write_forbidden')
        if path.suffix.lower() == '.png':
            append(root / 'PNG_READS.jsonl', {'path': str(path), 'phase': phase['value'],
                                           'opened_ns': time.perf_counter_ns(), 'writing': writing})

    sys.addaudithook(audit)
    original = live_service.LiveSpatialService
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

        def write(self, text):
            return outgoing.write(text)

        def flush(self):
            return outgoing.flush()

    streams = Streams()

    class NoHost:
        def __getattr__(self, key):
            if key in ('runtime_identity', 'runtime_manifest', 'verify_readonly_source', 'package_identity', 'source_identity'):
                raise AttributeError(key)
            counters['host_attempts'] += 1
            raise AssertionError('no_actual_host_allowed/' + key)

    class Replay(original):
        def __init__(self, config, *, production_mode=False):
            super().__init__(config, host=NoHost(), production_mode=production_mode)

        def _acquire(self, query, include_image):
            normalized = validate_query(query)
            first = records[0]['producer']
            if 'region_ref' in normalized:
                validate_region_ref(captured, normalized['region_ref'], _binding=first['binding'],
                    _ordered_geometry_sha256=first['region_ref']['ordered_geometry_sha256'])
                require(normalized['region_ref'] == first['region_ref'], 'different_valid_region_not_registered')
                normalized = {key: value for key, value in normalized.items() if key != 'region_ref'}
                normalized['region'] = deepcopy(expected['region'])
            require(normalized == expected and include_image == records[0]['request']['include_image'],
                    'exact_archived_acquisition_query_required')
            ordinal = counters['dispatches'] + 1
            record = records[min(ordinal - 1, len(records) - 1)]
            value = deepcopy(record['producer'])
            counters['dispatches'] = ordinal
            save(root / ('PRODUCER_' + str(ordinal).zfill(2) + '.json'), value)
            append(root / 'DISPATCHES.jsonl', {'ordinal': ordinal, 'query': query, 'include_image': include_image,
                'archive_case': record['case'], 'original_producer': record['producer_source'] if 'producer_source' in record else record['pins'][0],
                'mutations': data['mutations'], 'binding_unchanged': value['binding'] == record['producer']['binding']})
            if expected['mode'] == 'source_region':
                selected = value['facts']['region']['host_id']
                index, = [i for i, obj in enumerate(value['binding']['objects']) if obj['host_id'] == selected]
                context = self._read_context
                context.activate(value['binding'], 'source_region', query)
                private = SimpleNamespace(region_ref=value['region_ref'], observation=value, binding=value['binding'],
                    meshes=[SimpleNamespace(faces=mesh['faces']) for mesh in captured['meshes']], object_index=index,
                    source_triangle_indices=value['region_ref']['source_triangle_indices'])
                context.prepared('source_regions', lambda: {'regions': {value['region_ref']['region_id']: private}})
            return value

        def _observe_source_region(self, session_id, query, *, include_image):
            return self._acquire(query, include_image)

        def _observe_active_observation(self, session_id, *, include_image, selector=None, task_query=None, region_task=None):
            query = {'mode': 'active_observation'}
            if selector is not None:
                query['objects'] = [selector]
            if task_query is not None:
                query['task_query'] = task_query
            if region_task is not None:
                query['region_task'] = region_task
            return self._acquire(query, include_image)

        def observe(self, *args, **kwargs):
            counters['service_calls'] += 1
            ordinal = counters['service_calls']
            phase['value'] = 'observe_' + str(ordinal)
            try:
                value = super().observe(*args, **kwargs)
                save(root / ('SERVICE_' + str(ordinal).zfill(2) + '.json'), value)
                return value
            finally:
                phase['value'] = 'public_encoding_after_' + str(ordinal)

        def record_event(self, event, **fields):
            append(root / 'PRODUCT_EVENTS.jsonl', {'event': event, **fields})

        def close(self):
            guard.verify_loaded()
            unchanged = all(pin(row['path']) == row for row in data['pins'])
            save(root / 'EOF.json', {'closed': True, 'pid': os.getpid(), 'input_eof_observed': streams.eof,
                **counters, 'source_sha256': binding['source_sha256'], 'archived_inputs_unchanged': unchanged,
                'override_scope': 'archived acquisition only; installed arguments/ref-validator/service wrapper/production MCP/encoding'})

    config = root / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': binding['install_root'], 'state_file': data['config']['state_file'],
        'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': 30,
        'expected_identity': {'source_sha256': binding['source_sha256']}})
    argv = ['--config', str(config)] + (['--region-task-evidence'] if evidence else [])
    save(root / 'INPUTS.json', {'binding': pin(binding_path), 'identity': identity,
        'source_pins': data['pins'], 'mutations': data['mutations'], 'derivation': data.get('derivation'),
        'original_state_path': data['config']['state_file'], 'production_argv': argv,
        'raw_producer_identity_preserved': True, 'actual_models': 0, 'actual_new_rasters': 0})
    try:
        live_service.LiveSpatialService = Replay
        sys.stdin = sys.stdout = streams
        return production_server.main(argv)
    finally:
        live_service.LiveSpatialService = original
        sys.stdin, sys.stdout = incoming, outgoing


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--region-task-evidence', action='store_true')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_no_bytecode_required')
    raise SystemExit(worker(args.worker, args.binding, args.case, args.region_task_evidence))
