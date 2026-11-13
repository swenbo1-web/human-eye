# FIX1 capture 读取阶段错误与离线修复候选

2026-11-13。原 FIX1 唯一 C episode 在 BASE 工具成功返回及薄客户端正常退出后，被在线 capture reader 的 FileNotFoundError 中止。原失败和 REPEAT、EDIT 两轮未运行保持。此目录仅新增离线诊断与未应用 reader 候选，新增 live、Blender、模型及 API 调用均为零。

## 根因与输入可见时序

冻结 read_capture 将 WIRE/INDEX.json 当作每次 RPC 结束就存在的在线输入。实际 wire_meter.finish_rpc 只在内存中记录统计，WIRE 由 worker 主循环结束后的 meter.flush 才发布。FIX1 的离线原件已全部关闭，完整归档的存在掩盖了在线阶段缺项。

本次按原 worker 源码和实际失败输入复现该错误。pose_native_metered.py 的固定顺序如下。

| 步骤 | 源行 | 原动作 |
| --- | --- | --- |
| 保存执行脚本 | 319 | SCRIPT.py 的 write_text 完成关闭 |
| 保存输出 | 326 | stdout.txt、stderr.txt 的 write_text 完成关闭 |
| 形成终态保护事件 | 331 | 记录脚本 SHA、原 stdout/stderr 字节数、图像与几何保护 |
| 发布事件 | 345–346 | finish_rpc 统计，append 事件并 flush/fsync |
| 发送原生响应 | 347–348 | 编码并 sendall |
| 发布 WIRE | 365 | worker 主循环结束后 meter.flush |

因此，当工程 runner 已收到本次成功业务返回时，匹配的 call 文件和完成事件已可读取。WIRE 的传输封存与 WORKER_CLOSED 属于结束阶段材料。这个阶段合同应进入回归，已关闭 fixture 的文件全集不能代表在线可见文件。

## 一个未应用 reader 候选

read_capture_candidate.py 只读取 WORKER_EVENTS.jsonl 及不晚于当前序号的 call_N/SCRIPT.py、stdout.txt、stderr.txt。当前事件必须与调用方提供的实际 host_event 完全一致，并要求完成、无脚本错误、终态保护通过、零新图及渲染。

Windows write_text 的物理文件可能包含 CRLF。候选仅在原始 bytes 和精确 CRLF→LF 两个去重候选中，依据事件脚本 SHA 或原始输出字节数选择唯一值。它保留尾部换行，无法唯一重建时拒绝。逻辑输出还必须符合固定单 JSON 捕获信封。原始文件字节摘要、逻辑输出摘要和事件摘要分别保存。

当前 capture 的资源引用可以使用同一 worker 先前完成输出中已经记录的资源。id/revision、host source 和 document_epoch 保持绑定，同一 revision 内容变化会拒绝。当前 pose、资源顶点、面、单位和任务事实继续由唯一冻结 verify_c_turn 检查。

返回值保留原 capture 结构，wire_sources 为空，另给 capture_sources、evidence_phase 和 transport_confirmation。这些输入证明执行完成后的捕获内容，实际响应传输及 WIRE 发送确认仍需单独记录。候选未替换任何冻结源码。

MINIMAL_READER.diff 展示把 logical_bytes 和 reader 内联到现资格模块的最小差异。事实、来源几何适配和 sequence 验证仍由同一套活动函数承担。

## 阶段感知回归

测试环境硬拒绝任意 WIRE、WORKER_CLOSED、FINAL 和未来 call 文件读取，并将事件流截断到当前序号。原 reader 必然在 WIRE/INDEX.json 复现 FileNotFoundError。候选在相同限制下经实际 runner.verify_business 和唯一冻结 verify_c_turn 通过，禁止路径读取次数为零。

实际 FIX1 C BASE 的离线事实仍为 71 匹配、112 新 kernel、一次捕获。随后在限制解除后的单独审计中核对关闭后归档，逻辑 SCRIPT 字节与 WIRE 请求 code 完全一致，逻辑 stdout 字节与 WIRE 成功返回字符串完全一致，capture 解码、保留资源和来源序号也一致。这一后验对应不升级原在线失败。

旧已资格工程的 REPEAT 与 EDIT 零资源包也在同一阶段限制下回放，通过真实先前输出解析 24 份资源，分别核 71/72 匹配及 0/10 新 kernel。REPEAT fixture 只将历史 brief 请求标志合成为缺省，保留其实际响应、捕获和资源原件，该记录没有变成新的 live 样本。

反例覆盖脚本与输出文件改动、事件错误、终态保护、图像及渲染，以及保持输出长度的单位篡改。后者由唯一活动事实验证器按 capture_unit_scale 拒绝，字节数守卫没有被当作内容真实性的独立证明。精确文本重建还覆盖原串、CRLF→LF、缺少唯一匹配和缺少匹配。

最终七个离线方法通过，零 failure、零 error。首次六方法也通过，两份 PHASE_TEST 日志完整保留。REVIEW.json 保存阶段复现、实际 runner 事实、输入摘要、源码发布顺序和单独后验 WIRE 对应。

## 最小流程取舍与边界

在线资格可使用已经关闭的 call 文件与完成事件核对几何和来源，episode 关闭后再用 WIRE 做终态传输审计。该流程复用当前共享 worker，避免将尚未发布的归档作为在线依赖。输入缺项仍按错误处理，原绝对期限及业务次数继续由外层 runner 控制。

原 FIX1 episode 继续为 false，1 attempted、1 failed、2 not_run 保持。新 reader 没有真实工程验收。旧原生工程证据没有新增，本批没有补跑 C。模型连续记忆、实际多轮收益和 provider usage 范围也仍未实测。缺失 rich 来源字段保留原未知范围。
