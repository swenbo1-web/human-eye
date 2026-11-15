"""Exercise a private exact-restoration control through the real edit/read API."""

from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from session_api import load_state, save_readback, submit_edit
from score import score_packet
import numpy as np


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "API_PREFLIGHT.json").exists():
        raise ValueError("actual_control_already_completed")
    directory = HERE / "private/sessions/control_repair_restore"
    target = HERE / "private/scoring/target.npz"
    checks = {}
    initial_state = load_state(directory)
    checks["control_starts_at_actual_damaged_version_zero"] = initial_state["version"] == 0
    payload = directory / "payloads/control.npz"
    shutil.copyfile(HERE / "private/construction/control_restore.npz", payload)
    result = submit_edit(directory, payload, 0, "isolated_exact_restore")
    checks["real_sparse_write_and_independent_read"] = result["status"] == "saved_and_independently_read" and result["independently_reopened"]
    checks["technical_quality_pass"] = result["quality"]["status"] == "pass"
    checks["nonzero_actual_saved_edit"] = result["quality"]["displacement"]["changed_vertices"] > 0
    checks["exact_pair_scan_executed"] = result["quality"]["geometry"]["self_intersection"]["exact_pair_scan_executed"]
    repeated = submit_edit(directory, payload, 0, "isolated_exact_restore")
    checks["same_operation_returns_idempotent_receipt"] = repeated.get("idempotent_receipt") is True
    state = load_state(directory)
    checks["control_version_one"] = state["version"] == 1 and len(state["operations"]) == 1
    receipt = HERE / "private/jobs" / result["reader_job"] / "receipt.json"
    score = score_packet(state["current_npz"], target, HERE / "private/control/SCORE.json", receipt_path=receipt)
    checks["restoration_three_private_criteria_pass"] = score["restoration_quality_pass"]
    checks["saved_world_restoration_sub_micrometer"] = score["metrics"]["support_47"]["after"]["maximum_m"] < 1e-6
    checks["normal_editable_native_coordinates_preserved"] = score["normal_editable_misedit"]["maximum_m"] == 0
    second_read = save_readback(directory)
    checks["standalone_real_save_readback"] = second_read["independently_reopened"] and second_read["quality"]["status"] == "pass"
    checks["standalone_read_operation_displacement_zero"] = second_read["quality"]["displacement"]["input_to_after_maximum_world"] == 0
    checks["same_actual_saved_identity_on_two_reads"] = second_read["saved_blend"]["sha256"] == result["saved_blend"]["sha256"]
    rejected = []

    def reject(label, values, expected_version):
        path = directory / "payloads" / (label + ".npz")
        np.savez_compressed(path, **values)
        try:
            submit_edit(directory, path, expected_version, label)
        except ValueError as error:
            checks[label] = True
            rejected.append(dict(label=label, type=type(error).__name__, message=str(error)))
        else:
            checks[label] = False

    with np.load(state["initial_npz"], allow_pickle=False) as packet:
        editable = packet["I_ids"]
        vertices = packet["vertices_world"]
        protected = packet["protected_ids"]
    reject("reject_stale_version", dict(source_ids=editable[:1], displacements_world=np.zeros((1, 3))), 0)
    reject("reject_protected_vertex", dict(source_ids=protected[:1], displacements_world=np.zeros((1, 3))), 1)
    budget = read(state["source_spec"])["max_operation_displacement_m"]
    reject("reject_overbudget_operation", dict(source_ids=editable[:1], displacements_world=np.array([[2 * budget, 0., 0.]])), 1)
    state_after = load_state(directory)
    checks["rejected_calls_do_not_advance_version"] = state_after["version"] == 1 and len(state_after["operations"]) == 1
    consumer_states = [read(path) for path in (HERE / "private/sessions").glob("run_repair_*/session.json")]
    checks["two_consumer_sessions_still_unmodified"] = len(consumer_states) == 2 and all(row["version"] == 0 and not row["operations"] for row in consumer_states)
    checks["original_asset_unchanged"] = identity(read("CASE_BINDING.json")["original"]["path"])["sha256"] == read("CASE_BINDING.json")["original"]["sha256"]
    write("API_PREFLIGHT.json", {
        "status": "pass" if all(checks.values()) else "fail", "checks": checks,
        "passed": sum(checks.values()), "total": len(checks),
        "control_session": str(directory), "actual_operation": result,
        "independent_standalone_readback": second_read, "private_score": score,
        "rejected_calls": rejected, "control_isolated_from_consumers": True,
        "actual_Blender_calls": 3, "actual_Pro_sessions": 0,
        "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu,
    })
    if not all(checks.values()):
        raise RuntimeError("actual_control_checks_failed")
    print("actual clean-restoration control passed through edit, save and independent reads", flush=True)


if __name__ == "__main__":
    main()
