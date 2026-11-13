# 连续工程原件生命周期复核

2026-11-13。离线原件复核通过。原工程资格整体仍为未通过。新增 Blender、产品、模型和 API 运行均为零。

本复核共 654 项检查，绑定 356 份输入。原始 episode 和冻结准备文件保持原件。

| 组 | 实际业务 | 实际薄客户端 | 资格主分类 | 后续未运行 | 完整秒 | 关闭 |
| --- | --- | --- | --- | --- | --- | --- |
| N | 3 | 3 | passed | 0 | 2.2573118 | confirmed |
| C | 1 | 1 | validation_failed | 2 | 3.9755011 | confirmed |

N 的三个独立薄客户端均正常 EOF 退出，四个真实客户端 EXIT 都声明 backend_close_requested=false。逐次完整 stdio、逐消息附件和 owner 业务回执一致。N 三轮 owner、Blender PID、工作 namespace、内存标记及对象身份持续，编辑 barrier 后可读到登记姿态。

C BASE 的实际业务响应成功，薄客户端正常退出，owner 已结束 BASE。随后的资格检查因快照字段合同不一致抛出 AssertionError，原主分类继续保留 validation_failed。REPEAT、EDIT 没有启动，未将未运行视为通过。

C 关闭时未尝试 EDIT，初末快照及 worker initial/accepted/final fingerprint 相同。产品 launcher、真实 runtime 和 Blender 都有独立退出及回收确认。两组均在原绝对 590 秒内完成原结果文件关闭和终态计时发布。

每轮包含两个 metadata RPC、一个 initialized 通知和一个业务请求。N 完成三轮，C 仅完成一轮传输边界。本次不存在完整 C 连续缓存资格，也没有模型续接或模型 usage 的实测。

worker 通用关闭事件的 status=unknown 保留，同时单列真实关闭响应、worker closed 文件、launcher wait/reap 以及适用的 runtime retained-handle 退出证明。原件证明范围限已记录的身份和终态保护。

复核脚本只读输入，仅在本 postrun/lifecycle 目录写派生结果。完整逐项断言、输入字节和 SHA256 见 RESULTS.json。
