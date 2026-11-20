"""Prepare the only registered layout from the two exact historical geometry inputs."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUTPUT = Path('D:/he_m4_cross_scale_live_task_001/fixture')
INPUTS = (
    ('f32b02b5d4a32bdbe37e8e6a43e3f977c6981d31',
     'verification/m4_global_local_qualification_001/fixture/GEOMETRY.json',
     '34c4ad599c6ead7548b21300315df25808fa274dad9dccafbf3b5808fee56ad8'),
    ('1f3db153d', 'verification/m4_occluded_scene_transfer_001/inputs/SCENE_GEOMETRY_RATIONAL.json',
     'b8e9c63f636a1b1262b377163c9b1519ee9db9e7f5b39297b8ba0c1dc2e2ce74'),
)
COUNTS = {'objects': 21, 'vertices': 148, 'triangles': 184}
IDENTITY = [[int(i == j) for j in range(4)] for i in range(4)]
PRIOR_BUILDER = ROOT / 'verification/m4_global_local_qualification_001/fixture/build_asset.py'
PRIOR_BUILDER_SHA = 'be92f6a0bd11af3fe8812b643a7d0b20bdca3c0dba0d69c1addcd8eb711ade7f'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def receipt(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'sha256': sha(raw), 'bytes': len(raw)}


def load(commit, name, expected_sha):
    raw = subprocess.check_output(['git', 'show', f'{commit}:{name}'], cwd=ROOT)
    if sha(raw) != expected_sha or (ROOT / name).read_bytes() != raw:
        raise ValueError('registered_geometry_bytes_changed/' + name)
    return json.loads(raw, parse_float=F)


def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def representable(value):
    stored = struct.unpack('<f', struct.pack('<f', float(value)))[0]
    return F.from_float(stored) == value


def combine(original, rack):
    records, names = [], []
    for input_kind, meshes in (('original', original['objects']), ('rack', rack['objects'])):
        for item in meshes:
            ordinal = len(records)
            name = f'M{ordinal + 1:02d}'
            triangles = [list(face) for face in item['triangles']]
            if input_kind == 'original':
                if item['matrix_world'] != IDENTITY:
                    raise ValueError('original_recipe_matrix_changed')
                points = [tuple(map(F, point)) for point in item['vertices_world_m']]
            else:
                points = [(F(x) + 24, F(y), F(z)) for x, y, z in item['vertices']]
            mapped = {'input_kind': input_kind, 'old_name': item['name'], 'name': name,
                      'retained_source_triangle_indices': list(range(len(triangles)))}
            if input_kind == 'original' and item['name'] == 'Obj_03':
                first = len(points)
                mapped['added_screen_triangle_indices'] = [len(triangles), len(triangles) + 1]
                x0, x1, y0, y1, z = F(-67, 32), F(-49, 32), F(-15, 32), F(3, 32), F(5, 4)
                points.extend(((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)))
                triangles.extend(([first, first + 1, first + 2], [first, first + 2, first + 3]))
            if any(not representable(value) for point in points for value in point):
                raise ValueError('Blender_float32_would_change_registered_geometry/' + name)
            records.append({'name': name, 'ordinal': ordinal, 'matrix_world': IDENTITY,
                            'vertices_world_m': [list(map(str, p)) for p in points], 'triangles': triangles})
            names.append(mapped)
    counts = {'objects': len(records), 'vertices': sum(len(m['vertices_world_m']) for m in records),
              'triangles': sum(len(m['triangles']) for m in records)}
    if counts != COUNTS:
        raise ValueError('registered_assembly_counts_changed')
    return records, names


def main():
    geometry, names = combine(*(load(*item) for item in INPUTS))
    if sha(PRIOR_BUILDER.read_bytes()) != PRIOR_BUILDER_SHA:
        raise ValueError('reused_builder_changed')
    if any((HERE / name).exists() for name in ('GEOMETRY.json', 'ROLE_MAP.json', 'BUILD_PLAN.json')):
        raise FileExistsError('registered_recipe_already_prepared')
    write(HERE / 'GEOMETRY.json', {'schema': 'm4-cross-scale-live-task-geometry-v1',
          'coordinate_encoding': 'exact_rational_strings', 'unit': 'metre', 'scale_length': 1,
          'frame': 1, 'subframe': 0, 'counts': COUNTS, 'objects': geometry})
    write(HERE / 'ROLE_MAP.json', {'scope': 'scoring only', 'objects': names})
    pins = [receipt(p) for p in (HERE / 'GEOMETRY.json', HERE / 'ROLE_MAP.json', HERE / 'build_asset.py',
                                HERE / 'compose_fixture.py', PRIOR_BUILDER, *(ROOT / item[1] for item in INPUTS))]
    write(HERE / 'BUILD_PLAN.json', {'schema': 'm4-cross-scale-live-task-build-v1',
          'output_directory': str(OUTPUT.resolve()), 'counts': COUNTS,
          'geometry_path': str((HERE / 'GEOMETRY.json').resolve()), 'inputs': pins})
    print(json.dumps({'counts': COUNTS, 'geometry': pins[0], 'role_map': pins[1]}))


if __name__ == '__main__':
    main()
