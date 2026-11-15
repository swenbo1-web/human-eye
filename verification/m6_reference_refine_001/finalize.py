"""Publish measured correspondence with the explicit uncertainty outcome."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write

PUBLIC_CODE = ("common.py", "background.py", "blender_common.py", "blender_read.py", "blender_render.py", "prepare_sources.py", "prepare_views.py",
    "run_blender_prepare.py", "prepare_contract.py", "annotate_reference.py", "reference_geometry.py", "bind_model_anchors.py",
    "threshold_sensitivity.py", "independent_anchors.py", "observe.py", "verify_observation.py", "finalize.py")
PUBLIC_DATA = ("CONTRACT.md", "PRIOR_REVIEW.md", "INPUT_BINDING.json", "PLAN.json", "PLAN_FREEZE.json", "ANNOTATION.json",
    "INDEPENDENT_ANCHORS.json", "MODEL_ANCHOR_BINDING.json", "SENSITIVITY_REPORT.json", "OBSERVATION.json", "OBSERVATION_VERIFICATION.json",
    "IMAGE_PROTOCOL_PREFLIGHT_SUMMARY.json", "VISUAL_COSTS.json", "COSTS.json", "VIEWABLES.json", "RUN_STATUS.json", "REPORT.md", "MANIFEST.json")


def main():
    observed, annotation = read("OBSERVATION.json"), read("ANNOTATION_DRAFT.json")
    verification = read("OBSERVATION_VERIFICATION.json")
    if verification["status"] != "pass" or not all(observed["checks"].values()):
        raise AssertionError("observation_evidence_not_verified")
    sources = read("SOURCES.json")
    original = sources["cases"][0]
    if identity(Path(original["source_original"]))["sha256"] != original["source_identity"]["sha256"]:
        raise AssertionError("original_model_file_changed")
    for row in read("INPUT_BINDING.json")["inputs"]:
        if identity(Path(row["path"]))["sha256"] != row["sha256"]:
            raise AssertionError("reference_source_changed")
    if identity(HERE / "private/cases/s01/before.blend")["sha256"] != "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d":
        raise AssertionError("original_model_identity_mismatch")
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text(encoding="utf8"))
    plan = dict(cycle_id="M6-REFERENCE-REFINE-001", baseline_commit="d121d7fd86db16c3cf4f2338704359685571df9a",
        contract_commit="dff6c9b78493d2438ebedcde69fb2c69b9f8568d", branch="observation_measurement_correspondence_within_annotation_uncertainty",
        actual_goal="Correspond original image-right forearm to model positive-Y forearm and measure its outer contour under fixed EW similarity alignment",
        primary_anchors=observed["primary_anchors"], stations=annotation["stations"], target_interval=[.25,.8],
        annotation_uncertainty=observed["uncertainty"], independent_anchor_family=observed["alternative_anchors"],
        source_points_observed=599, editable_source_points=0, protected_source_points=27304,
        decision="All sampled signed uncertainty intervals cross zero, and an independently chosen plausible landmark family reverses the signed direction. The fixed contract permits correspondence delivery in this condition.",
        geometry_improvement_percent=None, engineering20percent_criterion="conditional on a resolved editable reference mismatch; current branch is correspondence only",
        consumer_plan=dict(maximum=4, initial_order=["native","facts"], optimized_order=["facts","native"], tool_limit=12, session_seconds=600,
            intended_model="gpt-6.1-sol", intended_reasoning_effort="medium", actual_Pro_sessions=0,
            execution_status="not_run_under_explicit_contract_uncertainty_branch"),
        annotation_provenance="Two agents selected visible landmarks independently. The second agent knew that uncertainty was under review, without seeing the first coordinates or desired edit sign. User landmark confirmation and artistic acceptance remain unmeasured.",
        geometry_protection="all source vertices protected for this observation outcome", training=0, original_asset_edits=0)
    write("PLAN.json", plan)
    write("ANNOTATION.json", dict(primary_anchors=annotation["anchors"], station_values=observed["primary_stations"],
        baseline_MAE=observed["primary_outer_MAE"], baseline_max_abs=annotation["baseline_outer_max_abs"],
        sensitivity=annotation["sensitivity"], alternate_stations=observed["alternative_stations"],
        selected_anchor_source_ids=dict(E=24321,W=16916), complete_annotation=identity(HERE / "ANNOTATION_DRAFT.json")))
    statuses = [dict(stage=stage,route=route,status="not_run_under_uncertainty_branch", Pro_sessions=0, geometry_edits=0)
        for stage, routes in (("v1",("native","facts")),("v2",("facts","native"))) for route in routes]
    write("RUN_STATUS.json", dict(correspondence_status="completed", stations_verified=5, consumer_runs=statuses,
        performance_optimization="not_run_without_initial_consumer_results_under_this_branch", actual_image_Pro_consumption=0,
        local_image_protocol_preflight=identity(HERE / "CONSUMER_PREFLIGHT.json"),
        local_protocol_scope="PNG bytes and four MCP image blocks verified by a local protocol client. No Pro model image-consumption claim.",
        draft_editing_adapter_status="local drafts, actual new-task edit/contour-quality integration was not executed under the uncertainty branch"))
    protocol=read("CONSUMER_PREFLIGHT.json")
    write("IMAGE_PROTOCOL_PREFLIGHT_SUMMARY.json",dict(status=protocol["status"],local_checks=protocol["count"],
        CLI_help_image_flag_verified=True, CLI_image_argument_construction_verified=True,
        actual_fresh_local_stdio_client_image_blocks=4, PNG_bytes_and_dimensions=protocol["real_image_inputs"],
        actual_Pro_image_consumption=0, actual_Blender_API_preflight=0,
        scope="Local protocol client receives exact original PNG data. Shared edit/focus/resolve/sections use fixture mocks.",
        full_local_record=identity(HERE/"CONSUMER_PREFLIGHT.json")))
    processes=[]
    for path in sorted((HERE / "private/processes").glob("*.controller.json")):
        row=read(path); process=row["process"]
        processes.append(dict(phase=row["phase"], wall_s=process["full_process_wall_s"], tree_CPU_s=process["tree_cpu_s"],
            sampled_tree_peak_RSS_bytes=process["tree_sampled_peak_working_set_bytes"], returncode=process["returncode"]))
    local_costs=[identity(HERE / path) for path in ("INPUT_BINDING.json", "VISUAL_COSTS.json", "private/independent_anchors/COSTS.json", "CONSUMER_PREFLIGHT.json")]
    jobs=[read(path) for path in sorted((HERE / "private/jobs").glob("*/run.json"))]
    image_records=[]
    for path in sorted((HERE/"private").rglob("*.png")):
        raw=path.read_bytes()
        width,height=struct.unpack(">II",raw[16:24])
        image_records.append(dict(identity(path),width=width,height=height))
    write("private/IMAGE_ARTIFACTS.json",dict(files=image_records,scope="Includes source copies, context views, annotation images and grid crops, each physical file counted once"))
    preflight_runs=HERE/"private/consumer_preflight/RUNS.json"
    write("COSTS.json",dict(Pro_sessions=0, Pro_tokens=0, training_runs=0, geometry_edits=0, actual_Blender_jobs=len(jobs),
        render_jobs=sum(row["script"]["path"]=="blender_render.py" for row in jobs), actual_baseline_read_jobs=sum(row["script"]["path"]=="blender_read.py" for row in jobs),
        monitored_processes=processes, monitored_inclusive_wall_s=sum(row["wall_s"] for row in processes),
        monitored_tree_CPU_s=sum(row["tree_CPU_s"] for row in processes), max_sampled_tree_RSS_bytes=max(row["sampled_tree_peak_RSS_bytes"] for row in processes),
        nested_Blender_wall_s=sum(row["wall_s"] for row in jobs), measured_local_reports=local_costs,
        local_image_files=len(image_records),local_image_bytes=sum(row["bytes"] for row in image_records),
        local_image_pixels=sum(row["width"]*row["height"] for row in image_records),image_index=identity(HERE/"private/IMAGE_ARTIFACTS.json"),
        all_consumer_preflight_attempts=identity(preflight_runs) if preflight_runs.exists() else None,
        failed_preflight="private/consumer_preflight retains a0.32859s incomplete mock-session fixture failure and recovery",
        failed_foreground_probe="VISUAL_COSTS retains a0.2028877s multi-intersection threshold probe and recovery",
        unknowns=["root/subagent reasoning and manual landmark-selection time and token cost", "read-only image-view tool time", "unmeasured CPU on early local probes"],
        accounting="Numerical controllers include nested Blender. Annotation/crop/preflight reports use separate enclosing timers, with nested function times marked. No cross-scope total is inferred.",
        no_new_Pro_image_model_calls=True))
    images=[dict(role=view["specification"]["name"],image=view["image"]) for view in read("BASE_VIEWS.json")["views"]]
    images += [dict(role=role,image=identity(HERE / "private/annotation" / filename)) for role,filename in (
        ("reference annotation","reference_annotated.png"),("source whole correspondence","whole_front_source_mapping.png"),
        ("source local correspondence","forearm_front_source_mapping.png"),("similarity contour overlay","similarity_contour_overlay.png"))]
    write("VIEWABLES.json",dict(whole_model=observed["whole_model"], images=images, geometry_result="original full model with verified correspondence and observation",
        after_edit_artifacts=0, station_source_mapping=observed["source_mapping"]))
    frozen=["PLAN.json","INPUT_BINDING.json","ANNOTATION_DRAFT.json","INDEPENDENT_ANCHORS.json","MODEL_ANCHOR_BINDING.json","SENSITIVITY_REPORT.json","OBSERVATION.json","OBSERVATION_VERIFICATION.json"]
    write("PLAN_FREEZE.json",dict(files=[identity(HERE/name) for name in frozen], actual_Pro_before_and_after=0,
        stage="observation-outcome freeze after annotation and independent verification, preceding any consumer or edit"))
    base=HERE.as_posix()
    lines=["# M6-REFERENCE-REFINE-001 原画前臂对应", "", "本批按固定合同的不确定度分支完成原画、真实模型与sourceID对应。当前标注尚不能稳定决定前臂外展或收窄。", "",
        "## 实际测量", "", "| 肘腕站 | 原画外距/EW | 模型外距/EW | 模型减原画 | 原画宽/EW | 模型宽/EW |", "|---|---:|---:|---:|---:|---:|"]
    for row in observed["primary_stations"]:
        lines.append(f"| {row['t']:.0%} | {row['reference_outer']:.6f} | {row['model_outer']:.6f} | {row['signed_outer']:+.6f} | {row['reference_width']:.6f} | {row['model_width']:.6f} |")
    lines += ["", "主标注原画E=(707,520)、W=(752,695)，模型局部E=(282,126)、W=(354,421)，仅用EW相似变换。五站平均外距误差为肘腕长的1.2750%。3个原画像素的保守边界项为1.6603%，原画与模型分别81组合理锚点情景的残差敏感性区间在五站均跨0。这些是手工定位敏感性，统计置信度未测。", "",
        "27组颜色阈值检查的边缘最大位移约1.03原画像素。另一名agent在看不到前组坐标和位移方向时独立选点，原画E=(708,524)、W=(751,678)，模型E=(274,140)、W=(350,393)。该对应的五站外距残差均为正，平均绝对误差1.4450%。两套腕前位置存在纵向分歧，锚点由agent视觉标注，用户尚未确认。", "",
        "主标注35%站的内外轮廓同向偏移，宽度仅差0.001038EW。轴线或姿态对应可产生这种投影差。当前证据支持先交付可核查对应，进一步单侧形变的方向需要更明确的锚点依据。", "",
        "## 模型与真实图", "", f"[完整对应模型]({base}/private/results/corresponding_model.blend) 的SHA与原始模型一致。599点前臂观察域、五站截线与原生polygon/sourceIDs的重心坐标映射已保留，最近可见E/W源点为24321与16916。独立边截法复算五站外距及宽度，24项来源/坐标/保护/引用检查通过，实际focus和resolve各1次。", "",
        f"[整体对应图]({base}/private/annotation/whole_front_source_mapping.png)、[局部对应图]({base}/private/annotation/forearm_front_source_mapping.png)、[同尺度轮廓叠图]({base}/private/annotation/similarity_contour_overlay.png)、[侧面]({base}/private/views/before/forearm_side.png)和[45度]({base}/private/views/before/forearm_45.png) 来自真实原模型。位置示意图标出原410点种子，599点观察域和五站源映射另有JSON及NPZ原件。原画标注与独立标注原件均在本机private目录。", "",
        "## 运行范围和成本", "", "依固定合同关于标注不确定度的条款，Pro会话0、几何编辑0、训练0。四个计划消费者及首版后优化记录为未运行，轮廓改善百分比记为不适用。本批交付对应模型和测量，修改后图片、消费者原回答与全任务提速结果均无新增原件。", "",
        "本地消费者预检18项通过，CLI图片参数和4个MCP图像块的原字节经协议客户端验证。Pro实际图像消费为0。新任务的编辑/评价适配草稿留作本机过程记录，其实际执行预检在当前分支中未运行。公开执行入口为prepare_sources、prepare_views、observe和verify_observation及标注/阈值/source映射脚本。", "",
        "实际Blender2次，1次新进程读取与1次生成4视图的渲染。数值控制器及标注、27阈值、独立选点、IPC/图片协议预检、失败探针均分别计入COSTS及关联原件，嵌套计时单列。模型推理费用、主线程与子agent视觉选点推理的时间和token成本未测。", "",
        "原画、模型文件及正式插件保持原有身份。当前全部27304源点受到保护，变动点0，新增自交的受影响域为空，坐标/拓扑/矩阵逐位保持由实际回读及源文件摘要核验。", "",
        "建议规划下一步先统一肘关节中心与腕前最窄位置的解剖标志，再结合姿态对应固定一个超过标注不确定度的可见修改目标。本批结束后进入既有独立复核和明确派工循环。", ""]
    (HERE/"REPORT.md").write_text("\n".join(lines),encoding="utf8",newline="\n")
    public=sorted(PUBLIC_CODE+PUBLIC_DATA)
    rows=[dict(identity(path),category="public" if path.parent==HERE and path.name in public else "local_private_evidence_or_unexecuted_draft")
        for path in sorted(HERE.rglob("*")) if path.is_file() and path.name not in ("MANIFEST.json","HANDOFF.json")]
    write("MANIFEST.json",dict(files=rows,count=len(rows),bytes=sum(row["bytes"] for row in rows),public_files=public,
        exclusions=["MANIFEST self","postcommit HANDOFF.json"],status="correspondence_completed_uncertainty_branch"))
    print("public",len(public),"manifest",len(rows),"uncertainty branch, Pro0/edit0")


if __name__ == "__main__":
    main()
