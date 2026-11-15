"""Freeze one shared perturbation before the two planned consumer sessions."""
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / '_m6ref3/batch'
SEED = 2026111604
HALF_WIDTH_M = 1 / 8192


def main():
    binding = json.loads((PREVIOUS / 'CASE_BINDING.json').read_bytes())
    sources = binding['source_files']
    for source in sources:
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    clean = np.load(sources[0]['path'])
    damaged = np.load(sources[1]['path'])
    faces = np.load(sources[2]['path'])
    with np.load(PREVIOUS / 'private/cases/matched/initial.npz') as packet:
        region = packet['F_source_ids']
        editable = packet['I_ids']
    support = np.flatnonzero(np.linalg.norm(damaged - clean, axis=1) > 0)
    assert len(region) == 410 and len(editable) == 274 and len(support) == 47
    noise = np.zeros_like(clean)
    noise[region] = np.random.default_rng(SEED).uniform(-HALF_WIDTH_M, HALF_WIDTH_M, size=(len(region), 3))
    normal_new, damaged_new = clean + noise, damaged + noise
    vector_difference = float(np.max(np.abs((damaged_new - normal_new) - (damaged - clean))))
    assert vector_difference < 1e-15
    geometry = []
    for name, before, after in (('normal', clean, normal_new), ('damaged', damaged, damaged_new)):
        old_triangles, new_triangles = before[faces], after[faces]
        old_cross = np.cross(old_triangles[:, 1] - old_triangles[:, 0], old_triangles[:, 2] - old_triangles[:, 0])
        new_cross = np.cross(new_triangles[:, 1] - new_triangles[:, 0], new_triangles[:, 2] - new_triangles[:, 0])
        reversed_count = int(np.count_nonzero(np.sum(old_cross * new_cross, axis=1) < 0))
        old_small = int(np.count_nonzero(np.linalg.norm(old_cross, axis=1) < 1e-14))
        new_small = int(np.count_nonzero(np.linalg.norm(new_cross, axis=1) < 1e-14))
        assert reversed_count == 0 and new_small <= old_small
        geometry.append(dict(state=name, reversed_count=reversed_count, small_cross_before=old_small, small_cross_after=new_small))
    lattice_distance = np.linalg.norm(damaged_new - np.round(damaged_new * 4096) / 4096, axis=1)
    detected = editable[lattice_distance[editable] > 1e-6]
    true_positive = len(np.intersect1d(detected, support))
    false_positive = len(np.setdiff1d(detected, support))
    assert len(detected) == 274 and true_positive == 47 and false_positive == 227
    result = dict(
        source_files=sources, seed=SEED, noise_scope='all fixed410 region points; all other points zero',
        rule='independent uniform[-1/8192,+1/8192] metres per coordinate, identical offset added to normal and damaged',
        region_points=len(region), editable_points=len(editable), damaged_points=len(support),
        noise_RMS_m=float(np.sqrt(np.mean(np.sum(noise[region] ** 2, axis=1)))),
        noise_maximum_m=float(np.linalg.norm(noise[region], axis=1).max()),
        noise_array_sha256=hashlib.sha256(noise.tobytes()).hexdigest(),
        maximum_damage_vector_change_m=vector_difference, geometry=geometry,
        frozen_detector=dict(threshold_m=1e-6, selected=len(detected), TP=true_positive, FP=false_positive,
            precision=true_positive / len(detected), original_TP=44, original_FP=0),
        actual_saved_mesh_QA='pending implementer Blender construction and fresh readback',
        new_Pro=0, new_Blender=0, new_training=0,
    )
    (HERE / 'PREFLIGHT.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    main()
