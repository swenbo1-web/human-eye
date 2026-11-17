# M6 当前进度与产出审阅索引

更新于 2026-11-17。本次发布汇总两条 M6 分支截至第 007 批的实现、实验记录和独立复核。

## 固定版本

| 内容 | 分支 | 本次汇总依据 |
| --- | --- | --- |
| 实现、作者报告、实验脚本和公开统计 | `codex/m6-model-selection-001` | `9047f179c01de3f699a61a6ffda5a9aab45645bf` |
| 任务合同、独立复核、路线与工作流 | `codex/m6-candidate-value` | 007 复核 `e34f3dbb1d09b0e7a68d9c1ad3ec8a711a289ab4`，阶段收口 `6cdde34c8e3be0ed37f27d520e4787dca5479460`，以及本索引提交 |

[实现分支](https://github.com/swenbo1-web/human-eye/tree/codex/m6-model-selection-001) · [复核分支](https://github.com/swenbo1-web/human-eye/tree/codex/m6-candidate-value)

## 当前结论

M6 整体仍在研发。当前已完成感知输入、局部几何事实、图像与源点对应、稀疏修改、保存回读和有限图像反馈的原型链。已尝试的小模型和恢复方法尚未满足完整任务的稳定质量与净收益要求。

当前研究流程为当前网格与参考图像 → 区域事实及 sourceID 对应 → 大模型构造稀疏三维提案 → 隔离副本执行与回读 → 图像反馈选择 → 独立几何评分。评分使用的正常目标和受损标签保持在评价端。后期批次主要在验证这条任务链，小模型的新训练尚待下一机制立项。

006–007 的固定提案幅度校准方向已收口，实施者待命，第 008 批尚未派发。当前主导问题是三维提案的覆盖、方向和局部形状。007 原提案只修改 43 个受损点中的 13 个，连续任意幅度的最佳支持域 RMSE 改善上限为 14.5465%。这使继续细调同一提案的幅度缺少收益空间。

## 优先审阅

1. [007 独立复核与阶段去留](M6_CALIBRATION_TRANSFER_007_REVIEW.md)，含恢复失败、完整成本和固定提案的可达上限。
2. [006 独立复核](M6_IMAGE_CALIBRATION_006_REVIEW.md)，含图像校准、一次批处理优化及冷暖态代价。
3. [005 独立复核](M6_IMAGE_CORRESPONDENCE_005_REVIEW.md)，含像素到 sourceID 的独立核查及恢复质量。
4. [M6 路线历史](M6_MODEL_ROADMAP.md)与[工作流记录](M6_REVIEW_WORKFLOW.md)，保留早期候选去留及用户要求。最新阶段结论见 007 复核和本索引。
5. [机器可读工作流状态](../verification/m6_workflow_state.json)，可定位各批合同、作者提交和独立复核。

## 最近七批的结果

| 批次 | 主要产出 | 实际结果 |
| --- | --- | --- |
| [REFERENCE-REFINE-001](M6_REFERENCE_REFINE_001_REVIEW.md) | 原画与模型对应材料 | 对应资料交付，真实模型消费和修改均为 0，随后补做消费试验 |
| [REFERENCE-CONSUME-002](M6_REFERENCE_CONSUME_002_REVIEW.md) | 4 次真实 Pro 消费与保存回读 | 全部选择不修改，V2 阶段 Pro 墙钟增加 11.72%，首版恢复使用 |
| [MATCHED-REFINE-003](M6_MATCHED_REFINE_003_REVIEW.md) | 4 次匹配图像任务与实际修改 | 4/4 通过恢复门槛，但均存在坐标格点捷径，插件因果收益未成立 |
| [DEGRID-004](M6_DEGRID_004_REVIEW.md) | 去除格点捷径的同任务对照 | 两次真实任务均未通过，暴露定位与恢复基面的缺口 |
| [IMAGE-CORRESPONDENCE-005](M6_IMAGE_CORRESPONDENCE_005_REVIEW.md) | 图像差异到源点的对应与一次局部支撑优化 | 单开发样本对应通过，受损点召回 47/47，最终恢复 1/4 通过 |
| [IMAGE-CALIBRATION-006](M6_IMAGE_CALIBRATION_006_REVIEW.md) | 两份固定提案的三档幅度校准、V2 批处理 | native 提案半幅通过，facts 三档均失败。V2 冷校准时间减少 36.69%，复用时间增加约 0.469 秒，峰值 RSS 增加 5.35% |
| [CALIBRATION-TRANSFER-007](M6_CALIBRATION_TRANSFER_007_REVIEW.md) | 既有外部谱系 cat 样本、1 次新 Pro 提案、冻结校准迁移 | 三档均未通过。图像选中的半幅使三维误差较原提案增加约 1.24%，增加校准约 13.51 秒，完整顺序成本增加约 6.66% |

007 使用先前验证材料中的 cat 个案，具有不同资产谱系，尚不能据此主张全新盲测泛化。006 的速度收益对应冻结提案的校准组件，完整修复任务收益需按各批独立分母理解。

## 更早的小模型与数据工作

- [训练首版](M6_SHAPE_TRAIN_001_REVIEW.md)和[一次优化](M6_SHAPE_OPT_001_REVIEW.md)未达质量门槛，候选已关闭。
- [Pointfilter 预训练迁移](M6_SHAPE_PRETRAIN_001_REVIEW.md)可运行，正常区保护和修复质量未通过，直接迁移未采用。
- [空心外环与连通簇](M6_SHAPE_RING_001_REVIEW.md)已做固定假设验证，当前构造已关闭。
- [感知数据工程](M6_PERCEPTION_DATA_001_REVIEW.md)交付 600 次观察、503 个有效配对，73 个失败保留。数据交付与模型收益分别验收。
- [任务感知原型](M6_TASK_PERCEPTION_001_REVIEW.md)保留 focus 细读与稳定引用能力，定位候选已关闭。
- [稀疏修改及恢复修复](M6_REFINE_RECOVERY_002_REVIEW.md)保留实际保存、回读和异常执行状态的核查记录。

## 作者产出与独立复核

作者源码、报告、成本和清单可从固定实现提交读取。

- [007 作者报告](https://github.com/swenbo1-web/human-eye/blob/9047f179c01de3f699a61a6ffda5a9aab45645bf/verification/m6_calibration_transfer_007/REPORT.md)与[实现目录](https://github.com/swenbo1-web/human-eye/tree/9047f179c01de3f699a61a6ffda5a9aab45645bf/verification/m6_calibration_transfer_007)。
- [006 作者报告](https://github.com/swenbo1-web/human-eye/blob/d7cbbac89389ee6f7bfbac8fb45de3ff348abbe0/verification/m6_image_calibration_006/REPORT.md)与[实现目录](https://github.com/swenbo1-web/human-eye/tree/d7cbbac89389ee6f7bfbac8fb45de3ff348abbe0/verification/m6_image_calibration_006)。

本分支提供独立程序和复算结果。

- [007 独立核验目录](../verification/m6_calibration_transfer_007_review/)及[连续幅度上限](../verification/m6_calibration_transfer_007_review/PROPOSAL_LIMITS.json)。
- [006 独立核验目录](../verification/m6_image_calibration_006_review/)。
- [005 独立核验目录](../verification/m6_image_correspondence_005_review/)。

各复核报告逐项记录本轮实际复算、作者日志与未运行内容。最新 007 复核核对 74 份公开文件和本地 1151 个清单成员，并独立复算三档图像及三维评分。本轮复核未新启动 Blender、Pro 或训练。

## 仓库审阅范围与剩余目标

本次发布包含已跟踪的实现脚本、任务合同、作者统计、独立复核程序和阶段结论。完整模型资产、权重、运行图片、原始会话及隔离快照依照各批本地清单保存，公开清单提供路径、大小和摘要。完整实验重放仍需这些本地依赖。

跨资产稳定定位与三维修复、用户美术验收、完整任务净收益仍待解决。当前尚无通过真实精修验收的小模型。实际 token 以各次 Pro 返回的 usage 为准，供应商费用和未暴露的内部用量保留未测。

本次新增本索引。`docs/M6_PERCEPTION_DATA_001_REVIEW.md` 另有本地分析草稿，待单独整理与复核。
