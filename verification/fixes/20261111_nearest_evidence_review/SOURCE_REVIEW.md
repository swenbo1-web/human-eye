M1-NEAREST-EVIDENCE-001 来源与证据复核通过，未发现阻断。固定提交 107641ec19919d56aa843c1949261590fc338148；本轮只读静态核查，未运行产品测试、模型或 Blender。

| 项目 | 本轮独立核查 |
|---|---|
| 新封存 | 230 成员 SHA256、字节数和固定 Git blob 一致；INDEX/SEAL 与指定 pin 一致 |
| 同版源码 | 两版初次及最终共 4 份物理副本各 137 源匹配 Git；候选只改 live_service、live_spatial_mcp、task_query，其余 134 份不变 |
| 旧采样保护 | 原 27 会话对应 2396 正式封存成员及 37 输入副本字节未变；固定 fa23496 Git 绑定保留 |
| 测试变量 | 每版 4 测试、15 fixture、26 既有引用材料及 runner 摘要一致；两版载入测试按核验原字节 compile |
| 产品加载 | runner 把核验 blobs 交给原 verified_source_loader；结束 guard 为 true，59 个模块有加载记录，均属该源清单 |
| 原事实比较 | 9 组/11 直接记录与 18 入口记录的原核心、measurements、diagnostics、packet_work 和调用计数一致 |
| 场景身份 | 18/18 入口 capture binding 一致；scene_revision、fingerprint、document_epoch、directory、host source 和 instance 信息完整保留 |
| 历史失败 | 两版首轮 50 项中的相同 state.json 缺失错误保留；compare_01 重复归一化摘要导致的首失败及旧比较器保留 |

归一化仅删除结果根层的两个新增字段和 trace_id，并在逐项核对各版 runtime_source_sha256 后替换该字段。没有删除或模糊化其他绑定字段。新增证据逐项对应原获胜 measurement；热命中从同绑定的冷记录确认来源。

两版各计 capture 18、pair 24、kernel 24、rank 16、nearest 20、closed-solid 0。这是保存的有限记录及本轮静态重算，不能扩展为模型消费收益或完整任务性能结论。

作者最终日志为每版 49/49，本轮未独立重跑。实际 source_kind 为 unregistered_runtime，证明范围是源码执行、fake RNA 和真实几何内核；隔离安装、默认入口、真实 Blender 和模型收益均未验收。59 个加载记录不意味着 137 源全部执行；fixture 的文件摘要核查也不升级为每个辅助模块的字节执行证明。

完整结果：SOURCE_REVIEW.json。复核脚本：CHECK_SOURCE.py。
