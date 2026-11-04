# V21-REFACTOR-002：post-anchor 读取与证据交付候选

本批接通一个有限流程：已有公开锚点/core 选择 → 两个静态来源的正常事实读取 → 任务必要见证及全局范围视图 → 持久化完整证据 → 来源不变与关闭检查 → 发布 → 协议取证/交付。它没有替换 `region_witness_control.Control`，没有接真实模型，也不建立调度器、学习库、全域缓存或写域。001 的显式候选纯投影和旧 full/audit/scorer 语义保留。

## 请求与身份

`deformation_task_view.validate_task_spec` 接受版本化 `surface-deformation-task-request-v1`：`question`、公开 `thresholds.high/low`、恰好两个标签来源。每来源固定 `source_ref`（文件、mesh/rig、保存帧）、目录摘要、已选 anchor、core 半宽及 profile 摘要。`task_digest` 对完整规范 ASCII JSON 加单个 LF 计算 SHA-256，问题或阈值变化不会继续冒充同一任务。

`DeliverySession(task_spec, *, run_nonce, condition_id, deadline_ns, store, reader, prior_usage, ...)` 冻结上述任务、32 个小写十六进制字符的 nonce、条件和原绝对期限。`store` 是受信操作者配置的持久账本根，不是模型参数；实际槽位固定为 `store/task_sha256`。同槽位再次构造直接拒绝，换 request ID、nonce、条件或期限不会把已消耗状态清零。独立操作者擅自换一套账本根不在这个有限权限边界内；本候选没有声称提供跨所有目录的全局防重服务。

来源准备仍由真实 `QualifiedReader` 完成，构造它会启动两个普通 owned worker、各读取一个真实目录快照，并保留目录和启动成本。公开模型/操作者选择通过 `bind_selection` 固定。本适配器检查两个目录回执的标签、来源、目录/profile/anchor/core、原任务期限和已发生的每来源目录逻辑读取；从真实累计成本核对目录配额。此前的事实/补查消耗由受信上游的 `prior_usage` 传入，不能由模型自行宣称为零。尚未接通从目录选择到本入口的完整生产控制器。

## 预算和真实读取

适配器保持 `directories<=2 / facts<=4 / native_supplements<=1` 上限，但候选面最多四个是独立的面数限制。默认 `request(request_id)` 是一次 post-anchor 双来源基础事实读取，每个来源 dispatch 前持久预扣一份 `facts`。两来源正常路径因此逻辑 `facts=2`，并不是“第一响应免费事实”。目录前缀为 `directories=2`；worker 底层 `inspect` 总数通常为目录 2 + 事实 2 = 4，另外逐项记录 B2、完整来源校验、启动与关闭。

每个读请求带原 task/run/condition、来源标签与选择，子期限为 `min(原任务期限, 当前+30秒)`。真实 reader 沿用每个 worker 本来的 30 秒期限，不将它重设为新窗口。完成门禁并非硬实时 OS 中断；reader 在各来源操作前后和持久化前后检查任务、子期限、worker 原期限。

普通事实来自新 `inspect`、完整外部绑定消费、正常 B2 和完整 core 计算。`facts` 回执明确是完整 source rows，`targeted_triangle_indices=None`，不能把后来选中的面包装成已经发生的定向读。若显式发起 `targeted`，真实 reader 必须实际走现有定向 binder/report，并从实际查询结果返回定向索引；源 B2 同次复用及物理 inspect 数另记。`joint_supplement` 只有在 reader 明确支持其真实语义时才可执行；当前真实 reader 不提供独立 native joint，明确拒绝，不把产品 B2 包装成 native oracle。

这个有限会话只发布一次。已有消耗可以使首次请求预算不足；成功、失败、unknown、取消或到期以后不能用新 ID 再执行读取。重复 request 不重做；读后失联和错误绑定都保留已耗逻辑额度与 reader 的实际成本快照，自动重试/退款均为零。取消在每次 dispatch 和构造/发布检查点可见；在检查点之前取消则停止后续来源，在提交完成之后取消则保留已完成的发布与真实计数，但禁止后续交付。read 与提交的这一离散边界不宣称连续中断已经运行的只读系统调用。

## 证据、发布和解析

`request` 调用 v2 producer，核对完整 request task、问题/阈值、各来源/profile/anchor/core 和 view binding。候选选择只使用已核验正常事实；同面 mixed 必要见证不能被单项极值和整数排序替代。全局 unknown 与完整 core 三态来自相应完整来源，回放一致性不被解释为物理测量误差认证。

先序列化并实际持久化 `EVIDENCE.json / VIEW.json / AUDIT.json / READ_RECEIPTS.json`，每个文件 flush/fsync、原子替换并回读验证。证据侧包上限 2 MiB、完整 audit 4 MiB、模型 view 512 KiB；这是两个来源的发布文件预算，不修改原 worker 单响应预算。临时写入失败文件保留，完整侧包没有为精简模型视图而被删除。

上述为发布层上限；复用的 001 evidence 仍受 512 KiB 限制，v2 producer 的新侧包另受 1 MiB 限制。完整链以先触发的门禁为准，发布层 2 MiB 不等于所有该大小的输入都可准入。

随后 reader 必须核对原始来源未变、关闭两个 worker、检查实际退出及所有原期限；失败后的 best-effort `close()` 仅资源清理，不重新核验、重新读取或构造一个成功关闭回执。发布 marker、账本 commit 和最终期限检查共同构成一次有效发布，单独一个 `PUBLISHED.json` 不足以证明成功。序列化、写盘、回读、关闭或最后期限失败均不会返回有效成功结果。

成功发布要求每个 worker 实际退出码为 `0`；仅有“已经关闭”不够。最终期限检查也覆盖返回对象的复制与构造。引用重用还会核对四份持久文件各自的字节数与 SHA，审计或读取回执丢失、损坏时不能继续交付。

返回引用固定为 `deformation-evidence-reference-v1`，包含 task/run/condition、证据 SHA、view SHA 和 evidence version 2，不包含任意文件路径。`resolve(reference, pointer)` 只访问本槽位已发布文件；核对内存及持久账本、marker、任务绑定、证据版本、完整实际文件摘要和原期限，再解析 JSON Pointer。跨 run、跨任务、错 hash、未发布、过期、篡改文件和任意路径均拒绝。source identity 与捕获时间仍明确绑定静态快照，不声称被关闭 worker 可持续证明当前 GUI 状态。

`published`、`delivered`、`model_received` 分开：`request` 成功只证明有效发布；`deliver(reference, delivery_id)` 只确认受信协议驱动收到，重复 delivery ID 拒绝。首次交付的写账/最终期限失败保留 `delivery_unknown`，不会标记实际已交付。所有成功和失败的 `model_received` 均为 false；没有“自填 received=true”替代真正模型图像/文字输入的证明。本批没有模型 token、阶段、首答率、USD 或净收益成绩。

## 成本与验收范围

账本预扣逻辑读取，真实 reader 的累计 `physical_inspect_requests / B2_rows_passes`、事件、启动/读取/校验/关闭跨度独立保留。适配器另测 producer、序列化/hash、各文件持久化加回读、总持久化、关闭、marker/账本 commit、解析和协议交付。`request` 回执保留真实 ledger 写入的次数、字节与耗时，以及完整请求墙钟；文件账本中的阶段计时不递归测量自身最后一次写盘。嵌套跨度不可加成总耗时，Python 分配峰值也不是进程 RSS。

旧 `Control` 仍是离线替身：它的两来源 `collect` 和四份事实上限对应本层逻辑 read，而不是底层 inspect 数；原 nonce/重复响应/交付/取消/终止/预算/原期限合同未被改写。本层不会被藏入 `RecordingReader`，也不声称已完成从首次目录到模型最终答案的生产闭环。完整预取阶段的更大控制协议变更、真实模型消费及后续公平比较留待来源复核后的独立批次。

正常真源验收使用现有合法作者两个保存帧，协议驱动执行 reader → qualified facts → v2 view → 完整持久证据 → 成功发布 → 绑定取证 → 协议交付。失败注入为隔离替身，单独记载，不冒充 Blender 真源验证。原作者资产、共享 GUI、P1、旧 full/audit/scorer、默认 MCP/Hook 与安装保持原状；Google/key/503/付费继续暂停，旧 US$0.02 预留不变。

## 002A：成本缺测与已完成执行分开记账

`cost_integrity` 使用 `deformation-cost-integrity-v1`，状态为 `complete / partial / unknown`。必需累计计数为 `physical_inspect_requests / B2_rows_passes`；其余已出现的顶层计数字段也进入合同，事件、进程状态、期限及时间跨度等明确元数据除外。每个当前计数必须是非负的精确整数，缺失、非法或小于该字段已知高水位时记为 `null`。采集、复制或规范序列化失败时，当前所有计数均为 `null`，不得用旧快照补齐 `reader_costs` 或 `usage`。`complete` 仅表示本次 reader 累计计数完整，不表示整任务成本完整或模型已经消费证据。

`current / counter_fields / unknown_fields / issues` 说明当前可用范围；`last_known` 为逐字段最后可信高水位，每项保留原 `sampled_at_ns`、`snapshot_sequence`、`event_sequence_through`、`logical_source_read_attempts_through` 及关闭状态。合法的部分样本也推进对应字段高水位，不能随后用较低的完整样本抹去它。事件序号表示采样时账本已有的事件边界，不涵盖之后追加的回执。普通缺测后，同一累计来源的完整、未回退样本可以恢复 `complete`；原缺口仍留在 `history`。已识别的 `started_ns` 改变或消失后，本会话不再自动认可该累计周期，也不靠计数归零恢复可信状态。

逻辑预算由执行事实独立确定：初始化逐条验证的两张目录回执仍确定 `directories=2`，事实读取在派发前预扣；成本缺测不能退还预算、重读来源、重算 B2 或改变已完成执行。若当前可用的 `logical_directory_reads` 明确与两次目录读取矛盾，仍按 `prior_directory_costs` 拒绝。缺测本身不撤销已验证的来源事实或有效发布。

`request / resolve / deliver` 的成功回执都复制同一已持久账本状态的 `usage` 与 `cost_integrity`；引用验证同时核对持久与内存的当前成本及完整性。异常退出和取消也尝试保留最新计量状态；不能写盘时保留原失败，不能宣称已经获得有效交付或持久失败回执。

真实 reader 仍先完成来源验证、资源关闭、实际退出码为零以及原任务和 actor 期限检查。只有最后的成本打包失败可以返回 `costs=null` 和 `cost_snapshot_error`；随后构造回执及返回前仍检查原期限。来源、退出或期限失败照常拒绝，不由缺测处理合成成功，也不重试关闭。初始化、逐来源读取、关闭、发布及后续协议操作的计量降级不引入新的来源请求。
