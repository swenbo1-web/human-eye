"""Check the installed scoped projection against original and exact arithmetic inputs."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

NS = Path(__file__).resolve().parent
RUN = Path('D:/he_m1_m2_source_region_scoped_measurement_001')
ORIGINAL = Path('D:/he_m2_source_region_selective_residency_001')
MODE = 'source_region_measurement'


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def check_original(source):
    score_path = ORIGINAL / 'SCORE.json'
    score = read(score_path)
    pins, rows = [pin(score_path)], []
    for label in ('AB', 'YB'):
        current = None
        for old in score['arms'][label]['calls']:
            rx, producer = (Path(row['path']) for row in (old['transport']['rx'], old['producer']))
            packet = read(rx)['result']['result'].partition('HUMAN_EYE_BLENDER_MCP:')[2]
            envelope = json.loads(packet)['result']
            query = source.validate_scoped_measurement_arguments({
                'query': {**old['query'], 'mode': MODE}, 'include_image': False,
            })
            if envelope['capture'] is not None:
                current = envelope['capture']
            binding = current['binding']
            capture = {**current, 'work': old['expanded'] | old['connector_work']}
            measured = source.measure_selective_region(
                capture, query['region']['object'], query['reference'],
                query['region']['world_box_m'], binding['host_source_sha256'])
            earlier = read(producer)
            assert measured['facts'] == earlier['facts']
            assert measured['source_mapping'] == earlier['source_mapping']
            result = source.project_scoped_measurement(measured, query)
            assert result['source_triangle_a'] in earlier['source_mapping']['nearest_witness']['a']['source_triangle_indices']
            assert result['source_triangle_b'] in earlier['source_mapping']['nearest_witness']['b']['source_triangle_indices']
            assert set(result).isdisjoint(('binding', 'payload_sha256', 'source_mapping', 'region_ref', 'frames'))
            rows.append({'slot': label, 'request': old['index'], 'result': result, 'body_bytes': len(encode(result))})
            pins.extend((pin(rx), pin(producer)))
    return rows, pins, measured, query


def check_precision(source):
    rows = {}
    for name, left in (('rational', [(1, 1, 1)] * 3), ('contact', [(0, 0, 1)] * 3)):
        triangles = [(0, 1, 2)]
        right = [(0, 0, 0), (3, 1, 0), (0, 0, 3)]
        meshes = source._meshes_from_objects(((left, triangles, 'a', 'a'), (right, triangles, 'b', 'b')))
        result = source._measure_region_surfaces(
            *meshes, [22], [0, 1, 2], lambda _: None, {'surface_pair_count': 0}, retain_witness_triangles=True)
        fact = source._surface_proximity_fact(result['surface'])
        assert fact['status'] == 'measured'
        if name == 'rational':
            exact = result['surface']['exact_witness_triangles']
            assert exact['points_m'] == [['1', '1', '1'], ['6/5', '2/5', '1']]
            assert exact['indices'] == [0, 0]
            assert fact['value']['nearest_witness']['b'] == [1.2, 0.4, 1.0]
            rows[name] = {'fact': fact, 'exact': exact}
        else:
            assert fact['value']['distance_m'] == 0 and fact['direction_status'] == 'not_applicable'
            assert fact['value']['nearest_witness']['direction_a_to_b'] is None
            rows[name] = {'fact': fact}
    return rows


def check_rejections(source, value, query):
    controls = {}
    for name in ('wrong_scope', 'wrong_signed_zero', 'unbound_source_triangle', 'unexpected_frame'):
        changed = deepcopy(value)
        if name == 'wrong_scope':
            changed['binding']['capture_scope'] = 'complete_scene_meshes'
        elif name == 'wrong_signed_zero':
            assert changed['binding']['world_box_m']['min'][2] == 0.0
            changed['binding']['world_box_m']['min'][2] = -0.0
        elif name == 'unbound_source_triangle':
            changed['witness_provenance']['source_triangle_a'] = -1
        else:
            changed['frames'] = ['unbound']
        try:
            source.project_scoped_measurement(changed, query)
        except ValueError as error:
            controls[name] = str(error)
        else:
            raise AssertionError(name)
    assert controls == {
        'wrong_scope': 'source_region_measurement_capture_scope_mismatch',
        'wrong_signed_zero': 'source_region_measurement_capture_scope_mismatch',
        'unbound_source_triangle': 'source_region_measurement_witness_source_unavailable',
        'unexpected_frame': 'source_region_measurement_current_capture_unavailable',
    }
    return controls


def main():
    binding = read(NS / 'install/PRODUCT_RUN_BINDING.json')
    installed = Path(binding['install_root'])
    sys.path[:0] = [str(installed), binding['dependency_root']]
    from human_eye_plugin import source_region as source
    loaded = Path(source.__file__).resolve()
    expected = next(row['sha256'] for row in binding['source_manifest']
                    if row['path'] == 'human_eye_plugin/source_region.py')
    assert loaded.is_relative_to(installed.resolve()) and pin(loaded)['sha256'] == expected
    cases, pins, last, query = check_original(source)
    output = RUN / 'preflight/PRECISION_CONTROLS.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as receipt:
        receipt.write(encode({
            'passed': True, 'candidate': binding['preparation_git'], 'loaded': pin(loaded),
            'source_pins': pins, 'prior_native_packet_replays': cases, 'precision_cases': check_precision(source),
            'projection_rejections': check_rejections(source, last, query),
            'actual_blender': 0, 'actual_model': 0, 'actual_rasters': 0,
        }) + b'\n')


if __name__ == '__main__':
    main()
