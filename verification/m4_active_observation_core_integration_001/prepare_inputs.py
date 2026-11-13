"""Copy fixed migration inputs and source witnesses without executing algorithms."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_triangulation_invariant_discovery_001'
EXTERNAL = Path('D:/he_core_001/payload')
SCENES = ('original', 'grid4_uniform', 'grid4_permuted_alternating',
          'grid16_uniform', 'grid16_permuted_alternating')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('prepared_file_changed:' + str(path))
    else:
        path.write_bytes(data)
    return {'file': path.relative_to(HERE).as_posix(), 'bytes': len(data), 'sha256': digest(data)}


def prepare():
    sources, files = {}, {}

    def copy(source, relative):
        source = Path(source)
        data = source.read_bytes()
        sources[str(source.resolve())] = digest(data)
        row = put(HERE / relative, data)
        files[relative] = row
        return relative

    manifest = {'schema': 'active-observation-core-integration-001-inputs-v1', 'scenes': {}, 'controls': {},
                'cameras': {}, 'offline_replays': [], 'scope': 'Fixed geometry and explicitly historical frame payloads. No expected ROI or coverage answers.'}
    for key in SCENES:
        name = 'scene_' + key + '.json'
        manifest['scenes'][key] = {'file': copy(OLD / 'inputs' / name, 'inputs/' + name)}
    for key in ('rotated_grid4', 'hole_grid4'):
        name = 'control_' + key + '.json'
        manifest['controls'][key] = {'file': copy(OLD / 'inputs' / name, 'inputs/' + name)}
    manifest['cameras']['normal'] = {'file': copy(OLD / 'inputs/CAMERAS.json', 'inputs/CAMERAS.json')}
    camera_source = ROOT / 'verification/m4_active_coverage_002/inputs/CAMERAS_PIXEL_SHORTFALL.json'
    raw = camera_source.read_bytes()
    sources[str(camera_source.resolve())] = digest(raw)
    cameras = json.loads(raw)
    for pose in cameras['views']:
        if pose['name'] == 'BACK':
            pose['name'] = 'BACK64'
    if 'directions' in cameras:
        cameras['directions'] = ['BACK64' if value == 'BACK' else value for value in cameras['directions']]
    relative = 'inputs/CAMERAS_BACK64.json'
    data = (json.dumps(cameras, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8')
    files[relative] = put(HERE / relative, data)
    manifest['cameras']['back64'] = {'file': relative,
        'transformation': 'The accepted span64 control is byte-preserved in numeric fields. Only the pose/directions name BACK becomes BACK64, changing camera identity.'}
    old_correctness = OLD / 'runs/correctness/RESULTS.json'
    old_results = json.loads(old_correctness.read_bytes())
    sources[str(old_correctness.resolve())] = digest(old_correctness.read_bytes())
    expected = {'schema': 'active-observation-core-integration-001-fixed-old-selected-v1', 'scenes': {}, 'controls': {}, 'replays': {}}
    for row in old_results['rows']:
        if row['variant'] != 'candidate':
            continue
        if 'scene' in row:
            expected['scenes'][row['scene']] = row['index']
        else:
            expected['controls'][row['control']] = row['regions']
    for scene in ('grid4_permuted_alternating', 'grid16_permuted_alternating'):
        for variant in ('reference', 'candidate'):
            identifier = scene + '_' + variant
            original = OLD / 'runs' / ('observe_' + identifier) / 'RESULTS.json'
            raw = original.read_bytes()
            sources[str(original.resolve())] = digest(raw)
            record = json.loads(raw)
            replay = {'id': identifier, 'scene': scene, 'camera': 'normal',
                      'scene_identity': record['index']['scene_identity'],
                      'candidate_identity': record['index']['candidate_identity'], 'frames': []}
            for view in record['final_state']['observed_views']:
                frame = record['frames'][view]
                png = copy(frame['PNG'], 'old_frames/' + identifier + '/' + view + '.png')
                npz = copy(frame['NPZ'], 'old_frames/' + identifier + '/' + view + '.npz')
                replay['frames'].append({'view_name': view, 'image_file': png, 'image_sha256': files[png]['sha256'],
                                         'arrays_file': npz, 'arrays_sha256': files[npz]['sha256'],
                                         'image_ref': 'old-replay-' + identifier + '-' + view})
            manifest['offline_replays'].append(replay)
            expected['replays'][identifier] = {'final_state': record['final_state'], 'steps': record['steps'],
                                                'pixel_rows_by_view': {name: frame['pixel_rows'] for name, frame in record['frames'].items()}}
    manifest['baseline'] = {
        'discovery_file': copy(OLD / 'discovery.py', 'baseline/m4_triangulation_invariant_discovery_001/discovery.py'),
        'coverage_file': copy(ROOT / 'verification/m4_active_coverage_001/coverage.py', 'baseline/m4_active_coverage_001/coverage.py'),
        'scope': 'Copied immutable selected baseline source, loaded only by the benchmark setup.'}
    manifest['files'] = files
    put(HERE / 'INPUTS.json', (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8'))
    put(HERE / 'admin/OLD_SELECTED.json', (json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8'))
    provenance = {'schema': 'active-observation-core-integration-001-input-provenance-v1',
                  'original_sources_sha256': sources, 'copied_files': files,
                  'historical_frame_count': sum(len(row['frames']) for row in manifest['offline_replays']),
                  'new_algorithm_render_model_calls': 0}
    put(HERE / 'INPUT_PROVENANCE.json', (json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8'))
    return manifest


def prepare_external():
    manifest = json.loads((HERE / 'INPUTS.json').read_bytes())
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    names = list(manifest['files']) + ['INPUTS.json', 'isolated_worker.py', 'verified_bootstrap.py']
    copied = {}
    for name in names:
        source, target = HERE / name, EXTERNAL / name
        raw = source.read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != raw:
            raise ValueError('external_payload_changed:' + name)
        if not target.exists():
            shutil.copyfile(source, target)
        copied[name] = {'bytes': len(raw), 'sha256': digest(raw)}
    value = {'schema': 'active-observation-core-integration-001-external-payload-v1', 'files': copied,
             'scope': 'Geometry/cameras, historical frame bytes, benchmark-only copied source and evidence worker. Administrative expected answers stay in the repository.'}
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8')
    target = EXTERNAL / 'PAYLOAD_MANIFEST.json'
    if target.exists() and target.read_bytes() != raw:
        raise ValueError('external_manifest_changed')
    target.write_bytes(raw)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external', action='store_true')
    options = parser.parse_args()
    result = prepare_external() if options.external else prepare()
    print(json.dumps({'prepared': True, 'external': options.external,
                      'files': len(result.get('files', {})), 'candidate_calls': 0, 'new_renders': 0}))
