"""Evidence worker copied outside the repository and run against the installed API."""

import argparse
import copy
from fractions import Fraction
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import time
import traceback


EXTERNAL = Path('D:/he_core_001').resolve()
PAIR_ORDER = (('old', 'new'), ('new', 'old'), ('old', 'new'), ('new', 'old'), ('old', 'new'))
AUDIT_STAGE = 'startup'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, default=str,
                       allow_nan=False, separators=(',', ':')) + '\n').encode('utf8')


def save(path, value):
    with Path(path).open('wb') as stream:
        stream.write(encoded(value))


def read(path):
    return json.loads(Path(path).read_bytes())


def region_row(region):
    return {'roi_id': region.roi_id, 'object_index': region.object_index, 'object_name': region.object_name,
            'triangle_indices': list(region.triangle_indices),
            'vertices': [[str(value) for value in point] for point in region.vertices],
            'normal': [str(value) for value in region.normal]}


def index_row(index):
    return {'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
            'regions': [region_row(region) for region in index.regions], 'view_order': list(index.view_order),
            'view_masks': index.view_masks, 'classifications': index.classifications}


def public_frame(frame):
    return {key: value for key, value in frame.items() if key != 'buffers'}


def audit_reads(payload, output, phase):
    stream = (output / 'ACCESS.jsonl').open('xb')
    events = {'reads': 0, 'writes': 0, 'denied': []}
    base = Path(sys.base_prefix).resolve()
    system = Path(os.environ.get('SystemRoot', 'C:/Windows')).resolve()
    baseline = (payload / 'baseline').resolve()

    def hook(event, arguments):
        if event != 'open' or not isinstance(arguments[0], (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(arguments[0])).resolve()
        mode, flags = arguments[1:3]
        writing = isinstance(mode, str) and any(value in mode for value in 'wax+')
        writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        allowed = path.is_relative_to(EXTERNAL) if writing else any(path.is_relative_to(root) for root in (EXTERNAL, base, system))
        if path.is_relative_to(baseline) and not (phase == 'benchmark' and AUDIT_STAGE == 'old_baseline_import'):
            allowed = False
        row = {'event': 'open', 'stage': AUDIT_STAGE, 'path': str(path), 'writing': writing, 'allowed': allowed}
        stream.write(encoded(row))
        stream.flush()
        events['writes' if writing else 'reads'] += 1
        if not allowed:
            events['denied'].append(row)
            raise PermissionError('isolated_worker_path_outside_contract')

    sys.addaudithook(hook)
    return stream, events


def load_inputs(payload, manifest, name, camera='normal', control=False):
    table = manifest['controls'] if control else manifest['scenes']
    return read(payload / table[name]['file']), read(payload / manifest['cameras'][camera]['file'])


def replay_frame(payload, specification, replay):
    return {'scene_identity': replay['scene_identity'], 'candidate_identity': replay['candidate_identity'],
            'view_name': specification['view_name'], 'image_path': str(payload / specification['image_file']),
            'image_sha256': specification['image_sha256'], 'image_ref': specification['image_ref'],
            'arrays_path': str(payload / specification['arrays_file']), 'arrays_sha256': specification['arrays_sha256']}


def qualification(core, image_api, payload, manifest, output):
    representations, controls, replays = [], [], []
    for name in manifest['scenes']:
        scene, cameras = load_inputs(payload, manifest, name)
        for diagnostics in (False, True):
            session = core.prepare_scene(scene, cameras, diagnostics=diagnostics)
            representations.append({'scene': name, 'diagnostics_enabled': diagnostics, 'index': index_row(session.index),
                                    'summary': session.summary(), 'diagnostics': session.diagnostics})
    for name in manifest['controls']:
        scene, cameras = load_inputs(payload, manifest, name, control=True)
        for diagnostics in (False, True):
            session = core.prepare_scene(scene, cameras, diagnostics=diagnostics)
            controls.append({'control': name, 'diagnostics_enabled': diagnostics,
                             'regions': [region_row(value) for value in session.regions]})
    saved = {}
    for specification in manifest['offline_replays']:
        scene, cameras = load_inputs(payload, manifest, specification['scene'])
        session = core.prepare_scene(scene, cameras)
        images = image_api.ActiveObservationImages(session, output / ('replay_' + specification['id']))
        steps, frames = [], []
        for source in specification['frames']:
            frame = replay_frame(payload, source, specification)
            observed = images.observe_frame(frame)
            steps.append(observed)
            frames.append(frame)
        replays.append({'id': specification['id'], 'steps': steps, 'summary': session.summary(),
                        'facts': session.short_facts(), 'historical_frames_read': len(frames), 'new_renders': 0})
        saved[specification['id']] = (session, images, frames)
    key = 'grid16_permuted_alternating_candidate'
    session, images, frames = saved[key]
    summary, facts = session.summary(), session.short_facts()
    duplicate = images.observe_frame(frames[0])
    assert duplicate['update']['reused'] is True and session.summary() == summary and session.short_facts() == facts
    scene4, cameras = load_inputs(payload, manifest, 'grid4_permuted_alternating')
    identity_before = (session.scene_identity, session.candidate_identity)
    assert session.rebind(scene4, cameras) is True
    assert not session.summary()['covered_roi_ids'] and not session.short_facts()['observations']
    try:
        images.observe_frame(frames[0])
    except ValueError:
        old_scene_rejected = True
    else:
        raise AssertionError('old_scene_frame_accepted')
    camera64 = read(payload / manifest['cameras']['back64']['file'])
    assert session.rebind(scene4, camera64) is True
    old4 = next(value for value in manifest['offline_replays'] if value['id'] == 'grid4_permuted_alternating_candidate')
    try:
        images.observe_frame(replay_frame(payload, old4['frames'][0], old4))
    except ValueError:
        old_camera_rejected = True
    else:
        raise AssertionError('old_camera_frame_accepted')
    invalidation = {'repeat_state_and_facts_equal': True, 'duplicate_update_reused': True,
                    'scene_change_invalidated': old_scene_rejected, 'camera_change_invalidated': old_camera_rejected,
                    'initial_identity': identity_before, 'final_identity': (session.scene_identity, session.candidate_identity),
                    'final_summary': session.summary(), 'new_renders': 0}
    result = {'representations': representations, 'controls': controls, 'offline_replays': replays,
              'repeat_and_invalidation_case': invalidation, 'historical_frame_count': 8, 'new_renders': 0}
    save(output / 'QUALIFICATION.json', result)
    return result


def reserve_render(output, chain, view):
    budget = EXTERNAL / 'run/render_budget'
    budget.mkdir(parents=True, exist_ok=True)
    for number in range(1, 9):
        path = budget / (str(number).zfill(2) + '.json')
        try:
            with path.open('x', encoding='utf8') as stream:
                row = {'attempt': number, 'chain': chain, 'view': view, 'started_ns': time.perf_counter_ns()}
                stream.write(encoded(row).decode('utf8'))
                stream.flush()
                os.fsync(stream.fileno())
            return row
        except FileExistsError:
            continue
    raise RuntimeError('eight_render_attempt_budget_exhausted')


def observe(core, image_api, payload, manifest, output):
    chains = []
    with (output / 'TRACE.jsonl').open('xb') as trace:
        for camera in ('normal', 'back64'):
            scene, cameras = load_inputs(payload, manifest, 'grid16_permuted_alternating', camera)
            session = core.prepare_scene(scene, cameras)
            images = image_api.ActiveObservationImages(session, output / camera)
            frames, steps = [], []
            while session.next_view() is not None:
                view = session.next_view()
                intent = reserve_render(output, camera, view)
                pending = {'attempt': intent, 'status': 'intent'}
                frames.append(pending)
                trace.write(encoded({'event': 'render_attempt', **intent}))
                trace.flush()
                os.fsync(trace.fileno())
                frame = images.render_view(view)
                observed = images.observe_frame(frame)
                pending.update(status='completed', frame=public_frame(frame))
                steps.append(observed)
                trace.write(encoded({'event': 'frame_complete', 'attempt': intent['attempt'],
                                     'view': view, 'image_sha256': frame['image_sha256']}))
                trace.flush()
                os.fsync(trace.fileno())
                save(output / 'PROGRESS.json', {'completed_chains': chains, 'current': camera,
                                               'frames': frames, 'steps': steps})
            chain = {'camera': camera, 'frames': frames, 'steps': steps, 'summary': session.summary(),
                     'facts': session.short_facts()}
            chains.append(chain)
    result = {'chains': chains, 'new_render_attempts': sum(len(row['frames']) for row in chains),
              'model_vision_consumption': 'not_requested_local_core_only'}
    save(output / 'OBSERVATIONS.json', result)
    return result


def benchmark(core, payload, manifest, output):
    global AUDIT_STAGE
    with (EXTERNAL / 'run/BENCHMARK_STARTED.json').open('x', encoding='utf8') as stream:
        stream.write(encoded({'pairs': PAIR_ORDER}).decode('utf8'))
    AUDIT_STAGE = 'old_baseline_import'
    public = read(payload / 'PAYLOAD_MANIFEST.json')
    for key in ('discovery_file', 'coverage_file'):
        relative = manifest['baseline'][key]
        if digest((payload / relative).read_bytes()) != public['files'][relative]['sha256']:
            raise ValueError('copied_baseline_source_changed:' + relative)
    path = payload / manifest['baseline']['discovery_file']
    spec = importlib.util.spec_from_file_location('_installed_comparison_old_candidate', path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    rows = []
    for pair, order in enumerate(PAIR_ORDER, 1):
        for arm in order:
            AUDIT_STAGE = 'benchmark_' + arm
            began = time.perf_counter_ns()
            scene_raw = (payload / manifest['scenes']['grid16_permuted_alternating']['file']).read_bytes()
            cameras_raw = (payload / manifest['cameras']['normal']['file']).read_bytes()
            scene_sha, camera_sha = digest(scene_raw), digest(cameras_raw)
            scene, cameras = json.loads(scene_raw), json.loads(cameras_raw)
            if arm == 'old':
                index = old.build_index(scene, cameras, discovery_variant='candidate')
            else:
                index = core.prepare_scene(scene, cameras).index
            closed = time.perf_counter_ns()
            row = {'pair': pair, 'arm': arm, 'started_ns': began, 'closed_ns': closed,
                   'elapsed_ns': closed - began, 'scene_sha256': scene_sha, 'camera_sha256': camera_sha,
                   'index': index_row(index)}
            rows.append(row)
            save(output / 'PROGRESS.json', rows)
    pairs = []
    for number in range(1, 6):
        old_row = next(value for value in rows if value['pair'] == number and value['arm'] == 'old')
        new_row = next(value for value in rows if value['pair'] == number and value['arm'] == 'new')
        assert old_row['index'] == new_row['index']
        pairs.append({'pair': number, 'old_ns': old_row['elapsed_ns'], 'new_ns': new_row['elapsed_ns'],
                      'new_over_old': new_row['elapsed_ns'] / old_row['elapsed_ns']})
    result = {'rows': rows, 'pairs': pairs, 'paired_ratio_median': statistics.median(value['new_over_old'] for value in pairs),
              'old_total_ns': sum(value['old_ns'] for value in pairs),
              'new_total_ns': sum(value['new_ns'] for value in pairs), 'new_renders': 0,
              'scope': 'Exactly five pairs, fresh source read/hash/JSON and complete index per trial. Setup and serialization outside trial clocks.'}
    save(output / 'BENCHMARK.json', result)
    return result


def main():
    global AUDIT_STAGE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('source_check', 'qualify', 'observe', 'benchmark'), required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--bootstrap', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quality-gate', type=Path)
    options = parser.parse_args()
    payload, output = options.payload.resolve(), options.output.resolve()
    if not all(path.is_relative_to(EXTERNAL) for path in (payload, output, Path(__file__).resolve(), options.binding.resolve(), options.bootstrap.resolve(), Path.cwd().resolve())):
        raise ValueError('isolated_external_paths_required')
    output.mkdir(parents=True, exist_ok=False)
    audit_stream, access = audit_reads(payload, output, options.phase)
    result = {'phase': options.phase, 'pid': os.getpid(), 'started_ns': time.perf_counter_ns(), 'passed': False}
    guard = None
    try:
        manifest = read(payload / 'INPUTS.json')
        public = read(payload / 'PAYLOAD_MANIFEST.json')
        for name, expected in public['files'].items():
            if name.startswith('baseline/'):
                continue
            if digest((payload / name).read_bytes()) != expected['sha256']:
                raise ValueError('payload_bytes_changed:' + name)
        binding = read(options.binding)
        result.update(binding_sha256=digest(options.binding.read_bytes()),
                      payload_manifest_sha256=digest((payload / 'PAYLOAD_MANIFEST.json').read_bytes()),
                      worker_source_sha256=digest(Path(__file__).read_bytes()),
                      bootstrap_source_sha256=digest(options.bootstrap.read_bytes()))
        spec = importlib.util.spec_from_file_location('_installed_verified_bootstrap', options.bootstrap)
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
        guard = helper.bootstrap(binding)
        AUDIT_STAGE = 'installed_product_import'
        core = importlib.import_module('human_eye_plugin.active_observation')
        image_api = importlib.import_module('human_eye_plugin.active_observation_images')
        install_root = Path(binding['install_root']).resolve()
        assert Path(core.__file__).resolve().is_relative_to(install_root)
        assert Path(image_api.__file__).resolve().is_relative_to(install_root)
        numpy = importlib.import_module('numpy')
        pillow = importlib.import_module('PIL')
        assert Path(numpy.__file__).resolve().is_relative_to(install_root)
        assert Path(pillow.__file__).resolve().is_relative_to(install_root)
        guard.verify_loaded()
        result['setup_closed_ns'] = time.perf_counter_ns()
        result['environment'] = {'python': sys.executable, 'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
            'cwd': str(Path.cwd()), 'core_module': core.__file__, 'image_module': image_api.__file__,
            'core_sha256': digest(Path(core.__file__).read_bytes()),
            'image_sha256': digest(Path(image_api.__file__).read_bytes()),
            'numpy_module': numpy.__file__, 'numpy_version': numpy.__version__,
            'Pillow_module': pillow.__file__, 'Pillow_version': pillow.__version__}
        AUDIT_STAGE = options.phase
        if options.phase == 'source_check':
            identity = importlib.import_module('human_eye_plugin.runtime_identity')
            result['runtime_identity'] = identity.runtime_identity(mode='demo')
            result['source_drift'] = identity.check_source_drift()
            assert result['source_drift']['compatible'] is True
        elif options.phase == 'qualify':
            result['qualification'] = qualification(core, image_api, payload, manifest, output)
        elif options.phase == 'observe':
            result['observations'] = observe(core, image_api, payload, manifest, output)
        else:
            if options.quality_gate is None or not options.quality_gate.resolve().is_relative_to(EXTERNAL):
                raise ValueError('external_quality_gate_required_before_benchmark')
            gate = read(options.quality_gate)
            assert gate['passed'] is True and gate['binding_sha256'] == digest(options.binding.read_bytes())
            phases = set()
            for path, wanted in gate['evidence_sha256'].items():
                path = Path(path).resolve()
                assert path.is_relative_to(EXTERNAL) and digest(path.read_bytes()) == wanted
                record = read(path)
                assert record['passed'] is True
                assert record['binding_sha256'] == gate['binding_sha256']
                phases.add(record['phase'])
            assert {'source_check', 'qualify', 'observe'} <= phases
            result['benchmark'] = benchmark(core, payload, manifest, output)
        guard.verify_loaded()
        assert not access['denied']
        result['passed'] = True
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    result['closed_before_publication_ns'] = time.perf_counter_ns()
    result['access'] = access
    result['new_model_CLI_Blender_provider_calls'] = 0
    save(output / 'RESULTS.json', result)
    audit_stream.flush()
    print(json.dumps({'phase': options.phase, 'passed': result['passed'], 'new_model_calls': 0}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
