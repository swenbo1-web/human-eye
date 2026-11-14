"""Exact rectangular-patch discovery and finite active-observation state.

Inputs contain complete world-space mesh geometry and an explicit orthographic
camera pool. Image feedback is supplied by the companion image adapter.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time


def vector(values):
    if len(values) != 3 or any(type(value) is bool for value in values):
        raise ValueError('three_numeric_coordinates_required')
    return tuple(Fraction(value) for value in values)


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def fingerprint(value):
    raw = json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def canonical_triangle(vertices):
    return min(vertices[index:] + vertices[:index] for index in range(3))


@dataclass(frozen=True)
class Region:
    roi_id: str
    object_index: int
    object_name: str
    triangle_indices: tuple
    vertices: tuple
    normal: tuple


@dataclass(frozen=True)
class Triangle:
    object_index: int
    triangle_index: int
    vertices: tuple
    key: tuple


def geometry(scene):
    """Normalize complete meshes once and retain original object/face indices."""
    objects, triangles = [], []
    for object_index, source in enumerate(scene['objects']):
        vertices = tuple(vector(value) for value in source['vertices'])
        faces = tuple(tuple(face) for face in source['triangles'])
        for face in faces:
            if len(face) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in face):
                raise ValueError('invalid_triangle_indices')
        key = (tuple(sorted(vertices)),
               tuple(sorted(canonical_triangle(tuple(vertices[i] for i in face)) for face in faces)))
        objects.append((vertices, faces, key, str(source.get('name', ''))))
        for triangle_index, face in enumerate(faces):
            points = tuple(vertices[i] for i in face)
            triangles.append(Triangle(object_index, triangle_index, points, canonical_triangle(points)))
    triangles.sort(key=lambda triangle: triangle.key)
    identity = fingerprint(tuple(sorted(item[2] for item in objects)))
    return tuple(objects), tuple(triangles), identity


class _NotRectangle(Exception):
    """A maximal planar component falls outside the rectangular-patch domain."""


def _planar_components(vertices, faces):
    """Partition shared-edge components using exact unoriented plane keys.

    Inconsistent winding remains inside its maximal plane component. Invalid
    shared edges mark every incident component, preserving their rejection.
    """
    normals, planes = [], []
    incidence = {}
    for face_index, face in enumerate(faces):
        a, b, c = (vertices[index] for index in face)
        normal = cross(subtract(b, a), subtract(c, a))
        normals.append(normal)
        plane = None
        if normal != (0, 0, 0):
            scale = next(value for value in normal if value)
            plane = tuple(value / scale for value in normal) + (dot(normal, a) / scale,)
        planes.append(plane)
        for index in range(3):
            a, b = face[index], face[(index + 1) % 3]
            edge = (min(a, b), max(a, b))
            incidence.setdefault(edge, []).append((a, b, face_index))
    neighbors = [[] for _ in faces]
    nonmanifold_faces, winding_faces = set(), set()
    for occurrences in incidence.values():
        if len(occurrences) > 2:
            nonmanifold_faces.update(face for _, _, face in occurrences)
        elif len(occurrences) == 2:
            a, b, first = occurrences[0]
            c, d, second = occurrences[1]
            if a != d or b != c or first == second:
                winding_faces.update((first, second))
        anchors = {}
        for _, _, face in occurrences:
            anchor = anchors.setdefault(planes[face], face)
            if face != anchor:
                neighbors[anchor].append(face)
                neighbors[face].append(anchor)

    labels = [-1] * len(faces)
    component_count = 0
    for first in range(len(faces)):
        if labels[first] != -1:
            continue
        labels[first] = component_count
        pending = [first]
        while pending:
            current = pending.pop()
            for neighbor in neighbors[current]:
                if labels[neighbor] == -1:
                    labels[neighbor] = component_count
                    pending.append(neighbor)
        component_count += 1
    components = [[] for _ in range(component_count)]
    for face_index, label in enumerate(labels):
        components[label].append(face_index)
    boundaries = [[] for _ in range(component_count)]
    for occurrences in incidence.values():
        if len(occurrences) == 1:
            a, b, face = occurrences[0]
            boundaries[labels[face]].append((a, b))
        elif len(occurrences) == 2:
            a, b, first = occurrences[0]
            c, d, second = occurrences[1]
            if labels[first] != labels[second]:
                boundaries[labels[first]].append((a, b))
                boundaries[labels[second]].append((c, d))
    return normals, components, boundaries, nonmanifold_faces, winding_faces


def _component_rectangle(vertices, faces, indices, normals, boundary,
                         nonmanifold_faces, winding_faces):
    if any(normals[index] == (0, 0, 0) for index in indices):
        raise _NotRectangle('degenerate_triangle')
    if any(index in nonmanifold_faces for index in indices):
        raise _NotRectangle('nonmanifold_edge')
    if any(index in winding_faces for index in indices):
        raise _NotRectangle('inconsistent_shared_edge_winding')
    if len(indices) < 2:
        raise _NotRectangle('insufficient_faces')
    normal = normals[indices[0]]
    axis = next(index for index, value in enumerate(normal) if value)
    positive_front = normal[axis] > 0
    total = 0
    referenced = set()
    for face_index in indices:
        area = normals[face_index][axis]
        if (area > 0) != positive_front:
            raise _NotRectangle('inconsistent_triangle_winding')
        total += area
        referenced.update(faces[face_index])
    quad, normal = _rectangle_boundary(vertices, boundary, referenced)
    if total != 2 * normal[axis]:
        raise _NotRectangle('triangle_area_boundary_mismatch')
    return quad, normal


def _rectangle_boundary(vertices, boundary, referenced):
    if len(boundary) < 4:
        raise _NotRectangle('insufficient_boundary')
    successor, incoming = {}, set()
    for a, b in boundary:
        if a in successor or b in incoming:
            raise _NotRectangle('branched_boundary')
        successor[a] = b
        incoming.add(b)
    if set(successor) != incoming:
        raise _NotRectangle('open_boundary')

    first = min(successor, key=lambda index: vertices[index])
    cycle, visited, current = [], set(), first
    while current not in visited:
        visited.add(current)
        cycle.append(current)
        current = successor[current]
    if current != first or len(cycle) != len(boundary):
        raise _NotRectangle('multiple_boundary_cycles')

    corners = []
    for index, vertex_index in enumerate(cycle):
        point = vertices[vertex_index]
        before = subtract(point, vertices[cycle[index - 1]])
        after = subtract(vertices[cycle[(index + 1) % len(cycle)]], point)
        if cross(before, after) == (0, 0, 0) and dot(before, after) > 0:
            continue
        corners.append(point)
    if len(corners) != 4 or len(set(corners)) != 4:
        raise _NotRectangle('four_corners_required')
    start = min(range(4), key=lambda index: corners[index])
    quad = tuple(corners[start:] + corners[:start])
    u, v = subtract(quad[1], quad[0]), subtract(quad[3], quad[0])
    normal = cross(u, v)
    if (normal == (0, 0, 0) or dot(u, v) or
            subtract(quad[2], quad[1]) != v or subtract(quad[2], quad[3]) != u):
        raise _NotRectangle('rectangle_required')
    u_squared, v_squared = dot(u, u), dot(v, v)
    for vertex_index in referenced:
        offset = subtract(vertices[vertex_index], quad[0])
        if not (0 <= dot(offset, u) <= u_squared and 0 <= dot(offset, v) <= v_squared):
            raise _NotRectangle('referenced_vertex_outside_rectangle')
    return quad, normal


def partition_regions(objects):
    """Return canonical rectangles and a complete source-triangle partition."""
    regions, scope = [], []
    for object_index, (vertices, faces, _, name) in enumerate(objects):
        normals, components, boundaries, nonmanifold, winding = _planar_components(vertices, faces)
        supported, unsupported = set(), []
        for indices, boundary in zip(components, boundaries):
            try:
                quad, normal = _component_rectangle(vertices, faces, indices, normals, boundary,
                                                     nonmanifold, winding)
            except _NotRectangle as error:
                unsupported.append({'triangle_indices': tuple(indices), 'reason': str(error)})
                continue
            region_id = 'roi_' + fingerprint(quad)[:24]
            regions.append(Region(region_id, object_index, name, tuple(indices), quad, normal))
            supported.update(indices)
        scope.append({
            'object_index': object_index, 'source_triangle_count': len(faces),
            'supported_triangle_count': len(supported),
            'supported_triangle_indices': tuple(index for index in range(len(faces)) if index in supported),
            'unsupported_triangle_count': len(faces) - len(supported),
            'unsupported_components': tuple(unsupported),
        })
    regions.sort(key=lambda region: region.roi_id)
    if len({region.roi_id for region in regions}) != len(regions):
        raise ValueError('coincident_independent_region_identity')
    return tuple(regions), tuple(scope)


def regions_from_objects(objects):
    return partition_regions(objects)[0]


def signed_area(polygon):
    return sum(a[0] * b[1] - a[1] * b[0]
               for a, b in zip(polygon, polygon[1:] + polygon[:1])) / 2


def clip_halfspace(polygon, distances):
    output = []
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        da, db = distances[index], distances[(index + 1) % len(polygon)]
        if da >= 0:
            output.append(a)
        if (da >= 0) != (db >= 0):
            fraction = da / (da - db)
            output.append(tuple(x + fraction * (y - x) for x, y in zip(a, b)))
    return tuple(output)


def clip_convex(polygon, boundary):
    for a, b in zip(boundary, boundary[1:] + boundary[:1]):
        if not polygon:
            break
        distances = tuple((b[0] - a[0]) * (point[1] - a[1]) -
                          (b[1] - a[1]) * (point[0] - a[0]) for point in polygon)
        polygon = clip_halfspace(polygon, distances)
    return polygon


def screen_basis(direction):
    up = (0, 0, 1)
    u = cross(up, direction)
    if not dot(u, u):
        u = cross((0, 1, 0), direction)
    return u, cross(direction, u)


def project(polygon, basis):
    return tuple((dot(point, basis[0]), dot(point, basis[1])) for point in polygon)


def bounds(polygon):
    return tuple((min(point[i] for point in polygon), max(point[i] for point in polygon)) for i in range(2))


def bounds_overlap(a, b):
    return all(min(x[1], y[1]) > max(x[0], y[0]) for x, y in zip(a, b))


def camera_planes(pose):
    view = tuple(tuple(Fraction(value) for value in row) for row in pose['view_matrix'])
    projection = tuple(tuple(Fraction(value) for value in row) for row in pose['projection_matrix'])
    if view[3] != (0, 0, 0, 1) or projection[3] != (0, 0, 0, 1):
        raise ValueError('affine_orthographic_camera_required')
    matrix = tuple(tuple(sum(projection[i][k] * view[k][j] for k in range(4))
                         for j in range(4)) for i in range(3))
    return tuple(tuple(sign * value for value in row[:3]) + (1 + sign * row[3],)
                 for row in matrix for sign in (1, -1))


def plane_distances(polygon, plane):
    return tuple(dot(point, plane[:3]) + plane[3] for point in polygon)


def inside_frustum(polygon, planes):
    return all(min(plane_distances(polygon, plane)) >= 0 for plane in planes)


def triangle_shadow(triangle, region, basis, planes, cached_screen=None):
    polygon = triangle.vertices
    for plane in planes:
        distances = plane_distances(polygon, plane)
        if min(distances) < 0:
            polygon = clip_halfspace(polygon, distances)
            if not polygon:
                return ()
    distances = tuple(dot(region.normal, subtract(point, region.vertices[0])) for point in polygon)
    if max(distances) <= 0:
        return ()
    if min(distances) < 0:
        polygon = clip_halfspace(polygon, distances)
    if cached_screen is not None and polygon == triangle.vertices:
        return cached_screen
    return project(polygon, basis)


@dataclass(frozen=True)
class CoverageIndex:
    scene_identity: str
    candidate_identity: str
    regions: tuple
    view_order: tuple
    view_masks: dict
    classifications: dict
    stats: dict = field(default_factory=dict)
    patch_scope: tuple = ()

    @property
    def region_ids(self):
        return tuple(region.roi_id for region in self.regions)

    def ids(self, mask):
        return [identity for i, identity in enumerate(self.region_ids) if mask & (1 << i)]


def build_index_from_parsed(objects, triangles, scene_identity, regions, cameras, *, patch_scope=()):
    """Build exact finite-view coverage from the existing normalized geometry."""
    poses = tuple(cameras['views'])
    view_names = {pose['name'] for pose in poses}
    if len(view_names) != len(poses):
        raise ValueError('unique_view_names_required')
    if 'SCENE' not in view_names:
        raise ValueError('common_SCENE_view_required')
    candidate_identity = fingerprint([
        {key: pose[key] for key in ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')}
        for pose in poses])
    masks, classifications = {}, {}
    region_triangles = {region.roi_id: frozenset(region.triangle_indices) for region in regions}
    for pose in poses:
        direction = vector(pose['direction_rational'])
        if not dot(direction, direction):
            raise ValueError('nonzero_camera_direction_required')
        basis, planes = screen_basis(direction), camera_planes(pose)
        projected, boxes = {}, {}
        points = sorted({point for triangle in triangles for point in triangle.vertices})
        values = project(tuple(points), basis)
        by_vertex = dict(zip(points, values))
        for triangle in triangles:
            screen = tuple(by_vertex[point] for point in triangle.vertices)
            projected[triangle.key] = screen
            boxes[triangle.key] = bounds(screen)
        mask, rows = 0, {}
        for index, region in enumerate(regions):
            status = 'complete'
            facing = dot(region.normal, direction)
            if facing <= 0:
                rows[region.roi_id] = {'status': 'back_facing' if facing < 0 else 'edge_on', 'complete': False}
                continue
            if not inside_frustum(region.vertices, planes):
                rows[region.roi_id] = {'status': 'outside_frustum', 'complete': False}
                continue
            region_screen = project(region.vertices, basis)
            if signed_area(region_screen) < 0:
                region_screen = tuple(reversed(region_screen))
            region_bounds = bounds(region_screen)
            blocker = None
            for triangle in triangles:
                if (triangle.object_index == region.object_index
                        and triangle.triangle_index in region_triangles[region.roi_id]):
                    continue
                if not bounds_overlap(region_bounds, boxes[triangle.key]):
                    continue
                shadow = triangle_shadow(triangle, region, basis, planes, projected.get(triangle.key))
                if len(shadow) < 3 or not signed_area(shadow):
                    continue
                overlap = clip_convex(shadow, region_screen)
                if overlap and abs(signed_area(overlap)) > 0:
                    status = 'positive_area_occlusion'
                    blocker = {
                        'triangle_geometry_id': fingerprint(triangle.key),
                        'overlap_area_screen_exact': str(abs(signed_area(overlap))),
                    }
                    break
            complete = status == 'complete'
            rows[region.roi_id] = {'status': status, 'complete': complete, 'first_blocker': blocker}
            if complete:
                mask |= 1 << index
        masks[pose['name']], classifications[pose['name']] = mask, rows
    return CoverageIndex(scene_identity, candidate_identity, regions,
                         tuple(pose['name'] for pose in poses), masks, classifications,
                         patch_scope=patch_scope)


@dataclass
class CoverageState:
    index: CoverageIndex
    observed_views: dict = field(default_factory=dict)
    covered_mask: int = 0
    updates: int = 0
    patch_mapping_identity: str | None = None
    patch_mapping_required: bool = False

    def bind_patch_mapping(self, identity):
        if not isinstance(identity, str) or not identity:
            raise ValueError('patch_mapping_identity_required')
        if identity != self.patch_mapping_identity:
            self.observed_views.clear()
            self.covered_mask = 0
            self.updates = 0
        self.patch_mapping_required = True
        self.patch_mapping_identity = identity

    def invalidate_patch_mapping(self):
        self.patch_mapping_required = True
        self.patch_mapping_identity = None
        self.observed_views.clear()
        self.covered_mask = 0
        self.updates = 0

    def next_view(self):
        if not self.observed_views:
            return 'SCENE'
        candidates = [(name, (self.index.view_masks[name] & ~self.covered_mask).bit_count())
                      for name in self.index.view_order if name not in self.observed_views]
        candidates = [row for row in candidates if row[1] > 0]
        return max(candidates, key=lambda row: row[1])[0] if candidates else None

    def observe(self, receipt):
        name = receipt['view_name']
        if self.patch_mapping_required and (
                self.patch_mapping_identity is None
                or receipt.get('patch_mapping_identity') != self.patch_mapping_identity):
            raise ValueError('current_patch_mapping_receipt_required')
        if (receipt.get('scene_identity') != self.index.scene_identity
                or receipt.get('candidate_identity') != self.index.candidate_identity
                or receipt.get('actual_image_delivered') is not True
                or not receipt.get('image_path') or not receipt.get('image_sha256')
                or receipt.get('pixel_evidence_scope') != 'actual_common_depth_owner'):
            raise ValueError('actual_bound_image_receipt_required')
        if name not in self.index.view_masks:
            raise ValueError('unknown_delivered_view')
        if not self.observed_views and name != 'SCENE':
            raise ValueError('common_SCENE_observation_required')
        raw = Path(receipt['image_path']).read_bytes()
        if raw[:8] != b'\x89PNG\r\n\x1a\n' or hashlib.sha256(raw).hexdigest() != receipt['image_sha256']:
            raise ValueError('actual_PNG_bytes_required')
        readable = set(receipt['readable_roi_ids'])
        if not readable.issubset(self.index.region_ids):
            raise ValueError('unknown_readable_region')
        if name in self.observed_views:
            return {'view_name': name, 'reused': True, 'new_roi_ids': []}
        readable_mask = sum(1 << i for i, identity in enumerate(self.index.region_ids) if identity in readable)
        delivered = self.index.view_masks[name] & readable_mask
        added = delivered & ~self.covered_mask
        self.covered_mask |= delivered
        self.observed_views[name] = dict(receipt)
        self.updates += 1
        return {'view_name': name, 'reused': False, 'new_roi_ids': self.index.ids(added),
                'covered_roi_ids': self.index.ids(self.covered_mask), 'unresolved_roi_ids': self.unresolved()}

    def unresolved(self):
        return self.index.ids(((1 << len(self.index.regions)) - 1) & ~self.covered_mask)

    def summary(self):
        possible = 0
        for mask in self.index.view_masks.values():
            possible |= mask
        return {'observed_views': list(self.observed_views), 'covered_roi_ids': self.index.ids(self.covered_mask),
                'unresolved_roi_ids': self.unresolved(),
                'candidate_pool_uncovered_roi_ids': self.index.ids(((1 << len(self.index.regions)) - 1) & ~possible),
                'state_updates': self.updates, 'scope': 'registered finite camera pool'}

    def rebind(self, index):
        changed = (index.scene_identity, index.candidate_identity) != (self.index.scene_identity, self.index.candidate_identity)
        self.index = index
        if changed:
            self.observed_views.clear()
            self.covered_mask = 0
            self.updates = 0
            if self.patch_mapping_required:
                self.patch_mapping_identity = None
        return changed


@dataclass
class ActiveObservationSession:
    objects: tuple
    triangles: tuple
    cameras: dict
    index: CoverageIndex
    state: CoverageState
    diagnostics: dict | None = None

    @property
    def scene_identity(self):
        return self.index.scene_identity

    @property
    def candidate_identity(self):
        return self.index.candidate_identity

    @property
    def regions(self):
        return self.index.regions

    def next_view(self):
        return self.state.next_view()

    def observe(self, receipt):
        return self.state.observe(receipt)

    def summary(self):
        return self.state.summary()

    def short_facts(self):
        summary = self.summary()
        covered = set(summary['covered_roi_ids'])
        unavailable = set(summary['candidate_pool_uncovered_roi_ids'])
        remaining = 0
        for name, mask in self.index.view_masks.items():
            if name not in self.state.observed_views:
                remaining |= mask
        regions = []
        for index, region in enumerate(self.regions):
            reason = 'observed_readable' if region.roi_id in covered else 'pending_observation'
            if region.roi_id in unavailable:
                reason = 'finite_camera_pool_uncovered'
            elif region.roi_id not in covered and not (remaining & (1 << index)):
                reason = 'pixel_evidence_insufficient'
            regions.append({'roi_id': region.roi_id, 'object_index': region.object_index,
                            'object_name': region.object_name,
                            'status': 'covered' if region.roi_id in covered else 'unknown', 'reason': reason})
        pixel_fields = (
            'roi_id', 'object_index', 'view', 'front_facing',
            'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable',
            'minimum_surface_pixels', 'minimum_boundary_pixels',
            'minimum_rgb_boundary_contrast',
        )
        observations = [
            {'view_name': name, 'image_path': receipt['image_path'],
             'image_ref': receipt.get('image_ref'),
             'image_sha256': receipt['image_sha256'],
             'readable_roi_ids': list(receipt['readable_roi_ids']),
             'pixel_rows': [
                 {key: row[key] for key in pixel_fields if key in row}
                 for row in receipt.get('pixel_rows', [])
             ]}
            for name, receipt in self.state.observed_views.items()
        ]
        return {'scene_identity': self.scene_identity, 'candidate_identity': self.candidate_identity,
                'regions': regions, 'observations': observations, 'coverage': summary,
                'image_delivery_scope': 'local_core_validation'}

    def rebind(self, scene, cameras):
        prepared = prepare_scene(scene, cameras, diagnostics=self.diagnostics is not None)
        ordered_geometry_changed = tuple((source[0], source[1]) for source in self.objects) != tuple(
            (source[0], source[1]) for source in prepared.objects)
        changed = self.state.rebind(prepared.index)
        if ordered_geometry_changed and self.state.patch_mapping_required:
            self.state.invalidate_patch_mapping()
        self.objects = prepared.objects
        self.triangles = prepared.triangles
        self.cameras = prepared.cameras
        self.index = prepared.index
        self.diagnostics = prepared.diagnostics
        return changed


def prepare_scene(scene, cameras, diagnostics=False):
    """Prepare complete world meshes and a registered pool containing SCENE.

    Each object supplies ``vertices``, ``triangles`` and an optional ``name``.
    Camera view dictionaries retain the explicit matrices, directions and
    image dimensions supplied by the caller. Diagnostics contain phase clocks
    and aggregate sizes.
    """
    if diagnostics:
        started = time.perf_counter_ns()
    objects, triangles, scene_identity = geometry(scene)
    if diagnostics:
        closed = time.perf_counter_ns()
        geometry_stage = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
    session = prepare_scene_from_parsed(objects, triangles, scene_identity, cameras, diagnostics=diagnostics)
    if diagnostics:
        session.diagnostics['stages'] = {'geometry': geometry_stage, **session.diagnostics['stages']}
    return session


def prepare_scene_from_parsed(objects, triangles, scene_identity, cameras, diagnostics=False):
    """Prepare from the exact objects/triangles/identity returned by geometry.

    Camera fitting and image conversion can share this normalized geometry
    before entering discovery and coverage. The caller retains its full mesh
    ordering in the returned session.
    """
    stages = {} if diagnostics else None
    if diagnostics:
        started = time.perf_counter_ns()
    owned_cameras = copy.deepcopy(cameras)
    regions, patch_scope = partition_regions(objects)
    if diagnostics:
        closed = time.perf_counter_ns()
        stages['discovery'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
        started = closed
    index = build_index_from_parsed(objects, triangles, scene_identity, regions, owned_cameras,
                                    patch_scope=patch_scope)
    if diagnostics:
        closed = time.perf_counter_ns()
        stages['coverage'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
    details = None
    if diagnostics:
        details = {'stages': stages, 'objects': len(objects), 'triangles': len(triangles),
                   'regions': len(regions), 'views': len(index.view_order)}
    return ActiveObservationSession(objects, triangles, owned_cameras, index, CoverageState(index), details)
