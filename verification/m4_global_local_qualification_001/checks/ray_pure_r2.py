"""Analytic square-plane control for the independent inverse-camera checker."""

import copy
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frames_ray_control', HERE / 'saved_frames_r2.py')
frames = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frames)
np = frames.np


def fixture():
    rows, columns = np.indices((512, 512))
    foreground = (rows < 511) & (columns < 511)
    owners = np.where(foreground, 0, -1).astype(np.int32)
    triangles = np.where(foreground, np.where(rows + columns >= 510, 0, 1), -1).astype(np.int32)
    depth = np.where(foreground, 1., np.inf)
    light = np.asarray([.4, -.5, 1.])
    light /= np.linalg.norm(light)
    color = (np.asarray([180, 190, 205]) * (.45 + .55 * light[2])).astype(np.uint8)
    rgb = np.zeros((512, 512, 3), dtype=np.uint8)
    rgb[foreground] = color
    capture = {'meshes': [dict(vertices=[[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1]],
                                faces=[[0, 1, 2], [0, 2, 3]])]}
    frame = {'pose': dict(view_matrix=np.eye(4).tolist(), projection_matrix=np.eye(4).tolist(), near=.08, far=2.)}
    return frame, capture, dict(owners=owners, triangle_ids=triangles, depth=depth, color=rgb)


def main():
    frame, capture, arrays = fixture()
    review = frames.ray_winner_checks(frame, capture, arrays, frames.Evidence())
    results = [dict(case='analytic_square_positive', passed=True, review=review)]
    extended = copy.deepcopy(capture)
    extended['meshes'][0]['vertices'] = [[-2, -2, -1], [2, -2, -1], [2, 2, -1], [-2, 2, -1]]
    extended_review = frames.ray_winner_checks(frame, extended, arrays, frames.Evidence())
    results.append(dict(case='oversize_plane_clips_outside_pixel_centres', passed=True, review=extended_review))
    changes = [('wrong_depth', 'depth', 2.), ('wrong_source_face', 'triangle_ids', 1), ('wrong_object', 'owners', 1)]
    for name, key, value in changes:
        altered = copy.deepcopy(arrays)
        altered[key][400, 400] = value
        try:
            frames.ray_winner_checks(frame, capture, altered, frames.Evidence())
        except ValueError as error:
            results.append(dict(case=name, passed=True, rejection_reason=str(error)))
        else:
            results.append(dict(case=name, passed=False))
    report = dict(schema='m4-global-local-ray-pure-controls-v1', passed_checked_scope=all(row['passed'] for row in results),
                  cases=results, source_sha256=frames.sha(HERE / 'saved_frames_r2.py'),
                  new_operations=dict(Blender=0, MCP=0, raster=0, model=0),
                  fixture='Synthetic analytic plane arrays only, not a scene render.')
    with (HERE / 'RAY_PURE_R2.json').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(passed_checked_scope=report['passed_checked_scope'], case_count=len(results))))
    raise SystemExit(0 if report['passed_checked_scope'] else 1)


if __name__ == '__main__':
    main()
