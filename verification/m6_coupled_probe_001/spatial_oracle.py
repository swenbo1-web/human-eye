"""Independent blocked endpoint-AABB enumeration, without product imports."""
import time

import numpy as np


def candidates(vertices, triangles, affected, deadline=None):
    started, cpu_started = time.perf_counter(), time.process_time()
    points = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(triangles, dtype=np.int64)
    selected = np.asarray(affected, dtype=np.int64)
    boxes = points[faces]
    low, high = boxes.min(axis=1), boxes.max(axis=1)
    del boxes
    active = np.zeros(len(faces), dtype=bool)
    active[selected] = True
    found = []
    domain = 0
    blocks = 0
    for row_start in range(0, len(selected), 256):
        left = selected[row_start:row_start + 256]
        for column_start in range(0, len(faces), 2048):
            if deadline is not None and time.perf_counter() > deadline:
                raise RuntimeError("independent_aabb_deadline")
            right = np.arange(column_start, min(column_start + 2048, len(faces)))
            allowed = ((~active[right])[None, :] | (left[:, None] < right[None, :])) & (left[:, None] != right[None, :])
            domain += int(allowed.sum())
            overlap = allowed.copy()
            for axis in range(3):
                overlap &= low[left, axis, None] <= high[right, axis][None, :]
                overlap &= low[right, axis][None, :] <= high[left, axis, None]
            rows, columns = np.nonzero(overlap)
            found.extend(tuple(sorted((int(left[i]), int(right[j])))) for i, j in zip(rows, columns))
            blocks += 1
    assert len(found) == len(set(found))
    return sorted(found), {"domain_pairs": domain, "candidates": len(found), "aabb_excluded": domain - len(found),
                           "blocks": blocks, "max_block_shape": [256, 2048],
                           "endpoint_comparisons_only": True, "padding": 0,
                           "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu_started}
