"""Exact coordinate-bound and source-row checks with zero product imports."""

from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = HERE.parent
VISIBILITY = NS / 'reference/next_region_preflight.py'
VISIBILITY_SHA = 'b47e43c85d13bc51510dff9cfcde384f6e7b470b7fe44f1abed4830236182569'
SOURCE = NS.parent / 'm4_global_local_qualification_001/fixture/GEOMETRY.json'
SOURCE_SHA = '34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8'


def pin(path):
    raw = Path(path).read_bytes()
    return dict(path=str(Path(path).resolve()), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def load_visibility():
    if pin(VISIBILITY)['sha256'] != VISIBILITY_SHA or pin(SOURCE)['sha256'] != SOURCE_SHA:
        raise ValueError('sealed_pre_result_source_changed')
    spec = importlib.util.spec_from_file_location('_sealed_source_region_fraction_visibility', VISIBILITY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def objects():
    recipe = json.loads((NS / 'fixture/GEOMETRY.json').read_bytes())
    return recipe, [dict(name=row['name'], vertices=[tuple(map(F, point)) for point in row['vertices_world_m']],
                        faces=[tuple(face) for face in row['triangles']]) for row in recipe['objects']]


def point_on_triangle(point, triangle, exact):
    a, b, c = triangle
    u, v, p = exact.sub(b, a), exact.sub(c, a), exact.sub(point, a)
    normal = exact.cross(u, v)
    if exact.dot(normal, p) != 0:
        return False
    uu, uv, vv, pu, pv = [exact.dot(x, y) for x, y in ((u, u), (u, v), (v, v), (p, u), (p, v))]
    gram = uu * vv - uv * uv
    s, t = (pu * vv - pv * uv) / gram, (pv * uu - pu * uv) / gram
    return s >= 0 and t >= 0 and s + t <= 1


def main():
    exact = load_visibility()
    recipe, scene = objects()
    old = json.loads(SOURCE.read_bytes())
    assert recipe['objects'][:6] == old['objects'][:6]
    assert recipe['objects'][7:9] == old['objects'][7:9]
    assert recipe['counts'] == dict(objects=11, vertices=64, triangles=62)
    assert [row['ordinal'] for row in recipe['objects']] == list(range(11))
    assert len(scene) == 11 and sum(len(o['vertices']) for o in scene) == 64 and sum(len(o['faces']) for o in scene) == 62
    for obj in scene:
        for face in obj['faces']:
            assert len(face) == len(set(face)) == 3 and all(0 <= index < len(obj['vertices']) for index in face)
            a, b, c = [obj['vertices'][index] for index in face]
            assert exact.dot(exact.cross(exact.sub(b, a), exact.sub(c, a)), exact.cross(exact.sub(b, a), exact.sub(c, a))) > 0
    source = next(obj for obj in scene if obj['name'] == 'Obj_07')
    vertices = source['vertices'][:6]
    faces = source['faces'][:4]
    assert faces == [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5)]
    normal = exact.cross(exact.sub(vertices[1], vertices[0]), exact.sub(vertices[2], vertices[0]))
    assert any(exact.dot(normal, exact.sub(point, vertices[0])) != 0 for point in vertices)
    turns = [exact.cross(exact.sub(vertices[(i+1) % 6], vertices[i]),
                         exact.sub(vertices[(i+2) % 6], vertices[(i+1) % 6]))[2] for i in range(6)]
    assert min(turns) < 0 < max(turns)
    definitions = [('selected_to_B', vertices, 'Ref_B', F(25, 16), vertices[1], (F(11, 2), F(4), F(0))),
        ('selected_to_C', vertices, 'Ref_C', F(137, 16), vertices[1], (F(15, 2), F(4), F(0))),
        ('whole_to_B', source['vertices'], 'Ref_B', F(1, 1024), source['vertices'][6], (F(6), F(4), F(0))),
        ('whole_to_C', source['vertices'], 'Ref_C', F(2305, 1024), source['vertices'][6], (F(15, 2), F(4), F(0)))]
    proofs = []
    for name, points, reference_name, wanted, p, q in definitions:
        reference = next(obj for obj in scene if obj['name'] == reference_name)
        dx = max(F(0), min(point[0] for point in reference['vertices']) - max(point[0] for point in points))
        z = min(point[2] for point in points)
        lower = dx * dx + z * z
        assert lower == wanted == exact.dot(exact.sub(p, q), exact.sub(p, q))
        source_rows = [index for index, face in enumerate(source['faces'])
                       if point_on_triangle(p, [source['vertices'][index] for index in face], exact)]
        reference_rows = [index for index, face in enumerate(reference['faces'])
                          if point_on_triangle(q, [reference['vertices'][index] for index in face], exact)]
        assert source_rows and reference_rows
        assert name.startswith('whole') or any(index < 4 for index in source_rows)
        proofs.append(dict(name=name, distance_squared_m2=str(wanted), attained_source_point=list(map(str, p)),
            attained_reference_point=list(map(str, q)), source_rows_containing_witness=source_rows,
            reference_rows_containing_witness=reference_rows,
            proof='All triangle interiors inherit x/z coordinate bounds by convexity. Explicit source and reference points attain the bound.'))
    moved = [tuple(value + (F(1, 4) if axis == 0 else 0) for axis, value in enumerate(point)) for point in vertices]
    assert (F(11, 2) - max(p[0] for p in moved)) ** 2 + min(p[2] for p in moved) ** 2 == F(5, 4)
    visibility = [dict(source_triangle_index=index, **exact.triangle_visible(scene, 'Obj_07', index, (F(4), F(-4), F(3))))
                  for index in range(4)]
    assert all(row['visible'] for row in visibility)
    result = dict(schema='m4-m5-source-region-static-preflight-v1', passed=True, geometry=pin(NS / 'fixture/GEOMETRY.json'),
        inputs=[pin(SOURCE), pin(VISIBILITY), pin(NS / 'reference/NEXT_REGION_PREFLIGHT.json'), pin(__file__)],
        counts=recipe['counts'], preserved_original_objects=8, changed_original_objects=['Obj_07'],
        selected_source_triangle_indices=list(range(4)), selected_source_vertex_indices=list(range(6)),
        whole_source_triangle_indices=list(range(6)), selected_noncoplanar=True, xy_boundary_concave=True,
        source_polygon_vertex_mapping='Native polygon rows, vertex rows, and evaluated triangle rows must be verified rowwise by the fresh asset readback.',
        coordinate_bound_proofs=proofs, moved_x_quarter_selected_to_B_squared_m2='5/4',
        SCENE_direction=[4, -4, 3], source_triangle_geometric_visibility=visibility,
        actual_camera_pixels='pending_saved_actual_frame_review',
        authorship='Fixture and oracle authored by the same delegated agent. Oracle imports no product code. Root provides a separate source review.',
        new_live_Blender=0, new_raster=0, new_model=0, product_imports=0)
    path = HERE / 'STATIC_PREFLIGHT.json'
    path.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(passed=True, report=pin(path))))


if __name__ == '__main__':
    main()
