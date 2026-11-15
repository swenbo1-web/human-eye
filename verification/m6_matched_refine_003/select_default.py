"""Choose the experimental default using the pre-bound minimum-quality rule."""

import difflib
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "API_SELECTION.json").exists():
        raise ValueError("default_selection_already_recorded")
    stats = read("CONSUMER_STATS_all.json")["sessions"]
    scored = read("FINAL_VERIFICATION.json")["sessions"]
    if len(stats) != 4 or len(scored) != 4:
        raise ValueError("four_completed_scored_trials_required")
    stage = {}
    for name in ("v1", "v2"):
        rows = [row for row in stats if row["stage"] == name]
        stage[name] = dict(wall_s=sum(row["wall_s"] for row in rows), tools=sum(row["tools"] for row in rows),
            PNG_bytes=sum(row["images"]["PNG_bytes"] for row in rows),
            public_text_UTF8_bytes=sum(row["public_text_UTF8_bytes"] for row in rows),
            input_tokens=sum(row["usage"]["input_tokens"] for row in rows),
            cached_input_tokens=sum(row["usage"]["cached_input_tokens"] for row in rows),
            output_tokens=sum(row["usage"]["output_tokens"] for row in rows),
            saved_version_preview_sessions=sum(row["images"].get("final_saved_version_visualized", False) for row in rows))
    v2 = [row for row in scored if row["stage"] == "v2"]
    requirements = dict(v2_two_repairs_pass=all(row["restoration_quality_pass"] for row in v2),
        v2_technical_QA_pass=all(row["technical_status"] == "pass" for row in v2),
        v2_two_saved_previews=stage["v2"]["saved_version_preview_sessions"] == 2,
        v2_stage_wall_at_most_v1=stage["v2"]["wall_s"] <= stage["v1"]["wall_s"])
    chosen = "v2" if all(requirements.values()) else "v1"
    tool_versions = {name: read(filename) for name, filename in (("v1", "TOOL_FREEZE.json"), ("v2", "TOOL_FREEZE_v2.json"))}
    selected_sources = []
    patches = []
    for filename in ("consumer_bridge.py", "consumer_runner.py"):
        versions = {}
        for name in ("v1", "v2"):
            row = next(row for row in tool_versions[name]["files"] if Path(row["path"]).name == filename)
            path = HERE / row["archived"]["path"]
            if identity(path)["sha256"] != row["sha256"]:
                raise ValueError("executed_tool_archive_changed")
            versions[name] = path
        before, after = (versions[name].read_text(encoding="utf8").splitlines(keepends=True) for name in ("v1", "v2"))
        patches.extend(difflib.unified_diff(before, after,
            fromfile="a/verification/m6_matched_refine_003/" + filename,
            tofile="b/verification/m6_matched_refine_003/" + filename))
        (HERE / filename).write_bytes(versions[chosen].read_bytes())
        selected_sources.append(identity(HERE / filename))
    patch = HERE / "OPTIMIZATION_DIFF.patch"
    patch.write_text("".join(patches), encoding="utf8", newline="\n")
    changes = {key: dict(v1=stage["v1"][key], v2=stage["v2"][key],
                        delta=stage["v2"][key] - stage["v1"][key],
                        percent_change=100 * (stage["v2"][key] - stage["v1"][key]) / stage["v1"][key]
                        if stage["v1"][key] else None) for key in stage["v1"]}
    write("API_SELECTION.json", dict(default=chosen, requirements=requirements,
        selection_scope="Version-aware saved-model preview component in this isolated experiment",
        decision_rule=read("OPTIMIZATION_BINDING.json")["acceptance"], stage_costs=stage, stage_comparison=changes,
        current_sources=selected_sources, candidate_patch=identity(patch),
        score_by_session=[dict(session=row["session"], technical=row["technical_status"],
            quality_pass=row["restoration_quality_pass"], support_RMSE_m=row["metrics"]["support_47"]["after"]["RMSE_m"],
            support_reduction_fraction=row["metrics"]["support_47"]["RMSE_reduction_fraction"]) for row in scored],
        interpretation="All four meet the fixed minimum restoration criteria. V2 adds actual saved-file visual feedback. Native restoration precision declined substantially between stages. The observed timing difference does not establish a matched-quality or general causal speed benefit.",
        causal_image_contribution_to_repair=None, same_quality_speed_benefit_established=False,
        preview_after_final_geometry="Each V2 preview followed its only submit. No edit followed either preview.",
        model_method_variation="Both routes identify current coordinate-grid residuals. Their independently chosen restoration algorithms differ across stages.",
        formal_plugin_deployment=False, additional_Pro=0, additional_Blender=0,
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu))
    print("selected", chosen, "saved-version previews; matched-quality speed benefit unestablished", flush=True)


if __name__ == "__main__":
    main()
