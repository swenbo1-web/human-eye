"""Summarize the fixed perception candidate and the offline region contract."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf8", newline="\n")


def main():
    started, cpu = time.perf_counter(), time.process_time()
    features, training, identity, calibration, evaluation, regions, region_verify, verification, costs = (read(name) for name in
        ("FEATURES.json", "TRAIN_LOG.json", "MODEL_IDENTITY.json", "CALIBRATION.json", "EVALUATION.json",
         "REGION_REPORTS.json", "REGION_VERIFY.json", "INDEPENDENT_VERIFY.json", "COSTS.json"))
    if verification["status"] != "passed_internal_perception_verification" or verification["failures"]:
        raise ValueError("internal_model_verification_not_passed")
    if region_verify["status"] != "passed_region_reference_contract_verification" or region_verify["failures"]:
        raise ValueError("region_reference_verification_not_passed")
    if evaluation["decision_gates"]["A_attention"]["passed"] or evaluation["decision_gates"]["B_abnormality"]["passed"]:
        raise ValueError("closure_summary_requires_review_of_successful_quality_gate")
    invalid = sum(row["unavailable_points"] for row in features["cases"])
    recommendation = {"count": 1, "action": "define_source_independent_perception_data_and_holdout_contract",
        "status": "proposal_only_no_new_acquisition_or_training_in_this_batch",
        "scope": "new-source normal geometry and authorized synthetic anomaly pairs with region labels, include legitimate natural concavity negatives and freeze source-group holdout",
        "basis": "development AUC/AP and budget recall are high while both existing transfer positions fail and underperform saved old_p, no single demonstrated capacity/loss/normalization fix",
        "supervision": "synthetic clean/corrupt pair supervision remains valid, human artistic before/after is a separate future acceptance question",
        "candidate_disposition": "current frozen-encoder/head weights fail both perception uses, full-scene and LLM-task benefits unmeasured",
        "approval": "planner independent review decides the next contract"}
    summary = {"cycle_id": "M6-PERCEPTION-001", "status": "completed_fixed_perception_v1",
        "candidate": "rejected_for_A_attention_and_B_abnormality", "quality_A_passed": False, "quality_B_passed": False,
        "offline_region_contract_passed": True, "product_model_selected": False,
        "case_count": 348, "patches": 42, "F_point_observations": 109443,
        "development_cases": 231, "validation_cases": 117, "unavailable_feature_points": invalid,
        "unavailable_feature_points_by_group": {purpose: sum(row["unavailable_points"] for row in features["cases"] if row["purpose"] == purpose)
                                                  for purpose in ("development_train_pool", "validation")},
        "model_identity": identity, "training_steps": training["completed_steps"], "training_runs": training["training_runs"],
        "case_equal_pi": training["case_equal_pi"], "positive_weight": training["positive_weight"],
        "calibration_threshold": calibration["threshold"], "calibration_binding": evaluation["calibration_binding"],
        "decision_gates": evaluation["decision_gates"],
        "principal_groups": {name: evaluation["groups"][name] for name in ("development_center", "validation_center", "validation_offcenter", "validation_normal_controls")},
        "region_contract": {"cases": regions["case_count"], "references": regions["reference_count"],
                            "coverage": region_verify["coverage"], "fixed_manual_cases": regions["audit_case_ids"],
                            "LLM_consumer_evaluations": 0, "product_integration": 0},
        "internal_verification": {"coverage": verification["coverage"], "element_comparisons_and_checks": verification["check_count"],
                                  "largest_absolute_difference": verification["largest_compared_absolute_difference"]},
        "unique_next_recommendation": recommendation,
        "scope": "specified F synthetic-dent localization only, dependent character sources and previously used pretrained-overlap Armadillo transfer",
        "zero_operations": {"decoder_forwards": 0, "encoder_training_updates": 0, "repair_outputs": 0, "Bunny_scoring": 0,
                            "LLM_consumer": 0, "Blender_assets_product": 0, "Google_Key_API_paid": 0, "new_dependencies": 0},
        "summary_wall_s_before_write": time.perf_counter() - started, "summary_CPU_s_before_write": time.process_time() - cpu,
        "bootstrap_wall_s_before_write": time.perf_counter() - BOOT_WALL, "bootstrap_CPU_s_before_write": time.process_time() - BOOT_CPU}
    write("SUMMARY.json", summary)
    link = lambda name: "[" + name + "](" + (HERE / name).as_posix() + ")"
    lines = ["# M6-PERCEPTION-001 冻结编码器定位与区域事实", "",
        "2026-11-15。基线`7ae143a6b062ac3c9fedcbf50939b79082884963`，合同`9f0d2cc3dcd9d7c0213c4fe62ad24af7b85ac077`，PLAN`cf9ad6c5ac2c64915fb883dfac41d91272d9ce3f`，开发训练/校准固定提交`6fa798646795d17081c1cf2cc7ce66f34dd7e53d`。", "",
        "**新头的A检查注意力和B阈值异常判定均未通过预定质量目标。348例可读区域与引用契约核验通过。当前权重未形成可用的插件感知候选。**", "",
        "## 范围与固定模型", "",
        "完整分母为231开发训练、117既有Armadillo迁移验证，共348观察、42patch、42正常、109443个F点观察。四人物同未知上游组且重叠patch/幅度变体相关，Armadillo已在多轮研究使用并与官方预训练图形状重合。当前范围为指定F的合成凹陷定位，整场景扫描、人体部位语义及人/动物全类型覆盖仍待验证。" + link("INPUT_WHITELIST.json"), "",
        f"官方Pointfilter固定提交`6e0ec1eac59ca9f81ee9ca6751c5b3f25effeda2`。只执行702464参数encoder，1024维输出，参数与BN全冻结eval。唯一新头为1024→64 GELU→1，共65665可训练参数，活跃总计768129。官方完整checkpoint另含未调用的decoder，文件中总参数1360899。编码器实际提取{features['encoder_forward_batches']}批，开发中{invalid}个F点观察不可用，以0保留，验证不可用0。" + link("FEATURES.json"), "",
        "完整当前源bbox对角×0.05半径，官方PCA及500采样，每case重置RandomState1729，按F源ID升序，邻域≤500有放回，其他无放回。输入仅当前观察坐标及任务查询ID，参考、损坏mask和生成参数进入encoder次数0。特征float32，开发231的全部F用于float64两遍mean/std，std<1e-6除数置1，标准化后转float32。验证标签与统计参与训练次数0。", "",
        f"一次seed1729训练1200步、batch1024、AdamW 1e-3/1e-4，每样本先均匀case再均匀F。case等权π={training['case_equal_pi']:.10f}，正类权重{training['positive_weight']:.10f}，BCEWithLogits保留弱损坏与正常负例。唯一评价权重为最终1200步。" + link("TRAIN_LOG.json"), "",
        f"encoder初终canonical tensor SHA均为`{identity['encoder_initial_tensor_sha256']}`，含BN缓冲。head初态文件SHA `{identity['head_initial_sha256']}`，最终文件SHA `{identity['head_final_sha256']}`，最终tensor SHA `{identity['head_final_tensor_sha256']}`。归一文件SHA `{identity['normalization_sha256']}`。" + link("MODEL_IDENTITY.json"), "",
        "## A 同25%面积预算的检查排序", "",
        "四分数在同F用当前完整源lumped面积，score降序、source ID升序，取面积≤25%的排序前缀，下一点超限即停止。正常例也给检查候选，候选性质为待核查。下表为普通S的patch等权宏，先平均patch内有效例再平均patch。点池、每例及面积/ell²汇总另存。", "",
        "| 组 | 分数 | 宏AUC | 宏AP | 宏面积召回 | 零命中凹陷 |", "| --- | --- | --- | --- | --- | --- |"]
    for group in ("development_center", "validation_center", "validation_offcenter"):
        for config in ("perception", "old_p", "solid_point", "ring_point"):
            row = evaluation["groups"][group]["configurations"][config]
            rank, operation = row["rank"]["support"], row["A"]["support"]
            lines.append(f"| {group} | {config} | {rank['patch_macro_ROC_AUC']['value']:.6f} | {rank['patch_macro_AP']['value']:.6f} | {100*operation['patch_macro_area_recall']['value']:.2f}% | {operation['zero_true_detection_cases']}/{operation['damage_cases_with_defined_zero_detection']} |")
    lines += ["", "中心与偏心各自的AUC≥0.80、AP较旧p增加0.05、宏面积召回≥0.60并较旧p增加0.10均失败。新头开发排序与召回较高，迁移验证明显下降，现有记录未确定编码器、头容量、损失或来源分布中的唯一失败原因。旧p与几何分数均只消费保存结果，未重新训练。", "",
        "强损坏任务使用norm(reference−observed)>0.10ell作为正类，其余同F为负类，5740个强正例与5027个弱损坏负例均保留。普通/强任务的每例、patch宏、点池、source、幅度、合法凹曲分层、最大漏检片区及并列情况都在完整评价中。" + link("EVALUATION.json"), "",
        "## B 固定阈值异常报告", "",
        f"只用33开发正常patch最大新score的线性q95得到{calibration['threshold']:.10f}，严格超过才选择。开发正常复用训练数据，校准误报为依赖样本上的描述。验证正常误报{evaluation['decision_gates']['B_abnormality']['validation_normal_false_patches']}/9，正常误报门槛通过。score为未校准异常分数。" + link("CALIBRATION.json"), "",
        "| 组 | B宏面积召回 | 零命中凹陷 |", "| --- | --- | --- |"]
    for group in ("development_center", "validation_center", "validation_offcenter"):
        operation = evaluation["groups"][group]["B"]["support"]
        lines.append(f"| {group} | {100*operation['patch_macro_area_recall']['value']:.2f}% | {operation['zero_true_detection_cases']}/{operation['damage_cases_with_defined_zero_detection']} |")
    lines += ["", "中心和偏心B宏面积召回均未达0.60。空结果、无选择时精确率为空、正常误报及漏检面积完整保留。A与B各自未通过，当前候选的感知消费与可靠异常判定均缺达标证据。", "",
        "## 可读区域与稳定引用", "",
        f"已输出348例精简事实、全部A/B区域和{regions['reference_count']}个可回读引用。A区域按sum(area×score)降序、最小source ID并列，文本最多3个区域并列其余数量与覆盖。B阈值预测单列。几何量由当前点实际求得，疑似凹陷标为模型预测，身体部位名与原因故事生成次数0。原始embedding未作为普通事实文本。", "",
        "| 固定抽查观察 | A区域 | B区域 | 文本 |", "| --- | --- | --- | --- |"]
    for row in regions["cases"]:
        if row["id"] in regions["audit_case_ids"]:
            lines.append(f"| {row['id']} | {row['attention_regions']} | {row['threshold_regions']} | [facts.md]({Path(row['text_report']['path']).as_posix()}) |")
    lines += ["", "引用绑定来源、观察SHA、F源ID、encoder/head/归一身份与区域源ID。resolve_region.py可回读同版本当前几何。质心采用当前lumped面积加权，零面积时显式回退顶点均值，bbox实算。三例文本已实际查看，其余字段与所有引用机器核验。普通事实保留原生坐标、面积平方单位和物理尺度unknown。" + link("REGION_REPORTS.json") + " " + link("MANUAL_REPORT_QA.json"), "",
        f"区域契约核验{region_verify['check_count']}项通过，覆盖{region_verify['coverage']['references']}引用。A选中点观察{region_verify['coverage']['selected_point_observations']['attention']}，B选中点观察{region_verify['coverage']['selected_point_observations']['threshold']}，其中两用途可能重复。B空观察{region_verify['coverage']['empty_case_counts']['threshold']}。当前LLM消费者评测、产品/MCP接入与完整任务净收益均未运行。" + link("REGION_VERIFY.json"), "",
        "## 内部复算与完整成本", "",
        f"内部公式复算通过，含1044个已有查询的官方encoder重放、37例PRETRAIN首次采样对照、全部109443个head logit、开发双遍统计、1228800采样对、首批初态BCE和全部A/B指标。额外optimizer step与完整训练重放均0。逐元素比较及检查计{verification['check_count']}，最大绝对差{verification['largest_compared_absolute_difference']:.3g}。规划者独立复核仍待完成。" + link("INDEPENDENT_VERIFY.json"), "",
        f"特征缓存{features['feature_cache_bytes']}字节、采样/PCA缓存{features['sampling_cache_bytes']}字节，首次提取成本保留。17项合成引用I/O与空结果检查通过。"]
    for name in ("features", "train", "predict", "evaluate", "regions_final", "verify", "verify_regions_final"):
        row = costs["phases"][name]
        lines.append(f"{name}完整窗口wall {row['controller']['main_wall_s_including_worker_before_write']:.6f}秒，worker树CPU {row['worker_tree']['tree_cpu_s']:.6f}秒。")
    lines += ["", "COSTS保存逐case取数、索引、PCA、encoder、cache、head读取推理与区域报告，以及共同加载、1200步训练、校准、评价和核验。缓存供训练重复使用的首次代价继续计入，头耗时只是一部分。现有CPU单线程、共享机器，正式提速与LLM端到端净收益仍未测。" + link("COSTS.json"), "",
        "报告呈现修正将空余区域面积改为直接求和，使空集合精确0，并补单位状态。原348份报告/目录、原执行源码与成本保留，2324条引用及几何记录前后一致。另一次只读比对误用references字段后改为实际regions字段，未新增模型或评分。准备阶段工具字符上限与未建目录读取、子agent线程上限均已恢复并记缺测。" + link("REGION_REFINEMENT.json"), "",
        "## 唯一下一建议", "",
        "建议先定义来源独立的感知定位数据与留出验收合同，纳入新来源正常几何、合法自然凹曲负例及合成异常配对区域标注，并冻结来源组划分。当前首版权重停止进入感知消费，候选后续由规划者根据新证据决定。合成正常/扰动配对监督持续有效，真人艺术修正记录对应另一层艺术验收。" + link("SUMMARY.json"), "",
        "本批学习候选与训练仅1次、1200步。encoder/BN更新、decoder调用、修复输出、Bunny评分、LLM消费、原资产/Blender/产品、Google Key/API及付费调用、新依赖均0。"]
    (HERE / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"candidate": summary["candidate"], "A_passed": False, "B_passed": False,
                      "region_contract_passed": True, "next_recommendations": 1}))


if __name__ == "__main__":
    main()
