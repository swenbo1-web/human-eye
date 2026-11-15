"""Record the fixed two-stage correspondence and actual-edit comparison."""

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, write


def main():
    if (HERE / "PLAN.json").exists():
        raise RuntimeError("plan_already_written")
    sequence = [dict(stage=stage, task_id="repair", route=route)
        for stage, route in (("v1", "native"), ("v1", "facts"), ("v2", "facts"), ("v2", "native"))]
    plan = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005",
        baseline_commit="6ed6c88e2ae91d08cff1e80fed436d2e3572bf77",
        contract_commit="b6a03e79807b494352eca71fd44dec9204780ecd",
        task_registration_epoch=1794783059.259194,
        consumer=dict(model="gpt-6.1-sol", reasoning_effort="medium", max_tool_calls=12,
            max_session_seconds=600, image_transport="mcp", required_API_preflight="API_PREFLIGHT.json",
            python_timeout_s=45, python_output_chars=5000, fact_output_chars=18000,
            answer_schema=dict(task_id="repair", execution_status="completed or incomplete with actual tool evidence",
                decision_status="completed or incomplete repair with observed evidence",
                modification_decision="edit or no_edit", visual_evidence="normal/current matched-view observations",
                active_region="computed source subset or region reference and transition",
                fit_audit="own diagnostic NPZ reference and actual support/rank/coverage/amplitude summary, or reason fitting was unused",
                operation_id="actual operation or null", version="actual final saved version",
                saved_blend="actual saved artifact", readback="independent actual saved-model readback",
                target_result="observed result", remaining_issues="remaining target uncertainty or incomplete repair")),
        sequence=sequence, actual_session_limit=4,
        correspondence=dict(algorithm="RGB maximum absolute channel difference minus DN2, full current displayed mesh pixel-center nearest-triangle zbuffer, incident visible-area normalized source aggregation, maximum of three matched local views",
            difference_threshold_DN=2, candidate_summary_budget=69, score_tie="source_ID_ascending",
            active_write_domain="I274", fitting_exclusion="All strictly positive-attention source IDs over the full current displayed mesh, plus the active core",
            visibility="incident_face_visible reports a source vertex's incident triangles having visible pixel-center area. Point visibility uses separate ray evidence.",
            region_references=["active_core", "outer_support", "transition", "unobserved", "full_mesh_exclusion"],
            allowed_algorithm_inputs=["current actual saved geometry", "matched normal/current PNG pixels", "frozen camera metadata"]),
        shared_capabilities="Both routes can read the same bound PNG pixels and camera metadata in Python, current full geometry, source IDs, F/I and protected domains, solve, submit, save/read back and preview the actual saved version. Facts additionally supplies deterministic correspondence and version-bound region references.",
        isolation="Normal reference 3D, hidden damaged support, noise parameters and independent target scoring remain controller/scorer-only. Consumer and correspondence imports/file access are restricted to current packets, shared image/camera inputs, registered reference packets and own payloads.",
        source_case=identity(HERE / "CASE_BINDING.json"), images=identity(HERE / "IMAGE_BINDING.json"),
        displacement_budget=dict(operation_m=0.006893660855829761, cumulative_m=0.006893660855829761),
        correspondence_scoring=dict(candidate_domain_points=274, candidate_budget=69, full_support_points=47,
            point_recall_minimum=.8, area_recall_minimum=.8, report="Actual visible-incident, positive-attention, unmapped, domain-exterior and pixel denominators; all TP/FP/FN and precision"),
        fitting_scoring="Read actual consumer diagnostic source IDs only after a stage is terminal, report support contamination, spatial/normal coverage, rank, estimated amplitudes and independent target amplitude bias. Missing diagnostics remain missing.",
        restoration_scoring=dict(support_points=47, support_RMSE_reduction_minimum=.30,
            observation_points=410, observation_RMSE="strict_decrease", normal_editable_points=227,
            normal_editable_RMS_maximum_m=.00010, normal_observation_points=363,
            report="Actual saved-file independent fresh readback, continuous RMSE/p95/max, changed points, transition/contact/side-depth and native identity"),
        technical_checks="Protected native coordinates, source and topology identities, matrix/UV/material/scene, finite values, new degeneracy/reversal and exact scoped contact. Gradient/normal changes are observations.",
        optimization="One evidence-based change after both v1 sessions and their result snapshots. Preserve data, DN2, 69-point evaluation budget, target and scoring. Freeze OPTIMIZATION_BINDING and stage-v2 sources before the reversed second pair.",
        limits=dict(training=0, Google_API_calls=0, new_paid_API_calls=0, formal_deployment=0,
            threads=1, numerical_Blender_timeout_s=7200, target_RSS_bytes=4 * 1024**3),
        accounting="All actual started consumers count, including failed runs. Preserve PNG decoding, raster/aggregation, first/reused cache, facts/reference and numerical arrays separately from model-visible text and image bytes. Nested timers retain their scope and unknown fees remain unmeasured.",
        completion="Fixed commit with complete local evidence, one authorized completion callback to the planning chat, AL delivery and batch end for independent review")
    write("PLAN.json", plan)
    print("fixed four-session two-stage plan written")


if __name__ == "__main__":
    main()
