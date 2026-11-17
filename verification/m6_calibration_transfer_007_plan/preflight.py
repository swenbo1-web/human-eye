"""Select one fixed existing external-asset pair before any new model call."""
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
DATA = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_data_001')


def main():
    index = json.loads((DATA / 'DATASET_INDEX.json').read_bytes())
    pair = next(row for row in index['pairs'] if row['split'] == 'validation' and row['candidate_valid'] and row['usable_for_training'])
    assert pair['id'] == 'cat_reference_roi0_c0_r0_a0_pair'
    observations = {row['id']: row for row in index['observations']}
    normal = observations[pair['normal_observation_id']]
    damaged = observations[pair['damaged_observation_id']]
    with np.load(DATA / normal['input']['base_mesh']) as packet:
        clean, faces = packet['vertices'].copy(), packet['faces'].copy()
    region = np.load(DATA / pair['region_mapping']).astype(np.int64)
    with np.load(DATA / normal['input']['current_local_positions']) as packet:
        clean[region] = packet['positions']
    current = clean.copy()
    with np.load(DATA / damaged['input']['current_local_positions']) as packet:
        current[region] = packet['positions']
    local_faces = faces[np.isin(faces, region).all(axis=1)]
    all_edges = np.sort(np.concatenate([local_faces[:, [0, 1]], local_faces[:, [1, 2]], local_faces[:, [2, 0]]]), axis=1)
    edges, counts = np.unique(all_edges, axis=0, return_counts=True)
    boundary = np.unique(edges[counts == 1])
    ring = np.setdiff1d(np.unique(edges[np.isin(edges, boundary).any(axis=1)]), boundary)
    editable = np.setdiff1d(region, np.union1d(boundary, ring))
    displacement = current - clean
    distances = np.linalg.norm(displacement, axis=1)
    support = np.flatnonzero(distances > 0)
    assert np.isin(support, editable).all()
    ell = float(np.linalg.norm(current[edges[:, 0]] - current[edges[:, 1]], axis=1).mean())
    quantization = np.linalg.norm(current - np.round(current * 1e6) / 1e6, axis=1)
    selected = editable[quantization[editable] > 1e-9]
    sources = ('DATASET_INDEX.json', 'data_io.py', normal['input']['base_mesh'], pair['region_mapping'],
               normal['input']['current_local_positions'], damaged['input']['current_local_positions'], 'private/source_notes/cat__README.txt')
    result = dict(
        selection_rule='First validation && candidate_valid && usable_for_training in existing DATASET_INDEX pairs order',
        pair_id=pair['id'], normal_observation_id=normal['id'], current_observation_id=damaged['id'],
        source_id=pair['source_id'], lineage_group=pair['group'], prior_usage='Previously used validation material; external to Yanyite lineage',
        files=[dict(path=name, bytes=(DATA / name).stat().st_size, sha256=hashlib.sha256((DATA / name).read_bytes()).hexdigest()) for name in sources],
        points=len(clean), triangles=len(faces), region_points=len(region), local_triangles=len(local_faces), local_edges=len(edges),
        B0=len(boundary), B1=len(ring), editable_points=len(editable), support_points=len(support),
        normal_editable_points=len(editable) - len(support), normal_region_points=len(region) - len(support),
        I_array_sha256=hashlib.sha256(editable.tobytes()).hexdigest(),
        current_vertices_sha256=hashlib.sha256(current.tobytes()).hexdigest(),
        unit='source_native_physical_length_unlabelled', ell_current=ell,
        maximum_damage=float(distances.max()), support_RMSE=float(np.sqrt(np.mean(distances[support] ** 2))),
        observation_RMSE=float(np.sqrt(np.mean(distances[region] ** 2))),
        operation_and_cumulative_budget=ell,
        normal_editable_RMS_limit_over_ell=0.014506080599458708,
        normal_editable_RMS_limit=ell * 0.014506080599458708,
        decimal_lattice_diagnostic=dict(step=1e-6, threshold=1e-9, TP=len(np.intersect1d(selected, support)),
            FP=len(np.setdiff1d(selected, support)), scope='Pre-existing observable clue. Audit actual model use; no perception attribution.'),
        current_geometry_camera_rule='Current F center, scale1.5*bbox diagonal, mean normal plus tangent-PCA plus/minus45 degrees',
        actual_saved_QA='pending', actual_reference_PNGs='pending',
        new_Pro=0, new_Blender=0, new_training=0,
    )
    (HERE / 'PREFLIGHT.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({key: value for key, value in result.items() if key != 'files'}))


if __name__ == '__main__':
    main()
