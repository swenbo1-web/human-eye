"""Complete technical and private scoring checks on the fixed root midpoint."""

from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from evaluate import evaluate_packets
from score import score_packet


def checked_path(descriptor):
    path = Path(descriptor["path"])
    path = path if path.is_absolute() else HERE / path
    current = identity(path)
    if current["sha256"] != descriptor["sha256"] or current["bytes"] != descriptor["bytes"]:
        raise ValueError("fixed_source_identity_changed_" + str(path))
    return path


def main():
    started, cpu = time.perf_counter(), time.process_time()
    source = read("SOURCE_BINDING.json")
    midpoint = read("MIDPOINT_SOURCE_BINDING.json")
    for row in midpoint["files"]:
        checked_path(row)
    initial = {key: checked_path(value) for key, value in source["initial"].items()}
    image_result_path = checked_path(midpoint["image_result"])
    image_before = identity(image_result_path)
    frozen_image_read_epoch = time.time()
    directory = Path(midpoint["source_directory"]) / "private/midpoint/workers"
    attempts = HERE / "private/midpoint_qa"
    attempt = attempts / ("attempt_" + str(len(list(attempts.glob("attempt_*"))) + 1).zfill(3))
    attempt.mkdir(parents=True, exist_ok=False)
    quality = evaluate_packets(initial["packet"], directory / "readback.npz", initial["packet"], initial["spec"],
        before_state_path=initial["scene"], after_state_path=directory / "scene.json")
    write(attempt / "QUALITY.json", quality)
    scoring = read("SCORING_BINDING.json")
    target = checked_path(scoring["target"])
    score = score_packet(directory / "readback.npz", target, attempt / "SCORE.json",
        receipt_path=directory / "read_receipt.json")
    expected = read("MIDPOINT_RESULT.json")["private_quality"]
    comparisons = dict(
        support_RMSE_matches_fixed_result=score["metrics"]["support_47"]["after"]["RMSE_m"] == expected["support"]["RMSE_m"],
        support_reduction_matches_fixed_result=abs(score["metrics"]["support_47"]["RMSE_reduction_fraction"] - expected["support_RMSE_reduction_fraction"]) <= 1e-15,
        normal_227_RMS_matches_fixed_result=score["normal_editable_misedit"]["RMSE_m"] == expected["normal_editable_misedit"]["RMSE_m"],
        observation_RMSE_matches_fixed_result=score["metrics"]["observation_410"]["after"]["RMSE_m"] == expected["observation"]["RMSE_m"],
        fixed_image_result_preserved=identity(image_result_path) == image_before,
        independent_saved_receipt_verified=score["provenance"]["independent_saved_readback_verified"],
        complete_contact_scan=quality["geometry"]["self_intersection"]["exact_pair_scan_executed"])
    result = dict(cycle_id="M6-IMAGE-CALIBRATION-006", status="pass" if quality["status"] == "pass" and all(comparisons.values()) else "fail",
        technical_status=quality["status"], technical_checks=quality["checks"], comparisons=comparisons,
        restoration_quality_pass=score["restoration_quality_pass"], metrics=score["metrics"],
        normal_editable_misedit=score["normal_editable_misedit"], geometry=quality["geometry"], transition=quality["transition"],
        image_result_fixed_before_private_scoring=image_before, image_result_checked_epoch=frozen_image_read_epoch,
        artifacts=dict(technical=identity(attempt / "QUALITY.json"), private_score=identity(attempt / "SCORE.json"),
            reader_receipt=identity(directory / "read_receipt.json")),
        reused_historical_Blender_jobs=3, new_Blender_jobs=0, new_Pro=0, training=0,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        scope="Fixed root midpoint actual saved-file export, completed native protection and exact scoped contact QA. Historical image selection was fixed in the planning commit before this private score.")
    write(attempt / "RESULT.json", result)
    write("MIDPOINT_QA.json", result)
    print({key: result[key] for key in ("status", "technical_status", "restoration_quality_pass", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
