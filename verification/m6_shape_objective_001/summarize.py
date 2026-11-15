"""Summarize objective differences while retaining every original failure."""

import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def main():
    started, cpu = time.perf_counter(), time.process_time()
    decomposition = read("DECOMPOSITION.json")
    surface = read("SURFACE_RESULTS.json")
    qa = read("METER_QA.json")
    verification = read("INDEPENDENT_VERIFY.json")
    repair = read("SURFACE_METADATA_REPAIR.json")
    if not qa["status"].startswith("passed") or verification["status"] != "passed_independent_saved_result_verification":
        raise ValueError("objective_tools_require_successful_verification")
    methods = ("no_op", "mls", "train_final", "opt_final_hard")
    comparisons = []
    ranking_changes = []
    for row in surface["cases"]:
        entry = {"case_id": row["case_id"], "normal_control": row["normal_control"], "methods": {}}
        for method in methods:
            value = row["methods"][method]
            legacy = value["legacy"]
            entry["methods"][method] = {
                "coordinate_A_RMSE": legacy["errors"]["A"]["rmse_over_scale"],
                "surface_symmetric_RMSE": value["symmetric_RMSE"],
                "surface_forward_RMSE": value["candidate_to_reference"]["distance"]["RMSE"],
                "surface_reverse_RMSE": value["reference_to_candidate"]["distance"]["RMSE"],
                "original_normal_protection_passed": legacy["original_normal_point_preservation_passed"],
                "original_normal_control_passed": legacy["original_normal_control_passed"],
                "original_normal_reversals": legacy["incident_quality"]["normal_reversals_from_input"],
                "original_new_degenerate_faces": legacy["incident_quality"]["new_degenerate_faces"],
            }
        entry["coordinate_order"] = row["coordinate_A_RMSE_order"]
        entry["surface_order"] = row["surface_symmetric_RMSE_order"]
        coordinate_best = min(value["coordinate_A_RMSE"] for value in entry["methods"].values())
        surface_best = min(value["surface_symmetric_RMSE"] for value in entry["methods"].values())
        entry["coordinate_best_method_set"] = [name for name in methods if entry["methods"][name]["coordinate_A_RMSE"] == coordinate_best]
        entry["surface_best_method_set"] = [name for name in methods if entry["methods"][name]["surface_symmetric_RMSE"] == surface_best]
        if entry["coordinate_order"] != entry["surface_order"]:
            ranking_changes.append(row["case_id"])
        comparisons.append(entry)
    cut_hits = sum(value[direction]["boundary_classification"]["cut"]["nearest_point_on_boundary_count"]
                   for row in surface["cases"] for value in row["methods"].values()
                   for direction in ("candidate_to_reference", "reference_to_candidate"))
    controls = [row for row in comparisons if row["normal_control"]]
    protection_failures = {method: sum(not row["methods"][method]["original_normal_protection_passed"]
                                       for row in controls) for method in methods}
    assert len(comparisons) == 6 and len(ranking_changes) == 1
    assert ranking_changes[0] == "Yunhex_patch_05/sample_00"
    assert protection_failures["train_final"] == protection_failures["opt_final_hard"] == 4
    result = {
        "cycle_id": "M6-SHAPE-OBJECTIVE-001", "status": "completed_objective_diagnostic",
        "coordinate_and_surface_quantities_numerically_equivalent": False,
        "rank_change_case_ids": ranking_changes, "unchanged_order_cases": 5,
        "best_method_set_changed_case_ids": [row["case_id"] for row in comparisons
                                             if row["coordinate_best_method_set"] != row["surface_best_method_set"]],
        "old_candidate_engineering_acceptance_changed": False,
        "decision": "close_surface_objective_alone_resolves_current_failure_explanation",
        "decision_scope": "the six saved cases offer no sufficient change to the failed candidates' engineering disposition; outcomes of unrun future losses remain unknown",
        "new_future_training_objective_proposal": None,
        "original_candidate": "closed_quality_failed",
        "coordinate_vs_surface": comparisons,
        "decomposition_primary": {name: decomposition["summaries"][name] for name in
                                  ("development_center", "validation_center", "validation_offcenter")},
        "cut_boundary_hits_all_48_directions": cut_hits,
        "normal_controls": len(controls), "normal_protection_failed_controls": protection_failures,
        "supervision_clarification": "synthetic clean/corrupt pairs remain authorized training/evaluation targets; human-approved real edits concern artistic product validation",
        "future_surface_loss_performance": "unmeasured, no causal impossibility conclusion",
        "zero_operations": {"model_forwards": 0, "training": 0, "new_repair_candidates": 0,
                            "threshold_searches": 0, "Bunny_arrays": 0, "Blender_product": 0},
        "summary_wall_s_before_write": time.perf_counter() - started,
        "summary_CPU_s_before_write": time.process_time() - cpu,
    }
    (HERE / "SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    decomposition_rows = []
    for name, value in result["decomposition_primary"].items():
        decomposition_rows.append(
            f"| {name} | {value['case_count']} | {value['denominators']['support_points']} | "
            f"{value['normal_energy']:.6f} | {value['tangent_energy']:.6f} | "
            f"{100*value['tangent_fraction_of_decomposable_target']:.4f}% | "
            f"{100*value['per_case_tangent_fraction']['median']:.4f}% |")
    comparison_rows = []
    for row in comparisons:
        comparison_rows.append("| " + row["case_id"] + " | " + " | ".join(
            f"{row['methods'][method]['coordinate_A_RMSE']:.6f} / {row['methods'][method]['surface_symmetric_RMSE']:.6f}"
            for method in methods) + " |")
    prefix = HERE.as_posix()
    report = f"""# M6-SHAPE-OBJECTIVE-001 目标量核查

2026-11-15。基线 `29e81ed1d1b2fde2464cdbf856f96086f9ae4b46`，合同 `75fa50b9d66aa91a5ba336438b4895354ec97500`，PLAN冻结 `38d772333cc8daf2fcf61585a4af1d65ba19d974`。所有新增文件位于本批目录。

**坐标量与表面量存在数值差异及一处失败方法间的排序互换，六个旧见证的工程去留保持原判。** 本批关闭“仅改成表面目标即可解决当前失败”的解释，当前证据对新目标训练没有形成充分推进依据。原失败候选继续关闭。

## 上批范围澄清

运行时给定认可的同索引参考，可以使用既有直接坐标恢复。只在训练/评价中提供未扰动参考，仍构成用户已授权的合成监督研究答案。真人认可修正记录对应真实艺术验收。TASK001中广义“无参考训练路线关闭”按这一范围修正，当前失败候选及无新依据训练的停止点继续适用。[本批澄清]({prefix}/TASK001_CLARIFICATION.md)

PointCleanNet第5节讨论了对应点坐标目标与表面接近、采样规则性的关系，提供本次检查的动机。本批用旧网格输出实测，论文结果与模型成绩的转移没有建立。[PointCleanNet 第5节](https://arxiv.org/html/1901.01060v3#S5)

## 306个凹陷标签的法向与切向分解

真实目标d采用binary64参考减观察，再除本例观察尺度。同patch sample00保存的法向提升float64并单位化，计算d_n=(d·n)n及d_t=d-d_n。使用参考法向属于标签辅助诊断，推理输入与旧候选均保持原样。

| 子集 | 凹陷观察 | 支持点 | 法向能量 | 切向能量 | 汇总能量切向占比 | 逐例占比中位 |
| --- | --- | --- | --- | --- | --- | --- |
{chr(10).join(decomposition_rows)}

10767个支持点的法向和目标均有效，零/非有限法向及非有限目标计数0，完整分母和无效处理保留。逐点能量闭合最大绝对差约1.78e-15。来源、幅度、半径/幅度分层与306例数值均保存。面积加权顶点法向在折痕处的物理方向可能有歧义，切向比例对可学习性和旧失败原因的解释尚无因果证据。[分解明细]({prefix}/DECOMPOSITION.json)

两验证高能量见证的切向占比为38.5537%和38.1369%，高于各验证池汇总值。六见证属于预选机制检查，整体成功率没有在本批重新评价。

## 六见证与四份旧输出

采用原OBSERVE001六例，读取既有no-op、MLS、TRAIN001末步和OPT001最终硬输出。每个方向用384个允许顶点，目标表面固定为同一保存context的全部闭三角面，两个方向合计18432个查询。float64使用共同观察origin及scale，query/triangle块为32/256。

表中每格为原A坐标RMSE / 双向表面RMSE，均除同一观察中位边长。表面MSE为两方向均方距离的平均，再开方得到表面RMSE。两方向的RMSE、p95、max与最近点明细另存。

| 观察 | no-op | MLS | TRAIN末步 | OPT硬输出 |
| --- | --- | --- | --- | --- |
{chr(10).join(comparison_rows)}

五例排序一致。Yunhex正常对照的坐标量偏向OPT（0.024537对MLS的0.049420），表面量偏向MLS（0.022226对OPT的0.022598）。表面差约0.00037224，高于计量舍入量。这一对照真实目标位移为0，目标标签的切向能量无法单独解释该排序变化。

六例的最优方法集合在两套量下完全相同。四正常对照均以保持原形状的no-op为最优，两个凹陷均以TRAIN末步为距离最小。唯一排序互换发生于正常对照的两个非最优方法。本轮未出现两目标要求选择不同最优输出的见证，因此尚无据此重定义未来任务目标的充分工程证据。该结论限这六例，旧保护失败另行保留。

两个Armadillo凹陷的TRAIN相对no-op坐标A改善约3.95%/5.20%，表面改善约4.64%/6.89%，方向一致。中心两方向TRAIN RMSE为0.296577/0.383691，no-op为0.313514/0.400435。偏心TRAIN为0.139041/0.178978，no-op为0.150907/0.190977。方向不对称已保留，单方向数值没有被用作候选验收。[完整距离与原判定]({prefix}/SURFACE_RESULTS.json)

## 边界、原保护与计量范围

48个方向的context切割边界最近点命中均0。Chipow有自然开边命中25点/方向，Yunhex为4点/方向，相关距离子集另列；它们根据原完整源拓扑与context边计数区分。完整源拓扑只用于边分类，距离面域始终为保存context。所有方向的非有限点、空面域和退化三角计数已补齐并保留。

四个正常见证中TRAIN和OPT的原正常点保护各4/4失败。Yunhex的MLS原正常保护失败且4面翻转。两验证凹陷的TRAIN原正常点保护均失败，偏心另有1面翻转，OPT两例保持旧no-op输出。固定/边界/域外保持、原A/S/N/N_F及全部incident面的记录原样并列。新的表面数值没有产生接受旧失败候选的依据。

本量只覆盖有限允许顶点到有限context三角面集合，连续表面最大偏差与完整源域仍未证明。最近点按面内部、闭边和顶点计算，退化面保留为线段/点并计数。计量器34项闭式及重排/共同刚体不变性QA通过，表面距离采用三角面最近点。边界长度舍入容差仅用于归因，旧误差/保护/面质量门槛维持。[计量QA]({prefix}/METER_QA.json) [独立核验]({prefix}/INDEPENDENT_VERIFY.json)

## 实际运行、修复与成本

法向分解worker外层wall5.9821秒，计量QA0.1746秒，首轮表面距离4.8350秒，元数据修复0.2353秒。读取、能量分解、距离、边界归因、保存及独立核验阶段均在成本账本分别记录，阶段内部时间属于外层包含范围。交互、部分预检查CPU/峰值及最终自查询后的写盘/退出仍有缺测。[成本]({prefix}/COSTS.json)

初版caller误将计量计数读作嵌套counts字段，48方向的公开诊断分母为空。实际距离计算先完成，之后修正caller。恢复保存了原报告与SHA精确匹配的原执行源码，只由已有查询/候选数组补计数，原48份距离详情、距离统计、排序和旧判定的payload SHA保持一致，最近点重算0。另有一次历史路径查找错误已记录恢复，最终PLAN冻结前一次snapshot schema检查读取3个旧数组，时序与缺测成本均公开。[元数据恢复]({prefix}/SURFACE_METADATA_REPAIR.json)

汇总入口首试将成功核验状态误匹配为统一passed字样，已按实际passed_independent_saved_result_verification修正。原失败源码与进程成本保留，汇总恢复不重跑分解或距离。[汇总恢复]({prefix}/SUMMARY_RECOVERY.json)

另一次默认Python静态预检退出1，已用既有CPU venv语法检查恢复，预检查未执行科学数据操作，其已知耗时与缺测计入COSTS。

新模型前向、训练、新修复候选、门限搜索、Bunny数组/评分、Blender/产品和付费API调用均0。公共源物理单位未知，报告只用观察尺度。当前结果记录两目标不等价，也记录候选工程判断未改变；未来使用不同损失的训练效果仍未测。该解释在本批收口，下一研究或训练由规划者独立决定。
"""
    (HERE / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    print(json.dumps({"decision": result["decision"], "rank_change_cases": ranking_changes,
                      "old_acceptance_changed": False, "cut_boundary_hits": cut_hits}))


if __name__ == "__main__":
    main()
