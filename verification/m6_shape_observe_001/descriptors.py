"""Two fixed observation-only summaries on the saved context graph."""

import numpy as np


class Neighborhoods:
    """Cache graph-distance balls without changing the observed context."""

    radii = (2, 4, 8)

    def __init__(self, edge_index, node_count):
        origin, neighbor = np.asarray(edge_index, dtype=np.int64)
        self.outgoing = [np.flatnonzero(origin == index) for index in range(node_count)]
        self.adjacency = [np.unique(neighbor[edges]) for edges in self.outgoing]
        self.cache = {}

    def balls(self, index):
        index = int(index)
        if index not in self.cache:
            seen, frontier, balls = {index}, {index}, []
            for radius in range(1, 9):
                next_frontier = set()
                for vertex in frontier:
                    next_frontier.update(int(value) for value in self.adjacency[vertex])
                next_frontier.difference_update(seen)
                seen.update(next_frontier)
                frontier = next_frontier
                if radius in self.radii:
                    balls.append(np.asarray(sorted(seen - {index}), dtype=np.int64))
            self.cache[index] = tuple(balls)
        return self.cache[index]


def describe(sample, indices, neighborhoods):
    """R0 uses raw saved scalar features, R1 adds the six fixed scale terms.

    Saved float32 observations are promoted to float64 for these calculations.
    No labels, source identity, reference positions or scores enter a summary.
    Invalid rows remain present and carry explicit reasons and NaN components.
    """
    indices = np.asarray(indices, dtype=np.int64)
    inputs = sample["inputs"]
    node = np.asarray(inputs["node_features"], dtype=np.float64)
    edge = np.asarray(inputs["edge_features"], dtype=np.float64)
    positions = np.asarray(inputs["positions"], dtype=np.float64)
    normals = np.asarray(inputs["normals"], dtype=np.float64)
    local = np.full((len(indices), 13), np.nan, dtype=np.float64)
    multiscale = np.full((len(indices), 19), np.nan, dtype=np.float64)
    sizes = np.zeros((len(indices), 3), dtype=np.int64)
    local_reasons, multiscale_reasons = [], []
    for row, index in enumerate(indices):
        reasons = []
        outgoing = neighborhoods.outgoing[index]
        if len(outgoing):
            values = edge[outgoing]
            local[row] = np.concatenate((node[index, :5], values.mean(axis=0), values.std(axis=0)))
        else:
            reasons.append("empty_outgoing_edges")
        if not np.isfinite(local[row]).all():
            reasons.append("nonfinite_R0")
        local_reasons.append(reasons.copy())
        curvature, variation = [], []
        for ordinal, neighbors in enumerate(neighborhoods.balls(index)):
            sizes[row, ordinal] = len(neighbors)
            if not len(neighbors):
                reasons.append("empty_ball_" + str(neighborhoods.radii[ordinal]))
                curvature.append(np.nan)
                variation.append(np.nan)
                continue
            relative = positions[neighbors] - positions[index]
            denominator = np.sum(relative * relative, dtype=np.float64)
            numerator = np.sum(relative @ normals[index], dtype=np.float64)
            if not np.isfinite(denominator) or denominator <= 0:
                reasons.append("zero_or_nonfinite_distance_denominator_" + str(neighborhoods.radii[ordinal]))
                curvature.append(np.nan)
            else:
                curvature.append(numerator / denominator)
            cosines = np.clip(normals[neighbors] @ normals[index], -1.0, 1.0)
            variation.append(np.mean(1.0 - cosines, dtype=np.float64))
        c2, c4, c8 = curvature
        v2, v4, v8 = variation
        multiscale[row] = np.concatenate((local[row], [c2, c4 - c2, c8 - c4,
                                                        v2, v4 - v2, v8 - v4]))
        if not np.isfinite(multiscale[row]).all():
            reasons.append("nonfinite_R1")
        multiscale_reasons.append(sorted(set(reasons)))
    return {
        "R0": local, "R1": multiscale,
        "R0_valid": np.isfinite(local).all(axis=1),
        "R1_valid": np.isfinite(multiscale).all(axis=1),
        "R0_invalid_reasons": local_reasons, "R1_invalid_reasons": multiscale_reasons,
        "ball_sizes": sizes,
    }
