"""Fixed static evaluated arrays for the legacy surface-relation contract."""
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
PRIOR = V / 'm3_whole_object_rounded_witness_001'
EXTERNAL = Path('D:/he_m3_whole_object_rounded_witness_compat_001/relations')
VERTICES = ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
            (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
FACES = ((0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7))
OFFSET = (0.75, 0.4375, 0.125)
SEPARATED_OFFSET = (1.25, 0.4375, 0.125)
EXPECTED_POINT = [1.0, 0.4375, 0.25]
CASES = {
    'closed': ('closed_solid_relation',),
    'closed_surface': ('closed_solid_relation', 'surface_proximity'),
    'spatial': ('spatial_relation',),
    'spatial_closed_surface': ('spatial_relation', 'closed_solid_relation', 'surface_proximity'),
    'separated': ('closed_solid_relation',),
}
LABELS = tuple(CASES)
F = run_path(str(PRIOR / 'harness/fixtures.py'))
DIRECT_PYTHON, compact, read, save, append, pin, require = (
    F[key] for key in ('DIRECT_PYTHON', 'compact', 'read', 'save', 'append', 'pin', 'require'))
digest = run_path(str(PRIOR / 'checks/fixtures.py'))['digest']


def fixture(label):
    selectors = [{'name': name} for name in ('A', 'B')]
    edges = sorted({tuple(sorted((face[i], face[(i + 1) % 3])))
                    for face in FACES for i in range(3)})
    meshes = []
    for name, translation in zip(('A', 'B'),
                                 ((0., 0., 0.), SEPARATED_OFFSET if label == 'separated' else OFFSET),
                                 strict=True):
        oid = 'blender:' + digest(['compat-static-cube', name])
        meshes.append({
            'object_id': oid, 'name': name, 'mark_label': f'#B{len(meshes) + 1:04d}',
            'color_rgb': [166, 166, 166], 'is_focal_target': False,
            'vertices': [[p + t for p, t in zip(point, translation, strict=True)] for point in VERTICES],
            'faces': [list(face) for face in FACES], 'edges': [list(edge) for edge in edges],
            'local_axes': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], 'pivot_world': list(translation),
            'axes_source': 'host', 'axes_confidence': 'explicit', 'axes_reason': 'blender_world_rotation',
        })
    instances = {row['object_id']: str(i) for i, row in enumerate(meshes, 1)}
    scene = {
        'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender', 'meshes': meshes,
        'capture_scope': 'selected_objects',
        'host_identity': {'schema_version': '1.0', 'capture_scope': 'selected_objects',
                          'document_epoch': digest('compat-closed-unit-cubes'), 'object_instances': instances},
        'task_selection': {'selectors': selectors, 'pair_reason': None, 'candidate_count': 2,
                           'bindings': [{'object_id': row['object_id'], 'name': row['name']} for row in meshes]},
    }
    scene['revision'] = 'blender:' + digest({'scene': scene, 'scale_length': 1.})
    scene['capture_state'] = {'instance_id': digest('compat-closed-unit-cubes')[:32],
                              'epoch': 1, 'revision': 1, 'selection_key': digest(['task', selectors])}
    request = {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call',
               'params': {'name': 'human_eye_scene_observe',
                          'arguments': {'include_image': False, 'response_detail': 'full',
                                        'query': {'mode': 'task', 'objects': selectors,
                                                  'requested_facts': list(CASES[label])}}}}
    return {'label': label, 'capture': scene, 'request': request,
            'capture_kind': 'fixed_synthetic_closed_shell_arrays'}
