"""Prepare equal consumer cases and exercise the actual edit protocol locally."""

from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from consumer_bridge import Bridge
import numpy as np


SEQUENCE = [("v1", "s01", "native"), ("v1", "s01", "facts"), ("v1", "s02", "facts"),
    ("v1", "s02", "native"), ("v2", "s02", "facts"), ("v2", "s01", "facts")]


def prepare_session(stage, case_id, route):
    directory = HERE / "private/sessions" / (stage + "_" + case_id + "_" + route)
    directory.mkdir(parents=True, exist_ok=False)
    case = HERE / "private/cases" / case_id
    shutil.copyfile(case / "before.blend", directory / "before.blend")
    state = dict(stage=stage, case_id=case_id, route=route, version=0, case_dir=str(case),
        current_blend=str(directory / "before.blend"), current_npz=str(case / "initial.npz"),
        initial_npz=str(case / "initial.npz"), current_scene=str(case / "baseline_scene.json"),
        source_spec=str(case / "spec.json"), current_blend_identity=identity(directory / "before.blend"),
        operations=[], pending=None)
    write(directory / "session.json", state)
    return directory


def prepare_cases():
    for row in read("GEOMETRY.json")["cases"]:
        case_id = row["case_id"]
        directory = HERE / "private/consumer_cases" / case_id
        directory.mkdir(parents=True, exist_ok=False)
        spec = read("private/cases/" + case_id + "/spec.json")
        task = dict(task_id=case_id, intent="Make the middle of the specified surface region slightly fuller outward along the supplied fixed initial smoothed normals, cover a connected middle region, fade smoothly to the protected boundary, and retain surface detail and all other vertices.",
            geometry=dict(full_vertices=27304 if case_id == "s01" else 29299, F=row["F"], B0=row["B0"], B1=row["B1"], I=row["I"], C=row["C"]),
            unit=spec["unit"], ell=spec["ell"], h=spec["h"], center_source_id=spec["center_source_id"],
            normal_definition=spec["normal_definition"],
            sets_definition="Local graph uses source triangles wholly in F. B0 are endpoints of edges incident to exactly one local triangle. B1 are local neighbors of B0 excluding B0. I=F minus B0 union B1. The entire full-source complement of I is fixed. Edge-length shortest distance is to B0 union B1 in the local graph. C consists of finite interior distances at least 0.75 times the largest finite interior distance.",
            disconnected_I_source_ids=row["I_unreachable"],
            disconnected_rule="Any I point unreachable from the protected layers must receive zero displacement.",
            acceptance=dict(center_axial_h_range=[.95, 1.05], core_median_axial_minimum_h=.6,
                maximum_displacement_h=1.1, tangential_maximum=max(spec["tangent_abs_tol"], .01*spec["h"]),
                high_set="I points with axial displacement greater than 0.5h form one local-edge-connected component containing center, and include at least half of C",
                maximum_incident_edge_displacement_gradient=.2, maximum_affected_template_normal_change_deg=5,
                outside_I="saved local float32 coordinates bitwise fixed", preserve="source IDs, native polygon loops, object matrices, other objects, UVs, materials and packed images",
                safety="no new degenerate or reversed affected triangles, and no new non-simplex surface intersections against the complete mesh"),
            accounting="Each task starts from an independent unchanged baseline. Displacements are measured cumulatively from V0. A submitted displacements_world payload is relative to current V. Unknown physical units on s02 remain native source units.",
            artistic_acceptance="The numerical specification is an engineering refinement target. Actual model and same-camera images support subsequent human visual judgement.")
        write(directory / "task.json", task)
        with np.load(HERE / "private/cases" / case_id / "initial.npz", allow_pickle=False) as initial:
            names = ("vertices", "vertices_world", "vertices_local", "faces", "source_ids", "F_source_ids", "I_ids", "C_ids", "B0_ids", "B1_ids", "n0")
            np.savez_compressed(directory / "input.npz", **{name:initial[name] for name in names})
    for item in SEQUENCE:
        prepare_session(*item)


def response_value(response):
    import json
    value = json.loads(response["content"][0]["text"])
    if response.get("isError"):
        raise RuntimeError(str(value))
    return value


def main():
    started = time.perf_counter()
    prepare_cases()
    checks, executions = {}, []
    for case_id in ("s01", "s02"):
        session = prepare_session("preflight", case_id, "native")
        bridge = Bridge(SimpleNamespace(case=HERE / "private/consumer_cases" / case_id, session=session,
            audit=HERE / "private/preflight" / case_id, route="native", max_tool_calls=10,
            python_timeout_s=45, python_output_chars=16000, fact_output_chars=50000))
        code = """import math
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import spsolve
print(type(V), repr(V[:2]), math.sqrt(4))
print(cKDTree(V[I_ids]).query(V[center], k=2))
A=csr_matrix(np.array([[2.,-1.],[-1.,2.]]))
print(dijkstra(abs(A),directed=False), spsolve(A,np.ones(2)), np.linalg.solve(A.toarray(),np.ones(2)))
print(save_edit(np.array([center]),np.array([0.2*h*n0[center]]),mode='displacements_world'))
"""
        result = response_value(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
        checks[case_id + "_ordinary_python"] = result["error"] is None
        payload = result["created_payloads"][0]
        api = bridge.load_api()
        if case_id == "s02":
            real_run_job = api.run_job
            def lose_writer_receipt(script, job, label):
                output = real_run_job(script, job, label)
                if script == "blender_edit.py":
                    receipt = Path(output["receipt_path"])
                    receipt.rename(receipt.with_name("receipt.delayed.json"))
                    raise RuntimeError("preflight_simulated_missing_writer_receipt_after_actual_save")
                return output
            api.run_job = lose_writer_receipt
        result = response_value(bridge.call(dict(name="submit_edit", arguments=dict(payload_id=payload["payload_id"],
            expected_version=payload["observed_version"], operation_id="protocol_preflight"))))
        checks[case_id + "_actual_save_read"] = result["independently_reopened"] and result["version"] == 1
        first_identity = result["saved_blend"]
        duplicate = api.submit_edit(session, session / "payloads" / (payload["payload_id"] + ".npz"), 0, "protocol_preflight")
        checks[case_id + "_idempotent_no_second_edit"] = duplicate["idempotent_receipt"] and duplicate["saved_blend"] == first_identity
        try:
            api.submit_edit(session, session / "payloads" / (payload["payload_id"] + ".npz"), 0, "stale_new_operation")
        except ValueError as error:
            checks[case_id + "_stale_version_rejected"] = str(error) == "stale_expected_version"
        state = api.load_state(session)
        with np.load(state["initial_npz"], allow_pickle=False) as initial, np.load(state["current_npz"], allow_pickle=False) as current:
            center = read(Path(state["source_spec"]))["center_source_id"]
            requested = initial["vertices"][center] + .2*read(Path(state["source_spec"]))["h"]*initial["n0"][center]
            inverse = np.linalg.inv(initial["matrix_world"])
            expected_native = (requested @ inverse[:3,:3].T + inverse[:3,3]).astype(np.float32)
            checks[case_id + "_actual_payload_quantization_only"] = expected_native.tobytes() == current["vertices_local"][center].tobytes()
            outside = np.setdiff1d(np.arange(len(initial["vertices"])), [center])
            checks[case_id + "_unsubmitted_native_bitwise"] = initial["vertices_local"][outside].tobytes() == current["vertices_local"][outside].tobytes()
            bad = session / "payloads/bad_outside.npz"
            np.savez_compressed(bad, source_ids=np.array([outside[~np.isin(outside, initial["I_ids"])][0]]), displacements_world=np.zeros((1,3)))
        try:
            api.submit_edit(session, bad, 1, "outside_test")
        except ValueError as error:
            checks[case_id + "_outside_I_rejected"] = str(error) == "sparse_source_ids_require_unique_nonempty_subset_of_I"
        if case_id == "s02":
            checks[case_id + "_missing_receipt_actual_recovery"] = bool(result["receipt_recovery"])
        bridge.save(True)
        executions.append(dict(case_id=case_id, operation=result))
    report = dict(status="pass" if all(checks.values()) else "fail", checks=checks, actual_Pro_sessions=0,
        actual_Blender_edits=2, actual_independent_Blender_reads=2, executions=executions,
        feasibility_scoring=False, purpose="ordinary interpreter, exact submission, version, idempotency and missing-receipt actual-state recovery", wall_s=time.perf_counter()-started)
    write("TOOL_PREFLIGHT.json", report)
    print(report["status"], report["wall_s"], len(checks), flush=True)
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
