# M2 精确目录：独立来源与执行记录闭合核查

复核对象：实施提交 `c0134088796d47a982edfc838aa6704c8e052d57`，固定产品 `fac9b4373575d653cc96f39f1dcb225300cd5977`，137 源摘要 `6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb`。本审查只读取源码、Git、wheel、已保存 JSON 和文件字节；没有启动模型、Blender、产品服务或安装，没有修改作者证据。

结论：**所核来源、同版安装和保存的执行/关闭记录一致，没有发现阻塞性来源缺陷。** 成本公式和产品数值正确性由同轮另外的独立审查承担，本报告不签发整体工程或默认激活准入。

## 本轮实际独立执行

`audit.py` 独立使用 Git archive、SHA256、AST 常量解析、ZIP/RECORD 和 JSON 字段核对，不导入产品，不调用作者 `verify_saved.py`。最后一次共 10,766 项机械一致性检查，无失败。这个数字是文件和记录断言数量，不是场景或测试任务数量。

- INDEX 摘要为 `bf33b9249869724209adecf9188de7f0f1ee6a33d0f6505a74061dcaada74bcf`。4700 个索引文件均核对大小、SHA 和对应 c013 Git blob；另外核对 COMPLETE 与 INDEX 自引用文件，共 4702 个 Git 文件。当前实施工作树干净。
- 旧 00b 和新 fac 两份 137 文件清单均与对应 Git blob 一致，重新用源码版本常量和清单计算 canonical 摘要，分别得到 4eb 与 6ac。新运行源码在 Git、当前源树、隔离构建源、wheel 和实际安装目录一致；旧实际安装源与 00b 也逐项一致。
- wheel 整包 SHA 为 `5575bd85ff0e89f956728f5925de06bee5d35037b4a42f546093bcf98ff84f34`。144 个 wheel 成员的 RECORD 及安装字节一致。实际 launcher、admin 和 RUNTIME_BINDING 三个文件摘要匹配安装回执。
- 从 00b 到 fac 只有七个预期产品文件变化；fac 到 c013 的 137 运行源没有变化。ROOT_PLAN 与根已提交计划逐字节相同。安装回执记录无默认激活/owned reference 变更；记录的保护文件当前字节也仍匹配安装前清单。
- 准备输入绑定与正式 run 的 INPUT_BINDINGS 完全一致；22 个调度来源固定项均匹配当前及测量前提交 `ceb31981` 的 Git 字节；九个早期基线固定项、三资产 SHA 保持一致。记录的冻结提交时间为 2026-11-12 08:48:17+08，正式矩阵进程起始为 00:48:53.577Z，顺序一致。
- 正式 schedule 与准备 schedule 一致：27 个纯目录会话，各 11 请求；另 9 个两步会话，各 2 请求。实际 315 个业务 RPC，含 36 close 后共 351 个宿主事件。没有性能替补/重试记录，三输入各路线和次数符合固定计划。
- 27 个涉及产品的会话，其 ACTUAL_INITIALIZE/config、业务回包来源、installed_distribution 和 137 文件身份相符。每个会话的 runtime 句柄证明在首次业务前获得；保存记录中 27 个真实 Python runtime 和 launcher 均退出 0，句柄已关闭。36 个自有 Blender 的 close/reap 为 0，初末几何指纹相同，记录的原文件/保护文件未变。
- 首轮 entry_01 的 forced close、passed=false 原件保留；修正后的 entry_02 有 21 观察记录、6ac 身份、非强制退出 0。额外 typed 功能会话也为同一 6ac 安装和正常回收。

## 需要正确表述的对照范围

**两步表中的 native 是“原生目录 → 旧插件 selected task”混合链。** `measurement/CONTRACT.md` 已预先明确所有路线第二步调用正常产品 selected 查询；冻结 `matrix.py:91` 对 native 选择旧版 ready，三个实际初始化记录均为 4eb。该设置用于检查目录节省是否转移到后续产品采集，符合本工程目的；它不是两个步骤均采用原生算法的完整任务基线。纯目录的 27 会话中，native 路线没有产品 runtime，和这三个混合链会话应分开。

审查脚本第一版误把 native 第二步预期为新候选，产生 6 项审查假失败。发现冻结脚本及合同的实际规则后，仅修正审查预期；`INITIAL_audit.py`、`INITIAL_RESULTS.json`、`INITIAL_CHECKS.json` 保存原错误。没有因此改作者源码、样本或证据。

## 保留的未验证项

- 上述退出核对是保存句柄/creation-time/exit 记录间的独立一致性复核，不是本轮重新见证历史进程退出。
- Git/UTC 和保存固定项证明记录上的预冻结顺序；不能独立证明作者每一次编辑发生的瞬间。没有借文件时间戳宣称更强时间保证。
- 原生各类状态变更的完整真实 Blender 序列、同世界几何对象替换的实机孤立反例、完整 JSON Schema 求值器，本来源审查没有运行。已有作者披露继续保留，不将共享 SceneResidency 和 fake-handler 通过扩大成实际全事件验收。
- 原生峰值内存、模型质量/轮次/token/费用及完整研发协调成本未测。工程目录通过不改写旧 M4 完整任务净收益失败。

机器结果见 `RESULTS.json`，逐项证据断言见 `CHECKS.json`。所有输出均位于根的独立复核目录，实施材料未改。
