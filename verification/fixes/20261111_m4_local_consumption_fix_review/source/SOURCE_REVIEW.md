# LRC-PREP-001 封存差异独立复核

**来源与冻结差异子项通过，无新增阻断；不代替根对打包行为的复核或整体 GO。**

固定旧准备 `169b0be061e91b126f46313478690564ccb2bd60`，新准备 `db4ec4c4e0fa3cbf44a8f57fb3f4826730432e81`。新 PLAN SHA `036a091cfc69a5cb085d5d71e649f7d2673967fb3be5552a6669e2e724117efb`，打包器 SHA `3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365`。

本轮只执行独立标准库 hash/JSON/ZIP 与只读 Git 对象核查；未运行作者 QA、产品、模型、Blender、CLI 或安装器，未改实施树。核查前后工作树干净，未重复 wheel/安装矩阵。

实际检查结果：

- **720 索引文件 + 4 根自引用文件 = 724 实际 Git 文件**，集合完全相等。全部 724 份当前字节、固定提交 blob、索引/封存摘要一致；索引文件字节总量 **27,498,323**。
- 四份排除仅限根 `ARTIFACT_INDEX.json`、`FIX_READY.json`、`FREEZE.json`、`PREP_READY.json`。原先漏索引的九份嵌套合成 FREEZE 这次全部纳入，且与旧 Git blob 相同。
- 原 **692** 条文件路径无删除。其间九份文件因修复或重新封存而变化，全部旧版本已在 `original_169b0be0/` 保全；该目录列出的 **11/11** 原件逐字节等于旧固定提交，包含原打包器、旧 seal/PLAN/报告和两份未变合成脚本/报告。
- 原输入、匿名映射、九格顺序、评分、收益合同、actor、transport、driver、schema、安装控制及准备失败历史等 **54** 项相关原文件 Git blob 不变。当前 **137** 产品源散列仍等于已审 `e077fce3 / 53db4197…` 清单。
- PLAN 的 12 条结构化变化仅为 pack/seal/reuse 摘要、五条修复材料引用、phase、preparation_fix、打包器顶层摘要和合成验收指向；分组、题面、模型请求、预算和评分收益条件未变。新 phase 仍要求单独根 GO，`preparation_fix.formal_GO=false`。
- 测试原件 ZIP 01 的 **2** 成员、ZIP 02 的 **618** 成员分别与完整成员集合、长度和 SHA 一致。原 wrapper 路径 `FileNotFoundError` 结果仍为失败，旧 wrapper 与第一次 ZIP 均保留。两次 wrapper 记录使用同一个新 pack hash；本轮不重跑其 310 项断言，也不把作者结果当成独立行为证明。
- 原 pyc 删除自动审批拒绝记录原字节不变；`quality_handoff/__pycache__/pack_quality.cpython-312.pyc` 仍留在本地。本轮没有清理、重试删除或绕过拒绝。
- 当前真实批次根仍无 GO、STARTED、RUN_RESULT 或 cells；合成材料不计为正式消费者。

原 PREP_READY 中 **875.063302 秒**准备窗口仍为原准备阶段的历史值，不能解释成此次修复也被纳入同一计时。新 FIX_READY 有封存 UTC，但本子审没有取得此次修复独立完整耗时，留未测。

逐项路径、PLAN 差异、原件 SHA 和可重复独立脚本分别见 `SOURCE_REVIEW.json`、`recompute.py`。该报告只支持新准备包的来源连续性与实验变量保持；根仍需结合行为审查决定是否放行唯一九格批次。
