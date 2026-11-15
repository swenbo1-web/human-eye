"""Independent saved-weight equations, full metric reconstruction and focus geometry."""

import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch.nn import functional as functional

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6tp1/batch'
torch.set_num_threads(1)


def read(name):
    return json.loads((BASE / name).read_bytes())


def geometry(vertices, faces):
    triangles = vertices[faces]
    vectors = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    areas = np.zeros(len(vertices))
    normals = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(areas, faces[:, corner], np.linalg.norm(vectors, axis=1)/6)
        np.add.at(normals, faces[:, corner], vectors)
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.where(lengths > 0, lengths, 1)[:, None]
    return areas, normals


def metrics(scores, threshold, area, truth, ids):
    order = np.lexsort((ids, -scores))
    selected = []
    used = 0.
    for index in order:
        if used + area[index] > area.sum()*.25:
            break
        used += area[index]
        selected.append(index)
    mask = np.zeros(len(ids), dtype=bool)
    mask[selected] = True
    predicted = scores > threshold
    positive_area = area[truth].sum()
    answer = dict(area_budget_recall=float(area[mask & truth].sum()/positive_area) if positive_area else None,
                  attention_hit=bool((mask & truth).any()), anomaly_any=bool(predicted.any()),
                  anomaly_area_recall=float(area[predicted & truth].sum()/positive_area) if positive_area else None)
    if truth.any() and (~truth).any():
        # Pairwise ranking handles score ties without sklearn's implementation.
        differences = scores[truth, None] - scores[~truth][None, :]
        answer['AUC'] = float(np.mean((differences > 0) + .5*(differences == 0)))
        sorted_truth = truth[order]
        group_ends = np.r_[np.flatnonzero(np.diff(scores[order]) != 0), len(order)-1]
        positives = np.cumsum(sorted_truth)[group_ends]
        precision = positives / (group_ends+1)
        answer['AP'] = float(np.sum(np.diff(np.r_[0, positives])*precision)/truth.sum())
    return answer


def saved_forward(state, features):
    x = torch.from_numpy(features.astype(np.float32))
    x = (x-state['feature_mean'])/state['feature_divisor']
    for prefix in ('encoder.0', 'encoder.2'):
        x = functional.gelu(functional.linear(x, state[prefix+'.weight'], state[prefix+'.bias']))
    x = x.flatten(1)
    x = functional.gelu(functional.linear(x, state['output.0.weight'], state['output.0.bias']))
    return torch.sigmoid(functional.linear(x, state['output.2.weight'], state['output.2.bias'])).numpy().ravel()


def main():
    started = time.perf_counter()
    cases = read('INPUT_INDEX.json')['cases']
    truth_index = {r['alias']: r for r in read('SUPERVISION_INDEX.json')['observations']}
    features = {r['alias']: r for r in read('FEATURES.json')['cases']}
    results = {}
    assertions = 0
    for version in ('v1', 'v2'):
        state = torch.load(BASE / f'private/model/{version}_final.pth', map_location='cpu', weights_only=True)['state_dict']
        evaluation = read(f'EVALUATION_{version}.json')
        saved_cases = {r['alias']: r for r in evaluation['cases']}
        thresholds = evaluation['calibration']['thresholds']
        rows = []
        forward_points = 0
        for case in cases:
            alias = case['alias']
            with np.load(BASE / features[alias]['path']) as data:
                raw = data['features']; area = data['area']; ids = data['source_ids']
                baseline = data['baseline_score']; valid = data['valid_mask']
            with torch.inference_mode():
                scores = saved_forward(state, raw)
            scores[~valid] = 0
            with np.load(BASE / saved_cases[alias]['prediction']['path']) as package:
                np.testing.assert_array_equal(scores, package['scores'])
            forward_points += len(scores)
            assertions += 1
            with np.load(BASE / truth_index[alias]['path']) as data:
                truth = data['mask'].astype(bool)
            if not case['valid_for_learning']:
                continue
            row = dict(alias=alias, split=case['split'], state=case['state'])
            for method, values in (('learned', scores), ('geometry', baseline)):
                row[method] = metrics(values, thresholds[method], area, truth, ids)
                for key, value in row[method].items():
                    claimed = saved_cases[alias][method][key]
                    if value is None:
                        assert claimed is None
                    elif isinstance(value, bool):
                        assert value == claimed
                    else:
                        assert abs(value-claimed) < 1e-12, (alias, method, key, value, claimed)
                    assertions += 1
            rows.append(row)
        validation = [r for r in rows if r['split'] == 'validation' and r['state'] == 'damaged']
        normal = [r for r in rows if r['split'] == 'validation' and r['state'] == 'normal']
        assert len(validation) == 165 and len(normal) == 8
        summary = {}
        for method in ('learned', 'geometry'):
            summary[method] = {key: float(np.mean([r[method][key] for r in validation]))
                               for key in ('AUC', 'AP', 'area_budget_recall', 'anomaly_area_recall')}
            summary[method]['normal_false_cases'] = sum(r[method]['anomaly_any'] for r in normal)
            summary[method]['zero_attention_hit_cases'] = sum(not r[method]['attention_hit'] for r in validation)
        results[version] = dict(summary=summary, cases=len(cases), forward_points=forward_points,
                                validation_dents=len(validation), validation_normal=len(normal))
    input_index = {r['alias']: r for r in cases}
    focus_results = []
    for task in read('FOCUS_TASKS.json')['cases']:
        alias = task['alias']
        with np.load(BASE / input_index[alias]['input']['path']) as data:
            vertices, faces, F = data['vertices'], data['faces'], data['F_source_ids']
        area, normals = geometry(vertices, faces)
        ids = np.asarray(task['target_ids'])
        protected = np.asarray(task['protected_ids'])
        report = read('private/focus_reports/'+task['id']+'.json')['report']
        measured = report['target']['geometry']
        weights = area[ids]
        centroid = (vertices[ids]*weights[:, None]).sum(axis=0)/weights.sum()
        mean_normal = (normals[ids]*weights[:, None]).sum(axis=0)
        mean_normal /= np.linalg.norm(mean_normal)
        for actual, expected in ((measured['centroid_native'], centroid),
                                 (measured['bbox_native']['min'], vertices[ids].min(axis=0)),
                                 (measured['bbox_native']['max'], vertices[ids].max(axis=0)),
                                 (measured['mean_normal'], mean_normal),
                                 (measured['lumped_area_native'], weights.sum())):
            np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-14)
            assertions += 1
        assert not np.intersect1d(ids, protected).size
        assert np.array_equal(np.union1d(ids, protected), F)
        assert report['entrypoint'] == 'focus'
        assertions += 3
        focus_results.append(dict(task=task['id'], alias=alias, target_points=len(ids), protected_points=len(protected)))
    result = dict(status='passed', assertions=assertions, versions=results,
                  focus_requests=len(focus_results), focus=focus_results,
                  replayed_predictions=1200, replayed_points=460800,
                  new_training=0, optimizer_steps_replayed=0, wall_s=time.perf_counter()-started)
    (HERE / 'NUMERICAL_RESULTS.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'focus'}))


if __name__ == '__main__':
    main()
