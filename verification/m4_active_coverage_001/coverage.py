"""Exact geometric ROI discovery, finite-view coverage and delivered state."""

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def vector(values):
    if len(values) != 3 or any(type(value) is bool for value in values):
        raise ValueError('three_numeric_coordinates_required')
    return tuple(Fraction(value) for value in values)


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def fingerprint(value):
    raw = json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def canonical_triangle(vertices):
    return min(vertices[index:] + vertices[:index] for index in range(3))


def geometry(scene):
    objects, triangles = [], []
    for object_index, source in enumerate(scene['objects']):
        vertices = tuple(vector(value) for value in source['vertices'])
        faces = tuple(tuple(face) for face in source['triangles'])
        for face in faces:
            if len(face) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in face):
                raise ValueError('invalid_triangle_indices')
        key = (tuple(sorted(vertices)), tuple(sorted(canonical_triangle(tuple(vertices[i] for i in face)) for face in faces)))
        objects.append((vertices, faces, key, str(source.get('name', ''))))
        for triangle_index, face in enumerate(faces):
            points = tuple(vertices[i] for i in face)
            triangles.append(Triangle(object_index, triangle_index, points, canonical_triangle(points)))
    triangles.sort(key=lambda triangle: triangle.key)
    identity = fingerprint(tuple(sorted(item[2] for item in objects)))
    return tuple(objects), tuple(triangles), identity


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


def regions_from_objects(objects):
    regions = []
    for object_index, (vertices, faces, _, name) in enumerate(objects):
        if len(vertices) != 4 or len(set(vertices)) != 4 or len(faces) != 2:
            continue
        normals = [cross(subtract(vertices[b], vertices[a]), subtract(vertices[c], vertices[a])) for a, b, c in faces]
        if not dot(normals[0], normals[0]) or not dot(normals[1], normals[1]):
            continue
        if cross(normals[0], normals[1]) != (0, 0, 0) or dot(normals[0], normals[1]) <= 0:
            continue
        if any(dot(normals[0], subtract(point, vertices[faces[0][0]])) for point in vertices):
            continue
        edges = [(face[i], face[(i+1) % 3]) for face in faces for i in range(3)]
        shared = [edge for edge in edges if (edge[1], edge[0]) in edges]
        boundary = [edge for edge in edges if (edge[1], edge[0]) not in edges]
        if len(shared) != 2 or len(boundary) != 4 or len({a for a, _ in boundary}) != 4:
            continue
        successor = dict(boundary)
        first = min(range(4), key=lambda i: vertices[i])
        cycle, current = [], first
        for _ in range(4):
            cycle.append(current)
            current = successor.get(current, -1)
        if current != first or len(set(cycle)) != 4:
            continue
        quad = tuple(vertices[i] for i in cycle)
        u, v = subtract(quad[1], quad[0]), subtract(quad[3], quad[0])
        if dot(u, v) or subtract(quad[2], quad[1]) != v or subtract(quad[2], quad[3]) != u:
            continue
        normal = cross(u, v)
        region_id = 'roi_' + fingerprint(quad)[:24]
        regions.append(Region(region_id, object_index, name, (0, 1), quad, normal))
    regions.sort(key=lambda region: region.roi_id)
    if len({region.roi_id for region in regions}) != len(regions):
        raise ValueError('coincident_independent_region_identity')
    return tuple(regions)


def discover_regions(scene):
    return regions_from_objects(geometry(scene)[0])


def signed_area(polygon):
    return sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(polygon, polygon[1:]+polygon[:1])) / 2


def clip_halfspace(polygon, distances):
    output = []
    for index, a in enumerate(polygon):
        b = polygon[(index+1) % len(polygon)]
        da, db = distances[index], distances[(index+1) % len(polygon)]
        if da >= 0:
            output.append(a)
        if (da >= 0) != (db >= 0):
            fraction = da / (da-db)
            output.append(tuple(x + fraction*(y-x) for x, y in zip(a, b)))
    return tuple(output)


def clip_convex(polygon, boundary):
    for a, b in zip(boundary, boundary[1:]+boundary[:1]):
        if not polygon:
            break
        distances = tuple((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]) for point in polygon)
        polygon = clip_halfspace(polygon, distances)
    return polygon


def screen_basis(direction):
    up = (0, 0, 1)
    u = cross(up, direction)
    if not dot(u, u):
        u = cross((0, 1, 0), direction)
    return u, cross(direction, u)


def project(polygon, basis, stats):
    stats['projected_vertices'] += len(polygon)
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
    matrix = tuple(tuple(sum(projection[i][k]*view[k][j] for k in range(4)) for j in range(4)) for i in range(3))
    return tuple(tuple(sign*value for value in row[:3]) + (1+sign*row[3],) for row in matrix for sign in (1, -1))


def plane_distances(polygon, plane):
    return tuple(dot(point, plane[:3])+plane[3] for point in polygon)


def inside_frustum(polygon, planes):
    return all(min(plane_distances(polygon, plane)) >= 0 for plane in planes)


def triangle_shadow(triangle, region, basis, planes, stats, cached_screen=None):
    polygon = triangle.vertices
    for plane in planes:
        distances = plane_distances(polygon, plane)
        if min(distances) < 0:
            stats['frustum_clips'] += 1
            polygon = clip_halfspace(polygon, distances)
            if not polygon:
                return ()
    stats['front_tests'] += 1
    distances = tuple(dot(region.normal, subtract(point, region.vertices[0])) for point in polygon)
    if max(distances) <= 0:
        stats['behind_rejected'] += 1
        return ()
    if min(distances) < 0:
        polygon = clip_halfspace(polygon, distances)
    if cached_screen is not None and polygon == triangle.vertices:
        return cached_screen
    return project(polygon, basis, stats)


@dataclass(frozen=True)
class CoverageIndex:
    scene_identity: str
    candidate_identity: str
    regions: tuple
    view_order: tuple
    view_masks: dict
    classifications: dict
    stats: dict

    @property
    def region_ids(self):
        return tuple(region.roi_id for region in self.regions)

    def ids(self, mask):
        return [identity for i, identity in enumerate(self.region_ids) if mask & (1 << i)]


def build_index(scene, cameras, variant='reference'):
    if variant not in ('reference', 'optimized'):
        raise ValueError('unknown_coverage_variant')
    objects, triangles, scene_identity = geometry(scene)
    regions = regions_from_objects(objects)
    poses = tuple(cameras['views'])
    if len({pose['name'] for pose in poses}) != len(poses):
        raise ValueError('unique_view_names_required')
    candidate_identity = fingerprint([{key: pose[key] for key in ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')} for pose in poses])
    stats = {key: 0 for key in ('projected_vertices', 'projection_index_vertices', 'bbox_tests', 'bbox_rejected',
                                'front_tests', 'behind_rejected', 'frustum_clips', 'exact_clips', 'tested_triangles')}
    stats.update(discovered_regions=len(regions), triangles=len(triangles), geometry_vertices=sum(len(item[0]) for item in objects))
    masks, classifications = {}, {}
    for pose in poses:
        direction = vector(pose['direction_rational'])
        if not dot(direction, direction):
            raise ValueError('nonzero_camera_direction_required')
        basis, planes = screen_basis(direction), camera_planes(pose)
        projected, boxes = {}, {}
        if variant == 'optimized':
            points = sorted({point for triangle in triangles for point in triangle.vertices})
            values = project(tuple(points), basis, stats)
            stats['projection_index_vertices'] += len(points)
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
            region_screen = project(region.vertices, basis, stats)
            if signed_area(region_screen) < 0:
                region_screen = tuple(reversed(region_screen))
            region_bounds = bounds(region_screen)
            blocker = None
            for triangle in triangles:
                if triangle.object_index == region.object_index:
                    continue
                stats['tested_triangles'] += 1
                if variant == 'optimized':
                    stats['bbox_tests'] += 1
                    if not bounds_overlap(region_bounds, boxes[triangle.key]):
                        stats['bbox_rejected'] += 1
                        continue
                shadow = triangle_shadow(triangle, region, basis, planes, stats, projected.get(triangle.key))
                if len(shadow) < 3 or not signed_area(shadow):
                    continue
                stats['exact_clips'] += 1
                overlap = clip_convex(shadow, region_screen)
                if overlap and abs(signed_area(overlap)) > 0:
                    status = 'positive_area_occlusion'
                    blocker = {'triangle_geometry_id': fingerprint(triangle.key), 'overlap_area_screen_exact': str(abs(signed_area(overlap)))}
                    break
            complete = status == 'complete'
            rows[region.roi_id] = {'status': status, 'complete': complete, 'first_blocker': blocker}
            if complete:
                mask |= 1 << index
        masks[pose['name']], classifications[pose['name']] = mask, rows
    return CoverageIndex(scene_identity, candidate_identity, regions, tuple(pose['name'] for pose in poses), masks, classifications, stats)


@dataclass
class CoverageState:
    index: CoverageIndex
    observed_views: dict = field(default_factory=dict)
    covered_mask: int = 0
    updates: int = 0

    def next_view(self):
        if not self.observed_views:
            return 'SCENE'
        candidates = [(name, (self.index.view_masks[name] & ~self.covered_mask).bit_count())
                      for name in self.index.view_order if name not in self.observed_views]
        candidates = [row for row in candidates if row[1] > 0]
        return max(candidates, key=lambda row: row[1])[0] if candidates else None

    def observe(self, receipt):
        name = receipt['view_name']
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
        return self.index.ids(((1 << len(self.index.regions))-1) & ~self.covered_mask)

    def summary(self):
        possible = 0
        for mask in self.index.view_masks.values():
            possible |= mask
        return {'observed_views': list(self.observed_views), 'covered_roi_ids': self.index.ids(self.covered_mask),
                'unresolved_roi_ids': self.unresolved(),
                'candidate_pool_uncovered_roi_ids': self.index.ids(((1 << len(self.index.regions))-1) & ~possible),
                'state_updates': self.updates, 'scope': 'registered finite camera pool'}

    def rebind(self, index):
        changed = (index.scene_identity, index.candidate_identity) != (self.index.scene_identity, self.index.candidate_identity)
        self.index = index
        if changed:
            self.observed_views.clear()
            self.covered_mask = 0
            self.updates = 0
        return changed
