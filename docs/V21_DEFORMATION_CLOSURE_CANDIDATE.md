# V21-REFACTOR-001：已绑定候选面的跨静态来源事实视图

本批从 `56ed427687976521524ca29d5d408c184f9032e6` 开始，只实现确定性的只读投影候选：已有合法锚点、核心区域和候选面之后，将同一原始三角面在两个静态来源中的事实按来源标签对齐，保留完整来源与审计侧文件。它不建立核心、不选择修复对象、不修改骨骼或权重，也不创建学习库。原 `deformation_context.plan(...)->(out,audit)`、完整报告、控制器和评分规则继续保留。

用户参考文档为 `Human Eye V21 Plugin Benefit Reaudit And Refactoring Spec.md`，原件 SHA-256 为 `ae9b16bc0a1e0e8781e10c3481c60df298f9c50f30177c137525b55cdfd0b3e8`。本批保留原文，其代码与性能数字作为待验证建议；不因文档写成“源码终审”就把未成立的合同或收益作为既定事实。

历史记录分母保持独立：

| 记录 | 实际任务与口径 | 本批采用的结论 |
| --- | --- | --- |
| B3e 124 源三路报告消费 | 10 个固定核心汇总任务；第一阶段文件为 99,924 / 99,427 / 39,288 B；普通组初答 1/10、9 次补查 | 说明普通报告在该集合常缺完整核心事实；不是双静态同面任务的首答成绩，也不是实际 token 数 |
| REVIEW-CYCLE-006 125 源双静态任务 | 一个作者、两个保存帧、一个同面见证任务；A/B/C 都 1/1；三阶段父端时间为 137.44 / 128.24 / 141.43 秒；独立数学与序列化为 0.163 / 0.231 / 0.567 秒 | C 同样有 35.42 秒完整 CLI 和 141.43 秒三阶段时间；不能把某路数学小计与另一整任务时间相除，宣称原生快 250 倍 |
| SPATIAL-PERCEPTION-AB-001 | 一个独立的低面数合成空间选择/孔洞关系任务，两个新消费者 | 独立保留其任务质量、适配失败与成本，不拼接为形变任务的分母、收益或失败 |

`8eace8b` 到基线 `56ed427` 的 `deformation_context.py`、`deformation_core_facts.py`、`region_witness_pilot.py`、`region_witness_control.py` 和 `region_witness_scoring.py` 无差异；上述源码合同差异不能归因版本漂移。

本批依据的真实源码合同：

- `grade` 的 `selected_triangle` 是整数；帧行有 `label`、`file_sha256`、`principal_stretches`、`area_ratio`、`state`、`reason`、`in_core` 和 `has_confirmed_mixed_witness`。数值沿用原 1e-9 相对/绝对容差，`measured` 的正常 `reason` 可为 `null`，不能默认改成 `"ok"`。
- `Control.sources` 是恰好两项的字典，prompt 使用 `run_nonce/condition/model/N`，终态是 `final/model_final`；没有参考代码假设的 `step()/stage_history`。`facts=4` 是逐来源物理事实读取配额，两来源基础读取扣 2、定向读取再扣 2；最多 4 个候选面是另一个限制。
- `has_confirmed_mixed_witness` 作用于某来源的完整核心：有同一 `measured` 面同时达到两个公开阈值则为 `true`；否则存在核心 `unknown` 则为 `null`；否则为 `false`，空核心也为 `false`。不同面的最大、最小伸长不能拼成同面见证。`collapsed` 事实保留其零值和原因，不改成 `unknown` 或 `measured`。
- `reference_geometry/current_geometry` 是几何零面积状态字符串，不是约 85 KB 的坐标矩阵。字节主因必须由本批真实字段分解测得。完整核心计数、unknown、四极值与其见证优先复用 `deformation_core_facts.project()`，不能从少量候选反推。
- 文档的 9–15 KB、10/10、26–32 秒、0.05 ms 与“零遗忘”均不是本批已达成的成绩。共享哈希槽保持非激活槽不变，也不能证明旧样本的模型输出不变。评测真值不进入候选面选择或训练。

新接口为 `human_eye_plugin.deformation_closure.project(task, frames, *, candidates_by_label, threshold_high, threshold_low, deadline_ns)`，返回独立视图和独立审计。它消费已通过完整来源校验的内部数据；不把 JSON 自报 `qualified`、一份包内哈希或纯投影调用视为外部来源准入。

`task` 保持三个键 `task_sha256/condition_id/sources`。本投影的 `sources` 是恰好两个实际标签，值固定该来源的 `source_ref/catalog_sha256/anchor_id/policy_sha256`；这是选择锚点后的投影绑定合同，未把离线 `Control` 升级成生产适配器。任务哈希的原问题含义由外部调用者绑定，投影视图另显式发布实际阈值和候选语义，不能只凭同一个哈希声称任务条件未变化。

`frames` 必须有且仅有两个带独立 `label` 的条目，持有完整 qualified proof、绑定几何行、完整 membership、policy、policy hash、query、operator pins 和来源校验元数据。输入按标签连接，乱序不改变语义；重复标签、缺标签、错来源、错 catalog 或锚点直接拒绝。每帧自己的 scene/frame/mesh/rig 与运行 pins 都要成立，不能把首帧的来源标记复制到第二帧。

同一原面证明至少固定原始顶点、原始三角面索引及顺序、单位、mesh/rig 逻辑角色和本窄域的同一锚点。每个来源的进程、文档 epoch、对象和 datablock 实例仍各自验证，不要求跨进程 session UID 相等。若同一整数 ID 对应换拓扑、换原始面顺序或不支持的映射，本候选拒绝，不凭坐标相似合并。

候选只能来自调用者明确已有选择或正常公开引擎事实，不读取私有 truth、`acceptable_witnesses`、评分输出或原生 oracle 来挑面。每标签列表允许为空，重复 ID/布尔 ID 拒绝；跨来源并集超过 4 面拒绝，不静默截断。一个面即使只在一帧成为候选，也必须在另一帧连接到同一原始面的真实绑定行。缺帧、缺行或缺同拓扑证明不是 `unknown` 的同义词，不能合成默认行冒充闭包。

完整原始几何、完整绑定行、全核心 membership 与审计留在独立侧文件，模型视图保留任务所需数值、完整核心汇总和稳定来源引用。侧文件先独立摘要，视图再引用；末端审计单独记录新视图的规范字节数和 SHA，避免视图与审计互相哈希循环。旧发布的 `published_publication_sha256/bytes` 不用于新视图。

实际 schema 分别为 `surface-deformation-cross-frame-view-v1`、`surface-deformation-cross-frame-evidence-v1` 和 `surface-deformation-cross-frame-audit-v1`。输入证据侧文件保留 `core_report`、完整核心 ID/行摘要和原始数据；原 `core_audit` 完整放在外层审计的 `core_verification_audits_by_label`，其中运行计时和原期限不会进入语义证据摘要。相同 qualified 输入在不同投影时刻或期限下，视图与输入侧文件规范字节相同；重新采集产生的 process/document/source 身份变化仍属于真实输入变化，不承诺跨不同捕获哈希相同。

新增包内 Python 模块自动进入 `runtime_identity._source_manifest` 和 worker 的 verified-source manifest；`_ROOT_MODULES` 只列仓库根模块，无需给包内模块重复注册。新候选的运行源数量与摘要会变化，隔离 QA 必须用新进程重算身份并绑定新 profile，不能沿用旧 `a045` 或 `29f8` 的 runtime pin。

本候选 revision 为 `v21-cross-frame-fact-view-candidate-20261104`。来源重核包括两次公开目录核对和每来源两次绑定行验证：`verified_rows_passes=4`、`bound_row_validation_rows=2*scanned_rows`。`scanned_rows` 是两来源完整行数之和，不能当作所有循环总次数；额外行字段检查和全核心统计/确认也计入实际投影耗时。`confirmation_core_rows_scanned` 单独记录三态确认遍历量；`B2_rows_passes=0` 与 `region_membership_scans=0` 仅表示没有重新计算这些已有几何产品，不表示投影无来源核验成本。`physical_reader_calls=0` 明确限定于纯投影函数，不能用它声称采集或预取免费。

验收需覆盖：单帧候选跨帧闭包、帧乱序、错 source/anchor、同 ID 换拓扑或原始面顺序、重复面/标签、缺帧/缺行、空核心、全 unknown、collapsed、三态确认、核心外极值和不同面拼阈值；输出与完整正常来源的对应字段逐项比较。旧控制器和 scorer 保持精度及门禁，取消、到期、失败不退款、重复响应和未交付证据等合同按变更范围回归。

本批新鲜隔离验收记录在 `verification/fixes/20261104_v21_refactor001/integration/fresh_r1/RESULT.json`。它重新启动两个合法只读来源 actor，实际执行 4 次 `inspect` 与 2 次 actor `analyze`，通过正常 owned collector、完整外部绑定与独立来源校验接通；不是仅重放旧冻结资料。新候选为 126 个运行源，摘要 `823175d7ac52fa1fe5e5485fbefeb6e123ba8cc534d4c55750f29aa8a3323814`。原件哈希未变，所有 owned 进程关闭，投影继续使用两个 actor 原期限的较早者。

该作者两份静态来源各有 188 条完整 B2 行。核心分别为 117 / 128 面，完整核心的同面混合阈值见证分别为 0 / 20，确认值为 `false / true`。独立只读复核按实际标签核对了 task/source/catalog/anchor/core 绑定、候选逐帧数值与原行一致、视图和侧文件精确字节摘要，以及外层原核心审计对其 `core_report` 的发布摘要。此核对证明本候选数据接通与投影一致性，不是新的模型消费或来源领域扩展。

| 本次实际发布物 | 规范字节数 | 内容口径 |
| --- | --- | --- |
| 两份普通 anchor/region 报告合计 | 18,046 B | 保留正常完整 JSON 字段，但逐面明细受既有上限约束；不是两份 188 行完整事实表 |
| 两份已有 core-facts 报告合计 | 6,516 B | 完整核心汇总及极值见证，不含新候选的全部跨帧同面轨迹 |
| 新双来源模型视图 | 8,664 B | 来源与完整核心汇总、三态确认、最多 4 个候选的跨帧精确事实和稳定证据引用 |
| 新输入证据侧文件 | 380,116 B | 完整 proof、绑定行、membership、策略、原核心报告与行摘要；未向模型默认展开 |

新视图比本次普通有界报告短，但比仅含核心汇总的旧 core-facts 包更大，信息量不同。上述四个数不能作为所有任务的压缩率，也不能把仅存于侧文件的字节当作已送入模型的内容。完整字段分解在实际结果中分别列出顶层发布字段及全部 B2 行字段；`reference_geometry/current_geometry` 实际值是 `nonzero_area` 等状态字符串，包含其重复键名的字节贡献也单列，未发现文档假设的 85 KB 坐标矩阵字段。

本次扫描完整行数 376，绑定行验证计 752 行 / 4 次，三态确认扫描核心 245 行；核心汇总与附加字段检查的成本也包含在调用耗时内。新投影本身没有重新跑 B2、region membership 或物理采集；QA 为普通报告对照和内部核心管线分别运行了 2 次 B2，共 4 次，不能隐去对照成本。4 次真实来源 `inspect` 不等价于已接通 `Control.facts` 的预算记账。

带 `tracemalloc` 的提取和投影外层调用实测 110.228 ms，审计内部投影为 107.490 ms，来源/绑定验证子跨度为 90.3972 ms；它们相互包含，不相加。Python 跟踪分配峰值为 2,799,968 B，不是进程 RSS 或 Blender 内存。完整父端只读 QA 为 7.8324747 秒，涵盖启动、来源、对照、落盘和关闭；不与前述局部耗时或其他历史任务的模型墙钟计算提速倍数。

尚未接通生产 `Control` 读取/预取适配，也没有本批真实模型交付；投影审计仍明确 `delivered=false`，要求调用者先持久化完整证据，再沿原期限发布。本批不运行真实模型消费，首答率、模型轮次、token、费用、零补查和整任务收益均为未测。下一批需要独立约定合法读取回执、读取扣数和交付合同，不能把本批内部完整行中的候选提取自报为已完成一次定向产品请求。

后续队列固定为：

1. 收口本批确定性的跨帧事实视图及真实来源接通证据。
2. 另批设计合法读取/预取适配，真实扣除每来源读取、失败、回退与来源核验；沿用原绝对期限。
3. 来源复核后冻结真实消费者对比，分别验证答案质量、局部证据、完整墙钟和成本，不以离线投影通过替代实际消费。
4. 仅在额外收益假设成立且有独立训练/评测隔离后，研究学习排序；不默认建立记忆库或用同批真值训练。

Google API、key、503 重试和外部费用账本继续暂停，旧 US$0.02 预留保持。原作者资产和共享 GUI 只读，默认 MCP/Hook 与正式安装不变。候选通过本批不等于正式部署或通用来源扩域。
