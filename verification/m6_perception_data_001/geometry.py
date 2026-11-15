"""Source topology, area/geodesic selection and current-mesh numerical checks."""

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra


def mesh_geometry(vertices, faces, source_normals=None, face_normal_ids=None):
    count = len(vertices)
    diagonal = float(np.linalg.norm(np.ptp(vertices, axis=0)))
    length_tol = 64 * np.finfo(np.float64).eps * diagonal
    area_tol = 64 * np.finfo(np.float64).eps * diagonal**2
    cross = np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]])
    cross_length = np.linalg.norm(cross, axis=1)
    degenerate = ~np.isfinite(cross_length) | (cross_length <= area_tol)
    vertex_cross = np.zeros_like(vertices)
    vertex_area = np.zeros(count)
    for corner in range(3):
        np.add.at(vertex_cross, faces[:, corner], np.where(degenerate[:, None], 0, cross))
        np.add.at(vertex_area, faces[:, corner], np.where(degenerate, 0, cross_length / 6))
    normal_length = np.linalg.norm(vertex_cross, axis=1)
    normals = np.divide(vertex_cross, normal_length[:, None], out=np.zeros_like(vertices), where=normal_length[:, None] > area_tol)
    invalid = ~np.isfinite(vertices).all(axis=1) | ~np.isfinite(normal_length) | (normal_length <= area_tol)
    invalid[np.unique(faces[degenerate])] = True
    directed = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges, inverse, incidence = np.unique(np.sort(directed, axis=1), axis=0, return_inverse=True, return_counts=True)
    balance = np.bincount(inverse, weights=np.where(directed[:, 0] < directed[:, 1], 1, -1))
    conflict = (incidence == 2) & (balance != 0)
    edge_order = np.argsort(inverse, kind="stable")
    offsets = np.r_[0, np.cumsum(incidence)]
    ordinary = np.flatnonzero((incidence == 2) & ~conflict)
    incident_face_ids = np.tile(np.arange(len(faces)), 3)
    left = incident_face_ids[edge_order[offsets[ordinary]]]
    right = incident_face_ids[edge_order[offsets[ordinary] + 1]]
    face_graph = csr_matrix((np.ones(len(left) * 2), (np.r_[left, right], np.r_[right, left])), shape=(len(faces), len(faces)))
    patch_count, face_patch = connected_components(face_graph, directed=False)
    patches = []
    for patch in range(patch_count):
        patch_faces = np.flatnonzero(face_patch == patch)
        centroids = vertices[faces[patch_faces]].mean(axis=1)
        anchor = int(patch_faces[np.lexsort((patch_faces, -centroids[:, 2]))[0]])
        patches.append(dict(patch=patch, triangles=len(patch_faces), anchor_face=anchor,
                            anchor_centroid=vertices[faces[anchor]].mean(axis=0).tolist(),
                            anchor_winding_normal=(cross[anchor] / cross_length[anchor]).tolist() if cross_length[anchor] else None))
    bad_edges = incidence != 2
    boundary_vertices = np.unique(edges[bad_edges])
    lengths = np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1)
    valid_edges = np.isfinite(lengths) & (lengths > length_tol)
    full_edges = edges[valid_edges]
    rows = np.concatenate((full_edges[:, 0], full_edges[:, 1]))
    cols = np.concatenate((full_edges[:, 1], full_edges[:, 0]))
    values = np.tile(lengths[valid_edges], 2)
    graph = csr_matrix((values, (rows, cols)), shape=(count, count))
    _, components = connected_components(graph, directed=False)
    eligible_edges = valid_edges & ~invalid[edges].any(axis=1)
    selected_edges = edges[eligible_edges]
    eligible_graph = csr_matrix((np.tile(lengths[eligible_edges], 2),
                                 (np.r_[selected_edges[:, 0], selected_edges[:, 1]],
                                  np.r_[selected_edges[:, 1], selected_edges[:, 0]])), shape=(count, count))
    face_component = components[faces[:, 0]]
    component_stats = []
    for component in np.unique(components):
        vertex_ids = np.flatnonzero(components == component)
        face_ids = np.flatnonzero(face_component == component)
        edge_ids = components[edges[:, 0]] == component
        closed = bool(len(face_ids) and np.all(incidence[edge_ids] == 2) and not conflict[edge_ids].any())
        origin = vertices[vertex_ids].mean(axis=0)
        tri = vertices[faces[face_ids]] - origin
        contributions = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6
        volume = float(contributions.sum())
        volume_tol = float(256 * np.finfo(float).eps * max(np.abs(contributions).sum(), diagonal**3))
        reliable = closed and abs(volume) > volume_tol
        component_stats.append(dict(component=int(component), vertices=len(vertex_ids), triangles=len(face_ids),
                                    closed_consistent=closed, signed_volume=volume, signed_volume_tolerance=volume_tol,
                                    volume_outward_sign=int(np.sign(volume)) if reliable else None,
                                    boundary_edges=int(np.sum(incidence[edge_ids] == 1)),
                                    nonmanifold_edges=int(np.sum(incidence[edge_ids] > 2)),
                                    shared_edge_winding_conflicts=int(conflict[edge_ids].sum())))
    vn_stats = dict(available=False)
    if source_normals is not None and len(source_normals) and face_normal_ids is not None:
        known = (face_normal_ids >= 0) & (face_normal_ids < len(source_normals))
        ids = np.clip(face_normal_ids, 0, len(source_normals) - 1)
        corner_normal = source_normals[ids]
        norms = np.linalg.norm(corner_normal, axis=2)
        dots = np.einsum("ij,ikj->ik", cross, corner_normal)
        cosine = np.divide(dots, cross_length[:, None] * norms, out=np.zeros_like(dots),
                           where=(cross_length[:, None] * norms) > 0)
        known &= np.isfinite(cosine) & (norms > 0) & ~degenerate[:, None]
        vn_stats = dict(available=True, valid_corners=int(known.sum()),
                        positive_corners=int(((cosine > 0) & known).sum()),
                        negative_corners=int(((cosine < 0) & known).sum()),
                        minimum_cosine=float(cosine[known].min()) if known.any() else None,
                        mean_cosine=float(cosine[known].mean()) if known.any() else None)
    stats = dict(vertices=count, triangles=len(faces), eligible_vertices=int((~invalid).sum()),
                 nonfinite_vertices=int((~np.isfinite(vertices).all(axis=1)).sum()),
                 original_degenerate_faces=int(degenerate.sum()), boundary_edges=int((incidence == 1).sum()),
                 nonmanifold_edges=int((incidence > 2).sum()), shared_edge_winding_conflicts=int(conflict.sum()),
                 bbox_diagonal=diagonal, length_tolerance=length_tol, cross_norm_tolerance=area_tol,
                 components=component_stats, orientation_patches=patches, source_vn_agreement=vn_stats)
    return dict(graph=graph, eligible_graph=eligible_graph, eligible=~invalid, edges=edges,
                boundary_vertices=boundary_vertices, normals=normals, vertex_area=vertex_area,
                cross=cross, degenerate=degenerate, component=components, face_patch=face_patch, stats=stats)


def stable_farthest(ids, distances):
    finite = np.isfinite(distances[ids])
    candidates = ids[finite]
    if not len(candidates):
        return None
    return int(candidates[np.lexsort((candidates, -distances[candidates]))[0]])


def select_rois(geometry, rng, target=384):
    eligible = geometry["eligible"]
    ids = np.flatnonzero(eligible)
    if not len(ids):
        return []
    weights = geometry["vertex_area"][ids]
    first = int(rng.choice(ids, p=weights / weights.sum()))
    graph = geometry["eligible_graph"]
    results = []
    for slot in range(2):
        available = eligible.copy()
        if slot:
            available[results[0]["source_ids"]] = False
            nearest = dijkstra(graph, directed=False, indices=results[0]["source_ids"], min_only=True)
            # Prefer a disconnected uncovered component, then farthest reachable area.
            remaining = np.flatnonzero(available)
            unreachable = remaining[np.isinf(nearest[remaining])]
            if len(unreachable):
                seed = int(unreachable[0])
            else:
                seed = stable_farthest(remaining, nearest)
            if seed is None:
                break
            # Disjoint induced graph prevents geodesic routes through ROI0.
            coo = graph.tocoo()
            keep = available[coo.row] & available[coo.col]
            local_graph = csr_matrix((coo.data[keep], (coo.row[keep], coo.col[keep])), shape=graph.shape)
        else:
            seed, local_graph = first, graph
        distances = dijkstra(local_graph, directed=False, indices=seed)
        candidates = np.flatnonzero(available & np.isfinite(distances))
        order = np.lexsort((candidates, distances[candidates]))
        selected = candidates[order[:target]]
        results.append(dict(slot=slot, seed=seed, source_ids=np.sort(selected), shortfall=max(0, target - len(selected))))
    return results


def select_centers(geometry, source_ids):
    graph = geometry["graph"]
    inside = np.zeros(graph.shape[0], dtype=bool)
    inside[source_ids] = True
    edges = geometry["edges"]
    crossing = edges[inside[edges[:, 0]] != inside[edges[:, 1]]]
    boundary = np.unique(np.r_[crossing.ravel(), geometry["boundary_vertices"]])
    boundary = boundary[inside[boundary]]
    if not len(boundary):
        return dict(boundary_ids=boundary, centers=[], reason="no_boundary")
    distance = dijkstra(graph, directed=False, indices=boundary, min_only=True)
    finite = source_ids[np.isfinite(distance[source_ids])]
    maximum = float(distance[finite].max()) if len(finite) else 0
    tolerance = geometry["stats"]["length_tolerance"]
    candidates = finite[(distance[finite] >= maximum * .5) & (distance[finite] > tolerance)]
    if not len(candidates):
        return dict(boundary_ids=boundary, centers=[], reason="no_eligible_interior")
    center = stable_farthest(candidates, distance)
    centers, nearest = [], np.full(graph.shape[0], np.inf)
    for slot in range(min(4, len(candidates))):
        centers.append(dict(slot=slot, source_id=center, D=float(distance[center])))
        from_center = dijkstra(graph, directed=False, indices=center)
        nearest = np.minimum(nearest, from_center)
        candidates = candidates[candidates != center]
        if not len(candidates):
            break
        center = stable_farthest(candidates, nearest)
        if center is None or nearest[center] <= tolerance:
            break
    return dict(boundary_ids=boundary, centers=centers, reason=None)
