# PERF-020-O5-A-R1 静态恢复准备

## 当前状态

本批静态准备已完成，运行验证状态为 `UNRUN`。Python 执行、编译、测试、产品观察、Blender、性能采样及新 probe 均为 0。当前独占窗口属于 M3 的 `PERF030-002-WINDOW-01`，R1 等待主线另行授窗。

原 O5-A 的 111 份封存文件及原报告保持原身份。原 `SUMMARY` 仍为 failed，实际完成 10/60，原有效账本仍为 0，后五项、50 次仍未运行。R1 已将这些原件接为离线复核输入，修订账本的运行结果尚未产生。

工作树 130 个产品文件及 E 隔离安装仍全等于接受 E，F 私有安装仍匹配原 130 个源文件。E 产品提交为 `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15`，F 比较对象仍为 `b644c79430ced0c710dc9c8c27b2c72598dfe63f`。O4 原准入判定继续保留。

## QA 修改

### 时界账本

服务事件按真实时间戳和已绑定的请求归属分成 preflush、postflush。原响应区间的起止保持原值，写出后的操作独立报告。跨 flush、重叠、外来 owner、缺少归属上界或边界时序不明均有明确拒绝原因。

归属上界使用已记录的下一次成功读取 stamp，末次可用最终服务自采样 stamp。两者均不能补出真实 readline 调用入口、EOF、完整 trace 尾段终点及尾段 CPU，这些字段保留未测。审计调用跨度仅证明尝试，成功持久化需要单独证据。[修订账本](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/harness/diagnostic_ledger.py)

### 原始成本与状态

分析器先保留实际记录的请求尝试、RTT、服务和宿主时界、生命周期资源与字节，再尝试修订账本。原 failed 状态、原有效账本 0、修订离线状态和未运行分母分别列出。缺少结果发布时保留 journal 可恢复的请求前缀，发送状态与精确数量缺证时列为未知。缺失的清理记录及不可用的内存字段保持未知。[恢复分析器](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/analyze_recovery.py)

### 原采集路径

九份采集与生命周期脚本，以及原 PREREGISTRATION、DIAGNOSTIC_PLAN，均按原字节复制到恢复目录。原采集器要求输出位于其自身目录下的 cost，因此用相同字节的新路径保持该约束，并给新结果提供排他目录。原 111 文件目录继续保持原状。

复制的旧计划承载原输入和采集绑定。当前 R1 的权限、控制版本与恢复约束由新 R1_PLAN、RECOVERY_FREEZE 及未来真实授窗证据明确记录。[副本身份清单](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/COLLECTOR_COPIES.json)

## 定向组合测试接线

已接线的十项定向测试将执行固定 E 的真正 `run_stdio_mcp_server`、MCP server、wire 及 MCP/service 两层 request_trace 和 telemetry context。业务操作与审计 writer 使用受控假对象，输入输出使用 StringIO。wire 包装先调用原写出和 flush，再保留同一请求事件列表，让原 trace context 退出后追加审计。

预定覆盖正常回复、错误业务回复、失败 writer、写出后非 audit 事件、外来 owner、跨 flush、边界零时长、重叠、超出下一成功读取上界及缺少归属上界。负例按具体拒绝原因验收。原错误合同应复现包含失败，修订合同应正确分段。

测试中的 read-entry 顺序记录只用于检验真实嵌套，不补入旧采集数据。假工具帧和 writer 尝试按实际测试活动计数。组合测试与旧十条复核均须在未来授窗后执行，当前没有通过记录。[组合测试源](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/checks/real_context_combination.py)

## 有界续接

薄控制器复用原 `run_one`、完成核验及生命周期代码，只把 QA 根目录指向字节相同的恢复副本和修订账本。新控制 HEAD 按实际 Git 记录进入恢复冻结，与原执行 HEAD `d67ff7f735461b284088cc1db4fa43f40ea589ab`、原交付 HEAD `67f904ae5492ce46329da9720701426206e0d94d` 分别保留。

未来调度项只能是原冻结中的以下五项，所有原 nonce、每项十个请求及六个背景控制原样保留。

| 顺序 | 会话 |
| --- | --- |
| 1 | 8-F |
| 2 | 64-F |
| 3 | 64-E |
| 4 | 256-E |
| 5 | 256-F |

原十条被排除出调度。续段最多 5 个 Blender 会话、50 次观察、55 次 stdio、50 次物理请求。加原阶段后累计上限 60。新输出目录排他创建，失败停止，未知尝试保留分母。[续接控制器](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/continue_series.py)

执行前须同时满足真实主线授窗回执、共享 STATE 的 M2/线程/cycle/token 绑定，以及固定旧十条复核和真实组合测试的通过证据。当前 `window_status=pending`、grant 为空。未来由 root 从实际授窗回执保存证据，无需用户另建审批表单。命令接线见 [DEFERRED_CHECKS.json](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/DEFERRED_CHECKS.json)。

## 静态审查与限制

独立静态核对确认旧 111 文件的长度、SHA 和完整目录身份，原五个剩余 nonce 与顺序匹配，原剩余输出目录均不存在。十一份采集与输入副本逐字节匹配，E/F 各 130 源及活动 E 130 源均匹配。[静态身份记录](D:/hefe/verification/fixes/20261106_perf020_o5a_r1/review/STATIC_IDENTITY.json)

准备阶段修正了动态 started/passed 状态影响账本重算、journal 坏尾行吞掉已知前缀、缺清理记录和缺分母等源级问题。另保留一次 PowerShell 路径分隔符导致的旧目录排除误报，修正比较后确认原 111 文件身份。相关首稿及记录保留在恢复目录。

当前结论限于源级准备。Python 语法、真实组合测试、旧十条修订离线复核、剩余五会话和完整 E/F 时界归因均待授窗。模型消费答案为 0，token 和费用未测，历史 US$0.02 预留保持原账本。

本次以 `PERF020_O5AR1_READY` 回报固定控制版本、QA 摘要与恢复冻结，确认接收后结束准备阶段，等待主线授窗。共享协调记录继续由主线写入。
