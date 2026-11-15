"""Bind one post-save image-feedback optimization to the completed first-stage evidence."""

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "OPTIMIZATION_BINDING.json").exists():
        raise ValueError("only_one_optimization_binding_allowed")
    rows = []
    for route in ("native", "facts"):
        folder = HERE / "private/consumers/v1/matched" / route
        consumer = read(folder / "CONSUMER.json")
        if consumer["status"] != "completed" or not consumer["safe_to_continue"]:
            raise ValueError("two_terminal_first_stage_consumers_required")
        session = HERE / "private/sessions" / ("v1_matched_" + route)
        score = read(HERE / "private/final_verify" / session.name / "SCORE.json")
        rows.append(dict(route=route, consumer=identity(folder / "CONSUMER.json"),
            session=identity(session / "session.json"), final=identity(folder / "PUBLIC_FINAL.txt"),
            actual_score=identity(HERE / "private/final_verify" / session.name / "SCORE.json"),
            final_views=identity(HERE / "private/results" / session.name / "RESULT.json"),
            wall_s=consumer["wall_s"], usage=consumer["usage"], image_blocks=consumer["MCP_image_count"],
            repair_quality_pass=score["restoration_quality_pass"],
            support_RMSE_reduction_fraction=score["metrics"]["support_47"]["RMSE_reduction_fraction"]))
    archive = HERE / "private/optimization_before"
    archive.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(HERE / "analyze_consumers.py", archive / "analyze_consumers.py")
    write("OPTIMIZATION_BINDING.json", dict(
        cycle_id="M6-MATCHED-REFINE-003", bound_at_UTC=datetime.now(timezone.utc).isoformat(),
        initial_results=rows, initial_analysis=identity(HERE / "CONSUMER_STATS_v1.json"),
        initial_tools=identity(HERE / "TOOL_FREEZE.json"),
        first_stage_verification=identity(HERE / "FINAL_VERIFICATION_v1.json"),
        issue="Both first-stage final answers lack post-edit visual feedback. Native's second images call redelivered the same eight initial PNGs.",
        selected_change="Keep initial eight-image delivery. Once the isolated saved model is edited, images() renders four current same-camera model views, version- and saved-SHA-bound with caching. Both routes have the same tool and shared usage guidance.",
        expected_component_effect="Actual saved-model visual feedback replaces stale initial-image repetition after edits. Rendering has an explicit additional cost. Target geometry remains unavailable.",
        consumer_changes=dict(instruction_addendum="After an edit, images() now returns four views rendered from your current saved model with the same frozen cameras. Compare these with the normal reference images you already received before finishing. Initial images remain fixed; numerical and saved-file quality records remain available."),
        invariants="Same sample, initial damaged blend, clean PNGs, cameras, initial public packet, task, domains, displacement budgets, model/effort, tool count/deadline, hidden target and scoring code. No hidden target or mask enters the image tool.",
        permitted_source_changes=["consumer_bridge.py", "consumer_runner.py", "analyze_consumers.py"],
        supporting_audit_change="Image audit must validate each response's actual PNG source and distinguish frozen input blocks from saved-version preview blocks. This measures the selected change.",
        acceptance=dict(required="Both v2 saved repairs pass fixed restoration and technical criteria, and both obtain actual saved-version views",
            default_selection="Retain V1 if second-stage total Pro wall is higher, or repair/technical quality criteria fail. Component feedback availability and full-stage performance are reported separately.",
            generalization="Single fixed synthetic case, no general causal performance or image-reconstruction claim"),
        second_order=["facts", "native"], additional_Pro_sessions=2, additional_optimizations_allowed=0,
        synthetic_cue="V1 native identifies 1/4096 m coordinate-grid residuals and infers a shared correction direction. The high restoration precision depends on that current-input cue; PNG causal contribution is unmeasured.",
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu,
    ))
    print("one actual post-save image-feedback issue bound before changing V2 tools", flush=True)


if __name__ == "__main__":
    main()
