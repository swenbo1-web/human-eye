"""Ordinary bounded Python over a versioned isolated geometry snapshot."""

import contextlib
import ast
import builtins
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from image_inputs import read_png_rgb
DEPS = HERE.parent / "m6_shape_pretrain_001/private/deps"
spec = importlib.util.spec_from_file_location("_refine_process_metrics", HERE.parent / "m6_task_perception_001/python_sandbox.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)

ALLOWED_IMPORTS = {
    "numpy", "numpy.linalg", "numpy.fft", "numpy.random", "numpy.polynomial",
    "scipy", "scipy.linalg", "scipy.spatial", "scipy.spatial.transform",
    "scipy.sparse", "scipy.sparse.linalg", "scipy.sparse.csgraph", "scipy.interpolate",
    "scipy.ndimage", "scipy.optimize", "scipy.signal", "scipy.stats",
    "math", "json", "statistics", "collections", "itertools", "functools", "heapq",
}
BLOCKED_ATTRIBUTES = {
    "os", "sys", "builtins", "ctypes", "ctypeslib", "cffi", "ffi", "f2py", "testing",
    "distutils", "pickle", "importlib", "inspect", "subprocess", "socket", "environ",
    "system", "popen", "spawn", "fork", "exec", "eval", "compile", "load_library",
    "LowLevelCallable", "from_address", "as_ctypes", "as_ctypes_type", "format_stack",
    "format", "format_map",
    "gi_frame", "gi_code", "cr_frame", "ag_frame", "f_globals", "f_locals", "tb_frame",
}
SAFE_BUILTINS = (
    "abs", "all", "any", "bool", "bytes", "callable", "chr", "complex", "dict", "divmod",
    "enumerate", "filter", "float", "frozenset", "hash", "hex", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "oct", "ord", "pow",
    "print", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str", "sum",
    "tuple", "type", "zip", "Exception", "ValueError", "RuntimeError", "AssertionError",
    "PermissionError", "FileNotFoundError", "ZeroDivisionError", "IndexError", "KeyError",
)
BLOCKED_NAMES = {"getattr", "setattr", "delattr", "globals", "locals", "vars", "eval", "exec", "compile", "input", "breakpoint", "help"}


def validate_code(code):
    tree = ast.parse(code, filename="<matched-consumer-python>")
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.Global, ast.Nonlocal)):
            raise PermissionError("consumer_AST_node_unavailable_" + type(node).__name__)
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in BLOCKED_NAMES):
            raise PermissionError("consumer_private_name_unavailable")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in BLOCKED_ATTRIBUTES):
            raise PermissionError("consumer_attribute_unavailable_" + node.attr)
        if isinstance(node, ast.Import):
            if any(item.name not in ALLOWED_IMPORTS for item in node.names):
                raise PermissionError("consumer_import_outside_numeric_allowlist")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in ALLOWED_IMPORTS or any(
                item.name == "*" or item.name.startswith("_") or item.name in BLOCKED_ATTRIBUTES for item in node.names
            ):
                raise PermissionError("consumer_import_outside_numeric_allowlist")
    return compile(tree, "<matched-consumer-python>", "exec")


def bounded_import(name, globals=None, locals=None, fromlist=(), level=0):
    numeric_runtime_import = name in sys.modules and name.split(".")[0] in ("numpy", "scipy")
    if level or (name not in ALLOWED_IMPORTS and not numeric_runtime_import):
        raise PermissionError("consumer_import_outside_numeric_allowlist_" + str(name))
    if any(item.startswith("_") or item in BLOCKED_ATTRIBUTES or item == "*" for item in (fromlist or ())):
        raise PermissionError("consumer_private_import_unavailable")
    return builtins.__import__(name, globals, locals, fromlist, 0)


def geometry_digest(*arrays):
    import numpy as np
    result = hashlib.sha256()
    for value in arrays:
        value = np.ascontiguousarray(value)
        result.update(json.dumps(dict(dtype=str(value.dtype), shape=list(value.shape)), sort_keys=True).encode())
        result.update(value.tobytes())
    return result.hexdigest()


LOCAL_SUPPORT_FIELDS = {
    "fit_target_source_ids", "fit_target_support_mask", "fit_target_support_count", "fit_target_design_rank",
    "fit_target_angular_bins", "fit_target_condition_number", "fit_target_nearest_distance_m",
    "fit_target_farthest_distance_m", "fit_target_max_angular_gap_rad", "fit_target_normal_dot_minimum",
    "fit_target_normals",
}


def validate_local_support_fields(fields, arrays):
    """Check optional local fitting membership against this exact current mesh."""
    import numpy as np
    present = LOCAL_SUPPORT_FIELDS & set(fields)
    if not present:
        return
    if present != LOCAL_SUPPORT_FIELDS:
        raise ValueError("local_fit_packet_requires_complete_field_group")
    targets = fields["fit_target_source_ids"]
    support_ids = fields["source_ids"]
    mask = fields["fit_target_support_mask"]
    if np.any(np.diff(support_ids) <= 0):
        raise ValueError("local_fit_outer_pool_requires_sorted_unique_source_ids")
    if targets.ndim != 1 or not np.issubdtype(targets.dtype, np.integer) or len(targets) != 69:
        raise ValueError("local_fit_targets_require_69_integer_source_ids")
    if not np.isin(targets, arrays["I_ids"]).all() or np.any(np.diff(targets) <= 0):
        raise ValueError("local_fit_targets_require_sorted_unique_editable_source_ids")
    if mask.dtype != np.bool_ or mask.shape != (len(support_ids), len(targets)):
        raise ValueError("local_fit_support_membership_shape_invalid")
    for key in LOCAL_SUPPORT_FIELDS - {"fit_target_source_ids", "fit_target_support_mask", "fit_target_normals"}:
        if fields[key].shape != targets.shape:
            raise ValueError("local_fit_target_metric_shape_invalid")
    for key in ("fit_target_support_count", "fit_target_design_rank", "fit_target_angular_bins"):
        if not np.issubdtype(fields[key].dtype, np.integer):
            raise ValueError("local_fit_counts_and_ranks_require_integer_arrays")
    if fields["fit_target_normals"].shape != (len(targets), 3):
        raise ValueError("local_fit_target_normal_shape_invalid")
    if "attention" in fields and np.any(fields["attention"] != 0):
        raise ValueError("local_fit_outer_pool_requires_zero_attention")
    if "incident_face_visible" in fields and not fields["incident_face_visible"].any(axis=1).all():
        raise ValueError("local_fit_outer_pool_requires_incident_face_observation")
    vertices, faces = arrays["vertices"], arrays["faces"]
    triangle = vertices[faces]
    cross = np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0])
    accumulated = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(accumulated, faces[:, corner], cross)
    length = np.linalg.norm(accumulated, axis=1)
    normals = np.divide(accumulated, length[:, None], out=np.zeros_like(vertices), where=length[:, None] > 0)
    if not np.allclose(fields["fit_target_normals"], normals[targets], rtol=0, atol=1e-12):
        raise ValueError("local_fit_target_normals_are_not_current_area_weighted_normals")
    if not np.allclose(fields["current_vertex_normals"], normals[support_ids], rtol=0, atol=1e-12):
        raise ValueError("local_fit_support_normals_are_not_current_area_weighted_normals")
    for column, target in enumerate(targets):
        delta = vertices[support_ids] - vertices[target]
        distances = np.linalg.norm(delta, axis=1)
        normal_dot = normals[support_ids] @ normals[target]
        eligible = np.flatnonzero((distances <= .032) & (normal_dot > .55))
        chosen = eligible[np.lexsort((support_ids[eligible], distances[eligible]))[:32]]
        expected = np.zeros(len(support_ids), dtype=bool)
        expected[chosen] = True
        if not np.array_equal(mask[:, column], expected) or fields["fit_target_support_count"][column] != len(chosen):
            raise ValueError("local_fit_membership_must_match_32mm_normal_055_nearest32_rule")
        if not len(chosen):
            observed = [fields[key][column] for key in ("fit_target_design_rank", "fit_target_angular_bins",
                "fit_target_condition_number", "fit_target_nearest_distance_m", "fit_target_farthest_distance_m",
                "fit_target_normal_dot_minimum", "fit_target_max_angular_gap_rad")]
            if not np.allclose(observed, [0, 0, -1, -1, -1, -1, 2 * np.pi], rtol=0, atol=1e-12):
                raise ValueError("empty_local_fit_metric_sentinels_invalid")
            continue
        normal = normals[target]
        anchor = np.eye(3)[int(np.argmin(np.abs(normal)))]
        tangent_u = np.cross(normal, anchor)
        tangent_u /= np.linalg.norm(tangent_u)
        tangent_v = np.cross(normal, tangent_u)
        u = delta[chosen] @ tangent_u / .032
        v = delta[chosen] @ tangent_v / .032
        design = np.column_stack((np.ones(len(chosen)), u, v, u * u, u * v, v * v))
        rank = int(np.linalg.matrix_rank(design))
        condition = float(np.linalg.cond(design)) if rank == 6 else -1.
        observed = (fields["fit_target_nearest_distance_m"][column], fields["fit_target_farthest_distance_m"][column],
            fields["fit_target_normal_dot_minimum"][column], fields["fit_target_condition_number"][column])
        recomputed = (float(distances[chosen].min()), float(distances[chosen].max()), float(normal_dot[chosen].min()), condition)
        if fields["fit_target_design_rank"][column] != rank or not np.allclose(observed, recomputed, rtol=1e-10, atol=1e-12):
            raise ValueError("local_fit_rank_condition_distance_or_normal_coverage_mismatch")
        angles = np.mod(np.arctan2(v, u), 2 * np.pi)
        angular_bins = len(np.unique(np.floor(angles * 8 / (2 * np.pi)).astype(int)))
        angles = np.sort(angles)
        angular_gap = float(np.diff(np.r_[angles, angles[0] + 2 * np.pi]).max())
        if fields["fit_target_angular_bins"][column] != angular_bins or not np.isclose(
                fields["fit_target_max_angular_gap_rad"][column], angular_gap, rtol=1e-10, atol=1e-12):
            raise ValueError("local_fit_angular_coverage_mismatch")


def validate_read_only_packet(descriptor, session, version, arrays):
    import numpy as np
    session_key = hashlib.sha256(str(Path(session).resolve()).casefold().encode()).hexdigest()
    binding = descriptor["binding"]
    if binding["session_key"] != session_key or binding["session_version"] != version:
        raise ValueError("reference_packet_session_version_binding_mismatch")
    if binding["current_geometry_sha256"] != geometry_digest(arrays["vertices"], arrays["faces"], arrays["source_ids"]):
        raise ValueError("reference_packet_current_geometry_binding_mismatch")
    path = Path(descriptor["path"])
    path = (path if path.is_absolute() else Path(session) / path).resolve()
    directory = HERE / "private/f" / session_key[:16] / ("v" + str(version)) / "arrays"
    if path.parent != directory or not re.fullmatch(r"a[0-9a-f]{64}\.npz", path.name):
        raise ValueError("reference_packet_outside_current_fact_array_directory")
    raw = path.read_bytes()
    if len(raw) != descriptor["bytes"] or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
        raise ValueError("reference_packet_SHA256_or_size_mismatch")
    with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
        fields = {key: archive[key] for key in archive.files}
    required = {"source_ids", "current_positions_world", "current_vertex_normals", "lumped_area_world"}
    image_fields = {"attention", "per_view_score", "incident_face_visible", "incident_face_pixel_area", "candidate_rank", "observation_reason"}
    if not required <= set(fields) or set(fields) - required - image_fields - LOCAL_SUPPORT_FIELDS:
        raise ValueError("reference_packet_only_current_geometry_fields_allowed")
    schema = {key: dict(dtype=str(value.dtype), shape=list(value.shape)) for key, value in fields.items()}
    if schema != descriptor["arrays"]:
        raise ValueError("reference_packet_array_schema_mismatch")
    ids = fields["source_ids"]
    if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer) or not np.isin(ids, arrays["source_ids"]).all():
        raise ValueError("reference_packet_source_ids_outside_current_geometry")
    if not np.array_equal(fields["current_positions_world"], arrays["vertices"][ids]):
        raise ValueError("reference_packet_positions_are_not_current_geometry")
    if fields["current_vertex_normals"].shape != (len(ids), 3) or fields["lumped_area_world"].shape != (len(ids),):
        raise ValueError("reference_packet_current_measurement_shapes_invalid")
    for key in image_fields & set(fields):
        expected = (len(ids), 3) if key in ("per_view_score", "incident_face_visible", "incident_face_pixel_area", "observation_reason") else (len(ids),)
        if fields[key].shape != expected:
            raise ValueError("reference_packet_image_measurement_shapes_invalid")
    if "candidate_rank" in fields and not np.issubdtype(fields["candidate_rank"].dtype, np.integer):
        raise ValueError("reference_packet_candidate_rank_must_be_integer")
    if "incident_face_visible" in fields and fields["incident_face_visible"].dtype != np.bool_:
        raise ValueError("reference_packet_visibility_must_be_boolean")
    if "observation_reason" in fields and (not np.issubdtype(fields["observation_reason"].dtype, np.integer)
            or not np.isin(fields["observation_reason"], [0, 1, 2]).all()):
        raise ValueError("reference_packet_observation_reason_codes_invalid")
    if any(not np.isfinite(value).all() for value in fields.values()):
        raise ValueError("reference_packet_nonfinite_values")
    validate_local_support_fields(fields, arrays)
    return path


def install_access_policy(packet_path, output_folder, read_only_packets=(), image_paths=()):
    events = []
    policy = {"active": True}
    packet_path = Path(packet_path).resolve() if packet_path else None
    read_only_paths = {Path(path).resolve() for path in read_only_packets}
    read_only_paths.update(Path(path).resolve() for path in image_paths)
    if packet_path is not None:
        read_only_paths.add(packet_path)
    output_folder = output_folder.resolve()

    def audit(event, arguments):
        if not policy["active"]:
            return
        if event == "open":
            target, mode, flags = arguments
            path = Path(target).resolve() if isinstance(target, (str, bytes, os.PathLike)) else None
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC))
            packet_read = path is not None and path in read_only_paths and not writing
            payload_access = path is not None and path.parent == output_folder and path.suffix in (".npz", ".npy", ".json", ".txt", ".csv")
            allowed = packet_read or payload_access
            events.append(dict(event=event, path=str(path) if path else repr(target), mode=mode,
                flags=flags, write=writing, allowed=allowed))
            if not allowed:
                raise PermissionError("consumer_file_access_outside_current_packet_or_payloads")
        elif event.startswith(("socket.", "subprocess.", "ctypes.", "winreg.")) or event in (
            "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.startfile",
            "os.listdir", "os.scandir", "os.chdir", "os.remove", "os.rename", "os.link", "os.symlink",
            "os.mkdir", "os.rmdir", "sys._getframe", "sys.settrace", "sys.setprofile", "pickle.find_class",
        ):
            events.append(dict(event=event, allowed=False))
            raise PermissionError("consumer_runtime_operation_unavailable_" + event)

    sys.addaudithook(audit)
    return events, policy


def validate_image_rows(rows, session, version):
    """Accept only the shared case PNGs and this session's actual version preview."""
    result = {}
    for item in rows:
        role = item["role"]
        if not re.fullmatch(r"(normal|current)_(whole_front|forearm_front|forearm_side|forearm_45)", role) or role in result:
            raise ValueError("invalid_or_duplicate_shared_image_role")
        path = Path(item["path"])
        path = (path if path.is_absolute() else session / path).resolve()
        expected = Path(item["case_images_root"]).resolve()
        if not expected.is_relative_to(HERE / "private") or expected.name != "images":
            raise ValueError("shared_image_case_root_outside_current_batch")
        parent = session / "previews" / ("v" + str(version)) / "images" if version and role.startswith("current_") else expected
        if path.parent != parent or path.name != role + ".png" and parent == expected:
            raise ValueError("shared_image_path_outside_bound_case_or_version")
        if path.suffix != ".png" or not isinstance(item.get("camera", {}), dict):
            raise ValueError("shared_image_requires_PNG_camera_metadata")
        result[role] = dict(item, path=str(path))
    if rows and len(result) != 8:
        raise ValueError("eight_shared_normal_current_image_roles_required")
    return result


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def worker():
    started = time.perf_counter()
    decode_started, decode_cpu = time.perf_counter(), time.process_time()
    payload = json.loads(sys.stdin.buffer.read())
    transport = dict(input_JSON_decode_wall_s=time.perf_counter()-decode_started,
        input_JSON_decode_CPU_s=time.process_time()-decode_cpu, mode="inline_arrays")
    sys.path.insert(0, str(DEPS))
    import numpy as np
    import scipy
    # Resolve supported numerical imports before enabling the data-file policy.
    # The untrusted code cannot use runtime imports to read additional code/data.
    for module_name in sorted(ALLOWED_IMPORTS):
        __import__(module_name)
    if "array_packet" in payload:
        packet_started, packet_cpu = time.perf_counter(), time.process_time()
        descriptor = payload["array_packet"]
        session = Path(payload["payload_folder"]).resolve().parent
        packet_path = Path(descriptor["path"]).resolve()
        binding = descriptor["binding"]
        cache_key = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()
        session_key = hashlib.sha256(str(session).casefold().encode("utf8")).hexdigest()
        if binding["session_key"] != session_key or binding["version"] != payload["version"] or cache_key != descriptor["cache_key"]:
            raise ValueError("packet_session_version_binding_mismatch")
        if packet_path.parent != session / "snapshots" / ("v" + str(payload["version"])):
            raise ValueError("packet_outside_session_version_snapshot_directory")
        raw = packet_path.read_bytes()
        if len(raw) != descriptor["bytes"] or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise ValueError("packet_SHA256_or_size_mismatch")
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        schema = {key: dict(dtype=str(value.dtype), shape=list(value.shape)) for key, value in arrays.items()}
        if schema != binding["schema"]:
            raise ValueError("packet_array_dtype_shape_binding_mismatch")
        transport.update(mode="NPZ_packet", packet_bytes=len(raw),
            packet_validate_load_wall_s=time.perf_counter()-packet_started,
            packet_validate_load_CPU_s=time.process_time()-packet_cpu)
    else:
        arrays = {key: np.asarray(value) for key, value in payload["arrays"].items()}
    reference_paths = [validate_read_only_packet(item, Path(payload["payload_folder"]).resolve().parent, payload["version"], arrays)
        for item in payload.get("read_only_packets", [])]
    for key in ("faces", "F_ids", "I_ids", "protected_ids", "source_ids", "B0", "B1", "local_edges"):
        if key in arrays:
            arrays[key] = arrays[key].astype(np.int64)
    for key in ("vertices", "initial_vertices"):
        arrays[key] = arrays[key].astype(np.float64)
    created = []
    output_folder = Path(payload["payload_folder"])
    output_folder.mkdir(parents=True, exist_ok=True)
    session = output_folder.resolve().parent
    image_rows = validate_image_rows(payload.get("image_inputs", []), session, payload["version"])
    image_cache, image_reads, fit_diagnostics = {}, [], []

    def read_image_pixels(role):
        if role not in image_rows:
            raise ValueError("image_role_must_be_in_image_roles")
        row = image_rows[role]
        began, image_cpu = time.perf_counter(), time.process_time()
        hit = role in image_cache
        if not hit:
            raw = Path(row["path"]).read_bytes()
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("shared_PNG_SHA256_or_size_mismatch")
            pixels = read_png_rgb(raw)
            if pixels.shape != (row["height"], row["width"], 3):
                raise ValueError("shared_PNG_decoded_shape_mismatch")
            pixels.setflags(write=False)
            image_cache[role] = pixels
        pixels = image_cache[role]
        image_reads.append(dict(role=role, cache_hit=hit, sha256=row["sha256"], PNG_bytes=row["bytes"],
            decoded_array_bytes=pixels.nbytes, wall_s=time.perf_counter() - began, CPU_s=time.process_time() - image_cpu))
        return pixels

    def save_fit_diagnostics(fit_target_ids, fit_offsets, fit_source_ids, fit_design_rank, fit_estimated_amplitude_m, **extra_arrays):
        target_ids, offsets, support_ids, ranks = [np.asarray(value) for value in
            (fit_target_ids, fit_offsets, fit_source_ids, fit_design_rank)]
        amplitude = np.asarray(fit_estimated_amplitude_m, dtype=np.float64)
        if any(value.ndim != 1 or not np.issubdtype(value.dtype, np.integer) for value in (target_ids, offsets, support_ids, ranks)):
            raise ValueError("fit_target_offsets_support_and_rank_require_integer_vectors")
        if not len(target_ids) or len(offsets) != len(target_ids) + 1 or len(ranks) != len(target_ids) or amplitude.shape != target_ids.shape:
            raise ValueError("fit_diagnostic_shapes_invalid")
        if offsets[0] != 0 or offsets[-1] != len(support_ids) or np.any(np.diff(offsets) < 0) or np.any(ranks < 0):
            raise ValueError("fit_offsets_or_design_rank_invalid")
        if not np.isin(target_ids, np.r_[-1, arrays["source_ids"]]).all() or not np.isin(support_ids, arrays["source_ids"]).all():
            raise ValueError("fit_diagnostic_ids_outside_current_source_geometry")
        fields = dict(fit_target_ids=target_ids.astype(np.int64), fit_offsets=offsets.astype(np.int64),
            fit_source_ids=support_ids.astype(np.int64), fit_design_rank=ranks.astype(np.int64), fit_estimated_amplitude_m=amplitude)
        for name, value in extra_arrays.items():
            if not re.fullmatch(r"fit_[A-Za-z0-9_]+", name):
                raise ValueError("fit_extra_array_name_requires_fit_prefix")
            fields[name] = np.asarray(value)
        if "fit_normals" in fields and fields["fit_normals"].shape != (len(target_ids), 3):
            raise ValueError("fit_normals_require_one_3D_estimate_axis_per_target")
        if any(value.dtype.kind not in "biuf" or not np.isfinite(value).all() for value in fields.values()):
            raise ValueError("fit_diagnostics_require_finite_numeric_arrays")
        diagnostic_id = "f" + uuid.uuid4().hex
        path = output_folder / (diagnostic_id + ".npz")
        np.savez_compressed(path, **fields)
        raw = path.read_bytes()
        item = dict(diagnostic_id=diagnostic_id, observed_version=payload["version"], version=payload["version"],
            path="payloads/" + path.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
            targets=len(target_ids), support_entries=len(support_ids),
            evidence="Consumer-declared actual fitting inputs; retained source code establishes their use")
        (output_folder / (diagnostic_id + ".json")).write_text(json.dumps(item, allow_nan=False) + "\n", encoding="utf8")
        fit_diagnostics.append(item)
        return item

    def save_edit(source_ids, values, mode="positions_world"):
        ids = np.asarray(source_ids)
        values = np.asarray(values, dtype=np.float64)
        if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer) or not len(ids):
            raise ValueError("source_ids_must_be_nonempty_integer_vector")
        ids = ids.astype(np.int64)
        if len(np.unique(ids)) != len(ids) or not np.isin(ids, arrays["I_ids"]).all():
            raise ValueError("submitted_source_ids_must_be_unique_and_inside_I")
        if values.shape != (len(ids), 3) or not np.isfinite(values).all():
            raise ValueError("submitted_values_must_be_finite_N_by3")
        if mode not in ("positions_world", "displacements_world"):
            raise ValueError("mode_must_be_positions_world_or_displacements_world")
        ident = "p" + uuid.uuid4().hex
        np.savez_compressed(output_folder / (ident + ".npz"), source_ids=ids, **{mode: values})
        item = dict(payload_id=ident, observed_version=payload["version"], points=len(ids), mode=mode)
        (output_folder / (ident + ".json")).write_text(json.dumps(item, allow_nan=False) + "\n", encoding="utf8")
        created.append(item)
        return item

    task = payload["task"]
    safe_builtins = {name: getattr(builtins, name) for name in SAFE_BUILTINS}
    safe_builtins.update(__import__=bounded_import, open=builtins.open)
    namespace = dict(__builtins__=safe_builtins, np=np, scipy=scipy, V=arrays["vertices"], current=arrays["vertices"], vertices=arrays["vertices"],
        V0=arrays["initial_vertices"], initial_vertices=arrays["initial_vertices"], faces=arrays["faces"],
        F_ids=arrays["F_ids"], I_ids=arrays["I_ids"], protected_ids=arrays["protected_ids"],
        source_ids=arrays.get("source_ids", np.arange(len(arrays["vertices"]))), version=payload["version"],
        task=task, save_edit=save_edit, G=arrays, geometry=arrays,
        packet_path=Path(os.path.relpath(packet_path, session)).as_posix() if "array_packet" in payload else None,
        payload_folder=Path(os.path.relpath(output_folder, Path(payload["payload_folder"]).resolve().parent)).as_posix())
    namespace["reference_packets"] = payload.get("read_only_packets", [])
    namespace.update(read_image_pixels=read_image_pixels, image_roles=tuple(image_rows),
        image_cameras={role: row.get("camera", {}) for role, row in image_rows.items()}, save_fit_diagnostics=save_fit_diagnostics)
    for key in ("normals", "n0", "B0", "B1", "local_edges"):
        if key in arrays:
            namespace[key] = arrays[key]
    stdout, stderr = io.StringIO(), io.StringIO()
    error = None
    access_events, policy = install_access_policy(packet_path if "array_packet" in payload else None, output_folder, reference_paths,
        [row["path"] for row in image_rows.values()])
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(validate_code(payload["code"]), namespace, namespace)
    except BaseException as exception:
        error = dict(type=type(exception).__name__, message=str(exception))
    finally:
        policy["active"] = False
    result = dict(stdout=stdout.getvalue(), stderr=stderr.getvalue(), error=error, created_payloads=created,
        observed_version=payload["version"], worker_wall_s_before_write=time.perf_counter() - started, process=legacy.lifetime_metrics(),
        transport=transport, file_access=access_events, image_pixel_reads=image_reads, created_fit_diagnostics=fit_diagnostics,
        access_policy=dict(implementation="AST/import restrictions and CPython audit-hook path allowlist",
            scope="current version NPZ, validated delivered references and shared bound PNGs read-only, own session payloads read/write",
            registered_reference_packets=len(reference_paths),
            registered_shared_PNGs=len(image_rows),
            OS_sandbox_certification=False, denied_accesses=sum(not row["allowed"] for row in access_events)))
    sys.stdout.write(json.dumps(result, ensure_ascii=True, allow_nan=False) + "\n")


def execute(code, snapshot, task, payload_folder, audit_path, python=None, timeout_s=45, output_chars=16000):
    started = time.perf_counter()
    audit_path = Path(audit_path)
    audit_path.mkdir(parents=True, exist_ok=False)
    payload_folder = Path(payload_folder).resolve()
    session = payload_folder.parent
    payload = dict(code=code, version=snapshot["version"], task=task, payload_folder="payloads")
    payload["read_only_packets"] = [dict(item, path=Path(os.path.relpath(item["path"], session)).as_posix())
        for item in snapshot.get("read_only_packets", [])]
    payload["image_inputs"] = [dict(item, path=Path(os.path.relpath(item["path"], session)).as_posix())
        for item in snapshot.get("image_inputs", [])]
    if "array_packet" in snapshot:
        payload["array_packet"] = dict(snapshot["array_packet"],
            path=Path(os.path.relpath(snapshot["array_packet"]["path"], session)).as_posix())
        shapes = {key: value["shape"] for key, value in snapshot["array_packet"]["binding"]["schema"].items()}
    else:
        payload["arrays"] = snapshot["arrays"]
        shapes = {key: [len(value)] for key, value in snapshot["arrays"].items()}
    encode_started, encode_cpu = time.perf_counter(), time.process_time()
    raw = (json.dumps(payload, ensure_ascii=True, allow_nan=False) + "\n").encode("utf8")
    encode_wall, encode_CPU = time.perf_counter()-encode_started, time.process_time()-encode_cpu
    write(audit_path / "REQUEST.json", dict(code=code, observed_version=snapshot["version"], task=task,
        input_JSON_bytes=len(raw), array_shapes=shapes, array_packet=snapshot.get("array_packet"),
        read_only_packets=snapshot.get("read_only_packets", []), image_inputs=snapshot.get("image_inputs", []), worker_cwd=str(session)))
    (audit_path / "CODE.py").write_text(code, encoding="utf8", newline="\n")
    python = Path(python or HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe")
    command = [str(python), "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--worker"]
    record = dict(command=command, timeout_s=timeout_s, observed_version=snapshot["version"], input_JSON_bytes=len(raw),
        status="running", returncode=None, worker=None, error=None, JSON_encode_wall_s=encode_wall, JSON_encode_CPU_s=encode_CPU,
        input_transport="NPZ_packet" if "array_packet" in snapshot else "inline_arrays")
    process = None
    try:
        environment = {key: value for key, value in os.environ.items() if key.upper() in
            ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "NUMBER_OF_PROCESSORS")}
        environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
            NUMEXPR_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", TEMP=str(audit_path), TMP=str(audit_path))
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=session, env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record["pid"] = process.pid
        stdout, stderr = process.communicate(raw, timeout=timeout_s)
        (audit_path / "STDOUT.bin").write_bytes(stdout)
        (audit_path / "STDERR.bin").write_bytes(stderr)
        record["returncode"] = process.returncode
        if process.returncode:
            raise RuntimeError("python_worker_exit_" + str(process.returncode))
        complete = json.loads(stdout)
        record["worker"] = complete
        write(audit_path / "COMPLETE_RESULT.json", complete)
        write(audit_path / "FILE_ACCESS.json", dict(policy=complete["access_policy"], events=complete["file_access"]))
        public = dict(complete)
        public.pop("transport", None)
        public.pop("file_access", None)
        for key in ("stdout", "stderr"):
            public[key] = complete[key][:output_chars]
        record["public_truncated"] = any(len(complete[key]) > output_chars for key in ("stdout", "stderr"))
        public["truncated"] = record["public_truncated"]
        record["status"] = "completed" if complete["error"] is None else "execution_error"
    except subprocess.TimeoutExpired:
        if process is not None and process.poll() is None:
            stop = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            record["timeout_tree_kill_returncode"] = stop.returncode
            if process.poll() is None:
                process.kill()
        stdout, stderr = process.communicate(timeout=5)
        (audit_path / "STDOUT.bin").write_bytes(stdout)
        (audit_path / "STDERR.bin").write_bytes(stderr)
        record.update(status="timeout", returncode=process.returncode, error=dict(type="TimeoutExpired", message="python_execution_deadline"))
        public = dict(stdout="", stderr="", error=record["error"], created_payloads=[])
    except BaseException as exception:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        record.update(status="failed", error=dict(type=type(exception).__name__, message=str(exception)))
        public = dict(stdout="", stderr="", error=record["error"], created_payloads=[])
    record["wall_s"] = time.perf_counter() - started
    write(audit_path / "EXECUTION.json", record)
    return public, record


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("use_module_execute_or_worker_protocol")
    worker()
