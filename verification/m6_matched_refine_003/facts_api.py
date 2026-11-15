"""Compact current-geometry facts with session- and version-bound references."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np

specification = importlib.util.spec_from_file_location("_matched003_reused_focus", HERE.parent / "m6_task_perception_001/interfaces.py")
FOCUS = importlib.util.module_from_spec(specification)
sys.modules[specification.name] = FOCUS
specification.loader.exec_module(FOCUS)


def digest(*arrays):
    result = hashlib.sha256()
    for value in arrays:
        value = np.ascontiguousarray(value)
        result.update(json.dumps(dict(dtype=str(value.dtype), shape=list(value.shape)), sort_keys=True).encode())
        result.update(value.tobytes())
    return result.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def path_for(session, value):
    path = Path(value)
    return path if path.is_absolute() else Path(session) / path


def prepare(session, state):
    session = Path(session).resolve()
    version = state["version"]
    if type(version) is not int or version < 0:
        raise ValueError("current_nonnegative_integer_session_version_required")
    with np.load(path_for(session, state["current_npz"]), allow_pickle=False) as archive:
        vertices = np.asarray(archive["vertices_world"] if "vertices_world" in archive else archive["vertices"], dtype=np.float64)
        faces = np.asarray(archive["faces"], dtype=np.int64)
        ids = np.asarray(archive["source_ids"], dtype=np.int64)
    with np.load(path_for(session, state["initial_npz"]), allow_pickle=False) as archive:
        F = np.asarray(archive["F_source_ids"], dtype=np.int64)
        I = np.asarray(archive["I_ids"], dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("finite_current_world_positions_required")
    if not np.array_equal(ids, np.arange(len(vertices))):
        raise ValueError("preserved_full_source_ID_indexing_required")
    F = FOCUS.checked_ids(F, len(vertices))
    I = FOCUS.checked_ids(I, len(vertices))
    if not np.isin(I, F).all():
        raise ValueError("editable_domain_within_observation_domain_required")
    protected = np.setdiff1d(F, I)
    source_spec = state["source_spec"]
    if not isinstance(source_spec, dict):
        source_spec = json.loads(path_for(session, source_spec).read_bytes())
    session_key = hashlib.sha256(str(session).casefold().encode()).hexdigest()
    logical = dict(session_key=session_key, session_version=version, case_id=state.get("case_id", "sample_05"),
        current_geometry_sha256=digest(vertices, faces, ids), scope_sha256=digest(F, I), unit=source_spec.get("unit", "m"))
    directory = HERE / "private/f" / session_key[:16] / ("v" + str(version))
    directory.mkdir(parents=True, exist_ok=True)
    binding_path = directory / "BINDING.json"
    packet = directory / "g.npz"
    alias = "mr" + session_key + "v" + str(version)
    if binding_path.exists():
        binding = json.loads(binding_path.read_bytes())
        if binding["logical"] != logical:
            raise ValueError("geometry_or_scope_changed_without_session_version")
        if hashlib.sha256(packet.read_bytes()).hexdigest() != binding["packet_sha256"]:
            raise ValueError("versioned_focus_packet_modified")
        expected = dict(cases=[dict(alias=alias, input=dict(path="g.npz", sha256=binding["packet_sha256"]))])
        if json.loads((directory / "INPUT_INDEX.json").read_bytes()) != expected:
            raise ValueError("versioned_focus_index_modified")
    else:
        np.savez_compressed(packet, vertices=vertices, faces=faces, F_source_ids=F)
        packet_sha = hashlib.sha256(packet.read_bytes()).hexdigest()
        write(directory / "INPUT_INDEX.json", dict(cases=[dict(alias=alias, input=dict(path="g.npz", sha256=packet_sha))]))
        write(binding_path, dict(logical=logical, packet_sha256=packet_sha))
    return FOCUS.TaskPerception(directory), directory, alias, logical, F, I, protected, len(vertices)


def world_geometry(facts, unit):
    facts["coordinate_space"] = "Blender_world"
    facts["physical_unit"] = unit
    facts["centroid_world"] = facts.pop("centroid_native")
    facts["bbox_world"] = facts.pop("bbox_native")
    facts["lumped_area_world"] = facts.pop("lumped_area_native")
    facts["area_unit"] = unit + "^2"


def focus(session, state):
    started, cpu = time.perf_counter(), time.process_time()
    prototype, directory, alias, logical, F, I, protected, full_count = prepare(session, state)
    result = prototype.focus(alias, F, protected, request="Repair the specified forearm region toward the provided normal reference images.")
    geometry = prototype._load_geometry(alias)
    result["editable"] = prototype._reference(geometry, I, "editable_interior", dict(parent_reference=result["target"]["reference"]))
    for role in ("target", "background", "protected", "context", "editable"):
        region = result[role]
        if region is not None:
            world_geometry(region["geometry"], logical["unit"])
            region["read_more"] = dict(resolver="resolve_ref", reference=region["reference"])
    result.pop("editable_target_source_ids", None)
    result.pop("prediction", None)
    result["session_binding"] = logical
    result["task_geometry_roles"] = dict(observation_F_points=len(F), editable_I_points=len(I),
        local_protected_points=len(protected), full_source_points=full_count, full_source_protected_points=full_count - len(I),
        editable_reference=result["editable"]["reference"])
    result["cost"].update(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        scope="current saved geometry reads, version validation, geometry focus and stable reference creation")
    write(directory / "FOCUS.json", result)
    return result


def resolve_ref(session, state, reference, *, include_arrays=False):
    started, cpu = time.perf_counter(), time.process_time()
    prototype, directory, alias, logical, *_ = prepare(session, state)
    prefix = FOCUS.REFERENCE_PREFIX
    if not isinstance(reference, str) or not reference.startswith(prefix):
        raise ValueError("invalid_region_reference")
    digest_value = reference[len(prefix):]
    if len(digest_value) != 64 or any(value not in "0123456789abcdef" for value in digest_value):
        raise ValueError("invalid_region_reference_digest")
    if not (directory / "private/references" / (digest_value + ".json")).exists():
        raise ValueError("region_reference_outside_current_session_version")
    result = prototype.resolve(reference, include_geometry=True)
    if result["identity"]["observation_alias"] != alias:
        raise ValueError("region_reference_alias_version_mismatch")
    world_geometry(result["geometry"], logical["unit"])
    arrays = dict(source_ids=np.asarray(result.pop("source_ids"), dtype=np.int64),
        current_positions_world=np.asarray(result.pop("current_positions_native"), dtype=np.float64),
        current_vertex_normals=np.asarray(result.pop("current_vertex_normals"), dtype=np.float64),
        lumped_area_world=np.asarray(result.pop("lumped_area_native"), dtype=np.float64))
    packet = directory / "arrays" / ("a" + digest_value + ".npz")
    packet.parent.mkdir(parents=True, exist_ok=True)
    if packet.exists():
        with np.load(packet, allow_pickle=False) as archive:
            if set(archive.files) != set(arrays) or any(archive[key].dtype != value.dtype or archive[key].shape != value.shape
                    or archive[key].tobytes() != value.tobytes() for key, value in arrays.items()):
                raise ValueError("current_reference_array_packet_changed")
    else:
        np.savez_compressed(packet, **arrays)
    raw = packet.read_bytes()
    result["geometry_packet"] = dict(path=str(packet), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
        arrays={key: dict(dtype=str(value.dtype), shape=list(value.shape)) for key, value in arrays.items()},
        binding=logical, reference=reference, read_with="NumPy np.load(path, allow_pickle=False)")
    if include_arrays:
        result.update({key: value.tolist() for key, value in arrays.items()})
    result["session_binding"] = logical
    result["cost"].update(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    write(directory / "private/resolved" / (digest_value + ".json"), result)
    return result
