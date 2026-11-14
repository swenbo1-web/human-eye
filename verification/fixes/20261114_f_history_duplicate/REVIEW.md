# 历史 F/E 重复回复与当前任务续推

2026-11-14。旧 PERF-020-O4 审核回复再次进入实施聊天，打断 REGION-ANCHORS-001。结论：维持旧 F 不准入；历史 E 恢复真实完成，既有独立审核已关闭。没有发现需要阻塞当前 anchors 的新缺陷，沿原计划续推，保留现有编辑及预算。

根本轮实际读取历史报告、原 FREEZE/SUMMARY、回退记录，以及 20261106_perf020_o4_independent、20261107_f_recheck、20261109_f_history_confirmation 三份既有审核，核对关键摘要。最后一份目录名为 11/09、正文记录日期为 11/10。没有将旧审核中的 CURRENT 源码当作本日源码。

本轮独立子审核分两项：门限审核以 Fraction 离线复算 SUMMARY 的 30 runs / 300 RTT，核对 received-sent、次序与来源，结果仍为原 7/12、机制暖 7/9、冷 1/3、十请求和 3/3；回退审核从 Git 读取 E/F/恢复各 130 源并比较原始字节。没有执行历史评分器、产品、Blender、新性能采样或模型调用。

四项原失败保留：8 档 cold p95 回退 8.7474 ms > 2.157315；64 档 cold 中位回退 1.2782 ms > 1；256 档 warm pose p95 回退 8.2753 ms > 2；warm geometry p95 回退 9.2542 ms > 2。暖中位收益不能覆盖这些失败。

E `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15` 与历史恢复 `9fc576a5216176b459586ce95a4f9e34a313da20` 的 130 源逐字节相等，摘要为 `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163`。旧 F `b644c79430ced0c710dc9c8c27b2c72598dfe63f` 摘要为 `30b28aab341dcec6d7504a95a15089acda506af0a0c11bd14ffd6644ecdb258d`。

当前实施 HEAD `efe7f77aabdab4f8de47fdb4f8714cb25f301503` 以 E 为祖先，F 与历史恢复提交均不是其祖先；恢复与当前的 merge-base 为 E。当前是从已接受 E 分叉后的后续实现，不能再次用旧 E 覆盖。读取时四份 anchors 产品文件有未提交编辑，未改动它们。

根实际核对的关键 SHA256：

- 历史报告：`1b1f4c831ebefb4f965c532728b169a983d81fde4c8c41f0776ddfe97434ccb4`
- 正式 FREEZE：`0d81a37e894f4902407a20c71c6b9c12d6c05c9aa7ff23a5f3e3aa8b5bae354f`
- SUMMARY：`4def42eca7c0ee521600487f4d912b7af6d8ea0e8b24ac9c3a890cb4502840f0`
- 原根独立审核：`aa7ef72e5795b08aa0ac0ff893bd390ebf253fd34b29b98ab6a2b9f54f7ba6be`
- 后续历史确认：`77a9171ed0d071c8f13604dab5fbbf693ccaf40438b823521d3140c4b31871af`
- 当前 anchors 计划：`209958cbefd346c7cbae5e38cd8c24b2c74e5c0e19ef05fde3532bd1cec59d8e`

处置：按 cycle=PERF-020-O4 + candidate=b644c794 + 原 FREEZE 识别此已关闭事项。相同历史回复只引用既有结论，不重开实验或暂停当前任务；出现新证据或用户明确要求重新研究时再处理。REGION-ANCHORS-001 沿原计划完成并回报 READY，不新建任务、不重置已发生的调用分母。
