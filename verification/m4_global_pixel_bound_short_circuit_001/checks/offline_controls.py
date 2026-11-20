"""Replay archived coverage decisions and native frame evidence in both installs."""

import argparse
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
A = V / 'm4_bound_blocker_evidence_001/install/PRODUCT_RUN_BINDING.json'
ARCHIVE_HELPER = V / 'm4_dense_region_brief_001/checks/offline_controls.py'
CAPTURE_HELPER = V / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
PATCH = 'human_eye_plugin/active_observation_region_task.py'
BINDING_SERVICE_FIELDS = ('disk_status', 'runtime_source_sha256', 'source_check_scope', 'source_status')
FIXTURES = (
    ('dense', 'm4_bound_blocker_evidence_001', 'QP',
     'c4558bea03d6b2dbb01a19057209b8a5efe66f76f5b5c3e519ebc7e6f372fdac', 1, (14, 3478, 6148)),
    ('assembly28', 'm4_cross_scale_pixel_evidence_001', 'P1',
     '0802bfd8968a14ceb9cb209b4378d27b3045acc61d9bede297d42dba29c5658e', 2, (28, 416, 744)),
    ('cross21', 'm4_cross_scale_cold_frustum_001', 'B1',
     '7f94dc9f4a1d01d5b8b38064293887504b8025065a3e2e994370aea4a1f1a3b0', 2, (21, 148, 184)),
)
BOUNDARY = {
    'empty': [], 'strict_15': [15], 'exact_16': [16], 'unknown': [None],
    'mixed_below_then_16': [3, 15, 16, 7], 'mixed_below_then_unknown': [15, None, 999],
    'first_above_makes_tail_irrelevant': [1551, 0, None], 'all_below': [0, 7, 15],
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()


def read(path):
    return json.loads(Path(path).read_bytes())


class ArchiveAudit:
    """Give the prior current-capture decoder only members of the original ZIP."""

    def __init__(self, archive):
        self.archive = archive

    def read(self, path, digest=None, within=None):
        path = Path(path).resolve()
        require(within is not None and path.is_relative_to(Path(within).resolve()), 'raw_host_wire_scope_changed')
        raw = self.archive.raw(path)
        require(digest is None or sha(raw) == digest, 'raw_host_wire_digest_changed')
        return json.loads(raw)

    @staticmethod
    def check(ok, reason):
        require(ok, reason)


def archived_cases(pins, archive_helpers, base):
    if base['dependency_root'] not in sys.path:
        sys.path.insert(0, base['dependency_root'])
    helpers = runpy.run_path(str(CAPTURE_HELPER))
    cases = {}
    with ExitStack() as stack:
        for key, batch, label, digest, count, sizes in FIXTURES:
            archive = archive_helpers['Archive'](pins, stack, batch, label, digest)
            cold = archive.take(1)
            installed = json.loads(pins.raw(V / batch / 'install/PRODUCT_RUN_BINDING.json'))
            terminal = archive.read(archive.slot / 'TERMINAL_SOURCE.json')
            result = archive.read(archive.slot / 'SLOT_RESULT.json')
            pub = archive.read(archive.slot / 'SLOT_PUBLICATION.json')
            require(result['product_source_sha256'] == installed['source_sha256']
                    and pub['result_sha256'] == sha(archive.raw(archive.slot / 'SLOT_RESULT.json'))
                    and pub['status'] == result['status'] == 'completed'
                    and result['terminal_source']['sha256'] == sha(archive.raw(archive.slot / 'TERMINAL_SOURCE.json'))
                    and terminal['source']['asset_sha256'] == result['asset_sha256']
                    == sha(archive.raw(archive.slot / 'native/input.blend')), 'original_slot_binding/' + key)
            audit = ArchiveAudit(archive)
            captures, _ = helpers['decode_captures'](archive.slot, installed, audit)
            observed = cold['producer']
            capture = helpers['current_capture'](captures, observed['binding'], audit)
            meshes = capture['meshes']
            require((len(meshes), sum(len(mesh['vertices']) for mesh in meshes),
                     sum(len(mesh['faces']) for mesh in meshes)) == sizes and all(terminal['display_object_mask']),
                    'current_mesh_denominator_changed/' + key)
            native = terminal['objects']
            require(len(meshes) == len(native) and all(mesh['object_id'] == obj['object_id']
                        and mesh['name'] == obj['name'] and mesh['vertices'] == obj['evaluated']['vertices_world_m']
                        and mesh['faces'] == obj['evaluated']['triangles'] for mesh, obj in zip(meshes, native, strict=True)),
                    'real_host_capture_not_equal_to_published_meshes/' + key)
            hot = archive.take(2) if count == 2 else None
            if hot:
                h = hot['producer']
                require(h['binding'] == observed['binding'] and h['work']['global_index_cache_hit'] is True
                        and h['work']['pixel_bound_region_calls'] == h['work']['raster_attempts'] == 0
                        and h['observation_status'] == 'prediction_only', 'invalid_retained_hot_no_image/' + key)
            cases[key] = {'capture': capture, 'cold': cold, 'hot': hot, 'counts': sizes,
                          'asset_sha256': result['asset_sha256']}
    return cases


def stable(value):
    """Remove elapsed clocks and the specific metric this optimization changes."""
    result = deepcopy(value)
    del result['stages']
    for frames in ('frames', 'constructed_frames'):
        for frame in result[frames]:
            frame.pop('feedback_stages', None)
    for field in ('frustum_proof_ns', 'pixel_bound_region_calls'):
        result['work'].pop(field)
    return result


def first_difference(a, b, path='value'):
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return f'{path}/different_keys/{sorted(a.keys() ^ b.keys())}'
        for key in a:
            if a[key] != b[key]:
                return first_difference(a[key], b[key], f'{path}/{key}')
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for index, (left, right) in enumerate(zip(a, b, strict=True)):
            if left != right:
                return first_difference(left, right, f'{path}/{index}')
    return f'{path}/{str(a)[:130]} vs {str(b)[:130]}'


def compare_archived(value, reference):
    # Earlier 21/28 captures predate the additive provenance in the blocker table.
    new = deepcopy(value['facts']['region_task'])
    old = deepcopy(reference['facts']['region_task'])
    if 'blocker_evidence' not in old:
        new.pop('blocker_evidence', None)
    if new != old:
        raise ValueError('archived_task_regions/' + first_difference(new, old))
    old_binding = {key: member for key, member in reference['binding'].items() if key not in BINDING_SERVICE_FIELDS}
    if value['binding'] != old_binding:
        raise ValueError('archived_task_binding/' + first_difference(value['binding'], old_binding))
    require(value['steps'] == reference['steps'] and value['image_delivery'] == reference['image_delivery'],
            'coverage_steps_differ_from_archived_capture')
    require([scope['skipped_views'] for scope in value['scopes']] ==
            [scope['skipped_views'] for scope in reference['scopes']], 'archived_skip_certificates_changed')
    require([frame_ids(value) for value in value['constructed_frames']] ==
            [frame_ids(value) for value in reference['constructed_frames']], 'original_frame_or_pixels_changed')


def frame_ids(frame):
    keys = ('scope_id', 'view_name', 'frame_identity', 'image_ref', 'image_sha256', 'arrays_sha256')
    return dict(zip(keys, (frame[key] for key in keys), strict=True))


def replay(regions, original, cold, hot, directory):
    frames = cold['producer']['constructed_frames']
    scopes = {scope['binding']['binding_sha256']: scope for scope in cold['producer']['scopes']}
    actual_frames = iter(frames)
    measured, decisions = {}, []
    original_bound = regions.pixel_center_upper_bound
    prepared = []

    def reuse_index(build):
        if prepared:
            return prepared[0], True
        value = build()
        prepared.append(value)
        return value, False

    def bound(region, objects, pose):
        calculated = original_bound(region, objects, pose)
        measured.setdefault(pose['name'], []).append(calculated)
        return calculated

    class OriginalImages(regions.ActiveObservationImages):
        def render_view(self, name):
            frame = deepcopy(next(actual_frames))
            scope = scopes[self.output_directory.name]
            require(frame['view_name'] == name and frame['scope_id'] == scope['scope_id'],
                    'real_scope_requested_an_unarchived_frame')
            return frame

    conditions = cold['arguments']['query']['region_task']
    with patch.object(regions, 'ActiveObservationImages', OriginalImages), \
            patch.object(regions, 'pixel_center_upper_bound', bound):
        pic = regions.observe_region_task(original, directory, conditions,
                construction_callback=decisions.append, prepare_global_index=reuse_index)
        compare_archived(pic, cold['producer'])
        require(next(actual_frames, None) is None and decisions == [f['view_name'] for f in frames]
                and sum(map(len, measured.values())) == pic['work']['pixel_bound_region_calls'],
                'actual_bound_or_frame_accounting_changed')
        predicted = regions.observe_region_task(original, directory, conditions, include_image=False,
                                                 prepare_global_index=reuse_index)
        require(predicted['status'] == 'predicted' and predicted['observation_status'] == 'prediction_only'
                and not predicted['frames'] and not predicted['constructed_frames']
                and all(not predicted['work'][x] for x in ('index_calls', 'raster_attempts', 'pixel_bound_region_calls'))
                and predicted['work']['global_index_cache_hit'] is True
                and pic['binding'] == predicted['binding'], 'same_capture_no_image_is_not_independent_prediction')
        if hot:
            compare_archived(predicted, hot['producer'])
    return pic, predicted, measured


def expected_branch(counts):
    return bool(counts) and all(count is not None and count < 16 for count in counts)


def boundary_run(regions, counts):
    keys = tuple(f'region_{n}' for n in range(len(counts)))
    # Keep an unrelated placeholder to force the real empty-eligible branch.
    relevant = set(keys) or {'not_in_session'}
    session = SimpleNamespace(regions=tuple(SimpleNamespace(roi_id=key) for key in keys),
        objects=(), cameras={'views': [{'name': 'LEFT'}]}, summary=lambda: {'covered_roi_ids': []},
        index=SimpleNamespace(classifications={'LEFT': {key: {'complete': True} for key in keys}}))
    calls, renders = [], []
    ledger = Counter()
    select = iter(('SCENE', 'LEFT', None))

    def bound(region, _objects, _pose):
        value = counts[len(calls)]
        calls.append(region.roi_id)
        return {'roi_id': region.roi_id, 'status': 'bounded' if value is not None else 'unknown', 'upper_bound': value}

    class Frames:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def render_view(name):
            renders.append(name)
            return dict(view_name=name, frame_identity=name, image_sha256=name, PNG_bytes=1,
                        compressed_array_file_bytes=1, array_payload_bytes=1,
                        patch_mapping_identity='p', owner_schema='p', owner_mapping_identity='p')

        @staticmethod
        def observe_frame(_frame):
            return {'update': {}, 'summary': {}, 'stages': {}}

    binding = {'binding_sha256': 'fixture', 'scene_revision': 'fixture', 'camera_identity': 'fixture'}
    with patch.object(regions, 'ActiveObservationImages', Frames), \
            patch.object(regions, '_task_next_view', side_effect=lambda *_: next(select)), \
            patch.object(regions, '_facts', return_value={}), \
            patch.object(regions, 'pixel_center_upper_bound', side_effect=bound):
        scope, _ = regions._render_scope(session, (), binding, 'global', relevant, HERE, ledger, {}, None, None, True)
    skip = expected_branch(counts)
    require(renders == (['SCENE'] if skip else ['SCENE', 'LEFT']) and
            bool(scope['skipped_views']) is skip and ledger['pixel_bound_region_calls'] == len(calls),
            'threshold_control_wrong_path')
    if skip:
        require([row['upper_bound'] for row in scope['skipped_views'][0]['regions']] == counts,
                'below_threshold_lost_certificate')
    return {'actual_calls': len(calls), 'call_keys': calls, 'skipped': skip,
            'renders_requested_on_test_double': renders, 'skip_certificates': scope['skipped_views']}


def render_payload(mcp, result, archived, detail):
    # Keep the genuine session binding and outer service metadata in the formatter replay.
    value = deepcopy({**archived, **result})
    if 'binding' in result and 'binding' in archived:
        metadata = {key: archived['binding'][key] for key in BINDING_SERVICE_FIELDS if key in archived['binding']}
        value['binding'].update(metadata)
        for scope in value.get('scopes', []):
            scope['binding'].update(metadata)
    return mcp._tool_result(value, is_error=False, response_detail=detail)


def child(binding):
    install = Path(binding['install_root']).resolve()
    sys.path[:0] = [str(install), binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin import active_observation_region_task as regions

    module = Path(regions.__file__).resolve()
    require(module == install / PATCH and len(binding['source_manifest']) == 143, 'runtime_not_isolated')
    source = next(row['sha256'] for row in binding['source_manifest'] if row['path'] == PATCH)
    require(sha(module.read_bytes()) == source, 'loaded_module_not_pinned')
    inputs = json.load(sys.stdin)
    results = {}
    with tempfile.TemporaryDirectory(prefix='human_eye_pixel_bound_replay_') as directory:
        for key, case in inputs['cases'].items():
            cold = case['cold']
            pic, predicted, measured = replay(regions, case['capture'], cold, case['hot'], Path(directory))
            wire = render_payload(mcp, pic, cold['producer'], 'brief')
            require(wire['isError'] is False, 'brief_formatter_rejected_replayed_result/' + key)
            images = wire['content'][1:]
            require(images == cold['original_result']['content'][1:], 'replayed_brief_image_bytes_changed/' + key)
            if key == 'dense':
                text, old_text = (item['content'][0]['text'] for item in (wire, cold['original_result']))
                require(json.loads(text) == json.loads(old_text) and len(text.encode()) == len(old_text.encode()),
                        'dense_v2_public_whole_reply_changed')
            hot_wire = render_payload(mcp, predicted, case['hot']['producer'] if case['hot'] else cold['producer'], 'full')
            require(len(hot_wire['content']) == 1 and hot_wire['isError'] is False, 'no_image_formatter_changed/' + key)
            # The full response intentionally includes actual bound counters.
            semantic = stable(pic)
            results[key] = {
                'source_counts': case['counts'], 'asset_sha256': case['asset_sha256'],
                'original_wire_sha256': cold['wire_sha256'], 'semantic_sha256': sha(encoded(semantic)),
                'hot_prediction_semantic_sha256': sha(encoded(stable(predicted))),
                'brief': wire, 'brief_body_sha256': sha(wire['content'][0]['text'].encode()),
                'brief_body_bytes': len(wire['content'][0]['text'].encode()), 'bound_results': measured,
                'work_pixel_bound_region_calls': pic['work']['pixel_bound_region_calls'],
                'bound_stage_elapsed_ns': {key: value['elapsed_ns'] for key, value in pic['stages'].items()
                                          if key.startswith('pixel_bounds_')},
                'frames': [frame_ids(frame) for frame in pic['constructed_frames']],
                'global_skips': pic['scopes'][0]['skipped_views'],
                'task_summary': pic['facts']['region_task']['summary'],
                'blocker_evidence': pic['facts']['region_task'].get('blocker_evidence'),
            }
    legacy = {name: sha(encoded(render_payload(mcp, value, value, detail)))
              for name, (value, detail) in inputs['legacy'].items()}
    report = {'source_sha256': binding['source_sha256'], 'module_sha256': source, 'fixtures': results, 'legacy': legacy,
              'tool_catalogue_sha256': sha(encoded([mcp.LIVE_MCP_TOOLS_SCHEMA, mcp.SPATIAL_TASK_TOOLS_SCHEMA])),
              'boundary': {key: boundary_run(regions, counts) for key, counts in BOUNDARY.items()}}
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))


def compare(a, b, archive_helpers):
    require(a['legacy'] == b['legacy'] and a['tool_catalogue_sha256'] == b['tool_catalogue_sha256'],
            'source_region_ordinary_or_schema_compatibility_change')
    for key, counts in BOUNDARY.items():
        baseline, candidate = a['boundary'][key], b['boundary'][key]
        short_length = next((i for i, val in enumerate(counts, 1) if val is None or val >= 16), len(counts))
        require(baseline['actual_calls'] == len(counts) and candidate['actual_calls'] == short_length
                and candidate['call_keys'] == baseline['call_keys'][:short_length]
                and all(baseline[field] == candidate[field] for field in
                        ('skipped', 'skip_certificates', 'renders_requested_on_test_double')),
                'boundary_equivalence_or_early_exit_failed/' + key)

    for key in a['fixtures']:
        original, optimized = a['fixtures'][key], b['fixtures'][key]
        for field in ('semantic_sha256', 'hot_prediction_semantic_sha256', 'brief', 'frames', 'global_skips',
                      'task_summary', 'blocker_evidence'):
            require(original[field] == optimized[field], 'actual_fixture_equivalence/' + key + '/' + field)
        aa, bb = original['bound_results'], optimized['bound_results']
        require(aa.keys() == bb.keys() and all(bb[view] == aa[view][:len(bb[view])] for view in aa),
                'exact_bound_certificates_or_candidate_order_changed/' + key)
        if key == 'dense':
            require(len(aa['LEFT']) == 10 and len(bb['LEFT']) == 1 and bb['LEFT'][0]['upper_bound'] == 1551
                    and [f['view_name'] for f in optimized['frames']] == ['SCENE', 'LEFT']
                    and len(optimized['blocker_evidence']['rows']) == 2
                    and optimized['task_summary']['eligible_region_count'] == 13
                    and optimized['task_summary']['observed_region_count'] == 11, 'dense_real_LEFT_not_short_circuited')
        elif key == 'assembly28':
            require(len(aa['TOP']) == len(bb['TOP']) == 1 and bb['TOP'][0]['upper_bound'] == 5026
                    and any(f['view_name'] == 'TOP' and f['scope_id'] == 'global' for f in optimized['frames']),
                    'assembly_global_TOP_materialization_changed')
        else:
            skipped = optimized['global_skips']
            require(len(skipped) == 5 and sum(len(view['regions']) for view in skipped) == 7
                    and sum(map(len, aa.values())) == sum(map(len, bb.values())) == 7
                    and [f['view_name'] for f in optimized['frames'] if f['scope_id'] == 'global'] == ['SCENE'],
                    'cross21_actual_skip_certificate_denominator_changed')
        stages = archive_helpers['cli_stages'](original['brief'])
        require(stages['passed'], 'fixed_cli_replay_lost_original_public_delivery')
        for row in (original, optimized):
            row['CLI'] = stages
            row.pop('brief')


def parent(candidate, output):
    archive_helpers = runpy.run_path(str(ARCHIVE_HELPER))
    prior = runpy.run_path(str(archive_helpers['PRIOR']))
    pins = prior['Evidence']()
    for path in (Path(__file__), ARCHIVE_HELPER, CAPTURE_HELPER,
                 archive_helpers['PRIOR'], archive_helpers['TYPED_PATH'], archive_helpers['POLICY_PATH']):
        pins.raw(path)
    bindings = []
    for path in (A, candidate):
        obj = json.loads(pins.raw(path))
        manifest = {row['path']: row['sha256'] for row in obj['source_manifest']}
        require(len(manifest) == 143, 'unexpected_distribution_source_count')
        for rel in (PATCH, 'human_eye_plugin/active_observation.py', 'human_eye_plugin/active_observation_host.py',
                    'human_eye_plugin/active_observation_images.py', 'human_eye_plugin/live_spatial_mcp.py'):
            pins.raw(Path(obj['install_root']) / rel, manifest[rel])
        bindings.append((obj, manifest, Path(path).resolve()))
    (orig, a_manifest, a_path), (opt, b_manifest, b_path) = bindings
    require(orig['preparation_git'] == 'e03ee486dc8f86f6a7d2fb75d012d181edcf8f3c'
            and orig['source_sha256'] == '84bf65eedbc0866375d760025437993b90ec54325af09b4e1f36b74abe233d62'
            and a_manifest.keys() == b_manifest.keys() and
            [path for path in a_manifest if a_manifest[path] != b_manifest[path]] == [PATCH],
            'baseline_identity_or_only_source_change_invalid')
    cases = archived_cases(pins, archive_helpers, orig)
    legacy = {}
    for name, path, digest in archive_helpers['LEGACY_MODES']:
        contents = json.loads(pins.raw(path, digest))
        for frame in contents['frames']:
            pins.raw(frame['image_path'], frame['image_sha256'])
            pins.raw(frame['arrays_path'], frame['arrays_sha256'])
        for detail in (None, 'brief', 'full'):
            legacy[f'{name}_{detail}'] = [contents, detail]
    legacy['plain_error_surface'] = [{'status': 'failed', 'error': {'code': 'offline_control'}}, 'brief']
    payload = encoded({'cases': cases, 'legacy': legacy})
    results = []
    for path in (a_path, b_path):
        ran = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--child', str(path)],
                             input=payload, capture_output=True, timeout=120)
        if ran.returncode:
            raise RuntimeError(ran.stderr.decode(errors='replace'))
        results.append(json.loads(ran.stdout))
    compare(*results, archive_helpers)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump({'passed': True, 'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
                   'fixture_semantics': 'Archived PNG/NPZ fed to installed actual render-scope feedback.', 'A': results[0],
                   'B': results[1], 'source_pins': [pins.pins[k] for k in sorted(pins.pins)]},
                  stream, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)
        stream.write('\n')
    print('Passed installed A/B archived coverage, actual frames, compact delivery and boundary controls.', sha(output.read_bytes()))


if __name__ == '__main__':
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--candidate', type=Path, default=NS / 'install/PRODUCT_RUN_BINDING.json')
    args.add_argument('--output', type=Path, default=HERE / 'OFFLINE_CONTROLS.json')
    args.add_argument('--child', type=Path)
    cfg = args.parse_args()
    if cfg.child:
        child(read(cfg.child))
    else:
        parent(cfg.candidate, cfg.output)
