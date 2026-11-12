# M4 无目标全场阈值扫描：下一批最小设计

2026-11-12。父任务 `bae07fd5-cd4d-494b-bb2c-e6b2947b7f7f` / revision 1 / write_version 603；自身 assignment `607d38d7-6876-4c65-95b9-a8769d05a502`，已用 Hook 句柄核对 `parent_read_only`。使用 learning-worker 技能。本轮只读源码和既有记录，只写本报告；新增产品、Blender、模型、API 运行均为 0，没有生成资产、修改产品或 Git 写操作。

## 1. 建议与下一批边界

**只推进一个问题：当前场景所有 mesh 对的 unsigned 表面距离是否不超过给定阈值。** 一次普通 `human_eye_scene_observe` 调用完成候选发现、一次批量几何获取、本地逐候选求解和完整覆盖判定。不给对象名、候选数或 Top-K，不做图像、不要求异常语义识别。

建议下一张派单先完成下面的固定输入资格及合同冻结，再进入最小工程，**该工程批新增消费者为 0，根复核后才另行开展模型消费**。这应是同一批的短前置步骤，不另造审批流程。理由不是缺开发授权，而是目前尚无已生成、独立全体真值已核且候选密度合格的无目标固定输入。本报告不能声称下面的 24 对象场景已具备真值或成本。资格材料确认后即可沿已授权模块流程实现，不再延长具名三对题。

唯一主要收益假设：把模型选对象、逐对请求和重复补查收回本地扫描，复用现有 M2/M3；不以新的几何领域或复杂新索引换取收益。初版独立审后，针对实际局部修改引发的无关 pair 重算做一轮实质优化。没有新证据不再追加变体或调阈值跑到赢。

## 2. 本次核对的代码事实

读取实施树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`，实际 HEAD 为 `ea70339772159e5f0279784ebe18b1bf16e70439`。对产品目录 `human_eye_plugin` 及根 `module_2_low_token_mcp_scene_bridge.py` 比较 `e836e03f4b3821f869c72ac3e50df5204f28b50f..HEAD`，diff stat 为空。137 源聚合 `2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390` 是父任务及既有冻结报告身份，本轮未重跑 137 文件聚合校验。没有用 `D:/hefe` 中旧产品代替实施树。

已读：`docs/GLOBAL_SCAN_CAPABILITY_AND_OPTIMIZATION_REVIEW_20261112.md`、该文 global 分项报告、`docs/HUMAN_EYE_FRAMEWORK_REFACTOR_PLAN_FINAL.md`。以下行号均指上述实施树。

| 实际位置 | 对最小设计的约束 |
| --- | --- |
| `live_spatial_mcp.py:70,103,410,858,870,894` | 公开 mode 没有无目标扫描；schema、入口参数约束、complete 的 MCP isError 判定、结果投影与发布预算必须一起接通，不能仅增内部函数。 |
| `query_policy.py:39,75`；`task_query.py:58`；`blender_host.py:1419` | task 最多 4 个显式对象，target+candidates 最多 3 候选；legacy 的 255 是精测工作上限，不是无目标候选全集大小。不可给模型分批发送这些小 task 冒充扫描。 |
| `blender_host.py:1134` | cold directory 为每个对象 `to_mesh` 并遍历全部求值顶点求 tight bounds；把 directory→capture 串起来会重复部分获取。 |
| `blender_host.py:233,270,1227` | 已有 outward evaluated-box 世界界、保守 L∞ 距离下界、单主线程窗口候选捕获；该路径限制静态独立三角 mesh，可作为首批获取合同。 |
| `blender_host.py:1353–1389` | 最近查询先筛后展开 selected union，同窗口检查来源；同时仍读全部三角索引，并检查被排除对象的 referenced 坐标有限性。不能宣称 cold 获取成本仅 O(N)。 |
| `surface_proximity.py:15–20,632,715`；`task_query.py:253` | 可直接复用表面距离、精确距离平方 key 及 pair 缓存；每对最多 4096 面、16384 narrow pairs，另有 work/bit 预算。阈值分类不能比较已四舍五入的展示距离。 |
| `surface_proximity.py:841` | spatial_relation 先 surface，再支持分离证明，失败才闭壳分类；无需为本次纯表面问题执行 solid。后续实体任务可复用，但不是本批顺带验收。 |
| `read_context.py:25–83`；`scene_cache.py:171–181,408` | 8 selections/每 selection 16 results；generation 改变清掉读上下文；pair 快键含 selection/generation，跨场景 revision 的无关 pair 也失去命中。partial/unknown 结果缓存不会自动续查。 |
| `scene_residency.py:62–77`；`blender_host.py:536,569` | 已有 resource revision、dirty、pose 复用和 scene epoch；sync 会清 capture/nearest。一个姿态变化不必重建静态网格，但服务端 pair 键仍随全场 generation 变。 |
| `live_service.py:365,519,1389`；`blender_mcp_host.py:251–290,512` | 请求预算从入口开始；host deadline 只能缩短剩余预算；过期会异常，最终 MCP 发布还检查。不能每 pair 续租，不能过期后把未交付 partial 记成完成。 |
| `auto_router.py:267–290` | complete scene/selected/nearest 三种 scope 严格区分，nearest 最少 1 mesh；新扫描可能全部被界排除，必须显式支持“完整目录＋0 个展开对象”，不能制造一个假焦点。 |

## 3. 冻结一个有限合同

建议公开 query 仅新增 `mode=surface_scan`、`threshold_m`，范围首版固定 `current_scene_meshes`，包含隐藏 mesh，采用 `_objects` 的全目录语义。示例：

```json
{"session_id":"…","include_image":false,"query":{"mode":"surface_scan","threshold_m":0.002}}
```

不接受 focal/reference/objects/candidates/goal/scene_delta，也不要求模型组合 requested_facts；不另增工具名字、任务注册、规则 DSL、resume token 或新服务。现有 `_QUERY_SCHEMA.threshold_m` 为别的入口带有 `maximum=0.01`；实现时应使用 mode 专属约束，不无意继承该上限。首版规范化为有限、非负 binary64 米值；布尔、NaN、Infinity 和负数拒绝。阈值 0 合法，表示表面相交/接触集合，仍不认证正体积穿入。

给定当前目录 U（1..256 meshes），无向全集 `P={(i,j):i<j}`，数量 `N(N−1)/2`。已绑定几何表示的三角并集表面距离为 d(i,j)，匹配谓词固定为 `d(i,j) ≤ τ`，边界包含。阈值和坐标的数值语义是工具实际接收/捕获的有限 binary64 值；使用其精确有理表示比较 d² 和 τ²，不先开根或舍入再比较。已有 `_exact_distance_sq`/`_compare_distance_keys` 足以复用，新增小转换/比较 helper 即可，不重写距离算法。

实体语义必须在一句话中明确：**“扫描当前三角表面距离；距离不是穿透深度，本结果不判定实体穿入或包含。”** 完全包含的两闭壳若表面距离大于 τ，在本任务中是合法不匹配，绝不由此宣称无碰撞；表面相交 d=0 也不自动等于实体正体积重叠。开放但有效的三角表面可以有距离；无效/退化或预算不足按 M3 返回 unknown。

若根任务决定必须问“所有穿入/包含或间隙不足”，应改成另一个明确谓词并重新冻结本批：AABB 严格分离距离大于 τ 才能整体排除；AABB 重叠者必须继续判实体关系，即使 surface d>τ 也不得排除。包含场景没有可用的“表面很远所以实体没问题”证明。这会增加闭壳资格与分类成本，当前不建议同时装入第一批。

最小公开输出：`status`、上述语义、实际阈值和范围、全部匹配 pair 的对象 ID/名称/距离/见证状态、coverage 计数、unresolved 原因摘要和 binding。对象名称只作输出标签，不参与发现或优先级。负例不逐条塞给模型；完整 pair disposition 留在可审的结构化诊断。匹配不可 Top-K 截断；若输出预算不能完整交付，应明确 partial/输出受限，不能标 complete。

状态计数恒等式：

`total_pairs = bound_excluded + measured_match + measured_nonmatch + unknown + deferred`

- `complete`：目录/快照有效、每对都精确分类或有适用严格排除证明，unknown=deferred=0；允许匹配为空，允许单对象 total_pairs=0。
- `partial`：全集已绑定，仍有 unknown/deferred；所有已证匹配可交付，但不能说“全部”。
- `unknown`：全目录/来源绑定都未完成，或完整快照不可获得；不编造漏检分母。
- witness/direction 不足单独保留，不必把已有有效的数值阈值分类抹掉；零距离方向为 not_applicable。主固定输入仍要求所需见证有效，避免用弱证据通过质量门。

## 4. 一次本地候选调度与获取

### 4.1 获取和宽筛

在现有 host 中增加一次有限 `capture_surface_scan_candidates(threshold, deadline, max_response_bytes)` 命令，仿照 nearest 的同窗口协议，而不是 service 先 RPC directory、再为每 pair RPC task。

1. 同一同步主线程窗口获取 graph、unit、完整对象目录、document/object incarnation、frame、source；沿用首版静态独立三角源资格。不要悄悄跳过不支持对象后称全场 complete。未知 bounds 不排除。
2. 每对象获取 evaluated local bbox，经已有 outward affine helper 得世界包围界；不需要 nearest seed/witness 上界。N≤256，直接枚举上三角最多 32640 对，已有 `_acquisition_lower` 的 L∞ 下界 L 足够。`L>τ` 才排除，等于阈值保留。中心距离、当前 active、显示顺序不作排除条件。
3. 非排除 pair 的 endpoint union 只展开一次，复用 `_resident_capture` 的资源/pose 和 wire delta；同一对象出现在多个 pair 不重复采集。首版静态阈值不会在测量后收紧阈值，故一次 union 获取比为了“按需”制造多次 host 往返更简单。选择 union 是按任务需要展开，并不承诺每个候选只读局部三角。
4. 保留现有输入有限性/拓扑来源检查和 source-change 检查；记录这些成本。使用 API bbox 可省完整 world transforms、复制和传输，但 cold 仍可能 O(F_all+V_excluded_referenced+V_retained)，不是跳过远物体的一切读取。被包含对象的 bbox overlap 使 L=0，天然保留，不会被正阈值宽筛丢弃。
5. packet 同时带全目录 binding、候选 pair、各对象 bound 状态、selected union 捕获和精简计数；新 scope 必须命名为扫描候选，不借用完整 scene 或 nearest scope。零候选时只交目录和排除覆盖，不调用要求非空 mesh 的 normalize。主窗口只获取，不把长精测循环塞进 Blender 主线程。

主风险是 Blender API bbox 的包围前提，不是浮点比较。沿用 nearest 静态域是最小风险方案；输入资格时对独立导出的全部顶点检查该包围前提并保存证据。invalid/missing bound 一律候选保留。若要使用现有通用 evaluated modifiers，需要扩大域并独立验证，留到真实需求触发后。

### 4.2 服务内求解与停止

一次 `ReadContext.activate` 后，正常化 union 一次。候选可按 `(lower_bound, estimated_face_work, canonical_pair_id)` 排序；排序只影响有限预算先做谁，不影响完整集合和完成证明。估计 face work 只能用已有目录计数，不能为排序先精算全体。优先复用缓存命中，剩下调用 `_surface_pair_measurement(... retain_exact_rank=True)`。

每对最多一次新 M3 调用，跨 pair 没有模型或 host RPC。按实际精确数值分类并更新 coverage；不要求返回全场排序，不动态缩小阈值。现有 M3 每 pair face/work/bit 限制继续成立，未被支持的 pair 进入 unknown。

保留现有请求总 deadline、host timeout、bridge payload 上限和 M3 每对预算。第一版内部可复用 255 次新精测的工作上限；这不是返回 255 个异常，也不是只枚举 255 对。全集仍是 N(N−1)/2，被 cap 留下的 pair 为 deferred；缓存命中、严格界排除不耗新精测次数。不要把 legacy 参数的上限直接套成场景完整性的上限。

硬超时仍走现有 RequestBudgetError，不承诺过期后成功交付 partial。要可见地验 partial，使用确定性 pair/work cap，在尚有发布预算时结束；若用软时间截止，必须预留/计入编码交付成本，不续 deadline。计时覆盖获取、求解、包装、实际发布，失败保留在分母。partial/unknown 不由普通结果缓存永远锁死：缓存终局数值和已证排除；未完成扫描可重建队列，不能把旧 partial 的原封命中说成续查成功。本批无需跨请求自动后台扫视或新恢复协议。

### 4.3 最少状态与后续复用

状态挂现有 ReadContext：当前 directory generation、规范化任务参数、pair dispositions、现有 scene_cache。最多保留当前扫描/已有有界 selection，不为每次调用永久落盘，不复制全量几何进新“扫描数据库”。

静态同请求先以当前宿主版本验证后命中，期望新资源展开=0、新精测=0；不能因模型再次问同一题就直接使用未经当前版本核对的历史文本。

首次实现可沿全 generation 保守失效，以最少改动取得正确闭环。初版审查中记录单对象刚体移动后：哪些 resource 没重建，哪些无关 pair 仍被重算。**预计的唯一追加优化：把本扫描的表面 pair 缓存依赖缩到各自对象，而不是整个 selection/generation。**

做法是将已有 host resource id/revision、object incarnation、matrix/scale、document epoch 通过现有 delta 解码保留为内部对象版本，扩展 scene_cache 的受信 surface-measurement 快键；再加算法版本与实际数值参数。不得仅按名称、同面数、矩阵或全场 revision 猜几何没变。普通旧实体缓存维持原合同，不给所有算法删所需 metadata。

场景目录变化后仍重新生成当前 pair 集合；一个对象移动只使关联 pair 的 bounds/测量失效，不复用旧 world witness；未变对象对的精确距离可直接复用。阈值变化可以复用精确距离而重新分类；排除证明不能跨较大阈值盲复用。删除去掉对应 pair；名称/active 变化更新标签但不凭标签选候选。undo/load/换 document epoch 沿现有 reset 全失效，首批不承诺跨撤销保留旧证明。一次冷建和每次廉价目录枚举可以存在，“不每次全场重算”指不重展开/重精测未变几何，不能假称根本不检查场景。

已有 triangle BVH 建在 pair 的整数坐标框架中，不应在本批顺手改成跨 pair 全局 BVH。N=24 的数组宽筛足够，未见瓶颈不加对象树或学习排序。

## 5. 最小实现接点

| 文件/边界 | 必要改动 |
| --- | --- |
| `query_policy.py`、`live_spatial_mcp.py` | 一个新 mode 的验证/schema；禁止显式对象选择；新 result_kind 的 complete/error、直接结果和发布预算接线。避免复用其他 mode 的 threshold 限制。 |
| `live_service.py` | 新增类似 `_observe_surface_nearest` 的小分支；一次 host capture、一次 ReadContext、一次结果编码。 |
| `blender_host.py` | 在既有获取辅助函数上组织 all-pairs bounds 与 union capture；提取必要共用 scope 参数，不能复制一整套 nearest。 |
| `blender_mcp_host.py`、`blender_process.py`、`blender_worker.py` | 同一有限命令的参数白名单、deadline 和 delta；覆盖实际支持的两条宿主接线，不能只把测试内 mock 接通。 |
| `auto_router.py` | 窄范围新增扫描 capture scope/0..256 union 的验证，保持完整目录 identity 与 union identity 分工；不走旧 focal router。 |
| `task_query.py`、`surface_proximity.py` | 新小 scan result reducer、精确阈值 helper；复用现有表面 solver，不改固体算法。 |
| `read_context.py`、`scene_cache.py`，必要时 delta 内部元数据 | 初版有界覆盖状态；优化轮按实际 trace 加 per-object surface key，复用现有缓存，不新增服务/第二份几何仓库。 |
| runtime source manifest/冻结材料 | 按仓库现有身份规则更新受影响源；这是具体候选交付的一部分，不在每次扫描现场重验所有源码。 |

这不是一个只改两行的扩枚举，但改动集中在既有获取—查询—结果链。可暂把扫描 reducer 留 `task_query.py`；若过长才拆一个普通 Python 模块，不建立通用任务语言。

## 6. 唯一固定问题与输入资格

拟定一个 **24 mesh 的小型导轨/支架装配单元**，不是 12 组相互独立盒对。组成可固定为：底座 1、长导轨 2、U/L 支架 4、滑块 2、盖片 3、垫片 4、止挡 4、销/隔套 4，共 24；静态、独立、显式三角化，适用原生与插件同一份 `.blend`。装配接触是匹配，不先称“异常”。对象名称用中性编号，不能暗示 near/fail/target。

几何包含细长斜件、U 形局部凹槽、薄片、至少一个开放但有效表面；共享空间有多对象交互。应有重叠 AABB 但表面分离的正常 pair，以及严格包含且表面间隔大于阈值的控制 pair。后者用于验证没有把 surface_nonmatch 解读成无实体穿入。问题区域不能只邻接 active object，至少一处有效匹配位于另一个装配子区。平移/旋转不依赖随机无限抽样。

唯一消费者提示：**“检查当前场景全部网格对象，列出所有两对象三角表面最短距离不超过 2 mm 的对象对及距离，并说明检查是否完整。这里仅要求表面距离，不要求判断实体穿入或包含。”** 提示中不透露对象数、名称、匹配数、答案或 Top-K。

资格步骤在消费者前、同一问题冻结一次：

1. 原生只读导出实际求值世界坐标、triangle indices、对象 incarnation/名称映射、unit 和 frame；冻结 `.blend`、导出、生成脚本和源码 hash。建议总面数约 600–1600、每对象≤256、每 pair 低于现有 4096 门；最终按实际可独立核验规模冻结，不能通过增面数无限加难。
2. 全体 276 对都建独立真值，而不是只验证算法返回 pair。现场统计 broad retained 和精测负例：应有明确数量的 L=0 但 d>τ pair，以及 d≤τ 真匹配；至少四分之一 pair 需要超越 cheap bounds，且不能仅靠增加远处盒子构造收益。此为输入难度资格，不是预给消费者的异常数量，也不是候选召回的替代分母。
3. 场景应确实存在既可被界排除、又须精测的工作。若实际全部极易筛或全体超过本批现有工作 cap，给出不合格原因，最多一次按预声明形态修正；在跑模型或性能候选前冻结。不能观察 P/N 输赢后换阈值、换对象或调真值。
4. 固定一个已在该装配中的局部对象刚体移动，以及静态重问，作为连续状态序列；新状态也有全部 pair 真值。删除/撤销/换 epoch、invalid bounds、低预算、阈值等号/紧邻两侧只作定向工程合同测试，不额外衍生模型题。

### 独立真值与漏检分母

独立 oracle 不 import 产品 `surface_proximity`、`surface_geometry` 或产品候选清单。对实际导出的三角面做穷举 triangle-pair 精确距离，另写独立的相交判定与点面/边边距离逻辑；用导出 binary64 的有理值保留阈值比较精度。它可以慢，运行一次用于冻结，不进入消费者输入或性能计时。主场景中的平面间隙、相交和包含控制再用解析构造值交叉核对，oracle 的单一实现不自动等于真理；分歧先解决，不能由产品结果决定 oracle。

若精确穷举在上述面数下成本过高，先减少不影响目标形态的重复三角化；不使用产品 BVH 作为“独立真值”，也不缩小到产品候选集合。资格阶段保存 oracle 资源/完成状态，不能把超时 pair 当阴性。

真匹配集 T 来自这 276 对；候选召回 `|T∩C|/|T|`，最终召回 `|T∩R|/|T|`，误报 `|R−T|`。同时核对全部阴性、重复 pair、unknown/deferred 和 complete 真假；不是仅报告返回项准确率。主场景通过条件：T 中无漏检、无误报、无意外 unknown/deferred、全部匹配距离及必要见证正确；消费者漏列/重复/误称完整计失败。若 matched 集为空另测单独工程边界，不能用空真值的“召回100%”证明主发现收益。

## 7. 公平比较、一次优化和停止

原生 N 与插件 P 使用同模型、提示、同一资产状态、相同通用 Blender/Python 工具、同总预算；P 只额外获得正常插件入口。N 可批量导出所有 mesh、用数学库/BVH/缓存，自写一次本地循环，无须每 pair 发 RPC；不故意给 N 低效脚本或禁止已有脚本复用。oracle/生成时标签/候选名单不给任一消费者。模型自行调用目录或补查的成本保留，不能试验者提前选好 union。

冷态比较包括插件启动、工具 schema、host 获取、几何求解和回退；持续使用双方保持各自真实进程/脚本/缓存。若已经有同类合格原生扫描脚本，N 可使用，其准备状态须明示；不能每轮强行让 N 从零重写而 P 始终常驻。第一次开发成本与后续使用成本分列。

顺序建议：

1. 输入资格/合同冻结 → 初版正常入口贯通及必要工程反例 → 独立源码/全体真值/完整成本审。
2. 同固定输入，记录 cold、静态重复、局部移动的分段工作。只有初版 trace 实际显示无关 pair 重算，再实施第 4.3 节的依赖键优化；若没有该成本，按 trace 指向的最大冗余选择一个替代点，不为“必须优化”改无关代码。
3. 初版/优化版使用相同状态序列，本地配对比较 kernel_calls、展开 vertices/faces、transforms、wire bytes、内存、总服务时长；质量保持全体真值一致。独立再审确认被消除的工作，不只看作者 PASS。
4. 本工程批到独立复核材料即止，消费者为 0。根任务复核后再固定最终候选及有界 N/P 消费预算，验证冷态和同一状态序列的连续使用。重复同一问题只能定位能力/成本，不能算多个独立任务或替代正式广域验收。本报告未启动或预授权任何 API 调用。

完整记录至少包括：模型全部累计 input/output/total usage、所有工具调用、图像=0、首请求至实际最终回答墙钟、失败/超时/回退，及 host 同步窗口、to_mesh/triangulations/transformed vertices、bound pairs/retained/每对 solver work、cache hits、编码量和内存。一次工具结果或某个函数变快不能替代完整任务收益。

质量先过，再按批准计划的中等任务目标检查完整任务配对中位耗时是否至少降低 30%，并报告实际 token 比率；若样本不足，仅写“本固定问题达到/未达到点目标”，不声称统计性泛化或 p95。失败/遗漏/超时仍在总体分母，速度只列双方正确完成的 pair 并注明覆盖率。token 不承诺凭压缩下降，未提供的费用记未测。

停止条件：输入和真值已冻结；初版与一轮有根据的实质优化均经独立审；普通入口无目标发现完整且机制计数兑现；本固定问题质量与成本结论明确，即收口。性能未达标时把剩余最大成本交根任务决策，不改阈值、不追加具名变体或扩大模型轮次。相同瓶颈连续两个候选无收益即重审假设，保留较优候选。下一独立批才能检验图像/遮挡/换视角，本批不能称“主动视觉已完成”。

## 8. 根任务可以直接采用的决策

优先派 **“M4-SURFACE-SCAN-001：固定 24 对象全场表面阈值输入资格＋最小扫描实现”**，在同一派单中把资格材料作为实施前置。若根任务当前只允许设计/资格，先交冻结资产与 276 对真值清单即可，后续工程不需要重新挑题。本设计首选纯表面阈值，原因是现有 M3 可直接满足、独立全体真值可列、包含语义能够清楚隔离，且可以实际测量发现/往返/驻留收益。

没有已生成资产、真实候选密度和 oracle 结果之前，不应把这里的面数或收益写成已通过，也没有新增消费者预算。可实现性来自已读代码；性能、完整召回与普通入口实际接通仍待下一批证据。
