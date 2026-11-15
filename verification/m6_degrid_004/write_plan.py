"""Write the single two-consumer contract before validating its public entrypoint."""

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    if (HERE / "PLAN.json").exists():
        raise ValueError("single_plan_already_written")
    plan = dict(
        cycle_id="M6-DEGRID-004", baseline_commit="c58e464d454c83b90b3c9baa026478c590e578e6",
        contract_commit="f974cf88ecdb0ccc3677aa204d7bba02521841ec",
        consumer=dict(model="gpt-6.1-sol", reasoning_effort="medium", max_tool_calls=12,
            max_session_seconds=600, image_transport="mcp", required_API_preflight="API_PREFLIGHT.json",
            python_timeout_s=45, python_output_chars=5000, fact_output_chars=18000,
            answer_schema=dict(task_id="repair", decision_status="completed or incomplete",
                modification_decision="edit or no_edit", visual_evidence="brief observed normal/current comparison",
                active_region="own active subset or stable region reference with transition",
                operation_id="actual operation or null", version="actual final saved version",
                saved_blend="actual saved artifact reference", readback="independent saved-model readback reference",
                target_result="observed target result", remaining_issues="actual limitations or incomplete repair")),
        sequence=[dict(stage="run", task_id="repair", route="facts"), dict(stage="run", task_id="repair", route="native")],
        actual_session_limit=2,
        runtime="Previously verified V2 current-geometry facts, sparse editing, independent saved readback and version-bound image preview. Current task paths and neutral public identifiers are adapted before the single freeze.",
        construction=dict(seed=2026111604, half_width_m=1 / 8192, region_points=410, editable_points=274,
            noise_array_sha256="cd8e84d38618d3de642a7023ea02d3244a61d3353a94582747130fd12118e5fb",
            rule="Fixed original F order, default_rng independent coordinate uniform noise; same array added to normal and damaged, exterior zero, original 47 damage vectors retained before save precision",
            normal_target="Actual new normal saved Blender readback", current_initial="Actual new damaged saved Blender readback"),
        input_isolation="Consumers receive current saved geometry, damaged V0/n0, shared normal/current PNGs and repair tools. Construction parameters, clean3D, hidden support and old programs remain in private controller/scoring records.",
        displacement_budget=dict(operation_m=0.006893660855829761, cumulative_m=0.006893660855829761),
        technical_checks="Source/native topology, protected native coordinates, matrix, UV/material/scene preservation, finite values, new degeneracy/reversal and exact scoped contact. Gradient and normal change are observed.",
        scoring=dict(support_points=47, support_RMSE_reduction_minimum=.30, observation_points=410,
            observation_RMSE_rule="strictly_decreases", normal_editable_points=227,
            normal_editable_displacement_RMS_maximum_m=.00010, normal_observation_points=363,
            continuous_metrics="RMSE/p95/max, normal point displacements, exterior/native precision, transition, contact and depth/inner observations",
            input="Final actual saved-file independent readback", same_quality="Minimum pass is reported alongside continuous errors"),
        old_program_diagnostics=identity(HERE / "DIAGNOSTICS.json"),
        case_binding=identity(HERE / "CASE_BINDING.json"), images=identity(HERE / "IMAGE_BINDING.json"),
        limits=dict(threads=1, numerical_Blender_s=7200, target_RSS_bytes=4 * 1024**3, training=0, Google_API=0),
        protocol="Single frozen facts then native sequence, no intermediate truth feedback, tuning or additional consumer",
        completion="Fixed Git commit and complete local evidence, one authorized planning callback and independent review",
    )
    write("PLAN.json", plan)
    print("single two-session plan written for public entrypoint preflight", flush=True)


if __name__ == "__main__":
    main()
