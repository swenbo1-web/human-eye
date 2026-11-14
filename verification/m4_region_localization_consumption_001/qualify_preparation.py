"""Check saved fake-consumer artifacts without another product or raster call."""

import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTERNAL = Path('D:/he_loc_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def load_frame(frame):
    assert sha(frame['PNG']) == frame['PNG_sha256']
    assert sha(frame['NPZ']) == frame['NPZ_sha256']
    with np.load(frame['NPZ'], allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    with Image.open(frame['PNG']) as image:
        assert image.size == (512, 512) and image.mode == 'RGB'
        assert image.tobytes() == arrays['color'].tobytes(order='C')
    for key, value in arrays.items():
        metadata = frame['arrays'][key]
        assert metadata['dtype'] == str(value.dtype)
        assert metadata['shape'] == list(value.shape)
        assert metadata['nbytes'] == value.nbytes
        assert metadata['sha256'] == hashlib.sha256(value.tobytes(order='C')).hexdigest()
    return arrays


def main():
    started = time.perf_counter_ns()
    launcher = module('_localization_qualify_launcher', HERE / 'launcher.py')
    plan = read(HERE / 'PLAN.json')
    current = launcher.source_file_list(plan)
    launcher.verify_frozen('PREP_FROZEN.json', current)
    local_results, saved, observations = [], {}, {}
    for group in ('N', 'P'):
        path = EXTERNAL / 'preparation' / (group + '1') / 'LOCAL_RESULT.json'
        result = read(path)
        assert result['passed'] and result['execution_sources_sha256'] == current
        assert all(result['checks']['checks'].values())
        local_results.append({'group': group, 'path': str(path), 'sha256': sha(path), 'attempts': 1})
        owner = Path(result['route']['owner_output'])
        observation = read(owner / 'OBSERVATIONS.json')
        assert observation['schema'] == 'region-localization-observations-v1'
        assert observation['replay_label'] == 'CAPTURE_REPLAY'
        assert not observation['runtime_faults']
        assert observation['audit']['forbidden_old_evidence_reads'] == 0
        assert observation['audit']['forbidden_old_writes'] == 0
        assert not observation['audit']['forbidden_product_calls']
        observations[group] = observation
        saved[group] = {'result': result, 'owner': owner}
    assert observations['N']['source_inputs'] == observations['P']['source_inputs']
    assert [frame['view_name'] for frame in observations['N']['frames']] == ['SCENE']
    assert [frame['view_name'] for frame in observations['P']['frames']] == ['SCENE', 'BACK', 'LEFT']
    native = load_frame(observations['N']['frames'][0])
    product = load_frame(observations['P']['frames'][0])
    shared = {name: np.array_equal(native[name], product[name]) for name in ('color', 'depth', 'owners')}
    assert all(shared.values())
    truth = read(HERE / 'admin/TRUTH.json')
    by_alias = {target['roi_alias']: target for target in truth['targets']}
    aliases = product['patch_roi_ids'].tolist()
    assert len(aliases) == len(set(aliases)) and set(aliases) == set(by_alias)
    face_to_patch = np.full(3337, -1, dtype=np.int32)
    for index, alias in enumerate(aliases):
        face_to_patch[by_alias[alias]['source_triangle_indices']] = index
    assert np.array_equal(face_to_patch, product['face_patch_ids'])
    assert np.array_equal(product['face_patch_offsets'], [0, 3337])
    triangles = native['triangle_ids']
    assert triangles.dtype == np.int32 and triangles.shape == (512, 512)
    assert not np.any((triangles < -1) | (triangles >= 3337))
    mapped = np.full(triangles.shape, -1, dtype=np.int32)
    occupied = triangles >= 0
    mapped[occupied] = face_to_patch[triangles[occupied]]
    assert np.array_equal(mapped, product['patch_owners'])
    owner = saved['P']['owner']
    response = read(owner / 'tool_03/RESPONSE.json')
    service = read(owner / 'product_call_01/SERVICE_RESULT.json')
    oracle = module('_localization_existing_delivery_oracle', ROOT /
                    'verification/m4_active_observation_region_anchors_001/delivery_oracle.py')
    delivery = oracle.verify_response(response, service, 'brief')
    assert delivery['passed'] and delivery['schema'] == 'active-observation-brief-v3'
    assert service['binding']['runtime_source_sha256'] == launcher.SOURCE_SHA256
    assert service['work']['capture_calls'] == 1 and service['work']['raster_attempts'] == 3
    assert len(observations['P']['replays']) == 1
    assert observations['P']['replays'][0]['actual_Blender_capture_calls'] == 0
    assert not observations['N']['replays'] and not observations['N']['active']
    for frame in observations['P']['frames'][1:]:
        load_frame(frame)
    slots = sorted((EXTERNAL / 'raster_budget').glob('attempt_*'))
    intents = [read(path / 'INTENT.json') for path in slots]
    assert len(intents) == 4
    assert [row['global_attempt'] for row in intents] == [1, 2, 3, 4]
    assert all(row['phase'] == 'preparation' for row in intents)
    assert [row['group'] for row in intents] == ['N', 'P', 'P', 'P']
    result = {'schema': 'region-localization-preparation-qualification-v1', 'passed': True,
              'local_results': local_results,
              'source_freeze_sha256': sha(HERE / 'PREP_FROZEN.json'),
              'shared_input_binding_equal': True, 'common_SCENE_arrays_equal': shared,
              'native_triangle_to_product_patch_owner_equal': True,
              'source_face_mapping_independently_bound': True,
              'current_installed_v3_delivery': delivery,
              'error_then_recovery_then_image_contracts': True,
              'actual_preparation_raster_attempts': 4, 'preparation_cap': 8,
              'current_native_images': 1, 'current_product_images': 3,
              'replay_scope': 'Current installed observation module on a recorded Blender capture. No new Blender acquisition.',
              'new_product_renderer_model_calls_in_this_saved_data_check': 0,
              'started_ns': started, 'before_publication_ns': time.perf_counter_ns()}
    with (HERE / 'PREPARATION_QUALIFICATION.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'preparation_rasters': 4,
                      'default_schema': delivery['schema'], 'new_model_sessions': 0}))


if __name__ == '__main__':
    main()
