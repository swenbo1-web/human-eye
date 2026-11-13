# 图片消费001：独立生命周期复核

固定作者提交 `a54ad3a9bf738e8f9b5a75c71c29b0a6b105a6ff`。独立脚本只读31个原始记录/源码文件，61项检查通过；没有运行作者验证器，没有启动CLI、actor、stdio、模型、光栅或Blender，也没有查询/终止当前进程。来源摘要和全部检查保存在 INPUTS.json、RESULTS.json。

结论：**图片传输与已有回答不因缺少stdio EXIT而作废；CLI与actor退出可确认，stdio实际退出时间、退出码和正常EOF仍为unknown。** 这两次资格无需补跑。下一正式任务可直接准备，但应在同一准备中补实际thin进程退出观测和完整终态字段接线，避免把unknown继续混入完整任务时间验收。

## 本轮原件实际证明了什么

| 项目 | N | P |
|---|---:|---:|
| CLI PID / actor PID | 1688 / 12576 | 12016 / 11232 |
| stdio STARTED PID | 24020 | 23948 |
| CLI/actor退出码 | 都为0 | 都为0 |
| CLI/actor原Popen句柄回收 | confirmed，未请求kill | confirmed，未请求kill |
| CLI读取线程与actor服务线程 | 已停止 | 已停止 |
| 实际completed工具调用 | 2 | 1 |
| 正常完成事件 | 1 | 1 |
| 保留的item.error警告 | 2 | 2 |
| 最终回答→CLI退出 | 2.6834623s | 3.4978962s |
| 完整已记录外层时界 | 27.9140274s | 15.9587049s |
| stdio EXIT | 缺失 | 缺失 |
| 事后PID不存在记录距该路结束 | 316.6714221s | 300.7121501s |

两路实际工具completed事件都先于最终回答，最终回答先于turn.completed与CLI退出。CLI最终文本与PUBLIC_FINAL一致，两个真实线程UUID不同且没有resume。两条警告是开发中功能提示与模型metadata回退；无顶层error/turn.failed，后续正常完成。警告未删除，也未将服务端resolved model推断为已知。

两路原始绝对450秒期限在actor endpoint、consumer和outer完全相同；已记录的CLI、actor、归档、回读及RESULT发布都在该期限内。不能把这个时界再解释成“全部thin子进程在此时已确认终止”：当时没有它的原句柄观测。

EXIT_OBSERVATION.json只支持约5分钟后查询时旧PID不存在。它不能给出历史退出码、退出时刻、正常EOF或关停原因。旧记录的bridge_cleanup.confirmed=null及receipt_status=unknown保持正确。

本地synthetic N/P确有匹配STARTED的正常EXIT，实际PID分别328与6972。fake_cli主动关闭stdin并wait，因此它只证明主动EOF那条分支；不能替代真实Codex宿主的退出行为。

## 为什么会出现unknown

以下行号相对于实施checkout：

- `verification/native_plugin_complex_003/reused/stdio_attach.py:50` 写STARTED，`:53–66` 读stdio直到EOF，`:67–71` 在finally写EXIT。正常EOF或普通Python异常会进入finally；外部强制终止或写文件本身失败不保证留下此文件。当前没有证据可唯一确定是哪种原因，不能直接断言CLI强杀。
- `verification/m4_surface_scan_compact_consumption_001/runtime/consumer_transport.py:20–45` 的wait_bridge_closed实际是一次文件扫描，既不等待，也不持有stdio进程句柄。缺EXIT故返回null，语义本身诚实。
- `verification/m4_active_image_consumption_001/consumer.py:345–353` 先回收持有的CLI进程、停止读取线程，再扫描thin回执。`:359–361` 使用`confirmed is not False`，所以unknown也允许safe_to_continue；旁边scope明确只覆盖consumer/readers。
- `verification/m4_active_image_consumption_001/driver.py:101–103` 的outer_valid_completion只要求consumer_valid_completion、owner_close、owner_process_cleanup和无错误。它没有纳入`:167`已保存的consumer_safe_to_continue。`:208–212`仅把consumer不安全用于停止后续槽，因此在未来异常情况下可以出现“当前槽completed，但余项停止”的不一致。本轮两路consumer实际回收均为true，没有触发这个潜在错误。
- `verification/m4_active_image_consumption_001/fake_cli.py:64–68` 显式关闭thin stdin并wait；真实CLI流程没有由测试壳持有这份stdin或Popen，因此本地模拟成功不能关闭此观测缺口。

缺陷是测试壳的生命周期观测和状态汇总不完整，不是已交付图片丢失、模型答错或需要重新做视觉资格的证据。

## 可复用的最小处理

已有代码可复用，无需新进程管理服务：

`verification/m1_task_entry_001_eval/preflight_client.py:27–118` 的 `_windows_runtime_proof(process,runtime_pid,deadline_ns)` 已使用只读OpenProcess（SYNCHRONIZE+QUERY_LIMITED_INFORMATION）、GetProcessTimes与最多4条父边的Toolhelp快照，将实际runtime绑定到持有Popen的launcher，并返回仍持有的原进程handle。`:121–141` 的 `_runtime_exit(handle)` 用该handle读取退出状态/退出码并关闭句柄。

下一消费loop可在STARTED第一次出现时，以实际CLI Popen及记录的stdio PID调用同类逻辑，核创建时间/实际base镜像并保留handle；CLI结束后用同handle有界等待，随后读取exit code和Close。不重新根据结束后的裸PID找进程，不发送终止信号，不把正常EOF当作必需条件。

旧proof里`before_stdin=True`不适用于这个调用点，项目旧复核也已有相关erratum。这里必须按真实时序标为`after_stdio_STARTED`，记录观察时刻，不照抄错误前置字段。新增观测和末尾等待计入两路同一完整时界，仍受原绝对期限约束。

状态建议拆为内容完成、CLI/owner回收、thin实际退出、thin正常EOF四项。outer完整准入纳入已有consumer_safe_to_continue及thin实际退出观察；EOF unknown不等于进程仍活着，也不应机械要求EOF成功。stdio确定已退出即使EOF记录缺失，也可以继续；退出方式仍unknown。

若实际thin handle无法绑定，或有界等待后仍不能确认退出，本槽图片/回答/已耗成本继续保留，完整终态记unknown并停后续模型槽，不重跑补样。这样不会把不能核算的残留进程混进下一配对。准备期用本地正常EOF和模拟强制退出两种方式检查观测逻辑即可；不为生命周期另增加Pro资格，也不重跑本轮两张图片。

本轮未测试任何新的观测实现，也未声称已修复该缺口。以上是下一正式消费准备中的最小实现建议。
