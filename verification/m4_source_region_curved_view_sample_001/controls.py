"""Check sparse votes against the corresponding cells of the real raster."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


RUN = Path('D:/he_m4_source_region_curved_view_sample_001')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def check(binding_path, output):
    binding = json.loads(binding_path.read_bytes())
    require(len(binding['source_manifest']) == 143 and output.resolve().is_relative_to(RUN.resolve()),
            'fixed_isolated_install_and_output_required')
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    import numpy as np
    from human_eye_plugin import attention_raster as raster
    from human_eye_plugin.active_observation_images import _meshes_from_objects

    path = Path(raster.__file__).resolve(strict=True)
    source_root = Path(binding['install_root']).resolve(strict=True)
    relative = path.relative_to(source_root).as_posix()
    expected, = [row['sha256'] for row in binding['source_manifest'] if row['path'] == relative]
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'installed_sparse_control_source_changed')

    size = 64
    matrix = np.eye(4)
    def pose(name, *, shift=0):
        projection = np.eye(4)
        projection[0, 3] = shift
        return {'name': name, 'size_px': [size, size], 'view_matrix': matrix.tolist(),
                'projection_matrix': projection.tolist()}

    def quad(x1, x2, z):
        return [(x1, -.95, z), (x2, -.95, z), (x2, .95, z), (x1, .95, z)]

    faces = [(0,1,2),(0,2,3)]
    def mesh(*objects):
        return _meshes_from_objects(tuple((pts, tris, ('test', i), 'test' + str(i))
                                          for i, (pts, tris) in enumerate(objects)))

    def independent_samples(meshes, poses, object_mask, indices):
        projections = {x['name']: np.array(x['projection_matrix']) for x in poses}
        labels, offset = [], 0
        for obj in meshes:
            labels.append(np.arange(offset, offset+len(obj.faces), dtype=np.int32))
            offset += len(obj.faces)
        grid = ((np.arange(8)*2 + 1) * size) // 16
        selected_global = np.asarray(indices, dtype=np.int32)
        results = {}
        for name, projection in projections.items():
            _, _, owners, triangles = raster.rasterize_attention(meshes, matrix, projection, size,
                return_owner=True, return_patch_owner=True, face_patch_ids=labels, object_mask=object_mask)
            hits = (owners == 0) & np.isin(triangles, selected_global)
            results[name] = {'sample_votes': int(np.count_nonzero(hits[np.ix_(grid, grid)])),
                             'actual_pixels': int(np.count_nonzero(hits))}
        return results

    cases = {}
    def compare(name, scene, poses, mask, indices, expected_view=None):
        full = independent_samples(scene, poses, mask, indices)
        view, votes = raster.select_sparse_attention_view(scene, poses, object_mask=mask, object_index=0,
            source_triangle_indices=indices, check_budget=lambda _: None)
        reference = {key: row['sample_votes'] for key,row in full.items()}
        wanted_votes = {'SCENE': reference['SCENE']} if reference['SCENE'] else reference
        wanted_view = 'SCENE' if reference['SCENE'] else max(reference, key=reference.get)
        require(votes == wanted_votes and view == wanted_view and (expected_view is None or view == expected_view),
                'sparse_differs_from_real_grid_owner/' + name)
        cases[name] = {'chosen_view': view, 'votes': votes, 'oracle': full}

    target = quad(-.95, .95, -.7)
    near_left = quad(-.95, 0, -.35)
    same = mesh((target+near_left, faces+[(a+4,b+4,c+4) for a,b,c in faces]))
    compare('same_object_unselected_occluders', same, [pose('SCENE')], (True,), (0,1), 'SCENE')
    require(0 < cases['same_object_unselected_occluders']['votes']['SCENE'] < 64, 'self_occluder_fixture_not_effective')

    obscured = mesh((target, faces), (quad(-.95,.95,-.35), faces))
    compare('hidden_occluder', obscured, [pose('SCENE')], (True, False), (0,1), 'SCENE')
    compare('visible_occluder', obscured, [pose('SCENE'),pose('LEFT')], (True, True), (0,1), 'SCENE')
    require(cases['hidden_occluder']['votes']['SCENE'] > 0 and
            cases['visible_occluder']['votes'] == {'SCENE': 0, 'LEFT': 0}, 'hidden_mask_control_not_effective')

    equal = mesh((target, faces), (target, faces))
    compare('exact_same_depth_original_draw_order', equal, [pose('SCENE')], (True, True), (0,1), 'SCENE')
    near_z = np.nextafter(-.7, 0.)
    parallel = mesh((target, faces), (quad(-.95,.95,near_z), faces))
    compare('adjacent_binary64_depth', parallel, [pose('SCENE')], (True, True), (0,1))

    crossing = [(-3.,-.94,-.4), (3.,-.94,-.4), (0.,.94,-1.7)]
    compare('crossing_clip_planes', mesh((crossing, [(0,1,2)])), [pose('SCENE')], (True,), (0,))
    compare('double_sided_reverse_winding', mesh((target, [(2,1,0),(3,2,0)])), [pose('SCENE')], (True,), (0,1))
    line = [(-.9,-.9,-.7), (0.,0.,-.7), (.9,.9,-.7)]
    compare('strict_projected_degeneracy', mesh((line, [(0,1,2)])), [pose('SCENE')], (True,), (0,))
    offscreen = mesh(([(x+3,y,z) for x,y,z in target],faces))
    compare('whole_common_clip_exclusion', offscreen, [pose('SCENE'),pose('LEFT')], (True,), (0,1))

    visible = mesh((target, faces))
    compare('scene_positive_short_circuits', visible, [pose('SCENE'),pose('TOP'),pose('LEFT')], (True,), (0,1))
    compare('alternative_tie_uses_registered_order', visible,
            [pose('SCENE', shift=3),pose('TOP'),pose('LEFT')], (True,), (0,1), 'TOP')
    small = [(x*2/(size-1)-1, 1-y*2/(size-1), -.4) for x,y in ((.8,.8),(2.25,.8),(.8,2.25))]
    compare('weak_true_pixel_missed_by_grid', mesh((small, [(0,1,2)])), [pose('SCENE'),pose('LEFT')], (True,), (0,), 'SCENE')
    rare = cases['weak_true_pixel_missed_by_grid']['oracle']['SCENE']
    require(rare['actual_pixels'] > 0 and rare['sample_votes'] == 0, 'weak_sample_fixture_must_distinguish_prediction')

    stopped = []
    def checkpoint(stage):
        stopped.append(stage)
        raise TimeoutError('frozen_control_deadline')
    try:
        raster.select_sparse_attention_view(visible, [pose('SCENE'),pose('LEFT')], object_mask=(True,),
            object_index=0, source_triangle_indices=(0,1), check_budget=checkpoint)
    except TimeoutError as error:
        require(str(error)=='frozen_control_deadline' and len(stopped)==1, 'sparse_deadline_control_failed')
    else:
        raise ValueError('sparse_deadline_not_checked')
    cases['real_budget_checkpoint'] = {'callback_stage': stopped[0]}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf8', newline='\n') as out:
        json.dump({'passed': True, 'cases': cases, 'product_git': binding['preparation_git'],
                   'sparse_source_sha256': expected, 'actual_Blender': 0, 'actual_models': 0}, out, indent=2)
        out.write('\n')
    print('Passed', len(cases), 'sparse and final-raster controls', flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_runtime_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--binding', type=Path, required=True)
    cli.add_argument('--output', type=Path, required=True)
    a = cli.parse_args()
    check(a.binding.resolve(strict=True), a.output)
