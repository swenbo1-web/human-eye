"""Frozen 326 qualification worker, with a removable QA diagnostic clone."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import time
import types
from unittest.mock import patch


STARTED_NS = time.perf_counter_ns()
SHARED_PATH = 'verification/perf030_002_worker.py'
SOURCE_PATH = 'human_eye_module1_operators/submodule_1_4_spatial_sniffer.py'
CASE_IDS = (0, 1, 2, 3, 4, 5, 6, 11)
STATES = ('cold_measure', 'primed_hot_measure', 'cold_task')


def load_shared(args):
    root = Path(args.qa_root).resolve()
    manifest = json.loads(Path(args.qa_manifest).read_bytes())
    row = next(item for item in manifest['files'] if item['path'] == SHARED_PATH)
    path = root / SHARED_PATH
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != row['sha256']:
        raise ValueError('qa_shared_worker_changed')
    module = types.ModuleType('_perf030_003_shared_worker')
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(blob, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def initialize(args, shared):
    state = shared.initialize(args)
    qa = state['qa']
    relative = Path(__file__).resolve().relative_to(state['qa_root']).as_posix()
    if relative not in qa.sources or Path(__file__).read_bytes() != qa.sources[relative]:
        raise ValueError('qa_stage_a_worker_changed')
    qa.executed[id(sys.modules[__name__])] = (sys.modules[__name__], relative)
    sniffer = importlib.import_module('human_eye_module1_operators.submodule_1_4_spatial_sniffer')
    orthogonal = importlib.import_module('human_eye_plugin.orthogonal_solid')
    original = sniffer._convex_shells
    aliases = (sniffer, state['geometry'], orthogonal)
    if any(module._convex_shells is not original for module in aliases):
        raise ValueError('qa_convex_alias_not_original')
    diagnostic = importlib.import_module('verification.perf030_003_diagnostic')
    clone, proof, recorder = diagnostic.build_diagnostic(sniffer, state['guard'].sources[SOURCE_PATH])
    state.update(shared=shared, aliases=aliases, original=original, clone=clone,
                 clone_proof=proof, recorder=recorder, seen_entries=set())
    state['ledger'] = {'entries': 0, 'prime_calls': 0, 'object_ns': 0,
                       'prime_ns': 0, 'kernel_ns': 0, 'process_ns': 0,
                       'instrumentation_prepare_ns': 0, 'trace_publish_prepare_ns': 0}
    return state


def support_snapshot(pair):
    values = []
    for mesh in pair:
        cached = getattr(mesh, '_certified_convex_shells', None)
        row = {'object_id': mesh.object_id, 'cache_state': 'not_evaluated',
               'component_count': None, 'components': None}
        if cached is not None:
            shells = cached[1]
            row['cache_state'] = 'negative' if shells is None else 'positive'
            row['component_count'] = None if shells is None else len(shells)
            if shells is not None:
                row['components'] = [{'points': points.tolist(), 'normals': normals.tolist(),
                                      'edge_axes': axes.tolist()} for points, normals, axes in shells]
        values.append(row)
    return values


def qualify(state, request):
    started = time.perf_counter_ns()
    case_index, entry_state, diagnostic = request['case_index'], request['state'], request['diagnostic']
    if case_index not in CASE_IDS or entry_state not in STATES or type(diagnostic) is not bool:
        raise ValueError('qualification_request_outside_freeze')
    key = (case_index, entry_state, diagnostic)
    if key in state['seen_entries']:
        raise ValueError('qualification_entry_already_run')
    state['seen_entries'].add(key)
    case = state['inputs']['cases'][case_index]
    costs = {'object_ns': 0, 'prime_ns': 0, 'kernel_ns': 0, 'process_ns': 0, 'prime_calls': 0,
             'instrumentation_prepare_ns': 0, 'trace_publish_prepare_ns': 0}
    result = {'case_index': case_index, 'case': case['name'], 'state': entry_state,
              'diagnostic': diagnostic, 'payload': None, 'diagnostics': {},
              'prime_payload': None, 'support_results': None, 'trace': None, 'costs': costs}
    if diagnostic:
        result['diagnostic_proof'] = state['clone_proof']
    shared, geometry = state['shared'], state['geometry']
    recorder_prepared = False
    try:
        stamp = time.perf_counter_ns()
        pair = shared.construct_pair(state, case)
        cache = state['cache'].SpatialSceneCache()
        costs['object_ns'] = time.perf_counter_ns() - stamp
        if entry_state == 'primed_hot_measure':
            stamp = time.perf_counter_ns()
            costs['prime_calls'] = 1
            try:
                result['prime_payload'] = geometry.measure_pair_geometry(*pair, need_clearance=True)
            finally:
                costs['prime_ns'] = time.perf_counter_ns() - stamp
        digest, hashes = shared.vertex_digests(state, pair)
        result['input_metadata'] = {'sha256': digest, 'object_sha256': hashes,
                                    'counts': [{'vertices': len(mesh.vertices), 'faces': len(mesh.faces),
                                                'edge_hints': len(mesh.edges)} for mesh in pair]}
        result['support_before'] = support_snapshot(pair)
        if diagnostic:
            stamp = time.perf_counter_ns()
            state['recorder'].reset()
            costs['instrumentation_prepare_ns'] = time.perf_counter_ns() - stamp
            recorder_prepared = True
        stamp = time.perf_counter_ns()
        try:
            with ExitStack() as context:
                if diagnostic:
                    for module in state['aliases']:
                        context.enter_context(patch.object(module, '_convex_shells', state['clone']))
                if entry_state == 'cold_task':
                    result['payload'], result['diagnostics'] = state['cases'].task_response(pair, cache)
                else:
                    result['payload'] = geometry.measure_pair_geometry(*pair, need_clearance=True)
        finally:
            costs['kernel_ns'] = time.perf_counter_ns() - stamp
        if any(module._convex_shells is not state['original'] for module in state['aliases']):
            raise ValueError('qa_convex_alias_restore_failed')
        if diagnostic:
            stamp = time.perf_counter_ns()
            result['trace'] = state['recorder'].snapshot()
            costs['trace_publish_prepare_ns'] = time.perf_counter_ns() - stamp
        result['support_results'] = support_snapshot(pair)
    except Exception as exc:
        if shared.identity_failure(exc):
            raise
        result['exception'] = shared.exception_record(exc)
        if recorder_prepared and result['trace'] is None:
            stamp = time.perf_counter_ns()
            try:
                result['trace'] = state['recorder'].snapshot()
            except Exception as trace_error:
                result['trace_exception'] = shared.exception_record(trace_error)
            costs['trace_publish_prepare_ns'] = time.perf_counter_ns() - stamp
    costs['process_ns'] = time.perf_counter_ns() - started
    state['ledger']['entries'] += 1
    for field, value in costs.items():
        state['ledger'][field] += value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--qa-root', required=True)
    parser.add_argument('--runtime-manifest', required=True)
    parser.add_argument('--qa-manifest', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--arm', required=True, choices=('baseline',))
    args = parser.parse_args()
    shared = None
    startup_log = io.StringIO()
    try:
        with redirect_stdout(startup_log), redirect_stderr(startup_log):
            shared = load_shared(args)
            state = initialize(args, shared)
            ready = {'event': 'ready', 'arm': args.arm,
                     'identity': shared.source_identity(state, 'ready'),
                     'qa_identity': shared.qa_identity(state), 'diagnostic_proof': state['clone_proof'],
                     'external_dependencies': shared.external_dependencies(state['runtime_root'], state['qa_root']),
                     'costs': {'startup_ns': time.perf_counter_ns() - STARTED_NS}}
        ready['captured_output'] = startup_log.getvalue()
        shared.emit(ready)
    except Exception as exc:
        error = {'event': 'error', 'kind': 'startup_failure', 'type': type(exc).__name__,
                 'message': str(exc), 'captured_output': startup_log.getvalue()}
        if shared is not None:
            error['exception'] = shared.exception_record(exc)
        print(json.dumps(error, ensure_ascii=True), flush=True)
        return 1
    for line in sys.stdin:
        request = {}
        output_log = io.StringIO()
        try:
            request = json.loads(line)
            operation = request['op']
            if operation == 'finish':
                result = {'identity': shared.source_identity(state, 'finish'),
                          'qa_identity': shared.qa_identity(state), 'ledger': state['ledger'],
                          'diagnostic_proof': state['clone_proof'],
                          'seen_entries': len(state['seen_entries']),
                          'worker_lifetime_ns': time.perf_counter_ns() - STARTED_NS}
                shared.emit({'event': 'finished', 'op': operation,
                             'request_id': request.get('request_id'), 'result': result})
                return 0
            if operation != 'qualify':
                raise ValueError('qualification_worker_has_only_qualify_and_finish')
            with redirect_stdout(output_log), redirect_stderr(output_log):
                result = qualify(state, request)
            if output_log.getvalue():
                result['captured_output'] = output_log.getvalue()
            shared.emit({'event': 'result', 'op': operation,
                         'request_id': request.get('request_id'), 'result': result})
        except Exception as exc:
            shared.emit({'event': 'error', 'op': request.get('op'),
                         'request_id': request.get('request_id'), 'exception': shared.exception_record(exc),
                         'captured_output': output_log.getvalue()})
            return 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
