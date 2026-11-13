"""Check the frozen whole-scene cameras and stored raster buffers offline."""

import importlib.util
import inspect
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
spec = importlib.util.spec_from_file_location('_active_raster_input_adapter', HERE / 'adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
np, Image = adapter.np, adapter.Image
from human_eye_plugin.attention_raster import _clip_polygon


def run():
    started = time.perf_counter_ns()
    checks = []

    def check(name, passed):
        checks.append({'check': name, 'passed': bool(passed)})

    scene_path = BATCH / 'inputs/SCENE_GEOMETRY_RATIONAL.json'
    direction_path = BATCH / 'inputs/DIRECTIONS.json'
    cameras_path = BATCH / 'inputs/CAMERAS.json'
    scene, directions, cameras = (adapter.read(path) for path in (scene_path, direction_path, cameras_path))
    check('public_geometry_matches_frozen_camera', adapter.digest(scene_path.read_bytes()) == cameras['source_geometry_file_sha256'])
    check('six_direction_binding', [row['name'] for row in cameras['views']] == list(adapter.ORDER)
          and all(row['direction_rational'] == directions['directions'][row['name']] for row in cameras['views']))
    meshes = adapter.load_meshes(scene)
    vertices = np.concatenate([mesh.vertices for mesh in meshes])
    receipts = adapter.read(HERE / 'RASTER_RESULTS.json')
    for pose, receipt in zip(cameras['views'], receipts['views']):
        view, projection = np.asarray(pose['view_matrix']), np.asarray(pose['projection_matrix'])
        camera = vertices @ view[:3, :3].T + view[:3, 3]
        ndc = camera @ projection[:3, :3].T + projection[:3, 3]
        check(pose['name'] + ':all_geometry_in_closed_frustum', np.all((ndc >= -1) & (ndc <= 1)))
        check(pose['name'] + ':common_center', pose['target'] == cameras['common_center_world_m'])
        check(pose['name'] + ':near_far_cover_all_vertices', np.all(-camera[:, 2] >= pose['near'])
              and np.all(-camera[:, 2] <= pose['far']))
        png, arrays = HERE / receipt['PNG'], HERE / receipt['owner_depth_RGB_arrays']
        check(pose['name'] + ':PNG_original_hash', adapter.digest(png.read_bytes()) == receipt['PNG_sha256'])
        check(pose['name'] + ':array_original_hash', adapter.digest(arrays.read_bytes()) == receipt['arrays_sha256'])
        with np.load(arrays, allow_pickle=False) as buffers:
            color, depth, owners = (buffers[name] for name in ('color', 'depth', 'owners'))
            check(pose['name'] + ':array_types', color.dtype == np.uint8 and depth.dtype == np.float64 and owners.dtype == np.int32)
            check(pose['name'] + ':512_shapes', color.shape == (512, 512, 3) and depth.shape == owners.shape == (512, 512))
            check(pose['name'] + ':owner_indices', np.all((owners >= -1) & (owners < len(meshes))))
            check(pose['name'] + ':owner_depth_correspondence', np.array_equal(owners >= 0, np.isfinite(depth)) and np.all(depth[owners >= 0] > 0))
            check(pose['name'] + ':PNG_is_saved_RGB_buffer', np.array_equal(np.asarray(Image.open(png)), color))
    clipping = []
    for axis in range(3):
        for bound in (-1., 1.):
            triangle = np.zeros((3, 4), dtype=np.float64)
            other_axes = [value for value in range(3) if value != axis]
            triangle[:, axis] = bound
            triangle[:, other_axes] = [[-.5, -.5], [.5, -.5], [0., .5]]
            triangle[:, 3] = 1.
            inside = _clip_polygon(triangle)
            check('closed_clip_boundary:' + str(axis) + ':' + str(bound), np.array_equal(inside, triangle))
            outside = triangle.copy()
            outside[:, axis] = np.nextafter(bound, -np.inf if bound < 0 else np.inf)
            rejected = _clip_polygon(outside)
            check('one_ulp_outside_clip:' + str(axis) + ':' + str(bound), len(rejected) == 0)
            clipping.append({'axis': axis, 'bound': bound, 'boundary_retained': bool(np.array_equal(inside, triangle)),
                             'one_ulp_outside_rejected': len(rejected) == 0})
    return {'schema': 'active-coverage-raster-input-check-v1', 'passed': all(row['passed'] for row in checks),
        'checks': checks, 'check_count': len(checks), 'clip_boundary_controls': clipping,
        'clipping_source_path': inspect.getsourcefile(_clip_polygon),
        'clipping_source_sha256': adapter.digest(Path(inspect.getsourcefile(_clip_polygon)).read_bytes()),
        'public_geometry_sha256': adapter.digest(scene_path.read_bytes()),
        'public_directions_sha256': adapter.digest(direction_path.read_bytes()),
        'frozen_cameras_sha256': adapter.digest(cameras_path.read_bytes()),
        'elapsed_ns': time.perf_counter_ns() - started, 'raster_calls': 0,
        'geometry_tolerance_added': 0, 'model_Blender_API_calls': 0,
        'scope': 'Public input binding, existing stored raster buffers and direct NDC clip controls.'}


if __name__ == '__main__':
    result = run()
    adapter.save(HERE / 'INPUT_CHECK.json', result)
    print(json.dumps({'passed': result['passed'], 'checks': result['check_count'], 'raster_calls': 0}))
    raise SystemExit(0 if result['passed'] else 1)
