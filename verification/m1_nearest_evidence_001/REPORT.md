# M1-NEAREST-EVIDENCE-001

本候选补齐最近查询首次响应的必要依据：直接投影同次已有测量中获胜及并列对象的最近点、方向、各自状态和原因。没有新增采集、几何求解、关系查询或模型消费者。后续是否减少模型补查、完整任务耗时和成本，仍未测量。

基线产品为 `7411ac7aa9338f17355ffe5cdf4df113ce862aed`，137 源 canonical `0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a`。实施树起点为 `fa23496e1565e34ddacf4a0ce28b65e0a85c3ca8`。候选同为 137 源，canonical `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1`；没有更改版本常量。运行证据按源码摘要绑定，不能由名义版本判断两版相同。

产品只改三个文件：`task_query.py` 从现有 `measurements[best]` 取 `best_known_evidence`，共同 `measurement_semantics` 只交付一次；`live_service.py` 将每项 candidate 绑定到同次捕获的 ID 和名称；`live_spatial_mcp.py` 仅准确补充精简 nearest 工具说明。普通及精简入口共用组装路径，原普通工具目录及参数保持兼容。排名、精确键、测量、来源验证、缓存、期限、工具数量、调用参数和预算均未改动。

`best_known_evidence` 顺序和 `best_known_objects` 一致。完整时覆盖全局并列最近；partial 时仍只是 best-known，`nearest_objects` 与全局距离仍为空。原距离、coverage、unresolved、measurement_notes 全部保留。见证无法可靠公开时保留空坐标及原原因，不抹去仍有效的距离或独立方向；零距离保留原 `not_applicable / undefined_zero_distance`。开放表面只提供表面事实，没有新增闭体或损伤判断，也不输出所有候选网格、内部精确排序键或长证明。

最终有限回归为两版各 **49/49**：原精简入口 14 项、现行 surface entry 18 项、适用 integration 9 项、新增 8 项。新测试产生 18 条定向记录，覆盖普通/精简入口、开放面、正距和零距并列、真实 bit-budget partial/all-unknown、世界见证未知而方向有效、浮点公布距离相同但并非精确并列、焦点逆序、热缓存和调用方修改返回值后的隔离。新增测试逐项核对测量原值，并用独立三角形点距判断核验公开见证的表面归属。

18 条记录在两版间的原核心结果逐字段一致；比较只去除新增两字段及 trace，并在先精确核对各版 runtime source pin 后替换该 pin。捕获绑定、场景/目录摘要、原测量和诊断不被删除或模糊化。两版各为 capture **18**、pair **24**、kernel **24**、rank **16**、底层 nearest **20**、closed-solid **0**；热请求保留当前 capture，但 pair/kernel/rank 为零。计数是这些有限记录的合计，不是完整任务调用数量或性能跑分。

17 条 MCP 记录的原始 `content[0].text` UTF-8 正文合计增加 **8,548 字节**。单获胜对象的常规开放面及 partial 案例各增加 **483 字节**；正距双并列 **744**，零距双并列 **826**；无 best-known 对象时增加 **187**。逐案字节数、直接 service 对象的编码数及 MCP 对象重编码数见 `compare_02`。原始正文、重编码 JSON 对象和真实网络帧是不同层级，本轮未记录网络帧，不混称 wire bytes。新增量随获胜/并列集合增长，未截断并列或放宽原预算。

这些正文增量不能与上一轮六次局部补查的响应量直接相减：任务输入及统计层级不同。本候选只证明现成依据能够随首次结果交付；没有证明消费者将少调用一次，更不能将原首次结果到最终答案的约 16 秒观察跨度视作预计提速。

首次尝试 `baseline_01` 和 `candidate_01` 各运行 50 项，各有 49 项通过及一项相同 `FileNotFoundError`：旧 `SurfaceNearestEntryTests.test_03_one_actual_packet_reaches_real_summary_and_no_history` 最后读取 action state 文件，而已经接受的独立 ReadContext 不再创建它。两份失败结果、全部日志和初版 runner 原字节保留；未修改旧测试或为其恢复账本写入。最终 runner 明确排除此过时方法，并用现行 `test_default_session_does_not_touch_opaque_action_journal` 及新入口/计数断言验证当前合同。

另一个旧 integration G06 在首次运行前即明确不选：它要求共线三角形拒绝，而已接受 v3 内核支持其闭包。既有 `verification/arch_read_context_001/HARNESS_NOTES.md` 已记录这个合同变化。本轮使用原有真实 `surface_exact_bit_budget` 输入验证 partial/unknown，没有改变内核或降低精度。最终两版无失败、异常或跳过；这不抹去首次两项旧验收错误，也不宣称整个历史测试矩阵已通过。

结果比较器首次 `compare_01` 因自身重复归一化源码摘要而拒绝自己生成的 sentinel，没有进入逐组成功结论。保留失败输出及比较器原字节，修正为先精确核 pin、再对完整原始行只归一化一次，`compare_02` 通过。产品和两版输入证据都没有改动，也没有为此重跑产品。最终比较覆盖既有 9 组中的 11 条直接结果及 18 条入口结果，全部原事实与调用计数一致；两版测试、fixture、runner 和原引用材料的摘要也一致。详见 `COMPARISON_EXECUTION.json`。

每版使用从原始 Git 基线或候选物理复制的 137 源，以及产品原 `verified_source_loader` 冻结执行；记录实际加载摘要、测试/fixture 摘要及结束来源核验。测试套件执行阶段的额外外部进程、网络、信号操作被禁止，尝试均为零；准备阶段的只读 Git 取源不在此零计数内。该证明是 guarded source + fake RNA + 真实内核验证，实际 source_kind 为 `unregistered_runtime`，不属于安装或真实 Blender 验收。未激活默认安装，未新建资产或任务，没有更改原资产。

本轮新增模型消费者 **0**；没有重跑或替换原 27 格，没有 Google/API/key 调用。原正式结果的 2,396 个归档文件及 37 份重复输入副本均逐字节核对通过，见 `PREVIOUS_RUN_INTEGRITY.json`。旧源、默认配置、竞争分支和根审查提交未被合并或覆盖。

未运行项包括：实际 Blender T2/T3 再采集、隔离安装验收、模型任务消费、完整任务速度/成本对照，以及 known-zero + unresolved 的组合子例、稀有的方向 unknown 见证 bit-budget 分支。当前已分别验证 zero 和 partial，原完整性逻辑及状态来源未改；本批不为补齐所有组合而继续扩大。下一步应由管理员复核固定候选，然后进入完整观察任务的设计，以真实失败决定后续优化，不继续重复当前已封顶小题。
