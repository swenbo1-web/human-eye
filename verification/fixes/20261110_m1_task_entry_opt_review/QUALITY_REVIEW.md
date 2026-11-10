# M1-TASK-ENTRY-001_OPTIMIZE 独立局部质量复核

日期：2026-11-10。复核者：`/root/scale_diag_quality_review`。
固定候选：`7411ac7aa9338f17355ffe5cdf4df113ce862aed`。
工作树：`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`。
证据基目录：[verification/m1_task_entry_001_optimize](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_optimize)。

**结论：局部复核无阻断，未发现事实、覆盖、拒绝顺序或service独立校验被改变。此次既定精简可收口，转向固定未见题的自然消费验收；不另开优化。**

本子审只读源码、历史脚本及原始结果，用标准库解析、哈希、字段差异和算术核对已有数据。没有执行比较器或测试运行器，没有运行产品、Blender、模型或新的数值试验，没有重新审核旧Blender/AB全链。本文是独立后处理和代码审查，作者的运行记录不冒称本子审重新执行。

## 1. 固定源码与改动边界

读取候选Git diff：产品仅 `_validate_arguments` 将显式query的第一次规范化结果保存为局部 `selected_query`；缺省query仍在image类型检查后规范化。后续mode/alignment/task判断复用该局部值。service模块及其独立校验未在产品diff中改变。

独立读取两轮四份MANIFEST，每份均137个唯一路径；旧MCP文件用 `git show b296bae6...:human_eye_plugin/live_spatial_mcp.py` 原字节核对，其余文件按候选文件核对。重新计算canonical摘要，与运行结果中的来源一致：

| 版本 | canonical源码摘要 | MANIFEST文件SHA256 |
|---|---|---|
| b296bae6基线 | 347ec4e52b24ff77239c5540caac52cdc6031e3542c0359798f821538ef4e3ea | 11c93ec2c037a14a75b2955b521fe9016ba1c669874ada3b9d545b99d99726c9 |
| 7411ac7候选 | 0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a | ea4c333ee5ca971e6cdc4880567633e08b3a51fabeb244f107bfdfc9c85f8c05 |

compare01与compare02各版本manifest完全一致；修复比较器没有更换产品。候选MCP文件SHA256为 `babbb88e4ee044e753798c81f78866aaa193642d7408ac4cd7c6ea7216e65928`。

## 2. compare01失败记录及脚本归档

[qa_history/compare_validation_01.py](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_optimize/qa_history/compare_validation_01.py) 的实算SHA256为 `4bbc2c5b27839ad1f454028091e31c78c43b9359be486bb5aaa3fa812dc34eae`，与compare01运行结果记录的runner SHA完全一致。可以将其视为该记录所绑定的原脚本字节，而不是用修改后的脚本覆盖首跑。

首跑两个子进程各自30项检查通过、exit=0，但跨版本聚合 `passed=false`；29配对中的三条失败保留：

- `overview_disabled`：记录中的差异仅为 `/request_trace/request_id` 和 `/request_trace/trace_id`。
- `ordinary_nearest_actual`、`compact_nearest_actual`：差异是 `/binding/document_epoch` 及其派生scene_revision、scene_fingerprint。几何输出本身未出现差异。

这些判断来自直接解析首跑两版本保存的结果并逐字段列出差异，不依赖作者失败解释。**首跑聚合仍是失败，不改记通过。**

## 3. compare02修正是否恰当

逐行比较首跑归档脚本与当前 [compare_validation.py](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_optimize/compare_validation.py)。当前脚本实算SHA256为 `4eae40867c41ab9ee87b7029c1a7d65f1f5e6ddab02ec0d69273ba0c670523d0`，与compare02记录一致。24项参数合同文件两轮同字节，SHA256为 `4bd27f2a9fca24821b7adbccbbbe9458d46104467ec4c87f927fffe0cc30e948`。

修正内容是：

1. 在nearest有限RNA宿主的真实采集之前，将空driver_namespace中的 `_human_eye_document_epoch_v1` 设为 `sha256(ascii case_id)[:32]`。两个版本使用相同case派生值，且检查采集后未改变。这是在配对之前固定夹具输入身份，不是删除或改写返回中的来源字段。
2. 从明确的 `/trace_id`、`/request_trace/trace_id`、`/request_trace/request_id` 读取关联ID，增加其比较归一化。保留原来的runtime source/build归一化。
3. 新增 `raw_output`，保存深拷贝的未归一化MCP工具结果对象，其中content.text仍是实际原字符串；另存被归一化的关联ID及fixture_settings。

**保存范围需精确表述：** compare02保存了未归一化的MCP返回对象及原text，足够独立复核此处结果；这些是离线 `_dispatch_tool` 返回值，不是实际stdio/TCP网络帧原始字节。compare01没有 `raw_output` 字段，不能反称首跑未归一化wire也已完整保留。首跑脚本和失败结果本身未覆盖。

作者normalize函数通过字符串替换处理身份值，覆盖范围理论上比字段路径更宽。因此本子审没有只相信归一化后的相等，而直接比较compare02两版本的原始body：

| 代表 | 未归一化body的全部实际差异 |
|---|---|
| overview_disabled | request_trace中的request_id、trace_id |
| ordinary_task_actual | 顶层trace_id、binding.runtime_source_sha256 |
| ordinary_nearest_actual | 顶层trace_id、binding.runtime_source_sha256 |
| compact_relations_actual | 顶层trace_id、context.runtime_source_sha256 |
| compact_nearest_actual | 顶层trace_id、binding.runtime_source_sha256 |

未发现几何值、对象、coverage、partial/unknown、document_epoch、scene_revision或scene_fingerprint被归一化掩盖。两条nearest固定epoch分别为 `a08d8fc101ef607e4e2dff0020b4d3b1` 和 `0e52bdff208a6c74e0d50c28f3fee31d`，与case_id独立重算相符。

## 4. 分母、计数与独立service拒绝

独立解析EXPECTED_CASES及两版本RESULTS，逐项核对异常类型/消息、实际校验计数、输入不变和采集计数；没有只读取顶层passed：

- 每版本 **24参数案例 + 5 service代表 + 1直接service拒绝 = 30项**。
- **29条配对**对应前两类；直接service拒绝作为独立对象另外比较，不能说配对表漏了一项，也不能把它重复算入29。
- compare01聚合3条不相等；compare02全部29条相等，直接service记录亦相等。
- 两版本子进程exit均为0；记录中的guard校验、快照未变、零额外进程/网络/信号尝试均成立。

| 成功参数路径 | 基线MCP validate_query | 候选MCP validate_query |
|---|---:|---:|
| 显式overview、普通nearest、task | 4 | 1 |
| 缺省query | 3 | 1 |
| surface-nearest selector或旧focal形式 | 5 | 1 |
| 简洁relations、简洁nearest | 1 | 1 |

参数失败的错误先后仍保留：显式坏query先于坏image，缺省query的坏image在query校验之前拒绝；False不是缺省query；session/额外字段/selector互斥/alignment等检查未被此次复用改变。失败路径的0、1等实际次数按其合同核对，没有一律假定为1。

五个service代表前后均为一次 `service.observe` 和一次service层 `validate_query`。disabled overview采集0次；四个task/nearest代表各采集1次，实际返回2米距离。原生完整overview几何没有在此验证。

直接绕过MCP调用 `service.observe('direct', query={'mode':'overview','unsupported':True}, include_image=False)`：前后均由service抛出 `ValueError: query contains unsupported observation fields`，service校验1次，采集增量0，输入不变。代码使用真正service调用，仅以wraps计数；不是mock拒绝结果。这足以支持该代表中service独立入口校验仍存在。

原首版14项回归的本批作者记录为14通过、0失败/错误/跳过。本子审读取该记录，不称重新执行。

## 5. 原件摘要及保留范围

| 原件（相对证据基目录） | SHA256 |
|---|---|
| compare_01/RESULTS.json | 4051e92c30abac6d47887ad7e2ddeb72572f3c1c75df731691aea635504f652c |
| compare_02/RESULTS.json | 558b9aad1e0215ce5cdedb63ab6cad7ea390c1e345e6c30b056f4bb909d19425 |
| compare_02/baseline/RESULTS.json | 0df7457663db8014d1deac92b886ebe3e2c7ae5088d0c05669f4fc272a998b14 |
| compare_02/candidate/RESULTS.json | 9e6e2e3e5e6a34235f94956ff83ddd5f10f189e8ecf8ba18d5f8f89b340db37c |

本次是有界离线合同与实现差异审查，不是性能基准，也没有重新执行旧Blender场景。首版两个真实Blender记录仍归属b296bae6，不能改称7411ac7实机通过。安装、真实CLI、完整overview、新模型自然选择与实际收益均保留为未验收。

不存在需要再开一轮局部优化的实质缺陷。后续按已批准的固定候选、同期C/S同内核、未见题及完整分母规则进入消费者验收；旧AB001负收益和004/005历史失败继续保留。
