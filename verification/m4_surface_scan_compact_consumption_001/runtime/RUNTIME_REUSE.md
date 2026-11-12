# 九格运行链的离线准备

新运行链复用上一批 `m4_surface_scan_consumption_001` 的 actor、driver、transport 与 formal 外层。每份复制前原字节均核对原提交 `e5c8afaf`，保存在 `.before`，对应差异和完整摘要见 `RUNTIME_REUSE.json`。

外部 N、O、C 保留在私有格归属中。内部 actor/transport 继续使用 N/P 两个能力配置，O 与 C 各自选择其固定安装和真实普通声明。N 只使用共同依赖解释器，实际配置的 entry、install_root 和 source 均为空。九格顺序固定为 N1/O1/C1、O2/C2/N2、C3/N3/O3。

transport 唯一功能改动是本批独立 workspace slug。模型设置、Pro 接点、环境隔离、thin client 生命周期、原最终消息字节和 usage 记录保持原链。actor 的归属证明明确 `before_stdin=false`，补充 initial QA、metadata 结束时界和 `before_consumer_business=true`，实际证明位于初始 QA 与元数据之后、消费者业务之前。

答题完成和执行安全分开判断。缺最终答案、一般 turn.failed、非零模型退出或本格超时保留为本格失败。执行边界可靠、owned 关闭确认时，后续固定格继续。真实传输/会计错误、未知动作状态、native/product poison、隔离偏离、缺上下文启动、认证/额度/服务不可用或关闭不明会停止尾部，完整九格分母继续保留。

最终 18 个 runtime 方法与 12 个 bridge 方法通过。所有真实进程启动在测试主体中被阻止，仅使用合成进程、owner、消息和时钟。前一轮 17 方法的干净运行另存，最终方法数按 18 计。测试覆盖缺 final 与 nonzero/turn.failed 后继续九格、450 秒和最终 570 秒逾期单格记录、协议或 provider 失败停止、未知 mutation/poison/关闭不明、精确组映射、独立空 workspace、两版声明与返回原样透传、字节与图像预算、归属证明标签及关闭次序。

最终业务会计和 owned 清理完成之后由 `CELL_FINAL_TIMING` 采样完整结束点。计时回执自身发布另记录，旧 `total_task_wall_ns` 继续标为 prefix。算法或答案质量由后续匿名审核判定，此准备阶段没有运行正式消费者或评分正式结果。

本子任务只新增本批 runtime 材料，实际 Blender、产品服务、模型消费者和推理 API 运行均为零。Agent Learning 当前未绑定，host epoch 为 5，任务记录尚待宿主重连。
