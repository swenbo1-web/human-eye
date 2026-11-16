"""Pure state-machine fixtures and actual read-only protocol calls."""

from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common
import calibrator
from common import identity, read, write
from protocol_client import call


def absolute_descriptors(value):
    if isinstance(value, list):
        return [absolute_descriptors(item) for item in value]
    if isinstance(value, dict):
        copied = {key: absolute_descriptors(item) for key, item in value.items()}
        if {"path", "sha256", "bytes"}.issubset(copied):
            copied["path"] = str(calibrator.absolute(copied["path"]))
        return copied
    return value


@contextmanager
def fixture_environment(directory, source):
    old_common, old_calibrator = common.HERE, calibrator.HERE
    directory.mkdir(parents=True)
    for name in calibrator.RUNTIME_SOURCES:
        (directory / name).write_text("# Identity-only numerical protocol fixture.\n", encoding="utf8")
    (directory / "SOURCE_BINDING.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf8")
    common.HERE = calibrator.HERE = directory
    try:
        yield
    finally:
        common.HERE, calibrator.HERE = old_common, old_calibrator


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/calibration_preflight" / uuid.uuid4().hex[:6]
    output.mkdir(parents=True)
    checks, expected_errors, attempts = {}, [], []

    def check(name, value):
        checks[name] = bool(value)

    def reject(name, action):
        try:
            action()
        except (ValueError, RuntimeError, FileNotFoundError) as error:
            expected_errors.append(dict(name=name, type=type(error).__name__, message=str(error)))
            check(name, True)
        else:
            check(name, False)

    request = calibrator.request_for("v1_native")
    real_status = call("status", request, output=output / "status")
    check("actual_JSON_lines_status_client_exit_zero", real_status["process_returncode"] == 0)
    check("actual_status_no_error", "error" not in real_status["response"])
    check("actual_status_formal_unstarted", real_status["response"].get("result", {}).get("status") == "not_started")
    bad = copy.deepcopy(request)
    bad["proposal_ref"]["sha256"] = "0" * 64
    protocol_reject = call("calibrate", bad, output=output / "badref")
    check("actual_protocol_rejects_changed_reference_before_execution", "error" in protocol_reject["response"])
    check("actual_protocol_stdout_exactly_one_JSON_line", len((output / "badref/STDOUT.bin").read_bytes().splitlines()) == 1)
    source = absolute_descriptors(read("SOURCE_BINDING.json"))
    original_measure = calibrator.measure_images
    counters = dict(executions=0, decodes=0, fail_once=True)

    def fake_executor(source, proposal, ids, delta, stage, alpha, tag, progress):
        counters["executions"] += 1
        if proposal["proposal_id"] == "v2_facts" and tag == "a05" and counters["fail_once"]:
            counters["fail_once"] = False
            progress["status"] = "mock_saved_output_needs_receipt_recovery"
            raise RuntimeError("fixture_partial_receipt")
        directory = calibrator.session_directory(stage, proposal["proposal_id"], tag)
        directory.mkdir(parents=True, exist_ok=True)
        result = dict(alpha=alpha, alpha_tag=tag, status="complete", technical_status="pass", session=str(directory))
        for key in ("payload", "saved_blend", "readback", "scene", "quality", "reader_receipt", "render_receipt", "render_run"):
            path = directory / (key + ".fixture")
            path.write_bytes((proposal["proposal_id"] + tag + key).encode())
            result[key] = identity(path)
        result["images"] = source["images"]["current"]
        return result

    def fake_measure(reference, candidate, *, output_dir=None, cache=None):
        counters["decodes"] += 1
        path = Path(output_dir) / "RGB.npz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"identity-only RGB fixture")
        tag = Path(output_dir).parent.name.rsplit("_", 1)[-1]
        sums = {"a0": 10, "a05": 5, "a1": 7}
        return dict(status="pass", absolute_error_sum=sums[tag], sample_count=3686400,
            pooled_MAE_DN=sums[tag] / 3686400, decoded_RGB_npz=identity(path))

    fixture = output / "unit"
    try:
        with fixture_environment(fixture, source):
            calibrator.measure_images = fake_measure
            first = calibrator.calibrate(calibrator.request_for("v1_native"), candidate_executor=fake_executor)
            check("cold_executes_exactly_three_candidates", counters["executions"] == 3)
            check("three_fixed_alphas", [row["alpha"] for row in first["result"]["candidates"]] == [0., .5, 1.])
            check("integer_MAE_selects_half", first["result"]["selected_alpha"] == .5)
            check("normalizes_to_current", [row["normalized_to_initial"] for row in first["result"]["candidates"]] == [1., .5, .7])
            check("selection_freeze_exists_before_private_scoring", calibrator.checked_identity(first["image_selection_freeze"]).is_file())
            before_exec, before_decode = counters["executions"], counters["decodes"]
            warm = calibrator.calibrate(calibrator.request_for("v1_native"), candidate_executor=fake_executor)
            check("warm_result_identity_preserved", warm["result_reference"] == first["result_reference"])
            check("warm_validates_and_reuses_zero_execution", warm["reused"] and counters["executions"] == before_exec and counters["decodes"] == before_decode)
            check("warm_reports_zero_new_Blender", warm["new_Blender_jobs"] == 0)
            freeze_path = calibrator.checked_identity(first["image_selection_freeze"])
            freeze_path.rename(fixture / "ORIGINAL_FREEZE_RECEIPT.json")
            recovered = calibrator.calibrate(calibrator.request_for("v1_native"), candidate_executor=fake_executor)
            check("missing_freeze_receipt_recovered_from_verified_result", recovered["reused"] and calibrator.checked_identity(recovered["image_selection_freeze"]).is_file())
            tie = [dict(alpha=a, technical_status="pass", image=dict(status="pass", absolute_error_sum=5)) for a in (1., .5, 0.)]
            check("exact_tie_selects_smallest_alpha", calibrator.select_candidate(tie)["alpha"] == 0.)
            tie[2]["technical_status"] = "fail"
            check("technical_failure_excluded_from_selection", calibrator.select_candidate(tie)["alpha"] == .5)
            check("no_eligible_candidate_is_explicit", calibrator.select_candidate([]) is None)
            bad = calibrator.request_for("v1_native")
            bad["camera_views"][0]["ortho_scale"] += 1
            reject("changed_camera_reference_rejected", lambda: calibrator.validate_request(bad))
            reject("unknown_proposal_rejected", lambda: calibrator.request_for("other"))
            runtime = fixture / "calibrator.py"
            original_runtime = runtime.read_bytes()
            runtime.write_bytes(original_runtime + b"# changed runtime\n")
            reject("cached_request_rejects_runtime_source_change", lambda: calibrator.calibrate(calibrator.request_for("v1_native"), candidate_executor=fake_executor))
            runtime.write_bytes(original_runtime)
            model = calibrator.checked_identity(first["result"]["candidates"][0]["saved_blend"])
            original_model = model.read_bytes()
            model.write_bytes(b"changed artifact")
            reject("warm_rejects_modified_saved_artifact", lambda: calibrator.calibrate(calibrator.request_for("v1_native"), candidate_executor=fake_executor))
            model.write_bytes(original_model)
            reject("partial_candidate_receipt_preserved", lambda: calibrator.calibrate(calibrator.request_for("v2_facts"), candidate_executor=fake_executor))
            status = calibrator.status(calibrator.request_for("v2_facts"))
            check("query_exposes_pending_failure_state", status["state"]["candidates"]["a05"]["status"] == "failed")
            check("failed_call_does_not_freeze_image_selection", not (fixture / "CALIBRATION_v1_v2_facts.json").exists())
            before_retry = counters["executions"]
            resumed = calibrator.calibrate(calibrator.request_for("v2_facts"), candidate_executor=fake_executor)
            check("resume_only_incomplete_candidate", counters["executions"] == before_retry + 1 and resumed["result"]["selected_alpha"] == .5)
            check("fixture_source_current_alpha_contract", source["alphas"] == [0., .5, 1.])
            attempts.append(dict(stage="pure_fixture", counters=dict(counters)))
    finally:
        calibrator.measure_images = original_measure
    check("formal_candidate_sessions_uncreated", not (HERE / "private/sessions").exists())
    result = dict(cycle_id="M6-IMAGE-CALIBRATION-006", status="pass" if all(checks.values()) else "fail",
        checks=checks, passed=sum(checks.values()), total=len(checks), expected_errors=expected_errors, attempts=attempts,
        protocol_status_evidence=identity(output / "status/RESULT.json"), protocol_rejection_evidence=identity(output / "badref/RESULT.json"),
        scope="Synthetic candidate artifacts exercise state/receipt/selection logic. Actual subprocess protocol calls are read-only status and changed-reference rejection. No fixture blend is opened by Blender.",
        evidence_directory=str(output.relative_to(HERE)), actual_Blender_calls=0, actual_Pro_calls=0,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    write(output / "RESULT.json", result)
    write("CALIBRATION_PREFLIGHT.json", result)
    print(json.dumps({key: result[key] for key in ("status", "passed", "total", "wall_s", "CPU_s")}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
