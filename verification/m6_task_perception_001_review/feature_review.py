"""Reconstruct selected descriptors with independent scalar geometry equations."""

import json
from pathlib import Path
import time
import numpy as np
from review import geometry

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6tp1/batch'


def descriptor(vertices, normals, areas, neighbors, query, count, spacing):
    ids = neighbors[:count]
    offset = vertices[ids]-vertices[query]
    radius = np.linalg.norm(offset[-1])
    unit = offset/radius
    normal = normals[query]
    axis = np.eye(3)[np.argmin(np.abs(normal))]
    tangent = np.cross(normal, axis)
    tangent /= np.linalg.norm(tangent)
    bitangent = np.cross(normal, tangent)
    h = unit@normal
    x, y = unit@tangent, unit@bitangent
    weights = areas[ids]/areas[ids].sum()
    mean = np.dot(weights, h)
    dots = normals[ids]@normal
    mean_dot = np.dot(weights, dots)
    centroid = weights@unit
    covariance = sum(w*np.outer(p-centroid, p-centroid) for w, p in zip(weights, unit))
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0)
    eigenvalues /= eigenvalues.sum()
    ring = np.linalg.norm(offset, axis=1) >= .6*radius
    ring_weights = weights*ring
    ring_weights /= ring_weights.sum()
    design = np.column_stack([x*x, x*y, y*y, x, y, np.ones(count)])
    gram = sum(w*np.outer(a, a) for w, a in zip(ring_weights, design))+np.eye(6)*1e-6
    rhs = sum(w*a*z for w, a, z in zip(ring_weights, design, h))
    coefficients = np.linalg.solve(gram, rhs)
    ring_center = ring_weights@unit
    cov = sum(w*np.outer(a-ring_center, a-ring_center) for w, a in zip(ring_weights, unit))
    _, vectors = np.linalg.eigh(cov)
    plane_normal = vectors[:, 0]
    plane_normal *= 1 if plane_normal@normal >= 0 else -1
    return np.array([mean, np.sqrt(np.dot(weights, (h-mean)**2)), h.min(), h.max(),
                     *np.quantile(h, [.25, .75]), np.dot(weights, abs(h)), mean_dot,
                     np.sqrt(np.dot(weights, (dots-mean_dot)**2)), dots.min(), *eigenvalues[:2],
                     -coefficients[-1], np.sqrt(np.dot(ring_weights, (h-design@coefficients)**2)),
                     -ring_center@plane_normal, np.log(radius/spacing)])


def main():
    started = time.perf_counter()
    index = json.loads((BASE / 'INPUT_INDEX.json').read_bytes())['cases']
    # First normal and valid damaged observation per source identity, fixed original order.
    evaluation = json.loads((BASE / 'EVALUATION_v2.json').read_bytes())['cases']
    chosen = {}
    for row in evaluation:
        key = (row['source'], row['state'])
        if row['scored'] and key not in chosen:
            chosen[key] = row['alias']
    source_index = {r['alias']: r for r in index}
    queries = []
    max_error = 0.
    for alias in chosen.values():
        with np.load(BASE / source_index[alias]['input']['path']) as data:
            vertices, faces, F = data['vertices'], data['faces'], data['F_source_ids']
        areas, normals = geometry(vertices, faces)
        with np.load(BASE / f'private/features/{alias}.npz') as data:
            features = data['features']
            np.testing.assert_allclose(data['area'], areas[F], rtol=1e-13, atol=1e-16)
        with np.load(BASE / f'private/features/{alias}_context.npz') as data:
            neighbors = data['neighbor_ids']
        for local in (0, len(F)//2, len(F)-1):
            ids = neighbors[local]
            distances = np.linalg.norm(vertices-vertices[F[local]], axis=1)
            assert len(np.unique(ids)) == 1024
            assert np.all(distances[np.setdiff1d(np.arange(len(vertices)), ids)] >= distances[ids[-1]]-1e-14)
            assert np.all(np.diff(distances[ids]) >= -1e-14)
            for scale, count in enumerate((16, 48, 128, 384, 1024)):
                expected = descriptor(vertices, normals, areas, ids, F[local], count, distances[ids[15]])
                error = float(np.max(abs(expected-features[local, scale])))
                max_error = max(max_error, error)
                np.testing.assert_allclose(features[local, scale], expected, rtol=2e-5, atol=2e-6)
            queries.append(dict(alias=alias, F_index=local, source_id=int(F[local])))
    result = dict(status='passed', source_state_cases=len(chosen), queries=len(queries), scale_fits=len(queries)*5,
                  maximum_descriptor_difference=max_error, original_geometry_unchanged=True,
                  wall_s=time.perf_counter()-started, checked_queries=queries)
    (HERE / 'FEATURE_RESULTS.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'checked_queries'}))


if __name__ == '__main__':
    main()
