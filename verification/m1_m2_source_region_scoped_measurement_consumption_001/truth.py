"""Independently derive exact closed-box selection and nearest surface witnesses."""

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from math import isfinite

ORIGINAL = Path('D:/he_m4_yanyite_opposite_direction_product_native_001/slots/P1')
RUN = Path('D:/he_m1_m2_source_region_scoped_measurement_consumption_001')
ASSET = ORIGINAL / 'native/input.blend'
TERMINAL = ORIGINAL / 'TERMINAL_SOURCE.json'
ASSET_SHA = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
TERMINAL_SHA = 'dd47f22335c8f0fcd3e6e0aa764d5d174be89b49d9e488867813135bb64fd3e6'
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
REFERENCE = 'Cube'
THRESHOLD = 0.300
BOXES = {
    'high': {'min': [-0.030, -0.055, 0.810], 'max': [0.030, 0.055, 0.855]},
    'low': {'min': [-0.050, 0.035, 0.530], 'max': [0.050, 0.140, 0.594]},
}
EXPECTED = {
    'high': (262, 173, 24722, 0.14501953294680436, [49114, 49115, 49125]),
    'low': (174, 128, 23463, 0.40625000327621974, [46767, 46776, 46777]),
}


def pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def exact_points(points):
    return [tuple(Fraction(v) for v in point) for point in points]


def arrays(row):
    ev = row['evaluated']
    world = ev['vertices_world_m']
    transform = row['matrix_world']
    projected = [[sum(c * x for c, x in zip(axis[:3], point, strict=True)) + axis[3]
                  for axis in transform[:3]] for point in ev['vertices']]
    assert all(isfinite(v) for p in projected for v in p)
    assert projected == world  # Independently reconstructed binary64 world frame.
    faces = ev['triangles']
    assert all(len(face) == 3 and all(type(i) is int and 0 <= i < len(world) for i in face)
               for face in faces)
    return exact_points(world), faces


def contains_xy(point, triangle):
    def area(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    sense = area(*triangle)
    return sense != 0 and all(sense * area(a, b, point) >= 0
                              for a, b in zip(triangle, triangle[1:]+triangle[:1]))


def infer(label, box, target, cube):
    vertices, faces = target
    ref_vertices, ref_faces = cube
    lower, upper = (tuple(map(Fraction, box[k])) for k in ('min','max'))
    inside = [all(a <= x <= b for a, x, b in zip(lower, p, upper, strict=True)) for p in vertices]
    rows = [i for i, triangle in enumerate(faces) if all(inside[v] for v in triangle)]
    selected_vertices = {v for i in rows for v in faces[i]}
    max_z = max(vertices[i][2] for i in selected_vertices)
    max_vertices = [i for i in selected_vertices if vertices[i][2] == max_z]
    assert len(max_vertices) == 1
    vertex = max_vertices[0]
    point = vertices[vertex]
    reference_point = point[:2] + (Fraction(1),)
    distance = reference_point[2] - point[2]
    target_witness = [i for i in rows if vertex in faces[i]]
    reference_witness = []
    per_side = {}
    for i, face in enumerate(ref_faces):
        points = [ref_vertices[v] for v in face]
        planes = [(axis, coord) for axis in range(3) for coord in (Fraction(-1), Fraction(1))
                  if all(p[axis] == coord for p in points)]
        assert len(planes) == 1
        axis, coord = planes[0]
        plane_key = (axis, str(coord))
        lower_bound = max(Fraction(0), lower[axis] - coord, coord - upper[axis])
        if plane_key == (2, '1'):
            lower_bound = 1 - max_z
            if contains_xy(reference_point, points):
                reference_witness.append(i)
        else:
            assert lower_bound > distance
        per_side[f'{axis}:{coord}'] = str(lower_bound)
    assert reference_witness == [0]
    assert (len(rows), len(selected_vertices), vertex, float(distance), target_witness) == EXPECTED[label]
    return {
        'box_m': box, 'triangle_count': len(rows), 'triangle_ids': rows,
        'associated_vertex_count': len(selected_vertices), 'max_z_source_vertex': vertex,
        'distance_m': float(distance), 'distance_exact_m': str(distance), 'direction_world': [0, 0, 1],
        'source_point_world_m': list(map(float, point)), 'reference_point_world_m': list(map(float, reference_point)),
        'source_point_exact_m': list(map(str, point)), 'reference_point_exact_m': list(map(str, reference_point)),
        'source_witness_triangle_ids': target_witness, 'cube_witness_triangle_ids': reference_witness,
        'cube_surface_plane_lower_bounds_m': per_side,
        'threshold_met': float(distance) >= THRESHOLD,
    }


def main():
    source_pins = [pin(ASSET), pin(TERMINAL)]
    assert [row['sha256'] for row in source_pins] == [ASSET_SHA, TERMINAL_SHA]
    source = json.loads(TERMINAL.read_bytes())
    assert source['source']['asset_sha256'] == ASSET_SHA and source['source']['scale_length'] == 1
    assert source['source']['frame'] == 1 and source['source']['subframe'] == 0.0
    objects = {row['name']: row for row in source['objects']}
    assert set(objects) == {TARGET, REFERENCE}
    assert objects[TARGET]['visible_get'] is True and objects[REFERENCE]['visible_get'] is False
    target, cube = arrays(objects[TARGET]), arrays(objects[REFERENCE])
    assert (len(target[0]), len(target[1]), len(cube[0]), len(cube[1])) == (27304, 53264, 8, 12)
    regions = {label: infer(label, box, target, cube) for label, box in BOXES.items()}
    assert set(regions['high']['triangle_ids']).isdisjoint(regions['low']['triangle_ids'])
    assert regions['high']['distance_m'] < THRESHOLD <= regions['low']['distance_m']
    output = {
        'passed': True, 'terminal_path': str(TERMINAL), 'terminal_sha256': TERMINAL_SHA,
        'asset_path': str(ASSET), 'asset_sha256': ASSET_SHA, 'source_pins': source_pins,
        'target': TARGET, 'reference': REFERENCE, 'threshold_m': THRESHOLD, 'nearer': 'high', 'regions': regions,
        'source_index_domain': source['source']['source_index_domain'],
        'checked_asset_geometry': {'objects': 2, 'vertices': 27312, 'triangles': 53276},
        'scope': 'independent exact surface proof with all three current world vertices in each closed box',
    }
    path = RUN / 'preflight/TRUTH.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write((json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode())
    print({label: {k: region[k] for k in ('triangle_count', 'associated_vertex_count', 'distance_m',
                                          'source_witness_triangle_ids', 'cube_witness_triangle_ids')}
           for label, region in regions.items()})


if __name__ == '__main__':
    main()
