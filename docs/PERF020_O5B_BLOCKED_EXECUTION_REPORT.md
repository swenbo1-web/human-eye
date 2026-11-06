# PERF-020-O5-B 运行阻塞与收口报告

整理日为 2026-11-07，实际执行记录的 UTC 日期为 2026-11-06。

## 结果

**BLOCKED。** 必要的 20 个 mock 场景和真实隔离 QA 入口检查通过，首个 normal 会话在实际产品启动时未通过方法体签名核验。服务尚未发布 `SERVICE_READY`，全部初始化、观察和 physical RPC 计数为 0。后续三个会话保持未启动，40 条观察均未发送。

本批的连接内归因状态为 `unknown_incomplete_batch`，连接操作、residual、RTT 和收益尚无样本。下一步由管理员按收口计划决定是否修复此 QA 接线或转入同版完整任务对照。本批交付具体阻塞和清理原件。

## 固定身份与授窗

控制 HEAD 为 `ca5b3d06744075e5fd28a92cbc7bf2783ecf9fc9`，分支为 `codex/perf010-direct-task-query`。本报告提交后的交付 HEAD 在最终封存中单独记录。本地 Git 提交收录本报告，QA 和原件通过本地逐文件封存交付。

固定 freeze 摘要为 `6fee603bff5b487d8aa02325d50bd44985ef74f29acc49189a1f4fb640ec1b81`。产品为 E `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15`，130 源摘要为 `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163`。

本次实际接收的管理员 `send_message_to_thread` FCO 为 `fco_01a1b0dd-001b-7343-ae97-c63cefa22f9a`。其完整原文保存在 `verification/fixes/20261106_perf020_o5b/execution/RECEIVED_WINDOW_FCO.json`。规范化 grant 的摘要为 `db274bbcc62cd91858351e939bf86d5e35c43d6a8a51e9fbe9a2b1e89de3cd74`，原始 FCO 与规范化合同分别保存。

窗口为 `PERF020-O5B-WINDOW-01`。主写 STATE 从授窗至离线分析结束的摘要保持 `06b2b1c015668b246e280d7c793e1b34715d05465479690572df48356183f58d`。实际运行严格使用四个预登记 nonce 的首项，输出目录和首错保留。

## 实际经过与分母

| 阶段 | 实际结果 |
| --- | --- |
| 01 必要检查 | 20/20 场景通过，每项分别执行 normal 和 diagnostic 假平台方法 |
| 真实 `-I -B` 入口检查 | 通过，在产品 bootstrap 前退出 |
| 02 四会话 | 第一个 normal 启动失败，后续三个会话未启动 |
| 初始化 stdio / 观察 / physical RPC | 0 / 0 / 0 |
| 宿主几何构造 / capture / 背景控制 | 0 / 0 / 0 |
| 服务构造 | 实际执行，audit 留有启动事件 |
| 产品 setter / 保存 | 0 / 0 |
| 本批测量角色 | 实际 3 个，计划完整会话为 12 个 |
| 03 离线分析 | 发布 incomplete 原件后 exit 1 |

原来的 60 条观察没有重新发送。本批 normal 和 diagnostic 的真实观察数都为 0，冷、暖请求耗时及五事实正确性保持未测。

## 首错与覆盖缺口

真实服务经固定入口加载产品，在 worker 的 `serve()` 中调用 `connect_internal.install()`。normal 和 diagnostic 都先构建并核验 clone，normal 的实际方法选择发生在核验之后。

首错位于 `harness/connect_internal.py` 第 239 行。

```python
assert _signature(original.__code__) == _signature(pristine.__code__)
```

worker 保存 `AssertionError` 和完整 traceback，`connect_internal_metadata`、`bridge_timing_metadata` 均为 null。方法体签名比较尚未完成，实际 `_connect` 也尚未执行。控制器随后记录 `WriterExitedBeforeRecord`，说明 `SERVICE_READY` 发布前服务已经退出。

必要 mock 从固定源中提取类方法并在假平台依赖下编译，两个模式经过同一种方法构建。真实隔离入口检查显式记录 `product_bootstrap=false` 和 `actual_product_entry_served=false`。这组检查覆盖了有限方法行为和导入接线，实际产品加载后的签名核验缺少前置覆盖。这是本次可避免的 QA 验收缺口。

签名包含字节码、异常表、栈大小、局部变量数量、常量、名称、参数和 flags 等字段。失败现场未记录逐字段比较值，具体不相等字段仍未知。已读固定 SourceGuard 源码，其正常路径使用完整模块原字节 `compile(..., dont_inherit=True)`，未发现显式 AST 改写。源码编译上下文差异是待验证范围，当前原件只证明签名断言失败。

离线分析读取不到 `SERVICE_READY.json`，因此保存 `FileNotFoundError` 并将捕获状态设为 `unknown_incomplete_batch`。首错、派生错误与各阶段退出状态分别保留。

## 清理与资源

原生命周期保留三个角色的 PID、创建时间和终态。

| 角色 | PID | 创建时间，100ns | 退出码 |
| --- | ---: | ---: | ---: |
| Blender | 25176 | 134384424684167435 | 0 |
| launcher | 10248 | 134384424694859791 | 1 |
| 实际 service | 18504 | 134384424695046390 | 1 |

三个终态均为 `alive=false`。launcher 已 reap，reader 已 join，绑定句柄、sampler 和 Popen 句柄已关闭。Blender 已 reap，控制 socket、sampler 和 Popen 句柄已关闭。产品 host close 返回，清理错误及强制终止列表为空。清理结论来自本次已记录终态，未追加进程表采样。

service 的退出前样本仍有可用内存值，退出后内存为 null，并附 `process_exited_memory_not_sampled`。这些范围单列于独立成本记录。三个测量角色的终态累计 CPU 可以按角色累加，整批控制器、检查及分析进程的完整 CPU 未测。

## 成本与未知

| 外层命令 | wall，ms | exit |
| --- | ---: | ---: |
| 01 必要检查 | 1284.3669 | 0 |
| 02 会话控制器 | 3105.9476 | 0 |
| 03 离线分析 | 119.7436 | 1 |
| 合计 | 4510.0581 | — |

完整 argv、UTC、wall、stdout、stderr 和退出码均在 `execution/01-required-checks`、`02-four-sessions` 和 `03-analysis`。02 的进程 exit 0 来自控制器发布失败 summary 后正常返回，实际会话结果为 failed。

表中合计只覆盖 01—03。后续报告提交与最终封存分别使用 04、05 命令记录，保留各自外层成本范围。

首个会话 `whole_owned_cycle_ns` 为 2301.4589ms，worker 的 `instrumented_worker_wall_ns` 为 863.3011ms。这些范围嵌套在外层命令 wall 内。clone 准备在返回元数据前失败，独立耗时未测，worker 总跨度包含产品启动及其他工作。

无观察请求期间 Blender 已执行 28 个轮询事件，新增 84 次 clock。stop check、control poll 和 accept wait 的原操作跨度分别为 1.1699ms、0.2135ms 和 991.8082ms，可见记录跨度合计 0.2036ms。这些属于等待及部分仪表成本。

20 个 diagnostic 假平台方法调用记录了 256 次额外 clock、160 个逻辑记录和 241 个逻辑容器。40 次 normal/diagnostic 检查准备另有 80 次 clock，准备跨度合计 684.4312ms，嵌套于 01 命令 wall。上述计数属于 mock QA 范围，真实观察计数仍为 0。

服务构造 audit 跨度为 30.6265ms，内部 inclusive span 为 30.3523ms，二者存在嵌套关系。模板生成已发布原件，末尾耗时字段随启动失败而缺失。完整观察扰动、失败 clone 准备、记录发布内部 CPU、静态支持操作、模型思考等待及整批端到端总成本仍未全面测量。新增模型消费答案为 0，token 和费用未测。

## 交付边界

本次中断后先核对了现有 HEAD、STATE 和原件。01—03 均已有完成的退出记录，恢复后只继续静态复核和报告收口。Agent Learning 恢复后再次确认本执行任务仍为 `a1b43a72-c60e-4b97-ac5c-449fc729b472`，write version 783。

独立失败复核和独立成本核算保存于相邻目录 `verification/fixes/20261106_perf020_o5b_runtime_review` 与 `20261106_perf020_o5b_runtime_cost`，最终封存记录其实际摘要。辅助命令出现的错误保留在各自记录中。

本批没有形成可移除代码的证据，连接内部归因仍未完成。既有 E 的 PT 假零及假目标、O4 的 F 准入失败保持开放。管理员收到具体 BLOCKED 和原件后复核，本线释放窗口并结束此次批次。
