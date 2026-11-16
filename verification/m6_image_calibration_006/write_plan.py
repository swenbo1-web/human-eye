"""Record fixed proposals, three coefficients and the single optimization boundary."""

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BLENDER, PYTHON, identity, read, write


def main():
    if (HERE / "PLAN.json").exists():
        raise RuntimeError("plan_already_written")
    source = read("SOURCE_BINDING.json")
    plan = dict(cycle_id="M6-IMAGE-CALIBRATION-006", baseline_commit=source["baseline_commit"],
        contract_commit=source["contract_commit"], task_registration_epoch=1794788664.5798278,
        proposals=[dict(proposal_id=row["proposal_id"], source_payload=row["source_payload"],
                        payload=row["payload"], source_points=row["points"]) for row in source["proposals"]],
        alphas=[0, .5, 1], geometry_rule="Each coefficient starts at the same actual V0, preserving source IDs and multiplying the frozen original world-displacement payload by alpha.",
        metric=dict(local_views=["forearm_front", "forearm_side", "forearm_45"], resolution=[640, 640],
            RGB_sample_count=3686400, rule="Pooled integer RGB absolute error sum divided by sample count; report per-view errors and ratio to actual alpha0.",
            selection="Minimum image error among technically available candidates, exact tie chooses smaller alpha.",
            binding="Current geometry, proposal, reference/current PNG bytes, camera and renderer source identities"),
        stage_v1=dict(entrypoint="Actual calibration protocol client calling the reusable calibrator", execution="Six cold candidates, each actual sparse write/save, independent fresh read and three-view render using existing owned workers.",
            expected_Blender_processes=18, warm_reuse="Repeat identical requests after validating complete input/output identities, with zero new owned Blender jobs."),
        stage_v2=dict(boundary="Only after all first-stage candidate/image/technical results, image choices and complete cost are fixed.",
            allowed_optimization="One owned-process batch per proposal, resetting to the same initial file before each candidate, then saving and freshly reopening for reading/rendering. Reference RGB reuse belongs to the same batch preparation change.",
            invariants="Alpha set, proposals, target images, sample count, metric, tie rule, actual native coordinates, camera, RGBA, image errors and selected coefficient.",
            adoption="Compare complete calibration wall/CPU/RSS, process versus logical operation counts and cold/warm costs. Retain first version if measured benefit is insufficient."),
        independent_scoring=dict(order="Freeze actual image result and coefficient choice before loading private target coordinates or support labels.",
            support_points=47, support_RMSE_reduction_minimum=.30, observation_points=410,
            observation_RMSE="strict_decrease", normal_editable_points=227, normal_editable_RMS_maximum_m=.00010,
            normal_observation_points=363, report="RMSE/p95/max, normal displacement, actual activity, exterior/native preservation, boundary/side-depth and complete scoped contacts."),
        technical_QA="Existing source/native topology, matrix, UV/material/scene and protected-coordinate preservation, operation/cumulative budget, finite coordinates, new degeneracy/reversal and full associated-domain contact comparison.",
        midpoint=dict(source=identity(HERE / "MIDPOINT_SOURCE_BINDING.json"), image_result=identity(HERE / "MIDPOINT_IMAGE_RESULT.json"),
            role="Historical independent pre-registered alpha0.5 control. New entrypoint reproduces its saved arrays and image ordering and completes its technical/contact QA."),
        isolation="Calibration and image selection use current state, fixed proposals, matched reference PNGs/cameras and technical QA. Private geometry target and damaged labels are read only by the independent scorer after image freezing.",
        recovery="Persist candidate and operation state. Inspect completed owned artifacts and identity-bound receipts before resuming. Preserve operation IDs and read attempt counters.",
        source_binding=identity(HERE / "SOURCE_BINDING.json"), Python=identity(PYTHON), Blender=identity(BLENDER),
        resources=dict(threads=1, target_RSS_bytes=4 * 1024**3, numerical_Blender_timeout_s=7200),
        limits=dict(new_Pro_consumers=0, training=0, Google_API_calls=0, new_paid_API_calls=0, formal_deployment=0),
        accounting="Separate actual protocol clients, historical proposal-model generation, all current calibration work/failed attempts, nested worker operations, process resources and image decode/cache observations. Unmeasured fees and root/agent usage remain unknown.",
        conclusion_scope="One fixed development asset and two historical proposals at exactly three coefficients. Report failure within these sampled coefficients and independent target quality separately from image improvement.",
        completion="Fixed commit, complete local evidence and source references, one authorized planning callback, AL delivery and batch end for independent review.")
    write("PLAN.json", plan)
    print("fixed calibration plan written")


if __name__ == "__main__":
    main()
