"""Check one preselected existing paired case without rendering or consumer calls."""
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
PAIR = AUTHOR / 'verification/m6_shape_pairs_001/private'


def main():
    clean = np.load(PAIR / 'reference_vertices.npy')
    damaged = np.load(PAIR / 'sample_05_abnormal.npy')
    faces = np.load(PAIR / 'triangles.npy')
    with np.load(AUTHOR / 'verification/m6_refine_001/private/cases/s01/initial.npz') as packet:
        region = packet['F_source_ids']
        editable = packet['I_ids']
        assert np.array_equal(faces, packet['faces'])
    with np.load(HERE.parent / '_m6ref1/batch/private/cases/s01/baseline_readback.npz') as source:
        source_rounding_error = float(np.max(np.abs(clean - source['vertices_world'])))
        assert source_rounding_error < 1e-7
    displacement = clean - damaged
    distances = np.linalg.norm(displacement, axis=1)
    support = np.flatnonzero(distances > 0)
    assert len(region) == 410 and len(editable) == 274 and len(support) == 47
    assert np.isin(support, editable).all()
    edges = np.unique(np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    incident_edges = edges[np.isin(edges, support).any(axis=1)]
    edge_lengths = np.linalg.norm(damaged[incident_edges[:, 0]] - damaged[incident_edges[:, 1]], axis=1)
    gradient = np.linalg.norm(displacement[incident_edges[:, 0]] - displacement[incident_edges[:, 1]], axis=1) / edge_lengths
    selected_faces = faces[np.isin(faces, support).any(axis=1)]
    clean_cross = np.cross(clean[selected_faces[:, 1]] - clean[selected_faces[:, 0]], clean[selected_faces[:, 2]] - clean[selected_faces[:, 0]])
    damaged_cross = np.cross(damaged[selected_faces[:, 1]] - damaged[selected_faces[:, 0]], damaged[selected_faces[:, 2]] - damaged[selected_faces[:, 0]])
    cosine = np.sum(clean_cross * damaged_cross, axis=1) / (np.linalg.norm(clean_cross, axis=1) * np.linalg.norm(damaged_cross, axis=1))
    angles = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
    result = dict(
        selected_existing_case='M6-SHAPE-PAIRS-001/sample_05',
        source_files=[dict(name=name, sha256=hashlib.sha256((PAIR / name).read_bytes()).hexdigest()) for name in ('reference_vertices.npy', 'sample_05_abnormal.npy', 'triangles.npy')],
        clean_source_world_maximum_rounding_difference_m=source_rounding_error,
        region_points=len(region), editable_points=len(editable), damaged_points=len(support),
        undamaged_editable_points=len(editable) - len(support),
        maximum_damage_m=float(distances.max()), region_RMSE_m=float(np.sqrt(np.mean(distances[region] ** 2))),
        support_RMSE_m=float(np.sqrt(np.mean(distances[support] ** 2))),
        exact_restoration_maximum_gradient=float(gradient.max()),
        exact_restoration_maximum_normal_change_deg=float(angles.max()),
        old_0_849mm_0_2gradient_5degree_styling_limits_would_reject_exact_restoration=True,
        scope='Planning-only source and solvability preflight. No new case, render, Pro consumer, Blender process, training or asset edit.',
    )
    (HERE / 'PREFLIGHT.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
