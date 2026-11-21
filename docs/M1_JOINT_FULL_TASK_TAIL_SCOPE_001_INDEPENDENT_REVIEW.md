# M1 联合全量单距离尾置独立复核

2026-11-21，接受隔离候选 `4e4c653a4d4726576f4f4d2a9d7b9decede44cbf`，关闭 [多事实来源裁切回归](M1_JOINT_FULL_TASK_TAIL_001_INDEPENDENT_REVIEW.md)。它仅在既有回包条件上要求 `facts` 恰为单项 `surface_proximity`，不改变采集、量测、图像或工具契约。

- 143 个运行源的 Git、wheel 和隔离安装逐件一致。248 件 ZIP 原件和 wire 包独立核验。两版实际五项工具目录逐字节一致。
- 十项合法量测的三版真实 MCP 线包均为 39,622 B。固定三种工具头、两个阶段独立重算，旧宽版有 **0/6** 保留达标 SCENE 完整帧和原源版本，窄修 **6/6**，与原布局一致。预计超出固定预算的 137 个量测叶仍被裁切，完整 MCP 原包含全部十项。图块和观察行路径／引用／摘要原样。距离加 AABB 与单项 `axis_gap` 均沿原顺序。
- Far00 和 M09 的单项距离回包与旧版通过的真请求逐字节相同，候选 **12/12** 保留整件量测、可读性证据和原 PNG。24 对兼容控制的两侧原包逐件匹配上批，单项距离 `unknown` 保存状态和原因。固定裁剪后的正文仍可能整体无法解析。
- 每臂每案 72 个热回放。派发中位 Far00 为 1.27845→1.28090 ms，M09 为 1.16100→1.15960 ms。新增 Blender、模型、构图、费用均为零。模型自然采用、补查和端到端效果未测。

候选作为 [范围反转对照](PERF050_SOURCE_SCOPE_RANK_TRANSFER_001_PLAN.md) 的固定隔离版本。正式部署未切换。

[实装结果与原件](https://github.com/swenbo1-web/human-eye/blob/595ed328a6eb2f00a1780171ea09b903c5d2bdfa/verification/m1_joint_full_task_tail_scope_001/REPORT.md)
