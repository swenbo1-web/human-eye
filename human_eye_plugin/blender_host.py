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
from contextlib import contextmanager


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
    'episode_gateway.py': 'b886b4b0d4da8ceaf32b952c810a9843ec4ec7d907830050db1e5b91815fe379',
    'forward_deadline.py': '72c4f6e3dba0c62f624a34f19c530b712833cbab963e13bcf9ecd34bcf5aaac2',
}
_READONLY_SOURCE_LIMIT = 256 * 1024
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


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _same_rna(left, right):
    """Blender can return different Python wrappers for the same RNA datablock."""
    if left is right:
        return True
    if left is None or right is None:
        return False
    if hasattr(left, "as_pointer") and hasattr(right, "as_pointer"):
        return left.as_pointer() == right.as_pointer()
    return False


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

    def _objects(self, graph):
        objects = list(self.scene.objects)
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

    def _identity_metadata(self, objects):
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
                'capture_scope': 'complete_scene_meshes'}

    def _capture(self, *, _native_evidence=False, _read_only_native=False):
        if type(_native_evidence) is not bool:
            raise BlenderHostError("_native_evidence must be boolean")
        if type(_read_only_native) is not bool:
            raise BlenderHostError("_read_only_native must be boolean")
        if _native_evidence and not (self.execution_metadata and self.identity_metadata):
            raise BlenderHostError("Native evidence requires explicit execution and identity metadata")
        graph, scale = self._depsgraph(), self._scale()
        objects = self._objects(graph)
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
        meshes, vertex_count, face_count = [], 0, 0
        for ordinal, obj in enumerate(objects, 1):
            evaluated = obj.evaluated_get(graph)
            if not bool(getattr(evaluated, "is_evaluated", True)):
                raise BlenderHostError("Mesh is not evaluated in the current view layer: " + obj.name)
            matrix = _matrix(evaluated.matrix_world)
            if _native_evidence and _matrix(obj.matrix_world) != matrix:
                raise BlenderHostError("Native original and evaluated world matrices disagree: " + obj.name)
            temporary = None
            try:
                temporary = evaluated.to_mesh()
                if temporary is None:
                    raise BlenderHostError("Evaluated mesh is unavailable: " + obj.name)
                temporary.calc_loop_triangles()
                if (vertex_count + len(temporary.vertices) > 500_000
                        or face_count + len(temporary.loop_triangles) > 1_000_000):
                    raise BlenderHostError("Scene geometry budget exceeded")
                vertices = []
                evaluated_local = [] if _native_evidence else None
                for vertex in temporary.vertices:
                    point = [float(vertex.co[i]) for i in range(3)]
                    if _native_evidence:
                        evaluated_local.append(point)
                    world = [(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale for r in range(3)]
                    if any(not math.isfinite(v) for v in world):
                        raise BlenderHostError("Nonfinite evaluated geometry: " + obj.name)
                    vertices.append(world)
                faces = [[int(i) for i in triangle.vertices] for triangle in temporary.loop_triangles]
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
        if self.execution_metadata:
            scene["host_execution"] = self._execution_status(objects)
        if self.identity_metadata:
            identity = self._identity_metadata(objects)
            if identity is not None:
                scene['host_identity'] = identity
        # Guard changes must invalidate approvals even if displayed geometry did
        # not move. The digest is deterministic across bridge process launches.
        scene["revision"] = "blender:" + _digest({"scene": scene, "scale_length": scale,
                "frame": int(getattr(self.scene, "frame_current", 0)),
                "guards": [[self.object_id(obj), self._guard_description(obj)] for obj in objects]})
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
            return self._capture()

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
            module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
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
        exec(compile(raw,str(source),'exec',dont_inherit=True),module.__dict__)
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
            spec.loader.exec_module(module)
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
            spec.loader.exec_module(module)
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
