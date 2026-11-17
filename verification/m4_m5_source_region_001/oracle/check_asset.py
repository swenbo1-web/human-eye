"""Saved-only rowwise review of the root-owned asset construction and reload."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = HERE.parent


def main():
    pins, checks = [], []

    def file(path, digest=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        assert digest is None or digest == actual, 'input_sha256/' + str(path)
        pins.append(dict(path=str(path), sha256=actual, bytes=len(raw)))
        return raw

    def read(path, digest=None):
        return json.loads(file(path, digest))

    binding = read(NS / 'fixture/ASSET_BINDING.json')
    recipe = read(binding['geometry']['path'], binding['geometry']['sha256'])
    plan = read(binding['build_plan']['path'], binding['build_plan']['sha256'])
    file(binding['builder']['path'], binding['builder']['sha256'])
    file(binding['asset_path'], binding['asset_sha256'])
    assert binding['asset_path'] == str(Path('D:/he_m4_m5_source_region_001/fixture/main.blend'))
    assert binding['counts'] == recipe['counts'] == plan['counts'] == dict(objects=11, vertices=64, triangles=62)
    assert binding['preparation_processes'] == 1 and binding['raster_attempts'] == binding['product_imports'] == 0
    for row in binding['input_pins']:
        file(row['path'], row['sha256'])
    before = read(binding['readback_before_save']['path'], binding['readback_before_save']['sha256'])
    after = read(binding['readback_after_reload']['path'], binding['readback_after_reload']['sha256'])
    assert before == after
    assert after['unit_system'] == 'METRIC' and after['scale_length'] == 1 and after['frame'] == 1 and after['subframe'] == 0
    assert after['object_names'] == sorted(row['name'] for row in recipe['objects'])
    identity = [[float(i == j) for j in range(4)] for i in range(4)]
    for actual, expected in zip(after['objects'], recipe['objects'], strict=True):
        assert actual['name'] == expected['name'] and actual['ordinal'] == expected['ordinal']
        assert actual['type'] == 'MESH' and actual['parent'] is None and actual['modifiers'] == []
        assert actual['matrix_world'] == actual['evaluated_matrix_world'] == identity
        vertices = [[float(F(value)) for value in point] for point in expected['vertices_world_m']]
        for mode in ('native', 'evaluated'):
            data = actual[mode]
            assert data['vertices_local'] == data['vertices_world'] == vertices
            assert data['polygons'] == data['triangles'] == expected['triangles']
            assert data['triangle_polygon_indices'] == list(range(len(expected['triangles'])))
        checks.append(dict(object_name=actual['name'], source_vertex_rows=len(vertices),
                           original_polygon_rows=len(expected['triangles']), evaluated_triangle_rows=len(expected['triangles']),
                           original_evaluated_order_identity=True))
    result = dict(schema='m4-m5-source-region-saved-asset-review-v1', passed=True,
        asset_sha256=binding['asset_sha256'], counts=recipe['counts'], unit='m', world_matrices_identity=True,
        before_save_equals_fresh_reopen=True, rowwise_source_maps=checks, input_pins=pins,
        author_association='Fixture constructor and this product-independent saved review share an author. Root reviews the frozen sources separately.',
        new_live_Blender=0, new_raster=0, new_model=0)
    output = HERE / 'ASSET_REVIEW.json'
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, asset_sha256=binding['asset_sha256'], output=str(output))))


if __name__ == '__main__':
    main()
