"""Independent scoring after actual image selections have been frozen."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from evaluate import evaluate_packets, packet
from score import score_packet
import numpy as np


def checked_path(descriptor):
    path = Path(descriptor["path"])
    path = path if path.is_absolute() else HERE / path
    current = identity(path)
    if current["sha256"] != descriptor["sha256"] or current["bytes"] != descriptor["bytes"]:
        raise ValueError("scoring_bound_file_changed_" + str(path))
    return path


def independent_image_sums(source, results, output):
    references = [dict(row, path=str(checked_path(row).resolve())) for row in source["images"]["normal"]]
    requests = []
    for result in results:
        for candidate in result["candidates"]:
            rows = [dict(row, path=str(checked_path(row).resolve())) for row in candidate["images"]]
            requests.append(dict(proposal_id=result["proposal_id"], alpha=candidate["alpha"], images=rows))
    code = """import json, sys
from PIL import Image, ImageChops, ImageStat
data = json.loads(sys.stdin.read())
views = ('forearm_front', 'forearm_side', 'forearm_45')
references = {}
for row in data['references']:
    view = next(view for view in views if row['role'].endswith(view))
    with Image.open(row['path']) as image:
        references[view] = image.convert('RGB')
results = []
for request in data['requests']:
    sums = []
    count = 0
    for row in request['images']:
        view = next(view for view in views if row['role'].endswith(view))
        with Image.open(row['path']) as image:
            current = image.convert('RGB')
        if current.size != (640, 640) or references[view].size != current.size:
            raise ValueError('fixed image dimensions required')
        difference = ImageChops.difference(references[view], current)
        absolute_sum = sum(int(value) for value in ImageStat.Stat(difference).sum)
        sums.append(dict(view=view, absolute_error_sum=absolute_sum))
        count += current.width * current.height * 3
    results.append(dict(proposal_id=request['proposal_id'], alpha=request['alpha'], per_view=sums,
        absolute_error_sum=sum(row['absolute_error_sum'] for row in sums), sample_count=count))
print(json.dumps(results))
"""
    python = Path("C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
    started = time.perf_counter()
    process = subprocess.run([str(python), "-I", "-B", "-X", "utf8", "-c", code],
        input=json.dumps(dict(references=references, requests=requests)).encode(), capture_output=True, check=True)
    (output / "PILLOW_IMAGE_SUMS.json").write_bytes(process.stdout)
    (output / "PILLOW_IMAGE_SUMS.stderr").write_bytes(process.stderr)
    return json.loads(process.stdout), time.perf_counter() - started


def score_stage(stage):
    started, cpu = time.perf_counter(), time.process_time()
    source = read("SOURCE_BINDING.json")
    results, freezes = [], []
    checks = {}
    output = HERE / "private/scoring" / stage
    output.mkdir(parents=True, exist_ok=True)
    for proposal in source["proposals"]:
        proposal_id = proposal["proposal_id"]
        result_path = HERE / ("CALIBRATION_" + stage + "_" + proposal_id + ".json")
        freeze_path = HERE / ("IMAGE_SELECTION_FREEZE_" + stage + "_" + proposal_id + ".json")
        frozen = read(freeze_path)
        if frozen["status"] != "image_selection_frozen" or frozen["private_target_read_by_calibrator"] is not False:
            raise ValueError("frozen_image_only_selection_required")
        if checked_path(frozen["image_result"]).resolve() != result_path.resolve():
            raise ValueError("freeze_bound_to_other_result")
        result = read(result_path)
        if result["binding_sha256"] != frozen["binding_sha256"]:
            raise ValueError("image_result_binding_mismatch")
        if [candidate["alpha"] for candidate in result["candidates"]] != [0., .5, 1.]:
            raise ValueError("fixed_three_alpha_order_required")
        for candidate in result["candidates"]:
            for key in ("saved_blend", "payload", "readback", "scene", "quality", "reader_receipt", "render_receipt", "render_run"):
                checked_path(candidate[key])
            checked_path(candidate["image"]["decoded_RGB_npz"])
            render = read(checked_path(candidate["render_receipt"]))
            if render["status"] != "rendered_actual_saved_full_character" or render["current_blend"]["sha256"] != candidate["saved_blend"]["sha256"]:
                raise ValueError("image_score_render_saved_model_binding_mismatch")
            if render["geometry_scale"] != 1 or render["displacement_scale"] != 1 or render["scene_changes_saved"]:
                raise ValueError("image_score_render_scale_or_saved_scene_mismatch")
            by_view = {row["role"].removeprefix("current_"): row for row in candidate["images"]}
            normal_by_view = {row["role"].removeprefix("normal_"): row for row in source["images"]["normal"]}
            if len(render["views"]) != 3 or set(by_view) != set(normal_by_view):
                raise ValueError("fixed_three_render_views_required")
            for view in render["views"]:
                row = by_view[view["specification"]["name"]]
                camera = {key: view[key] for key in ("specification", "camera_matrix_world", "world_to_image_affine_2_by_3", "world_to_image_offset", "pixel_convention")}
                if row["camera"] != camera or camera != normal_by_view[view["specification"]["name"]]["camera"]:
                    raise ValueError("score_matched_camera_provenance_mismatch")
                if checked_path(row).resolve() != checked_path(view["image"]).resolve():
                    raise ValueError("score_image_path_differs_from_render_receipt")
        results.append(result)
        freezes.append(dict(path=identity(freeze_path), frozen=frozen, image_result=identity(result_path)))
    independent, pillow_wall = independent_image_sums(source, results, output)
    by_key = {(row["proposal_id"], row["alpha"]): row for row in independent}
    for result in results:
        proposal_id = result["proposal_id"]
        for candidate in result["candidates"]:
            comparison = by_key[(proposal_id, candidate["alpha"])]
            prefix = proposal_id + " alpha" + str(candidate["alpha"])
            checks[prefix + " exact independent Pillow RGB sum"] = comparison["absolute_error_sum"] == candidate["image"]["absolute_error_sum"]
            checks[prefix + " full RGB sample count"] = comparison["sample_count"] == candidate["image"]["sample_count"] == 3686400
        eligible = [candidate for candidate in result["candidates"] if candidate["technical_status"] == "pass" and candidate["image"]["status"] == "pass"]
        selected = min(eligible, key=lambda candidate: (candidate["image"]["absolute_error_sum"], candidate["alpha"])) if eligible else None
        checks[proposal_id + " fixed image technical selector"] = result["selected_alpha"] == (selected["alpha"] if selected else None)
    if not all(checks.values()):
        raise ValueError("independent_image_selection_verification_failed_before_private_scoring")
    private_started = time.time()
    target = checked_path(read("SCORING_BINDING.json")["target"])
    initial = {key: checked_path(value) for key, value in source["initial"].items()}
    scored_rows = []
    for result in results:
        for candidate in result["candidates"]:
            proposal_id, alpha = result["proposal_id"], candidate["alpha"]
            directory = output / proposal_id / candidate["alpha_tag"]
            directory.mkdir(parents=True, exist_ok=True)
            after_path, scene_path = checked_path(candidate["readback"]), checked_path(candidate["scene"])
            qa = evaluate_packets(initial["packet"], after_path, initial["packet"], initial["spec"],
                before_state_path=initial["scene"], after_state_path=scene_path)
            write(directory / "QUALITY.json", qa)
            score = score_packet(after_path, target, directory / "SCORE.json", receipt_path=checked_path(candidate["reader_receipt"]))
            points = packet(directory / "SCORE_points.npz")
            changed = points["displacement_norm"] > 1e-12
            support = points["support_ids"]
            changed_ids = points["source_ids"][changed]
            technical_agrees = qa["status"] == candidate["technical_status"]
            checks[proposal_id + " alpha" + str(alpha) + " technical QA agreement"] = technical_agrees
            scored_rows.append(dict(proposal_id=proposal_id, alpha=alpha, selected=alpha == result["selected_alpha"],
                technical_status=qa["status"], image=dict(absolute_error_sum=candidate["image"]["absolute_error_sum"],
                    sample_count=candidate["image"]["sample_count"], MAE_DN=candidate["image"]["pooled_MAE_DN"],
                    normalized_to_initial=candidate["normalized_to_initial"]),
                restoration_quality_pass=score["restoration_quality_pass"], restoration_checks=score["checks"],
                metrics=score["metrics"], normal_editable_misedit=score["normal_editable_misedit"],
                activity=dict(changed_points=len(changed_ids), TP=len(np.intersect1d(changed_ids, support)),
                    FP=len(np.setdiff1d(changed_ids, support)), FN=len(np.setdiff1d(support, changed_ids))),
                geometry=qa["geometry"], transition=qa["transition"], displacement=qa["displacement"],
                depth_and_axis_observations=score["depth_and_axis_observations"],
                artifacts=dict(saved_blend=candidate["saved_blend"], reader_receipt=candidate["reader_receipt"],
                    readback=candidate["readback"], quality=identity(directory / "QUALITY.json"),
                    score=identity(directory / "SCORE.json"), points=identity(directory / "SCORE_points.npz")),
                new_model_consumer=False, model_self_assessment="Historical 005 proposal source only"))
    for row in freezes:
        checked_path(row["image_result"])
        checked_path(row["path"])
    summary = dict(cycle_id="M6-IMAGE-CALIBRATION-006", stage=stage,
        status="pass" if all(checks.values()) else "fail", checks=checks, passed=sum(checks.values()), total=len(checks),
        candidates=scored_rows, selection_freezes=freezes, private_scoring_started_epoch=private_started,
        Pillow_independent_image_sum_wall_s=pillow_wall, actual_Blender_calls=0, actual_Pro_calls=0,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        negative_scope="Independent restoration results cover exactly alpha 0, 0.5 and 1 for the two fixed proposals.")
    write("CALIBRATION_SCORES_" + stage + ".json", summary)
    print(dict(status=summary["status"], candidates=len(scored_rows), restoration_passes=sum(row["restoration_quality_pass"] for row in scored_rows), wall_s=summary["wall_s"]))
    if summary["status"] != "pass":
        raise SystemExit(1)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2"), required=True)
    score_stage(parser.parse_args().stage)


if __name__ == "__main__":
    main()
