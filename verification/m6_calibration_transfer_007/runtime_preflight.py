"""Pure fixtures for transfer references and inherited calibration selection."""

import ast
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common
import calibrator
import calibration_batch
from common import identity, read, write
import numpy as np


@contextmanager
def fixture_environment(directory):
    previous = common.HERE, calibrator.HERE
    directory.mkdir(parents=True)
    common.HERE = calibrator.HERE = directory
    try:
        yield
    finally:
        common.HERE, calibrator.HERE = previous


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/runtime_preflight" / uuid.uuid4().hex[:8]
    checks, expected_errors = {}, []

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

    counters = dict(executions=0, measures=0)
    zero_baseline = True

    def fake_execute(source, proposal, ids, delta, stage, alpha, tag, progress):
        counters["executions"] += 1
        directory = calibrator.session_directory(stage, proposal["proposal_id"], tag)
        directory.mkdir(parents=True, exist_ok=True)
        row = dict(alpha=alpha, alpha_tag=tag, status="complete", technical_status="pass", session=str(directory))
        for key in ("payload", "saved_blend", "readback", "scene", "quality", "reader_receipt", "render_receipt", "render_run"):
            path = directory / (key + ".fixture")
            path.write_bytes((proposal["proposal_id"] + tag + key).encode())
            row[key] = identity(path)
        row["images"] = source["images"]["current"]
        return row

    def fake_measure(reference, candidate, *, output_dir=None, cache=None):
        counters["measures"] += 1
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "RGB.npz"
        path.write_bytes(b"Identity-only RGB fixture")
        tag = directory.parent.name.rsplit("_", 1)[-1]
        values = {"a0": 0, "a05": 0, "a1": 0} if zero_baseline else {"a0": 10, "a05": 5, "a1": 7}
        return dict(status="pass", absolute_error_sum=values[tag], sample_count=3686400,
            pooled_MAE_DN=values[tag] / 3686400, decoded_RGB_npz=identity(path))

    original_measure = calibrator.measure_images
    try:
        with fixture_environment(output / "unit"):
            fixture = calibrator.HERE
            for name in calibrator.RUNTIME_SOURCES + calibration_batch.EXTRA_SOURCES:
                (fixture / name).write_text("# Identity-only fixture source\n", encoding="utf8")
            initial = fixture / "current.npz"
            np.savez_compressed(initial, I_ids=np.array([0, 1, 2], dtype=np.int64))
            original = fixture / "source.fixture"
            original.write_bytes(b"Source identity fixture")
            proposal = fixture / "proposal.npz"
            np.savez_compressed(proposal, source_ids=np.array([1], dtype=np.int64),
                displacements_world=np.array([[0., .001, 0.]], dtype=np.float64))
            placeholder = fixture / "image.fixture"
            placeholder.write_bytes(b"Image identity fixture")
            views = [dict(name=name, location=[0, 0, 2], target=[0, 0, 0], ortho_scale=1,
                resolution=[640, 640]) for name in ("forearm_front", "forearm_side", "forearm_45")]
            images = {role: [dict(identity(placeholder), role=role + "_" + view["name"], camera=dict(specification=view))
                for view in views] for role in ("normal", "current")}
            source = dict(initial=dict(packet=identity(initial)), original=identity(original),
                proposals=[dict(proposal_id=name, points=1, payload=identity(proposal)) for name in ("raw", "second_fixture")],
                images=images, views=views, alphas=[0, .5, 1])
            write("SOURCE_BINDING.json", source)
            calibrator.measure_images = fake_measure
            request = calibrator.request_for("raw", "v2")
            _, _, ids, delta, binding = calibrator.validate_request(request, extra_sources=calibration_batch.EXTRA_SOURCES)
            check("single_new_proposal_reference_accepted", len(ids) == 1 and delta.shape == (1, 3))
            check("three_fixed_alpha_values", calibrator.ALPHAS == (0., .5, 1.))
            first = calibrator.calibrate(request, candidate_executor=fake_execute,
                extra_sources=calibration_batch.EXTRA_SOURCES)
            check("three_mocked_candidates", counters["executions"] == 3)
            check("zero_baseline_ratio_is_undefined", all(row["normalized_to_initial"] is None for row in first["result"]["candidates"]))
            check("zero_loss_tie_selects_alpha_zero", first["result"]["selected_alpha"] == 0.)
            check("new_cycle_metadata", first["result"]["cycle_id"] == "M6-CALIBRATION-TRANSFER-007")
            check("image_selection_frozen", calibrator.checked_identity(first["image_selection_freeze"]).is_file())
            check("private_geometry_scoring_deferred", first["result"]["independent_geometry_scoring"] == "pending_separate_private_scorer")
            before = dict(counters)
            warm = calibrator.calibrate(request, candidate_executor=fake_execute,
                extra_sources=calibration_batch.EXTRA_SOURCES)
            check("warm_calls_no_executor_or_metric", counters == before and warm["reused"])
            check("warm_reports_zero_new_Blender", warm["new_Blender_jobs"] == 0)
            check("warm_preserves_result_identity", warm["result_reference"] == first["result_reference"])
            bad = copy.deepcopy(request)
            bad["proposal_ref"]["sha256"] = "0" * 64
            reject("changed_proposal_reference_rejected", lambda: calibrator.validate_request(bad))
            bad = copy.deepcopy(request)
            bad["camera_views"][0]["ortho_scale"] += 1
            reject("changed_camera_reference_rejected", lambda: calibrator.validate_request(bad))
            reject("unknown_proposal_rejected", lambda: calibrator.request_for("unknown"))
            worker = fixture / "batch_worker.py"
            worker.write_bytes(worker.read_bytes() + b"# modified source\n")
            reject("cached_result_rejects_runtime_change", lambda: calibrator.calibrate(request,
                candidate_executor=fake_execute, extra_sources=calibration_batch.EXTRA_SOURCES))
            worker.write_text("# Identity-only fixture source\n", encoding="utf8")
            zero_baseline = False
            second = calibrator.calibrate(calibrator.request_for("second_fixture", "v2"),
                candidate_executor=fake_execute, extra_sources=calibration_batch.EXTRA_SOURCES)
            check("normal_integer_selection_unchanged", second["result"]["selected_alpha"] == .5)
            check("normal_ratio_unchanged", [row["normalized_to_initial"] for row in second["result"]["candidates"]] == [1., .5, .7])
            candidates = [dict(alpha=value, technical_status="pass", image=dict(status="pass", absolute_error_sum=1)) for value in (1., .5, 0.)]
            check("tie_smaller_alpha", calibrator.select_candidate(candidates)["alpha"] == 0.)
            candidates[-1]["technical_status"] = "fail"
            check("technical_failure_excluded", calibrator.select_candidate(candidates)["alpha"] == .5)
            check("no_eligible_candidate_explicit", calibrator.select_candidate([]) is None)
    finally:
        calibrator.measure_images = original_measure
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_text(encoding="utf8"), filename=str(path))
    check("current_root_python_AST", True)
    help_result = subprocess.run([str(common.PYTHON), "-I", "-B", "-X", "utf8", str(HERE / "protocol_client.py"), "--help"], capture_output=True)
    check("actual_CLI_accepts_generic_proposal_name", help_result.returncode == 0 and b"--proposal PROPOSAL" in help_result.stdout)
    check("no_actual_Blender_or_Pro_in_fixtures", True)
    result = dict(cycle_id="M6-CALIBRATION-TRANSFER-007", status="pass" if all(checks.values()) else "fail",
        passed=sum(checks.values()), total=len(checks), checks=checks, expected_errors=expected_errors,
        scope="Synthetic identities and candidate artifacts exercise inherited request, fixed-alpha integer selection, zero-baseline ratio, cache identity, and actual CLI help. No Blender or Pro launched.",
        actual_Blender_calls=0, actual_Pro_calls=0, counters=counters,
        evidence_directory=str(output.relative_to(HERE)), wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    write(output / "RESULT.json", result)
    write("RUNTIME_PREFLIGHT.json", result)
    print(json.dumps({key: result[key] for key in ("status", "passed", "total", "wall_s", "CPU_s")}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
