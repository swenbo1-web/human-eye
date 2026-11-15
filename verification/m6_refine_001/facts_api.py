"""Current saved geometry focus facts with session/version-bound references."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np

_SPEC = importlib.util.spec_from_file_location("_refine_reused_focus", HERE.parent / "m6_task_perception_001/interfaces.py")
_FOCUS = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _FOCUS
_SPEC.loader.exec_module(_FOCUS)


def _digest(*arrays):
    value = hashlib.sha256()
    for array in arrays:
        array = np.ascontiguousarray(array)
        header = json.dumps(dict(dtype=str(array.dtype), shape=list(array.shape)), sort_keys=True).encode("utf8")
        value.update(len(header).to_bytes(8, "little"))
        value.update(header)
        value.update(array.tobytes())
    return value.hexdigest()


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def _prepare(session_dir, state):
    session_dir = Path(session_dir).resolve()
    session_key = hashlib.sha256(str(session_dir).casefold().encode("utf8")).hexdigest()
    version = state["version"]
    if type(version) is not int or version < 0:
        raise ValueError("session_version_must_be_nonnegative_integer")
    with np.load(state["current_npz"], allow_pickle=False) as source:
        vertices = np.asarray(source["vertices_world"] if "vertices_world" in source else source["vertices"], dtype=np.float64)
        faces = np.asarray(source["faces"], dtype=np.int64)
        source_ids = np.asarray(source["source_ids"] if "source_ids" in source else np.arange(len(vertices)), dtype=np.int64)
    with np.load(state["initial_npz"], allow_pickle=False) as initial:
        F = np.asarray(initial["F_source_ids"] if "F_source_ids" in initial else initial["F_ids"], dtype=np.int64)
        allowed = np.asarray(initial["I_ids"], dtype=np.int64)
    specification = state["source_spec"]
    if not isinstance(specification, dict):
        specification = json.loads(Path(specification).read_bytes())
    unit = specification.get("unit", "native_unknown")
    if not np.array_equal(source_ids, np.arange(len(vertices))):
        raise ValueError("focus_requires_preserved_full_source_ID_indexing")
    protected = np.setdiff1d(F, allowed)
    if not np.isin(allowed, F).all() or len(np.unique(F)) != len(F) or len(np.unique(allowed)) != len(allowed):
        raise ValueError("focus_scope_or_allowed_set_invalid")
    logical = dict(session_key=session_key, session_version=version, case_id=state["case_id"], coordinate_unit=unit,
        current_geometry_sha256=_digest(vertices, faces, source_ids), initial_scope_sha256=_digest(F, allowed))
    directory = HERE / "private/f" / session_key[:10] / ("v" + str(version))
    directory.mkdir(parents=True, exist_ok=True)
    binding_path = directory / "BINDING.json"
    packet = directory / "g.npz"
    alias = "rf" + session_key + "v" + str(version)
    index_path = directory / "INPUT_INDEX.json"
    if binding_path.exists():
        previous = json.loads(binding_path.read_bytes())
        if previous["logical_identity"] != logical:
            raise ValueError("current_geometry_changed_without_session_version")
        if hashlib.sha256(packet.read_bytes()).hexdigest() != previous["packet_sha256"]:
            raise ValueError("current_focus_packet_changed")
        expected_index = dict(cases=[dict(alias=alias, input=dict(path="g.npz", sha256=previous["packet_sha256"]))])
        if json.loads(index_path.read_bytes()) != expected_index:
            raise ValueError("current_focus_index_binding_changed")
    else:
        np.savez_compressed(packet, vertices=vertices, faces=faces, F_source_ids=F)
        _write(index_path, dict(cases=[dict(alias=alias, input=dict(path="g.npz", sha256=hashlib.sha256(packet.read_bytes()).hexdigest()))]))
        _write(binding_path, dict(logical_identity=logical, packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest()))
    prototype = _FOCUS.TaskPerception(directory)
    return prototype, directory, alias, logical, vertices, F, allowed, protected


def _world_geometry(facts, unit):
    facts["coordinate_space"] = "Blender_world"
    facts["physical_unit"] = "unknown" if unit == "native_unknown" else unit
    facts["centroid_world"] = facts.pop("centroid_native")
    facts["bbox_world"] = facts.pop("bbox_native")
    facts["lumped_area_world"] = facts.pop("lumped_area_native")
    facts["area_unit"] = "native_unknown_squared" if unit == "native_unknown" else unit + "^2"


def focus(session_dir, state):
    started, cpu = time.perf_counter(), time.process_time()
    prototype, directory, alias, logical, vertices, F, allowed, protected = _prepare(session_dir, state)
    result = prototype.focus(alias, allowed, protected, request="Read the explicitly designated refinement target, protected boundary and observable surrounding geometry.")
    for role in ("target", "background", "protected", "context"):
        region = result[role]
        if region is not None:
            _world_geometry(region["geometry"], logical["coordinate_unit"])
            region["read_more"] = dict(resolver="resolve_ref", reference=region["reference"])
    result["session_binding"] = logical
    result["task_geometry_roles"] = dict(F_points=len(F), editable_I_points=len(allowed), local_protected_points=len(protected),
        full_source_points=len(vertices), outside_I_protection=dict(rule="every_full_source_vertex_not_in_I_is_protected_from_editing",
            protected_points=len(vertices)-len(allowed), allowed_I_reference=result["target"]["reference"],
            full_source_ID_domain=dict(first=0, last=len(vertices)-1)))
    result["editing_authorized_scope"] = "sparse edits to I through the isolated session edit API"
    result["cost"].update(wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu,
        scope="current saved NPZ read, canonical packet/cache validation, shared focus geometry and versioned refs")
    return result


def resolve_ref(session_dir, state, reference):
    started, cpu = time.perf_counter(), time.process_time()
    prototype, directory, alias, logical, _, _, _, _ = _prepare(session_dir, state)
    prefix = _FOCUS.REFERENCE_PREFIX
    if not isinstance(reference, str) or not reference.startswith(prefix):
        raise ValueError("invalid_focus_reference")
    digest = reference[len(prefix):]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("invalid_focus_reference_digest")
    path = directory / "private/references" / (digest + ".json")
    if not path.exists():
        raise ValueError("reference_not_bound_to_current_session_version")
    result = prototype.resolve(reference, include_geometry=True)
    if result["identity"]["observation_alias"] != alias:
        raise ValueError("focus_reference_crossed_session_version")
    _world_geometry(result["geometry"], logical["coordinate_unit"])
    result["current_positions_world"] = result.pop("current_positions_native")
    result["lumped_area_world"] = result.pop("lumped_area_native")
    result["session_binding"] = logical
    result["cost"].update(wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu)
    return result
