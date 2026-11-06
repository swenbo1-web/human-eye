# PERF-020-O5-A-R1 恢复与时界诊断

## 结果

R1 已完成旧十条离线复核、10/10 真实 stdio/trace 组合测试、原剩余五会话的唯一 50 次观察及合并分析。累计达到原定 60 次，E/F 各 30 次。旧 O5-A 的 failed、原有效账本 0 与原封存保持，新合同下的 60 条分段账本另列为通过。

当前产品继续使用 E。O4 原准入结论保留，F 本次作为固定诊断比较对象。E 已知的 PT 假零、假目标缺陷仍开放，M3 的修复没有混入此轮。当前五项事实通过仅覆盖已登记场景，模型消费与复杂资产质量尚未测量。

## 固定身份与授窗

| 项目 | 绑定 |
| --- | --- |
| 实际运行控制 HEAD | `950402d25ddcfe6c768b9db22b08dfebc698ba6c` |
| 分支 | `codex/perf010-direct-task-query` |
| 恢复 FREEZE SHA256 | `d72949758cf5aefdb4fb65ef96973b0e25ed1e611aa63358f116ad4decaf1bde` |
| 原 O5-A FREEZE SHA256 | `bf6d90d915ede327d26a76595968e2e342e3c09fd5769612b08ee012349cda2b` |
| 原 111 文件 manifest SHA256 | `5f917a97aef09b5fe9a0a5d38e374f20358b8635aa37977c08fdf98784b611d1` |
| 静态准备 55 文件 manifest SHA256 | `3da6794ee9af9cc9dfb2dff8bd0159187e9fc889e53f890d82da4d15ef548d19` |
| E 提交 / 源码 SHA256 | `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15` / `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163` |
| F 提交 / 源码 SHA256 | `b644c79430ced0c710dc9c8c27b2c72598dfe63f` / `30b28aab341dcec6d7504a95a15089acda506af0a0c11bd14ffd6644ecdb258d` |
| 独占窗口 | `PERF020-O5AR1-WINDOW-01` |
| 整个运行窗口 STATE SHA256 | `4012f495eaded5ca53004c14f61208326e8326c7c9237494e8373ad43daad421` |

真实收到的主线宿主消息已完整保存。为适配既有 gate 而建立的 receiving_fco 明确标为 `normalized_from_actual_received_message`，其 output.text 与原文逐字相同，保留原有来源标签。该本地结构不冒称原始宿主 FCO。[原文](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/execution/ACTUAL_RECEIVED_MESSAGE.txt) [规范化归档](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/execution/GRANT_RECORD.json)

## 分母、质量与清理

| 项目 | 原阶段 | R1 续接 | 累计 |
| --- | --- | --- | --- |
| 实际 Blender 会话 | 1 | 5 | 6 |
| 观察 / physical RPC / 构造 / capture | 各 10 | 各 50 | 各 60 |
| stdio | 11 | 55 | 66 |
| 测量角色进程 | 3 | 15 | 18 |
| live / terminal 资源记录 | 39 / 3 | 195 / 15 | 234 / 18 |
| 原 QA 状态 | failed | 五项均 passed | 原 failed 保留 |
| 修订分段账本 | 离线 10 条 passed | 50 条 passed | 60 条 passed |
| 未运行观察 | 原剩余 50 | 0 | 0 |

实际顺序为原 8-E 十条，再续 8-F、64-F、64-E、256-E、256-F。五项续接保留原 nonce、每项十请求和六背景控制。原十条没有重发，实际观察重试、替换样本均为 0。

60 次五项事实均严格符合原期望，每次采集 2 对象、16 顶点、24 三角形。36 次背景控制共 54 次 QA 属性赋值，产品 setter 和文件保存均为 0。18 个测量角色均正常退出，reader、socket、sampler 和进程句柄已核清理。252 份资源记录中，未知 live 内存字段为 0。六个目录均具备 WORKER_PROCESS 原件，未出现 CLIENT_CONSTRUCTOR_FAILURE。[独立原件复审](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/runtime_review/FINAL_REVIEW.md)

组合测试实际调用固定 E 的 stdio、MCP server、wire、MCP/service request_trace 和 telemetry context，业务与 RAM writer 使用假对象。10 个 fixture 共实际读取、调度、返回各 20 个假工具帧，真实几何观察为 0。测试复现旧包含失败，并验证新时间分段、错误回复、失败 writer 和归属反例。[真实组合结果](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/checks/REAL_CONTEXT_RESULTS.json)

## 描述性耗时

每个 tier/arm 的暖样本为 9，cold 为 1。旧 8-E 来自原阶段，其余来自获准续段，时间间隔和仪器化条件属于实验限制。这些值用于诊断，未重新评分 O4。

| tier | E 暖中位 ms | F 暖中位 ms | E 暖最大 ms | F 暖最大 ms | E first ms | F first ms |
| --- | --- | --- | --- | --- | --- | --- |
| 8 | 24.6140 | 10.1102 | 28.1106 | 14.5084 | 39.7285 | 39.5353 |
| 64 | 24.8657 | 8.1956 | 53.3070 | 18.0052 | 37.8708 | 41.3559 |
| 256 | 26.0426 | 8.5239 | 51.2234 | 12.9370 | 39.1472 | 41.5150 |

十条完整 caller RTT 之和，三个 tier 的 E/F 分别为 262.3947/131.6794、332.5922/128.5327、321.5042/121.3103ms。该总和只覆盖十条响应往返。

完整 instrumented 单会话 QA 周期，8-E/F 为 2827.9868/2816.5488ms，64-E/F 为 2864.6208/2703.3816ms，256-E/F 为 2966.4211/2711.1932ms，包含启动、控制、EOF 回收、STOP 后发布及离线完成检查。原 8-E 完成检查当时失败，当前其他会话使用修订检查，这一周期差异需要保留。

原始角色 CPU、逐次 WS/private 与进程生命周期峰值保存在各 RESULT/WORKER 及独立成本数据。各进程的峰值和 CPU 范围单列，不把峰值相加解释为同时使用量。外层控制器未计的内部阶段继续未测。[合并原件分析](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/cost/COMBINED_ANALYSIS.json)

## 长跨度定位

本轮 E 的五个长请求对应原客户端 `_connect` 整体调用约 24–25ms。另有一条 F 请求的 `_connect` 达到 10.3018ms。

| arm / tier / 请求 | caller ms | client `_connect` ms |
| --- | --- | --- |
| E / 64 / capture-4 | 47.4815 | 24.2949 |
| E / 64 / capture-7 | 53.3070 | 24.9389 |
| E / 64 / capture-8 | 47.9038 | 24.7570 |
| E / 256 / capture-4 | 51.2234 | 25.1621 |
| E / 256 / capture-9 | 48.4594 | 24.3652 |
| F / 64 / capture-4 | 18.0052 | 10.3018 |

对应 E 请求在服务端自己的 `request_recv` 范围为 23.9648–24.8379ms。对应 F 请求为 10.0879ms，server code_execution 为 0.8785ms。客户端和服务端分别在自身时钟上解释，两个跨度可能覆盖同一等待，不能相加。

现在能定位到原 `_connect` 调用范围，尚未区分其中 connect_ex、select、getsockopt、settimeout 及其他原步骤。当前证据不支持将原因指定为 TCP、操作系统、GC 或杀毒软件。QA AST、STOP、control 的观测范围没有解释这五条约 25ms 的 client connect 跨度，未测的观测扰动仍不能排除。

F 的 27 条暖请求全部低于 20ms，本轮没有捕获其历史约 25ms 长尾。六条 first 的 service 写出前、capture 之外范围为 16.4908–21.0481ms，没有重现历史 30.8199ms。以上未捕获项保持原因未定，不追加采样。

## 分段与观测成本

原响应 envelope 保留读取成功 stamp 至 flush stamp。60 条写出后的审计操作独立归于原请求，合计原调用跨度 26.0736ms。它们的完整 trace-finalization 尾部、下一次 readline 调用入口、EOF 和尾段 CPU 未记录，保持未测。audit span 仅证明尝试调用，持久化成功需要单独证据。

| 层 | 新增 clock calls | 新增逻辑记录 | 可见部分记录跨度合计 ms |
| --- | --- | --- | --- |
| service | 1260 | 420 | 与原 capture 记录合计 0.5297 |
| 原 capture 补 stamp | 60 | 0 | 同上一行 |
| bridge | 1500 | 540 | 0.6027 |
| server 请求 | 1860 | 780，另有原 120 条 | 2.4269 |
| server loop | 1377 | 519 | 2.4069 |

60 条业务 WORKER observer 字段结构差量 164,460B，initialize 差量 972B，server 业务字段差量 158,623B。定义为结束后固定 compact JSON 字段移除的差量，整体证据复制、元数据及总 IO 另属其他范围。实际 physical request 共 242,820B，response 共 204,240B。

可见 record_done 减 end 只覆盖部分 RAM 记录工作，未完整测量 wrapper、clock、缓存及调度扰动。各层部分范围可能包含或重叠，原 caller RTT 保持未校正。独立算术从原件重建，没有导入作者账本、分析器或评分器。[独立成本数据](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/runtime_cost/INDEPENDENT_COST.json)

## 命令与准备错误

| 命令 | 外层 wall ms | exit | 结果 |
| --- | --- | --- | --- |
| 01 原 old-only 入口 | 89.2185 | 1 | 隔离导入失败 |
| 02 old-only 外部入口适配 | 172.2322 | 0 | 原十条修订离线 passed |
| 03 真实组合测试 | 590.5242 | 0 | 10/10 passed |
| 04 唯一五会话续接 | 14849.5227 | 0 | 50 条完成 |
| 05 合并分析 | 270.9365 | 0 | 累计 60 条记录 |
| 06 独立原件复核 | 208.3524 | 0 | 只读复核 |
| 07 独立成本复算 | 132.5821 | 0 | 只读算术 |

以上独立进程命令均保存完整 argv、开始/结束 UTC、stopwatch ticks/频率、退出码、stdout 和 stderr。外层 wall 从 Process.Start 前到退出及管道读取完成，外部记录文件发布随后进行。它包含子阶段，不与嵌套 RTT、单会话周期或角色 CPU 混加。[命令证据目录](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/execution)

01 的冻结分析器在 `-I` 下未加入自身目录，导入 continue_series 失败。原失败日志保留。02/05 使用外部 runpy 入口，校验同一脚本 SHA、只加入固定可信 R1 目录并保持原 argv、`__file__` 和隔离 flags。全部 15 个冻结脚本和运行控制 HEAD 保持原样。此适配得到独立审查。[入口适配记录](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/execution/ANALYZER_ENTRY_ADAPTATION.md)

另有两个早期独立只读支持调用没有完整外层计时。原件复核的工具观察 wall 为 354.222ms，quick 成本扫描为 168.4971ms，均 exit 0，开始/结束 UTC、部分独立 stdout/stderr 边界及 Python-only wall 未采。原记录保留，06/07 是另行记录的只读命令，没有回填这些缺项，也没有新增观察或资产覆盖。

独立成本数据首版的 candidate scope 文字误写为只含 E，且证据投影缺 arm。实际另含 F64 的 10.3018ms。该元数据错位以独立补充更正，原版、原数值及输入保持原样。[范围勘误](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/runtime_cost/CANDIDATE_SCOPE_CORRECTION.json)

## 唯一后续候选与结论边界

下一批仅可考虑原 `_connect` 完成路径这个瓶颈候选。E 五次约 25ms、F 一次约 10ms 支持对该有限范围继续定位。可删除或缩短的具体原步骤和预期收益尚未证明，需先在同一 socket、单次连接、原期限与原成功判定的合同内确认冗余等待，再提交最小候选。当前跨度不能全部视为可节省成本。

本批没有新增产品优化实现。F 的历史长尾与最慢 cold 尚未解释，O4 准入失败、E 的已知 PT 缺陷、复杂三维资产能力和模型实际消费质量分别保留原状态。新增模型消费答案为 0，token/费用未测，历史 US$0.02 预留保留。

最终回执以 `PERF020_O5AR1_COMPLETE` 报告恢复诊断完成及上述限制，明确释放 `PERF020-O5AR1-WINDOW-01`，随后结束本批等待主线深度复核。
