# b32g 整版隔离验收证据

2026-11-24。A 为桌面现行发行 `9.7.2+20261110.scale.opt.r1`，源码 `df016079b0265ee327f884c90dd4815c392016b6`。B 为集成发行 `9.7.2+b32g`，源码 `6c93f2375d1073b33e721a168f1fcf610ac6dbdc`。本批只做隔离验收。

- [结论与分段](REPORT.md)记录同题量测、4 次只读概览、Hook、8 次启动诊断、回退和正式发布边界。
- [矩阵](matrix/SUMMARY.json)和[原包复核](matrix/RAW_COMPARISON.json)对应四个实 Blender 和固定 MCP 槽。各槽保留合成夹具初末几何、请求、回包、得分、独立闭槽证据和阶段计时。两版共 12/12 几何、4/4 只读。
- [Hook](hook/REPORT.md)同时保留原线上评估失败与[同原件复核](hook/live/CLOSED_HOOK_REVIEW.json)，以及固定 launcher 的轻路径审计缺口。
- [启动对照](startup_verified/RESULT.json)冻结顺序 ABBABAAB。首轮设置错误发生在进程启动之前。
- [回退](rollback/verified/RESULT.json)是隔离项目 A→B→A 的最终验证，含[过期计划拒绝](rollback/verified/reverse_stale_refused.stderr)。[保护状态](PROTECTED_AFTER_FINAL.json)保留现行版审计出现两条同期初始化记录的事实。

## 核验和复现

在本目录运行 `python verify_public_evidence.py`。脚本核对[总索引](EVIDENCE_INDEX.json)中发布文件的 SHA-256，并核对矩阵、Hook、启动和回退的判定分母。无需 Blender 或外部 API。

现场重放需两份 Windows 隔离安装、相同 Blender 和 NumPy 2.3.5 / Pillow 12.3.0。工具原脚本为 [matrix/run_matrix.py](matrix/run_matrix.py) 与 [matrix/ENTRY_CHECK.py](matrix/ENTRY_CHECK.py)。按实际隔离目录设置归档脚本的 Blender 与安装路径，加载 `matrix/FROZEN.json` 所列的输入。G60_D12 和 D48 的合成 Blender 文件、输入元数据、独立真值、评分器和宿主辅助脚本在产品提交内附带，可按冻结摘要恢复。[冻结版合成夹具与辅助代码](https://github.com/swenbo1-web/human-eye/tree/6c93f2375d1073b33e721a168f1fcf610ac6dbdc/verification/scale_diag_001)

实际运行脚本随证据保存为历史版本，沿用原现场路径常量。回退脚本会读取指定项目的真实状态以构造隔离副本。复现回退时请使用自己的测试输入，在仓库外的隔离目录运行。

## 公开范围

索引逐项保留源文件摘要。发布后字节相同的条目标记 `byte_exact`，调整过本机路径或导出的管理回执摘要有独立发布哈希。夹具本体使用上述 Git 固定版本。同实验的本机连接配置、桌面 Hook 注册副本、生产会话和审计原件、迁移备份、锁及含本机细节的原生逐调用材料保留在原归档。
