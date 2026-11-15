"""Interpret the fixed saved transfer screen without changing any candidate."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def distribution(values):
    values = np.asarray(values, dtype=np.float64)
    return {"count": len(values), "min": float(values.min()) if len(values) else None,
            "median": float(np.median(values)) if len(values) else None,
            "p95": float(np.quantile(values, .95)) if len(values) else None,
            "max": float(values.max()) if len(values) else None}


def main():
    started, cpu = time.perf_counter(), time.process_time()
    evaluation, model, qa, verification = (read(name) for name in
        ("EVALUATION.json", "MODEL_OUTPUTS.json", "TETRAHEDRON_CHECK.json", "INDEPENDENT_VERIFY.json"))
    if verification["status"] != "passed_independent_saved_result_verification" or verification["failures"]:
        raise ValueError("independent_saved_result_verification_not_passed")
    selected = read("CASE_SELECTION.json")["cases"]
    if len(evaluation["cases"]) != 37 or model["status"] != "completed_all_frozen_cases":
        raise ValueError("fixed_screen_incomplete")
    original = {}
    for path in (HERE.parent / "m6_shape_data_001/DATASET_INDEX.json", HERE.parent / "m6_shape_train_001/PUBLIC_DATASET_INDEX.json"):
        original.update({row["id"]: row for row in json.loads(path.read_bytes())["cases"] if row["purpose"] != "reserved_test"})
    outputs = {row["id"]: row for row in model["cases"]}
    diagnostics = []
    identities = {}

    def load_array(path):
        path = Path(path)
        data = path.read_bytes()
        identities[str(path)] = {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        return np.load(path, allow_pickle=False)

    for case in evaluation["cases"]:
        result = case["methods"]["pointfilter"]
        observed = load_array(result["observed_path"])
        reference = load_array(result["reference_path"])
        with load_array(result["mapping_path"]) as package:
            context = package["context_source_ids"]
        labels_path = Path(result["observed_path"]).parents[1] / "labels" / (Path(result["observed_path"]).stem + ".npz")
        with load_array(labels_path) as package:
            support = package["damaged_mask"].astype(bool)
        final = load_array(result["candidate_path"])[context]
        target, correction = reference[support] - observed[support], final[support] - observed[support]
        dot = np.einsum("ij,ij->i", target, correction)
        target_norm, correction_norm = np.linalg.norm(target, axis=1), np.linalg.norm(correction, axis=1)
        cosine_valid = (target_norm > 0) & (correction_norm > 0)
        cosines = dot[cosine_valid] / (target_norm[cosine_valid] * correction_norm[cosine_valid])
        first = outputs[case["id"]]["methods"]["pointfilter"]["iterations"][0]
        with load_array(first["sampling_path"]) as package:
            neighbor_counts = package["neighbor_count"]
            duplicates = package["sampling_duplicate_count"]
        source_case = original[case["id"]]
        dent_radius = source_case.get("radius_native", source_case.get("radius_m"))
        radius = first["statistics"]["radius_native"]
        diagnostics.append({"id": case["id"], "source": case["source"], "normal_control": case["normal_control"],
                            "position_group": case["position_group"], "purpose": case["purpose"],
                            "model_radius_native": radius, "dent_radius_native": dent_radius,
                            "model_radius_over_dent_radius": radius / dent_radius if dent_radius else None,
                            "model_radius_over_observed_median_edge": radius / result["scale_native"],
                            "iteration1_neighbor_count": distribution(neighbor_counts),
                            "iteration1_sampling_duplicates": distribution(duplicates),
                            "support_points": len(target), "positive_target_dot_points": int(np.count_nonzero(dot > 0)),
                            "negative_target_dot_points": int(np.count_nonzero(dot < 0)),
                            "zero_target_dot_points": int(np.count_nonzero(dot == 0)),
                            "direction_cosine_valid_points": int(np.count_nonzero(cosine_valid)),
                            "direction_cosine_invalid_or_zero_points": int(np.count_nonzero(~cosine_valid)),
                            "direction_cosine": distribution(cosines),
                            "correction_RMSE_over_target_RMSE": float(np.sqrt(np.sum(correction * correction) / np.sum(target * target))) if np.any(target) else None})
    boundary = {}
    for method in ("no_op", "pointfilter", "robust_mls"):
        boundary[method] = {kind: sum(case["methods"][method]["surface"][direction]["boundary_classification"][kind]["nearest_point_on_boundary_count"]
                                    for case in evaluation["cases"] for direction in ("candidate_to_reference", "reference_to_candidate"))
                            for kind in ("cut", "natural_open", "unknown")}
    groups = {}
    for name, predicate in (("all", lambda row: True), ("development_center", lambda row: row["purpose"] == "development_train_pool"),
                            ("validation_center", lambda row: row["purpose"] == "validation" and row["position_group"] == "center"),
                            ("validation_offcenter", lambda row: row["position_group"] == "offcenter")):
        rows = [row for row in diagnostics if predicate(row)]
        groups[name] = {"cases": len(rows), "support_point_observations": sum(row["support_points"] for row in rows),
                        "positive_target_dot_point_observations": sum(row["positive_target_dot_points"] for row in rows),
                        "model_radius_over_dent_radius": distribution([row["model_radius_over_dent_radius"] for row in rows if row["model_radius_over_dent_radius"] is not None]),
                        "per_case_iteration1_median_neighbor_count": distribution([row["iteration1_neighbor_count"]["median"] for row in rows]),
                        "per_case_iteration1_median_sample_duplicates": distribution([row["iteration1_sampling_duplicates"]["median"] for row in rows]),
                        "per_case_direction_cosine_median": distribution([row["direction_cosine"]["median"] for row in rows if row["direction_cosine"]["median"] is not None]),
                        "per_case_correction_RMSE_over_target_RMSE": distribution([row["correction_RMSE_over_target_RMSE"] for row in rows if row["correction_RMSE_over_target_RMSE"] is not None])}
    write("TRANSFER_DIAGNOSTIC.json", {"cycle_id": "M6-SHAPE-PRETRAIN-001", "cases": diagnostics,
          "groups": groups, "surface_boundary_hits_over_both_directions": boundary,
          "formula": "support dot=(final-observed) dot (reference-observed); cosine only positive nonzero norms; correction/target energy ratio square root",
          "interpretation": "post-result descriptive use of saved outputs and authorized labels, no parameter selection or causal failure proof; repeated support point observations are dependent",
          "input_file_identities": list(identities.values()), "new_forwards_or_unique_surface_queries": 0,
          "wall_s_before_write": time.perf_counter() - started, "CPU_s_before_write": time.process_time() - cpu})
    recommendation = {
        "count": 1, "action": "propose_one_Pointfilter_local_dent_domain_finetune_for_review",
        "status": "proposal_only_training_not_run", "initialization": "same fixed official checkpoint and architecture",
        "inference_input": "current complete source, current official-radius neighborhood/PCA/500 points and task F query IDs; no support labels or clean reference",
        "supervision": "existing authorized clean/corrupt pairs, local PCA/radius-normalized target displacement; normal samples and originally normal F points have zero displacement targets",
        "source_split": "existing development group231 observations for training, Armadillo117 observations for fixed transfer validation; Armadillo pretraining shape overlap and unknown upstream character independence remain disclosed",
        "training_focus": "case-balanced dent displacement and normal-preservation losses, retain zero correction on protected vertices; freeze numerical loss/step budget before the proposed run",
        "acceptance": "same original support/no-op and MLS gains, N/NF and normal controls, fixed domains and full incident gates; contact/artistic acceptance remain separate unknowns",
        "new_evidence": "official noise-domain workflow improves pointset distance; direct dent transfer fails normal preservation and no-op baseline, showing a measured target-distribution gap",
        "approval": "planner independent review decides the next contract"}
    summary = {"cycle_id": "M6-SHAPE-PRETRAIN-001", "status": "completed_fixed_pretrained_screen",
               "direct_pretrained_candidate": "rejected_shape_quality_failed", "model_selected_for_product": False,
               "case_count": 37, "actual_denominators": evaluation["actual_denominators"],
               "failed_or_unrun_case_methods": model["failures"], "all_frozen_cases_evaluated": True,
               "pointfilter_quality": evaluation["summaries"]["all"]["pointfilter"],
               "official_noise_workflow": qa["pair_evaluation"], "transfer_diagnostic_groups": groups,
               "boundary_hits": boundary, "unique_next_recommendation": recommendation,
               "training": 0, "Bunny_arrays_or_scores": 0, "old_network_retuning": 0,
               "independent_verification": {"status": verification["status"], "checks": verification["check_count"], "coverage": verification["coverage"]},
               "scope": "bounded selected-case transfer screen, Armadillo pretrained-shape overlap, coupling and artistic acceptance unknown37/37 per method",
               "summary_wall_s_before_write": time.perf_counter() - started,
               "summary_CPU_s_before_write": time.process_time() - cpu,
               "bootstrap_wall_s_before_write": time.perf_counter() - BOOT_WALL,
               "bootstrap_CPU_s_before_write": time.process_time() - BOOT_CPU}
    write("SUMMARY.json", summary)
    link = lambda name: "[" + name + "](" + (HERE / name).as_posix() + ")"
    text = ["# M6-SHAPE-PRETRAIN-001 预训练迁移筛选", "",
            "2026-11-15。基线`e2d163159bd9c3110395304b16ac9cd43a0da905`，合同`27e6d5a22569dddf57b032fccc57f09009965cb8`，最终PLAN冻结`da7e2d7ebb784ef67c1cacd4b2d0e6f633b7d5a1`。", "",
            "**Pointfilter官方预训练直接迁移未通过局部凹陷质量筛选。唯一后续建议是提交一次同架构凹陷领域微调方案供规划者复核。当前模型产品验收状态为未通过。**", "",
            "## 固定来源与执行", "",
            "固定官方提交`6e0ec1eac59ca9f81ee9ca6751c5b3f25effeda2`，权重SHA256 `86600e6d57fab7887fbda0cf54292578a52d956c36766a130d1e32a475d18cee`，参数1,360,899。六份官方源码/MIT、权重和两份Tetrahedron数组均核对官方Git blob后使用。Torch2.15.0+cpu/NumPy2.3.5复用旧只读安装，SciPy1.15.3/sklearn1.7.2等装入本批private/deps。" + link("SOURCE_INDEX.json") + " " + link("ENVIRONMENT.json"), "",
            "推理包严格只有完整当前源vertices、原任务F源ID与context源ID三个字段。每步完整当前源bbox对角×0.05半径，官方PCA和500采样，batch64单线程，两次同步只更新F，以第2步为结果。每例每方法重置seed1729，第二步沿用该例RNG，37例首步采样全部一致。网络及逆旋转float32，局部增量加回float64中心。该任务更新F及省略全云float32保存的适配已在官方流程对照中核查。" + link("INPUT_INDEX.json") + " " + link("MODEL_OUTPUTS.json"), "",
            "7正常、12角色中心凹陷、9Armadillo中心、9偏心共37例全部完成，两新方法74例方法均完成，无遗漏或执行失败。四角色同未知上游组，旧压力选例依据保留。论文训练图可辨认Armadillo/Bunny形状，具体采样重合未知，Armadillo按迁移压力组解释。Bunny数组及评分次数0。", "",
            "## 官方流程检查", "",
            f"1555项官方预处理/采样/PCA/逆变换及前向等价性检查通过，预处理最大差0。两官方输入各128固定查询单次过滤，另复算4个已有查询。噪声128点到完整干净点集RMSE比值{qa['pair_evaluation']['noisy_pointset_RMSE_ratio']:.6f}，干净输入位移RMSE为bbox对角的{qa['pair_evaluation']['clean_input_requested_point_movement']['RMSE']:.8f}。逐点对应关系未证实，采用有限查询到点集的距离。" + link("TETRAHEDRON_CHECK.json"), "",
            "## 凹陷修复与正常保持", "",
            "表中S比值为支持区RMSE/同例no-op，正常控制的S为空。A改善为1−候选A/no-op A。各数值为逐例中位，全部原分母、p95/max、幅度与source/patch分层在完整评价中。", "",
            "| 子集 | 凹陷数 | PF S比值 | 同邻域MLS S比值 | PF A改善 |", "| --- | --- | --- | --- | --- |"]
    for group in ("development_center", "validation_center", "validation_offcenter", "all"):
        a = evaluation["summaries"][group]
        pf, mls = a["pointfilter"], a["robust_mls"]
        text.append(f"| {group} | {pf['dented_evaluated']} | {pf['support_RMSE_ratio_to_noop']['median']:.6f} | {mls['support_RMSE_ratio_to_noop']['median']:.6f} | {100*pf['allowed_improvement_to_noop']['median']:.2f}% |")
    all_pf = summary["pointfilter_quality"]
    text += ["", f"PF全部30凹陷S比值p95/max为{all_pf['support_RMSE_ratio_to_noop']['p95']:.6f}/{all_pf['support_RMSE_ratio_to_noop']['max']:.6f}。对同输入MLS支持改善中位{100*all_pf['support_improvement_to_same_input_MLS']['median']:.2f}%。验证source Armadillo中位1.336359，目标上限0.85。支持中位≤0.70、p95≤1.05、max≤1.25及A改善≥20%均失败。", "",
             f"7正常对照全部失败，A RMSE归一中位{all_pf['normal_control_RMSE_over_scale']['median']:.6f}，规定每例≤0.01。37例N/N_F保护全部失败，N_F逐例p95中位{all_pf['normal_free_p95_over_scale']['median']:.6f}，规定每例≤0.02。{len(all_pf['face_quality_failed_case_ids'])}/37例发生面质量失败，逐例翻面计数之和{all_pf['normal_reversals_sum_over_cases']}，新增退化0。固定、边界和全源域外均逐位保持，全A incident覆盖完整。MLS翻面逐例和1502。该计数重复观察中的同源面，独立资产数另列。" + link("EVALUATION.json"), "",
             "旧门控MLS/TRAIN/OPT的37例保存历史均在逐例评价中引用，原失败保留。source-file门槛按验证source应用，开发source与patch分布另列；相对MLS收益门槛用于Pointfilter候选，MLS自身标不适用。", "",
             "## 表面量、输入尺度与修正方向", "",
             "双向有限A顶点到保存context闭三角面覆盖37×3方法、222方向、85248查询。每方向RMSE/p95/max、最近点及边界归因均保存，连续全表面与全源表面最大偏差仍未知。", "",
             "| 方法 | 双向RMSE逐例中位 | 切割边命中点观察 | 自然开边命中点观察 | unknown边命中 |", "| --- | --- | --- | --- | --- |"]
    for method in ("no_op", "pointfilter", "robust_mls"):
        hits = boundary[method]
        text.append(f"| {method} | {evaluation['summaries']['all'][method]['surface_symmetric_RMSE']['median']:.6f} | {hits['cut']} | {hits['natural_open']} | {hits['unknown']} |")
    text += ["", "边界点数按两方向和37观察求和，裁剪归因和原坐标/保护/incident条件同时保留。接触、耦合、完整交点及艺术认可均为每方法37/37 unknown。", ""]
    text += ["邻域与采样重复统计包含正常对照，各组为16、12、9例。模型/凹陷半径比只含有凹陷半径者，方向统计只含非空S，各项分母在JSON单列。", ""]
    for group in ("development_center", "validation_center", "validation_offcenter"):
        row = groups[group]
        text.append(f"{group}的模型半径/凹陷半径逐例中位{row['model_radius_over_dent_radius']['median']:.3f}，首步每例邻域数中位的中位{row['per_case_iteration1_median_neighbor_count']['median']:.1f}，500采样重复数相应中位{row['per_case_iteration1_median_sample_duplicates']['median']:.1f}。S修正与目标位移点积为正的点观察{row['positive_target_dot_point_observations']}/{row['support_point_observations']}，每例修正RMS/目标RMS中位{row['per_case_correction_RMSE_over_target_RMSE']['median']:.3f}。")
    text += ["", "这些是保存输出的标签辅助解释统计。官方先验面向噪声点集过滤，当前输入为不均匀网格顶点与成片凹陷；半径尺度、稀疏邻域重复采样、修正幅度和正常区域移动均已实测。上述关系对训练分布差距提供证据，失败根因及可训练性仍无因果结论。" + link("TRANSFER_DIAGNOSTIC.json"), "",
             "## 唯一后续建议", "",
             "提议同一Pointfilter架构和官方初始化进行一次合成凹陷领域微调。输入保留当前源邻域/PCA/500点与F，监督为配对参考给出的PCA局部位移，训练包含零目标正常样本和正常F点。建议沿现有231开发观察/117 Armadillo迁移验证划分，在下一合同计算前冻结例均衡凹陷位移与正常保持损失、权重和步数预算。原no-op/MLS收益、正常保持、固定域和全部incident质量共同验收。规划者独立复核后决定是否执行。" + link("SUMMARY.json"), "",
             "## 复核、恢复与成本", "",
             f"独立保存结果核验{verification['check_count']}项通过，覆盖和最大数值差在核验记录中。新训练0，旧网络重调0，其他模型0，Bunny数组/评分0，Blender/产品/原资产编辑0，Google及付费API调用0。" + link("INDEPENDENT_VERIFY.json"), "",
             "初版PLAN后发现跨案例共享RNG会使第二步耗用影响后续首步样本，在任何新数组读取/前向前澄清为每例重置相同seed1729并重新冻结，初冻提交fcb0d4b5留存。准备中一次猜测旧文件路径和Windows rg glob失败已恢复，未执行模型。pip按私有target安装成功，随后补上子进程-B复跑保护，旧site自任务登记以来pyc写入扫描为0，原执行源码已归档。" + link("PREPARATION_INTEGRITY.json"), "",
             "成本包含获取/依赖、导入加载、全源构建、索引/PCA/采样、前向/恢复、MLS和评价，各阶段内外包含关系见COSTS。当前为单线程CPU质量筛选，独占窗口未确认；完整产品管线、同质量20%提速及货币成本仍未测。" + link("COSTS.json")]
    (HERE / "REPORT.md").write_text("\n".join(text) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"decision": summary["direct_pretrained_candidate"], "next_recommendation_count": 1}))


if __name__ == "__main__":
    main()
