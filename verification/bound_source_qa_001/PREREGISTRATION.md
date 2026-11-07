# BOUND-SOURCE-QA-001 冻结口径

固定 aaa7d881 / 131 源2ef16；原 far_second_degenerate 原件只读，现有 NativeSession 新建一个副本。只在私有进程内存测试，正常 RNA/API 改动，逐状态 finally 恢复全部原始坐标和 loop 索引，不保存 blend。worker 独立比对初末场景指纹及磁盘原件/副本哈希。

四份脚本预先生成、编译和摘要冻结；每状态一个 RPC，最多一次真实 `capture_nearest_candidates`，另一个 close，最多5 RPC。无 builder、第二 session、重试、性能、消费者或生产修改。原600秒窗口＋最多60秒清理；完整turn截止13:25Z（北京时间21:25）。未知执行不重放。

1. baseline：一次 build 信息，原始包络、首面和完整 native 坐标/索引 oracle。
2. 规范更新：后续面顶点3移至(0.25,0.25,0.25)，越旧 x=100 的盒；mesh.update + view_layer.update，当前候选应保留此对象。然后恢复。
3. NaN：仅一次正常 RNA 将顶点3的 x 置 NaN；记录拒绝/实际读回/归一化，正常更新，再看真实目录。若构造或更新被拒绝，本状态不调用 capture、不换手段。然后恢复。
4. index：仅一次正常 RNA 将 loop3.vertex_index 设为顶点数+7；同样记录拒绝/读回/更新，不二进制损坏、不裸指针、不换构造。安全读取后最多一次 capture；异常/崩溃保留未知，然后只清理。

native oracle 前后记录同图指针、frame、单位、evaluated身份、完整本地/世界坐标、面/loop索引及有限性。不会调用 mesh.validate 修复后再当原测试，也不使用生产算法产生自己的真值。NaN/Inf转换为明确JSON标签，不允许非标准JSON数值。QA全扫描不是生产gate。

正常更新被保留支持正常dirty路径，不能推广全部异常都安全。NaN/非法索引被保留或归一化需据实际读回判定；若有限盒且排除异常对象，只认采集来源前提缺口，不称为错误nearest complete。拒绝/不能构造也算实际结果。报告一个最小建议，不自动实施全场景扫描。

冻结 PLAN/FREEZE 绑定原件、二进制、131源、helper、controller与四份实际发送脚本。RPC原始TX/RX、worker SCRIPT/stdout/事件和最终恢复/清理全部保留。阶段journal仅写私有证据目录，帮助区分崩溃前实际进入到哪里；不从缺回执推断完成。
