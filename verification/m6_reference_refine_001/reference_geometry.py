"""Fixed-axis front projection and silhouette sections for reference matching."""

import numpy as np


def axis_frame(elbow, wrist):
    elbow = np.asarray(elbow, dtype=np.float64)
    direction = np.asarray(wrist, dtype=np.float64) - elbow
    length = float(np.linalg.norm(direction))
    if length <= 0 or not np.isfinite(length):
        raise ValueError("distinct_finite_elbow_and_wrist_required")
    tangent = direction / length
    outward = np.array([tangent[1], -tangent[0]])
    if outward[0] <= 0:
        raise ValueError("front_axis_requires_wrist_below_elbow_and_positive_screen_right")
    return elbow, tangent, outward, length


def normalized_coordinates(points, elbow, wrist):
    origin, tangent, outward, length = axis_frame(elbow, wrist)
    delta = np.asarray(points, dtype=np.float64) - origin
    return np.column_stack((delta @ tangent, delta @ outward)) / length


def align_similarity(points, source_elbow, source_wrist, target_elbow, target_wrist):
    coordinates = normalized_coordinates(points, source_elbow, source_wrist)
    origin, tangent, outward, length = axis_frame(target_elbow, target_wrist)
    return origin + length * (coordinates[:, :1] * tangent + coordinates[:, 1:] * outward)


def front_pixels(vertices, width=640, height=640, scale=.285, center_y=.155, center_z=.565):
    """Orthographic +X camera, screen right=+Y and screen down=-Z."""
    vertices = np.asarray(vertices, dtype=np.float64)
    pixels_per_unit = max(width, height) / scale
    return np.column_stack((width/2 + (vertices[:, 1]-center_y)*pixels_per_unit,
        height/2 - (vertices[:, 2]-center_z)*pixels_per_unit))


def front_pixel_to_world_yz(points, width=640, height=640, scale=.285, center_y=.155, center_z=.565):
    points = np.asarray(points, dtype=np.float64)
    units_per_pixel = scale / max(width, height)
    return np.column_stack((center_y + (points[:, 0]-width/2)*units_per_pixel,
        center_z - (points[:, 1]-height/2)*units_per_pixel))


def _containing_interval(intervals):
    """Merge projected occupied intervals and select the component at the axis."""
    ordered = sorted(intervals, key=lambda row: row[0])
    merged = []
    for lower, upper, face in ordered:
        if merged and lower <= merged[-1][1] + 1e-11:
            if upper > merged[-1][1]:
                merged[-1][1], merged[-1][3] = upper, face
        else:
            merged.append([lower, upper, face, face])
    at_axis = [row for row in merged if row[0]-1e-11 <= 0 <= row[1]+1e-11]
    if len(at_axis) != 1:
        raise ValueError("axis_not_inside_one_projected_forearm_component")
    return at_axis[0], merged


def measure_projected_sections(points, faces, elbow, wrist, stations, face_ids=None):
    """Intersect the actual projected triangles with each fixed EW station.

    The occupied projected interval containing the EW axis is the forearm
    section. Other disconnected projected components are recorded separately.
    Distances are normalized by the fixed initial elbow-wrist length.
    """
    coordinates = normalized_coordinates(points, elbow, wrist)
    faces = np.asarray(faces, dtype=np.int64)
    selected = np.arange(len(faces)) if face_ids is None else np.asarray(face_ids, dtype=np.int64)
    triangles = coordinates[faces[selected]]
    records = []
    for station in np.asarray(stations, dtype=np.float64):
        active = (triangles[:, :, 0].min(axis=1) <= station) & (triangles[:, :, 0].max(axis=1) >= station)
        triangle_rows = selected[active]
        cut = triangles[active]
        intersections = np.full((len(cut), 6), np.nan)
        for edge, (first, second) in enumerate(((0, 1), (1, 2), (2, 0))):
            start, end = cut[:, first], cut[:, second]
            denominator = end[:, 0]-start[:, 0]
            crossing = (denominator != 0) & (np.minimum(start[:, 0], end[:, 0]) <= station) & (np.maximum(start[:, 0], end[:, 0]) >= station)
            fraction = np.divide(station-start[:, 0], denominator, out=np.zeros(len(cut)), where=denominator != 0)
            intersections[crossing, edge*2] = (start[:, 1]+fraction*(end[:, 1]-start[:, 1]))[crossing]
            along = (denominator == 0) & (start[:, 0] == station)
            intersections[along, edge*2] = start[along, 1]
            intersections[along, edge*2+1] = end[along, 1]
        valid = np.isfinite(intersections).any(axis=1)
        intersections, triangle_rows = intersections[valid], triangle_rows[valid]
        lower = np.nanmin(intersections, axis=1)
        upper = np.nanmax(intersections, axis=1)
        chosen, components = _containing_interval([(float(a), float(b), int(face)) for a, b, face in zip(lower, upper, triangle_rows)])
        records.append(dict(t=float(station), inner=chosen[0], outer=chosen[1], width=chosen[1]-chosen[0],
            inner_source_face=chosen[2], outer_source_face=chosen[3], component_contains_axis=True,
            projected_components=[row[:2] for row in components], crossed_triangles=len(cut)))
    return records


def measure_mesh_sections(vertices, faces, elbow_world_yz, wrist_world_yz, stations, face_ids=None):
    vertices = np.asarray(vertices, dtype=np.float64)
    points = np.column_stack((vertices[:, 1], -vertices[:, 2]))
    elbow = np.asarray(elbow_world_yz, dtype=np.float64) * [1., -1.]
    wrist = np.asarray(wrist_world_yz, dtype=np.float64) * [1., -1.]
    return measure_projected_sections(points, faces, elbow, wrist, stations, face_ids)


def measure_polyline_sections(inner, outer, elbow, wrist, stations):
    """Intersect explicit foreground contour polylines with station lines."""
    records = []
    for station in np.asarray(stations, dtype=np.float64):
        values = {}
        for name, polyline in (("inner", inner), ("outer", outer)):
            coordinates = normalized_coordinates(polyline, elbow, wrist)
            first, second = coordinates[:-1], coordinates[1:]
            crossing = (np.minimum(first[:, 0], second[:, 0]) <= station) & (np.maximum(first[:, 0], second[:, 0]) > station)
            denominator = second[:, 0]-first[:, 0]
            fractions = np.divide(station-first[:, 0], denominator, out=np.zeros(len(first)), where=denominator != 0)
            intersections = (first[:, 1]+fractions*(second[:, 1]-first[:, 1]))[crossing]
            if len(intersections) != 1:
                raise ValueError("one_contour_intersection_per_station_required_"+name)
            values[name] = float(intersections[0])
        records.append(dict(t=float(station), **values, width=values["outer"]-values["inner"]))
    return records
