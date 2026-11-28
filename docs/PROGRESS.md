# 当前发行版本

2026-11-28 以正在使用的桌面 MCP、已安装文件和原 wheel 核对本版身份。

| 项目 | 已核对的值 |
| --- | --- |
| Python 发行版本 | `9.7.2+k049final` |
| 插件基础版本 | `9.7.2` |
| 实现修订 | `v26-surface-scan-pair-cache-20261112` |
| 运行源码 | 145 份 Python 文件 |
| 运行源码摘要（SHA-256） | `7075c79b8aff6821e3cb37882b7123be2728cbf38972f34b93e05ef8afa8e50c` |
| 桌面 wheel（SHA-256） | `308dd624cb4916b28bbe2decae87ac0a80d05dfad793da5afecebc65ac698964` |

桌面安装验收中，真实 Blender 场景的 11 个候选均取得有效量测，最近的 `Peer_000` 为 3.000006 毫米。迁移后的 `UserPromptSubmit` 命令也在该场景返回了空间概览。切换时五条项目 Hook 标记为 `modified`，自动触发取决于使用者的宿主审阅状态。

## 已交付的几何内核

本版对满足工作预算的表面对采用 R3 路径，在超出其保守预算等条件下分派到已交付的 032 求解器。两条路径都使用当前网格，并返回本次量测的有效性和证据。专项中的候选对比、计时原件及未发布实现可按固定提交复查。[049 验收](https://github.com/swenbo1-web/human-eye/blob/5ac2d1815b86eaeef27dbacf148a54ddcc1537e7/verification/m6_r3_final_replacement_049/REPORT.md)

## 历史验收

M1–M5 的模块分工、选区传输、联合观察与量测的原始验收均可按实验批次追溯。032 接入后的整版验收也有独立记录。[M1–M5 阶段记录](https://github.com/swenbo1-web/human-eye/blob/9f6cf33c36b523b07b16f12ee73376628c3d573c/docs/M1_M5_PROGRESS_AND_NEXT_PLAN_20261115.md) · [b32g 整版验收](https://github.com/swenbo1-web/human-eye/tree/c55442993a86bdaea4b4e9f4875b552765c79d16/verification/b32g_whole_release_acceptance_001)

2026-11-03 及更早的主线快照保留当时的报告、判定、发布脚本和接口说明。查询早期 M1–M5 验收时，请按报告记载的产品版本和运行范围解释结果。[旧主线文档目录](https://github.com/swenbo1-web/human-eye/tree/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs) · [旧主线验证目录](https://github.com/swenbo1-web/human-eye/tree/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/verification)
