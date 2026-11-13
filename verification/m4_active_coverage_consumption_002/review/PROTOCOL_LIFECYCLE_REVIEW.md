# 第二批协议与实际进程终态复核

新批六槽均正式 completed，六个 fresh CLI thread 各有真实 actor 与 stdio 来源、创建时间及持有句柄退出证据。188 项新冻结来源与旧 176 项来源 SHA 保持一致，前后 13 项指针检查一致。

正式工具回执分类为 14 个 success、0 个 tool_error。请求名、完整参数、RPC ID、正文全部字段与真实 CLI completed 事件逐项一致。stdout 原字节及双层 ZIP 的哈希、成员和复制原件均通过核对。六槽 CLI error 与 retry observation 均为零。

两路本地各有一次真实 actor ValueError，经 fake CLI 保留 failed/null/原正文投影后匹配为 tool_error，再执行 42 恢复。两路均普通 EOF，实际 thin exit 为 0，EXIT 回执明确且持有进程清理没有请求 kill。正式六槽本轮没有工具业务错误，错误恢复证据按上述本地范围报告。

正式 CLI 与 actor 各自 exit 为 0。六个实际 stdio runtime 的持有句柄均证实 exit 为 1 并已关闭，EXIT 文件的 EOF 状态保持 unknown。退出原因未测，原完成门依据已证终态接受这些槽位。

原第一批保持 4 完成、2 失败，新批独立为 6 完成。准备说明已更正，旧 run_batch 本来包含 actual_CLI_processes，两个批次的 RUN_RESULT 均实记 6。launcher 删除的是冗余复制字段。

本次复核只读原件，新增模型、本地会话、矩阵、工具代码和渲染调用均为零。provider 内部请求、费用及 resolved effort 保持未测。时间与用量比较由独立成本账本处理。

逐项生命周期、绑定和原件 SHA 见 [JSON 复核](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002/review/PROTOCOL_LIFECYCLE_REVIEW.json)。计数说明原件见 [准备说明更正](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_002/PREPARATION_NOTE_CORRECTION.json)。
