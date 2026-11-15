"""Small, dependency-free Blender scene boundary for the external eye runtime.

Importing this file needs neither ``bpy`` nor the engine's NumPy/Pillow stack.
Inside Blender, load this file directly when the full engine is installed in a
different Python environment. All ``bpy`` access must run on Blender's main
thread. Merely constructing the host or capturing a snapshot never edits data.

Coverage is conservative: every mesh in the scene must be evaluated, including
hidden meshes. A viewport-disabled or layer-excluded mesh that Blender cannot
evaluate blocks the snapshot; it never falls back to unevaluated original data.
Ordinary evaluated modifiers are readable. Instancing, geometry-node modifiers,
and other geometry types are rejected rather than silently omitted. Executing a
transform has a narrower contract: the entire mesh scene must consist of static,
independent rigid meshes without modifiers, shape keys, parenting, constraints,
animation, drivers, or rigid-body simulation. This connector checks an endpoint;
it does not certify motion paths or physical behaviour.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import threading
import time
import uuid
import copy
from contextlib import contextmanager


def _exec_source_snapshot(module,source,blob=None):
    """Use a controlled worker's source witness; never accept cached pyc."""
    import sys
    from pathlib import Path
    source=Path(source).resolve()
    guard=next((f for f in sys.meta_path if getattr(f,'protocol',None)=='human-eye-verified-source-v1' and f.root==source.parents[1]),None)
    if guard is not None:return guard.exec_path(module,source,expected_blob=blob)
    if blob is None:
        with source.open('rb') as stream:blob=stream.read(512*1024+1)
    if len(blob)>512*1024:raise BlenderHostError('host_dependency_source_budget')
    exec(compile(blob,str(source),'exec',dont_inherit=True),module.__dict__)


class BlenderHostError(ValueError):
    """The Blender scene or requested operation exceeds the host contract."""


class EpisodePrewriteRefused(BlenderHostError):
    """Exact typed common-native refusal before any assignment entry."""


class EpisodeUncertain(BlenderHostError):
    """The common episode has incomplete or invalid physical evidence."""


class _ForwardDeadlineExpired(BlenderHostError):
    def __init__(self, checked_ns):
        self.checked_ns = checked_ns
        super().__init__('Forward deadline reached before native setter entry')


PREWRITE_REFUSAL_PROTOCOL = "host-prewrite-refusal-v1-20261024"
_PREWRITE_CODE = "host_transform_unrepresentable"
_PREWRITE_REASON = "world_pivot_storage_precision_exceeded"
_READBACK_TOLERANCE_M = 1e-6
# The host source digest commits transitively to these two read-only helpers.
# Keep the public V1 capability unchanged; load only the exact checked bytes.
_READONLY_DEPENDENCY_SHA256 = {
    'episode_gateway.py': '11bddcf41f775ccb7ee8d01e8c03369258367865f2ec6e0698bd99b3507c88cb',
    'forward_deadline.py': '72c4f6e3dba0c62f624a34f19c530b712833cbab963e13bcf9ecd34bcf5aaac2',
}
_READONLY_SOURCE_LIMIT = 256 * 1024
_REFERENCE_VIEW_SHA256 = '4680b2c52be8494a59f53283cd2294e066cdfd9de36b062fcf7e5c9d016d4265'
_RAW_MESH_SHA256 = 'a9c50cdf2141158a2eff16a5827581cbae5e506a8e40f64b236f4ee676752d5d'
_PATCH_FOCUS_SHA256 = 'cd54ed3f2ea100b5cc7662a30523c5f6548c4315d73dc4047c3d93d337964bc8'
_NONPLANAR_FOCUS_SHA256 = 'fad0fd0d5eebebf7f6de907cb74005777b442538998867a342d3e0b218e41c02'


def _hex_string(value, length):
    return (isinstance(value, str) and len(value) == length
            and all(character in "0123456789abcdef" for character in value))


def _binary32_nearest(value):
    return struct.unpack("!f", struct.pack("!f", value))[0]


def _binary32_closest_world(world, scale):
    """Check nearest binary32 and its neighbours in actual world units.

    The division and world multiplication may each round in binary64. Adjacent
    storage values keep that rounding from turning a threshold case into a
    false impossibility claim. All arithmetic matches captured pivot units.
    """
    requested, nearest, errors = [], [], []
    for coordinate in world:
        host_units = coordinate / scale
        rounded = _binary32_nearest(host_units)
        if not math.isfinite(host_units) or not math.isfinite(rounded):
            raise ValueError("No bounded binary32 precision proof")
        bits = struct.unpack("!I", struct.pack("!f", rounded))[0]
        if rounded == 0:
            neighbours = [rounded, struct.unpack("!f", struct.pack("!I", 1))[0],
                          struct.unpack("!f", struct.pack("!I", 0x80000001))[0]]
        else:
            neighbours = [struct.unpack("!f", struct.pack("!I", value))[0]
                          for value in (bits, bits - 1, bits + 1)]
        candidates = [(value, abs(value * scale - coordinate)) for value in neighbours
                      if math.isfinite(value) and math.isfinite(value * scale)]
        if not candidates:
            raise ValueError("No finite binary32 pivot candidate")
        closest, error = min(candidates, key=lambda item: (item[1], abs(item[0] - rounded)))
        requested.append(host_units); nearest.append(closest); errors.append(error)
    return requested, nearest, errors


def validate_prewrite_refusal(value, *, action, expected_revision,
                             expected_fingerprint, request_nonce):
    """Accept only a complete, current invocation's narrowly scoped refusal.

    This is a trusted-host protocol, not proof supplied by an agent. A matching
    transport envelope is still required at each remote bridge. Unknown or
    malformed results must retain the ordinary uncertain-mutation path.
    """
    if (type(value) is not dict or set(value) != {"status", "rejection"}
            or value["status"] != "rejected_before_mutation"):
        raise ValueError("Invalid prewrite refusal envelope")
    refusal = value["rejection"]
    fields = {"contract_revision", "source", "code", "request_nonce", "expected_revision",
              "scene_revision", "expected_fingerprint", "scene_fingerprint", "action_sha256",
              "focal_id", "mutation_started", "scene_unchanged", "reason_codes", "precision"}
    if type(refusal) is not dict or set(refusal) != fields:
        raise ValueError("Invalid prewrite refusal fields")
    if (not _hex_string(request_nonce, 32) or not _hex_string(expected_fingerprint, 64)
            or not isinstance(expected_revision, str) or not expected_revision
            or not isinstance(action, dict)):
        raise ValueError("A prewrite refusal needs fresh action and scene bindings")
    if (refusal["contract_revision"] != PREWRITE_REFUSAL_PROTOCOL
            or refusal["source"] != "blender_scene_host" or refusal["code"] != _PREWRITE_CODE
            or refusal["request_nonce"] != request_nonce
            or refusal["expected_revision"] != expected_revision
            or refusal["scene_revision"] != expected_revision
            or refusal["expected_fingerprint"] != expected_fingerprint
            or refusal["scene_fingerprint"] != expected_fingerprint
            or refusal["action_sha256"] != _digest(action)
            or refusal["focal_id"] != action.get("focal_id")
            or refusal["mutation_started"] is not False or refusal["scene_unchanged"] is not True
            or refusal["reason_codes"] != [_PREWRITE_REASON]):
        raise ValueError("Prewrite refusal does not match this action and scene")
    precision = refusal["precision"]
    precision_fields = {"scope", "storage_kind", "coordinate_tolerance_m", "unit_scale_m",
                        "requested_translation_host_units", "nearest_translation_host_units",
                        "before_pivot_world_m", "requested_pivot_world_m", "nearest_pivot_world_m", "absolute_error_m",
                        "exceeded_axes", "preflight_authorizes_execution"}
    if (type(precision) is not dict or set(precision) != precision_fields
            or precision["scope"] != "world_pivot_translation_only"
            or precision["storage_kind"] != "mathutils_matrix_binary32"
            or type(precision["coordinate_tolerance_m"]) is not float
            or precision["coordinate_tolerance_m"] != _READBACK_TOLERANCE_M
            or precision["preflight_authorizes_execution"] is not False):
        raise ValueError("Invalid prewrite precision contract")
    scale = precision["unit_scale_m"]
    if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid prewrite unit scale")
    vectors = {}
    for key in ("requested_translation_host_units", "nearest_translation_host_units",
                "before_pivot_world_m", "requested_pivot_world_m", "nearest_pivot_world_m", "absolute_error_m"):
        values = precision[key]
        if (type(values) is not list or len(values) != 3
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in values)):
            raise ValueError("Invalid prewrite precision vector")
        vectors[key] = values
    try:
        translation = _vector(action.get("translation", [0, 0, 0]), "translation")
        expected_world = [vectors["before_pivot_world_m"][i] + translation[i] for i in range(3)]
        requested, rounded, errors = _binary32_closest_world(expected_world, scale)
    except (OverflowError, ValueError, struct.error) as exc:
        raise ValueError("Unbounded prewrite precision proof") from exc
    exceeded = [i for i in range(3) if errors[i] > _READBACK_TOLERANCE_M]
    if (vectors["requested_translation_host_units"] != requested
            or vectors["nearest_translation_host_units"] != rounded or vectors["absolute_error_m"] != errors
            or vectors["requested_pivot_world_m"] != expected_world
            or vectors["nearest_pivot_world_m"] != [x * scale for x in rounded]
            or not exceeded or type(precision["exceeded_axes"]) is not list
            or any(type(i) is not int for i in precision["exceeded_axes"])
            or precision["exceeded_axes"] != exceeded):
        raise ValueError("Prewrite precision proof is inconsistent")
    # JSON roundtrip provides a bounded, independent value and rejects NaN.
    return json.loads(json.dumps(refusal, allow_nan=False))


def _bounds_midpoint(low, high):
    total = low + high
    return total / 2 if math.isfinite(total) else low / 2 + high / 2


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _same_rna(left, right):
    """Blender can return different Python wrappers for the same RNA datablock."""
    if left is right:
        return True
    if left is None or right is None:
        return False
    try:
        if hasattr(left, "as_pointer") and hasattr(right, "as_pointer"):
            return left.as_pointer() == right.as_pointer()
    except ReferenceError:
        # Undo/file load can leave an old Python wrapper around a freed ID.
        return False
    return False


def _scene_residency_module():
    """The bridge may preload this standalone helper from its source snapshot."""
    import sys
    import types
    from pathlib import Path
    source=Path(__file__).resolve().with_name('scene_residency.py')
    name='_human_eye_scene_residency'
    module=sys.modules.get(name)
    if module is not None and Path(getattr(module,'__file__','')).resolve()==source:
        return module
    module=types.ModuleType(name);module.__file__=str(source)
    _exec_source_snapshot(module,source);sys.modules[name]=module
    return module


def _acquisition_bounds(corners, matrix, scale):
    """Outward binary64 affine interval; unknown never excludes geometry.

    The local box must be Blender's evaluated box for the restricted static
    triangle mesh, not a model-supplied estimate. Every product/add/scale is
    widened, covering both exact affine coordinates and _capture's operation
    sequence. This proves arithmetic enclosure, not the Blender API premise.
    """
    try:
        if len(corners) != 8:
            return None
        points = [tuple(float(p[k]) for k in range(3)) for p in corners]
        if any(not math.isfinite(v) for p in points for v in p) or all(p == (-1., -1., -1.) for p in points):
            return None
        low = [min(p[k] for p in points) for k in range(3)]
        high = [max(p[k] for p in points) for k in range(3)]
        expected = {(x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])}
        if set(points) != expected:
            return None
        lower, upper = [], []
        for r in range(3):
            lo = hi = 0.
            for c in range(3):
                products = matrix[r][c] * low[c], matrix[r][c] * high[c]
                lo = math.nextafter(lo + math.nextafter(min(products), -math.inf), -math.inf)
                hi = math.nextafter(hi + math.nextafter(max(products), math.inf), math.inf)
            lo = math.nextafter(math.nextafter(lo + matrix[r][3], -math.inf) * scale, -math.inf)
            hi = math.nextafter(math.nextafter(hi + matrix[r][3], math.inf) * scale, math.inf)
            if not math.isfinite(lo) or not math.isfinite(hi):
                return None
            lower.append(lo)
            upper.append(hi)
        return [lower, upper]
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _acquisition_lower(left, right):
    if left is None or right is None:
        return 0.
    gap = max(0., *(math.nextafter(left[0][k] - right[1][k], -math.inf) for k in range(3)),
                   *(math.nextafter(right[0][k] - left[1][k], -math.inf) for k in range(3)))
    return gap if math.isfinite(gap) else 0.


def _acquisition_upper(left, right):
    """L1 distance upper bound between actual captured triangle vertices."""
    if left is None or right is None:
        return math.inf
    total = 0.
    for a, b in zip(left, right):
        if a != b:
            delta = math.nextafter(abs(a - b), math.inf)
            total = math.nextafter(total + delta, math.inf)
    return total


def _acquisition_witness(data, matrix, scale):
    """Read three vertices of one real triangle; never sample vertex zero alone."""
    from fractions import Fraction
    try:
        polygon = data.polygons[0]
        start, total = polygon.loop_start, polygon.loop_total
        if (type(start) is not int or type(total) is not int or total != 3
                or start < 0 or start + 3 > len(data.loops)):
            return None
        face = [data.loops[start + offset].vertex_index for offset in range(3)]
        if any(type(i) is not int or not 0 <= i < len(data.vertices) for i in face):
            return None
        points = []
        for index in face:
            point = [float(data.vertices[index].co[k]) for k in range(3)]
            world = [(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale for r in range(3)]
            if any(not math.isfinite(v) for v in world):
                return None
            points.append(world)
        edges = [[Fraction.from_float(points[j][k]) - Fraction.from_float(points[0][k])
                  for k in range(3)] for j in (1, 2)]
        if not any(edges[0][i] * edges[1][j] != edges[0][j] * edges[1][i] for i, j in ((0, 1), (0, 2), (1, 2))):
            return None
        return {'point_world_m': points[0], 'triangle_vertex_indices': face, 'triangle_world_m': points}
    except (AttributeError, TypeError, ValueError, IndexError, OverflowError, RuntimeError):
        return None


def _acquisition_validate_triangles(data, *, check_coordinates, checkpoint, object_id):
    """Validate references before exclusion or native triangle expansion.

    The directory already bounds scene counts. Excluded meshes also need
    finite referenced coordinates; retained meshes reuse capture's coordinate
    checks. No mesh edits, geometric qualification or bounds recalculation.
    """
    checkpoint()
    vertices, polygons, loops = data.vertices, data.polygons, data.loops
    vertex_count, loop_count = len(vertices), len(loops)
    seen = bytearray(vertex_count) if check_coordinates else None
    for ordinal, polygon in enumerate(polygons):
        if ordinal % 256 == 0:
            checkpoint()
        try:
            start, total = polygon.loop_start, polygon.loop_total
        except (AttributeError, TypeError, ValueError) as exc:
            raise BlenderHostError('acquisition_invalid_triangle_structure:' + object_id) from exc
        if (type(start) is not int or type(total) is not int or total != 3
                or start < 0 or start + total > loop_count):
            raise BlenderHostError('acquisition_invalid_triangle_structure:' + object_id)
        for offset in range(3):
            try:
                index = loops[start + offset].vertex_index
            except (AttributeError, IndexError, TypeError, ValueError) as exc:
                raise BlenderHostError('acquisition_invalid_triangle_indices:' + object_id) from exc
            if type(index) is not int or not 0 <= index < vertex_count:
                raise BlenderHostError('acquisition_invalid_triangle_indices:' + object_id)
            if seen is not None:
                seen[index] = 1
    if seen is not None:
        # Complete index validation above precedes any coordinate dereference.
        for index, referenced in enumerate(seen):
            if index % 256 == 0:
                checkpoint()
            if referenced:
                try:
                    coordinate = vertices[index].co
                    finite = all(math.isfinite(float(coordinate[k])) for k in range(3))
                except (AttributeError, IndexError, TypeError, ValueError, OverflowError) as exc:
                    raise BlenderHostError('acquisition_nonfinite_referenced_vertex:' + object_id) from exc
                if not finite:
                    raise BlenderHostError('acquisition_nonfinite_referenced_vertex:' + object_id)
    checkpoint()


def _acquisition_vertices(vertices, checkpoint):
    for index, vertex in enumerate(vertices):
        if index % 128 == 0:
            checkpoint()
        yield vertex


def _scan_local_summary(local, faces, checkpoint):
    """Exact dyadic local eligibility; the cache retains only small summaries."""
    from fractions import Fraction as F
    rational = []
    for ordinal, point in enumerate(local):
        if ordinal % 128 == 0:
            checkpoint()
        rational.append(tuple(F(value) for value in point))
    minimum_cross = None
    maximum_edge = F(0)
    for ordinal, face in enumerate(faces):
        if ordinal % 128 == 0:
            checkpoint()
        a, b, c = (rational[index] for index in face)
        first = tuple(b[k] - a[k] for k in range(3))
        second = tuple(c[k] - a[k] for k in range(3))
        cross = _cross(first, second)
        magnitude = max(abs(value) for value in cross)
        if not magnitude:
            raise BlenderHostError('degenerate_local_triangle_source')
        minimum_cross = magnitude if minimum_cross is None else min(minimum_cross, magnitude)
        maximum_edge = max(maximum_edge, *(abs(value) for value in first + second),
                           *(abs(c[k] - b[k]) for k in range(3)))
    checkpoint()
    return dict(min_cross_inf=minimum_cross, max_edge_inf=maximum_edge,
                local_abs_max=tuple(max(abs(point[k]) for point in rational) for k in range(3)))


def _scan_world_precision(summary, matrix, scale):
    """Certify every captured triangle stays finite and nondegenerate.

    The local cross/edge summary covers all faces. Exact rational error bounds
    follow capture's binary64 product, sum, translation and scale operations.
    Failure is unresolved precision, not a claim of definite degeneracy.
    """
    from fractions import Fraction as F
    unit, underflow = F(1, 2**52), F(1, 2**1074)
    finite_limit = F(float.fromhex('0x1.fffffffffffffp+1023'))
    physical_scale = F(scale)
    linear = [[F(matrix[r][c]) * physical_scale for c in range(3)] for r in range(3)]
    determinant = sum(linear[0][c] * (
        linear[1][(c+1)%3] * linear[2][(c+2)%3]
        - linear[1][(c+2)%3] * linear[2][(c+1)%3]) for c in range(3))
    transpose_norm = max(sum(abs(linear[r][c]) for r in range(3)) for c in range(3))
    if not determinant or not transpose_norm:
        return False
    cross_lower = abs(determinant) * summary['min_cross_inf'] / transpose_norm
    edge_upper = max(sum(abs(value) for value in row) for row in linear) * summary['max_edge_inf']
    delta = F(0)
    for row in matrix[:3]:
        amplitude = error = F(0)
        for coefficient, local_maximum in zip(row[:3], summary['local_abs_max']):
            product = abs(F(coefficient)) * local_maximum
            product_error = unit * product + underflow
            product_amplitude = product + product_error
            operation_error = unit * (amplitude + product_amplitude) + underflow
            amplitude += product_amplitude + operation_error
            error += product_error + operation_error
            if product_amplitude > finite_limit or amplitude > finite_limit:
                return False
        operation_error = unit * (amplitude + abs(F(row[3]))) + underflow
        amplitude += abs(F(row[3])) + operation_error
        error += operation_error
        scale_error = unit * amplitude * physical_scale + underflow
        if amplitude > finite_limit or amplitude * physical_scale + scale_error > finite_limit:
            return False
        delta = max(delta, error * physical_scale + scale_error)
    return cross_lower > 8 * delta * edge_upper + 8 * delta * delta


def _vector(value, name):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(isinstance(x, (bool, str)) or not isinstance(x, (int, float))
                   or not math.isfinite(x) for x in value)):
        raise BlenderHostError(name + " must be a finite numeric 3-vector")
    return [float(x) for x in value]


def _matrix(value):
    try:
        rows = [[float(value[i][j]) for j in range(4)] for i in range(4)]
    except (TypeError, IndexError, ValueError) as exc:
        raise BlenderHostError("Invalid world matrix") from exc
    if any(not math.isfinite(x) for row in rows for x in row):
        raise BlenderHostError("World matrix contains a nonfinite value")
    if any(abs(rows[3][i] - (1 if i == 3 else 0)) > 1e-7 for i in range(4)):
        raise BlenderHostError("World matrix must be affine")
    return rows


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _norm(a):
    return math.sqrt(_dot(a, a))


def _frame(matrix):
    """World-axis row basis; even an ambiguous export stays a proper rotation."""
    columns = [[matrix[r][c] for r in range(3)] for c in range(3)]
    lengths = [_norm(c) for c in columns]
    reason = "blender_world_rotation"
    if min(lengths) <= 1e-12:
        return [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], "ambiguous", "singular_world_transform", lengths
    normalized = [[x / length for x in c] for c, length in zip(columns, lengths)]
    if _dot(_cross(normalized[0], normalized[1]), normalized[2]) < 0:
        reason = "mirrored_world_transform"
    elif max(abs(_dot(normalized[i], normalized[j])) for i, j in ((0, 1), (0, 2), (1, 2))) > 1e-6:
        reason = "sheared_world_transform"
    first = normalized[0]
    projection = _dot(first, normalized[1])
    second = [normalized[1][i] - projection * first[i] for i in range(3)]
    length = _norm(second)
    if length <= 1e-12:
        return [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], "ambiguous", "singular_world_transform", lengths
    second = [x / length for x in second]
    return [first, second, _cross(first, second)], ("explicit" if reason == "blender_world_rotation" else "ambiguous"), reason, lengths


def _euler_xyz(degrees):
    """World XYZ extrinsic rotation, exactly Rz @ Ry @ Rx in the engine API."""
    rx, ry, rz = (math.radians(x) for x in degrees)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    return [[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
            [-sy, cy * sx, cy * cx]]


class BlenderSceneHost:
    """Capture world-space metres and apply a revision-checked delta SE(3).

    IDs derive from the Blender object name and linked-library path. They remain
    stable across captures and processes, but an object rename is a new identity.
    ``object_names`` is an assertion of complete mesh coverage, not a filter that
    silently removes potential collision objects. Hidden meshes are included if
    evaluated; unavailable evaluation blocks the entire snapshot.
    """

    prewrite_refusal_protocol = PREWRITE_REFUSAL_PROTOCOL
    identity_metadata_protocol = 'host-identity-v1-20261026'
    forward_deadline_protocol = 'owned-qpc-forward-deadline-v1-20261030'
    common_native_protocol = 'owned-common-native-v1-20261031'
    readonly_native_evidence_protocol = 'owned-readonly-native-evidence-v1-20261031'
    native_render_audit_protocol = 'owned-native-render-audit-v1-20261031'
    native_multiscale_protocol = 'owned-native-multiscale-v1-20261031'
    native_observation_protocol = 'typed-native-readonly-observation-v1-20261031'

    def __init__(self, bpy_module=None, scene=None, view_layer=None, object_names=None,
                 execution_metadata=False, identity_metadata=False):
        if bpy_module is None:
            try:
                import bpy as bpy_module
            except ImportError as exc:
                raise BlenderHostError("This operation requires Blender's Python runtime") from exc
        self.bpy = bpy_module
        self._default_scene = scene is None
        self._default_view_layer = view_layer is None
        self.scene = scene if scene is not None else bpy_module.context.scene
        self.view_layer = view_layer if view_layer is not None else bpy_module.context.view_layer
        layers = getattr(self.scene, "view_layers", None)
        if layers is not None and all(not _same_rna(layer, self.view_layer) for layer in layers):
            raise BlenderHostError("The view layer does not belong to the supplied scene")
        if object_names is not None and (not isinstance(object_names, (list, tuple, set))
                or any(not isinstance(name, str) or not name for name in object_names)):
            raise BlenderHostError("object_names must contain nonempty object names")
        self.object_names = None if object_names is None else frozenset(object_names)
        if type(execution_metadata) is not bool:
            raise BlenderHostError("execution_metadata must be boolean")
        # Old long-running clients load this file on every RPC. Preserve their
        # captured-scene fingerprint shape until they reload the v1 transport.
        self.execution_metadata = execution_metadata
        if type(identity_metadata) is not bool:
            raise BlenderHostError('identity_metadata must be boolean')
        self.identity_metadata = identity_metadata
        self._lock = threading.RLock()
        self._residency_module = self._residency = None
        self._residency_stats = dict(to_mesh=0, triangulations=0, resource_builds=0,
            world_transforms=0, capture_cache_hits=0, nearest_cache_hits=0,
            directory_builds=0, directory_vertices=0, directory_cache_hits=0,
            scan_cache_hits=0, source_qualification_vertices=0,
            source_qualification_faces=0, source_qualification_cache_hits=0,
            resource_vertices_read=0, resource_faces_read=0, world_vertices_transformed=0,
            scan_directory_objects=0, scan_bound_tests=0)

    @staticmethod
    def _main_thread():
        if threading.current_thread() is not threading.main_thread():
            raise BlenderHostError("Blender host operations require the main thread")

    @staticmethod
    def object_id(obj):
        library = getattr(obj, "library", None)
        identity = [str(getattr(library, "filepath", "")), str(getattr(obj, "name_full", obj.name))]
        return "blender:" + _digest(identity)

    def _depsgraph(self):
        try:
            return self._current_depsgraph()
        except ReferenceError as exc:
            if not self._default_scene:
                raise BlenderHostError('The explicitly supplied scene or view layer is no longer available') from exc
            self.scene=self.bpy.context.scene
            self.view_layer=self.bpy.context.view_layer
            if self._residency is not None:self._residency.reset()
            return self._current_depsgraph()

    def _current_depsgraph(self):
        if self._default_scene and not _same_rna(self.bpy.context.scene,self.scene):
            self.scene=self.bpy.context.scene
            self.view_layer=self.bpy.context.view_layer
        elif self._default_view_layer and _same_rna(self.bpy.context.scene,self.scene):
            self.view_layer=self.bpy.context.view_layer
        # Explicit scenes remain pinned, but invalid RNA must be a clear refusal.
        if not self._default_scene:
            getattr(self.scene,'name',None)
        self.view_layer.update()
        graph = getattr(self.view_layer, "depsgraph", None)
        if graph is None:
            if not _same_rna(self.bpy.context.scene, self.scene):
                raise BlenderHostError("The supplied scene is not the active Blender scene")
            graph = self.bpy.context.evaluated_depsgraph_get()
        graph_scene = getattr(graph, "scene_eval", None)
        if graph_scene is not None and not _same_rna(getattr(graph_scene, "original", graph_scene), self.scene):
            raise BlenderHostError("The dependency graph belongs to a different scene")
        return graph

    def close_residency(self):
        if self._residency is not None:self._residency.close()

    def residency_work(self):
        return dict(self._residency_stats, enabled=self._residency is not None and self._residency.enabled,
                    resident_resources=len(self._residency.resources) if self._residency is not None else 0)

    def _sync_residency(self, graph, scale, *, _surface_scan=False):
        if self._residency is None:
            self._residency_module=_scene_residency_module()
            self._residency=self._residency_module.SceneResidency(self.bpy)
        state=self._residency
        if not state.enabled:return False
        rows=[];live=set();by_id={}
        ident=self._residency_module.identity
        for obj in self.scene.objects:
            key=ident(obj);data=getattr(obj,'data',None)
            live.add(key)
            live.add(ident(data))
            if getattr(obj,'type',None)=='MESH':by_id[self.object_id(obj)]=key
            try:
                matrix = _matrix(obj.matrix_world)
            except BlenderHostError:
                if not _surface_scan:
                    raise
                matrix = 'invalid_world_matrix'
            row = (key,ident(data),str(obj.name),str(getattr(obj,'name_full',obj.name)),
                getattr(obj,'type',None),matrix,self._guard_description(obj),
                list(getattr(obj,'color',())),getattr(obj,'hide_viewport',None),getattr(obj,'hide_render',None),
                len(getattr(data,'vertices',())),len(getattr(data,'polygons',())))
            if _surface_scan:
                row += (getattr(obj, 'instance_type', 'NONE'), bool(getattr(obj, 'is_instancer', False)))
            rows.append(row)
        namespace=getattr(getattr(self.bpy,'app',None),'driver_namespace',None)
        namespace_marker=None
        if isinstance(namespace,dict):
            key='_human_eye_residency_document_v1'
            if key not in namespace:namespace[key]=uuid.uuid4().hex
            namespace_marker=namespace[key]
        context=(ident(self.scene),ident(self.view_layer),namespace_marker,
                 str(getattr(getattr(self.bpy,'data',None),'filepath','')))
        signature=(rows,scale,getattr(self.scene.unit_settings,'system',None),
            getattr(self.scene.unit_settings,'length_unit',None),int(getattr(self.scene,'frame_current',0)),
            float(getattr(self.scene,'frame_subframe',0)),
            ident(getattr(getattr(self.view_layer,'objects',None),'active',None)))
        if _surface_scan:
            signature += (any(bool(getattr(item, 'is_instance', False))
                              for item in getattr(graph, 'object_instances', ())),)
        state.sync(context,signature,live);state.by_object_id=by_id
        state.wire={oid:entry for oid,entry in state.wire.items() if oid in by_id}
        return True

    def _resource_stamp(self, obj):
        state = self._residency
        ident = self._residency_module.identity
        key, data = ident(obj), getattr(obj, 'data', None)
        guards = self._guard_description(obj)
        dynamic = bool(guards['modifiers'] or guards['animation'] or guards['data_animation'] or guards['shape_keys'])
        geometry_guards = dict(guards, parent=ident(getattr(obj, 'parent', None)),
                              children=sorted(ident(child) for child in getattr(obj, 'children', ())))
        return (ident(data), state.dirty.get(key, 0), state.dirty.get(ident(data), 0), geometry_guards,
                int(getattr(self.scene, 'frame_current', 0)) if dynamic else None,
                float(getattr(self.scene, 'frame_subframe', 0)) if dynamic else None)

    def _resident_capture(self, graph, scale, objects, task_selection, task_identity, acquisition,
                          acquisition_scope, prepared_local):
        state=self._residency
        selection_key=_digest([acquisition_scope if acquisition is not None else
            'task' if task_selection is not None else 'scene',
            task_selection['selectors'] if task_selection is not None else [self.object_id(o) for o in objects]])
        cached=state.captures.get(selection_key)
        if cached is not None:
            self._residency_stats['capture_cache_hits']+=1
            return cached
        meshes=[];vertex_count=face_count=0
        active=getattr(getattr(self.view_layer,'objects',None),'active',None)
        ident=self._residency_module.identity
        selected_keys={ident(obj) for obj in objects}
        for ordinal,obj in enumerate(objects,1):
            checkpoint=acquisition[4] if acquisition is not None else lambda:None
            checkpoint()
            evaluated=obj.evaluated_get(graph) if acquisition is None else acquisition[3][self.object_id(obj)]
            if not bool(getattr(evaluated,'is_evaluated',True)):
                raise BlenderHostError('Mesh is not evaluated in the current view layer: '+obj.name)
            matrix=_matrix(evaluated.matrix_world);key=ident(obj)
            stamp=self._resource_stamp(obj)
            resource=state.resources.get(key)
            if resource is None or resource['stamp']!=stamp:
                temporary=None
                try:
                    prepared = prepared_local.get(self.object_id(obj)) if prepared_local is not None else None
                    if prepared is None:
                        self._residency_stats['to_mesh']+=1;temporary=evaluated.to_mesh()
                        if temporary is None:raise BlenderHostError('Evaluated mesh is unavailable: '+obj.name)
                        if len(temporary.vertices)>500000:raise BlenderHostError('Scene geometry budget exceeded')
                        self._residency_stats['triangulations']+=1;temporary.calc_loop_triangles()
                        if len(temporary.loop_triangles)>1000000:raise BlenderHostError('Scene geometry budget exceeded')
                        local=tuple(tuple(float(v.co[i]) for i in range(3)) for v in
                                    _acquisition_vertices(temporary.vertices,checkpoint))
                        faces=tuple(tuple(int(i) for i in triangle.vertices) for triangle in temporary.loop_triangles)
                        self._residency_stats['resource_vertices_read'] += len(local)
                        self._residency_stats['resource_faces_read'] += len(faces)
                    else:
                        local, faces = prepared
                    if (len(local)<3 or not faces or any(not math.isfinite(x) for p in local for x in p)
                            or any(len(f)!=3 or min(f)<0 or max(f)>=len(local) for f in faces)):
                        raise BlenderHostError('A mesh requires valid evaluated triangles: '+obj.name)
                    edges=tuple(sorted({tuple(sorted((f[a],f[b]))) for f in faces for a,b in ((0,1),(1,2),(2,0))}))
                    remaining=[k for k in state.resources if k!=key]
                    def cache_exceeded():
                        return (len(remaining)>=256 or len(local)+sum(len(state.resources[k]['vertices_local']) for k in remaining)>500000
                                or len(faces)+sum(len(state.resources[k]['faces']) for k in remaining)>1000000)
                    while cache_exceeded():
                        evict=next((k for k in remaining if k not in selected_keys),None)
                        if evict is None:raise BlenderHostError('Scene geometry budget exceeded')
                        remaining.remove(evict);old_resource=state.resources.pop(evict)
                        state.wire={oid:item for oid,item in state.wire.items() if item[0] is not old_resource}
                        state.captures.clear();state.nearest.clear()
                    state.resource_serial+=1
                    resource=dict(resource_id='mesh:'+str(key),revision=state.resource_serial,
                        stamp=copy.deepcopy(stamp),vertices_local=local,faces=faces,edges=edges,pose=None,mesh=None)
                    state.resources[key]=resource;self._residency_stats['resource_builds']+=1
                finally:
                    if temporary is not None:evaluated.to_mesh_clear()
            vertex_count+=len(resource['vertices_local']);face_count+=len(resource['faces'])
            if vertex_count>500000 or face_count>1000000:raise BlenderHostError('Scene geometry budget exceeded')
            color=[int(round(min(1.,max(0.,float(c)))*255)) for c in list(getattr(obj,'color',(0.5,0.5,0.5,1)))[:3]]
            if len(color)!=3:raise BlenderHostError('Object color must have three components')
            # World geometry depends on the evaluated resource and physical
            # pose. Names, selection ordinals, active state and colors must
            # refresh metadata without repeating the vertex forward map.
            pose=(matrix,scale)
            if resource['pose']!=pose:
                vertices=[[(sum(matrix[r][c]*p[c] for c in range(3))+matrix[r][3])*scale for r in range(3)]
                          for p in resource['vertices_local']]
                if any(not math.isfinite(v) for p in vertices for v in p):raise BlenderHostError('Nonfinite evaluated geometry: '+obj.name)
                axes,confidence,reason,_=_frame(matrix)
                resource['mesh']=dict(vertices=vertices,
                    faces=[list(f) for f in resource['faces']],edges=[list(e) for e in resource['edges']],
                    local_axes=axes,pivot_world=[matrix[r][3]*scale for r in range(3)],
                    axes_source='host',axes_confidence=confidence,axes_reason=reason)
                resource['pose']=copy.deepcopy(pose);self._residency_stats['world_transforms']+=1
                self._residency_stats['world_vertices_transformed'] += len(resource['vertices_local'])
            state.wire[self.object_id(obj)]=(resource,copy.deepcopy(matrix),scale)
            # Copy the small metadata dict; geometry remains private and is
            # detached once at the public capture boundary. Older selections
            # retain their own labels when another selection reuses a resource.
            meshes.append(dict(resource['mesh'],object_id=self.object_id(obj),
                mark_label='#B%04d'%ordinal,name=str(obj.name),
                is_focal_target=_same_rna(obj,active),color_rgb=color))
        scene=dict(unit='m',coordinate_frame='world',source='blender',meshes=meshes)
        if task_selection is not None:
            scene.update(capture_scope='selected_objects',task_selection=task_selection,host_identity=task_identity)
        elif acquisition is not None:scene.update(capture_scope=acquisition_scope,execution_authority=False)
        elif self.execution_metadata:scene['host_execution']=self._execution_status(objects)
        if task_selection is None and self.identity_metadata:
            identity=self._identity_metadata(objects,capture_scope=acquisition_scope) if acquisition is not None else self._identity_metadata(objects)
            if identity is not None:scene['host_identity']=identity
        if task_selection is None:
            scene['revision']='blender:'+_digest(dict(scene=scene,scale_length=scale,
                frame=int(getattr(self.scene,'frame_current',0)),guards=[[self.object_id(o),self._guard_description(o)] for o in objects]))
        else:scene['revision']='blender:'+_digest(dict(scene=scene,scale_length=scale))
        if len(state.captures)>=8:state.captures.clear()
        state.captures[selection_key]=scene
        return scene

    def _capture_state(self, scene, selection_key):
        result=copy.deepcopy(scene)
        if self._residency is not None and self._residency.enabled:result['capture_state']=self._residency.token(selection_key)
        return result

    def capture_delta(self, capture, known=None):
        scene=capture.get('capture',capture);token=scene.get('capture_state')
        if token is None or self._residency is None or token!=self._residency.token(token.get('selection_key','')):
            return copy.deepcopy(capture)
        return self._residency_module.encode_capture(capture,known,self._residency.wire)

    def _objects(self, graph, *, _surface_scan=False):
        objects = list(self.scene.objects)
        if _surface_scan:
            meshes = sorted((obj for obj in objects if getattr(obj, 'type', None) == 'MESH'), key=self.object_id)
            if len(meshes) > 256:
                raise BlenderHostError('surface_scan_scene_object_budget')
            if self.object_names is not None and self.object_names != frozenset(obj.name for obj in meshes):
                raise BlenderHostError('object_names must cover every scene mesh, including hidden meshes')
            return meshes
        unsupported = {"CURVE", "SURFACE", "FONT", "META", "VOLUME", "POINTCLOUD", "CURVES", "GREASEPENCIL", "GPENCIL"}
        for obj in objects:
            if getattr(obj, "type", None) in unsupported:
                raise BlenderHostError("Unsupported scene geometry: " + obj.name)
            if getattr(obj, "instance_type", "NONE") != "NONE" or bool(getattr(obj, "is_instancer", False)):
                raise BlenderHostError("Instanced scene geometry is unsupported: " + obj.name)
            if any(getattr(modifier, "type", None) == "NODES" for modifier in getattr(obj, "modifiers", ())):
                raise BlenderHostError("Geometry-node instances cannot be excluded: " + obj.name)
        if any(bool(getattr(instance, "is_instance", False)) for instance in getattr(graph, "object_instances", ())):
            raise BlenderHostError("Evaluated instances are not supported")
        meshes = sorted((obj for obj in objects if getattr(obj, "type", None) == "MESH"), key=self.object_id)
        if not 1 <= len(meshes) <= 256:
            raise BlenderHostError("The scene must contain 1..256 mesh objects")
        if self.object_names is not None and self.object_names != frozenset(obj.name for obj in meshes):
            raise BlenderHostError("object_names must cover every scene mesh, including hidden meshes")
        return meshes

    def _scale(self):
        scale = float(self.scene.unit_settings.scale_length)
        if not math.isfinite(scale) or scale <= 0:
            raise BlenderHostError("Scene unit scale_length must be positive and finite")
        return scale

    @staticmethod
    def _guard_description(obj):
        return {"parent": getattr(getattr(obj, "parent", None), "name", None),
                "children": sorted(child.name for child in getattr(obj, "children", ())),
                "constraints": len(getattr(obj, "constraints", ())),
                "modifiers": [(str(getattr(m, "name", "")), str(getattr(m, "type", ""))) for m in getattr(obj, "modifiers", ())],
                "animation": getattr(obj, "animation_data", None) is not None,
                "data_animation": getattr(getattr(obj, "data", None), "animation_data", None) is not None,
                "rigid_body": getattr(obj, "rigid_body", None) is not None,
                "rigid_body_constraint": getattr(obj, "rigid_body_constraint", None) is not None,
                "shape_keys": getattr(getattr(obj, "data", None), "shape_keys", None) is not None,
                "linked": getattr(obj, "library", None) is not None,
                "edit_mode": getattr(obj, "mode", "OBJECT") != "OBJECT",
                "locks": [bool(v) for field in ("lock_location", "lock_rotation", "lock_scale") for v in getattr(obj, field, (False, False, False))]}

    def _execution_status(self, objects):
        """Describe the same conservative restrictions enforced before writes.

        Readable evaluated geometry is a wider contract than editable geometry.
        Publish this distinction in the captured, revision-bound scene so an
        ordinary unsupported object does not become an uncertain write attempt.
        """
        reasons = []
        for obj in objects:
            guards = self._guard_description(obj)
            conditions = {
                "parented_object": guards["parent"] is not None,
                "object_has_children": bool(guards["children"]),
                "constraints_present": bool(guards["constraints"]),
                "modifiers_present": bool(guards["modifiers"]),
                "animation_present": guards["animation"] or guards["data_animation"],
                "rigid_body_present": guards["rigid_body"] or guards["rigid_body_constraint"],
                "shape_keys_present": guards["shape_keys"],
                "linked_object": guards["linked"],
                "object_not_in_object_mode": guards["edit_mode"],
                "transform_locks_present": any(guards["locks"]),
            }
            _, confidence, _, lengths = _frame(_matrix(obj.matrix_world))
            conditions["nonrigid_or_nonuniform_world_frame"] = (
                confidence != "explicit" or max(lengths) - min(lengths) > 1e-6 * max(lengths))
            reasons.extend({"object_id": self.object_id(obj), "object_name": str(obj.name), "reason": reason}
                           for reason, present in conditions.items() if present)
        return {"schema_version": "1.0", "operation": "rigid_transform",
                "supported": not reasons, "scope": "independent_static_rigid_meshes", "reasons": reasons}

    def _identity_metadata(self, objects, *, capture_scope='complete_scene_meshes'):
        """Bind new goal segments to runtime IDs without editing a .blend file.

        The driver namespace is ephemeral Blender runtime storage and resets
        when a file loads. ID.session_uid is Blender's per-session incarnation,
        rather than a name. Older hosts without these facilities omit the
        optional contract; new autonomous writes must then refuse explicitly.
        """
        namespace = getattr(getattr(self.bpy, 'app', None), 'driver_namespace', None)
        scene_uid = getattr(self.scene, 'session_uid', None)
        values = [getattr(obj, 'session_uid', None) for obj in objects]
        if (not isinstance(namespace, dict) or type(scene_uid) is not int or scene_uid == 0
                or any(type(value) is not int or value == 0 for value in values)
                or len(set(values)) != len(values)):
            return None
        key = '_human_eye_document_epoch_v1'
        if key not in namespace:
            namespace[key] = uuid.uuid4().hex
        epoch = namespace[key]
        if not isinstance(epoch, str) or not _hex_string(epoch, 32):
            return None
        document = [epoch, scene_uid, str(getattr(getattr(self.bpy, 'data', None), 'filepath', ''))]
        return {'schema_version': '1.0', 'document_epoch': _digest(document),
                'object_instances': {self.object_id(obj): str(value) for obj, value in zip(objects, values)},
                'capture_scope': capture_scope}

    def _task_objects(self, selectors):
        """Bind finite selectors before expanding any selected geometry."""
        candidates = [obj for obj in self.scene.objects if getattr(obj, 'type', None) == 'MESH']
        candidate_ids = ([self.object_id(obj) for obj in candidates]
                         if any('id' in selector for selector in selectors) else None)
        selected, bindings = {}, []
        for selector in selectors:
            if 'id' in selector:
                matches = [obj for obj, object_id in zip(candidates, candidate_ids) if object_id == selector['id']]
            else:
                matches = [obj for obj in candidates if obj.name == selector['name']]
            if len(matches) != 1:
                bindings.append({'status': 'unknown', 'selector': dict(selector),
                    'reason': 'object_not_found' if not matches else 'object_name_ambiguous'})
                continue
            obj = matches[0]
            object_id = self.object_id(obj)
            selected[object_id] = obj
            bindings.append({'object_id': object_id, 'name': str(obj.name)})
        objects = [selected[object_id] for object_id in sorted(selected)]
        for obj in objects:
            if getattr(obj, 'instance_type', 'NONE') != 'NONE' or bool(getattr(obj, 'is_instancer', False)):
                raise BlenderHostError('Instanced selected geometry is unsupported: ' + obj.name)
            if any(getattr(modifier, 'type', None) == 'NODES' for modifier in getattr(obj, 'modifiers', ())):
                raise BlenderHostError('Selected geometry-node instances cannot be excluded: ' + obj.name)
        pair_reason = None
        if (len(bindings) == 2 and all('object_id' in row for row in bindings)
                and bindings[0]['object_id'] == bindings[1]['object_id']):
            pair_reason = 'pair_selectors_resolve_to_same_object'
        return objects, {'selectors': [dict(selector) for selector in selectors], 'bindings': bindings,
                         'pair_reason': pair_reason, 'candidate_count': len(candidates)}

    def _capture(self, *, _native_evidence=False, _read_only_native=False, _task_selectors=None,
                 _acquisition_context=None, _resident=False,
                 _acquisition_scope='surface_nearest_candidates', _prepared_local=None):
        if type(_native_evidence) is not bool:
            raise BlenderHostError("_native_evidence must be boolean")
        if type(_read_only_native) is not bool:
            raise BlenderHostError("_read_only_native must be boolean")
        if _native_evidence and not (self.execution_metadata and self.identity_metadata):
            raise BlenderHostError("Native evidence requires explicit execution and identity metadata")
        graph, scale = (self._depsgraph(), self._scale()) if _acquisition_context is None else _acquisition_context[:2]
        task_selection = task_identity = None
        if _acquisition_context is not None:
            if _native_evidence or _task_selectors is not None:
                raise BlenderHostError('Acquisition context cannot supply legacy evidence')
            objects = _acquisition_context[2]
        elif _task_selectors is None:
            objects = self._objects(graph)
        else:
            objects, task_selection = self._task_objects(_task_selectors)
            task_identity = self._identity_metadata(objects, capture_scope='selected_objects')
            if task_identity is None:
                raise BlenderHostError('Selected capture requires document and object instance identity')
        native_objects = [] if _native_evidence else None
        native_capability = native_identity = None
        if _native_evidence:
            native_capability = self._execution_status(objects)
            native_identity = self._identity_metadata(objects)
            if not native_capability['supported'] and not (_read_only_native and all(
                    item['reason'] == 'transform_locks_present' for item in native_capability['reasons'])):
                raise BlenderHostError("Native original-pose evidence requires independent static rigid meshes")
            if native_identity is None:
                raise BlenderHostError("Native original-pose evidence requires complete host identity")
        active = getattr(getattr(self.view_layer, "objects", None), "active", None)
        if _resident and self._sync_residency(graph,scale,_surface_scan=_acquisition_scope=='surface_scan_candidates'):
            return self._resident_capture(graph,scale,objects,task_selection,task_identity,
                                          _acquisition_context,_acquisition_scope,_prepared_local)
        meshes, vertex_count, face_count = [], 0, 0
        for ordinal, obj in enumerate(objects, 1):
            if _acquisition_context is not None:
                _acquisition_context[4]()
            evaluated = obj.evaluated_get(graph) if _acquisition_context is None else _acquisition_context[3][self.object_id(obj)]
            if not bool(getattr(evaluated, "is_evaluated", True)):
                raise BlenderHostError("Mesh is not evaluated in the current view layer: " + obj.name)
            matrix = _matrix(evaluated.matrix_world)
            if _native_evidence and _matrix(obj.matrix_world) != matrix:
                raise BlenderHostError("Native original and evaluated world matrices disagree: " + obj.name)
            temporary = None
            try:
                prepared = _prepared_local.get(self.object_id(obj)) if _prepared_local is not None else None
                if prepared is None:
                    temporary = evaluated.to_mesh()
                    if temporary is None:
                        raise BlenderHostError("Evaluated mesh is unavailable: " + obj.name)
                    temporary.calc_loop_triangles()
                    if (vertex_count + len(temporary.vertices) > 500_000
                            or face_count + len(temporary.loop_triangles) > 1_000_000):
                        raise BlenderHostError("Scene geometry budget exceeded")
                vertices = []
                evaluated_local = [] if _native_evidence else None
                vertex_source = (prepared[0] if prepared is not None else temporary.vertices if _acquisition_context is None else
                                 _acquisition_vertices(temporary.vertices, _acquisition_context[4]))
                for vertex_ordinal, vertex in enumerate(vertex_source):
                    if prepared is not None and vertex_ordinal % 128 == 0:
                        _acquisition_context[4]()
                    point = list(vertex) if prepared is not None else [float(vertex.co[i]) for i in range(3)]
                    if _native_evidence:
                        evaluated_local.append(point)
                    world = [(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale for r in range(3)]
                    if any(not math.isfinite(v) for v in world):
                        raise BlenderHostError("Nonfinite evaluated geometry: " + obj.name)
                    vertices.append(world)
                faces = ([list(face) for face in prepared[1]] if prepared is not None else
                         [[int(i) for i in triangle.vertices] for triangle in temporary.loop_triangles])
                if prepared is not None:
                    self._residency_stats['world_transforms'] += 1
                    self._residency_stats['world_vertices_transformed'] += len(vertices)
                if len(vertices) < 3 or not faces or any(len(face) != 3 or min(face) < 0 or max(face) >= len(vertices) for face in faces):
                    raise BlenderHostError("A mesh requires valid evaluated triangles: " + obj.name)
                vertex_count, face_count = vertex_count + len(vertices), face_count + len(faces)
                if vertex_count > 500_000 or face_count > 1_000_000:
                    raise BlenderHostError("Scene geometry budget exceeded")
                edges = sorted({tuple(sorted((face[a], face[b]))) for face in faces for a, b in ((0, 1), (1, 2), (2, 0))})
                axes, confidence, reason, _ = _frame(matrix)
                color = list(getattr(obj, "color", (0.5, 0.5, 0.5, 1.0)))
                color = [int(round(min(1., max(0., float(c))) * 255)) for c in color[:3]]
                if len(color) != 3:
                    raise BlenderHostError("Object color must have three components")
                if _native_evidence:
                    # A static evaluated mesh is not itself proof of the raw
                    # original mesh. Compare native storage by vertex index
                    # and polygon topology before using the same triangulation.
                    original = getattr(obj, 'data', None)
                    if (original is None or not hasattr(original, 'vertices')
                            or not hasattr(original, 'polygons') or not hasattr(temporary, 'polygons')
                            or len(original.vertices) != len(evaluated_local)):
                        raise BlenderHostError("Native original mesh data is unavailable: " + obj.name)
                    original_local = [[float(vertex.co[i]) for i in range(3)] for vertex in original.vertices]
                    if (len(original.polygons) != len(temporary.polygons)
                            or len(original.polygons) > len(faces)):
                        raise BlenderHostError("Native original polygon budget or coverage is invalid: " + obj.name)
                    if original_local != evaluated_local:
                        raise BlenderHostError("Native original and evaluated local meshes disagree: " + obj.name)
                    corners = 0
                    for raw_polygon, evaluated_polygon in zip(original.polygons, temporary.polygons):
                        raw_indices, evaluated_indices = raw_polygon.vertices, evaluated_polygon.vertices
                        corners += len(raw_indices)
                        if (len(raw_indices) < 3 or corners > 3 * len(faces)
                                or len(raw_indices) != len(evaluated_indices)
                                or any(int(a) != int(b) for a, b in zip(raw_indices, evaluated_indices))):
                            raise BlenderHostError("Native original and evaluated local meshes disagree: " + obj.name)
                    native_color = list(getattr(obj, 'color', ()))
                    if (len(native_color) != 4 or any(type(value) not in (int, float)
                            or not math.isfinite(value) for value in native_color)):
                        raise BlenderHostError("Native object color requires four finite components: " + obj.name)
                    local_metres = [[value * scale for value in point] for point in original_local]
                    matrix_metres = [row[:] for row in matrix]
                    for r in range(3):
                        matrix_metres[r][3] *= scale
                    if any(not math.isfinite(value) for point in local_metres for value in point):
                        raise BlenderHostError("Native local geometry exceeds finite metre units: " + obj.name)
                    if any(not math.isfinite(value) for row in matrix_metres for value in row):
                        raise BlenderHostError("Native world matrix exceeds finite metre units: " + obj.name)
                    native_objects.append({'object_id': self.object_id(obj), 'name': str(obj.name),
                        'local_vertices': local_metres, 'world_vertices': [point[:] for point in vertices],
                        'faces': [face[:] for face in faces], 'matrix': matrix_metres,
                        'color': [float(value) for value in native_color]})
                meshes.append({"object_id": self.object_id(obj), "mark_label": "#B%04d" % ordinal,
                               "name": str(obj.name), "is_focal_target": _same_rna(obj, active),
                               "color_rgb": color, "vertices": vertices, "faces": faces,
                               "edges": [list(edge) for edge in edges], "local_axes": axes,
                               "pivot_world": [matrix[r][3] * scale for r in range(3)],
                               "axes_source": "host", "axes_confidence": confidence,
                               "axes_reason": reason})
            finally:
                if temporary is not None:
                    evaluated.to_mesh_clear()
        scene = {"unit": "m", "coordinate_frame": "world", "source": "blender", "meshes": meshes}
        if task_selection is not None:
            scene['capture_scope'] = 'selected_objects'
            scene['task_selection'] = task_selection
            scene['host_identity'] = task_identity
        elif _acquisition_context is not None:
            scene['capture_scope'] = _acquisition_scope
            scene['execution_authority'] = False
        elif self.execution_metadata:
            scene["host_execution"] = self._execution_status(objects)
        if task_selection is None and self.identity_metadata:
            identity = self._identity_metadata(objects, capture_scope=_acquisition_scope) if _acquisition_context is not None else self._identity_metadata(objects)
            if identity is not None:
                scene['host_identity'] = identity
        # Guard changes must invalidate approvals even if displayed geometry did
        # not move. The digest is deterministic across bridge process launches.
        if task_selection is None:
            scene["revision"] = "blender:" + _digest({"scene": scene, "scale_length": scale,
                    "frame": int(getattr(self.scene, "frame_current", 0)),
                    "guards": [[self.object_id(obj), self._guard_description(obj)] for obj in objects]})
        else:
            scene['revision'] = 'blender:' + _digest({'scene': scene, 'scale_length': scale})
        if _native_evidence:
            current_objects = self._objects(graph)
            if (len(current_objects) != len(objects)
                    or any(not _same_rna(a, b) for a, b in zip(objects, current_objects))
                    or self._execution_status(objects) != native_capability
                    or self._identity_metadata(objects) != native_identity
                    or scene.get('host_execution') != native_capability
                    or scene.get('host_identity') != native_identity):
                raise BlenderHostError("Native scene membership, capability or identity changed during capture")
            # This ASCII digest is the native evidence schema's canonical form;
            # the existing capture/fingerprint keeps its original UTF-8 form.
            payload = json.dumps(native_objects, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=True, allow_nan=False).encode('utf-8')
            native = {'unit': 'm', 'coordinate_frame': 'world',
                      'revision': 'native:' + hashlib.sha256(payload).hexdigest(),
                      'objects': native_objects}
            return {'protocol': 'native-pose-evidence-v1-20261030',
                'capture': scene, 'native_scene': native,
                'coherence': {'same_traversal': True, 'raw_original_mesh_verified': True,
                    'execution_scope': 'independent_static_rigid_meshes', 'snapshot_not_history': True,
                    'capture_revision': scene['revision'], 'capture_fingerprint': _digest(scene),
                    'native_revision': native['revision'],
                    'sample_source': 'single_synchronous_blender_main_thread_capture',
                    'world_coordinate_evaluation': 'binary64_original_local_matrix_forward_map',
                    'independent_physical_measurement': False, 'external_edit_history_proven': False,
                    'execution_authority': False}}
        return scene

    def _raw_mesh_module(self):
        """Independent pinned raw reader; old native dependency pins stay fixed."""
        from pathlib import Path
        source=Path(__file__).resolve().with_name('mesh_structure.py')
        if source.resolve()!=source:raise BlenderHostError('raw_mesh_source_path_changed')
        with source.open('rb') as stream:raw=stream.read(_READONLY_SOURCE_LIMIT+1)
        if len(raw)>_READONLY_SOURCE_LIMIT or hashlib.sha256(raw).hexdigest()!=_RAW_MESH_SHA256:
            raise BlenderHostError('raw_mesh_source_mismatch')
        module=getattr(self,'_raw_mesh_module_cache',None)
        if module is None:
            module=self._readonly_checked_module(source,raw,'_human_eye_raw_mesh')
            self._raw_mesh_module_cache=module
        return module

    def _reference_view_module(self):
        from pathlib import Path
        source=Path(__file__).resolve().with_name('reference_view.py')
        with source.open('rb') as stream:raw=stream.read(_READONLY_SOURCE_LIMIT+1)
        if source.resolve()!=source or len(raw)>_READONLY_SOURCE_LIMIT or hashlib.sha256(raw).hexdigest()!=_REFERENCE_VIEW_SHA256:
            raise BlenderHostError('reference_view_source_mismatch')
        return self._readonly_checked_module(source,raw,'_human_eye_reference_view')

    def reference_view_capabilities(self):
        module=self._reference_view_module()
        return dict(protocol=module.PROTOCOL,helper_sha256=_REFERENCE_VIEW_SHA256,native=self.native_observation_capabilities(),
            limits=module.LIMITS,read_only=True,execution_authority=False)

    def observe_reference_patch(self,request_id,object_id,patch,deadline_ns):
        self._main_thread()
        with self._lock:return self._reference_view_module().observe(self,object_id,patch,request_id,deadline_ns)

    def _surface_geometry_module(self):
        from pathlib import Path
        source=Path(__file__).resolve().with_name('surface_geometry.py')
        with source.open('rb') as stream:raw=stream.read(_READONLY_SOURCE_LIMIT+1)
        if source.resolve()!=source or len(raw)>_READONLY_SOURCE_LIMIT or hashlib.sha256(raw).hexdigest()!='bf6873df6fc9d77e43a062d254805f874a003bf0734acc77441673e544e7b5de':
            raise BlenderHostError('surface_helper_source_mismatch')
        return self._readonly_checked_module(source,raw,'_human_eye_surface_geometry')

    def surface_geometry_capabilities(self):
        m=self._surface_geometry_module()
        return dict(protocol=m.PROTOCOL,helper_sha256='bf6873df6fc9d77e43a062d254805f874a003bf0734acc77441673e544e7b5de',raw_helper_sha256=_RAW_MESH_SHA256,
            limits=m.LIMITS,clock=self._readonly_clock_module().counter_descriptor(),read_only=True,execution_authority=False,images=False)

    def capture_surface_source(self,request_id,object_id,deadline_ns):
        self._main_thread();m=self._surface_geometry_module();raw_module=self._raw_mesh_module()
        budget=raw_module.WorkBudget(deadline_ns=deadline_ns)
        with self._lock:
            prepared=raw_module.capture_raw(self,object_id,budget=budget)
            obj=next(o for o in self.scene.objects if self.object_id(o)==object_id)
            before=raw_module._host_header(self,obj)
            # Count before calculating a possibly large tessellation cache.
            if sum(len(p.vertices)-2 for p in obj.data.polygons)>m.LIMITS['triangles']:
                raise BlenderHostError('surface_geometry_budget')
            budget.check('before_host_tessellation');obj.data.calc_loop_triangles()
            triangles=[[int(i) for i in t.vertices] for t in obj.data.loop_triangles]
            polygons=[int(t.polygon_index) for t in obj.data.loop_triangles]
            if raw_module._host_header(self,obj)!=before:raise BlenderHostError('surface_tessellation_source_changed')
            m.validate_tessellation(prepared['raw'],triangles,polygons,budget)
            budget.check('surface_host_reply')
            return dict(schema=m.PROTOCOL,request_id=request_id,source=prepared['source'],raw=prepared['raw'],
                triangles=triangles,triangle_polygons=polygons)

    def observe_surface_geometry(self,request_id,object_id,deadline_ns,near_m):
        packet=self.capture_surface_source(request_id,object_id,deadline_ns)
        raw_module=self._raw_mesh_module();m=self._surface_geometry_module()
        packet['diagnostic']=m.analyze(dict(raw=packet['raw'],source=packet['source']),packet['triangles'],packet['triangle_polygons'],
            budget=raw_module.WorkBudget(deadline_ns=deadline_ns),near_m=near_m)
        return packet

    def mesh_structure_capabilities(self):
        module=self._raw_mesh_module()
        return {'protocol':module.PROTOCOL,'supported_categories':list(module.SUPPORTED),
                'helper_sha256':_RAW_MESH_SHA256,'process_id':os.getpid(),
                'clock':self._readonly_clock_module().counter_descriptor(),
                'read_only':True,'execution_authority':False,'images':False}

    def observe_mesh_structure(self, request_id, object_id, categories, deadline_ns):
        """Single-target structural facts; never call the pair/render/write path."""
        self._main_thread()
        with self._lock:
            return self._raw_mesh_module().observe_raw(self,object_id,request_id=request_id,
                categories=categories,deadline_ns=deadline_ns)

    def mesh_region_summary_capabilities(self):
        caps=self.mesh_structure_capabilities()
        caps['protocol']=self._raw_mesh_module().REGION_SUMMARY_PROTOCOL
        return caps

    def observe_mesh_structure_summary(self, request_id, object_id, categories, deadline_ns):
        self._main_thread()
        with self._lock:
            return self._raw_mesh_module().observe_raw(self,object_id,request_id=request_id,
                categories=categories,deadline_ns=deadline_ns,region_summaries=True)

    def _patch_focus_module(self):
        from pathlib import Path
        source=Path(__file__).resolve().with_name('patch_focus.py')
        if source.resolve()!=source:raise BlenderHostError('patch_source_path_changed')
        with source.open('rb') as stream:raw=stream.read(_READONLY_SOURCE_LIMIT+1)
        if len(raw)>_READONLY_SOURCE_LIMIT or hashlib.sha256(raw).hexdigest()!=_PATCH_FOCUS_SHA256:
            raise BlenderHostError('patch_source_mismatch')
        module=getattr(self,'_patch_focus_module_cache',None)
        if module is None:
            module=self._readonly_checked_module(source,raw,'_human_eye_patch_focus')
            self._patch_focus_module_cache=module
        return module

    def patch_observation_capabilities(self):
        module=self._patch_focus_module()
        return dict(protocol=module.PROTOCOL,helper_sha256=_PATCH_FOCUS_SHA256,
            native=self.native_observation_capabilities(),read_only=True,execution_authority=False)

    def observe_patch(self, request_id, object_id, patch, deadline_ns):
        """Private one-target patch lease; never changes rigid execution admission."""
        self._main_thread()
        with self._lock:
            return self._patch_focus_module().observe(self,object_id,patch,request_id,deadline_ns)

    def _nonplanar_focus_module(self):
        """Separate checked-byte helper; never imported by the default XY path."""
        from pathlib import Path
        source=Path(__file__).resolve().with_name('nonplanar_focus.py')
        if source.resolve()!=source:raise BlenderHostError('nonplanar_source_path_changed')
        with source.open('rb') as stream:raw=stream.read(_READONLY_SOURCE_LIMIT+1)
        if len(raw)>_READONLY_SOURCE_LIMIT or hashlib.sha256(raw).hexdigest()!=_NONPLANAR_FOCUS_SHA256:
            raise BlenderHostError('nonplanar_source_mismatch')
        module=getattr(self,'_nonplanar_focus_module_cache',None)
        if module is None:
            module=self._readonly_checked_module(source,raw,'_human_eye_nonplanar_focus')
            self._nonplanar_focus_module_cache=module
        return module

    def nonplanar_observation_capabilities(self):
        module=self._nonplanar_focus_module()
        return dict(protocol=module.PROTOCOL,helper_sha256=_NONPLANAR_FOCUS_SHA256,
            modes=list(module.MODES),native=self.native_observation_capabilities(),
            read_only=True,execution_authority=False)

    def observe_nonplanar_patch(self, request_id, object_id, patch, deadline_ns, mode):
        self._main_thread()
        with self._lock:
            return self._nonplanar_focus_module().observe(self,object_id,patch,request_id,deadline_ns,mode)

    def capture_scene(self):
        """Read evaluated world geometry; raises if collision coverage is incomplete."""
        self._main_thread()
        with self._lock:
            return self._capture_state(self._capture(_resident=True),_digest(['scene']))

    def capture_directory(self, deadline_ns, max_response_bytes):
        """Aggregate evaluated vertex bounds without creating a mesh capture."""
        self._main_thread()
        if type(deadline_ns) is not int or deadline_ns <= 0:
            raise BlenderHostError('directory_deadline')
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 64 * 1024 * 1024:
            raise BlenderHostError('directory_document_budget')

        def checkpoint():
            if time.perf_counter_ns() >= deadline_ns:
                raise BlenderHostError('directory_deadline_exceeded')

        checkpoint()
        with self._lock:
            graph, scale = self._depsgraph(), self._scale()
            checkpoint()
            objects = self._objects(graph)
            resident = self._sync_residency(graph, scale)
            selection_key = _digest(['directory'])
            cached = self._residency.captures.get(selection_key) if resident else None
            if cached is not None:
                result = self._capture_state(cached, selection_key)
                result['cache_hit'] = True
                self._residency_stats['directory_cache_hits'] += 1
            else:
                identity = self._identity_metadata(objects, capture_scope='scene_directory')
                source_sha = globals().get('_READONLY_LOADED_HOST_SHA256')
                if identity is None or not _hex_string(source_sha, 64):
                    raise BlenderHostError('directory_source_identity_unavailable')
                rows = []
                vertex_count = triangle_budget = 0
                for obj in objects:
                    checkpoint()
                    evaluated = obj.evaluated_get(graph)
                    if not bool(getattr(evaluated, 'is_evaluated', True)):
                        raise BlenderHostError('directory_object_not_evaluated: ' + obj.name)
                    matrix = _matrix(evaluated.matrix_world)
                    temporary = None
                    try:
                        self._residency_stats['to_mesh'] += 1
                        temporary = evaluated.to_mesh()
                        if temporary is None or not len(temporary.vertices):
                            raise BlenderHostError('directory_empty_or_unavailable_mesh: ' + obj.name)
                        vertex_count += len(temporary.vertices)
                        # A polygon with n loops has at most n-2 triangles.
                        # Read collection lengths without triangulating or walking faces.
                        triangle_budget += max(0, len(temporary.loops) - 2 * len(temporary.polygons))
                        if vertex_count > 500000 or triangle_budget > 1000000:
                            raise BlenderHostError('Scene geometry budget exceeded')
                        low = [math.inf] * 3
                        high = [-math.inf] * 3
                        for vertex in _acquisition_vertices(temporary.vertices, checkpoint):
                            point = tuple(float(vertex.co[i]) for i in range(3))
                            world = [(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale
                                     for r in range(3)]
                            self._residency_stats['directory_vertices'] += 1
                            if any(not math.isfinite(value) for value in world):
                                raise BlenderHostError('directory_nonfinite_geometry: ' + obj.name)
                            for axis in range(3):
                                low[axis] = min(low[axis], world[axis])
                                high[axis] = max(high[axis], world[axis])
                        rows.append(dict(object_id=self.object_id(obj), name=str(obj.name),
                            bbox_min=low, bbox_max=high,
                            center=[_bounds_midpoint(a, b) for a, b in zip(low, high)]))
                    finally:
                        if temporary is not None:
                            evaluated.to_mesh_clear()
                packet = dict(schema='human-eye-directory-v1', result_kind='scene_directory',
                    status='complete', unit='m', coordinate_frame='world', objects=rows,
                    coverage=dict(status='complete', mesh_objects=len(objects), measured_objects=len(rows)),
                    binding=dict(host_source_sha256=source_sha, host_identity=identity,
                        frame=int(getattr(self.scene, 'frame_current', 0)),
                        subframe=float(getattr(self.scene, 'frame_subframe', 0.)), scale_length=scale),
                    execution_authority=False)
                packet['directory_sha256'] = _digest(packet)
                packet['capture_state'] = None
                packet['cache_hit'] = False
                checkpoint()
                # Cache only a complete independent directory. Mesh resources,
                # delta baselines and action state retain their own ownership.
                if resident:
                    if len(self._residency.captures) >= 8:
                        self._residency.captures.clear()
                    self._residency.captures[selection_key] = packet
                self._residency_stats['directory_builds'] += 1
                result = self._capture_state(packet, selection_key)
            checkpoint()
            encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf8')
            if len(encoded) > max_response_bytes:
                raise BlenderHostError('directory_document_budget_exceeded')
            checkpoint()
            return result

    def _acquisition_directory_source(self, obj, graph, scale, *, allow_hidden=False):
        """Shared cheap static directory read; geometry expansion stays separate."""
        oid = self.object_id(obj)
        guards = self._guard_description(obj)
        if (guards['parent'] is not None or guards['children'] or guards['constraints']
                or guards['modifiers'] or guards['animation'] or guards['data_animation']
                or guards['rigid_body'] or guards['rigid_body_constraint'] or guards['shape_keys']
                or guards['linked'] or guards['edit_mode']
                or getattr(getattr(obj, 'data', None), 'library', None) is not None
                or getattr(obj, 'instance_type', 'NONE') != 'NONE'
                or bool(getattr(obj, 'is_instancer', False))):
            raise BlenderHostError('acquisition_static_triangle_source_required:' + oid)
        evaluated = obj.evaluated_get(graph)
        source_mode = 'evaluated_static'
        if getattr(evaluated, 'is_evaluated', False) is not True:
            hidden = bool(getattr(obj, 'hide_viewport', False))
            hidden_get = getattr(obj, 'hide_get', None)
            if callable(hidden_get):
                hidden = hidden or bool(hidden_get())
            if not allow_hidden or not hidden:
                raise BlenderHostError('acquisition_evaluation_unavailable:' + oid)
            from types import SimpleNamespace
            evaluated = SimpleNamespace(data=obj.data, matrix_world=obj.matrix_world,
                                        is_evaluated=True, bound_box=getattr(obj, 'bound_box', ()))
            source_mode = 'static_original_hidden'
        data = getattr(evaluated, 'data', None)
        if (data is None or not hasattr(data, 'vertices') or not hasattr(data, 'polygons')
                or not hasattr(data, 'loops') or len(data.vertices) < 3 or not len(data.polygons)
                or len(data.loops) != 3 * len(data.polygons)):
            raise BlenderHostError('acquisition_triangle_data_required:' + oid)
        matrix = _matrix(evaluated.matrix_world)
        try:
            corners = evaluated.bound_box
        except (AttributeError, RuntimeError):
            corners = ()
        return evaluated, guards, matrix, _acquisition_bounds(corners, matrix, scale), source_mode

    def _scan_local_geometry(self, data, checkpoint, oid):
        _acquisition_validate_triangles(data, check_coordinates=False, checkpoint=checkpoint, object_id=oid)
        local = tuple(tuple(float(vertex.co[k]) for k in range(3)) for vertex in
                      _acquisition_vertices(data.vertices, checkpoint))
        if any(not math.isfinite(value) for point in local for value in point):
            raise BlenderHostError('nonfinite_local_triangle_source')
        faces = []
        for ordinal, polygon in enumerate(data.polygons):
            if ordinal % 256 == 0:
                checkpoint()
            faces.append(tuple(data.loops[polygon.loop_start + offset].vertex_index for offset in range(3)))
        self._residency_stats['resource_vertices_read'] += len(local)
        self._residency_stats['resource_faces_read'] += len(faces)
        return local, tuple(faces)

    def capture_nearest_candidates(self, focal_id, deadline_ns, max_response_bytes, *, selector=None):
        """Internal unsigned-surface acquisition, one synchronous host window.

        Restricted to independent static triangle meshes. API-derived bounds
        only choose acquisition; the returned packet is not a nearest result,
        solid certificate, legacy complete-scene capture or action authority.
        """
        self._main_thread()
        if selector is None:
            if type(focal_id) is not str or not focal_id or len(focal_id.encode('utf8')) > 256:
                raise BlenderHostError('acquisition_focal_id')
        else:
            if focal_id is not None:
                raise BlenderHostError('acquisition_focal_selector_conflict')
            if (type(selector) is not dict or set(selector) not in ({'id'}, {'name'})
                    or any(type(value) is not str or not value.strip() or len(value.encode('utf8')) > 256
                           for value in selector.values())):
                raise BlenderHostError('acquisition_selector')
            selector_key, selector_value = next(iter(selector.items()))
        if type(deadline_ns) is not int or deadline_ns <= 0:
            raise BlenderHostError('acquisition_deadline')
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 64 * 1024 * 1024:
            raise BlenderHostError('acquisition_document_budget')
        def checkpoint():
            if time.perf_counter_ns() >= deadline_ns:
                raise BlenderHostError('acquisition_deadline_exceeded')
        checkpoint()
        with self._lock:
            graph, scale = self._depsgraph(), self._scale()
            checkpoint()
            objects = self._objects(graph)
            ids = [self.object_id(obj) for obj in objects]
            if selector is not None:
                matches = [oid for obj, oid in zip(objects, ids)
                           if (oid if selector_key == 'id' else obj.name) == selector_value]
                if not matches:
                    raise BlenderHostError('acquisition_selector_not_found')
                if len(matches) != 1:
                    raise BlenderHostError('acquisition_selector_ambiguous')
                focal_id = matches[0]
            if len(set(ids)) != len(ids) or focal_id not in ids or len(ids) < 2:
                raise BlenderHostError('acquisition_object_coverage')
            resident=self._sync_residency(graph,scale)
            nearest_key=_digest(['nearest',focal_id])
            cached=self._residency.nearest.get(nearest_key) if resident else None
            if cached is not None:
                checkpoint()
                if cached[1]>max_response_bytes:raise BlenderHostError('acquisition_document_budget_exceeded')
                result=copy.deepcopy(cached[0]);checkpoint()
                self._residency_stats['nearest_cache_hits']+=1
                return result
            identity = self._identity_metadata(objects)
            source_sha = globals().get('_READONLY_LOADED_HOST_SHA256')
            if identity is None or not _hex_string(source_sha, 64):
                raise BlenderHostError('acquisition_source_identity_unavailable')
            frame = int(getattr(self.scene, 'frame_current', 0))
            evaluated_by_id, frozen, rows = {}, {}, {}
            source_vertices = source_faces = 0

            def read_directory(obj):
                nonlocal source_vertices, source_faces
                checkpoint()
                oid = self.object_id(obj)
                evaluated, guards, matrix, bounds, _ = self._acquisition_directory_source(obj, graph, scale)
                data = evaluated.data
                source_vertices += len(data.vertices)
                source_faces += len(data.polygons)
                if source_vertices > 500_000 or source_faces > 1_000_000:
                    raise BlenderHostError('acquisition_scene_geometry_budget')
                evaluated_by_id[oid] = evaluated
                frozen[oid] = (guards, matrix, len(data.vertices), len(data.polygons))
                row = {'object_id': oid, 'bounds_world_m': bounds,
                       'witness': _acquisition_witness(data, matrix, scale)}
                if row['bounds_world_m'] is not None and row['witness'] is not None:
                    lo, hi = row['bounds_world_m']
                    if any(not lo[k] <= point[k] <= hi[k] for point in row['witness']['triangle_world_m'] for k in range(3)):
                        row['bounds_world_m'] = None
                checkpoint()
                return row

            focal_obj = objects[ids.index(focal_id)]
            rows[focal_id] = read_directory(focal_obj)
            focal_witness = rows[focal_id]['witness']
            upper, seed, focal_index, seed_index = math.inf, None, 0, 0
            for obj, oid in zip(objects, ids):
                if oid != focal_id:
                    rows[oid] = read_directory(obj)
                    witness = rows[oid]['witness']
                    if focal_witness is not None and witness is not None and upper != 0.:
                        for fi, point_a in enumerate(focal_witness['triangle_world_m']):
                            for si, point_b in enumerate(witness['triangle_world_m']):
                                value = _acquisition_upper(point_a, point_b)
                                if value < upper:
                                    upper, seed, focal_index, seed_index = value, oid, fi, si
                                if upper == 0.:
                                    break
                            if upper == 0.:
                                break
            # Search uses the original triangle ordering throughout. Cyclic
            # rotation preserves orientation and the existing first-point
            # witness schema, including the capture readback and digest.
            if seed is not None:
                for oid, offset in ((focal_id, focal_index), (seed, seed_index)):
                    witness = rows[oid]['witness']
                    for field in ('triangle_world_m', 'triangle_vertex_indices'):
                        values = witness[field]
                        witness[field] = values[offset:] + values[:offset]
                    witness['point_world_m'] = witness['triangle_world_m'][0]
            selected, coverage = [], []
            for obj, oid in zip(objects, ids):
                checkpoint()
                row = rows[oid]
                lower = _acquisition_lower(rows[focal_id]['bounds_world_m'], row['bounds_world_m'])
                excluded = oid != focal_id and oid != seed and row['witness'] is not None and lower > upper
                _acquisition_validate_triangles(evaluated_by_id[oid].data,
                    check_coordinates=excluded, checkpoint=checkpoint, object_id=oid)
                row.update(lower_bound_m=lower, disposition='excluded_strict_bound' if excluded else 'retained',
                           bounds_status='enclosed' if row['bounds_world_m'] is not None else 'unknown')
                coverage.append(row)
                if not excluded:
                    selected.append(obj)
            scene = self._capture(_acquisition_context=(graph, scale, selected, evaluated_by_id, checkpoint),_resident=True)
            checkpoint()
            # The witness defining U must survive the actual selected capture.
            captured = {mesh['object_id']: mesh for mesh in scene['meshes']}
            for oid in (focal_id, seed):
                witness = rows[oid]['witness'] if oid is not None else None
                if witness is not None:
                    mesh = captured[oid]
                    indices = witness['triangle_vertex_indices']
                    if (not any(sorted(face) == sorted(indices) for face in mesh['faces'])
                            or [mesh['vertices'][i] for i in indices] != witness['triangle_world_m']):
                        raise BlenderHostError('acquisition_witness_capture_mismatch')
            # No second dependency-graph update; reject observable mutations in
            # this synchronous main-thread read, never describe edit history.
            if (self._objects(graph) != objects or self._scale() != scale
                    or int(getattr(self.scene, 'frame_current', 0)) != frame
                    or self._identity_metadata(objects) != identity):
                raise BlenderHostError('acquisition_source_changed')
            for obj, oid in zip(objects, ids):
                old = frozen[oid]
                evaluated = evaluated_by_id[oid]
                if (self._guard_description(obj) != old[0] or _matrix(evaluated.matrix_world) != old[1]
                        or len(evaluated.data.vertices) != old[2] or len(evaluated.data.polygons) != old[3]):
                    raise BlenderHostError('acquisition_source_changed')
            scene=self._capture_state(scene,nearest_key)
            packet = {'protocol': 'single-read-surface-candidates-v1', 'capture': scene,
                'focal_id': focal_id, 'coverage': coverage,
                'scope': 'independent_static_triangle_meshes_current_evaluated_surfaces',
                'bound_method': 'outward_evaluated_local_box_affine_linf',
                'upper_method': 'outward_L1_real_triangle_vertex_pair',
                'M3_qualification_performed': False,
                'witness_upper_bound_m': upper if math.isfinite(upper) else None, 'upper_seed_id': seed,
                'unresolved_bounds_ids': [row['object_id'] for row in coverage if row['bounds_status'] == 'unknown'],
                'unresolved_witness_ids': [row['object_id'] for row in coverage if row['witness'] is None],
                'binding': {'host_source_sha256': source_sha, 'host_identity': identity, 'frame': frame,
                            'scale_length': scale, 'coordinate_frame': 'world', 'unit': 'm',
                            'same_main_thread_read': True, 'external_edit_history_proven': False},
                'work': {'directory_objects': len(objects), 'source_vertices': source_vertices,
                         'source_faces': source_faces, 'expanded_objects': len(selected),
                         'expanded_vertices': sum(len(m['vertices']) for m in scene['meshes']),
                         'expanded_faces': sum(len(m['faces']) for m in scene['meshes'])},
                'result_kind': 'acquisition_only_not_nearest_result', 'execution_authority': False}
            packet['binding']['directory_sha256'] = _digest(coverage)
            checkpoint()
            packet_bytes=len(json.dumps(packet, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf8'))
            if packet_bytes > max_response_bytes:
                raise BlenderHostError('acquisition_document_budget_exceeded')
            checkpoint()
            if resident:
                if len(self._residency.nearest)>=8:self._residency.nearest.clear()
                self._residency.nearest[nearest_key]=(copy.deepcopy(packet),packet_bytes)
            return packet

    def capture_surface_scan(self, threshold_m, deadline_ns, max_response_bytes):
        """Acquire one complete mesh directory and one retained endpoint union."""
        self._main_thread()
        if type(threshold_m) not in (int, float):
            raise BlenderHostError('surface_scan_threshold')
        try:
            threshold_m = float(threshold_m)
        except OverflowError as exc:
            raise BlenderHostError('surface_scan_threshold') from exc
        if not math.isfinite(threshold_m) or threshold_m < 0:
            raise BlenderHostError('surface_scan_threshold')
        if type(deadline_ns) is not int or deadline_ns <= 0:
            raise BlenderHostError('acquisition_deadline')
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 64 * 1024 * 1024:
            raise BlenderHostError('acquisition_document_budget')
        def checkpoint():
            if time.perf_counter_ns() >= deadline_ns:
                raise BlenderHostError('acquisition_deadline_exceeded')
        def instances():
            return any(bool(getattr(item, 'is_instance', False)) for item in getattr(graph, 'object_instances', ()))
        def current_scope_issues():
            issues = ['evaluated_instances_not_supported'] if instances() else []
            if any(getattr(obj, 'type', None) != 'MESH' and
                   (getattr(obj, 'instance_type', 'NONE') != 'NONE' or bool(getattr(obj, 'is_instancer', False)))
                   for obj in self.scene.objects):
                issues.append('nonmesh_scene_instancers_not_supported')
            return issues
        checkpoint()
        with self._lock:
            before = dict(self._residency_stats)
            graph, scale = self._depsgraph(), self._scale()
            objects = self._objects(graph, _surface_scan=True)
            ids = [self.object_id(obj) for obj in objects]
            if len(set(ids)) != len(ids):
                raise BlenderHostError('acquisition_object_coverage')
            resident = self._sync_residency(graph, scale, _surface_scan=True)
            state = self._residency
            selection_key = _digest(['surface_scan', threshold_m])
            identity = self._identity_metadata(objects)
            source_sha = globals().get('_READONLY_LOADED_HOST_SHA256')
            if identity is None or not _hex_string(source_sha, 64):
                raise BlenderHostError('acquisition_source_identity_unavailable')
            scope_issues = current_scope_issues()
            def current_work(work, cache_hit):
                return dict(work, cache_hit=cache_hit,
                            residency_delta={key: self._residency_stats[key] - value for key, value in before.items()})
            cached = state.nearest.get(selection_key) if resident else None
            if cached is not None and (cached[0]['binding']['host_identity'] != identity
                                       or cached[0]['binding']['host_source_sha256'] != source_sha
                                       or cached[0]['scope_issues'] != scope_issues):
                cached = None
            if cached is not None:
                checkpoint()
                result = copy.deepcopy(cached[0])
                self._residency_stats['scan_cache_hits'] += 1
                result['work'] = current_work(result['work'], True)
                # Only current-request counters changed. Reuse the established
                # full-document size without serializing all cached geometry.
                def work_bytes(value):
                    return len(json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf8'))
                packet_bytes = cached[1] - work_bytes(cached[0]['work']) + work_bytes(result['work'])
                if packet_bytes > max_response_bytes:
                    raise BlenderHostError('acquisition_document_budget_exceeded')
                checkpoint()
                return result
            frame = (int(getattr(self.scene, 'frame_current', 0)), float(getattr(self.scene, 'frame_subframe', 0)))
            rows, sources, frozen, prepared = {}, {}, {}, {}
            source_vertices = source_faces = 0
            ident = self._residency_module.identity
            def source_observable(obj):
                try:
                    matrix = _matrix(obj.matrix_world)
                except BlenderHostError:
                    matrix = None
                return (self._guard_description(obj), ident(getattr(obj, 'data', None)), matrix,
                        getattr(obj, 'instance_type', 'NONE'), bool(getattr(obj, 'is_instancer', False)))
            for obj, oid in zip(objects, ids):
                checkpoint()
                self._residency_stats['scan_directory_objects'] += 1
                frozen[oid] = source_observable(obj)
                row = dict(object_id=oid, name=str(obj.name), bounds_world_m=None, bounds_status='unknown',
                           source_status='unsupported', source_mode=None, reason=None)
                try:
                    evaluated, guards, matrix, bounds, source_mode = self._acquisition_directory_source(
                        obj, graph, scale, allow_hidden=True)
                    data = evaluated.data
                    source_vertices += len(data.vertices)
                    source_faces += len(data.polygons)
                    if source_vertices > 500_000 or source_faces > 1_000_000:
                        raise BlenderHostError('acquisition_scene_geometry_budget')
                    sources[oid] = (evaluated, matrix, self._resource_stamp(obj), len(data.vertices), len(data.polygons))
                    row.update(bounds_world_m=bounds, bounds_status='enclosed' if bounds is not None else 'unknown',
                               source_status='supported', source_mode=source_mode)
                except (BlenderHostError, AttributeError, TypeError, ValueError, IndexError, RuntimeError) as exc:
                    if str(exc).startswith(('acquisition_deadline', 'acquisition_scene_geometry_budget')):
                        raise
                    row['reason'] = str(exc)[:512] or type(exc).__name__
                rows[oid] = row
            pairs, provisional_union = [], set()
            for index, oid in enumerate(ids):
                checkpoint()
                for other in ids[index + 1:]:
                    lower = _acquisition_lower(rows[oid]['bounds_world_m'], rows[other]['bounds_world_m'])
                    self._residency_stats['scan_bound_tests'] += 1
                    unsupported = rows[oid]['source_status'] != 'supported' or rows[other]['source_status'] != 'supported'
                    disposition = 'unknown_source' if unsupported else 'excluded_strict_bound' if lower > threshold_m else 'retained'
                    pairs.append(dict(object_ids=[oid, other], lower_bound_m=lower, disposition=disposition))
                    if disposition == 'retained':
                        provisional_union.update((oid, other))
            for obj, oid in zip(objects, ids):
                checkpoint()
                if oid not in sources:
                    continue
                evaluated, matrix, stamp, _, _ = sources[oid]
                key = ident(obj)
                resource = state.resources.get(key) if resident else None
                if resource is not None and resource['stamp'] != stamp:
                    resource = None
                check = state.source_checks.get(key) if resident else None
                local = faces = None
                try:
                    if check is not None and check['stamp'] == stamp:
                        self._residency_stats['source_qualification_cache_hits'] += 1
                        if check['reason'] is not None:
                            raise BlenderHostError(check['reason'])
                        summary = check['summary']
                    else:
                        if resource is not None:
                            local, faces = resource['vertices_local'], resource['faces']
                        else:
                            local, faces = self._scan_local_geometry(evaluated.data, checkpoint, oid)
                        self._residency_stats['source_qualification_vertices'] += len(local)
                        self._residency_stats['source_qualification_faces'] += len(faces)
                        summary = _scan_local_summary(local, faces, checkpoint)
                        if resident:
                            state.source_checks[key] = dict(stamp=copy.deepcopy(stamp), summary=summary, reason=None)
                    if not _scan_world_precision(summary, matrix, scale):
                        raise BlenderHostError('world_precision_unresolved')
                    if oid in provisional_union and resource is None:
                        if local is None:
                            local, faces = self._scan_local_geometry(evaluated.data, checkpoint, oid)
                        prepared[oid] = (local, faces)
                except (BlenderHostError, AttributeError, TypeError, ValueError, IndexError, OverflowError) as exc:
                    reason = str(exc)[:512] or type(exc).__name__
                    if reason.startswith('acquisition_deadline'):
                        raise
                    if resident and reason != 'world_precision_unresolved':
                        state.source_checks[key] = dict(stamp=copy.deepcopy(stamp), summary=None, reason=reason)
                    rows[oid].update(source_status='unsupported', reason=reason)
            union = set()
            for ordinal, pair in enumerate(pairs):
                if ordinal % 256 == 0:
                    checkpoint()
                oid, other = pair['object_ids']
                if rows[oid]['source_status'] != 'supported' or rows[other]['source_status'] != 'supported':
                    pair['disposition'] = 'unknown_source'
                if pair['disposition'] == 'retained':
                    union.update((oid, other))
            selected = [obj for obj, oid in zip(objects, ids) if oid in union]
            evaluated_by_id = {oid: value[0] for oid, value in sources.items()}
            scene = self._capture(_acquisition_context=(graph, scale, selected, evaluated_by_id, checkpoint),
                                  _resident=True, _acquisition_scope='surface_scan_candidates', _prepared_local=prepared)
            checkpoint()
            if (self._objects(graph, _surface_scan=True) != objects or self._scale() != scale
                    or (int(getattr(self.scene, 'frame_current', 0)), float(getattr(self.scene, 'frame_subframe', 0))) != frame
                    or self._identity_metadata(objects) != identity or current_scope_issues() != scope_issues):
                raise BlenderHostError('acquisition_source_changed')
            for obj, oid in zip(objects, ids):
                if source_observable(obj) != frozen[oid]:
                    raise BlenderHostError('acquisition_source_changed')
                if oid in sources:
                    evaluated, matrix, stamp, vertex_count, face_count = sources[oid]
                    if (_matrix(evaluated.matrix_world) != matrix or self._resource_stamp(obj) != stamp
                            or len(evaluated.data.vertices) != vertex_count or len(evaluated.data.polygons) != face_count):
                        raise BlenderHostError('acquisition_source_changed')
            coverage = [rows[oid] for oid in ids]
            directory_sha = _digest(coverage)
            # A far source or catalog-scope change can leave the endpoint union
            # unchanged. Its revision still invalidates complete result reuse.
            scene = dict(scene, revision='blender:' + _digest(dict(capture_revision=scene['revision'],
                directory_sha256=directory_sha, scope_issues=scope_issues, host_identity=identity)))
            scene = self._capture_state(scene, selection_key)
            packet = dict(protocol='single-read-surface-scan-v1', result_kind='acquisition_only_not_surface_scan_result',
                threshold_m=threshold_m, scope='independent_static_triangle_meshes_current_evaluated_surfaces',
                scope_issues=scope_issues, capture=scene, coverage=coverage, pairs=pairs,
                bound_method='outward_evaluated_local_box_affine_linf', M3_qualification_performed=False,
                binding=dict(host_source_sha256=source_sha, host_identity=identity, directory_sha256=directory_sha,
                    frame=frame[0], scale_length=scale, coordinate_frame='world', unit='m',
                    same_main_thread_read=True, external_edit_history_proven=False),
                execution_authority=False,
                work=current_work(dict(directory_objects=len(objects), source_vertices=source_vertices, source_faces=source_faces,
                    broad_pairs=len(pairs), retained_pairs=sum(pair['disposition']=='retained' for pair in pairs),
                    expanded_objects=len(selected), expanded_vertices=sum(len(mesh['vertices']) for mesh in scene['meshes']),
                    expanded_faces=sum(len(mesh['faces']) for mesh in scene['meshes'])), False))
            checkpoint()
            packet_bytes = len(json.dumps(packet, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf8'))
            if packet_bytes > max_response_bytes:
                raise BlenderHostError('acquisition_document_budget_exceeded')
            checkpoint()
            if resident:
                if len(state.nearest) >= 8:
                    state.nearest.clear()
                state.nearest[selection_key] = (copy.deepcopy(packet), packet_bytes)
            return packet

    def capture_task_scene(self, selectors):
        """Read only the uniquely bound targets in one synchronous observation."""
        self._main_thread()
        if type(selectors) is not list or not 1 <= len(selectors) <= 4:
            raise BlenderHostError('Task objects require 1..4 selectors')
        for selector in selectors:
            if (type(selector) is not dict or set(selector) not in ({'id'}, {'name'})
                    or any(type(value) is not str or not value.strip() or len(value.encode('utf8')) > 256
                           for value in selector.values())):
                raise BlenderHostError('Task selector requires one bounded nonempty id or name')
        with self._lock:
            return self._capture_state(self._capture(_task_selectors=selectors,_resident=True),_digest(['task',selectors]))

    def capture_evidence(self):
        """Read one coherent original-pose sidecar without changing old capture.

        This single synchronous main-thread traversal is a snapshot, not an
        independent physical measurement or a record of external edit history.
        Unsupported execution scope, missing identity or a disagreement between
        original and evaluated native data rejects the complete new method.
        """
        self._main_thread()
        with self._lock:
            return self._capture(_native_evidence=True)

    def _arm_twist_source_module(self, *, execution=False):
        cache_name = '_arm_twist_execution_module' if execution else '_arm_twist_module'
        module = getattr(self, cache_name, None)
        if module is not None:
            return module
        import importlib.util
        import sys
        import types
        from pathlib import Path
        root = Path(__file__).resolve().parent
        names = ('rig_pose.py', 'arm_twist_weights.py', 'arm_twist_expert.py', 'arm_twist_source.py')
        if execution:
            names += ('arm_twist_correction.py',)
        sources = getattr(self, '_arm_correction_dependency_sources' if execution else '_arm_twist_dependency_sources', None)
        if sources is None:
            guard = next((f for f in sys.meta_path if getattr(f, 'protocol', None) ==
                'human-eye-verified-source-v1' and f.root == root.parent), None)
            sources = {name: (guard.sources['human_eye_plugin/' + name] if guard is not None
                else (root / name).read_bytes()) for name in names}
        if set(sources) != set(names):
            raise BlenderHostError('Arm twist dependency snapshot unavailable')
        digest = hashlib.sha256(str(root).encode('utf8') + b''.join(sources[n] for n in names)).hexdigest()
        package_name = '_human_eye_arm_twist_' + digest[:24]
        package = sys.modules.get(package_name)
        if package is None:
            package = types.ModuleType(package_name)
            package.__path__ = [str(root)]
            package.__package__ = package_name
            sys.modules[package_name] = package
            created = [(package_name, package)]
            try:
                for name in names:
                    leaf = name[:-3]
                    spec = importlib.util.spec_from_file_location(package_name + '.' + leaf, root / name)
                    child = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = child
                    setattr(package, leaf, child)
                    created.append((spec.name, child))
                    _exec_source_snapshot(child, root / name, sources[name])
            except BaseException:
                for key, child in reversed(created):
                    if sys.modules.get(key) is child:
                        del sys.modules[key]
                raise
        if execution:
            self._arm_correction_module = package.arm_twist_correction
            self._arm_correction_preview = package.arm_twist_correction.preview_axial_redistribution
        setattr(self, cache_name, package.arm_twist_source)
        return getattr(self, cache_name)

    def _arm_axial_side(self, mesh, rig, bones, sentinel, scale):
        """Small native facts missing from the selected source patch."""
        ident = self._residency_module.identity
        for obj in (mesh, rig, sentinel):
            present = self.scene.objects.get(obj.name)
            if present is None or not _same_rna(present, obj):
                raise BlenderHostError('arm_execution_object_incarnation_changed')
        def pose_in_metres(bone):
            matrix = _matrix(rig.pose.bones.get(bone.name).matrix)
            for row in matrix[:3]:row[3] *= scale
            return matrix
        return {
            'mesh_world': _matrix(mesh.matrix_world), 'rig_world': _matrix(rig.matrix_world),
            'frame': [int(self.scene.frame_current), float(getattr(self.scene, 'frame_subframe', 0.))],
            'unit_scale_m': scale,
            'object_static': [{'object_id': self.object_id(obj),
                'parent_instance': ident(getattr(obj, 'parent', None)),
                'constraints': len(getattr(obj, 'constraints', ())),
                'animated': getattr(obj, 'animation_data', None) is not None,
                'data_animated': getattr(obj.data, 'animation_data', None) is not None}
                for obj in (mesh, rig, sentinel)],
            'bone_static': [{'name': b.name, 'length_m': float(b.length)*scale,
                'inherit_rotation': bool(getattr(b, 'use_inherit_rotation', True)),
                'inherit_scale': getattr(b, 'inherit_scale', 'FULL'),
                'local_location': bool(getattr(b, 'use_local_location', True)),
                'connected': bool(getattr(b, 'use_connect', False)),
                'constraints': len(getattr(rig.pose.bones.get(b.name), 'constraints', ())),
                'rotation_mode': getattr(rig.pose.bones.get(b.name), 'rotation_mode', None)} for b in bones],
            'heads_m': [[float(v)*scale for v in rig.pose.bones.get(b.name).head] for b in bones],
            'tails_m': [[float(v)*scale for v in rig.pose.bones.get(b.name).tail] for b in bones],
            'poses_m': [pose_in_metres(b) for b in bones],
            'sentinel': {'object_id': self.object_id(sentinel), 'instance': ident(sentinel),
                'data_instance': ident(sentinel.data), 'world': _matrix(sentinel.matrix_world),
                'vertices_m': [[float(v)*scale for v in vertex.co] for vertex in sentinel.data.vertices],
                'faces': [list(poly.vertices) for poly in sentinel.data.polygons]}}

    def _arm_axial_scope(self, mesh, rig, bones, sentinel):
        """The writable subset is the declared static generated three-bone rig."""
        if (len(bones) != 3 or len(rig.data.bones) != 3 or getattr(bones[0], 'parent', None) is not None
                or sentinel is mesh or sentinel is rig or getattr(sentinel, 'type', None) != 'MESH'
                or len(sentinel.data.vertices) > 64 or len(sentinel.data.polygons) > 128
                or len(getattr(sentinel, 'modifiers', ()))
                or getattr(sentinel.data, 'shape_keys', None) is not None):
            raise BlenderHostError('arm_execution_fixture_scope')
        for obj in (mesh, rig, sentinel):
            if (getattr(obj, 'parent', None) is not None or getattr(obj, 'animation_data', None) is not None
                    or getattr(obj.data, 'animation_data', None) is not None or len(getattr(obj, 'constraints', ()))
                    or getattr(obj, 'library', None) is not None or getattr(obj.data, 'library', None) is not None):
                raise BlenderHostError('arm_execution_static_unconstrained_required')
        if getattr(mesh.data, 'users', 1) != 1 or getattr(rig.data, 'users', 1) != 1:
            raise BlenderHostError('arm_execution_shared_data_unsupported')
        for bone in bones:
            pose = rig.pose.bones.get(bone.name)
            if (pose is None or len(getattr(pose, 'constraints', ()))
                    or not getattr(bone, 'use_inherit_rotation', True)
                    or getattr(bone, 'inherit_scale', 'FULL') != 'FULL'
                    or not getattr(bone, 'use_local_location', True)
                    or getattr(bone, 'use_connect', False) or getattr(bone, 'bbone_segments', 1) != 1):
                raise BlenderHostError('arm_execution_default_bone_inheritance_required')
        # Only metadata is inspected here, never unrelated mesh geometry.
        for obj in self.scene.objects:
            if obj is not mesh and any(getattr(modifier, 'type', None) == 'ARMATURE'
                    and _same_rna(getattr(modifier, 'object', None), rig)
                    for modifier in getattr(obj, 'modifiers', ())):
                raise BlenderHostError('arm_execution_shared_rig_unsupported')

    def correct_arm_axial(self, task):
        """One owned typed pair, with actual feedback and no automatic retry."""
        self._main_thread()
        start = time.perf_counter_ns()
        result = {'schema': 'arm-axial-execution-result-v1',
            'event_id': task.get('event_id') if type(task) is dict else None,
            'status': 'not_applicable', 'reason': '', 'executed': False,
            'setter_attempts': 0, 'setter_returns': 0, 'task_succeeded': False,
            'before_source': None, 'after_source': None, 'feedback': None,
            'timings_ns': {}, 'work': {'source_capture_attempts': 0, 'source_captures': 0,
                'preview_calls': 0, 'model_calls': 0, 'feedback_rest_area_batches': 0}}
        audit = {'task': task, 'receipt': result}
        self._last_arm_axial_audit = audit
        bound = mesh = rig = bones = sentinel = None
        stage = 'prewrite_scope'

        def finish():
            result['timings_ns']['host_total'] = time.perf_counter_ns()-start
            if bound is not None:result['work']['source'] = bound.work_totals()
            return result

        with self.transaction():
            try:
                if (getattr(self, '_owned_arm_correction_worker', False) is not True
                        or getattr(self, '_material_readview_only', False)
                        or not getattr(self.bpy.app, 'background', False)):
                    raise BlenderHostError('arm_execution_owned_background_worker_required')
                fields = {'schema', 'event_id', 'selection', 'u_interval_deg', 'max_section_area_loss',
                    'protected_vertex_ids', 'angle_tolerance_deg', 'position_tolerance_m', 'area_tolerance', 'sentinel_name'}
                if (type(task) is not dict or set(task) != fields or task.get('schema') != 'arm-axial-execution-task-v1'
                        or type(task['event_id']) is not str or not 0 < len(task['event_id']) <= 256
                        or any(ord(v) < 32 for v in task['event_id'])):
                    raise BlenderHostError('arm_execution_task_schema')
                if self._active_motion() is not None or self._episode_store() is not None:
                    raise BlenderHostError('arm_execution_other_mutation_domain_active')
                module = self._arm_twist_source_module(execution=True)
                correction = self._arm_correction_module
                np, r = correction.np, correction.r
                adapter = getattr(self, '_arm_correction_adapter', None)
                if adapter is None:
                    adapter = module.ArmTwistSource(self);self._arm_correction_adapter = adapter
                bound = adapter.bind(task['selection'])
                mesh = self.scene.objects.get(task['selection']['mesh_name'])
                rig = self.scene.objects.get(task['selection']['armature_name'])
                sentinel = self.scene.objects.get(task['sentinel_name'])
                if mesh is None or rig is None or sentinel is None:
                    raise BlenderHostError('arm_execution_bound_object_missing')
                result['timings_ns']['scope'] = time.perf_counter_ns()-start
                stage = 'before_capture';mark = time.perf_counter_ns()
                result['work']['source_capture_attempts'] += 1
                before = bound.capture(_export_static_patch=False, _prepare_expert=False)
                result['work']['source_captures'] += 1
                result['timings_ns']['source_before'] = time.perf_counter_ns()-mark
                static = bound._static;scale = self._scale()
                result['before_source'] = before['source']
                audit.update(static_patch=static, before_capture=before)
                stage = 'prewrite_scope'
                ident = self._residency_module.identity
                for obj, key in ((mesh, 'mesh'), (rig, 'armature')):
                    source_object = before['source'][key]
                    if (source_object['instance'] != ident(obj)
                            or source_object['data_instance'] != ident(obj.data)):
                        raise BlenderHostError('arm_execution_source_object_incarnation_changed')
                bones = [rig.data.bones.get(name) for name in task['selection']['bone_names']]
                if any(bone is None for bone in bones):raise BlenderHostError('arm_execution_bound_bone_missing')
                if len(bound._indices) != len(mesh.data.vertices):
                    raise BlenderHostError('arm_execution_full_generated_mesh_required')
                mark = time.perf_counter_ns();self._arm_axial_scope(mesh, rig, bones, sentinel)
                result['timings_ns']['scope'] += time.perf_counter_ns()-mark
                patch = dict(static, current_vertices=before['current_vertices'], bone_chain=[
                    dict(bone, pose_matrix=pose) for bone, pose in zip(static['bone_chain'], before['pose_matrices'])])
                resolved = {key: task[key] for key in ('u_interval_deg', 'max_section_area_loss', 'protected_vertex_ids',
                    'angle_tolerance_deg', 'position_tolerance_m', 'area_tolerance')}
                resolved.update(schema=correction.TASK_SCHEMA,
                    fixed_end_pose_matrices=[before['pose_matrices'][0], before['pose_matrices'][-1]])
                side_before = self._arm_axial_side(mesh, rig, bones, sentinel, scale)
                result['before_source'] = before['source']
                audit.update(static_patch=static, input_patch=patch, resolved_task=resolved,
                             before_capture=before, side_before=side_before)
                stage = 'preview';mark = time.perf_counter_ns();result['work']['preview_calls'] += 1
                proposal = self._arm_correction_preview(patch, resolved)
                result['timings_ns']['solve'] = time.perf_counter_ns()-mark
                audit['preview'] = proposal
                result['preview'] = {'status': proposal['status'], 'reason': proposal['reason'],
                    'u_deg': proposal.get('optimal_u_deg'), 'objective': proposal.get('objective')}
                if proposal['status'] != 'candidate':
                    result.update(status=proposal['status'], reason=proposal['reason'],
                                  task_succeeded=proposal['status'] == 'no_op')
                    objective = proposal.get('objective')
                    result['feedback'] = {'source': 'actual_before_no_write', 'target_met': result['task_succeeded'],
                        'max_section_area_loss': objective['before']['max_section_area_loss'] if objective else None}
                    return finish()
                candidate = proposal['candidate']
                from mathutils import Matrix
                if (len(candidate['bone_changes']) != 2 or len(candidate['local_basis_matrices']) != 3
                        or len(candidate['pose_matrices']) != 3):
                    raise BlenderHostError('arm_execution_candidate_shape')
                assignments = []
                for index, change in zip((1, 2), candidate['bone_changes']):
                    if change['name'] != bones[index].name or change['basis_matrix'] != candidate['local_basis_matrices'][index]:
                        raise BlenderHostError('arm_execution_candidate_binding')
                    basis = [row[:] for row in change['basis_matrix']]
                    for row in basis[:3]:row[3] /= scale
                    native = Matrix(basis);_matrix(native)
                    assignments.append((rig.pose.bones.get(bones[index].name), native))
                if len(assignments) != 2:raise BlenderHostError('arm_execution_two_changes_required')
                stage = 'basis_assignment';mark = time.perf_counter_ns()
                for pose, basis in assignments:
                    result['setter_attempts'] += 1
                    pose.matrix_basis = basis
                    result['setter_returns'] += 1
                result['timings_ns']['assignment'] = time.perf_counter_ns()-mark
                result['executed'] = True
                stage = 'after_capture';mark = time.perf_counter_ns()
                result['work']['source_capture_attempts'] += 1
                after = bound.capture(_export_static_patch=False, _prepare_expert=False)
                result['work']['source_captures'] += 1
                result['timings_ns']['source_after'] = time.perf_counter_ns()-mark
                result['after_source'] = after['source'];audit['after_capture'] = after
                audit['after_static_patch'] = bound._static
                if (static != bound._static or any(before['source'][key] != after['source'][key]
                        for key in before['source'] if key not in ('revision', 'max_lbs_readback_error_m'))):
                    raise BlenderHostError('arm_execution_after_source_binding_changed')
                stage = 'actual_feedback';mark = time.perf_counter_ns()
                side_after = self._arm_axial_side(mesh, rig, bones, sentinel, self._scale())
                audit['side_after'] = side_after
                sections = static['sections'];points = np.asarray(after['current_vertices'])
                old_points = np.asarray(before['current_vertices'])
                result['work']['feedback_rest_area_batches'] += 1
                areas0 = correction._areas(np.asarray(static['rest_vertices']), sections)
                actual = correction._objective(points, sections, areas0)
                def point_error(left, right):
                    return float(np.linalg.norm(np.asarray(left)-np.asarray(right), axis=-1).max())
                pose_angles = [];pose_translations = [];candidate_angles = [];candidate_translations = []
                for index in (0, 1, 2):
                    old = candidate['pose_matrices'][index];new = after['pose_matrices'][index]
                    angle = r.angles(r.multiply(r.inverse(old), new))['rotation_deg']
                    translation = point_error(np.asarray(old)[:3,3], np.asarray(new)[:3,3])
                    candidate_angles.append(angle);candidate_translations.append(translation)
                    if index not in (0, 2):continue
                    pose_angles.append(angle)
                    pose_translations.append(translation)
                by_id = {value: index for index, value in enumerate(static['vertex_ids'])}
                protected = [by_id[index] for index in task['protected_vertex_ids']]
                protected_delta = point_error(old_points[protected], points[protected])
                center_delta = point_error([old_points[row].mean(axis=0) for row in sections],
                                           [points[row].mean(axis=0) for row in sections])
                bone_center_delta = max(point_error(side_before['heads_m'], side_after['heads_m']),
                                        point_error(side_before['tails_m'], side_after['tails_m']))
                target_error = point_error(candidate['current_vertices'], points)
                static_side_same = all(side_before[key] == side_after[key] for key in
                    ('mesh_world', 'rig_world', 'frame', 'unit_scale_m', 'object_static', 'bone_static', 'sentinel'))
                pose_error = max(float(np.max(np.abs(np.asarray(left)-np.asarray(right))))
                                 for left, right in zip(candidate['pose_matrices'], after['pose_matrices']))
                feedback = {'source': 'actual_after_capture', 'max_section_area_loss': actual['max_section_area_loss'],
                    'target_met': actual['max_section_area_loss'] <= task['max_section_area_loss']+task['area_tolerance'],
                    'end_pose_angle_deg': max(pose_angles), 'end_pose_translation_m': max(pose_translations),
                    'protected_points_delta_m': protected_delta, 'section_centers_delta_m': center_delta,
                    'bone_heads_tails_delta_m': bone_center_delta, 'candidate_points_error_m': target_error,
                    'candidate_pose_angle_deg': max(candidate_angles), 'candidate_pose_translation_m': max(candidate_translations),
                    'candidate_pose_max_abs': pose_error, 'static_side_unchanged': static_side_same}
                verified = (feedback['target_met'] and static_side_same and max(pose_angles) <= task['angle_tolerance_deg']
                    and max(candidate_angles) <= task['angle_tolerance_deg']
                    and max(pose_translations + candidate_translations + [protected_delta, center_delta, bone_center_delta, target_error]) <= task['position_tolerance_m'])
                result.update(feedback=feedback, status='satisfied' if verified else 'feedback_failed',
                    reason='actual_goal_and_preservation_verified' if verified else 'actual_feedback_did_not_verify',
                    task_succeeded=bool(verified))
                result['timings_ns']['feedback'] = time.perf_counter_ns()-mark
                return finish()
            except Exception as exc:
                result.update(status='execution_uncertain' if result['setter_attempts'] else 'not_applicable',
                    reason=stage+':'+str(exc)[:1500], task_succeeded=False,
                    executed=True if result['setter_returns'] else None if result['setter_attempts'] else False)
                audit['failure'] = {'stage': stage, 'type': type(exc).__name__, 'message': str(exc)[:1500]}
                if result['setter_attempts'] and all(value is not None for value in (mesh, rig, bones, sentinel)):
                    try:
                        self._depsgraph()
                        audit['partial_native_after'] = self._arm_axial_side(mesh, rig, bones, sentinel, self._scale())
                        result['partial_pose_matrices'] = audit['partial_native_after']['poses_m']
                    except Exception as read_error:audit['partial_readback_error'] = str(read_error)[:1500]
                return finish()

    def observe_arm_twist(self, selection):
        """Estimate the current explicitly selected native arm patch, read-only."""
        self._main_thread()
        with self.transaction():
            adapter = getattr(self, '_arm_twist_adapter', None)
            if adapter is None:
                adapter = self._arm_twist_source_module().ArmTwistSource(self)
                self._arm_twist_adapter = adapter
            bound = getattr(self, '_arm_twist_bound', None)
            retained = None if bound is None else bound._selection
            if (type(selection) is dict and 'vertex_indices' not in selection and retained is not None
                    and getattr(self, '_arm_twist_bound_default_indices', False)):
                retained = {key: value for key, value in retained.items() if key != 'vertex_indices'}
            def same(left, right):
                if type(left) is not type(right):
                    return False
                if type(left) is dict:
                    return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
                if type(left) is list:
                    return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
                return left == right
            # bool/int/float equality must not bypass the source's typed bind.
            if bound is None or not same(selection, retained):
                bound = adapter.bind(selection)
                self._arm_twist_bound = bound
                self._arm_twist_bound_default_indices = 'vertex_indices' not in selection
            return bound.analyze()

    def capture_readonly_evidence(self):
        """Read locked static original poses without making them executable.

        Only transform-lock reasons are permitted by this explicit read path.
        Native/evaluated identity, geometry, topology and every other static
        requirement remain the same as the strict production evidence path.
        """
        self._main_thread()
        with self._lock:
            packet = self._capture(_native_evidence=True, _read_only_native=True)
            packet['coherence']['read_only_evidence'] = True
            packet['coherence']['read_only_evidence_protocol'] = self.readonly_native_evidence_protocol
            packet['coherence']['execution_authority'] = False
            return packet

    @contextmanager
    def transaction(self):
        """Keep a direct in-process gateway's capture/check/apply on one thread."""
        self._main_thread()
        with self._lock:
            yield self

    @staticmethod
    def _verify_readback(before, after, focal_id, rotation, translation):
        actual = {mesh["object_id"]: mesh for mesh in after["meshes"]}
        if len(actual) != len(before["meshes"]):
            raise BlenderHostError("Scene membership changed during host execution")
        for old in before["meshes"]:
            new = actual.get(old["object_id"])
            if new is None or any(new[field] != old[field] for field in
                    ("name", "mark_label", "is_focal_target", "color_rgb", "faces", "edges", "axes_source", "axes_confidence", "axes_reason")):
                raise BlenderHostError("Scene identity, topology, or frame provenance changed during execution")
            pivot = old["pivot_world"]
            changed = old["object_id"] == focal_id
            expected_vertices = old["vertices"]
            expected_axes, expected_pivot = old["local_axes"], pivot
            if changed:
                expected_vertices = [[sum(rotation[r][k] * (vertex[k] - pivot[k]) for k in range(3))
                                      + pivot[r] + translation[r] for r in range(3)] for vertex in old["vertices"]]
                expected_axes = [[sum(rotation[r][k] * axis[k] for k in range(3)) for r in range(3)] for axis in old["local_axes"]]
                expected_pivot = [pivot[r] + translation[r] for r in range(3)]
            if (len(expected_vertices) != len(new["vertices"])
                    or any(abs(a - b) > 1e-6 for va, vb in zip(expected_vertices, new["vertices"]) for a, b in zip(va, vb))
                    or any(abs(a - b) > 1e-6 for va, vb in zip(expected_axes, new["local_axes"]) for a, b in zip(va, vb))
                    or any(abs(a - b) > 1e-6 for a, b in zip(expected_pivot, new["pivot_world"]))):
                raise BlenderHostError("Readback does not match the requested rigid transform within 1e-6 metres")

    def _assign_matrix(self, obj, rows):
        try:
            from mathutils import Matrix
        except ImportError:
            # Injectable bpy test doubles may implement their own matrix class.
            candidate = type(obj.matrix_world)(rows)
        else:
            candidate = Matrix(rows)
        token = self._episode_before_setter(obj, rows, '_assign_matrix')
        try:
            self._enter_forward_setter()
            self._episode_enter_setter(token)
        except _ForwardDeadlineExpired:
            self._episode_cancel_setter(token)
            raise
        try:
            obj.matrix_world = candidate
        except BaseException:
            self._episode_after_setter(token, assignment_error=True)
            raise
        self._episode_after_setter(token)

    def _assign_translation(self, obj, values):
        # An independent object's location is additive with delta_location.
        # Leave all rotation, scale, delta and rotation-mode channels untouched.
        token = self._episode_before_setter(obj, values, '_assign_translation')
        try:
            self._enter_forward_setter()
            self._episode_enter_setter(token)
        except _ForwardDeadlineExpired:
            self._episode_cancel_setter(token)
            raise
        try:
            obj.location = values
        except BaseException:
            self._episode_after_setter(token, assignment_error=True)
            raise
        self._episode_after_setter(token)

    def _episode_store(self, *, create=False):
        namespace = getattr(getattr(self.bpy, 'app', None), 'driver_namespace', None)
        key = '_human_eye_owned_episode_gateway_v1'
        if not isinstance(namespace, dict):
            if create:raise EpisodePrewriteRefused('episode_driver_namespace_required')
            return None
        if key not in namespace:
            if not create:return None
            namespace[key] = {}
        state = namespace[key]
        if type(state) is not dict:raise EpisodeUncertain('episode_store_invalid')
        module = getattr(self, '_episode_module', None)
        if module is None:
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location('_human_eye_owned_episode_gateway',
                Path(__file__).resolve().with_name('episode_gateway.py'))
            if spec is None or spec.loader is None:raise EpisodeUncertain('episode_module_unavailable')
            module = importlib.util.module_from_spec(spec);_exec_source_snapshot(module,Path(__file__).resolve().with_name('episode_gateway.py'))
            self._episode_module = module
        return module, state

    @staticmethod
    def _episode_call(module, method, *args, **kwargs):
        try:return getattr(module, method)(*args, **kwargs)
        except module.EpisodePrewriteRefused as exc:raise EpisodePrewriteRefused(str(exc)) from exc
        except module.EpisodeUncertain as exc:raise EpisodeUncertain(str(exc)) from exc

    def begin_owned_episode(self, episode_id, focal_id, reference_id, deadline_ns,
                            read_only=False, limits=None):
        """Trusted fixed-worker owner binding; not a model authorization API."""
        self._main_thread()
        with self._lock:
            # Prove the parent's QPC domain through the same local descriptor.
            self._forward_deadline_module().counter_descriptor()
            packet = self._capture(_native_evidence=True, _read_only_native=read_only is True)
            module, state = self._episode_store(create=True)
            return self._episode_call(module, 'begin_episode', state, episode_id=episode_id,
                binding=self._motion_binding(packet['capture'], focal_id, reference_id),
                initial_native=packet['native_scene'], deadline_ns=deadline_ns,
                now_ns=time.perf_counter_ns(), read_only=read_only, limits=limits)

    def owned_episode_status(self, after_event_count=0):
        self._main_thread()
        with self._lock:
            store = self._episode_store()
            if store is None:raise EpisodePrewriteRefused('episode_not_bound')
            return self._episode_call(store[0], 'snapshot', store[1], after_event_count=after_event_count)

    def _episode_before_setter(self, obj, values, helper, *, preflight=False):
        store = self._episode_store()
        if store is None:return None
        module, state = store
        report = self._episode_call(module, 'snapshot', state)
        packet = self._capture(_native_evidence=True)
        old = _matrix(obj.matrix_world);scale = self._scale()
        if helper == '_assign_translation':
            previous = _vector([float(v) for v in obj.location], 'location')
            requested = [old[k][3] * scale + (float(values[k]) - previous[k]) * scale for k in range(3)]
            # Blender location and the resulting independent translation are
            # binary32 RNA/matrix storage. Check the represented candidate as
            # well as the request, so a nominal1mm request cannot cross the
            # actual1mm cap by quantization before being noticed on readback.
            delta_location = [float(v) for v in getattr(obj, 'delta_location', (0., 0., 0.))]
            target = [_binary32_nearest(_binary32_nearest(float(values[k])) + delta_location[k]) * scale
                      for k in range(3)]
            if math.dist([old[k][3] * scale for k in range(3)], requested) > report['limits']['max_step_translation_m']:
                raise EpisodePrewriteRefused('episode_requested_step_cap')
        else:
            target_matrix = _matrix(values)
            if any(old[r][c] != target_matrix[r][c] for r in range(4) for c in range(4) if c != 3 or r == 3):
                raise EpisodePrewriteRefused('episode_matrix_rotation_forbidden')
            requested = [target_matrix[k][3] * scale for k in range(3)]
            target = [_binary32_nearest(target_matrix[k][3]) * scale for k in range(3)]
            if math.dist([old[k][3] * scale for k in range(3)], requested) > report['limits']['max_step_translation_m']:
                raise EpisodePrewriteRefused('episode_requested_step_cap')
        pair = report['binding']
        arguments = dict(helper=helper, object_id=self.object_id(obj), requested_world=target,
            before_native=packet['native_scene'],
            binding=self._motion_binding(packet['capture'], pair['focal_id'], pair['reference_id']),
            now_ns=time.perf_counter_ns(), kind='rollback' if getattr(self, '_episode_rollback_context', False) else 'forward')
        value = self._episode_call(module, 'preflight_setter' if preflight else 'reserve_setter', state, **arguments)
        return None if preflight else (module, state, value)

    def _episode_cancel_setter(self, token):
        if token is not None:self._episode_call(token[0], 'cancel_setter', token[1], token[2])

    def _episode_enter_setter(self, token):
        if token is not None:
            self._episode_call(token[0], 'enter_setter', token[1], token[2], time.perf_counter_ns())

    def _episode_after_setter(self, token, *, assignment_error=False):
        if token is None:return
        module, state, index = token
        try:
            packet = self._capture(_native_evidence=True)
            pair = state['record']['binding']
            if self._motion_binding(packet['capture'], pair['focal_id'], pair['reference_id']) != pair:
                raise EpisodeUncertain('episode_binding_changed_after_entry')
        except BaseException as exc:
            self._episode_call(module, 'mark_unknown', state, index, 'episode_native_after_unavailable')
            raise EpisodeUncertain('episode_native_after_unavailable') from exc
        try:
            self._episode_call(module, 'confirm_setter', state, index,
                after_native=packet['native_scene'], now_ns=time.perf_counter_ns(), assignment_error=assignment_error)
        except EpisodePrewriteRefused as exc:
            self._episode_call(module, 'mark_unknown', state, index, 'episode_confirmation_failed')
            raise EpisodeUncertain('episode_confirmation_failed') from exc

    def native_scene_query(self):
        self._main_thread()
        with self._lock:
            status = self.owned_episode_status()
            return self._capture(_native_evidence=True,
                _read_only_native=status['read_only'])['native_scene']

    def native_look(self, view):
        return self._native_render_view(view)

    def _native_render_view(self, view, *, frame=None, coverage='all_native_vertices',
                            expected_native=None, frustum_sink=None):
        self._main_thread()
        with self._lock:
            module, state = self._episode_store() or (None, None)
            if module is None:raise EpisodePrewriteRefused('episode_not_bound')
            status = self._episode_call(module, 'snapshot', state)
            sequence = getattr(self, '_native_render_sequence', 0) + 1
            self._native_render_sequence = sequence
            audit = {'schema_version':'native-render-audit-v1', 'protocol':self.native_render_audit_protocol,
                'status':'failed', 'view':view, 'sequence':sequence, 'before':None, 'after':None,
                'restored':False, 'geometry_restored':None, 'error':None,
                'state_capture_errors':[], 'execution_authority':False}
            self._last_native_render_audit = audit
            before = result = caught = None
            try:
                audit['before'] = self._episode_call(module, 'native_render_state', self.bpy, self.scene, self.view_layer)
                before = self.native_scene_query()
                if expected_native is not None and before != expected_native:
                    raise EpisodeUncertain('native_multiscale_revision_changed_before_render')
                if frame is None and frustum_sink is None:
                    result = module.native_look(self.bpy, self.scene, self.view_layer,before,view)
                else:
                    result = module.native_look(self.bpy, self.scene, self.view_layer,before,view,
                        _frame=frame,_screen_coverage=coverage,_frustum_sink=frustum_sink)
                audit['geometry_restored'] = self.native_scene_query() == before
                if not audit['geometry_restored']:
                    raise EpisodeUncertain('native_render_changed_geometry')
            except BaseException as exc:
                caught = exc
                audit['error'] = {'type':type(exc).__name__, 'message':str(exc)[:2000]}
            finally:
                try:
                    audit['after'] = self._episode_call(module, 'native_render_state', self.bpy, self.scene, self.view_layer)
                except BaseException as exc:
                    audit['state_capture_errors'].append({'stage':'after','type':type(exc).__name__,'message':str(exc)[:2000]})
                if before is not None and audit['geometry_restored'] is None:
                    try:audit['geometry_restored'] = self.native_scene_query() == before
                    except BaseException as exc:
                        audit['state_capture_errors'].append({'stage':'geometry_after','type':type(exc).__name__,'message':str(exc)[:2000]})
                audit['restored'] = (audit['before'] is not None and audit['after'] is not None
                    and audit['before'] == audit['after'] and audit['geometry_restored'] is True
                    and not audit['state_capture_errors'])
            if caught is not None or not audit['restored']:
                if audit['error'] is None:
                    audit['error'] = {'type':'EpisodeUncertain','message':'native_render_state_not_restored_or_unavailable'}
                if state.get('record', {}).get('frozen_reason') is None:
                    state['record']['frozen_reason'] = 'native_render_failed_or_not_restored'
                if caught is not None:raise caught
                raise EpisodeUncertain('native_render_state_not_restored_or_unavailable')
            audit['status'] = 'completed'
            return result

    def native_look_multiscale(self, view):
        """One atomic overview/detail opportunity, never an action capability."""
        self._main_thread()
        with self._lock:
            import base64
            module,state=self._episode_store() or (None,None)
            if module is None:raise EpisodePrewriteRefused('episode_not_bound')
            sequence=getattr(self,'_native_multiscale_sequence',0)+1
            self._native_multiscale_sequence=sequence
            bundle={'schema_version':'native-multiscale-audit-v1','protocol':self.native_multiscale_protocol,
                'status':'failed','view':view,'sequence':sequence,'native_revision_before':None,
                'native_revision_after':None,'plan':None,'frames':[],'error':None,'execution_authority':False}
            self._last_native_multiscale_audit=bundle
            render_start=getattr(self,'_native_render_sequence',0)
            active_kind='overview';proof=[]
            try:
                status=self.owned_episode_status();native=self.native_scene_query()
                if time.perf_counter_ns()>=status['deadline_ns']:
                    raise EpisodePrewriteRefused('native_multiscale_original_deadline_expired')
                bundle['native_revision_before']=native['revision']
                focal=status['binding']['focal_id']
                actual=next((obj for obj in self._objects(self._depsgraph()) if self.object_id(obj)==focal),None)
                if actual is None:raise EpisodePrewriteRefused('native_multiscale_focal_missing')
                plan,overview_frame,detail_frame=module.plan_native_multiscale(native,focal,view,self._scale(),
                    focal_hidden_render=bool(getattr(actual,'hide_render',False)))
                bundle['plan']=json.loads(json.dumps(plan,allow_nan=False))
                images={}
                for kind,frame in [('overview',overview_frame)]+([('detail',detail_frame)] if detail_frame is not None else []):
                    active_kind=kind;proof=[]
                    if time.perf_counter_ns()>=status['deadline_ns']:
                        raise EpisodePrewriteRefused('native_multiscale_original_deadline_expired')
                    image=self._native_render_view(view,frame=frame,
                        coverage='all_native_vertices' if kind=='overview' else 'intentional_local_window',
                        expected_native=native,frustum_sink=proof)
                    if len(proof)!=1:raise EpisodeUncertain('native_multiscale_frustum_missing')
                    raw=base64.b64decode(image['image_base64'],validate=True)
                    bundle['frames'].append({'kind':kind,'png_sha256':hashlib.sha256(raw).hexdigest(),
                        'render_audit':self.last_native_render_audit(),'frustum':proof[0]})
                    images[kind]=image
                after=self.native_scene_query();bundle['native_revision_after']=after['revision']
                if after!=native:raise EpisodeUncertain('native_multiscale_revision_changed_after_render')
                bundle['status']='completed'
                return {'overview':images['overview'],'detail':images.get('detail'),
                    'plan':json.loads(json.dumps(plan,allow_nan=False))}
            except BaseException as exc:
                bundle['error']={'type':type(exc).__name__,'message':str(exc)[:2000]}
                latest=self.last_native_render_audit()
                recorded=[item['render_audit']['sequence'] for item in bundle['frames']]
                if latest['sequence']>render_start and latest['sequence'] not in recorded:
                    bundle['frames'].append({'kind':active_kind,'png_sha256':None,
                        'render_audit':latest,'frustum':proof[0] if len(proof)==1 else None})
                try:bundle['native_revision_after']=self.native_scene_query()['revision']
                except BaseException:pass
                if state.get('record',{}).get('frozen_reason') is None:
                    state['record']['frozen_reason']='native_multiscale_failed_or_not_restored'
                raise

    def last_native_multiscale_audit(self):
        """Owner-private bundle; images are published only after every audit."""
        self._main_thread()
        with self._lock:
            if not hasattr(self,'_last_native_multiscale_audit'):
                return {'schema_version':'native-multiscale-audit-v1','protocol':self.native_multiscale_protocol,
                    'status':'not_captured','view':None,'sequence':0,'native_revision_before':None,
                    'native_revision_after':None,'plan':None,'frames':[],'error':None,'execution_authority':False}
            return json.loads(json.dumps(self._last_native_multiscale_audit,allow_nan=False))

    def native_observation_capabilities(self):
        """Negotiate an independent read channel without capturing or binding."""
        from pathlib import Path
        sources=self._readonly_dependency_sources()
        clock=self._readonly_clock_module(sources)
        # Fixed MCP/owned loaders set this from the exact bytes they compiled.
        # Direct imports retain the legacy on-disk descriptor, without claiming
        # that an arbitrary importer proved which host bytes it executed.
        source_sha=globals().get('_READONLY_LOADED_HOST_SHA256')
        if source_sha is None:source_sha=hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
        return {'schema_version':'native-readonly-capabilities-v1',
            'protocol':self.native_observation_protocol,'process_id':os.getpid(),
            'clock':clock.counter_descriptor(),
            'max_duration_ns':30_000_000_000,'host_source_sha256':source_sha,
            'read_only':True,'execution_authority':False}

    @staticmethod
    def _readonly_dependency_sources():
        """Recheck fixed siblings even when a trusted compiled module is warm."""
        from pathlib import Path
        root=Path(__file__).resolve().parent
        sources={}
        for name,expected in _READONLY_DEPENDENCY_SHA256.items():
            source=root/name
            try:
                if source.resolve()!=source or not source.is_file():
                    raise BlenderHostError('readonly_dependency_root_or_file_invalid:'+name)
                with source.open('rb') as stream:raw=stream.read(_READONLY_SOURCE_LIMIT+1)
            except OSError as exc:
                raise BlenderHostError('readonly_dependency_unavailable:'+name) from exc
            if len(raw)>_READONLY_SOURCE_LIMIT or hashlib.sha256(raw).hexdigest()!=expected:
                raise BlenderHostError('readonly_dependency_source_mismatch:'+name)
            sources[name]=(source,raw)
        return sources

    @staticmethod
    def _readonly_checked_module(source, raw, name):
        """Compile the verified snapshot, never a second read or cached pyc."""
        import importlib.util
        spec=importlib.util.spec_from_file_location(name,source)
        if spec is None or spec.loader is None:raise BlenderHostError('Readonly native helpers unavailable')
        module=importlib.util.module_from_spec(spec)
        _exec_source_snapshot(module,source,raw)
        return module

    def _readonly_clock_module(self, sources=None):
        """An independently checked clock; never reuse the action loader cache."""
        if sources is None:sources=self._readonly_dependency_sources()
        module=getattr(self,'_readonly_clock_module_cache',None)
        if module is None:
            module=self._readonly_checked_module(*sources['forward_deadline.py'],
                '_human_eye_readonly_native_clock')
            self._readonly_clock_module_cache=module
        return module

    def _readonly_native_module(self):
        """Load stateless render helpers; never ask for an action episode."""
        sources=self._readonly_dependency_sources()
        module=getattr(self,'_readonly_native_module_cache',None)
        if module is None:
            module=self._readonly_checked_module(*sources['episode_gateway.py'],
                '_human_eye_readonly_native_render')
            self._readonly_native_module_cache=module
        return module

    def _material_readview_preflight(self, binding):
        """Candidate-only static appearance domain; never a motion admission."""
        from pathlib import Path
        self._main_thread()
        if not getattr(self, '_material_readview_only', False):
            raise EpisodePrewriteRefused('material_readview_owned_readonly_worker_required')
        keys={'schema','source_path','source_sha256','target_id','view','center_world_m','span_m'}
        if (type(binding) is not dict or set(binding)!=keys or binding['schema']!='static-material-readview-v1'
                or binding['view']!='head_front' or not _hex_string(binding['source_sha256'],64)
                or type(binding['target_id']) is not str or len(binding['target_id'])>256
                or type(binding['center_world_m']) is not list or len(binding['center_world_m'])!=3
                or any(type(v) not in (float,int) or not math.isfinite(v) for v in binding['center_world_m'])
                or type(binding['span_m']) not in (float,int) or not .01<=binding['span_m']<=1.):
            raise EpisodePrewriteRefused('material_readview_binding_invalid')
        path=Path(binding['source_path']).resolve()
        if (path!=Path(self.bpy.data.filepath).resolve() or not path.is_file()
                or path.stat().st_size>64*1024*1024
                or hashlib.sha256(path.read_bytes()).hexdigest()!=binding['source_sha256']):
            raise EpisodePrewriteRefused('material_readview_source_changed')
        objects=list(self.scene.objects)
        if len(objects)>32:raise EpisodePrewriteRefused('material_readview_object_budget')
        counts={'vertices':0,'edges':0,'polygons':0,'corners':0,'triangles':0}
        for obj in objects:
            if (getattr(obj,'library',None) is not None or getattr(obj,'animation_data',None) is not None
                    or len(obj.constraints) or getattr(obj,'parent',None) is not None):
                raise EpisodePrewriteRefused('material_readview_static_source_required')
            if obj.type not in ('MESH','CAMERA','LIGHT','EMPTY'):
                raise EpisodePrewriteRefused('material_readview_object_type_unsupported')
            if obj.type!='MESH':continue
            if len(obj.modifiers) or obj.data.shape_keys is not None:
                raise EpisodePrewriteRefused('material_readview_static_mesh_required')
            mesh=obj.data
            for name,amount in [('vertices',len(mesh.vertices)),('edges',len(mesh.edges)),
                    ('polygons',len(mesh.polygons)),('corners',len(mesh.loops)),
                    ('triangles',sum(max(0,p.loop_total-2) for p in mesh.polygons))]:counts[name]+=amount
            if (counts['vertices']>32768 or counts['triangles']>65536 or counts['corners']>262144
                    or counts['edges']>131072 or counts['polygons']>65536):
                raise EpisodePrewriteRefused('material_readview_geometry_budget')
        target=next((obj for obj in objects if obj.type=='MESH' and self.object_id(obj)==binding['target_id']),None)
        if target is None:raise EpisodePrewriteRefused('material_readview_target_missing')
        if target.hide_render or target.name not in self.view_layer.objects:
            raise EpisodePrewriteRefused('material_readview_target_hidden')
        if (not self.view_layer.use or not bool(getattr(target,'visible_camera',True))
                or bool(getattr(target,'is_holdout',False)) or bool(getattr(target,'is_shadow_catcher',False))):
            raise EpisodePrewriteRefused('material_readview_target_not_camera_visible')
        def visible_path(node,blocked=False):
            blocked=blocked or node.exclude or node.holdout or node.indirect_only or node.collection.hide_render
            return ((not blocked and target.name in node.collection.objects)
                or any(visible_path(child,blocked) for child in node.children))
        if not visible_path(self.view_layer.layer_collection):
            raise EpisodePrewriteRefused('material_readview_target_collection_hidden')
        compositor=getattr(self.scene,'compositing_node_group',None) or getattr(self.scene,'node_tree',None)
        sequence=getattr(self.scene,'sequence_editor',None)
        strips=getattr(sequence,'strips',getattr(sequence,'sequences_all',())) if sequence else ()
        if (self.scene.animation_data is not None or compositor is not None and len(compositor.nodes)
                or len(strips)):
            raise EpisodePrewriteRefused('material_readview_pipeline_unsupported')
        counts.update(source_bytes=path.stat().st_size,linear_work_units=sum(counts.values()))
        return target,counts

    def _material_readview_store(self):
        namespace=self.bpy.app.driver_namespace
        key='_human_eye_static_material_readview_v1'
        if key not in namespace:
            namespace[key]={'requests':{},'attempts':0,'constructed':0,'returned':0,'active':False,
                'quarantined':False,'binding':None,'last_audit':None}
        return namespace[key]

    def material_readview_header(self, binding):
        with self._lock:
            target,counts=self._material_readview_preflight(binding)
            store=self._material_readview_store();digest=_digest(binding)
            if store['quarantined'] or store['active']:raise EpisodePrewriteRefused('material_readview_worker_unavailable')
            if store['binding'] is not None and store['binding']!=digest:
                raise EpisodePrewriteRefused('material_readview_worker_rebinding_forbidden')
            store['binding']=digest
            module=self._readonly_native_module()
            state=self._episode_call(module,'material_readview_state',self.bpy,self.scene,self.view_layer,target)
            evidence=self.capture_readonly_evidence()
            return {'protocol':'static-material-readview-v1','binding':binding,'binding_digest':digest,
                'appearance':state,'capture_revision':evidence['capture']['revision'],'counts':counts,
                'saved_frame':self.scene.frame_current,'process_id':os.getpid(),
                'clock':self._readonly_clock_module().counter_descriptor(),
                'read_only':True,'execution_authority':False,'max_attempts':2,
                'geometry_limits':{'vertices':32768,'triangles':65536,'corners':262144},
                'native_packet_bytes':len(json.dumps(evidence['native_scene'],allow_nan=False).encode('utf8'))}

    def last_material_readview_audit(self):
        return json.loads(json.dumps(self._material_readview_store()['last_audit'],allow_nan=False))

    def observe_material_readview(self, request_id, binding, expected_fingerprint, deadline_ns):
        """An image is constructed evidence, never confirmed consumer delivery."""
        self._main_thread()
        with self._lock:
            self._readonly_request_id(request_id)
            now=time.perf_counter_ns()
            if type(deadline_ns) is not int or not now<deadline_ns<=now+30_000_000_000:
                raise EpisodePrewriteRefused('material_readview_deadline_invalid')
            store=self._material_readview_store()
            if store['active'] or store['quarantined']:raise EpisodePrewriteRefused('material_readview_worker_unavailable')
            if request_id in store['requests']:raise EpisodePrewriteRefused('material_readview_request_reused')
            if len(store['requests'])>=16:raise EpisodePrewriteRefused('material_readview_request_budget')
            store['requests'][request_id]=True;store['active']=True
            audit={'protocol':'static-material-readview-v1','request_id':request_id,'status':'failed',
                'clock':self._readonly_clock_module().counter_descriptor(),
                'started_ns':now,'deadline_ns':deadline_ns,'finished_ns':None,'render_attempted':False,
                'image_constructed':False,'image_returned_to_transport':False,'restored':None,
                'error':None,'read_only':True,'execution_authority':False}
            store['last_audit']=audit;constructed={};before=None;result=None
            try:
                target,counts=self._material_readview_preflight(binding)
                if store['binding']!=_digest(binding):raise EpisodePrewriteRefused('material_readview_binding_changed')
                module=self._readonly_native_module()
                before=self._episode_call(module,'material_readview_state',self.bpy,self.scene,self.view_layer,target)
                if (not _hex_string(expected_fingerprint,64) or before['fingerprint']!=expected_fingerprint):
                    raise EpisodePrewriteRefused('material_readview_stale_appearance')
                evidence=self.capture_readonly_evidence();native=evidence['native_scene'];scale=self._scale()
                center=[v/scale for v in binding['center_world_m']]
                frame={'center_bu':center,'direction':[1.,0.,0.],'right':[0.,1.,0.],'up':[0.,0.,1.],
                    'camera_location_bu':[center[0]+4./scale,center[1],center[2]],
                    'ortho_scale_bu':binding['span_m']/scale,'clip_start_bu':.001/scale,'clip_end_bu':10./scale}
                if time.perf_counter_ns()>=deadline_ns:raise EpisodePrewriteRefused('material_readview_deadline_expired')
                if store['attempts']>=2:raise EpisodePrewriteRefused('material_readview_render_budget')
                store['attempts']+=1;audit['render_attempted']=True
                result=self._episode_call(module,'native_material_readview',self.bpy,self.scene,self.view_layer,
                    native,binding['view'],frame=frame,constructed_sink=constructed)
                after=self._episode_call(module,'material_readview_state',self.bpy,self.scene,self.view_layer,target)
                audit['restored']=after==before and self.capture_readonly_evidence()==evidence
                if not audit['restored']:raise EpisodeUncertain('material_readview_state_not_restored')
                self._material_readview_preflight(binding)
                if time.perf_counter_ns()>=deadline_ns:raise EpisodePrewriteRefused('material_readview_deadline_expired_after_render')
                if not constructed.get('image_constructed'):raise EpisodeUncertain('material_readview_construction_receipt_missing')
                audit.update(status='ready',image_returned_to_transport=True)
                store['returned']+=1
                return {'protocol':'static-material-readview-v1','request_id':request_id,'binding':binding,
                    'binding_digest':store['binding'],'appearance':before,'counts':counts,'image':result,
                    'expected_appearance_fingerprint':expected_fingerprint,
                    'audit':audit,'delivery':'constructed_not_confirmed_model_read','read_only':True,'execution_authority':False}
            except BaseException as exc:
                audit['error']={'type':type(exc).__name__,'message':str(exc)[:2000]}
                if before is not None:
                    try:audit['restored']=self._episode_call(module,'material_readview_state',self.bpy,self.scene,self.view_layer,target)==before
                    except BaseException:audit['restored']=False
                if audit['restored'] is False:store['quarantined']=True
                return {'protocol':'static-material-readview-v1','request_id':request_id,'status':'unavailable',
                    'binding':binding,'binding_digest':store['binding'],'appearance':before,
                    'expected_appearance_fingerprint':expected_fingerprint,
                    'audit':audit,'image':None,'read_only':True,'execution_authority':False}
            finally:
                if constructed.get('image_constructed'):
                    store['constructed']+=1;audit.update(image_constructed=True,
                        png_sha256=constructed.get('sha256'),png_bytes=constructed.get('bytes'))
                audit.update(finished_ns=time.perf_counter_ns(),attempts_spent=store['attempts'],
                    constructed_spent=store['constructed'],returned_to_transport=store['returned'])
                store['active']=False

    @staticmethod
    def _readonly_request_id(value):
        if (type(value) is not str or not 1<=len(value)<=128
                or any(not (character.isascii() and (character.isalnum() or character in '_.:-')) for character in value)):
            raise EpisodePrewriteRefused('readonly_observation_request_id_invalid')
        return value

    def _readonly_observation_store(self, *, create=False):
        """Ephemeral bounded read state, separate from every writer registry.

        BlenderMCPHost creates a new bridge object on every request, so neither
        quarantine nor deduplication may live only on the Python host instance.
        Expired IDs may be pruned; this is not unbounded historical exactly-once.
        """
        namespace=getattr(getattr(self.bpy,'app',None),'driver_namespace',None)
        if type(namespace) is not dict:
            if create:raise EpisodePrewriteRefused('readonly_observation_namespace_required')
            return None
        key='_human_eye_native_readonly_observation_v1'
        if key not in namespace:
            if not create:return None
            namespace[key]={'schema_version':'native-readonly-observation-store-v1',
                'seen':{},'active_request_id':None,'sequence':0,'render_sequence':0,
                'quarantined':False,'quarantine_reason':None,'last_audit':None}
        store=namespace[key]
        expected={'schema_version','seen','active_request_id','sequence','render_sequence',
            'quarantined','quarantine_reason','last_audit'}
        if (type(store) is not dict or set(store)!=expected
                or store['schema_version']!='native-readonly-observation-store-v1'
                or type(store['seen']) is not dict or len(store['seen'])>128
                or type(store['quarantined']) is not bool
                or any(type(store[field]) is not int or not 0<=store[field]<(1<<63)
                    for field in ('sequence','render_sequence'))
                or store['quarantine_reason'] is not None and type(store['quarantine_reason']) is not str
                or store['last_audit'] is not None and type(store['last_audit']) is not dict
                or store['active_request_id'] is not None and store['active_request_id'] not in store['seen']):
            raise EpisodeUncertain('readonly_observation_store_invalid')
        for request,deadline in store['seen'].items():
            self._readonly_request_id(request)
            if type(deadline) is not int or not 0<deadline<(1<<63):
                raise EpisodeUncertain('readonly_observation_store_invalid')
        return store

    def _readonly_render_view(self, module, store, view, *, frame, coverage,
                              expected_evidence, audit_sink, frustum_sink):
        """Restore one read-only frame without consulting the action stores."""
        store['render_sequence']+=1
        audit={'schema_version':'native-render-audit-v1','protocol':self.native_render_audit_protocol,
            'status':'failed','view':view,'sequence':store['render_sequence'],'before':None,'after':None,
            'restored':False,'geometry_restored':None,'error':None,
            'state_capture_errors':[],'execution_authority':False}
        audit_sink.append(audit);before=result=caught=None
        try:
            audit['before']=self._episode_call(module,'native_render_state',self.bpy,self.scene,self.view_layer)
            before=self.capture_readonly_evidence()
            if before!=expected_evidence:
                raise EpisodeUncertain('readonly_observation_changed_before_render')
            result=self._episode_call(module,'native_look',self.bpy,self.scene,self.view_layer,before['native_scene'],view,
                _frame=frame,_screen_coverage=coverage,_frustum_sink=frustum_sink)
            audit['geometry_restored']=self.capture_readonly_evidence()==before
            if not audit['geometry_restored']:raise EpisodeUncertain('readonly_observation_render_changed_geometry')
        except BaseException as exc:
            caught=exc;audit['error']={'type':type(exc).__name__,'message':str(exc)[:2000]}
        finally:
            try:audit['after']=self._episode_call(module,'native_render_state',self.bpy,self.scene,self.view_layer)
            except BaseException as exc:
                audit['state_capture_errors'].append({'stage':'after','type':type(exc).__name__,'message':str(exc)[:2000]})
            if before is not None and audit['geometry_restored'] is None:
                try:audit['geometry_restored']=self.capture_readonly_evidence()==before
                except BaseException as exc:
                    audit['state_capture_errors'].append({'stage':'geometry_after','type':type(exc).__name__,'message':str(exc)[:2000]})
            audit['restored']=(audit['before'] is not None and audit['after'] is not None
                and audit['before']==audit['after'] and audit['geometry_restored'] is True
                and not audit['state_capture_errors'])
        if caught is not None or not audit['restored']:
            if audit['error'] is None:audit['error']={'type':'EpisodeUncertain','message':'readonly_render_restoration_unconfirmed'}
            if caught is not None:raise caught
            raise EpisodeUncertain('readonly_render_restoration_unconfirmed')
        audit['status']='completed'
        return result

    def observe_readonly_native(self, request_id, focal_id, reference_id,
                                expected_capture_revision, deadline_ns, view='SCENE'):
        """One finite visual lease; its result can never authorize a setter.

        A successful response carries its own complete evidence and audit. This
        avoids a second-call race through a freshly loaded Blender bridge. No
        action-episode state, budget, deadline or historical receipt is reset.
        """
        self._main_thread()
        with self._lock:
            import base64
            self._readonly_request_id(request_id)
            if (any(type(identity) is not str or not identity or len(identity)>256
                    for identity in (focal_id,reference_id,expected_capture_revision))
                    or focal_id==reference_id or view not in ('XY','XZ','SCENE')):
                raise EpisodePrewriteRefused('readonly_observation_arguments_invalid')
            now=time.perf_counter_ns()
            if type(deadline_ns) is not int or not now<deadline_ns<=now+30_000_000_000:
                raise EpisodePrewriteRefused('readonly_observation_original_qpc_window_required')
            module=self._readonly_native_module();store=self._readonly_observation_store(create=True)
            if store['quarantined']:raise EpisodeUncertain('readonly_observation_quarantined')
            if store['active_request_id'] is not None:raise EpisodePrewriteRefused('readonly_observation_busy')
            # Prune only expired read IDs. No live lease is evicted or renewed.
            store['seen']={key:limit for key,limit in store['seen'].items() if limit>now}
            if request_id in store['seen']:raise EpisodePrewriteRefused('readonly_observation_request_reused')
            if len(store['seen'])>=128:raise EpisodePrewriteRefused('readonly_observation_capacity')
            store['seen'][request_id]=deadline_ns;store['active_request_id']=request_id;store['sequence']+=1
            bundle={'schema_version':'native-multiscale-audit-v1','protocol':self.native_multiscale_protocol,
                'status':'failed','view':view,'sequence':store['sequence'],'native_revision_before':None,
                'native_revision_after':None,'plan':None,'frames':[],'error':None,'execution_authority':False}
            observation={'schema_version':'native-readonly-observation-v1','protocol':self.native_observation_protocol,
                'request_id':request_id,'view':view,'status':'failed','expected_capture_revision':expected_capture_revision,
                'binding':None,'started_ns':now,'deadline_ns':deadline_ns,'finished_ns':None,
                'capture_revision_before':None,'capture_revision_after':None,
                'native_revision_before':None,'native_revision_after':None,'geometry_restored':None,
                'state_restored':True,'quarantined':False,'error':None,'bundle':bundle,
                'read_only':True,'execution_authority':False}
            store['last_audit']=observation
            evidence=None;frame_audits=[];proof=[];active_kind='overview'
            try:
                evidence=self.capture_readonly_evidence();native=evidence['native_scene'];capture=evidence['capture']
                observation.update(capture_revision_before=capture['revision'],native_revision_before=native['revision'])
                bundle['native_revision_before']=native['revision']
                if capture['revision']!=expected_capture_revision:
                    raise EpisodePrewriteRefused('readonly_observation_stale_capture')
                identities={obj['object_id'] for obj in native['objects']}
                if focal_id not in identities or reference_id not in identities:
                    raise EpisodePrewriteRefused('readonly_observation_pair_missing')
                binding=self._motion_binding(capture,focal_id,reference_id)
                observation['binding']={**binding,'process_id':os.getpid()}
                if time.perf_counter_ns()>=deadline_ns:raise EpisodePrewriteRefused('readonly_observation_deadline_expired')
                actual_pair={self.object_id(obj):obj for obj in self._objects(self._depsgraph())}
                actual=actual_pair.get(focal_id);actual_reference=actual_pair.get(reference_id)
                if actual is None:raise EpisodePrewriteRefused('readonly_observation_focal_missing')
                if actual_reference is None:raise EpisodePrewriteRefused('readonly_observation_reference_missing')
                plan,overview_frame,detail_frame=self._episode_call(module,'plan_readonly_dense_focus',native,focal_id,reference_id,view,self._scale(),
                    focal_hidden_render=bool(getattr(actual,'hide_render',False)),
                    reference_hidden_render=bool(getattr(actual_reference,'hide_render',False)))
                plan['budget_scope']='per_call_readonly_observation_lease_deadline'
                bundle['plan']=json.loads(json.dumps(plan,allow_nan=False))
                images={}
                for kind,frame in [('overview',overview_frame)]+([('detail',detail_frame)] if detail_frame is not None else []):
                    active_kind=kind;frame_audits=[];proof=[]
                    if time.perf_counter_ns()>=deadline_ns:raise EpisodePrewriteRefused('readonly_observation_deadline_expired')
                    frame_view=plan['task_feature']['detail_view'] if kind=='detail' and plan['schema_version']=='native-task-gap-plan-v2' else view
                    image=self._readonly_render_view(module,store,frame_view,frame=frame,
                        coverage='all_native_vertices' if kind=='overview' else 'intentional_local_window',
                        expected_evidence=evidence,audit_sink=frame_audits,frustum_sink=proof)
                    if len(proof)!=1:raise EpisodeUncertain('readonly_observation_frustum_missing')
                    raw=base64.b64decode(image['image_base64'],validate=True)
                    bundle['frames'].append({'kind':kind,'png_sha256':hashlib.sha256(raw).hexdigest(),
                        'render_audit':frame_audits[0],'frustum':proof[0]})
                    images[kind]=image
                after=self.capture_readonly_evidence()
                observation.update(capture_revision_after=after['capture']['revision'],
                    native_revision_after=after['native_scene']['revision'],geometry_restored=after==evidence)
                bundle['native_revision_after']=after['native_scene']['revision']
                observation['state_restored']=all(item['render_audit']['restored'] for item in bundle['frames'])
                if not observation['geometry_restored']:raise EpisodeUncertain('readonly_observation_changed_after_render')
                if not observation['state_restored']:raise EpisodeUncertain('readonly_observation_state_not_restored')
                finished=time.perf_counter_ns()
                if finished>=deadline_ns:raise EpisodePrewriteRefused('readonly_observation_deadline_expired')
                observation.update(finished_ns=finished,status='completed');bundle['status']='completed'
                return {'evidence':evidence,'overview':images['overview'],'detail':images.get('detail'),
                    'plan':json.loads(json.dumps(plan,allow_nan=False)),
                    'observation':json.loads(json.dumps(observation,allow_nan=False))}
            except BaseException as exc:
                error={'type':type(exc).__name__,'message':str(exc)[:2000]}
                observation['error']=error;bundle['error']=dict(error)
                recorded={item['render_audit']['sequence'] for item in bundle['frames']}
                for audit in frame_audits:
                    if audit['sequence'] not in recorded:
                        bundle['frames'].append({'kind':active_kind,'png_sha256':None,
                            'render_audit':audit,'frustum':proof[0] if len(proof)==1 else None})
                observation['state_restored']=all(item['render_audit']['restored'] for item in bundle['frames'])
                if evidence is not None:
                    try:
                        after=self.capture_readonly_evidence()
                        observation.update(capture_revision_after=after['capture']['revision'],
                            native_revision_after=after['native_scene']['revision'],geometry_restored=after==evidence)
                        bundle['native_revision_after']=after['native_scene']['revision']
                    except BaseException:observation['geometry_restored']=None
                if bundle['frames'] and (not observation['state_restored'] or observation['geometry_restored'] is not True):
                    store['quarantined']=True;store['quarantine_reason']='readonly_native_restoration_unconfirmed'
                observation['quarantined']=store['quarantined'];observation['finished_ns']=time.perf_counter_ns()
                raise
            finally:
                store['active_request_id']=None

    def last_readonly_native_audit(self, request_id):
        """Detached owner diagnostic, never a historical image or authority."""
        self._main_thread();self._readonly_request_id(request_id)
        with self._lock:
            store=self._readonly_observation_store()
            audit=store['last_audit'] if store is not None else None
            if audit is None or audit['request_id']!=request_id:
                return {'schema_version':'native-readonly-observation-unavailable-v1',
                    'protocol':self.native_observation_protocol,'request_id':request_id,
                    'status':'unavailable','read_only':True,'execution_authority':False}
            return json.loads(json.dumps(audit,allow_nan=False))

    def native_render_state(self):
        """Owner-private readback; this is absent from the model tool surface."""
        self._main_thread()
        with self._lock:
            # The caller must use the negotiated owned episode. This method
            # remains available for diagnostics when that episode is frozen.
            module, state = self._episode_store() or (None, None)
            if module is None:raise EpisodePrewriteRefused('episode_not_bound')
            return self._episode_call(module, 'native_render_state', self.bpy, self.scene, self.view_layer)

    def last_native_render_audit(self):
        """Last actual render record, never a replacement for fresh geometry."""
        self._main_thread()
        with self._lock:
            if not hasattr(self, '_last_native_render_audit'):
                return {'schema_version':'native-render-audit-v1','protocol':self.native_render_audit_protocol,
                    'status':'not_captured','view':None,'sequence':0,'before':None,'after':None,
                    'restored':False,'geometry_restored':None,'error':None,
                    'state_capture_errors':[],'execution_authority':False}
            return json.loads(json.dumps(self._last_native_render_audit, allow_nan=False))

    def native_transform(self, object_id, delta_world_m, expected_revision):
        """Explicit world-Z write under the original owner episode meter."""
        self._main_thread()
        with self._lock:
            status = self.owned_episode_status()
            if self._active_motion() is not None:
                raise EpisodePrewriteRefused('native_blocked_by_active_or_unresolved_goal')
            if object_id != status['binding']['focal_id']:
                raise EpisodePrewriteRefused('native_wrong_object')
            try:delta = _vector(delta_world_m, 'delta_world_m')
            except BlenderHostError as exc:raise EpisodePrewriteRefused('native_finite_delta_required') from exc
            if delta[:2] != [0., 0.]:raise EpisodePrewriteRefused('native_world_z_only')
            before = self.native_scene_query()
            if type(expected_revision) is not str or expected_revision != before['revision']:
                raise EpisodePrewriteRefused('native_stale_revision')
            obj = next((v for v in self._objects(self._depsgraph()) if self.object_id(v) == object_id), None)
            if obj is None:raise EpisodePrewriteRefused('native_unknown_object')
            capability = self._execution_status(self._objects(self._depsgraph()))
            if not capability['supported']:raise EpisodePrewriteRefused('native_execution_unsupported')
            scale = self._scale()
            if hasattr(obj, 'location'):
                target = [float(obj.location[k]) + delta[k] / scale for k in range(3)]
                self._episode_before_setter(obj, target, '_assign_translation', preflight=True)
                if self._native_translation_is_noop(obj, target):
                    raise EpisodePrewriteRefused('native_no_effect')
                self._assign_translation(obj, target)
            else:
                # Same explicit matrix-only test-double compatibility as the
                # old host. Real bpy meshes always use the location helper.
                target = _matrix(obj.matrix_world)
                for k in range(3):target[k][3] += delta[k] / scale
                self._episode_before_setter(obj, target, '_assign_matrix', preflight=True)
                if target == _matrix(obj.matrix_world):
                    raise EpisodePrewriteRefused('native_no_effect')
                self._assign_matrix(obj, target)
            after = self.native_scene_query()
            old_position = next(v for v in before['objects'] if v['object_id'] == object_id)['matrix']
            new_position = next(v for v in after['objects'] if v['object_id'] == object_id)['matrix']
            return {'applied': True, 'object_id': object_id, 'revision': after['revision'],
                'delta_world_m': [new_position[k][3] - old_position[k][3] for k in range(3)], 'scene': after}

    def _native_translation_is_noop(self, obj, target):
        """Read-only proof for this explicit native entry, never rollback.

        Unchanged input values are always known to need no assignment. For a
        changed value, only the real bpy location/Vector storage may establish
        quantization; an injectable host keeps its original execution path.
        The caller performs the original episode preflight before this check.
        """
        previous = [float(value) for value in obj.location]
        if target == previous:
            return True
        try:
            import bpy
            from mathutils import Vector
            if (self.bpy is not bpy or not isinstance(obj, bpy.types.Object)
                    or type(obj.location) is not Vector or getattr(obj, 'bl_rna', None) is None):
                return False
            represented = [float(value) for value in Vector(target)]
            expected = [_binary32_nearest(value) for value in target]
            return (all(math.isfinite(value) for value in represented)
                and represented == expected == previous
                and [float(value) for value in obj.location] == previous)
        except (ImportError, AttributeError, ReferenceError, TypeError, ValueError, OverflowError, struct.error):
            # No storage proof is not a refusal. The existing metered setter
            # and complete native readback remain authoritative.
            return False

    def _enter_forward_setter(self):
        """Final cooperative gate adjacent to the native assignment itself.

        All proposal and register work precedes this sample. The operating
        system can still pause between the sample and assignment; this is not
        a zero-error hard realtime primitive. Rollback uses no forward context.
        """
        context = getattr(self, '_forward_setter_context', None)
        if context is not None:
            checked_ns = time.perf_counter_ns()
            wire = context['wire']
            context['checked_ns'] = checked_ns
            if checked_ns + wire['clock']['guard_ns'] >= wire['forward_deadline_ns']:
                raise _ForwardDeadlineExpired(checked_ns)
            context['entered'] = True

    def _forward_deadline_module(self):
        module = getattr(self, '_forward_module', None)
        if module is None:
            import importlib.util
            from pathlib import Path
            source = Path(__file__).resolve().with_name('forward_deadline.py')
            spec = importlib.util.spec_from_file_location('_human_eye_forward_deadline', source)
            if spec is None or spec.loader is None:
                raise BlenderHostError('Cannot load trusted forward deadline contract')
            module = importlib.util.module_from_spec(spec)
            _exec_source_snapshot(module,source)
            self._forward_module = module
        return module

    def _forward_registry(self, *, create=False):
        namespace = getattr(getattr(self.bpy, 'app', None), 'driver_namespace', None)
        key = '_human_eye_forward_deadline_requirements_v1'
        if not isinstance(namespace, dict):
            if create:raise BlenderHostError('Forward deadline requires runtime document identity')
            return None
        if key not in namespace:
            if not create:return None
            namespace[key] = {'schema_version':'host-forward-requirement-v1','records':{}}
        registry = namespace[key]
        if (type(registry) is not dict or set(registry) != {'schema_version','records'}
                or registry['schema_version'] != 'host-forward-requirement-v1'
                or type(registry['records']) is not dict or len(registry['records']) > 16):
            raise BlenderHostError('Invalid forward deadline registry')
        module = self._forward_deadline_module()
        local_clock = module.counter_descriptor()
        for identity, record in registry['records'].items():
            if (type(identity) is not str or not identity or len(identity) > 128
                    or type(record) is not dict or set(record) != {'binding','clock','process_id','base'}
                    or type(record['binding']) is not dict
                    or record['clock'] != local_clock or type(record['process_id']) is not int
                    or record['process_id'] != os.getpid()):
                raise BlenderHostError('Invalid forward deadline requirement')
            if record['base'] is not None:
                module.validate_base(record['base'], binding=record['binding'],
                    process_id=os.getpid(), goal_id=identity)
        try:
            if len(json.dumps(registry, allow_nan=False).encode('utf-8')) > 2 * 1024 * 1024:
                raise BlenderHostError('Forward deadline registry exceeds its bound')
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise BlenderHostError('Invalid bounded forward deadline registry') from exc
        return module, registry

    def _forward_profile(self, goal_id, record):
        module = self._forward_deadline_module()
        base = record['base']
        parent_open = base is not None and time.perf_counter_ns() + record['clock']['guard_ns'] < base['parent_deadline_ns']
        return {'protocol':module.PROTOCOL, 'goal_id':goal_id,
            'required':True, 'clock':json.loads(json.dumps(record['clock'])),
            'process_id':record['process_id'],
            'parent_deadline_ns':None if base is None else base['parent_deadline_ns'],
            'forward_admission_open':parent_open,
            'admission_scope':'parent window only; every forward requires its own bound token',
            'execution_authority':False}

    def require_forward_deadline(self, goal_id):
        """Trusted embedding enables a gate before a parent deadline exists."""
        self._main_thread()
        with self._lock:
            active = self._active_motion()
            if active is None or active[2] != goal_id:
                raise BlenderHostError('Forward deadline requires this active registered goal')
            motion_module, state, _ = active
            record = state['records'][goal_id]
            scene = self._capture(_native_evidence=True)['capture']
            pair = record['binding']
            binding = self._motion_binding(scene, pair['focal_id'], pair['reference_id'])
            motion_module.observe_scene(state, goal_id, binding=binding,
                world_position=self._motion_pivot(scene, pair['focal_id']),
                scene_fingerprint=_digest(scene), now=time.monotonic())
            module, registry = self._forward_registry(create=True)
            requirement = registry['records'].get(goal_id)
            if requirement is None:
                if record['events']:
                    raise BlenderHostError('Forward requirement must precede the first registered setter')
                if len(registry['records']) >= 16:
                    raise BlenderHostError('Forward requirement capacity exhausted')
                requirement = {'binding':json.loads(json.dumps(binding)),
                    'clock':module.counter_descriptor(), 'process_id':os.getpid(), 'base':None}
                registry['records'][goal_id] = requirement
            if requirement['binding'] != binding:
                raise BlenderHostError('Forward requirement object identity changed')
            return self._forward_profile(goal_id, requirement)

    def _bind_forward_base(self, base, *, before, active):
        if active is None:
            raise BlenderHostError('Forward deadline requires an active registered goal')
        _, state, goal_id = active
        store = self._forward_registry()
        if store is None or goal_id not in store[1]['records']:
            raise BlenderHostError('Forward deadline requirement must be registered first')
        module, registry = store
        requirement = registry['records'][goal_id]
        pair = state['records'][goal_id]['binding']
        binding = self._motion_binding(before, pair['focal_id'], pair['reference_id'])
        if requirement['binding'] != binding:
            raise BlenderHostError('Forward deadline document or object identity changed')
        validated = module.validate_base(base, binding=binding, process_id=os.getpid(), goal_id=goal_id)
        if requirement['base'] is None:
            requirement['base'] = validated
        elif any(requirement['base'][field] != validated[field]
                 for field in module.BASE_FIELDS if field != 'forward_deadline_ns'):
            raise BlenderHostError('The parent forward deadline cannot change or renew')
        return self._forward_profile(goal_id, requirement)

    def bind_forward_deadline(self, lease):
        self._main_thread()
        with self._lock:
            before = self._capture(_native_evidence=True)['capture']
            return self._bind_forward_base(lease, before=before, active=self._active_motion())

    def _validate_forward_context(self, token, *, before, action, expected_revision,
                                  expected_fingerprint, request_nonce):
        active = self._active_motion()
        registry = self._forward_registry()
        requirement = None if active is None or registry is None else registry[1]['records'].get(active[2])
        if requirement is None and registry is not None and registry[1]['records']:
            # Managed mode is sticky both when idle and between begin(new)
            # and require(new); neither window may reopen legacy writes.
            raise BlenderHostError('Managed host requires a new registered and authorized goal')
        if requirement is None:
            if token is not None:
                raise BlenderHostError('This host goal did not negotiate a forward deadline')
            return None
        if token is None:
            raise BlenderHostError('An active forward requirement cannot omit its deadline token')
        module = registry[0]
        pair = active[1]['records'][active[2]]['binding']
        binding = self._motion_binding(before, pair['focal_id'], pair['reference_id'])
        wire = module.validate_deadline(token, action=action, expected_revision=expected_revision,
            expected_fingerprint=expected_fingerprint, request_nonce=request_nonce,
            binding=binding, process_id=os.getpid(), goal_id=active[2])
        self._bind_forward_base({field:wire[field] for field in module.BASE_FIELDS}, before=before, active=active)
        return {'module':module,'wire':wire,'entered':False,'checked_ns':None}

    def _cancel_motion_before_entry(self, token, before):
        if token is None:return None
        module, state, goal_id, event_id = token
        pair = state['records'][goal_id]['binding']
        module.cancel_setter(state, goal_id, event_id,
            binding=self._motion_binding(before, pair['focal_id'], pair['reference_id']), now=time.monotonic())
        return event_id

    @staticmethod
    def _verify_translation_pose(obj, previous):
        current = _matrix(obj.matrix_world)
        if any(current[r][c] != previous[r][c]
               for r in range(4) for c in range(4) if c != 3 or r == 3):
            raise BlenderHostError("Translation changed the nontranslation world matrix")

    def _precision_refusal(self, *, action, before, target, scale, request_nonce,
                           expected_fingerprint):
        """Prove only an unrepresentable pivot before assigning any object.

        A detached mathutils Matrix establishes this host's binary32 storage.
        Rotation/decomposition, vertex rounding and tighter goal tolerances are
        deliberately not predicted; actual readback remains mandatory.
        """
        if request_nonce is None:
            return None  # Legacy callers do not negotiate a fresh refusal.
        if not _hex_string(request_nonce, 32) or not _hex_string(expected_fingerprint, 64):
            raise BlenderHostError("Prewrite refusal requires a nonce and scene fingerprint")
        before_pivot = next(mesh["pivot_world"] for mesh in before["meshes"] if mesh["object_id"] == action["focal_id"])
        translation = _vector(action.get("translation", [0, 0, 0]), "translation")
        requested_world = [before_pivot[i] + translation[i] for i in range(3)]
        try:
            # Any one stored candidate inside tolerance disproves a precision
            # impossibility. Avoid constructing matrices/neighbours on the
            # ordinary path; this does not authorize execution.
            candidate_errors = [abs(_binary32_nearest(x / scale) * scale - x) for x in requested_world]
            if all(error <= _READBACK_TOLERANCE_M for error in candidate_errors):
                return None
            try:
                from mathutils import Matrix
            except ImportError:
                return None  # No proven storage model for an injectable host.
            target_rounded = [_binary32_nearest(target[i][3]) for i in range(3)]
            stored = Matrix(target)
            if any(not math.isfinite(x) for x in target_rounded):
                return None
            if [float(stored[i][3]) for i in range(3)] != target_rounded:
                return None
            requested, nearest, errors = _binary32_closest_world(requested_world, scale)
            if any(not math.isfinite(x) for x in errors):
                return None
        except (OverflowError, ValueError, TypeError, struct.error):
            return None
        exceeded = [i for i in range(3) if errors[i] > _READBACK_TOLERANCE_M]
        if not exceeded:
            return None
        result = {"status": "rejected_before_mutation", "rejection": {
            "contract_revision": PREWRITE_REFUSAL_PROTOCOL, "source": "blender_scene_host",
            "code": _PREWRITE_CODE, "request_nonce": request_nonce,
            "expected_revision": before["revision"], "scene_revision": before["revision"],
            "expected_fingerprint": expected_fingerprint, "scene_fingerprint": _digest(before),
            "action_sha256": _digest(action), "focal_id": action["focal_id"],
            "mutation_started": False, "scene_unchanged": True, "reason_codes": [_PREWRITE_REASON],
            "precision": {"scope": "world_pivot_translation_only", "storage_kind": "mathutils_matrix_binary32",
                "coordinate_tolerance_m": _READBACK_TOLERANCE_M, "unit_scale_m": scale,
                "requested_translation_host_units": requested, "nearest_translation_host_units": nearest,
                "before_pivot_world_m": before_pivot, "requested_pivot_world_m": requested_world,
                "nearest_pivot_world_m": [x * scale for x in nearest], "absolute_error_m": errors,
                "exceeded_axes": exceeded, "preflight_authorizes_execution": False}}}
        validate_prewrite_refusal(result, action=action, expected_revision=before["revision"],
            expected_fingerprint=expected_fingerprint, request_nonce=request_nonce)
        return result

    def _motion_store(self, *, create=False):
        """Runtime-only state shared by fresh bridge instances in this Blender.

        This registers this adapter's setters only. Shared Blender UI and other
        scripts remain outside its coverage; no all-channel claim is made here.
        """
        namespace = getattr(getattr(self.bpy, 'app', None), 'driver_namespace', None)
        key = '_human_eye_motion_ledger_v1'
        if not isinstance(namespace, dict):
            if create:
                raise BlenderHostError('Host motion accounting requires driver namespace identity')
            return None
        if key not in namespace:
            if not create:
                return None
            namespace[key] = {}
        # The host is also imported directly inside Blender, without importing
        # the NumPy/Pillow package. Only a fixed trusted sibling may be loaded.
        import importlib.util
        from pathlib import Path
        module = getattr(self, '_motion_module', None)
        if module is None:
            source = Path(__file__).resolve().with_name('host_motion_ledger.py')
            spec = importlib.util.spec_from_file_location('_human_eye_host_motion_ledger', source)
            if spec is None or spec.loader is None:
                raise BlenderHostError('Cannot load trusted host motion accounting')
            module = importlib.util.module_from_spec(spec)
            _exec_source_snapshot(module,source)
            self._motion_module = module
        state = namespace[key]
        module.validate_ledger(state)
        return module, state

    def _active_motion(self):
        store = self._motion_store()
        if store is None:
            return None
        module, state = store
        active = [identity for identity, record in state.get('records', {}).items() if not record['closed']]
        if len(active) > 1:
            raise BlenderHostError('Multiple active host motion goals')
        return (module, state, active[0]) if active else None

    def _motion_binding(self, scene, focal_id, reference_id):
        identity = scene.get('host_identity')
        namespace = getattr(getattr(self.bpy, 'app', None), 'driver_namespace', None)
        epoch = namespace.get('_human_eye_document_epoch_v1') if isinstance(namespace, dict) else None
        if not isinstance(identity, dict) or not _hex_string(epoch, 32):
            raise BlenderHostError('Complete runtime host identity required for motion accounting')
        return {'host_epoch': epoch, 'document_epoch': identity['document_epoch'],
            'focal_id': focal_id, 'reference_id': reference_id,
            'object_instances': dict(identity['object_instances'])}

    @staticmethod
    def _motion_pivot(scene, focal_id):
        return next(mesh['pivot_world'][:] for mesh in scene['meshes'] if mesh['object_id'] == focal_id)

    @staticmethod
    def _motion_report(report):
        report['clock_domain'] = 'blender-host:' + report['binding']['document_epoch']
        report['setter_count_semantics'] = 'confirmed registered setters; a lower bound when outcomes are unknown'
        report['deadline_scope'] = 'no new forward setters after deadline; bounded rollback may finish later'
        return report

    def begin_motion_goal(self, goal_id, focal_id, reference_id, limits=None):
        """Trusted embedding bookkeeping, never task authorization or a setter."""
        self._main_thread()
        with self._lock:
            bundle = self._capture(_native_evidence=True)
            scene = bundle['capture']
            module, state = self._motion_store(create=True)
            return self._motion_report(module.begin_goal(state, goal_id,
                binding=self._motion_binding(scene, focal_id, reference_id),
                initial_world=self._motion_pivot(scene, focal_id),
                scene_fingerprint=_digest(scene), now=time.monotonic(), limits=limits))

    def motion_goal_status(self, goal_id, after_event_count=0):
        self._main_thread()
        with self._lock:
            store = self._motion_store()
            if store is None:
                raise BlenderHostError('No registered host motion history')
            module, state = store
            record = state.get('records', {}).get(goal_id)
            if not isinstance(record, dict):
                raise BlenderHostError('Unknown registered host goal')
            if not record['closed']:
                try:
                    scene = self._capture()
                    pair = record['binding']
                    module.observe_scene(state, goal_id,
                        binding=self._motion_binding(scene, pair['focal_id'], pair['reference_id']),
                        world_position=self._motion_pivot(scene, pair['focal_id']),
                        scene_fingerprint=_digest(scene), now=time.monotonic())
                except Exception:
                    try:module.mark_unknown(state, goal_id, reason='host_scene_or_identity_unavailable')
                    except module.HostMotionStopped:pass
            report = self._motion_report(module.snapshot(state, goal_id, after_event_count=after_event_count))
            requirements = self._forward_registry()
            if requirements is not None and goal_id in requirements[1]['records']:
                profile = self._forward_profile(goal_id, requirements[1]['records'][goal_id])
                report['forward_deadline_required'] = True
                report['forward_admission_open'] = profile['forward_admission_open']
                report['forward_deadline_requirement'] = profile
            return report

    def end_motion_goal(self, goal_id):
        self._main_thread()
        with self._lock:
            module, state = self._motion_store() or (None, None)
            if module is None:
                raise BlenderHostError('No registered host motion history')
            record = state.get('records', {}).get(goal_id)
            if not isinstance(record, dict):
                raise BlenderHostError('Unknown registered host goal')
            scene = self._capture()
            pair = record['binding']
            binding = self._motion_binding(scene, pair['focal_id'], pair['reference_id'])
            module.observe_scene(state, goal_id, binding=binding,
                world_position=self._motion_pivot(scene, pair['focal_id']),
                scene_fingerprint=_digest(scene), now=time.monotonic())
            return self._motion_report(module.end_goal(state, goal_id, binding=binding, now=time.monotonic()))

    def _reserve_motion_setter(self, before, action, target_world, event_id, *, kind='forward'):
        active = self._active_motion()
        if active is None:
            return None
        module, state, goal_id = active
        record = state['records'][goal_id]
        pair = record['binding']
        if (action.get('focal_id') != pair['focal_id'] or action.get('reference_id') != pair['reference_id']
                or any(action.get('rotation_euler_deg', [0, 0, 0]))
                or list(action.get('translation', [0, 0, 0]))[:2] != [0, 0]):
            raise BlenderHostError('Registered host goal permits its original pair and world Z translation only')
        binding = self._motion_binding(before, pair['focal_id'], pair['reference_id'])
        pivot = self._motion_pivot(before, pair['focal_id'])
        if kind == 'forward':
            current = module.observe_scene(state, goal_id, binding=binding,
                world_position=pivot, scene_fingerprint=_digest(before), now=time.monotonic())
            # Retain one setter and the worst-case return path for a possible
            # verified rollback. This optional registered mode is stricter than
            # the legacy unregistered host; never spend a ninth hidden setter.
            maximum = math.hypot(*_vector(action.get('translation', [0, 0, 0]), 'translation')) + math.sqrt(3.) * _READBACK_TOLERANCE_M
            if maximum > record['limits']['max_step_translation_m']:
                raise BlenderHostError('Registered step must reserve its readback precision margin')
            if current['remaining_setters'] < 2 or 2 * maximum > current['remaining_translation_m']:
                raise BlenderHostError('Host budget must retain a rollback setter and return path')
        reserved = module.reserve_setter(state, goal_id, event_id, binding=binding,
            before_world=pivot, requested_world=target_world, before_scene_fingerprint=_digest(before),
            now=time.monotonic(), kind=kind)
        if reserved['fresh_reservation'] is not True:
            raise BlenderHostError('A registered setter identity must not execute twice')
        return module, state, goal_id, event_id

    def _confirm_motion_setter(self, token, scene, *, allow_frozen=False):
        if token is None:
            return
        module, state, goal_id, event_id = token
        pair = state['records'][goal_id]['binding']
        result = module.confirm_setter(state, goal_id, event_id,
            binding=self._motion_binding(scene, pair['focal_id'], pair['reference_id']),
            after_world=self._motion_pivot(scene, pair['focal_id']),
            after_scene_fingerprint=_digest(scene), now=time.monotonic())
        if result['frozen_reason'] is not None and not allow_frozen:
            raise BlenderHostError('Registered host setter requires review: ' + result['frozen_reason'])

    @staticmethod
    def _unknown_motion_setter(token, reason):
        if token is not None:
            module, state, goal_id, event_id = token
            try:module.mark_unknown(state, goal_id, event_id=event_id, reason=reason)
            except module.HostMotionStopped:pass

    def apply_transform(self, action, expected_revision, expected_fingerprint=None, request_nonce=None,
                        forward_deadline=None):
        """Apply only explicit world-metre delta SE(3), after a fresh revision check.

        ``expected_fingerprint`` is the router's normalized scene digest. The
        connector itself does not grant collision approval: callers must obtain
        the engine gate first. Returns an actual readback, never a simulated one.
        Blender stores transforms with finite precision; consumers should compare
        coordinates with an explicit tolerance (at least 1e-6 metres).
        """
        self._main_thread()
        allowed = {"focal_id", "reference_id", "translation", "rotation_euler_deg"}
        if (not isinstance(action, dict) or set(action) - allowed
                or not {"translation", "rotation_euler_deg"}.intersection(action)
                or not isinstance(action.get("focal_id"), str)):
            raise BlenderHostError("Only an identified world-space delta SE(3) action is supported")
        translation = _vector(action.get("translation", [0, 0, 0]), "translation")
        rotation_degrees = _vector(action.get("rotation_euler_deg", [0, 0, 0]), "rotation_euler_deg")
        if not isinstance(expected_revision, str) or not expected_revision:
            raise BlenderHostError("A nonempty expected scene revision is required")
        with self._lock:
            before = self._capture()
            if before["revision"] != expected_revision:
                raise BlenderHostError("Scene revision changed before host execution")
            if expected_fingerprint is not None and expected_fingerprint != _digest(before):
                raise BlenderHostError("Scene fingerprint changed before host execution")
            forward_context = self._validate_forward_context(forward_deadline, before=before,
                action=action, expected_revision=expected_revision,
                expected_fingerprint=expected_fingerprint, request_nonce=request_nonce)
            graph = self._depsgraph()
            objects = self._objects(graph)
            by_id = {self.object_id(obj): obj for obj in objects}
            obj = by_id.get(action["focal_id"])
            if obj is None or (action.get("reference_id") is not None and action["reference_id"] not in by_id):
                raise BlenderHostError("Unknown focal or reference object")
            capability = self._execution_status(objects)
            if not capability["supported"]:
                first = capability["reasons"][0]
                raise BlenderHostError("Transforms require independent static rigid meshes with positive uniform scale: "
                                       + first["object_name"] + " (" + first["reason"] + ")")
            previous = _matrix(obj.matrix_world)
            rotation, scale = _euler_xyz(rotation_degrees), self._scale()
            target = [[sum(rotation[r][k] * previous[k][c] for k in range(3)) for c in range(3)]
                      + [previous[r][3] + translation[r] / scale] for r in range(3)]
            target.append([0., 0., 0., 1.])
            _matrix(target)
            refusal = self._precision_refusal(action=action, before=before, target=target,
                scale=scale, request_nonce=request_nonce, expected_fingerprint=expected_fingerprint)
            if refusal is not None:
                return refusal
            pure_translation = not any(rotation_degrees)
            no_op = pure_translation and not any(translation)
            previous_location = None
            if pure_translation and hasattr(obj, "location"):
                previous_location = _vector([float(value) for value in obj.location], "location")
                target_location = _vector([previous_location[i] + translation[i] / scale
                                           for i in range(3)], "target location")
            # Check the shared episode before reserving a per-goal setter or
            # entering the old rollback handler. A known refusal cannot create
            # a fake physical event or an unnecessary rollback assignment.
            if previous_location is not None and target_location != previous_location:
                self._episode_before_setter(obj, target_location, '_assign_translation', preflight=True)
            elif previous_location is None and not no_op:
                self._episode_before_setter(obj, target, '_assign_matrix', preflight=True)
            # Real bpy objects provide location. Matrix-only injectable doubles
            # retain their legacy path; a location failure never falls back to it.
            assignment_started = False
            motion_token = None
            motion_active = self._active_motion() is not None
            motion_nonce = (request_nonce if _hex_string(request_nonce, 32) else uuid.uuid4().hex) if motion_active else ''
            if getattr(self, '_forward_setter_context', None) is not None:
                raise BlenderHostError('Nested forward mutation contexts are not supported')
            self._forward_setter_context = forward_context
            try:
                if previous_location is not None:
                    if target_location != previous_location:
                        motion_token = self._reserve_motion_setter(before, action,
                            [target[r][3] * scale for r in range(3)], motion_nonce + ':forward') if motion_active else None
                        assignment_started = forward_context is None
                        self._assign_translation(obj, target_location)
                        assignment_started = True
                elif not no_op:
                    motion_token = self._reserve_motion_setter(before, action,
                        [target[r][3] * scale for r in range(3)], motion_nonce + ':forward') if motion_active else None
                    assignment_started = forward_context is None
                    self._assign_matrix(obj, target)
                    assignment_started = True
                after = self._capture()
                self._confirm_motion_setter(motion_token, after)
                if pure_translation:
                    self._verify_translation_pose(obj, previous)
                self._verify_readback(before, after, action["focal_id"], rotation, translation)
            except _ForwardDeadlineExpired as exc:
                if forward_context is None or forward_context['entered']:
                    raise BlenderHostError('Invalid forward pre-entry refusal') from exc
                cancelled_id = self._cancel_motion_before_entry(motion_token, before)
                return forward_context['module'].build_refusal(forward_context['wire'],
                    checked_ns=exc.checked_ns, cancelled_event_id=cancelled_id)
            except EpisodePrewriteRefused:
                # Only the pre-entry episode hooks can raise this exact local
                # type. Post-entry confirmation is always EpisodeUncertain.
                # Cancel the already reserved per-goal entry, without reading
                # an unchanged endpoint as a confirmed physical setter.
                if motion_token is not None:
                    self._cancel_motion_before_entry(motion_token, before)
                raise
            except Exception as exc:
                assignment_started = assignment_started or bool(forward_context and forward_context['entered'])
                # A required forward window applies only to the original
                # forward setter. Necessary bounded rollback is accounted
                # separately and must not be recast as another forward.
                self._forward_setter_context = None
                episode_store = self._episode_store()
                if episode_store is not None and assignment_started:
                    self._episode_call(episode_store[0], 'freeze_episode', episode_store[1],
                        'episode_outer_host_verification_failed')
                restored = False
                if motion_token is not None:
                    try:
                        self._confirm_motion_setter(motion_token, self._capture(), allow_frozen=True)
                    except Exception:
                        self._unknown_motion_setter(motion_token, 'registered_setter_outcome_unknown')
                try:
                    rollback_token = None
                    if assignment_started:
                        if motion_token is not None:
                            rollback_before = self._capture()
                            rollback_token = self._reserve_motion_setter(rollback_before, action,
                                [previous[r][3] * scale for r in range(3)], motion_nonce + ':rollback', kind='rollback')
                        self._episode_rollback_context = True
                        try:
                            if previous_location is not None:
                                self._assign_translation(obj, previous_location)
                            else:
                                self._assign_matrix(obj, previous)
                        finally:
                            self._episode_rollback_context = False
                    restored_scene = self._capture()
                    self._confirm_motion_setter(rollback_token, restored_scene, allow_frozen=True)
                    if pure_translation:
                        self._verify_translation_pose(obj, previous)
                    restored = restored_scene["revision"] == before["revision"]
                except Exception:
                    self._unknown_motion_setter(locals().get('rollback_token'), 'registered_rollback_outcome_unknown')
                    pass
                self._unknown_motion_setter(motion_token, 'host_execution_or_rollback_requires_review')
                raise BlenderHostError("Host execution/readback failed; rollback_verified=" + str(restored)) from exc
            finally:
                self._forward_setter_context = None
            return {"scene": after, "receipt": {"source": "blender", "host_execution_verified": True,
                    "focal_id": action["focal_id"], "before_revision": before["revision"],
                    "after_revision": after["revision"], "execution_scope": "terminal_geometry_only",
                    "coordinate_tolerance_m": 1e-6}}
