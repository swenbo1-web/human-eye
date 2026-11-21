# M1 选区默认量测入口独立复核

2026-11-21，隔离候选 `1cb43fd35e680169c0a6275b52e47513de638624` 工程通过。屏蔽 `human_eye_scene_observe.description` 后两版 AST 完全一致。实际五项工具目录只有该描述从 3,254 增至 3,287 B，输入 schema 一致。143 个 Git、wheel、运行源及 319 件回放原件核验通过。

同一历史无图选区量测的两版实际完整回包逐字节相同。明确 full 为 39,717 B，默认与显式 brief 正文逐字节相同，均为 **7,042 B**。默认包含 7.318640584152224 m、世界最近点、相应源三角与可复用区域引用。三头双阶段 12/12 保全。历史实际 CLI 事件有原全文，固定回放的六个 full 阶段丢过量测和引用。62 组兼容 A/B 原包相同，其中两条过期引用逐字节匹配历史拒绝。

N15 P2 第 5 调的 12,032 B 无图简报保有量测、点对、选区引用。固定预算裁掉显示目录一行的三个字段，列为另一个真实边界。新增模型、Blender、构图和付费均为零。说明的自然采用、模型用量和调用收益尚未测。本批之后用 [双选区遮挡对照](PERF050_DUAL_REGION_OCCLUSION_TRANSFER_001_PLAN.md) 观察自然行为，先前的模型试题照原分母封存。

[报告、实际线包及边界](https://github.com/swenbo1-web/human-eye/blob/c6e25f1e998280ecbd210f2a0a0d3713d6940c05/verification/m1_source_region_default_measurement_entry_001/REPORT.md)
