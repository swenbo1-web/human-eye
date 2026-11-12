# 原期限与数值预算独立复算

保存原件的检查通过。`CONTRACT_CHECK.json` 将原始 turn.completed usage、单格起止、阶段台账和数值预算分开复算，共 151 项通过。

完整单格原期限从输入核验前开始，加 570 秒。相同值逐一对应 ACTOR_LAUNCH、ACTOR_CONFIG、ENDPOINT、native CONFIG、SESSION、READY、WORKER_CLOSED、QA 及公开原生调用回执。消费者原期限从其 started 加 450 秒，actor 启动截止为 prepare_started 加 40 秒并受完整单格原截止约束。全部实际完成和关闭均在这些原期限内。

| 格 | 工具尝试 | 物理请求含 close | native execute | actor 回包预算字节 | 最大执行代码 UTF-8 字节 |
|---|---:|---:|---:|---:|---:|
| grc01 | 3 | 6 | 5 | 6,017 | 4,434 |
| grc02 | 1 | 4 | 3 | 7,997 | 88,728 |
| grc03 | 2 | 4 | 3 | 9,898 | 88,728 |
| grc04 | 3 | 6 | 5 | 3,253 | 5,631 |
| grc05 | 3 | 6 | 5 | 4,471 | 4,518 |
| grc06 | 1 | 4 | 3 | 7,997 | 88,728 |

工具尝试 13 次、执行代码请求 24 次、含 close 的物理请求 30 次。每格分别核 32 次尝试、128 个物理请求、30 秒实际工具窗口、累计 1 MiB 业务回包及单代码 256 KiB。错误回包进入同一累计字节账本，修正没有重开单格。实际代码字节按 worker 的原始 script_sha256 对应 UTF-8 源码核对，磁盘换行后的文件长度另外保留。

Native helper 的 128 次 guard 作用于非 close 分支，close 分支先行接受。本批包含 close 的真实序列也分别低于 128。关闭日志最后一行的 unknown 原样保留，关闭回包、WORKER_CLOSED 和 owner reap 分别提供实际退出证据。

产品配置暴露局部 request_budget_s=30 和 host timeout=30，trace 给出 cooperative 服务范围及实际时长。外层 chain、Peer 剩余工具窗口和 native 原截止分别核验。原始记录未暴露全部内部绝对 deadline。检查结论限于本批实际窗口和已保存传播字段。

首次 checker 将早期参数拒绝也要求具有 service budget annotation。grc03 的无效 nearest_witness 请求在 service.observe 之前拒绝，仅记录 wire_encode 与 stdio_write，返回 executed=false、not_executed，host 执行为零。初版 checker 和结果保存在 `check_history/initial/`。最终检查分别核服务进入和早拒绝，保留两者实际外层时界。

最终累计 input 加 output 为 N 84,248、P 50,269。完整单格中位为 N 64.3644234 秒、P 25.2085744 秒，冻结门限通过。cached input 与 reasoning output 子项单列，费用和未暴露归因保持未测。
