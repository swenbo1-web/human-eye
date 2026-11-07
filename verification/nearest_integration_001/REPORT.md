# NEAREST-INTEGRATION-001：同版本内部只读链已接通

**COMPLETE。** 唯一固定候选通过10组离线集成、158项相关回归，以及同一个NativeSession的三态真实接线；3次采集+1次close，0真实重试、0未运行状态。原始状态返回Near=2，正常更新后返回Far=.25，保留退化候选时返回partial，未把Near冒称全局最近。

本方分支 `codex/nearest-integration`。原 `codex/nearest-exact-ranking` 仍为bdbd700，旧perf报告分支仍为c899da0。正常merge固定602e9c5，合入提交f9a67c3完整保留双方证据；M3内核来自bdbd700、host及完整来源/首面helper来自602e9c5，字节未再修改。

**冻结产品提交 `25553f023ee4cddc2cf527406a192b9c95fb1fec`；131源SHA256 `f0f9a09f0fbe586902256347428c6b1e80bc4ef3ca5b7a09a5230663be6a1b1a`。** 统一版本v23-same-capture-surface-nearest-20261107，host仍为de429b26…。冻结后无产品修改。[CANDIDATE_IDENTITY.json](CANDIDATE_IDENTITY.json) 保存131源、输入提交与未改函数/分支核对；交付提交只补证据。

## 最小接线

新增 `task_query.surface_nearest_result(packet, cache, checkpoint, diagnostics=...)`。一个边界对齐本次目录唯一ID、完整实例绑定、focal/seed、retained捕获集合、document epoch及当前host源码身份；不重算全量目录/几何哈希。严格排除要求本次焦点和目标包络可用、真实见证存在及L>U。错误/重复/混代/集合不符在pair工作前拒绝，不能产生complete。

`auto_router._validated_scene` 增加显式内部 `_surface_nearest_capture` 路径。规范化结果、host身份和指纹保留surface_nearest_candidates；原complete/selected入口默认不变，并拒绝候选scope。没有把采集包改名完整场景，不记录scene history或生成动作权限。

每个retained非focal pair首次就retain_exact_rank=True，只调用一次原pair helper，前后均检查原checkpoint（包括cache hit）。只调用一次原精确ranker。有效精确距离、严格界排除、排名未决覆盖本次非focal全集；无未决且有有效距离才返回全局nearest_ids。partial只给best_known_ids/距离及原因，nearest_ids和distance_m为null；已知零也不能忽略未知并列。

距离有效但witness/direction发布未知时，排名保留有效距离，未知另列。排除对象仅有not_evaluated_pruned/当前界原因，没有未测distance/topology或历史退化理由。私有大整数不进入输出；结果只给简要覆盖、来源和必要未决。只新增修改task_query、auto_router和统一runtime_identity；host、M3比较器、cache、公共MCP/schema及live默认流程保持。

## 实际执行字节与离线结果

外层先核runner字节SHA，再编译同一字节；runner冻结131产品源，以既有verified_source_loader执行，测试主模块也由SHA标记的同一字节编译并用loadTestsFromModule发现。最终快照的56个实际加载产品模块有执行见证，另核namespace；没有用-B、模块路径或删缓存代替执行绑定。第三方/标准库与普通测试依赖在产品guard之外。原件为每轮EXECUTION_IDENTITY、EXECUTED_BYTES.zip和runner流。

最终 [offline_02/RESULTS.json](offline_02/RESULTS.json)：10集成+116规范化/task/surface/exact-rank+25来源/首面+17明确RNA适配M4，**168执行全通过，0失败/错误/跳过**。原fake适配只用于legacy组，不覆盖明确非法字段；新来源/首面组先直接执行真实helper。旧失败目录随固定输入完整保留，未清零。

10组覆盖唯一最近、精确正/零并列、发布相同而精确不同、跨pair尺度、远退化严格排除、retained unknown/零加未知并列/全未知、bounds或witness未知但全量量测完成、witness发布失败、目录/保留/来源错配、期限含cache hit。独立答案来自Fraction或可证明构造。[预登记](tests/PREREGISTRATION.md) 与 [测试原件](tests/test_integration.py) 固定这些组。最终10组累计实际pair21、kernel19、_nearest16、rank14；这是带子例/命中的原调用计数，不是额外几何求解或真实capture。另158项回归未统一插桩solver总数，不把该计数扩为整套总量。

初版 [offline_01](offline_01/RESULTS.json) 168项亦通过，源码摘要ad8b…；只读复核随后发现“focal包络未知却保留旧排除”这一宿主不应产生的目录矛盾，最终边界补充拒绝，并将rank尝试计数移到调用前。group09在原几何上加元数据子例并明确修订登记，未增加第11组。最终源码重新受控执行同168项。合计336方法执行、10独立集成组，不能说仅执行168次；初版及其执行字节归档保留。两轮均有原未改foveated renderer极值加法RuntimeWarning，原stderr保留，不当成产品测试失败。

## 唯一真实三态批次

启动前用旧资产recipe/full_RAW静态核坐标、哈希和独立答案，见 [PREREGISTRATION.json](qa_prepare/PREREGISTRATION.json)。只用旧far_second_degenerate.blend私有副本，原资产9a7671bb…只读。prepare在冻结产品提交后核匹配的离线通过摘要并快照同131源；client与remote host均沿用原loader执行这些字节，三份最终RPC代码及同一原期限在启动前冻结。

| 状态 | 独立构造与实际结果 | 覆盖：有效/排除/未决 | pair/kernel/_nearest | cache hit |
|---|---|---:|---:|---:|
| 原始 | Near为x2平行三角面，Far全部x100，后面退化；complete、Near=2 | 1/1/0 | 1/1/1 | 0 |
| 正常更新 | Far顶点3改为(.25,.25,.25)，投影在focal内部，所有Far点x≥.25；complete、Far=.25 | 2/0/0 | 2/1/1 | 1 |
| 保留未知 | Far后续三点改为(1,2,0)/(1,3,0)/(1,4,0)，仍共线；partial，best-known Near=2，Far原因surface_degenerate_triangle | 1/0/1 | 2/1/0 | 1 |

第三态几何上Far端点到focal顶点平方距离2可达，且是下界，因此Far实际sqrt2<Near2。该独立反例证明把partial放行为Near全局最近会错；这个答案没有传进产品补测。

本批实际 **3次capture、5次pair helper、3次kernel、2次_nearest、3次rank、2次cache hit**。每个retained pair最多一次kernel，排序和命中零额外求解；baseline Far未展开到捕获几何、未调用M3。源码来源验证仍读取其必要引用坐标，不把少展开说成零来源读取。cache frames始终0，正常更新后复用未变Near的缓存是实际观测，不预设跨状态必须命中。

QA另有 **8次完整原生oracle扫描、96个顶点位置读取**，作独立真值/恢复核查，不进入产品，不冒称采集成本为零。三态都在finally精确恢复原Far坐标/索引，capture前后原生几何相同；终末fingerprint等于初值，worker未poison。真实build为5.2.1 LTS / 9e2066aef7ef。client46个已加载模块有执行或namespace见证，bound generation compatible；远端每态host字节de429b26…由guard.exec_path执行。

[qa_prepare/run_01/RESULTS.json](qa_prepare/run_01/RESULTS.json) 保存全部状态、计数、未运行栏与owner回收；3个SUMMARY、原CAPTURE/原生ORACLE、最终STATE脚本、WORKER_EVENTS以及4份原TX/RX/TRANSPORT均保留。[AUDIT.json](AUDIT.json) 独立离线核请求原代码、worker执行事件SHA、恢复、独立几何答案、全部源与传输字节：发送尝试=完成84368B、接收20509B。

一次后处理审计误要求Windows write_text保存的SCRIPT.py字节等于线上LF脚本；实际文件仅有CRLF换行差异，原始TX和worker事件SHA已证明执行的输入原字节。保留 [AUDIT_PREP_ERROR.json](AUDIT_PREP_ERROR.json) 与初版审计脚本，只修正离线核对口径，没有更改原件、产品或重放RPC。

## 回收、成本与范围

只启动1 NativeSession，原期限600秒并预留60秒清理；3状态+close共4RPC，0真实重试。close事件原unknown标签保留，closed回复、初末指纹、owner wait exit0/reaped分别证明关闭。PID29988无存活匹配，原资产、private input.blend、helper及受保护文件哈希不变，见 [CLEANUP.json](CLEANUP.json)。

外层命令完整耗时：初轮离线4.197113秒、最终离线4.179061秒、QA prepare5.138861秒、QA run **3.313021秒**。controller内部begun计时段为2.1408113秒，不代替完整进程成本；剩余差额未进一步归因。完整聊天turn起点14:35:49Z，终点由根在本turn结束后核；15:40Z实施截止、16:00Z根复核不重置，见 [WINDOW.json](WINDOW.json)。

本批为工程正确性：0模型消费者、付费API、正式性能采样、默认安装/公开MCP部署、原资产写或第二会话。模型usage/费用未测。没有声称三路模型收益、净加速或将M2旧五态拼作本版通过。三名辅助Agent只准备离线/QA文件或只读复核，未运行产品测试/Blender/RPC；全部实际执行由本实施者完成。后续公开接入与模型消费不在本批范围。
