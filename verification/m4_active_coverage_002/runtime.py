"""Fresh-process on-demand full-frame observation using the frozen 001 code."""

import time

STARTED_NS = time.perf_counter_ns()

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback


STDLIB_CLOSED_NS = time.perf_counter_ns()
BATCH = Path(__file__).resolve().parent
ROOT = BATCH.parents[1]
BASELINE = ROOT / 'verification/m4_active_coverage_001'
CORE = BASELINE / 'coverage.py'
ADAPTER = BASELINE / 'render/adapter.py'
SOURCE_HASHES = {
    CORE: '2561ecaf2f2df98ec7c03ed48cb95dd08c34f10ce73c1e9ecc2e32f31c41daf4',
    ADAPTER: 'df7e207ebd38c2876c54683e29899fccbe23187a4dd544cde1fcd9ed6ace82cd',
}
ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')


def encode(value):
    return (json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, allow_nan=False) + '\n').encode('utf8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save_new(path, value):
    raw = encode(value)
    with Path(path).open('xb') as stream:
        stream.write(raw)
    return raw


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def error_record(error, stage):
    return {'stage': stage, 'type': type(error).__name__, 'message': str(error),
            'traceback': traceback.format_exc()}


class QualificationFailure(Exception):
    pass


class Trace:
    def __init__(self, path, arm, scenario):
        self.path = path
        self.arm = arm
        self.scenario = scenario
        self.sequence = 0
        self.stream = path.open('xb')

    def emit(self, event, durable=False, **fields):
        self.sequence += 1
        value = {'sequence': self.sequence, 'event': event, 'monotonic_ns': time.perf_counter_ns(),
                 'process_id': os.getpid(), 'arm': self.arm, 'scenario': self.scenario, **fields}
        self.stream.write(encode(value))
        self.stream.flush()
        if durable:
            os.fsync(self.stream.fileno())
        return value

    def close(self):
        self.stream.close()


def install_old_evidence_audit(trace):
    evidence = {'installed_before_dynamic_imports': True, 'allowed_source_reads': [],
                'forbidden_old_evidence_reads': 0, 'old_evidence_read_attempts': [],
                'forbidden_old_writes': 0, 'old_write_attempts': []}

    def hook(event, arguments):
        if event != 'open' or not isinstance(arguments[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(arguments[0])).resolve()
        if not path.is_relative_to(BASELINE.resolve()):
            return
        mode, flags = arguments[1], arguments[2]
        writing = (isinstance(mode, str) and any(character in mode for character in 'wax+'))
        writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        record = {'path': str(path), 'mode': mode, 'flags': flags}
        if writing:
            evidence['forbidden_old_writes'] += 1
            evidence['old_write_attempts'].append(record)
            trace.emit('forbidden_old_write', durable=True, **record)
            raise PermissionError('old_active_coverage_tree_write_forbidden')
        source = path in SOURCE_HASHES
        cache = ((path.parent == BASELINE / '__pycache__' and path.name.startswith('coverage.'))
                 or (path.parent == BASELINE / 'render/__pycache__' and path.name.startswith('adapter.')))
        if source or cache and path.suffix == '.pyc':
            evidence['allowed_source_reads'].append(record)
            trace.emit('allowed_baseline_source_read', **record)
            return
        evidence['forbidden_old_evidence_reads'] += 1
        evidence['old_evidence_read_attempts'].append(record)
        trace.emit('forbidden_old_evidence_read', durable=True, **record)
        raise PermissionError('old_active_coverage_evidence_read_forbidden')

    sys.addaudithook(hook)
    return evidence


@contextmanager
def stage(result, trace, name, frame=None):
    key = name if frame is None else 'frame_' + str(frame['attempt_id']).zfill(2) + '.' + name
    value = {'started_ns': time.perf_counter_ns(), 'closed_ns': None, 'elapsed_ns': None}
    result['stages'][key] = value
    if frame is not None:
        frame['stages'][name] = value
    trace.emit('stage_start', stage=key)
    try:
        yield value
    finally:
        value['closed_ns'] = time.perf_counter_ns()
        value['elapsed_ns'] = value['closed_ns'] - value['started_ns']
        trace.emit('stage_complete', stage=key, **value)


def array_metadata(value):
    return {'dtype': str(value.dtype), 'dtype_str': value.dtype.str, 'shape': list(value.shape),
            'nbytes': int(value.nbytes), 'sha256': sha(value.tobytes(order='C'))}


def observe_view(result, trace, adapter, state, meshes, pose, output):
    attempt_id = len(result['render_attempts']) + 1
    if attempt_id > len(ORDER):
        raise QualificationFailure('registered_camera_attempt_limit')
    if result['arm'] == 'B' and result['scenario'] == 'main' and attempt_id > 2:
        trace.emit('qualification_failure', durable=True, reason='main_B_requires_additional_image',
                   selected_view=pose['name'], completed_attempts=len(result['render_attempts']))
        raise QualificationFailure('main_B_requires_additional_image')
    if pose['name'] in state.observed_views:
        raise QualificationFailure('observed_view_selected_again')
    directory = output / 'frames' / (str(attempt_id).zfill(2) + '_' + pose['name'])
    directory.mkdir(parents=True, exist_ok=False)
    frame = {'attempt_id': attempt_id, 'view_name': pose['name'], 'pose': pose,
             'stages': {}, 'pixel_rows': [], 'receipt': None, 'state_update': None}
    result['frames'].append(frame)
    with stage(result, trace, 'render_attempt_publication', frame):
        intent = trace.emit('render_attempt', durable=True, attempt_id=attempt_id, view_name=pose['name'])
    attempt = {'attempt_id': attempt_id, 'view_name': pose['name'], 'status': 'attempted',
               'intent_ns': intent['monotonic_ns'], 'intent_trace_sequence': intent['sequence'],
               'render_started_ns': None, 'render_closed_ns': None, 'completed_ns': None}
    result['render_attempts'].append(attempt)
    try:
        with stage(result, trace, 'raster', frame):
            attempt['render_started_ns'] = time.perf_counter_ns()
            buffers = adapter.render_one(meshes, pose)
            attempt['render_closed_ns'] = time.perf_counter_ns()
        attempt['status'] = 'rendered'
        trace.emit('render_complete', durable=True, attempt_id=attempt_id, view_name=pose['name'],
                   started_ns=attempt['render_started_ns'], closed_ns=attempt['render_closed_ns'],
                   elapsed_ns=attempt['render_closed_ns'] - attempt['render_started_ns'])
        pixel_error = None
        frame['pixel_evaluation_attempted_roi_count'] = len(state.index.regions)
        frame['pixel_evaluation_completed'] = False
        try:
            with stage(result, trace, 'pixels', frame):
                frame['pixel_rows'] = adapter.readability_for_rois(meshes, pose, buffers, state.index.regions)
                frame['pixel_evaluation_completed'] = True
        except BaseException as error:
            pixel_error = error
            result['exceptions'].append(error_record(error, 'pixels'))
        finally:
            with stage(result, trace, 'PNG', frame):
                png = directory / (pose['name'] + '.png')
                with png.open('xb') as stream:
                    adapter.Image.fromarray(buffers['color'], mode='RGB').save(stream, format='PNG')
                frame.update(PNG=str(png.resolve()), PNG_sha256=sha(png.read_bytes()), PNG_bytes=png.stat().st_size)
            with stage(result, trace, 'NPZ', frame):
                arrays = directory / (pose['name'] + '.npz')
                with arrays.open('xb') as stream:
                    adapter.np.savez_compressed(stream, **buffers)
                frame.update(owner_depth_RGB_arrays=str(arrays.resolve()), arrays_sha256=sha(arrays.read_bytes()),
                             compressed_array_file_bytes=arrays.stat().st_size)
        with stage(result, trace, 'array_metadata', frame):
            frame['arrays'] = {key: array_metadata(buffers[key]) for key in ('color', 'depth', 'owners')}
            frame['array_payload_bytes'] = sum(row['nbytes'] for row in frame['arrays'].values())
            frame['foreground_pixels'] = int((adapter.np.isfinite(buffers['depth']) & (buffers['depth'] > 0)).sum())
        if pixel_error is not None:
            raise pixel_error
        complete = set(state.index.ids(state.index.view_masks[pose['name']]))
        readable = {row['roi_id'] for row in frame['pixel_rows'] if row['readable']}
        shortfall = sorted(complete - readable)
        receipt = {'scene_identity': state.index.scene_identity, 'candidate_identity': state.index.candidate_identity,
                   'view_name': pose['name'], 'actual_image_delivered': True,
                   'image_path': frame['PNG'], 'image_sha256': frame['PNG_sha256'],
                   'pixel_evidence_scope': 'actual_common_depth_owner', 'readable_roi_ids': sorted(readable)}
        with stage(result, trace, 'observe', frame):
            update = state.observe(receipt)
        frame['receipt'], frame['state_update'] = receipt, update
        result['steps'].append({'attempt_id': attempt_id, 'view_name': pose['name'],
            'geometry_complete_roi_ids': sorted(complete), 'readable_roi_ids': sorted(readable),
            'pixel_shortfall_roi_ids': shortfall, 'pixel_rows': frame['pixel_rows'],
            'new_roi_ids': update['new_roi_ids'], 'covered_roi_ids': update['covered_roi_ids'],
            'unresolved_roi_ids': update['unresolved_roi_ids'], 'receipt': receipt})
        metadata = directory / 'FRAME.json'
        frame['metadata_path'] = str(metadata.resolve())
        with stage(result, trace, 'metadata', frame):
            completed_stages = {key: value for key, value in frame['stages'].items() if value['closed_ns'] is not None}
            raw = save_new(metadata, {**frame, 'stages': completed_stages,
                'metadata_stage_scope': 'Completed pre-publication stages. Final metadata interval is in RESULT.'})
        frame['metadata_sha256'], frame['metadata_bytes'] = sha(raw), len(raw)
        attempt['status'] = 'completed'
        attempt['completed_ns'] = time.perf_counter_ns()
        trace.emit('frame_complete', durable=True, attempt_id=attempt_id, view_name=pose['name'],
                   PNG_sha256=frame['PNG_sha256'], arrays_sha256=frame['arrays_sha256'])
    except BaseException as error:
        attempt['status'] = 'failed'
        attempt['exception'] = error_record(error, 'observe_view')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('A', 'B'), required=True)
    parser.add_argument('--scenario', choices=('main', 'pixel_shortfall'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute() or not args.trace.is_absolute():
        raise ValueError('absolute_output_and_trace_required')
    output, trace_path = args.output.resolve(), args.trace.resolve()
    if output.is_relative_to(BASELINE.resolve()) or trace_path.parent != output:
        raise ValueError('new_output_directory_trace_binding')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'RESULT.json').exists() or (output / 'frames').exists():
        raise ValueError('fresh_run_output_required')
    trace = Trace(trace_path, args.arm, args.scenario)
    result = {'schema': 'active-coverage-002-runtime-v1', 'arm': args.arm, 'scenario': args.scenario,
        'process_id': os.getpid(), 'output_directory': str(output), 'status': 'running',
        'started_ns': STARTED_NS, 'work_closed_ns': None, 'index': None, 'frames': [], 'steps': [],
        'render_attempts': [], 'final_state': None, 'repeat_query': None, 'exceptions': [],
        'stages': {'stdlib_import': {'started_ns': STARTED_NS, 'closed_ns': STDLIB_CLOSED_NS,
                                   'elapsed_ns': STDLIB_CLOSED_NS - STARTED_NS}},
        'inputs_sha256': {}, 'dependencies': None,
        'publication_receipt': str((output / 'RESULT_PUBLICATION.json').resolve())}
    result['audit'] = install_old_evidence_audit(trace)
    state = None
    active_stage = 'startup'
    try:
        trace.emit('runtime_start', durable=True, output_directory=str(output))
        active_stage = 'dependency_import'
        with stage(result, trace, active_stage):
            for path, wanted in SOURCE_HASHES.items():
                actual = sha(path.read_bytes())
                if actual != wanted:
                    raise ValueError('frozen_baseline_source_changed:' + str(path))
                result['inputs_sha256'][str(path.resolve())] = actual
            core = load('_active002_fixed_geometry', CORE)
            adapter = load('_active002_fixed_raster', ADAPTER)
        active_stage = 'dependency_binding'
        with stage(result, trace, active_stage):
            result['dependencies'] = adapter.dependency_binding()
        active_stage = 'read_inputs'
        with stage(result, trace, active_stage):
            scene_path = BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json'
            camera_path = BATCH / 'inputs' / ('CAMERAS.json' if args.scenario == 'main' else 'CAMERAS_PIXEL_SHORTFALL.json')
            scene_raw, camera_raw = scene_path.read_bytes(), camera_path.read_bytes()
            result['source_scene'], result['source_camera'] = str(scene_path.resolve()), str(camera_path.resolve())
            result['source_scene_sha256'], result['source_camera_sha256'] = sha(scene_raw), sha(camera_raw)
            result['inputs_sha256'].update({str(scene_path.resolve()): sha(scene_raw), str(camera_path.resolve()): sha(camera_raw),
                                           str(Path(__file__).resolve()): sha(Path(__file__).read_bytes())})
            scene, cameras = json.loads(scene_raw), json.loads(camera_raw)
            if tuple(pose['name'] for pose in cameras['views']) != ORDER or any(pose['size_px'] != [512, 512] for pose in cameras['views']):
                raise ValueError('registered_camera_pool_required')
        active_stage = 'geometry_index'
        with stage(result, trace, active_stage):
            index = core.build_index(scene, cameras, 'optimized')
            state = core.CoverageState(index)
        active_stage = 'resident_meshes'
        with stage(result, trace, active_stage):
            meshes = adapter.load_meshes(scene)
        active_stage = 'index_serialization'
        with stage(result, trace, active_stage):
            result['index'] = {'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
                'roi_ids': list(index.region_ids), 'regions': [asdict(region) for region in index.regions],
                'view_order': list(index.view_order), 'view_masks': index.view_masks,
                'classifications': index.classifications, 'stats': index.stats}
        active_stage = 'observation'
        poses = {pose['name']: pose for pose in cameras['views']}
        if args.arm == 'A':
            for name in ORDER:
                observe_view(result, trace, adapter, state, meshes, poses[name], output)
        else:
            while True:
                name = state.next_view()
                if name is None:
                    break
                observe_view(result, trace, adapter, state, meshes, poses[name], output)
        active_stage = 'same_version_repeat_query'
        with stage(result, trace, active_stage):
            before = len(result['render_attempts'])
            state_before = state.summary()
            reused = state.observe(result['frames'][-1]['receipt'])
            state_after = state.summary()
            result['repeat_query'] = {'render_attempts_before': before,
                'render_attempts_after': len(result['render_attempts']),
                'new_render_attempts': len(result['render_attempts']) - before,
                'state_before': state_before, 'state_after': state_after, 'reuse_update': reused,
                'next_view': state.next_view()}
            if not reused['reused'] or state_before != state_after or result['repeat_query']['new_render_attempts']:
                raise QualificationFailure('same_version_query_not_idempotent')
        result['status'] = 'completed'
    except BaseException as error:
        result['status'] = 'qualification_failed' if isinstance(error, QualificationFailure) else 'failed'
        result['exceptions'].append(error_record(error, active_stage))
        trace.emit('runtime_failure', durable=True, type=type(error).__name__, message=str(error), stage=active_stage)
    finally:
        if state is not None:
            result['final_state'] = state.summary()
            historical = {identity for step in result['steps'] for identity in step['pixel_shortfall_roi_ids']}
            result['pixel_shortfall_history_roi_ids'] = sorted(historical)
            result['final_pixel_shortfall_roi_ids'] = sorted(historical.intersection(state.unresolved()))
        result['metrics'] = {'raster_attempts': len(result['render_attempts']),
            'raster_completed': sum(attempt['render_closed_ns'] is not None for attempt in result['render_attempts']),
            'frames_completed': sum(attempt['status'] == 'completed' for attempt in result['render_attempts']),
            'pixel_tests': sum(len(frame['pixel_rows']) for frame in result['frames']),
            'pixel_test_attempts': sum(frame.get('pixel_evaluation_attempted_roi_count', 0) for frame in result['frames']),
            'pixel_test_count_scope': 'Completed returned rows. Internal evaluations in a failed helper remain unknown.',
            'PNG_bytes': sum(frame.get('PNG_bytes', 0) for frame in result['frames']),
            'NPZ_bytes': sum(frame.get('compressed_array_file_bytes', 0) for frame in result['frames']),
            'frame_metadata_bytes': sum(frame.get('metadata_bytes', 0) for frame in result['frames']),
            'array_payload_bytes': sum(frame.get('array_payload_bytes', 0) for frame in result['frames']),
            'array_payload_scope': 'Sum of generated color/depth/owner ndarray nbytes. RSS unmeasured.',
            'raster_attempt_scope': 'Durable pre-call intents. Successful returns are recorded separately.',
            'new_model_provider_Blender_API_runs': 0}
        trace.emit('work_complete', durable=True, status=result['status'], metrics=result['metrics'])
        result['work_closed_ns'] = time.perf_counter_ns()
        result['elapsed_before_result_publication_ns'] = result['work_closed_ns'] - result['started_ns']
        result['trace_bytes_before_result_publication'] = trace_path.stat().st_size
        published_start = time.perf_counter_ns()
        raw = save_new(output / 'RESULT.json', result)
        published_close = time.perf_counter_ns()
        publication = {'started_ns': published_start, 'closed_ns': published_close,
            'elapsed_ns': published_close - published_start, 'RESULT_sha256': sha(raw), 'RESULT_bytes': len(raw),
            'scope': 'RESULT JSON encoding, write and close. This receipt and final trace publication are covered by the parent full-process interval.',
            'durability': 'Buffered RESULT write/close. Render intent trace records explicitly flush and fsync.'}
        save_new(output / 'RESULT_PUBLICATION.json', publication)
        trace.emit('process_complete', durable=True, status=result['status'], RESULT_sha256=publication['RESULT_sha256'])
        trace.close()
    return 0 if result['status'] == 'completed' else 2 if result['status'] == 'qualification_failed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
