# M4-B3e 固定任务核心的上下文精简与验收

更新：2026-11-02。排期只由[唯一主计划](PRODUCT_ROADMAP.md)决定。本批沿用[B3b可信来源](M4_SMALL_SOURCE_PRODUCT_ACCEPTANCE.md)、[B3c完整区域事实](M4_DEFORMATION_REGION_QUERY_ACCEPTANCE.md)和[B3d原生锚点](M4_DEFORMATION_ANCHOR_QUERY_ACCEPTANCE.md)，完成一个可验证的小域：操作者指定不可丢失的任务核心，引擎只在核心事实完整、最终输出净减小时省略外围上下文。

这不是通用取景质量、可见性、损伤或自动语义定位算法。空核心、全unknown核心、缩框却成员不变以及没有净字节收益，各自保留原范围和准确原因，不盲目放大、改锚点或追加图片。

## 固定候选与合同

| 项目 | 内容 |
| --- | --- |
| 发行/运行源 | `9.7.2+20261102.deformation.context.r1`，122运行源 |
| 源码SHA | `1bb705d67df4e14f0c02f0c3eb15d2c7ebb6569f7bca95fb8eef170a39af99d1` |
| wheel SHA | `feb5db6b2b6141002576013d3b15c8fa5c9496d61980887d54cf3f40423f0a48` |
| 新入口 | `--context-query SELECTION --context-policy POLICY --context-policy-sha256 SHA`；与旧查询/目录互斥 |
| 来源/执行边界 | 原B3b固定来源、256点/256面/16骨、完整依赖与外部pins保持；旧B1的128点上限不变。只读、不切帧、不保存，无新增setter |
| 原预算 | 每调用30秒、16请求、512KiB包/报告；policy和selection各最多4096字节 |
| 可选规划 | 有效primary生成后，另有1–250ms子期限，始终受原期限约束；最多2个操作者有序候选，先合格者优先，无最优性声明 |

独立策略文件严格为`surface-deformation-context-policy-v1`：保存scene/roles/frame、catalog摘要、原生anchor身份、core/primary/candidate半宽、允许的额外整面数、最低净省字节和规划预算。原始文件SHA由操作者在进程参数中固定，接收后冻结并在分析、关闭和发布时复核。模型selection只引用该策略SHA和相同来源/目录/锚点，不能覆写范围、候选、阈值或预算。

三轴半宽为有限非bool数，各在1e-6至1e6米；必须满足core≤candidate≤primary，候选互异且不等于primary。`max_surplus_members`为0–256的任务额外整面记录预算，不能解释为面积或体积覆盖率；`min_saved_bytes`为256–65536。异常字段或不支持范围准确拒绝，不能退回无策略成功。

## 算法与输出

1. 完整来源独立验证，生成一次完整B2逐面事实；同一proof建立一次不可变的精确有理世界坐标缓存，primary/core/candidates复用，不为每个候选重新捕获或执行整套B2。
2. 先完成与旧anchor查询同语义的primary报告，包括`source_validation`和`anchor_query`。再开始可选规划计时，避免拿尚未完成的primary当安全回退。
3. 核心为闭框触及的全部原始三角形，边/点接触和塌缩仍保留。完整core IDs、measured/collapsed/unknown计数、unknown原因和完整B2行摘要绑定；局部详情仍最多4面并明确省略，不声称全部core细节都已发送。
4. 空core保留`focus_empty`，全unknown保留`focus_all_unknown`；primary额外成员已在预算内，保留`within_surplus_budget`且不评估候选。外围unknown减少不能提升核心精度或改变全局统计。
5. 超预算时按操作者次序查询候选。必须保留全部core事实、严格减少外围成员、达到额外成员预算，并使**包含完整context_quality轨迹的最终规范输出**相对同源旧anchor primary至少净省指定字节。只缩小几何框不算收益；元数据使输出更大也不能采用。
6. 可选期限/明确算术资源预算耗尽时，仅在原期限仍有效时保留已完成primary，标记core/search完整度；原期限过期或来源/策略失效不能发布有效成功。

显式新模式stdout为排序紧凑ASCII JSON加一个LF，含非ASCII名字时按实际转义字节计数。运行路径、完整耗时和最终byte/hash放在本地`PUBLICATION.json`，完整core rows、baseline、各候选报告及选择审计放在`CONTEXT_AUDIT.json`；不在报告里添加自计数字段。身份和source/catalog/core摘要继续使用原UTF8规范，不能与发布编码混用。

旧模式保留schema、数值、查询范围、准确拒因和生命周期；共享内部行缓存会规范化JSON对象键顺序，不承诺旧CLI原始文本顺序逐字相同。原producer/schema/worker、默认MCP/live/Hook不改。

## 验收与证据

| 验收项 | 结果与范围 |
| --- | --- |
| 固定源码/隔离安装/wheel/干净源码 | 122运行源逐字节一致；原121源中116保持、5修改，新增context模块。536份公共Python与受测干净导出一致，producer/worker保持。初始与final wheel同SHA；final包仅更新README |
| 新原生与准确拒因 | source32/32、installed32/32：每套10场景（8个QA副本、一个作者样本两个固定帧）+21个精确合同组+1个实际CLI；独立SAT/SVD、完整core行、source/catalog/anchor/policy绑定、策略改变/原窗口/混合模式拒绝与正常入口均通过。两个安装形态几何事实和选择相同，fresh PID/epoch/source观察摘要正常不同 |
| 字节收益与无收益 | 4个构造场景每次保留1个core面，由9个primary成员缩至1个；净省1174–1293B（约16.5%–18.0%），已含质量轨迹。point contact和collapsed各保留事实，外围unknown减少不改core/global计数。normal不试备选，长面缩框但成员未减不采用；empty/allunknown不换目标 |
| 真实产品调用与作者任务 | 当前任务实际执行10次固定安装CLI，全部canonical ASCII+LF，与PUBLICATION/audit byte/hash一致。作者另以非空core半宽0.5m、primary2m和固定候选做两静态帧任务：core117/128面，primary均128面；frame1候选无净收益，frame25已在成员预算内，均保留primary，实际增加982/1021B。新native中作者0.25m空核是另两种任务，不能冒报为非空任务成功压缩 |
| 完整成本与收益范围 | 实际10次CLI完整墙钟约3.20–3.65秒（含独立进程、绑定、两次完整观察、分析、关闭和发布）；新native可选planning约0.56–10.56ms，非旧/新整任务配对比较。回退轨迹在构造任务增加605–640B，在上述非空作者任务增加982/1021B。未测完整模型token/费用或端到端提速；共享行缓存序列化亦不作为旧入口性能通过证据 |
| 独立Codex实际消费 | 一个全新上下文仅看10份实际公开报告、operator policy与发布byte测量；10项、170个字段核对通过。正确区分4净省/6保留、空核/全unknown、collapsed、详情省略和全局unknown，未推断损伤、体积、正面积接触、解剖或整任务加速。未给私有oracle、完整隐藏坐标或生产实现；这是消费检查，不是双盲或无引擎收益对照 |
| 公共与旧原生回归 | 152模块2481项，本地2478过/3既有跳过、干净公共源码2468过/13跳过，无新增跳过；QA枚举修正后两套重新完整运行。旧331组保持：B1/B2各66、B3b各22、B3c各20、B3d各28、constraints43、restore13、dyadic3；只读域零setter，restore仍仅隔离测试副本的原授权恢复回归 |
| 验收器修正与失败保留 | 独立anchor QA helper的UTF8身份摘要与实际协议对齐，新增中文骨名反例，未改生产摘要或旧sealed。首次新native的QA枚举within_budget与冻结生产within_surplus_budget不一致，失败完整保留后只修oracle；原256B门和事实预期未放宽。最终审计首次比较独立core_facts内存整数键与JSON字符串键失败，保留修正记录后按JSON往返语义比较，未改产品或oracle |
| 原件/历史/Git | 所有测试原文件SHA保持，worker全部回收，89份旧seal及6域9036文件复核通过。源码、公共反例与本文随Git同步；完整本机证据另封存，默认MCP/live/Hook不切换。新封存对应最终commit、source/install/受测导出及包体，不改历史成绩 |

原生controller为比较同源完整primary而额外调用一次旧分析，属于QA开销；生产context每次仍只有一个B2行构建和一个世界坐标缓存，无额外inspect。source/install两个运行不会累计成新资产覆盖。

## 本地清理

本批先清理再构建：删除4处当前源码缓存的168份可再生pyc（5,760,152字节），17组相同初始/最终wheel经逐字节校验后使用硬链接共享15,482,944字节重复载荷，保留两条路径和SHA并设为只读。只读属性改变已记录，后续不能就地覆写这些历史包。

对最近6个M4封存域中119份明确白名单的大型只读JSON做经典NTFS透明压缩；逻辑大小103,315,184字节保持，实际分配从103,608,320降到25,829,376字节，减少77,778,944字节（约74.18MiB）。内容SHA、逻辑长度、创建/修改时间保持；压缩属性与文件系统变更记录会改变，不声称全部元数据不变。未改封存清单内容，不跟随旧junction，不删源码、原资产、venv、历史包路径或验收证据。

89份旧seal摘要与项目配置保持；最终逐文件复核记录另见本批本地`CLEANUP_FINAL_AUDIT.json`。重复载荷、缓存逻辑长度和实际磁盘分配分别统计，不把不同口径相加成精确磁盘回收总数。

## 结论边界与后续

本批目标仅为固定核心的数据保留和可验证字节收益。正常/无收益回退仍会增加质量轨迹开销；原生捕获、全量来源验证和全量B2并未减少。构造场景输出变短不能外推为真实作者资产普遍获益、token降低、整任务加速或模型能力提升。

后续仅按唯一主计划收口同域任务的端到端价值资格：冻结任务、合理共同基线、完整耗时/字节/质量及停止规则，再决定是否值得进入有限模型对照。不为追求净省继续无限微调，也不同时扩解剖、来源、动画、图片或写入域。正式模型试次仍为0。

本地原始记录：`verification/fixes/20261102_m4_b3e_context_quality/`。源码、独立oracle、公开反例和重放工具随Git同步；本机profile、外部作者资产、隔离包和完整历史日志不上传源码仓库。
