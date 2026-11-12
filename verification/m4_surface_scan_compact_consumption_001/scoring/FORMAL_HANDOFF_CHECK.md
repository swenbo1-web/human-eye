# 九格匿名交接的非评分核对

本次仅核最终字节、归属、原归档和匿名管理投影。正式质量评分为 0，分组质量、成本和 usage 分析为 0。

九格固定映射、冻结计划和匿名 ID 一一对应。九份最终答案与原 consumer.final、PUBLIC_FINAL、CLI final 和最后一条原始模型消息的 UTF-8 字节一致。执行状态保留 completed 7、failed 2，最终答案文件 present 9。两条 failed 仍保留原 CLI 重连/网络解码错误事件，后续 exit 0、turn completed 和最终文件完整不覆盖其 valid_completion=false。

全部 owner 正常或错误响应、请求参数、原生代码、重复尝试及消费者 started/completed 工具事件与原件逐项对应。旧详细与新紧凑表示均完整保留，未按业务字段名清除 group、usage、时间、路径或 unknown。来源和关闭记录使用原生产者证据，未把未知项改为通过。

初版 handoff_01 的两个 consumer error 管理信封包含 perf_ns。按根授权保留初版、PROVENANCE 和首 ZIP，另生成 quality/public。仅从 INDEX.answers[*].consumer_execution_errors[*] 移除这两个 perf_ns；该冻结信封实际仅有 event/perf_ns，未发现其他同层管理时间字段。错误 event/message 完整。其他 41 个文件逐字不变，INDEX 其余结构一致，重插原值可恢复原 INDEX 编码。

quality/ADMIN_REDACTION.json 记录原新 INDEX、每条精确 pointer/value hash 和最终 42 文件清单。最终公开树 canonical SHA256 为 `03c566a5438fad7454b1d9f91157c3627a5fbd3740856972b61a353338fec101`。

本次通过 1317 项检查，核 807 个原归档文件、27 次 owner 尝试和 54 条消费者工具事件。数量表示交接核对工作量，实验分母仍为九格。

业务内容可能透露路线，匿名性有限。后台完整响应、CLI 完整事件和实际模型输入完整性保留各自证明范围。本检查没有调用 scorer、没有判定答案正确性，也没有生成新的模型、Blender、产品或 API 运行。

原冻结打包脚本和全部原运行证据保持原字节。Agent Learning 仍未绑定，host epoch 5。
