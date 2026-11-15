"""Write compact public summaries and a byte manifest, leaving geometry local."""

import ast
from pathlib import Path
import sys
import time
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from collect_costs import collect


PUBLIC_JSON = {"PLAN.json", "PLAN_FREEZE.json", "PLANNING_PREFLIGHT.json", "SOURCES.json", "GEOMETRY.json",
    "FACTS_PREFLIGHT.json", "TOOL_PREFLIGHT.json", "TOOL_FREEZE.json", "TOOL_FREEZE_v2.json",
    "OPTIMIZATION_BINDING.json", "CONSUMER_STATS_v1.json", "CONSUMER_STATS_v2.json", "CONSUMER_STATS_all.json",
    "REFERENCE_SUMMARY.json", "RENDER_SUMMARY.json", "RECOVERY_SUMMARY.json", "TRANSPORT_SUMMARY.json",
    "QUALITY_VERIFICATION.json", "ARTIFACT_VERIFICATION.json", "VIEWABLES_SUMMARY.json", "CONSUMER_PERFORMANCE.json", "COSTS.json", "MANIFEST.json", "FINALIZATION.json"}


def public_paths():
    return sorted(path for path in HERE.iterdir() if path.is_file() and (path.suffix == ".py" or path.name in PUBLIC_JSON or path.name in ("REPORT.md", "CONTRACT.md", "CONSUMER_STATS_v1.md", "CONSUMER_STATS_v2.md", "CONSUMER_STATS_all.md")))


def summarize_local_evidence():
    reference = read("REFERENCE_CONTROL.json")
    keys = ("case_id", "status", "checks", "center_over_h", "core_median_over_h", "maximum_gradient", "maximum_normal_change_deg", "unreachable_I", "original_source_unchanged")
    write("REFERENCE_SUMMARY.json", dict(cases=[{key:row[key] for key in keys} for row in reference["cases"]],
        wall_s=reference["wall_s"], cpu_s=reference["cpu_s"], nested_Blender_wall_s=reference["nested_blender_wall_s"],
        image_count=reference["image_count"], full_local_evidence=identity(HERE / "REFERENCE_CONTROL.json"),
        final_reference_fields_supplied_to_consumers=False, thresholds_changed=False))
    render = read("RENDER_PREFLIGHT.json")
    write("RENDER_SUMMARY.json", dict(status=render["status"], display_version=render["display_version"],
        camera_and_geometry_scale_unchanged=render["camera_and_geometry_scale_unchanged"], displacement_scale=render["displacement_scale"],
        render_specs=render["render_specs"], wall_s=render["wall_s"], cpu_s=render["cpu_s"], nested_Blender_wall_s=render["nested_blender_wall_s"],
        full_local_evidence=identity(HERE / "RENDER_PREFLIGHT.json"), source=render["renderer"],
        display_choice="Initial 80/20 light exposure and 8/2 preview retained. Final shared 16/4 clay lighting and fixed initial cameras used for every consumer comparison."))
    recovery = read("RECOVERY_REGRESSION.json")
    write("RECOVERY_SUMMARY.json", dict(status=recovery["status"], checks=recovery["checks"], wall_s=recovery["wall_s"],
        parent_cpu_s=recovery["cpu_s"], nested_Blender_wall_s=recovery["nested_Blender_wall_s"],
        full_local_evidence=identity(HERE / "RECOVERY_REGRESSION.json"),
        repair="Persist independent-reader attempt index before launch, so a prelaunch failure can recover through a fresh job identity",
        actual_writer_processes=1, actual_reader_processes=1, injected_prelaunch_faults=1, formal_consumer_occurrences=0))
    transport = read("TRANSPORT_BENCHMARK.json")
    names = ("status", "checks", "comparison", "totals", "wall_s", "accounting", "formal_v2_snapshot_cache_before", "formal_v2_snapshot_cache_after", "actual_Pro_sessions", "actual_Blender_calls")
    write("TRANSPORT_SUMMARY.json", {name:transport[name] for name in names} | dict(full_local_evidence=identity(HERE / "TRANSPORT_BENCHMARK.json")))
    views = read("VIEWABLES.json")
    compact = []
    for row in views["sessions"]:
        compact.append({key:row[key] for key in ("session", "stage", "case_id", "route", "version", "before_blend", "after_blend")})
        compact[-1]["local_results_directory"] = (HERE / "private/results" / row["session"]).as_posix()
    write("VIEWABLES_SUMMARY.json", dict(sessions=compact, session_count=views["session_count"], image_count=views["image_count"],
        geometry_scale=1., displacement_scale=1., full_local_evidence=identity(HERE / "VIEWABLES.json")))


def write_report(costs):
    rows = read("CONSUMER_STATS_v1.json")["sessions"] + read("CONSUMER_STATS_v2.json")["sessions"]
    lines = ["# M6-REFINE-001 实际定向精修", "",
        "本批把大模型计算位移、修改独立 Blender 副本、保存及新进程回读连成完整闭环。两例使用事前固定的初始平滑法向、核心、保护层和局部尺度幅度，六次真实 Pro 会话均保留原文、操作记录和模型。", "",
        "## 实际结果", "", "| 轮次 | 来源 | 组别 | 回读 | 中心位移/h | 核心中位数/h | 工具数 | 会话秒 |", "|---|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        state = read(HERE / "private/sessions" / (row["stage"]+"_"+row["task_id"]+"_"+row["route"]) / "session.json")
        measured = state["operations"][-1]["quality"]
        lines.append(f"| {row['stage']} | {row['task_id']} | {row['route']} | {measured['status']} | {measured['displacement']['center_over_h']:.6f} | {measured['displacement']['core_median_over_h']:.6f} | {row['tools']} | {row['wall_s']:.3f} |")
    lines += ["", "初末模型由额外十二个新 Blender 进程再次打开。独立核验重算了位移、连通、保存精度、拓扑、场景和完整网格相关自交候选，最终结果见 QUALITY_VERIFICATION.json。消费者最终回答中的操作、文件引用及测量值另行核对。", "",
        "s01 为 Yanyite 的固定 410 点空间选区，允许修改 274 点，h 为 0.714294 毫米。s02 为 face 正常观察 o0002 的 384 点区域，允许修改 220 点，h 为 0.01191649 原生单位。s02 的物理单位未知，两个无局部三角形连接的点保留零位移。", "",
        "I 外的宿主 float32 坐标逐位保持。原生多边形顶点环、source ID、矩阵、其他对象、材质、UV 和打包图片分别核对。Yanyite 原有十个退化三角形继续保留，其与本次受影响域的相关候选通过精确 AABB 和交叠核检查。", "",
        "## 模型与同机位图片", "", "每行模型均来自该消费者实际保存的完整 blend。局部 OBJ 与三向前后 PNG 位于同一结果目录，全部文件身份见 VIEWABLES.json。前图在完整 baseline blend 摘要和相机规格一致时复制已核验渲染，复制成本单列。后图由实际保存几何重新渲染。", ""]
    for row in read("VIEWABLES.json")["sessions"]:
        blend = row["after_blend"]["absolute_path"].replace("\\", "/")
        directory = HERE / "private/results" / row["session"]
        image = (directory / "after_views/view_01.png").as_posix()
        before = (directory / "before_views/view_01.png").as_posix()
        lines += [f"- {row['session']} 的[完整模型]({blend})、[修改前]({before})和[修改后]({image})。"]
    lines += ["", "图片采用统一中性材质、冻结的相机和真实位移尺度。前期过曝图和调整光照的预览原件均保留。face 区域近乎平片，固定幅度下变化细微。工程规格由规划合同确定，美术满意度仍需人工观看判断。", "",
        "## 一次性能优化与恢复修复", "", "四个首版结果固定后，用 session 和版本绑定的二进制 NPZ 几何包替换重复大数组 JSON 传输。八次首版 Python 调用共传输 52,746,408 字节请求 JSON，四次重复了同版本快照。冷创建、复用、数组逐位一致和普通 SciPy 调用另有本地对照，详见 TRANSPORT_SUMMARY.json。两次优化会话继续从独立原始模型开始，其位移由各自消费者计算。", "",
        "独立审计同时复现了 reader 在创建输出目录前失败后的重试标签冲突。修复将下一次 reader 编号在启动前写入状态。真实故障注入后保留已保存模型，另一新进程回读成功，版本只增加一次。六个正式消费者均未触发这一异常路径，速度变化的解释单独列出该修复。", "",
        "六次本地传输对照的 snapshot 加 executor 合计为 inline 4.9414 秒、NPZ 3.4641 秒。正式两次 v2 事实会话合计 145.9407 秒，首版两次事实会话合计 127.2288 秒。两例按固定次序单次运行，模型 token 缓存、执行顺序和会话差异共同影响总时间，当前样本量仅覆盖这两例。组件成本及逐任务总时间见 CONSUMER_PERFORMANCE.json。", "",
        "## 成本与原件", "", f"真实 Pro 会话共 {costs['actual_Pro_sessions']} 次，累计会话墙钟 {costs['consumer_wall_s']:.3f} 秒。训练次数为 0。数值阶段控制器累计 {costs['numerical_controller_inclusive_wall_s']:.3f} 秒，峰值采样进程树工作集 {costs['numerical_controller_max_sampled_tree_RSS_bytes']/1024**2:.2f} MiB。Blender 和 Python 子调用属于嵌套成本，独立预检与失败恢复均保留分类记录。完整成本见 COSTS.json 和 private/costs/FULL_COSTS.json。", "",
        "输入、缓存输入、输出 token 按 CLI 实际事件统计。货币费用、提供方内部重试及完整 CLI 进程树 CPU/RSS 缺少测量值，记为 unknown。MANIFEST.json 覆盖本地原件字节身份，原模型、数组、图片、完整回执和模型回答留在本机。公开提交包含脚本、规格及紧凑统计。", "",
        "首版分析器在绑定后追加 Blender 作业状态，审核文件随后追加恢复回归结果。v2 运行前补记了证据身份，原始绑定另存 private/optimization/BOUND_ORIGINAL.json。原四个消费者及 session 原件保持固定，性能选择与目标保持原绑定。此前聚合文件的早期完整字节未单独留存，其身份和全部原始事件继续可查。", "",
        "## 执行入口与下一批", "", "consumer_runner.py 驱动固定会话，consumer_bridge.py 提供普通 Python 计算和提交工具，session_api.py 提供 submit_edit、state、save_readback 及版本化实际保存。blender_edit.py 和 blender_read.py 分别执行修改与独立导出。verify_quality.py 从实际 blend 重读核验。每次 payload 与 operation ID 保留独立身份，读取恢复状态后可安全查询既有结果。", "",
        "建议下一批在新区域加入真实美术修改指令和人工前后判定，复用本批已经验证的保存、保护和独立回读链路。该批固定提交回报规划后，继续既有独立复核和明确派工循环。", ""]
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf8", newline="\n")


def main():
    started = time.perf_counter()
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text(encoding="utf8"))
    summarize_local_evidence()
    costs = collect()
    write_report(costs)
    public = public_paths()
    public_names = {path.name for path in public} | {"FINALIZATION.json", "MANIFEST.json"}
    write("FINALIZATION.json", dict(AST_scripts=len(list(HERE.glob("*.py"))), public_files=[path.name for path in public],
        all_actual_sessions=6, private_geometry_and_raw_receipts_excluded_from_public_commit=True,
        wall_s_before_manifest=time.perf_counter()-started))
    paths = sorted(path for path in HERE.rglob("*") if path.is_file() and path.name not in ("MANIFEST.json", "HANDOFF.json"))
    rows = []
    for path in paths:
        category = "public" if path.parent == HERE and path.name in public_names else "local_private_evidence"
        rows.append(dict(identity(path), category=category))
    write("MANIFEST.json", dict(files=rows, count=len(rows), bytes=sum(row["bytes"] for row in rows),
        exclusions=["MANIFEST.json self", "postcommit HANDOFF.json"], public_file_names=sorted(public_names | {"FINALIZATION.json", "MANIFEST.json"})))
    print("manifest", len(rows), "public", len(public_names | {"FINALIZATION.json", "MANIFEST.json"}), flush=True)


if __name__ == "__main__":
    main()
