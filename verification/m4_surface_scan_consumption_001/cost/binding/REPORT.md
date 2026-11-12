# 六格消费原件的来源与计时边界复核

6276 项离线断言通过。匿名质量封存、六个私有 final、原始模型事件、26 次业务请求和返回、六个完整原始 ZIP、12 份初末网格快照均能对应到同一冻结批次。检查运行仅使用 Python 标准库与 Git 只读查询。

## 固定版本

- 交付提交为 `e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3`，准备提交为 `bedcc827ec548e3afab816c0986db0c99eb42bb8`。
- 产品提交为 `c1cb2da32034e056a270384e691a2cde8dddbc0d`，138 源聚合摘要为 `c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943`。
- 根质量 seal 的 SHA256 为 `1a205c053d7bfff76e427f83a73749bbb2a04d4ca040b92396254dd12b82942f`。外部成本计划 SHA256 为 `21d3bb4a1a947a8debfe3db2c5e412359fae58ed6436e0979b6c558c2ac30393`。
- 原交付 1974 个内容文件与交付清单共 1975 文件，逐字核当前磁盘与交付 Git 对象。138 源另核完整枚举、逐文件 SHA256、产品／准备／交付三个 Git 树、wheel 与现有隔离安装，重新计算版本元数据加 manifest 的聚合摘要。

## 匿名归属和实际消费记录

| 实际顺序 | 消费格 | 匿名 ID 后缀 | 业务尝试 | 已记录 provider cached input |
| --- | --- | --- | ---: | ---: |
| 1 | N1 | 007886c1beefd7c6 | 4 | 27136 |
| 2 | P1 | a5958c6899df02aa | 5 | 65408 |
| 3 | P2 | 16df3f049c011e05 | 4 | 48896 |
| 4 | N2 | b9ec064a37f1c4a1 | 4 | 21504 |
| 5 | N3 | 3b74126ed5f72eba | 3 | 12416 |
| 6 | P3 | 7958cbdd56ce7e5d | 6 | 63872 |

私有匿名表与准备提交、PLAN、原打包 provenance、公开 INDEX 和质量 seal 一一对应。每格 `consumer.final` 的 UTF-8 字节、CLI `final.txt`、`PUBLIC_FINAL.txt`、匿名 `answer.txt` 以及原始模型事件最后一条公开 agent message 全等。六个原 ZIP 的文件集合与每个文件的字节和当前原件相同。

逐事件核私有 `events.jsonl`、`CONSUMER.public_events/tool_calls/all_public_messages` 与公开业务投影。26 次 owner 请求、参数、返回以及薄客户端原始 TX/RX 均对应，全部保留。每格实际 `tools/list` 的原始 RX 包含冻结的共同原生声明，P 组额外包含冻结的完整普通 observe 声明。实际 CLI 参数中的共同模型、effort、隔离和功能设置与准备合同一致，共同文字输入 SHA256 和 UTF-8 长度一致。

CLI 会把 MCP 返回中的 `structuredContent` 映射到 `structured_content`，并用 item 的 `status` 表达工具失败。26 次 `content` 块全等，owner 的 `isError` 字段没有以原字段名进入 CLI 事件。P1 第 3 次和 P3 第 3、4 次 owner `isError=true` 对应 CLI `status=failed`，CLI `error` 字段为 null，错误正文保留。计数须同时使用这些实际失败证据。

## 输入、进程与冷态范围

六个模型 `thread.started` ID 各异，六个 owned Blender backend、六个实际 owner PID 和三个产品 runtime PID 分别各异。每格私有 `input.blend` 与 BASE 文件 SHA256 相同。实际初末 host response 内的完整顶点、面、世界矩阵与单位数据，和冻结 BASE 的相同字段逐值相等，共 12 份。

N 组实际配置、进程记录和清理记录仅包含原生后端。P 组的独立产品进程在模型消费前完成真实 runtime 归属证明，记录的 installed identity、138 源摘要和版本均与冻结候选一致。P 组启动阶段的 RPC 顺序均为 initialize、initialized notification、tools/list、ping。三个首个 observe 的 measurement cache entry 均为 0，cache hits 均为 0，112 对候选分别完成 112 次 pair/kernel 计算。

这里的冷态证据覆盖 fresh 模型线程、独立 owned 后端与首次未预热的引擎测量缓存。六格记录的 provider cached input 均大于 0。provider 的内部共享状态和前缀缓存受控程度未知，实际解析的模型版本与 effort 未获得回执确认。请求配置与工具 metadata 保留其原有证明范围。

历史 runtime identity 与当前源码字节的一致性可以复核。历史进程内存没有重演。初末快照及文件检查覆盖记录中的终态，运行中已恢复的瞬时变化仍受原 helper 记录范围限制。

## 完整时界与关闭

六格时间戳均满足以下顺序。

1. 外层 `cell_started_ns`，随后完成输入检查、prepare 与实际 backend 启动。
2. 消费者启动、prompt 提交、最后模型消息、turn completed、CLI 退出及 consumer cleanup。
3. owner 完成最终网格回读、产品关闭与独立 runtime 句柄确认、原生后端回收，随后返回 owner finish。
4. prefix 结束，最终 `CONSUMER.json` 与 `OWNER_FINISH.json` 已写入，更新 per-cell `RUN_RESULT.json` 并关闭文件，随后采样 `business_receipts_closed_ns`。
5. 单独发布 `CELL_FINAL_TIMING.json` 并记录其写入关闭区间。六格均在下一格开始前完成该区间。

第 4 步的文件关闭先后由冻结 driver 的调用顺序及标准库 `Path.write_text` 的返回语义支撑。原件包含实际后端关闭时间、owner 结束时间和外层最终采样，未增加 OS 文件关闭探针。`full_cell_wall_ns` 逐格等于最终 business close 减原始 start。原 `total_task_wall_ns` 与 RUN_RESULT 内 `full_cell_wall_ns` 保留 prefix 含义。六格最终 business-close 均在原 570 秒期限内。

`CELL_TIMING_PUBLICATION` 覆盖 timing receipt 的发布，其自身回执写入关闭与后来批次汇总属于原口径之外的区间。缓冲写入和关闭保持原持久化级别，物理磁盘刷写未测。完整成本账本需继续分列批次发布、准备和打包区间。

六份薄客户端 `EXIT.json` 实际缺失，`bridge_cleanup.confirmed=null`、`receipt_status=unknown`、`missing_exit_count=1` 均保持。消费者、owner、原生与适用产品的回收记录独立确认。它们各自保留原有证明范围。

## 核验器修正与重放

第一次离线核验把 CLI result 与 owner result 的完整结构直接比较，因上述字段映射失败。修正为明确核完整 content、structured content 映射与 failed 状态后继续。第二次误将 owner 的 `TOOLS.json` 尝试账本当成工具声明，改为读取薄客户端实际 tools/list RX 后通过。修正详情保存在 `CHECKER_CORRECTIONS.json`。原始消费数据保持原字节。

在同一工作区和已有隔离安装下，可使用现有 Python 以 `-I -B -X utf8` 运行 `cost/binding/verify_binding.py`。脚本将断言明细和每格绑定记录写入 `BINDING_RESULT.json`，自身摘要也记录在结果中。6276 是复核断言数量，实际任务样本仍为六格。

当前 Agent Learning 连接为 `context_bound=false`、`host_epoch=5`、`rebind_required=true`，本子任务未借用其他对话的句柄。
