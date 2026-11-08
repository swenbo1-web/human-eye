# M1-NAME-NEAREST-001 独立复核

接受固定候选 `24bfe492c4888caf1d989ddb22f36e5752829d46`，交付提交 `3d6c6e58338836b4bbae855cff490f54e4fd722e`。名称可在原 nearest 采集内解析，省去前置 AABB/目录请求的需求；模型是否实际少调用、完整任务是否更省，交给一次 RUN005 对照，不由工程验收代替。

根逐字节核对：相对固定 `88c977b` 共 395 个 Git 文件变化＝6 个产品源、1 个相关测试源、388 个新增证据。394 个索引成员共 10,906,847 字节与 Git、磁盘全部一致。独立枚举 131 份产品源码并重算现有 canonical 规则，摘要为 `74263d8b18aec48fac21e3c3b25e26c890739c6b697503a9f6b91acf7c30c0e3`。两次离线的 engine 快照和各 135 成员执行 ZIP 均使用同一产品字节；实际测试字节另行核对。根 ZIP 核查首遍错误使用后缀匹配，碰到根/package 同名文件后停止，改为精确归档前缀通过；没有产品执行或变更。

`/root/tc1_geometry_review` 独立审了六源及测试差异：query.objects 恰一已有 name/id 选择器，与旧顶层 focal_id 互斥，形状和冲突在宿主读取前拒绝。名称在原锁、主线程与当前 scene.objects 目录中精确匹配；无模糊匹配、全局 bpy.data 兜底、默认首项或名称缓存。connector/service 核对同一返回包的选择器匹配及 focal_id，再进入原 nearest 汇总。只有一个 connector request，期限、geometry、exact ranking、pruning 和末尾 coherence 逻辑保持。描述 1422 UTF-8 字节，低于旧 1453；这是接口改善，不等于模型实际输入 token 下降。

作者离线执行：同 23 方法跑两次，共 46 次方法执行。首遍 19 通过、2 失败、2 错误，原件保留；两项逻辑 ID/实例 ID 测试假设错误和旧 fake-RNA 字段缺失修正后，第二遍 23/23 通过，0 失败、错误、跳过。产品字节未因测试失败而改变。测试覆盖 name/id/legacy 的 complete、partial、unknown、全部并列等价，缺名/歧义/冲突、替换和改名、错包绑定、实际采集及既有来源/期限。fake-RNA 歧义覆盖不扩大为 linked 来源支持。根和子审未重复执行作者测试或无关矩阵。

`/root/approval_gaps` 独立解析实际原件：7 组公开 stdio 帧、4 组产品 socket、setup/close、5 份 worker SCRIPT 及事件哈希、PROFILE、bootstrap 和 owner receipts。1 session、6 RPC＝计数准备 1＋公开观察 4＋close 1；四次为 name、legacy、missing、name 恢复。三次成功原始结果仅 trace_id 不同，完整返回 5 个零距离并列目标；missing 的 isError、acquisition_selector_not_found、unknown、不执行、不 verified、不自动重试保留。无前置 AABB/task/scene 请求。id-selector 真实 RPC 未跑，以离线三入口等价覆盖，不能扩大真实测试分母。

实际 `_objects=[2,2,1,2]`、`_capture=[1,1,0,1]`：成功时原初始目录加末尾 coherence 复查，缺名在初始目录后拒绝，未声称总共只遍历一次。生产 bootstrap 有 57 个已加载模块的 guard witness，generation 匹配该 131 源；产品脚本与 worker 执行事件哈希对应，无捕获包或合成结果旁路。Native33928、stdio2004、controller19484 有各自 owner exit0/reap 原件。worker close-event unknown 保持，独立 close response 与 owner receipt 证明关闭。原期限、初末几何、资产/helper 字节保持，source drift 为空。

成本独立复核：控制 TX/RX 4997/194B、产品 socket 15217/25641B、stdio 1283/29643B 分属不同边界；外层 2.5973815s 和 controller 2.3107376s 嵌套，不能相加、扣除计量开销或用冷暖差宣称净收益。prepare 5.2250113s 单列。根从 read_thread 完成 metadata 补得作者完整回合 2,675,179ms（turn 01a1ba85-f746-78f0-a3c8-652171ab5f16），与 QA 秒数不同。作者 token/费用未测。本轮根/独立子审新增实际测试、模型、Blender、RPC、API 均为 0。

无必要再开名称候选。下一批固定此产品源和已接受 `d2ecb396` 协作计量补丁，仅跑原四题 N/P 各一次。题面/原生能力/模型/预算/顺序不变，不提前提供 ID 或增加教程。先独立判断答案与证据，再合并完整成本；协作 usage 未暴露则继续 unknown。Google 付费、竞争分支、原资产及正式默认配置保持原边界。
