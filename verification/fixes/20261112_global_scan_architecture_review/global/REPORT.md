# 全场空间扫视与候选发现只读源码审查

审查日期：2026-11-12。父任务：b67eb704-e56b-472c-811a-5f50f165c006 / revision 1。子 assignment：ea0d6b53-5604-48a6-a15e-95ba0d33269b；已用自身 context_handle 核对 parent_read_only。本次不运行产品、Blender、模型、测试或 API，不修改实施树。只读源码及保存证据，写入本报告。

## 固定身份和结论

实施树：`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`。观察 HEAD：`a44a6138b9d354ecc98a4fbd76095f0536d6973f`；固定产品提交：`e836e03f4b3821f869c72ac3e50df5204f28b50f`。读取时 `git status --short` 为空。对 `verification/m3_sufficient_separation_001/CANDIDATE_FREEZE.json` 的 137 条运行源逐一用 Get-FileHash 核对，137/137 一致、0 不匹配。固定聚合摘要是 `2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390`；本次核对的是冻结清单中每份实际文件，未导入 runtime 模块重算聚合摘要。两提交间所检查产品目录/根 bridge 无 diff；HEAD 后续提交主要为证据。

**当前有完整场景目录、有目标相对全场的最近查询、有保守宽筛和局部精测，也有目标对视角择优；没有从无目标全场发现出发，自动维护候选优先级、按需精测、更新已查覆盖并证明停止的统一扫视循环。** “目录 complete”“某 target 的 nearest complete”“指定三候选集合 observed”“全场景问题已找全”是四个不同命题。

固定源码清单及已存验收：

- [冻结清单](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m3_sufficient_separation_001/CANDIDATE_FREEZE.json:5)
- [固定版本公开报告](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m3_sufficient_separation_001/REPORT.md:7)

## 实际入口与能力边界

普通工具 `human_eye_scene_observe` 由 [live_spatial_mcp.py:858](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:858) 调用 `LiveSpatialService.observe`。公开 query 枚举位于 [live_spatial_mcp.py:70](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:70)，是 directory/task/surface_nearest/overview/exact_pairs/nearest/top1/mesh_structure/mesh_surface，没有独立 global/broad/regions 全场发现模式。这里的 broad-phase 是内部剪枝算法，regions 是目标网格诊断的输出/选区概念，不宜按名称等同整场扫视。

| 入口 | 目标要求 | 实际完成的事 | 不能外推 |
| --- | --- | --- | --- |
| directory | 无 target；要求 include_image=false，无 instruction/pair/goal | 全部当前 mesh 的 tight evaluated 世界 AABB、center、来源绑定及目录覆盖 | 没有对象关系、异常候选、优先级或后续查询 |
| overview，无已解析 pair | 可无 target | 捕获完整 scene，给 bounds/图片/能力信息 | query complete 只是 overview；attention hold，不能认证 nearest/碰撞/问题发现 |
| overview，已解析 pair | 要有可绑定 pair；空指令可依赖配置/active/仅剩对象 | 围绕 focal 的邻近宽筛、所选关系测量及局部注意力 | 非任意对象对全场扫描；远离 focal 的对象间问题没有检查 |
| exact_pairs/nearest/top1 | 要有 focal + reference；可选 object_ids | 对指定集合或 focal 外全部对象的精测/排名/最近证明 | 无 pair 时 unknown；不是无目标任务选择 |
| surface_nearest | 必须一个 focal_id 或一个 query.objects selector | 同一 host 读窗口里扫全场边界/见证点、排除不可能最近者、精测保留者并排名 | unsigned 表面最近；不是所有穿入/凹槽/语义异常；静态独立三角网格限制 |
| task | 显式 objects，或 target + 1..3 candidates | 一次选择性捕获、事实计算和集合内完整性 | 候选是谁由调用者提供，集合 complete 不保证全场候选召回 |
| mesh_structure / mesh_surface | 受信注册对象，query 可省焦点但注册状态带 object_id | 该对象拓扑/表面/局部图等有限工作 | 省略 query target 不等于自动选择全场目标 |

关键接线：

1. [live_service.py:1048](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_service.py:1048) 对 directory/surface_nearest/task 直接分支返回；没有先调用 directory 后继续调度的环。
2. [live_service.py:1094](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_service.py:1094) 普通 overview 先 `capture_scene()`，随后才解 pair。[live_service.py:1136](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_service.py:1136) 无 pair 时走 `_overview`，attention 原因 `contact_pair_not_established`，精测 0，非 overview 请求 `query_pair_required`。
3. [live_service.py:950](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_service.py:950) 空指令下的旧选择规则允许配置名/唯一 active 和唯一 remaining object。非空自然语言不会默选，交 [prompt_pairing.py:217](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/prompt_pairing.py:217) 解析两个显式描述的对象；歧义/未知词保留 unresolved。此策略安全，但不能解决“看看哪里有问题”的非指向性定位。
4. [task_query.py:58](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:58) 限定 target + 1..3 显式候选；[live_service.py:1457](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_service.py:1457) 选 capture_task_scene；[task_query.py:436](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:436) 按请求顺序逐对求解，coverage 仅 requested_candidates。
5. [structure_task.py:67](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/structure_task.py:67) 注册 object_id；[surface_task_service.py:86](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_task_service.py:86) 绑定注册对象。

## 宽筛、排序与精测的实际算法

### 目录不是零成本元数据

[blender_host.py:1134](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/blender_host.py:1134) 的 cold directory 对每个对象 evaluated.to_mesh，再逐顶点转换世界坐标、求 tight AABB（1165–1197）；不复制完整 faces 给服务，但仍是 O(V_all) 顶点遍历，外加 Blender 求值成本。预算为 500000 顶点、1000000 三角估计，宿主总体为 1..256 meshes（680–694）。缓存相同代目录可命中（1152–1157）；只保存完整独立目录，不建立 complete-scene/action baseline（1212）。因此既不应说目录已实现“只读几个 bbox 的常数成本”，也不应因其读取全体顶点而说已诊断全体几何问题。

### 旧 SpatialSceneIndex：保守，但不是空间层级树

[spatial_index.py:59](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/spatial_index.py:59) 对全场建立 AABB 并检查每个对象 solid support；bounds 至少 O(V_all)，支持检查成本额外。`query`（110–174）向量化地比较 focal 与所有 N 对象，O(N)，没有 object BVH 或网格分区。未知支持、无效数值、forced reference 全保留；其余按 outward L∞ lower bound 判定。该保守性不会把未知对象伪装成已排除，代价是稠密/重叠 bounds 时候选接近全量。

[auto_router.py:900](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/auto_router.py:900) 的 overview 半径是 focal bbox 对角线的 25%，reference 强制保留；精测按 reference 首位再 requested/scene 顺序。它筛的是 focal 邻域，不保证别处问题召回；这不是“漏掉已声明全场检查”的代码错误，而是任务范围根本不同。default overview 仍用 collective work admission，超预算可整体 block（920–941）。

### 旧 top1 已有可复用的自适应证明调度

[top1_query.py:38](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/top1_query.py:38) 先精测 reference，再按有效 lower bound / object_id 排序；每测一次更新 best，后续仅在严格 `lower > best + outward guard` 时跳过。等距并列不被剪掉。max_exact_pairs 包含 reference，默认 255；不支持/预算未做者在 [top1_query.py:79](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/top1_query.py:79) 从实际返回 evidence 重算 unresolved；只在所有 requested 已测或被证明排除时 complete。排序成本 O(N log N)，精测数取决于下界质量，最坏仍 N−1。

它仍要求 pair、先发生全场 capture 和 support 检查，只认证非穿入的旧 signed_clearance 最近关系，不能直接改名为新 surface_nearest。可重用的是“下界队列 → 精测 → 收紧 best → 严格排除 → coverage”的调度形式，必须沿新表面距离合同复核数值和并列语义。

### 新 surface_nearest：已有全场候选获取，但宽筛只做一轮

[blender_host.py:1227](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/blender_host.py:1227) 在同一同步 host 主线程读内扫描全部对象。1291–1304 拒绝 parent/children/modifier/animation/shape keys/linked/edit 等，并要求静态三角面。每对象读取 evaluated bbox、一个真实三角见证；对 focal 与各 witness 的 3×3 顶点组合求 L1 上界，挑最小 seed（1325–1342）。以 outward AABB L∞ 下界和严格 `lower > upper` 排除对象（1353–1365）；未知 bounds/witness 保留。此种真实点上界加保守下界在声明域内不会因中心距离启发式漏掉最近对象。

但 upper 在实际精测前就固定；保留者一次展开成选定 scene。服务 [task_query.py:603](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:603) 随后**按 object_id 排序精测全部 retained**，最后统一 rank，没有用第一个精测结果的新上界跳过后续者。第一次采集的上界来自单个三角，可能很松；近邻密集、细长/旋转/凹形 bounds 大量重叠时，lower 常为 0，宽筛自然变弱。不能把这个特征描述成已证明数值错误，但它清楚解释“全场对象一多仍花很多成本”。

此路径也不只是 O(N) bbox 读取：全部对象遍历三角索引，排除对象另查全部被引用顶点有限性（[blender_host.py:318](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/blender_host.py:318)，1359）；随后保留对象被完整捕获。冷成本含 O(F_all + V_excluded_referenced + V_retained + F_retained) 及求值/元数据成本，不能宣传只展开候选就完全不读远物体。

`surface_nearest_result` 在 618 以 best 非空且无 unresolved 才 complete，否则 partial/unknown；639–642 明确 unsigned_surface_distance_not_penetration_depth。这是真实的一次请求内证明终止，但不含跨请求未查 frontier/自动续查，也不是非指向性全场发现。

### 精测已有 BVH，应避免重复造基础设施

[surface_proximity.py:464](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_proximity.py:464) 已用 priority heap 做三角树对搜索，以当前 best 的精确 AABB/plane lower bounds 剪枝；小输入走 linear（522）。[surface_geometry.py:122](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:122) 中位分树，每节点重复 sort；按代码推导一般最坏构建 O(F log² F)，树对搜索稠密最坏仍趋近 O(Fa·Fb)，并受 work/face/narrow-pair 门限制。不能把“有 BVH”当全局无二次风险，也不宜把改算法的唯一建议写成“再加一棵 BVH”。

[surface_proximity.py:841](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_proximity.py:841) 新 spatial_relation 已先复用一次 surface 求解、再沿公开见证方向检查全部 referenced vertices 的严格支持分离，失败最多回退一次闭壳分类，预算停即 unknown。应复用这一条适当充分证明路径，不让无关候选默认先做完整闭壳资格。

## 为什么现有 attention/goal/cache 不等于扫视循环

- [attention_policy.py:293](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/attention_policy.py:293) 只接收已有测量 contacts，筛正间隙、见证可用、相对尺寸范围内的项；reference 优先、distance 次优，只考虑最多 4 个 contact（334）。这是“已有目标证据怎样看得更清楚”，不产生全场未测对象间问题候选。
- [support_plane_discovery.py:76](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/support_plane_discovery.py:76) 扫指定 reference 原三角并要求已给 focal/reference，scope 明确 current_represented_pair_original_support_planes。不是任意对象的“支撑关系发现”。
- [goal_scheduler.py:148](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/goal_scheduler.py:148) 和 [goal_execution.py:402](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/goal_execution.py:402) 的自动环受既有 focal/reference/目标约束；存在 goal while-loop 不证明无目标感知环存在。
- [read_context.py:25](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/read_context.py:25) 保存每 generation 最近 8 个 selection、每 selection 16 个 result。包括 partial/unknown 的原状态（result 方法）；重复同请求会命中旧结果，并不会自动完成先前未知部分。
- [scene_residency.py:62](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/scene_residency.py:62) 有对象资源、capture、nearest cache 和 generation 失效。这是可复用底座，不是“未查/已排除/已精测/未知”覆盖账本。无需再建立另一套常驻 scene 服务。

## 工程证据与未证明部分

已存 [RESULTS.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m3_sufficient_separation_001/entry/run_01/RESULTS.json:1) 的原 MCP request/response 可直接读出：directory 完成 14/14 mesh bounds；随后的 spatial_assembly_task 是预先显式 target + 3 candidates，observed、3/3 classified；legacy_assembly_task 同样三候选却 partial、0 classified；control 显式 1 candidate，observed。保存调用时长分别 53.4671 / 2353.4085 / 3357.6478 / 36.7750 ms。它证明该固定版本普通入口可接收、执行这些有限请求，不能证明模型自动找出三候选，也不能由 14/14 目录覆盖推出所有对象对事实完整。

报告所述 230 方法、六十次成本及收益属于已有工程记录；本次没有重跑，未把它们当新独立验收。该批公开报告末段明确默认激活与模型消费者未进入验收。旧 nearest/top1/source 中存在相应测试文件只是源码存在；本审未由测试文件名推断历史已通过。其他历史模型消费与视觉轮次由父任务其他子审处理，不在此重复推定。

## 最小改进路线与可验收收益

唯一优先主线应是**把候选发现和覆盖调度接入现有只读 observe，复用既有来源、驻留、宽筛和精测，而不是继续堆独立包装层**。以下属于未来实现建议，不改变正在做的凹槽资格任务。

1. 先补一个绑定当前 generation 的有限候选队列。输入是“检查哪类可计算关系/阈值/范围”，target 可选；无 target 时枚举全场该关系的对象候选，有 target 时直接复用 surface_nearest/bounds。不要把语义“不好看/损伤”等未知任务硬转成距离。每候选至少保留对象/区域来源、下界、所需事实、状态与原因。N≤256 时可先用现有 AABB 数组形成去重无向对，明确 O(N²) 最坏成本并计费；只有实际瓶颈出现再改对象层树，不能先增加新索引服务。
2. 将 top1 的自适应策略内联复用到新 surface_nearest 的事实调度：用当前 lower 排序，先测 seed/最有希望者，每次用新真实距离收紧界，后续严格排除；未知及等距保留。第一步即可在同一已捕获 retained scene 内省窄相，保持 host 单次捕获合同；要进一步省捕获，再在同一受信读窗口/同 generation 上按需 materialize，不能用第二次任意捕获冒充同快照。
3. 覆盖状态直接挂在现有 ReadContext/scene residency generation 下：unseen、bound-excluded、measured、unknown、budget-deferred；同一未变对象对不重复求解，有变动仅重新入队受影响候选，source/epoch 变化使相关证明失效。未知不是已查正常。视觉仅按事实缺口或不可读证据按需补，勿每候选默认渲染。
4. 仅在 task-required 集合全部有结论或有适用排除证明时 complete；最近问题采用 frontier 最小 lower 严格大于 best 的停止证明，阈值问题采用每候选 lower 大于阈值或精测结论，预算停止返回 partial 加剩余覆盖。视觉/结构/语义任务的停止条件应各自独立，不共用“没有新候选”充当全场无问题。

最低验收：同版普通 MCP，任务提示不给目标名/ID、候选名/ID、面号；至少放入远离当前 active 的问题、中心距离误导的细长/旋转对象、重叠 AABB 但分离、等距 ties、包含、开放/退化、未知/预算停止、场景局部编辑。固定真值检查候选召回和最终遗漏，不只检查返回项准确率。保存每步候选总数/排除/精测/未知、cache 命中、host 捕获和展开量、窄相工作与图像数。先证明全过程来源和 coverage，再验证同任务模型首次定位成功率、错误/漏检、总调用/总时长/实际费用；不得用函数局部快了替代完整任务收益。

候选路线最值得先验证的收益是减少“模型猜一个对象 → 发一次查询 → 发现不是 → 重新猜”以及 dense retained 中已经不可能胜出的额外精测。现源码能支持这条路线的一大部分底座，但实现、接通、工程覆盖和模型实测需要分别完成。
