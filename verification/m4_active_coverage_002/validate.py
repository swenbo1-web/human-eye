"""Controller-only validation of published active-coverage run artifacts.

Reads completed files and independently counts current owner/RGB evidence.
It never imports the coverage algorithm, renderer, product or oracle answers.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.with_name('m4_active_coverage_001')
VIEW_ORDER = ['SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK']


class AttemptCountUnknown(ValueError):
    """The durable trace does not establish an unambiguous attempt count."""
    def __init__(self, message, known_attempts):
        super().__init__(message)
        self.known_attempts = known_attempts
        self.attempt_count_unknown = True


def _need(value, message):
    if not value:
        raise ValueError(message)


def _read(path):
    return json.loads(Path(path).read_bytes(), parse_constant=lambda value: (
        _need(False, 'nonfinite JSON constant ' + value)))


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fingerprint(value):
    return _sha(json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode('utf8'))


def _trace(directory):
    path = Path(directory) / 'TRACE.jsonl'
    if not path.exists():
        return []
    rows = []
    attempts = 0
    identities = set()
    for number, raw in enumerate(path.read_bytes().splitlines(), 1):
        if not raw.strip():
            raise AttemptCountUnknown('empty trace line ' + str(number), attempts)
        try:
            row = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise AttemptCountUnknown('unreadable trace line ' + str(number), attempts) from error
        if not isinstance(row, dict):
            raise AttemptCountUnknown('trace object required', attempts)
        if row.get('event') == 'render_attempt':
            attempts += 1
            identity = row.get('attempt_id')
            if type(identity) is not int or identity <= 0 or identity in identities:
                raise AttemptCountUnknown('invalid or repeated render attempt identity', attempts)
            identities.add(identity)
        rows.append(row)
    return rows


def read_attempts(directory):
    """Count fsynced attempt records, even when RESULT was never published."""
    return sum(row.get('event') == 'render_attempt' for row in _trace(directory))


def _vector(value):
    _need(isinstance(value, (list, tuple)) and len(value) == 3, 'three coordinates required')
    return tuple(Fraction(item) for item in value)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def _scene_identity(scene):
    objects = []
    for item in scene['objects']:
        vertices = tuple(_vector(value) for value in item['vertices'])
        triangles = []
        for face in item['triangles']:
            points = tuple(vertices[index] for index in face)
            triangles.append(min(points[offset:]+points[:offset] for offset in range(3)))
        objects.append((tuple(sorted(vertices)), tuple(sorted(triangles))))
    return _fingerprint(tuple(sorted(objects)))


def _inside(directory, value, suffix):
    path = Path(value).resolve()
    _need(path.is_relative_to(directory) and path.suffix.lower() == suffix, 'artifact path escaped run directory')
    _need(path.is_file(), 'missing artifact ' + str(path))
    return path


def _pixel_counts(color, owners):
    """Independent four-neighbour boundary map using whole-frame integer RGB."""
    boundary = np.zeros(owners.shape, dtype=bool)
    vertical = color[1:].astype(np.int32) - color[:-1].astype(np.int32)
    changed = (owners[1:] != owners[:-1]) & ((vertical*vertical).sum(axis=2) >= 24*24)
    boundary[1:] |= changed
    boundary[:-1] |= changed
    horizontal = color[:, 1:].astype(np.int32) - color[:, :-1].astype(np.int32)
    changed = (owners[:, 1:] != owners[:, :-1]) & ((horizontal*horizontal).sum(axis=2) >= 24*24)
    boundary[:, 1:] |= changed
    boundary[:, :-1] |= changed
    return boundary


def _identities(index, scene, cameras):
    regions = index['regions']
    ids = index['roi_ids']
    _need(len(regions) == len(ids) == len(set(ids)) == 6, 'six unique discovered regions required')
    _need([row['roi_id'] for row in regions] == ids, 'region order or identity mismatch')
    _need(index['scene_identity'] == _scene_identity(scene), 'whole-scene source identity mismatch')
    poses = cameras['views']
    _need([pose['name'] for pose in poses] == index['view_order'] == VIEW_ORDER, 'complete candidate camera order mismatch')
    candidate = _fingerprint([{key: pose[key] for key in (
        'name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')} for pose in poses])
    _need(candidate == index['candidate_identity'], 'full camera candidate identity mismatch')
    object_indices = set()
    for row in regions:
        object_index = row['object_index']
        _need(type(object_index) is int and 0 <= object_index < len(scene['objects']), 'invalid region object index')
        _need(object_index not in object_indices, 'region object repeated')
        object_indices.add(object_index)
        source = scene['objects'][object_index]
        vertices = tuple(_vector(point) for point in row['vertices'])
        native = tuple(_vector(point) for point in source['vertices'])
        _need(len(native) == len(set(native)) == 4 and len(source['triangles']) == 2, 'region is not the whole selected quad object')
        _need(set(vertices) == set(native) and len(vertices) == 4, 'region vertices differ from current source')
        normal = _cross(_subtract(vertices[1], vertices[0]), _subtract(vertices[3], vertices[0]))
        _need(_vector(row['normal']) == normal, 'region orientation differs from its current boundary')
        _need(row['roi_id'] == 'roi_' + _fingerprint(vertices)[:24], 'region identity is not geometry-derived')
    masks = index['view_masks']
    _need(set(masks) == set(VIEW_ORDER), 'missing candidate mask')
    for name, mask in masks.items():
        _need(type(mask) is int and 0 <= mask < (1 << len(ids)), 'invalid geometric coverage mask')
        classifications = index['classifications'][name]
        _need(set(classifications) == set(ids), 'classification row count mismatch')
        for number, identity in enumerate(ids):
            complete = classifications[identity]['complete']
            _need(type(complete) is bool and complete == bool(mask & (1 << number)), 'geometry classification/mask disagreement')
    return {row['roi_id']: row for row in regions}, {pose['name']: pose for pose in poses}


def _frame(directory, frame, regions, pose, scenario, object_count, reference_hashes):
    name = frame['view_name']
    _need(frame['pose'] == pose and pose['size_px'] == [512, 512], 'complete generated camera pose mismatch')
    png_path = _inside(directory, frame['PNG'], '.png')
    npz_path = _inside(directory, frame['owner_depth_RGB_arrays'], '.npz')
    png_raw, npz_raw = png_path.read_bytes(), npz_path.read_bytes()
    _need(len(png_raw) == frame['PNG_bytes'] and _sha(png_raw) == frame['PNG_sha256'], 'PNG byte/hash mismatch')
    _need(len(npz_raw) == frame['compressed_array_file_bytes'] and _sha(npz_raw) == frame['arrays_sha256'], 'NPZ byte/hash mismatch')
    with np.load(npz_path, allow_pickle=False) as archive:
        _need(set(archive.files) == {'color', 'depth', 'owners'}, 'complete current buffer set required')
        arrays = {key: archive[key] for key in archive.files}
    specs = {'color': ('uint8', (512, 512, 3)), 'depth': ('float64', (512, 512)), 'owners': ('int32', (512, 512))}
    raw_hashes = {}
    for key, (dtype, shape) in specs.items():
        value, metadata = arrays[key], frame['arrays'][key]
        _need(str(value.dtype) == dtype and value.shape == shape, 'current buffer dtype/shape mismatch ' + key)
        raw_hashes[key] = _sha(value.tobytes(order='C'))
        _need(metadata == {'dtype': dtype, 'dtype_str': value.dtype.str, 'shape': list(shape),
                           'nbytes': value.nbytes, 'sha256': raw_hashes[key]}, 'raw current array evidence mismatch ' + key)
    payload = sum(value.nbytes for value in arrays.values())
    _need(payload == frame['array_payload_bytes'], 'array payload count mismatch')
    color, depth, owners = arrays['color'], arrays['depth'], arrays['owners']
    _need(bool(np.all((owners >= -1) & (owners < object_count))), 'owner references another source object')
    _need(not bool(np.isnan(depth).any()) and bool(np.all(np.isfinite(depth[owners >= 0]) & (depth[owners >= 0] > 0))), 'invalid winning depth')
    _need(frame['foreground_pixels'] == int(np.count_nonzero(np.isfinite(depth) & (depth > 0)))
          == int(np.count_nonzero(owners >= 0)), 'foreground depth/owner count mismatch')
    with Image.open(png_path) as image:
        _need(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512), 'full RGB PNG required')
        _need(image.tobytes() == color.tobytes(order='C'), 'PNG pixels differ from current RGB buffer')
    compare_reference = scenario == 'main' or name != 'BACK'
    if compare_reference:
        old_png = PREVIOUS / 'render' / (name + '.png')
        old_metadata_path = PREVIOUS / 'render' / (name + '.json')
        old_metadata_raw = old_metadata_path.read_bytes()
        _need(_sha(old_metadata_raw) == reference_hashes[str(old_metadata_path.resolve())], 'frozen 001 metadata source changed')
        old_metadata = json.loads(old_metadata_raw)
        old_png_raw = old_png.read_bytes()
        _need(_sha(old_png_raw) == old_metadata['PNG_sha256'] == reference_hashes[str(old_png.resolve())], 'frozen 001 PNG source changed')
        _need(png_raw == old_png_raw, 'main generated PNG differs from frozen 001 image')
        old_arrays = PREVIOUS / 'render' / old_metadata['owner_depth_RGB_arrays']
        _need(_sha(old_arrays.read_bytes()) == old_metadata['arrays_sha256'] == reference_hashes[str(old_arrays.resolve())], 'frozen 001 buffer source changed')
        with np.load(old_arrays, allow_pickle=False) as archive:
            _need(np.array_equal(color, archive['color']), 'main generated RGB differs from frozen 001 image')
    boundary = _pixel_counts(color, owners)
    rows = frame['pixel_rows']
    _need(len(rows) == len(regions) and {row['roi_id'] for row in rows} == set(regions), 'pixel row identity/count mismatch')
    _need(frame['pixel_evaluation_attempted_roi_count'] == len(regions), 'frame pixel attempt count mismatch')
    readable = []
    for row in rows:
        region = regions[row['roi_id']]
        object_index = region['object_index']
        mask = owners == object_index
        surface_count = int(np.count_nonzero(mask))
        boundary_count = int(np.count_nonzero(boundary & mask))
        front = sum(float(Fraction(value))*component for value, component in zip(region['normal'], pose['target_to_eye_unit'])) > 0
        qualified = front and surface_count >= 16 and boundary_count >= 4
        _need(row['object_index'] == object_index and row['view'] == name, 'pixel row source/view mismatch')
        _need(row['visible_surface_pixels'] == surface_count and row['contrasting_boundary_pixels'] == boundary_count, 'independent owner/RGB count disagreement')
        _need(type(row['front_facing']) is bool and row['front_facing'] == front and type(row['readable']) is bool and row['readable'] == qualified, 'independent pixel qualification disagreement')
        _need(row['minimum_surface_pixels'] == 16 and row['minimum_boundary_pixels'] == 4 and row['minimum_rgb_boundary_contrast'] == 24, 'pixel thresholds changed')
        _need(row['annotations_count_as_evidence'] is False and row['model_texture_recognition_proven'] is False, 'pixel scope changed')
        if qualified:
            readable.append(row['roi_id'])
    metadata_path = _inside(directory, frame['metadata_path'], '.json')
    metadata_raw = metadata_path.read_bytes()
    _need(_sha(metadata_raw) == frame['metadata_sha256'] and len(metadata_raw) == frame['metadata_bytes'], 'frame metadata publication mismatch')
    metadata = _read(metadata_path)
    _need(set(metadata) == (set(frame) - {'metadata_sha256', 'metadata_bytes'}) | {'metadata_stage_scope'},
          'frame metadata fields differ from result publication schema')
    for key in metadata:
        if key not in ('stages', 'metadata_stage_scope'):
            _need(metadata[key] == frame[key], 'frame metadata differs from result ' + key)
    _need(metadata['stages'] == {name: value for name, value in frame['stages'].items() if name != 'metadata'},
          'pre-publication frame stages differ from final completed stage records')
    return {'readable': set(readable), 'PNG_bytes': len(png_raw), 'NPZ_bytes': len(npz_raw),
            'array_payload_bytes': payload, 'metadata_bytes': len(metadata_raw), 'raw_array_sha256': raw_hashes,
            'reference_compared': compare_reference}


def _ids(mask, identities):
    return [identity for number, identity in enumerate(identities) if mask & (1 << number)]


def _timings(result, trace):
    started, closed = result['started_ns'], result['work_closed_ns']
    _need(type(started) is int and type(closed) is int and closed >= started, 'invalid child work interval')
    _need(result['elapsed_before_result_publication_ns'] == closed-started, 'child work duration mismatch')
    for name, value in result['stages'].items():
        begin, end, delta = value['started_ns'], value['closed_ns'], value['elapsed_ns']
        _need(all(type(item) is int for item in (begin, end, delta))
              and started <= begin <= end <= closed and delta == end-begin, 'invalid stage interval ' + name)
        if name == 'stdlib_import':
            continue
        starts = [row for row in trace if row['event'] == 'stage_start' and row.get('stage') == name]
        ends = [row for row in trace if row['event'] == 'stage_complete' and row.get('stage') == name]
        _need(len(starts) == len(ends) == 1, 'stage trace count mismatch ' + name)
        _need(begin <= starts[0]['monotonic_ns'] <= end <= ends[0]['monotonic_ns'], 'stage trace order mismatch ' + name)
        _need(all(ends[0][key] == value[key] for key in ('started_ns', 'closed_ns', 'elapsed_ns')), 'stage result/trace mismatch ' + name)
    for frame in result['frames']:
        prefix = 'frame_' + str(frame['attempt_id']).zfill(2) + '.'
        _need(set(frame['stages']) == {'render_attempt_publication', 'raster', 'pixels', 'PNG', 'NPZ',
                                     'array_metadata', 'observe', 'metadata'}, 'frame stages incomplete')
        for name, value in frame['stages'].items():
            _need(result['stages'][prefix+name] == value, 'frame stage alias differs from result')


def _replay(result, frame_facts, arm):
    index, frames, steps = result['index'], result['frames'], result['steps']
    identities = index['roi_ids']
    all_mask = (1 << len(identities))-1
    _need(len(steps) == len(frames), 'step count differs from generated frame count')
    observed, covered, history = [], 0, set()
    for frame, facts, step in zip(frames, frame_facts, steps):
        name = frame['view_name']
        if arm == 'B':
            gains = [(view, (index['view_masks'][view] & ~covered).bit_count())
                     for view in index['view_order'] if view not in observed]
            gains = [item for item in gains if item[1] > 0]
            expected = 'SCENE' if not observed else max(gains, key=lambda item: item[1])[0] if gains else None
            _need(name == expected, 'on-demand view differs from current-state finite greedy choice')
        geometry = index['view_masks'][name]
        readable = sum(1 << number for number, identity in enumerate(identities) if identity in facts['readable'])
        shortfall = set(_ids(geometry & ~readable, identities))
        history.update(shortfall)
        added = geometry & readable & ~covered
        covered |= geometry & readable
        receipt = frame['receipt']
        _need(receipt['actual_image_delivered'] is True and receipt['pixel_evidence_scope'] == 'actual_common_depth_owner', 'unqualified image receipt')
        _need(receipt['scene_identity'] == index['scene_identity'] and receipt['candidate_identity'] == index['candidate_identity'], 'receipt source/candidate mismatch')
        _need(receipt['view_name'] == name and Path(receipt['image_path']).resolve() == Path(frame['PNG']).resolve()
              and receipt['image_sha256'] == frame['PNG_sha256'], 'receipt does not bind generated PNG')
        _need(receipt['readable_roi_ids'] == sorted(facts['readable']), 'receipt readable IDs differ from current pixels')
        update = {'view_name': name, 'reused': False, 'new_roi_ids': _ids(added, identities),
                  'covered_roi_ids': _ids(covered, identities), 'unresolved_roi_ids': _ids(all_mask & ~covered, identities)}
        _need(frame['state_update'] == update, 'coverage update differs from geometry/pixel intersection')
        expected_step = {'attempt_id': frame['attempt_id'], 'view_name': name,
            'geometry_complete_roi_ids': _ids(geometry, identities), 'readable_roi_ids': sorted(facts['readable']),
            'pixel_shortfall_roi_ids': sorted(shortfall), 'pixel_rows': frame['pixel_rows'],
            'new_roi_ids': update['new_roi_ids'], 'covered_roi_ids': update['covered_roi_ids'],
            'unresolved_roi_ids': update['unresolved_roi_ids'], 'receipt': receipt}
        _need(step == expected_step, 'step record omits or changes current observation facts')
        observed.append(name)
    possible = 0
    for mask in index['view_masks'].values():
        possible |= mask
    final = {'observed_views': observed, 'covered_roi_ids': _ids(covered, identities),
        'unresolved_roi_ids': _ids(all_mask & ~covered, identities),
        'candidate_pool_uncovered_roi_ids': _ids(all_mask & ~possible, identities),
        'state_updates': len(observed), 'scope': 'registered finite camera pool'}
    _need(result['final_state'] == final, 'final state differs from actual delivered intersections')
    _need(result['pixel_shortfall_history_roi_ids'] == sorted(history), 'historical pixel shortfall mismatch')
    final_shortfall = sorted(history.intersection(final['unresolved_roi_ids']))
    _need(result['final_pixel_shortfall_roi_ids'] == final_shortfall, 'recovered shortfall incorrectly counted as final')
    _need(not any(index['view_masks'][view] & ~covered for view in index['view_order'] if view not in observed), 'run stopped with an unattempted geometric gain')
    repeated = result['repeat_query']
    _need(repeated['render_attempts_before'] == repeated['render_attempts_after'] == len(frames)
          and repeated['new_render_attempts'] == 0, 'same-state repeat generated an image')
    _need(repeated['state_before'] == repeated['state_after'] == final and repeated['next_view'] is None, 'same-state repeat changed coverage or failed to terminate')
    _need(repeated['reuse_update'] == {'view_name': observed[-1], 'reused': True, 'new_roi_ids': []}, 'same-state receipt replay mismatch')
    return final, history, final_shortfall


def validate_run(directory: Path, arm: str, scenario: str) -> dict:
    """Read the complete child publication and current frame artifacts."""
    directory = Path(directory).resolve()
    _need(arm in ('A', 'B') and scenario in ('main', 'pixel_shortfall'), 'unknown registered arm/scenario')
    result_path = directory / 'RESULT.json'
    raw_result = result_path.read_bytes()
    result = _read(result_path)
    _need(result['schema'] == 'active-coverage-002-runtime-v1' and result['arm'] == arm
          and result['scenario'] == scenario and result['status'] == 'completed', 'result run/schema/status mismatch')
    _need(Path(result['output_directory']).resolve() == directory and not result['exceptions'], 'result directory or exceptions mismatch')
    frozen = _read(HERE / 'FROZEN.json')
    reference_hashes = frozen['parent_post_run_reference_only']
    scene_path = HERE / 'inputs/SCENE_GEOMETRY_RATIONAL.json'
    camera_path = HERE / 'inputs' / ('CAMERAS.json' if scenario == 'main' else 'CAMERAS_PIXEL_SHORTFALL.json')
    _need(Path(result['source_scene']).resolve() == scene_path.resolve()
          and Path(result['source_camera']).resolve() == camera_path.resolve(), 'result source input paths mismatch')
    _need(result['source_scene_sha256'] == _sha(scene_path.read_bytes())
          and result['source_camera_sha256'] == _sha(camera_path.read_bytes()), 'result source input bytes changed')
    expected_inputs = [scene_path, camera_path, HERE / 'runtime.py', PREVIOUS / 'coverage.py', PREVIOUS / 'render/adapter.py']
    _need(result['inputs_sha256'] == {str(path.resolve()): frozen['runtime_sources'][str(path.resolve())]
                                    for path in expected_inputs}, 'full runtime input binding mismatch')
    scene, cameras = _read(scene_path), _read(camera_path)
    dependencies = _read(HERE / 'inputs/DEPENDENCIES.json')
    _need(result['dependencies'] == dependencies, 'fixed product dependency binding mismatch')
    _need(dependencies['source_count'] == 138 and dependencies['source_sha256'] ==
          '4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6', 'fixed product identity changed')
    audit = result['audit']
    _need(audit['installed_before_dynamic_imports'] is True and audit['forbidden_old_evidence_reads'] == 0
          and audit['old_evidence_read_attempts'] == [] and audit['forbidden_old_writes'] == 0
          and audit['old_write_attempts'] == [], 'child accessed old image/answer evidence')
    trace_path = directory / 'TRACE.jsonl'
    trace_raw = trace_path.read_bytes()
    trace = _trace(directory)
    _need(bool(trace), 'complete child trace required')
    previous_time = result['started_ns']
    for sequence, row in enumerate(trace, 1):
        timestamp = row['monotonic_ns']
        _need(type(timestamp) is int and timestamp >= previous_time and row['sequence'] == sequence, 'trace sequence/time disorder')
        _need(row['arm'] == arm and row['scenario'] == scenario and row['process_id'] == result['process_id'], 'trace run binding mismatch')
        previous_time = timestamp
    _need(trace[0]['event'] == 'runtime_start' and trace[-1]['event'] == 'process_complete', 'incomplete process trace')
    intents = [row for row in trace if row['event'] == 'render_attempt']
    completed = [row for row in trace if row['event'] == 'render_complete']
    frame_completed = [row for row in trace if row['event'] == 'frame_complete']
    frames, attempts = result['frames'], result['render_attempts']
    count = len(intents)
    _need(count == len(completed) == len(frame_completed) == len(frames) == len(attempts), 'render attempt/return/frame count mismatch')
    _need(0 < count <= 6 and [row['attempt_id'] for row in intents] == list(range(1, count+1)), 'render attempt IDs are not consecutive')
    views = [frame['view_name'] for frame in frames]
    _need(len(set(views)) == count and all(name in VIEW_ORDER for name in views), 'view repeated or outside finite pool')
    if arm == 'A':
        _need(views == VIEW_ORDER, 'fixed-six arm did not generate the registered six views')
    if scenario == 'main' and arm == 'B':
        _need(views == ['SCENE', 'BACK'], 'main on-demand arm did not generate exactly SCENE/BACK')
    _timings(result, trace)
    regions, poses = _identities(result['index'], scene, cameras)
    frame_facts = []
    for number, (frame, intent, finish, published, attempt) in enumerate(zip(frames, intents, completed, frame_completed, attempts), 1):
        name = frame['view_name']
        _need(all(row['attempt_id'] == number and row['view_name'] == name for row in (frame, intent, finish, published, attempt)), 'frame trace identity mismatch')
        _need(attempt['status'] == 'completed' and attempt['intent_ns'] == intent['monotonic_ns']
              and attempt['intent_trace_sequence'] == intent['sequence'], 'attempt intent/status mismatch')
        begin, end = attempt['render_started_ns'], attempt['render_closed_ns']
        raster = frame['stages']['raster']
        _need(frame['stages']['render_attempt_publication']['closed_ns'] <= raster['started_ns'] <= begin <= end <= raster['closed_ns'], 'render preceded its durable intent')
        _need(finish['started_ns'] == begin and finish['closed_ns'] == end and finish['elapsed_ns'] == end-begin,
              'render timing differs between result and trace')
        _need(end <= finish['monotonic_ns'] <= frame['stages']['pixels']['started_ns']
              and frame['stages']['metadata']['closed_ns'] <= attempt['completed_ns'] <= published['monotonic_ns'] <= result['work_closed_ns'], 'frame execution/publication order mismatch')
        _need(published['PNG_sha256'] == frame['PNG_sha256'] and published['arrays_sha256'] == frame['arrays_sha256'], 'frame complete hashes mismatch')
        frame_facts.append(_frame(directory, frame, regions, poses[name], scenario, len(scene['objects']), reference_hashes))
    final, history, final_shortfall = _replay(result, frame_facts, arm)
    _need(result['metrics']['raster_attempts'] == result['metrics']['raster_completed']
          == result['metrics']['frames_completed'] == count, 'result workload counts mismatch')
    _need(result['metrics']['pixel_tests'] == count*6, 'child pixel test count mismatch')
    _need(result['metrics']['pixel_test_attempts'] == count*6, 'child pixel attempt count mismatch')
    totals = {key: sum(row[key] for row in frame_facts)
              for key in ('PNG_bytes', 'NPZ_bytes', 'array_payload_bytes', 'metadata_bytes')}
    for key in ('PNG_bytes', 'NPZ_bytes', 'array_payload_bytes'):
        _need(result['metrics'][key] == totals[key], 'result byte total mismatch ' + key)
    _need(result['metrics']['frame_metadata_bytes'] == totals['metadata_bytes'], 'frame metadata byte total mismatch')
    _need(result['metrics']['new_model_provider_Blender_API_runs'] == 0, 'new external execution recorded')
    if scenario == 'main':
        _need(len(final['covered_roi_ids']) == 5 and len(final['candidate_pool_uncovered_roi_ids']) == 1
              and len(final['unresolved_roi_ids']) == 1, 'main actual coverage qualification failed')
    else:
        back = next(step for step in result['steps'] if step['view_name'] == 'BACK')
        _need(bool(back['pixel_shortfall_roi_ids']), 'BACK64 control has no actual geometric/pixel shortfall')
        _need(final['unresolved_roi_ids'] == final['candidate_pool_uncovered_roi_ids'] and not final_shortfall,
              'control ended with recoverable or unresolved pixel shortfall')
        if arm == 'B':
            back_position = views.index('BACK')
            _need(back_position < len(views)-1, 'on-demand pixel shortfall stopped before another finite candidate')
            later_added = {identity for step in result['steps'][back_position+1:] for identity in step['new_roi_ids']}
            _need(bool(set(back['pixel_shortfall_roi_ids']).intersection(later_added)),
                  'later control images did not actually recover a BACK pixel-shortfall region')
    publication_path = _inside(directory, result['publication_receipt'], '.json')
    _need(publication_path == directory/'RESULT_PUBLICATION.json', 'result publication path mismatch')
    publication_raw = publication_path.read_bytes()
    publication = json.loads(publication_raw)
    _need(publication['RESULT_sha256'] == _sha(raw_result) and publication['RESULT_bytes'] == len(raw_result), 'result publication bytes mismatch')
    _need(result['work_closed_ns'] <= publication['started_ns'] <= publication['closed_ns']
          <= trace[-1]['monotonic_ns'] and publication['elapsed_ns'] == publication['closed_ns']-publication['started_ns'], 'result publication interval mismatch')
    _need(trace[-1]['status'] == 'completed' and trace[-1]['RESULT_sha256'] == publication['RESULT_sha256'], 'process completion/result mismatch')
    work_rows = [row for row in trace if row['event'] == 'work_complete']
    _need(len(work_rows) == 1 and work_rows[0]['status'] == 'completed'
          and work_rows[0]['metrics'] == result['metrics'], 'work completion trace mismatch')
    work_sequence = work_rows[0]['sequence']
    _need(work_rows[0]['monotonic_ns'] <= result['work_closed_ns']
          and sum(len(line) for line in trace_raw.splitlines(keepends=True)[:work_sequence])
          == result['trace_bytes_before_result_publication'], 'trace publication byte count mismatch')
    return {'render_attempts': count, 'render_completed': count, 'views': views,
        'roi_ids': result['index']['roi_ids'], 'covered_roi_ids': final['covered_roi_ids'],
        'unresolved_roi_ids': final['unresolved_roi_ids'],
        'candidate_pool_uncovered_roi_ids': final['candidate_pool_uncovered_roi_ids'],
        'scene_identity': result['index']['scene_identity'], 'candidate_identity': result['index']['candidate_identity'],
        'pixel_tests': count*6, 'validator_pixel_tests': count*6, 'validator_PNG_decodes': count,
        'parent_old_image_comparisons': sum(row['reference_compared'] for row in frame_facts),
        **totals, 'result_bytes': len(raw_result), 'publication_bytes': len(publication_raw),
        'trace_bytes': len(trace_raw), 'raw_array_sha256': [row['raw_array_sha256'] for row in frame_facts],
        'stage_timings': result['stages'], 'result_publication': publication,
        'pixel_shortfall_history_roi_ids': sorted(history), 'final_pixel_shortfall_roi_ids': final_shortfall,
        'recovered_pixel_shortfall_roi_ids': sorted(history.difference(final_shortfall)),
        'repeat_query_new_render_attempts': 0, 'forbidden_old_evidence_reads': 0,
        'scope': 'Parent full-file readback and independent current owner/RGB count replay. No new renderer or coverage solver execution.'}

