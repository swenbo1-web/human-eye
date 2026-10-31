"""Create the human-readable report from completed, revealed experiment records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    data = json.loads((run / "results_revealed.json").read_text(encoding="utf-8"))
    scores = json.loads((run / "blind_scores.json").read_text(encoding="utf-8"))
    locks = json.loads((run / "private/response_locks.json").read_text(encoding="utf-8"))
    n_trials = int(data.get("trials", 60))
    n_scenes = int(data.get("scenes", n_trials // 2))
    experiment_mode = data.get("experiment_mode", "full_product")
    if not args.allow_incomplete:
        assert scores["complete"] and len(scores["results"]) == len(locks) == n_trials
    else:
        assert len(scores["results"]) == len(locks) >= n_trials
    for row in scores["results"]:
        digest = hashlib.sha256((run / "responses" / (row["trial_id"] + ".json")).read_bytes()).hexdigest()
        assert digest == row["response_sha256"] == locks[row["trial_id"]]["sha256"]
    keys = data["reveal_key"]
    control, plugin = (data["groups"][keys[k]] for k in ("control", "plugin"))
    categories = {"floating": "悬空间隙", "tilted": "倾斜偏航", "near_contact": "近距离贴合",
                  "occluded": "遮挡", "penetrating": "初始穿模", "inclined": "斜面"}
    def number(value):
        return "无数据" if value is None else f"{value:.4f}"
    col_control = "单视角基线视图" if experiment_mode == "vision_only" else "未接入"
    col_plugin = "Human-Eye 四宫格视觉画布" if experiment_mode == "vision_only" else "接入完整系统"
    title = (
        f"# 人类之眼：{n_scenes} 场景纯 3D 视觉引擎唯一变量双盲配对试验"
        if experiment_mode == "vision_only"
        else f"# 人类之眼：{n_scenes} 场景盲化配对试验"
    )
    intro = (
        f"本轮已收齐 {n_trials} 份真实子代理动作答案。每个场景的两组 packet.json 文字与标定参数逐字节一致（剔除解析动作建议与额外文本遥测），"
        "唯一自变量为 768×768 视觉图像（普通单透视图 vs Human-Eye 四宫格中央凹+主动消遮挡画布），统一按模型原始动作（raw.success）独立几何评分。"
        if experiment_mode == "vision_only"
        else f"本轮已收齐 {n_trials} 份真实子代理动作答案。每个场景分别提供普通视图和人类之眼完整辅助，统一使用预先固定的独立几何评分。"
    )
    lines = [title, "", intro,
             "", "## 主要结果", "",
             f"| 指标 | {col_control} | {col_plugin} |", "|---|---:|---:|",
             f"| 单步成功 | {control['successes']}/{n_scenes}（{control['success_rate_pct']:.2f}%） | {plugin['successes']}/{n_scenes}（{plugin['success_rate_pct']:.2f}%） |",
             f"| 无效答案 | {control['invalid_answers']} | {plugin['invalid_answers']} |",
             f"| 终态穿模 | {control['terminal_collisions']} | {plugin['terminal_collisions']} |",
             f"| 底面距目标平面 RMS 中位数，毫米 | {number(control['median_bottom_face_rms_mm'])} | {number(plugin['median_bottom_face_rms_mm'])} |",
             f"| 姿态误差中位数，度 | {number(control['median_rotation_error_deg'])} | {number(plugin['median_rotation_error_deg'])} |",
             f"| 面内位置漂移中位数，毫米 | {number(control['median_tangential_drift_mm'])} | {number(plugin['median_tangential_drift_mm'])} |",
             "", f"成功率差：**{plugin['success_rate_pct'] - control['success_rate_pct']:+.2f} 个百分点**。", "",
             f"| 场景 | {col_control}成功 | {col_plugin}成功 |", "|---|---:|---:|"]
    for category, label in categories.items():
        if category in control["by_category"]:
            a, b = (g["by_category"][category] for g in (control, plugin))
            lines.append(f"| {label} | {a['successes']}/{a['trials']} | {b['successes']}/{b['trials']} |")
    pair = data["paired"]
    if experiment_mode == "vision_only":
        attr_lines = [
            f"{col_control}组直接执行模型原始动作，成功 {control['raw_successes']}/{n_scenes}。"
            f"{col_plugin}组在无任何解析动作建议泄露、仅依靠 768×768 四宫格中央凹+主动消遮挡画布下作答，直接执行模型原始答案成功 {plugin['raw_successes']}/{n_scenes}。",
            f"若作为次要参考叠加 3.2/3.3 控制器后处理，两组辅助后通过数分别为 {control['assisted_successes']}/{n_scenes} 与 {plugin['assisted_successes']}/{n_scenes}（主终点严格固定为模型原始动作 raw.success）。",
        ]
        method_scope_line = "- 单视角基线组使用原生 768×768 单透视图；视觉引擎组使用 768×768 四宫格中央凹+主动消遮挡画布。两组 packet.json 文字描述与标定参数逐字节恒等，不含任何解析动作建议或额外文本遥测。"
    else:
        attr_lines = [
            f"未接入组直接执行模型原始动作，成功 {control['raw_successes']}/{n_scenes}。接入组在四宫格和插件遥测、解析动作建议下作答，直接执行这些原始答案成功 {plugin['raw_successes']}/{n_scenes}；再经过插件融合、护栏和执行后成功 {plugin['assisted_successes']}/{n_scenes}。",
            f"接入组的执行结果有 {plugin['changed_actions']}/{n_scenes} 次与原始动作不同。这是整套产品辅助的结果，包含解析动作建议与自动纠偏，不能单独归因于模型视觉能力提高。",
        ]
        method_scope_line = "- 未接入组使用原生 768×768 单透视图；接入组使用 768×768 四宫格及正式插件观测，保留产品的动作建议和自动相机行为。双方获得一致的任务、目标平面、坐标规则和零件尺寸。"
    lines += ["", f"配对结果：两组都成功 {pair.get('both', 0)} 个；仅{col_plugin}成功 {pair.get('only_' + keys['plugin'], 0)} 个；仅{col_control}成功 {pair.get('only_' + keys['control'], 0)} 个；两组都失败 {pair.get('neither', 0)} 个。",
              "", "## 收益来自哪里", "", *attr_lines,
              "", "## 方法与固定标准", "",
              f"- 固定随机种子，六类场景共 {n_scenes} 个新场景；每个场景的两组共享相同初始几何和隐藏目标。",
              method_scope_line,
              "- 每题只允许一次旋转和平移动作，禁止运行几何求解器、读取隐藏真值、查看评分或按执行反馈修改答案。所有提交保存为独立 JSON 文件。",
              "- 成功须同时满足：指定局部底面对目标平面 RMS ≤0.5 毫米、姿态误差 ≤1°、面内中心漂移 ≤5 毫米、底面在指定区域内、终态无超过 0.1 毫米容差的实体穿模。长方体允许平面内 180° 等价姿态。",
              "- 独立评分不使用产品自身的通过标志，直接从最终位姿和隐藏目标计算接触误差及有向包围盒穿模。无效答案计失败；不会用标准答案替换模型答案。",
              "- 评分器不读取分组映射，对每份答案均计算原始执行及插件执行两种终态。全部答案锁定后才汇总 X/Y 组并揭晓标签。",
              "", "## 解释范围与限制", "",
              "- 受试端题包采用随机哈希 ID 且隐去分组标签；评分端在揭盲前不读取分组映射，汇总为匿名 Group X / Group Y。",
              "- 所有受试代理继承同一父级模型设置，未主动修改模型或推理强度；文件访问限制由指令约束。",
              "- 本轮考察终态贴合，不验证运动路径安全、真实物理接触、闭环多步泛化或其他模型。初始穿模题允许零件从穿模状态恢复。",
              "- 子代理工具未暴露真实 Token 用量，不能据此报告费用或 Token 节省。",
              f"- 协议冻结至最后答案保存的总墙钟时间为 {data['wall_time_from_protocol_freeze_to_last_response_s']:.1f} 秒，包含调度、图像读取和等待，不能作为纯推理速度对比。",
              "", "## 审计文件", "",
              "- protocol.json：实验协议、唯一变量声明、成功阈值和冻结的业务及评分源文件哈希。",
              "- private/generation_manifest.json：输入和隐藏真值的冻结哈希。",
              f"- public/：{n_trials} 份匿名输入和图像；responses/：{n_trials} 份原始答案；private/response_locks.json：提交内容哈希。",
              f"- blind_scores.json：{n_trials} 份答案原始及辅助执行的完整独立评分、实际动作和终态。",
              "- cohort_summary_blind.json：揭晓前 X/Y 汇总；results_revealed.json 与 results.csv：揭晓结果。",
              "", f"协议 SHA-256：`{data['protocol_sha256']}`", ""]
    failure_path = run / "failure_analysis.json"
    if failure_path.exists():
        failures = json.loads(failure_path.read_text(encoding="utf-8"))
        section = ["## 失败样例与执行退化", "",
                   "以下为揭盲后的描述性诊断，不修改本轮规则或成绩。",
                   "", "| 场景 | 类型 | 原始成功 | 最终底面 RMS，毫米 | 最终姿态误差，度 | 产品自报通过 |",
                   "|---|---|---:|---:|---:|---:|"]
        for row in failures["plugin_failures"]:
            section.append(f"| {row['scene']} | {categories[row['category']]} | {'是' if row['raw_success'] else '否'} | {row['final_bottom_rms_mm']:.4f} | {row['final_rotation_error_deg']:.4f} | {'是' if row['product_pass'] else '否'} |")
        section += [""]
        insertion = lines.index("## 方法与固定标准")
        lines[insertion:insertion] = section
    diagnostics = run / "diagnostic_notes.md"
    if diagnostics.exists():
        lines += ["## 源码诊断记录", "", diagnostics.read_text(encoding="utf-8"), ""]
    (run / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"report": str(run / "report.md"), "control": control["successes"], "plugin": plugin["successes"]}))


if __name__ == "__main__":
    main()
