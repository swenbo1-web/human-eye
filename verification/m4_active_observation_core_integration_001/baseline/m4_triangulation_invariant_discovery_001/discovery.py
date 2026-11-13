"""Exact, triangulation-invariant discovery for one rectangular mesh object.

The two discovery variants share topology, plane and boundary validation.  Both
feed the unchanged optimized coverage code from the frozen coverage-001 core.
"""

import hashlib
import importlib.util
from pathlib import Path
import sys
import time
import types


HERE = Path(__file__).resolve().parent
CORE_PATH = HERE.with_name('m4_active_coverage_001') / 'coverage.py'
CORE_SHA256 = '2561ecaf2f2df98ec7c03ed48cb95dd08c34f10ce73c1e9ecc2e32f31c41daf4'


def _load_core():
    if hashlib.sha256(CORE_PATH.read_bytes()).hexdigest() != CORE_SHA256:
        raise RuntimeError('frozen_coverage_core_changed')
    name = '_triangulation_invariant_001_frozen_coverage'
    spec = importlib.util.spec_from_file_location(name, CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


legacy = _load_core()
Region = legacy.Region
Triangle = legacy.Triangle
CoverageIndex = legacy.CoverageIndex
CoverageState = legacy.CoverageState
subtract = legacy.subtract
cross = legacy.cross
dot = legacy.dot


class _NotRectangle(Exception):
    """An object falls outside this batch's single rectangular surface domain."""


WORK_KEYS = (
    'face_incidence_visits', 'oriented_edge_insertions', 'undirected_edges',
    'interior_edges', 'boundary_edges', 'referenced_vertices', 'plane_tests',
    'face_orientation_visits', 'full_area_cross_products',
    'projected_area_determinants', 'orientation_dot_products',
    'area_component_additions', 'orientation_vector_components_constructed',
    'area_rational_multiply_calls', 'area_rational_subtract_calls',
    'area_rational_add_calls',
    'connectivity_face_visits', 'connectivity_neighbor_visits',
    'boundary_walk_steps', 'collinear_tests', 'inside_tests',
    'input_fraction_components',
)


def source_binding():
    return {
        'coverage_core_path': str(CORE_PATH),
        'coverage_core_sha256': CORE_SHA256,
        'coverage_entry': 'build_index',
        'coverage_variant': 'optimized',
        'coverage_code_reuse': 'FunctionType with identical frozen code object',
        'region_type_module': Region.__module__,
        'state_type_module': CoverageState.__module__,
    }


def parse_geometry(scene, stats=None):
    """Parse Fraction geometry and compute its old identity exactly once."""
    started = time.perf_counter_ns()
    parsed = legacy.geometry(scene)
    closed = time.perf_counter_ns()
    if stats is not None:
        objects, triangles, identity = parsed
        stats['geometry'] = {
            'started_ns': started,
            'closed_ns': closed,
            'elapsed_ns': closed - started,
            'calls': 1,
            'object_count': len(objects),
            'vertex_count': sum(len(item[0]) for item in objects),
            'triangle_count': len(triangles),
            'scene_identity': identity,
        }
    return parsed


def _work(object_index, vertices, faces):
    result = {key: 0 for key in WORK_KEYS}
    result.update({
        'object_index': object_index,
        'source_vertices': len(vertices),
        'source_faces': len(faces),
        'input_max_numerator_bits': 0,
        'input_max_denominator_bits': 0,
        'temporary_payload_unit': 'structural element counts, not bytes or RSS',
        'edge_occurrences_retained': 0,
        'adjacency_entries_retained': 0,
        'boundary_vertex_ids_retained': 0,
        'orientation_vector_components_peak': 0,
        'area_accumulator_components': 0,
        'area_sum_max_numerator_bits': 0,
        'area_sum_max_denominator_bits': 0,
    })
    return result


def _topology(vertices, faces, work):
    """One incidence construction, then one face-connectivity traversal."""
    if len(faces) < 2:
        raise _NotRectangle('insufficient_faces')
    first = faces[0]
    origin = vertices[first[0]]
    plane_normal = cross(subtract(vertices[first[1]], origin),
                         subtract(vertices[first[2]], origin))
    if plane_normal == (0, 0, 0):
        raise _NotRectangle('degenerate_seed_triangle')

    referenced = set()
    incidence = {}
    for face_index, face in enumerate(faces):
        work['face_incidence_visits'] += 1
        referenced.update(face)
        for index in range(3):
            a, b = face[index], face[(index + 1) % 3]
            edge = (min(a, b), max(a, b))
            occurrences = incidence.setdefault(edge, [])
            occurrences.append((a, b, face_index))
            work['oriented_edge_insertions'] += 1
            if len(occurrences) > 2:
                raise _NotRectangle('nonmanifold_edge')

    work['undirected_edges'] = len(incidence)
    work['referenced_vertices'] = len(referenced)
    work['edge_occurrences_retained'] = work['oriented_edge_insertions']
    for vertex_index in referenced:
        point = vertices[vertex_index]
        for component in point:
            work['input_fraction_components'] += 1
            work['input_max_numerator_bits'] = max(
                work['input_max_numerator_bits'], abs(component.numerator).bit_length())
            work['input_max_denominator_bits'] = max(
                work['input_max_denominator_bits'], component.denominator.bit_length())
        work['plane_tests'] += 1
        if dot(plane_normal, subtract(point, origin)):
            raise _NotRectangle('noncoplanar_referenced_vertex')

    neighbors = [[] for _ in faces]
    boundary = []
    for occurrences in incidence.values():
        if len(occurrences) == 1:
            a, b, _ = occurrences[0]
            boundary.append((a, b))
            continue
        a, b, first_face = occurrences[0]
        c, d, second_face = occurrences[1]
        if a != d or b != c or first_face == second_face:
            raise _NotRectangle('internal_edge_orientation')
        neighbors[first_face].append(second_face)
        neighbors[second_face].append(first_face)
        work['interior_edges'] += 1
    work['boundary_edges'] = len(boundary)
    work['adjacency_entries_retained'] = 2 * work['interior_edges']

    visited = {0}
    pending = [0]
    while pending:
        face_index = pending.pop()
        work['connectivity_face_visits'] += 1
        for neighbor in neighbors[face_index]:
            work['connectivity_neighbor_visits'] += 1
            if neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    if len(visited) != len(faces):
        raise _NotRectangle('disconnected_faces')
    return plane_normal, referenced, boundary


def _reference_area(vertices, faces, plane_normal, work):
    """Clear vector reference with exact full 3D triangle normals."""
    total = (0, 0, 0)
    for a, b, c in faces:
        normal = cross(subtract(vertices[b], vertices[a]),
                       subtract(vertices[c], vertices[a]))
        work['face_orientation_visits'] += 1
        work['full_area_cross_products'] += 1
        work['orientation_vector_components_constructed'] += 3
        work['orientation_vector_components_peak'] = 3
        work['area_rational_multiply_calls'] += 6
        work['area_rational_subtract_calls'] += 9
        if normal == (0, 0, 0):
            raise _NotRectangle('degenerate_triangle')
        work['orientation_dot_products'] += 1
        work['area_rational_multiply_calls'] += 3
        work['area_rational_add_calls'] += 3
        if dot(normal, plane_normal) <= 0:
            raise _NotRectangle('inconsistent_triangle_winding')
        total = tuple(total[index] + normal[index] for index in range(3))
        work['area_component_additions'] += 3
        work['area_rational_add_calls'] += 3
    work['area_accumulator_components'] = 3
    return total


def _candidate_area(vertices, faces, plane_normal, work):
    """Coplanarity makes one nonzero projected component sufficient."""
    axis = next(index for index, value in enumerate(plane_normal) if value)
    first_axis, second_axis = ((1, 2), (2, 0), (0, 1))[axis]
    positive_front = plane_normal[axis] > 0
    total = 0
    for a, b, c in faces:
        origin, point_b, point_c = vertices[a], vertices[b], vertices[c]
        signed_area = (
            (point_b[first_axis] - origin[first_axis]) *
            (point_c[second_axis] - origin[second_axis]) -
            (point_b[second_axis] - origin[second_axis]) *
            (point_c[first_axis] - origin[first_axis]))
        work['face_orientation_visits'] += 1
        work['projected_area_determinants'] += 1
        work['area_rational_multiply_calls'] += 2
        work['area_rational_subtract_calls'] += 5
        if not signed_area:
            raise _NotRectangle('degenerate_triangle')
        if (signed_area > 0) != positive_front:
            raise _NotRectangle('inconsistent_triangle_winding')
        total += signed_area
        work['area_component_additions'] += 1
        work['area_rational_add_calls'] += 1
    work['area_accumulator_components'] = 1
    return axis, total


def _rectangle_boundary(vertices, boundary, referenced, work):
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
        work['boundary_walk_steps'] += 1
        current = successor[current]
    if current != first or len(cycle) != len(boundary):
        raise _NotRectangle('multiple_boundary_cycles')
    work['boundary_vertex_ids_retained'] = len(cycle)

    corners = []
    for index, vertex_index in enumerate(cycle):
        point = vertices[vertex_index]
        before = subtract(point, vertices[cycle[index - 1]])
        after = subtract(vertices[cycle[(index + 1) % len(cycle)]], point)
        work['collinear_tests'] += 1
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
        work['inside_tests'] += 1
        if not (0 <= dot(offset, u) <= u_squared and 0 <= dot(offset, v) <= v_squared):
            raise _NotRectangle('referenced_vertex_outside_rectangle')
    return quad, normal


def regions_from_objects(objects, discovery_variant='reference', stats=None):
    """Discover each whole-object rectangle, preserving all source face IDs."""
    if discovery_variant not in ('reference', 'candidate'):
        raise ValueError('unknown_discovery_variant')
    started = time.perf_counter_ns()
    regions, records = [], []
    for object_index, (vertices, faces, _, name) in enumerate(objects):
        work = _work(object_index, vertices, faces)
        records.append(work)
        try:
            plane_normal, referenced, boundary = _topology(vertices, faces, work)
            if discovery_variant == 'reference':
                area = _reference_area(vertices, faces, plane_normal, work)
            else:
                axis, area = _candidate_area(vertices, faces, plane_normal, work)
            quad, normal = _rectangle_boundary(vertices, boundary, referenced, work)
            expected = (tuple(2 * value for value in normal)
                        if discovery_variant == 'reference' else 2 * normal[axis])
            if area != expected:
                raise _NotRectangle('triangle_area_boundary_mismatch')
            area_components = area if discovery_variant == 'reference' else (area,)
            work['area_sum_max_numerator_bits'] = max(abs(value.numerator).bit_length() for value in area_components)
            work['area_sum_max_denominator_bits'] = max(value.denominator.bit_length() for value in area_components)
        except _NotRectangle as error:
            work.update(status='rejected', reason=str(error))
            continue
        region_id = 'roi_' + legacy.fingerprint(quad)[:24]
        regions.append(Region(region_id, object_index, name, tuple(range(len(faces))), quad, normal))
        work.update(status='accepted', reason='rectangle', roi_id=region_id)
    regions.sort(key=lambda region: region.roi_id)
    if len({region.roi_id for region in regions}) != len(regions):
        raise ValueError('coincident_independent_region_identity')
    closed = time.perf_counter_ns()
    if stats is not None:
        stats['discovery'] = {
            'variant': discovery_variant,
            'started_ns': started,
            'closed_ns': closed,
            'elapsed_ns': closed - started,
            'object_count': len(objects),
            'accepted_objects': len(regions),
            'rejected_objects': len(objects) - len(regions),
            'work': {key: sum(record[key] for record in records) for key in WORK_KEYS},
            'input_max_numerator_bits': max((record['input_max_numerator_bits'] for record in records), default=0),
            'input_max_denominator_bits': max((record['input_max_denominator_bits'] for record in records), default=0),
            'objects': records,
        }
    return tuple(regions)


def build_index_from_parsed(objects, triangles, scene_identity, regions, cameras):
    """Run the frozen optimized coverage body with already parsed inputs."""
    namespace = legacy.build_index.__globals__.copy()
    namespace['geometry'] = lambda unused_scene: (objects, triangles, scene_identity)
    namespace['regions_from_objects'] = lambda unused_objects: regions
    entry = types.FunctionType(
        legacy.build_index.__code__, namespace, legacy.build_index.__name__,
        legacy.build_index.__defaults__, legacy.build_index.__closure__)
    entry.__kwdefaults__ = legacy.build_index.__kwdefaults__
    return entry(None, cameras, variant='optimized')


def build_from_parsed(objects, triangles, scene_identity, cameras,
                      discovery_variant='reference', stats=None):
    regions = regions_from_objects(objects, discovery_variant, stats)
    started = time.perf_counter_ns()
    index = build_index_from_parsed(objects, triangles, scene_identity, regions, cameras)
    closed = time.perf_counter_ns()
    if stats is not None:
        stats['coverage'] = {
            'started_ns': started,
            'closed_ns': closed,
            'elapsed_ns': closed - started,
            'variant': 'optimized',
            'frozen_code_object_reused': True,
            'geometry_reparsed': False,
            'discovery_repeated': False,
        }
    return index


def build_index(scene, cameras, discovery_variant='reference', stats=None):
    parsed = parse_geometry(scene, stats)
    return build_from_parsed(*parsed, cameras, discovery_variant, stats)
