"""Reopen every saved session and audit geometry independently of consumer claims.

Run after the sessions finish. Each initial/final Blender file is opened by a new
background reader process. Fresh packets are evaluated against frozen initial
targets, with independent scalar, topology and blocked full-mesh AABB checks.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
from evaluate import evaluate_packets
import numpy as np

EXPECTED = ("v1_s01_native", "v1_s01_facts", "v1_s02_facts", "v1_s02_native", "v2_s02_facts", "v2_s01_facts")
oracle_path = HERE.parent / "m6_coupled_probe_001/spatial_oracle.py"
oracle_spec = importlib.util.spec_from_file_location("_refine_independent_aabb", oracle_path)
oracle = importlib.util.module_from_spec(oracle_spec)
oracle_spec.loader.exec_module(oracle)


def status(checks):
    values = list(checks.values())
    return "fail" if any(value is False for value in values) else "pass" if values and all(value is True for value in values) else "unknown"


def packet(path):
    with np.load(path, allow_pickle=False) as package:
        return {name: package[name] for name in package.files}


def same_bits(first, second):
    return first.dtype == second.dtype and first.shape == second.shape and first.tobytes() == second.tobytes()


def independent_measurements(before, after, fixed, spec):
    """Separate calculations use only fresh readback bytes and frozen targets."""
    initial, final = before["vertices"], after["vertices"]
    allowed, core = fixed["I_ids"], fixed["C_ids"]
    outside = np.setdiff1d(np.arange(len(initial)), allowed)
    movement = final-initial
    projection = np.sum(movement*fixed["n0"], axis=1)
    tangent = np.sqrt(np.sum((movement-projection[:, None]*fixed["n0"])**2, axis=1))
    magnitude = np.sqrt(np.sum(movement**2, axis=1))
    center, h = int(spec["center_source_id"]), float(spec["h"])
    world_error = float(np.max(np.abs(movement[outside]))) if len(outside) else 0.
    checks = dict(center_displacement=bool(.95*h <= projection[center] <= 1.05*h),
        core_median=bool(np.median(projection[core]) >= .6*h),
        maximum_displacement=bool(np.max(magnitude) <= 1.1*h),
        tangential_residual=bool(np.max(tangent[allowed]) <= max(float(spec["tangent_abs_tol"]), .01*h)),
        outside_I_local_float32_bitwise=same_bits(before["vertices_local"][outside], after["vertices_local"][outside]),
        outside_I_world_save_precision=world_error <= float(spec["world_preservation_tol"]),
        polygon_topology=bool(np.array_equal(before["poly_offsets"], after["poly_offsets"]) and np.array_equal(before["poly_vertices"], after["poly_vertices"])),
        source_vertex_ids=bool(np.array_equal(before["source_ids"], after["source_ids"]) and len(np.unique(before["source_ids"])) == len(initial)),
        target_matrix=bool(np.array_equal(before["matrix_world"], after["matrix_world"])))
    unreachable = allowed[~np.isfinite(fixed["boundary_distance"][allowed])]
    checks["unreachable_I_local_float32_bitwise"] = same_bits(before["vertices_local"][unreachable], after["vertices_local"][unreachable])
    high = set(map(int, allowed[projection[allowed] > .5*h]))
    local = before["faces"][np.isin(before["faces"], fixed["F_source_ids"]).all(axis=1)]
    adjacency = {source: set() for source in high}
    for triangle in local:
        for first, second in zip(triangle, np.roll(triangle, -1)):
            if int(first) in high and int(second) in high:
                adjacency[int(first)].add(int(second))
                adjacency[int(second)].add(int(first))
    reached, pending = set(), [center] if center in high else []
    while pending:
        source = pending.pop()
        if source not in reached:
            reached.add(source)
            pending.extend(adjacency[source]-reached)
    checks["high_displacement_contiguous"] = bool(high and reached == high and np.count_nonzero(projection[core] > .5*h) >= int(np.ceil(.5*len(core))))
    return dict(checks=checks, center_over_h=float(projection[center]/h), core_median_over_h=float(np.median(projection[core])/h),
        maximum_displacement_over_h=float(np.max(magnitude)/h), maximum_tangent=float(np.max(tangent[allowed])),
        outside_maximum_world_component_error=world_error, unreachable_ids=unreachable.tolist(), high_vertices=len(high))


def audit_packets(before_path, after_path, fixed_path, spec_path, before_scene, after_scene):
    started, cpu = time.perf_counter(), time.process_time()
    before, after, fixed = packet(before_path), packet(after_path), packet(fixed_path)
    spec = read(spec_path)
    quality = evaluate_packets(before_path, after_path, fixed_path, spec_path,
        before_state_path=before_scene, after_state_path=after_scene)
    measured = independent_measurements(before, after, fixed, spec)
    checks = {"independent_"+key+"_agrees": bool(value == quality["checks"].get(key)) for key, value in measured["checks"].items()}
    frozen_fields = ("vertices", "vertices_local", "faces", "source_ids", "matrix_world", "poly_offsets", "poly_vertices", "triangle_polygon_ids")
    checks.update({"initial_"+key+"_matches_frozen": same_bits(before[key], fixed[key]) for key in frozen_fields})
    changed = np.flatnonzero(np.any(before["vertices_local"].view(np.uint32) != after["vertices_local"].view(np.uint32), axis=1))
    active = np.union1d(fixed["I_ids"], changed)
    coverage = {}
    for phase, values in (("before", before), ("after", after)):
        native, matrix = values["vertices_local"], values["matrix_world"]
        reconstructed = native.astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
        scale = max(1., float(np.max(np.abs(values["vertices"]))))
        error = float(np.max(np.abs(reconstructed-values["vertices"])))
        checks[phase+"_local_is_float32"] = native.dtype == np.dtype("float32")
        checks[phase+"_world_matches_native_and_matrix"] = bool(error <= 64*np.finfo(float).eps*scale)
        affected = np.flatnonzero(np.isin(values["faces"], active).any(axis=1))
        pairs, cost = oracle.candidates(values["vertices"], values["faces"], affected, deadline=time.perf_counter()+180)
        scan = quality["self_intersection"].get(phase)
        if scan is None:
            checks[phase+"_full_mesh_candidate_coverage"] = None
        else:
            checks[phase+"_full_mesh_candidate_coverage"] = bool(scan["candidate_complete"] and pairs == [tuple(pair) for pair in scan["candidates"]]
                and cost["domain_pairs"] == scan["pair_domain"] and affected.tolist() == scan["affected_face_ids"])
        coverage[phase] = dict(independent_AABB=cost, native_world_maximum_component_error=error,
            affected_face_ids=affected.tolist(), independent_candidate_count=len(pairs))
    return dict(audit_status=status(checks), checks=checks, independent=measured, coverage=coverage,
        quality=quality, wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        input_files=[identity(path) for path in (before_path, after_path, fixed_path, spec_path, before_scene, after_scene)],
        sources=[identity(HERE / name) for name in ("verify_quality.py", "quality.py", "evaluate.py")]+[identity(oracle_path)])


def audit_session(directory, output):
    state_path = directory / "session.json"
    state = read(state_path)
    spec = read(state["source_spec"])
    jobs = {}
    before_blend, after_blend = directory / "before.blend", Path(state["current_blend"])
    for phase, blend in (("before", before_blend), ("after", after_blend)):
        target = output / phase
        target.mkdir(parents=True, exist_ok=False)
        label = "verify_"+hashlib.sha256((str(output)+phase).encode()).hexdigest()[:18]
        jobs[phase] = run_job("blender_read.py", dict(current_blend=str(blend), object_name=spec["object_name"],
            source_original=spec["source_original"], base_npz=state["initial_npz"], expected_input_sha256=identity(blend)["sha256"],
            readback_npz=str(target / "readback.npz"), scene_signature_json=str(target / "scene.json"),
            local_obj=str(target / "local.obj")), label)
    result = audit_packets(output / "before/readback.npz", output / "after/readback.npz", Path(state["initial_npz"]),
        Path(state["source_spec"]), output / "before/scene.json", output / "after/scene.json")
    checks = result["checks"]
    checks["session_stable_during_audit"] = read(state_path) == state
    checks["session_has_no_pending_edit"] = True if state.get("pending") is None else None
    checks["initial_saved_copy_matches_case_baseline"] = identity(before_blend)["sha256"] == identity(spec["base_blend_path"])["sha256"]
    current_identity = state.get("current_blend_identity")
    checks["final_saved_identity_matches_session"] = identity(after_blend)["sha256"] == current_identity["sha256"] if current_identity else None
    for phase, job in jobs.items():
        receipt = job["receipt"]
        checks[phase+"_actual_new_process_readback"] = bool(receipt.get("input_unchanged") and receipt.get("writer_arrays_or_receipts_read") is False
            and receipt.get("status") == "read_actual_saved_blend" and job["process"]["returncode"] == 0)
    result.update(audit_status=status(checks), session=identity(state_path), version=state["version"],
        case_id=state["case_id"], stage=state.get("stage"), route=state.get("route"),
        saved_blends=dict(before=identity(before_blend), after=identity(after_blend)),
        Blender_jobs=jobs, Blender_wall_s=sum(job["wall_s"] for job in jobs.values()), consumer_claims_used_as_geometry_input=False)
    write(output / "AUDIT.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions-root", type=Path, default=HERE / "private/sessions")
    parser.add_argument("--session", action="append", choices=EXPECTED)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    output = args.output_dir.resolve()
    if not output.is_relative_to(HERE):
        raise ValueError("audit_output_must_be_in_current_batch")
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name in args.session or EXPECTED:
        directory = args.sessions_root.resolve() / name
        if not (directory / "session.json").exists():
            results.append(dict(session=name, audit_status="unknown", reason="session_missing"))
            continue
        try:
            result = audit_session(directory, output / name)
        except Exception as error:
            result = dict(audit_status="unknown", reason=type(error).__name__, detail=str(error), traceback=traceback.format_exc())
            write(output / name / "AUDIT_EXCEPTION.json", result)
        results.append(dict(session=name, audit_status=result["audit_status"], geometry_status=result.get("quality", {}).get("status"),
            report=identity(output / name / "AUDIT.json") if (output / name / "AUDIT.json").exists() else None))
        write(output / "PROGRESS.json", dict(sessions=results))
    all_sessions = {row["session"]: True if row["audit_status"] == "pass" else False if row["audit_status"] == "fail" else None for row in results}
    report = dict(audit_status=status(all_sessions), sessions=results, expected_sessions=list(args.session or EXPECTED),
        wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        category="independent final saved-Blender audit, nested Blender costs recorded separately in each session",
        consumer_claims_used_as_geometry_input=False, training_runs=0, Pro_calls=0, source_files=[identity(Path(__file__)), identity(oracle_path)])
    write(output / "SUMMARY.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
