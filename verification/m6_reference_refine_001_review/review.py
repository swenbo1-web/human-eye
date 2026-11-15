"""Independent projection and EW-profile measurement of both saved annotations."""
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6ref1/batch'


def read(name):
    return json.loads((BASE / name).read_bytes())


def normalize(points, elbow, wrist):
    elbow = np.array(elbow, dtype=float)
    delta = np.array(wrist, dtype=float) - elbow
    length = np.linalg.norm(delta)
    axis = delta / length
    normal = np.array([axis[1], -axis[0]])
    offsets = np.asarray(points) - elbow
    return np.column_stack([offsets @ axis, offsets @ normal]) / length


def contour(polyline, elbow, wrist, station):
    line = normalize(polyline, elbow, wrist)
    values = []
    for first, last in zip(line[:-1], line[1:]):
        if min(first[0], last[0]) <= station < max(first[0], last[0]):
            weight = (station - first[0]) / (last[0] - first[0])
            values.append(first[1] + weight * (last[1] - first[1]))
    assert len(values) == 1
    return float(values[0])


def section(pixels, faces, elbow, wrist, station):
    triangles = normalize(pixels, elbow, wrist)[faces]
    active = triangles[
        (triangles[:, :, 0].min(axis=1) <= station)
        & (triangles[:, :, 0].max(axis=1) >= station)
    ]
    intervals = []
    for triangle in active:
        cuts = []
        for first_id, last_id in ((0, 1), (1, 2), (2, 0)):
            first, last = triangle[first_id], triangle[last_id]
            if first[0] == last[0]:
                if first[0] == station:
                    cuts.extend([first[1], last[1]])
            elif min(first[0], last[0]) <= station <= max(first[0], last[0]):
                weight = (station - first[0]) / (last[0] - first[0])
                cuts.append(first[1] + weight * (last[1] - first[1]))
        if cuts:
            intervals.append((min(cuts), max(cuts)))
    intervals.sort()
    merged = []
    for lower, upper in intervals:
        if not merged or lower > merged[-1][1] + 1e-11:
            merged.append([lower, upper])
        else:
            merged[-1][1] = max(merged[-1][1], upper)
    at_axis = [interval for interval in merged if interval[0] <= 0 <= interval[1]]
    assert len(at_axis) == 1
    return at_axis[0]


def main():
    started = time.perf_counter()
    annotation = read('ANNOTATION_DRAFT.json')
    observation = read('OBSERVATION.json')
    with np.load(BASE / 'private/cases/s01/observation.npz') as data:
        vertices = data['vertices_world']
        faces = data['faces']
        pixels = data['projected_pixels']
        observed_count = len(data['F_source_ids'])
        editable_count = len(data['I_ids'])
        assert observed_count == 599 and editable_count == 0
    affine = np.asarray(annotation['source_projection']['affine_2_by_3'])
    offset = np.array(annotation['source_projection']['offset'])
    np.testing.assert_allclose(vertices @ affine.T + offset, pixels, rtol=0, atol=1e-12)
    foreground = annotation['reference_foreground']
    rows = []
    for name in ('primary', 'alternative'):
        anchors = observation[name + '_anchors']
        reference_elbow, reference_wrist = anchors['reference']['E'], anchors['reference']['W']
        model_elbow, model_wrist = anchors['model']['E'], anchors['model']['W']
        stations = []
        for index, station in enumerate(annotation['stations']):
            reference_inner = contour(foreground['inner_polyline'], reference_elbow, reference_wrist, station)
            reference_outer = contour(foreground['outer_polyline'], reference_elbow, reference_wrist, station)
            model_inner, model_outer = section(pixels, faces, model_elbow, model_wrist, station)
            calculated = dict(
                reference_inner=reference_inner, reference_outer=reference_outer,
                model_inner=float(model_inner), model_outer=float(model_outer),
                signed_outer=float(model_outer - reference_outer),
                signed_inner=float(model_inner - reference_inner),
                signed_width=float((model_outer - model_inner) - (reference_outer - reference_inner)),
            )
            claimed = observation[name + '_stations'][index]
            for key, value in calculated.items():
                assert abs(value - claimed[key]) < 1e-12, (name, key)
            calculated['centerline_residual'] = (calculated['signed_outer'] + calculated['signed_inner']) / 2
            calculated['t'] = station
            stations.append(calculated)
        rows.append(dict(
            family=name, stations=stations,
            outer_MAE=float(np.mean([abs(row['signed_outer']) for row in stations])),
        ))
    assert all(row['signed_outer'] < 0 for row in rows[0]['stations'])
    assert all(row['signed_outer'] > 0 for row in rows[1]['stations'])
    status = read('RUN_STATUS.json')
    actual_sessions = sum(run['Pro_sessions'] for run in status['consumer_runs'])
    actual_edits = sum(run['geometry_edits'] for run in status['consumer_runs'])
    assert len(status['consumer_runs']) == 4
    assert actual_sessions == actual_edits == status['actual_image_Pro_consumption'] == 0
    assert not list((BASE / 'private').rglob('CONSUMER.json'))
    result = dict(
        status='passed_observation_only', families=rows,
        source_projection_points=len(vertices), mesh_triangles=len(faces),
        independently_measured_stations=10, observation_points=observed_count,
        editable_points=editable_count, actual_Pro_calls=actual_sessions,
        actual_geometry_edits=actual_edits, new_consumer_calls=0, new_training=0,
        uncertainty_scope='manual finite sensitivity scenarios, not a statistical confidence interval',
        wall_s=time.perf_counter() - started,
    )
    (HERE / 'RESULTS.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
