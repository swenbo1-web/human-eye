"""Installed MCP entry with frozen, evidence-only capture and intent wrappers.

The product server, source guard, host and active observation implementation
remain the actual installed implementations. This script is copied into the
controller's external payload before launch.
"""

import argparse
import hashlib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import sys
import time


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def append(path, value):
    with Path(path).open('ab') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def serve(config, binding_path, bootstrap_path, evidence_directory, budget_directory):
    started = time.perf_counter_ns()
    evidence = Path(evidence_directory).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    budget = Path(budget_directory).resolve()
    budget.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('_patch_ownership_trusted_bootstrap', bootstrap_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    binding_raw = Path(binding_path).read_bytes()
    guard = helper.bootstrap(json.loads(binding_raw))
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server, _configure_utf8_stdio
    from human_eye_plugin import active_observation_host as bridge

    _configure_utf8_stdio()
    service = LiveSpatialService(config, production_mode=True)
    original_capture = service.host.capture_scene
    original_observe = service.observe
    original_event = service.record_event
    original_prepare = bridge.prepare_scene_from_parsed
    prepare_identity = {
        'module': original_prepare.__module__, 'qualname': original_prepare.__qualname__,
        'source_path': original_prepare.__code__.co_filename,
        'source_sha256': hashlib.sha256(Path(original_prepare.__code__.co_filename).read_bytes()).hexdigest(),
        'code_sha256': hashlib.sha256(marshal.dumps(original_prepare.__code__)).hexdigest(),
    }
    captures = []
    intents = []
    indexes = []
    results = []

    def capture_scene():
        call_started = time.perf_counter_ns()
        capture = original_capture()
        host_returned = time.perf_counter_ns()
        raw = encoded(capture)
        index = len(captures) + 1
        path = evidence / ('CAPTURE_' + str(index).zfill(2) + '.json')
        with path.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        closed = time.perf_counter_ns()
        row = {'index': index, 'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
               'bytes': len(raw), 'revision': capture.get('revision'),
               'host_identity': capture.get('host_identity'),
               'started_ns': call_started, 'host_returned_ns': host_returned, 'closed_ns': closed,
               'host_call_elapsed_ns': host_returned - call_started,
               'evidence_serialization_write_elapsed_ns': closed - host_returned,
               'elapsed_ns': closed - call_started,
               'same_object_returned_to_bridge': True, 'additional_host_capture_calls': 0}
        captures.append(row)
        append(evidence / 'CAPTURES.jsonl', row)
        return capture

    def prepare_scene_from_parsed(*args, **kwargs):
        call_started = time.perf_counter_ns()
        session = original_prepare(*args, **kwargs)
        original_returned = time.perf_counter_ns()
        assert captures, 'actual_capture_before_bridge_prepare_required'
        capture = captures[-1]
        projection = {
            'actual_capture_index': capture['index'], 'actual_capture_sha256': capture['sha256'],
            'capture_revision': capture['revision'], 'host_identity': capture['host_identity'],
            'scene_identity': session.scene_identity, 'candidate_identity': session.candidate_identity,
            'cameras': session.cameras,
            'regions': [{'roi_id': region.roi_id, 'object_index': region.object_index,
                         'object_name': region.object_name, 'triangle_indices': list(region.triangle_indices),
                         'vertices': [[str(value) for value in point] for point in region.vertices],
                         'normal': [str(value) for value in region.normal]} for region in session.regions],
            'view_order': list(session.index.view_order), 'view_masks': session.index.view_masks,
            'classifications': session.index.classifications,
            'patch_scope': session.index.patch_scope,
            'diagnostics': session.diagnostics,
            'objects': [{'object_index': index, 'object_name': obj[3],
                         'source_vertex_count': len(obj[0]), 'source_triangle_count': len(obj[1])}
                        for index, obj in enumerate(session.objects)],
            'fresh_state': session.summary(),
        }
        raw = encoded(projection)
        index = len(indexes) + 1
        path = evidence / ('INDEX_' + str(index).zfill(2) + '.json')
        with path.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        closed = time.perf_counter_ns()
        row = {'index': index, 'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
               'actual_capture_index': capture['index'], 'actual_capture_sha256': capture['sha256'],
               'started_ns': call_started, 'original_returned_ns': original_returned, 'closed_ns': closed,
               'original_call_elapsed_ns': original_returned - call_started,
               'evidence_projection_write_elapsed_ns': closed - original_returned,
               'elapsed_ns': closed - call_started, 'same_session_returned_to_bridge': True,
               'extra_prepare_calls': 0, 'original_callable': prepare_identity}
        indexes.append(row)
        append(evidence / 'INDEXES.jsonl', row)
        return session

    def observe(*args, **kwargs):
        call_started = time.perf_counter_ns()
        capture_start = len(captures)
        result = original_observe(*args, **kwargs)
        original_returned = time.perf_counter_ns()
        raw = encoded(result)
        index = len(results) + 1
        path = evidence / ('RESULT_' + str(index).zfill(2) + '.json')
        with path.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        closed = time.perf_counter_ns()
        row = {
            'index': index, 'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'capture_associations': [{'index': capture['index'], 'sha256': capture['sha256'],
                                      'revision': capture['revision']}
                                     for capture in captures[capture_start:]],
            'started_ns': call_started, 'original_returned_ns': original_returned, 'closed_ns': closed,
            'original_call_elapsed_ns': original_returned - call_started,
            'evidence_serialization_write_elapsed_ns': closed - original_returned,
            'elapsed_ns': closed - call_started,
            'ledger_append_in_outer_request_time': True,
            'ledger_append_excluded_from_row_clock': True,
            'same_result_returned_to_mcp': True, 'extra_observe_calls': 0,
        }
        results.append(row)
        append(evidence / 'RESULTS.jsonl', row)
        return result

    def record_event(event, **fields):
        if event == 'active_observation_render_attempt':
            # Exclusive fixed slots count failed attempts across restarts too.
            # The marker is durable before the product callback may render.
            for number in range(1, 15):
                slot = budget / ('attempt_' + str(number).zfill(2))
                try:
                    slot.mkdir()
                except FileExistsError:
                    continue
                row = {'attempt': number, 'event': event, 'fields': fields,
                       'pid': os.getpid(), 'monotonic_ns': time.perf_counter_ns()}
                save(slot / 'INTENT.json', row)
                append(budget / 'INTENTS.jsonl', row)
                intents.append(row)
                break
            else:
                raise RuntimeError('global_new_raster_hard_cap_14_exhausted')
        return original_event(event, **fields)

    service.host.capture_scene = capture_scene
    service.observe = observe
    service.record_event = record_event
    bridge.prepare_scene_from_parsed = prepare_scene_from_parsed
    guard.verify_loaded()
    save(evidence / 'START.json', {'pid': os.getpid(), 'started_ns': started,
                                 'ready_ns': time.perf_counter_ns(),
                                 'binding_sha256': hashlib.sha256(binding_raw).hexdigest(),
                                 'capture_wrapper': 'original once, identical decoded object returned',
                                 'prepare_wrapper': 'actual installed bridge import alias, original once, identical session returned',
                                 'observe_wrapper': 'original service once, identical complete result returned to MCP',
                                 'intent_event': 'active_observation_render_attempt',
                                 'raster_hard_cap': 14,
                                 'new_model_calls': 0, 'new_Blender_processes': 0})
    failure = None
    try:
        run_stdio_mcp_server(service)
    except BaseException as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        source_error = None
        try:
            guard.verify_loaded()
        except BaseException as exc:
            source_error = {'type': type(exc).__name__, 'message': str(exc)}
        save(evidence / 'FINISH.json', {'pid': os.getpid(), 'started_ns': started,
                                      'closed_ns': time.perf_counter_ns(), 'failure': failure,
                                      'source_check_error': source_error,
                                      'capture_calls': len(captures), 'raster_intents': len(intents),
                                      'raster_hard_cap': 14,
                                      'prepare_calls': len(indexes), 'index_projection_bytes': sum(row['bytes'] for row in indexes),
                                      'observe_calls': len(results), 'result_projection_bytes': sum(row['bytes'] for row in results),
                                      'new_model_calls': 0, 'capture_evidence_writes_in_outer_time': True})
        if source_error is not None and failure is None:
            raise RuntimeError('final_installed_source_check_failed:' + str(source_error))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--binding', required=True)
    parser.add_argument('--bootstrap', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--budget', required=True)
    args = parser.parse_args()
    serve(args.config, args.binding, args.bootstrap, args.evidence, args.budget)
