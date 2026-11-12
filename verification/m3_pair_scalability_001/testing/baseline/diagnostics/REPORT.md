# SPATIAL-TASK-QUALIFICATION-001：M3 算法边界独立复核

日期：2026-11-12。结论：实际能力缺口成立，但**“删除乘积门并把距离双循环换成现有 AABB 树”不足以完成 G508 装配**。后续应作为一个 M3 成对精测候选，复用精确准备并按实际工作准入；需要同时面对正距离下界不够紧、闭壳自交候选和宽相访问三个问题，不能按每撞一个门就加大常数的方式推进。

## 本轮独立做了什么

- 只读核对实施 HEAD `93121974595badc90944d5353d23ae7897feda54` 的资格报告、实际响应和固定产品源码。产品仍为 `fac9b4373575d653cc96f39f1dcb225300cd5977`。
- `diagnose.py` 独立核对137项当前源码与隔离安装均等于冻结 manifest 字节，摘要 `6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb`；核对实际 entry SHA256。执行的是从已核字节编译到独立合成包的两个几何模块，没有运行包初始化或安装入口。
- 从正式 `ACTUAL_SNAPSHOT.json` 构造相同世界 binary64 顶点和三角输入，原样函数独立复现三对 surface/closed 的提前乘积拒绝。随后做有界、明确标注的内存门限诊断及静态计数，证据列于末尾。
- Blender、模型、付费调用、新安装与产品改动均为0。没有重新进行实际入口验收；作者的公开链/控制通过与本轮离线复现分开。子 AL 句柄恢复为 parent_read_only 且 assignment 已过期，未覆盖父任务。

## 真实剩余瓶颈

原样 `_admit` 在准备前拒绝，独立结果与公开回执一致。只在诊断进程中取消这一个理论乘积门后：

| 对 | 旧距离访问全部三角对 | 实际窄相交入口 | 完整特征测试合计 | 原闭壳的下一拒绝 |
|---|---:|---:|---:|---|
| Target / Peer_000 | 258064 | 18791 | 620103 | self pair=16384，cross/ray=0 |
| Target / Competing_001 | 30480 | 1048 | 34584 | self pair=16384，cross/ray=0 |
| Target / Near_003 | 30480 | 4012 | 132396 | self pair=16384，cross/ray=0 |

特征合计为 point-face、point-edge、edge-edge 三项真实计数。Peer 的旧距离诊断约2.98秒，只是本机一次算法归因窗口，不是候选性能或完整任务收益。

进一步仅为诊断放开 closed pair cap，保留原262144总工作门，Peer 又在总工作门停止：self=40230、cross=3218，仍未开始 ray。其余两对可完成 separated，但分别耗25580、27991对，已越过原 pair 上限。因此旧 gate 后面确实还有真实工作量问题。

**AABB 树也不能单独解决新的窄对限制。** 用已完成穷举的最终最优距离作事后固定上界，逐对检查当前精确 AABB 后：

| 对 | 最终 best 下 AABB 仍保留 | 再加严格三角平面距离下界后仍保留 |
|---|---:|---:|
| Peer_000 | 18146 | 7250 |
| Competing_001 | 1001 | 333 |
| Near_003 | 3766 | 1072 |

Peer 即使一开始拥有最终 best，单靠现有 AABB 仍超过16384；真正近优先搜索只可能比这个理想计数更多。这是选择更紧廉价界的证据，不是候选能达到7250的证明。

闭壳方面，提取原有严格平面排除，再加下述有证明的共享 simplex 证书，Peer 的完整 `_intersection` 潜在可由57638降至12737；但原树准备、节点、叶访问与剩余谓词本体已约322387工作，尚未加新便宜证书或 ray，仍超过262144。**邻接证书可以减少完整交点工作，但不能单独承诺完整闭壳通过。**

我还静态检查了“在现有世界树补3条从首三角导出的精确投影 slab”这一看似简单的加强：Peer 的节点/叶访问只略降，额外轴测试约269044次；证据不支持采用此补层。该方向不纳入最小候选，不据此新增 OBB/kDOP 通用模块。

## 当前接线与可复用内容

源码位置均为固定实施树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/`：

- `human_eye_plugin/surface_proximity.py:149` `_admit` 同时承担静态输入验证与理论乘积预拒；应分清两者。保留非空、4096总面、索引/非有限值等输入域，替换的是乘积作为工作量的假定。
- `surface_proximity.py:171` 已有共同局部原点、精确 dyadic 整数化、三角法向/边/边长/精确 AABB；新界必须复用这些数据，不重新读取顶点或换 float32。
- `surface_proximity.py:305` `_aabb_exceeds_best` 是可直接复用的严格界比较：用 floor(n/d) 和剩余平方量避免危险乘积；相等不剪枝。当前实际距离循环名为 `_nearest`，位于319行，仍是全笛卡尔扫描，不是已完成的层级 nearest。
- `surface_geometry.py:122` `_bvh` 和132行 `candidate_pairs` 已有精确整数箱体、稳定分割、节点/叶计量。`candidate_pairs(pad=0)` 只能枚举可能相交者，不能直接替代正距离搜索。
- `surface_geometry.py:265` `_closed_topology` 末尾创建 bounds/root；317行自交、392行射线候选、404行精确位置、445行总分类可继续使用原证明链。总工作262144，self+cross窄对16384，ray16384分别存在，不是一项门限。
- `surface_geometry.py:464` 与 `task_query.py:318` 的 holder 已经让同一对 closed→surface 共享 records/topology/origin/factor/prepared 和已发现零距离见证；**树留在 shells 内，当前没有交给 surface**。优先将几何树视为这份既有 query-local 准备的一部分，避免 closed 建好树后 surface 又建一次。树的可用性应独立于“闭壳已通过”，因为表面距离支持开放/退化三角形。
- `task_query.py:268、295` 还有两处乘积条件，作用是绕开完整 pair-cache key 构造，不是第二个测量 gate。更新时保留总面数和 loose-vertex 快速路径；不能把整个 if 删除后让大量无引用顶点先进入全量哈希。
- `task_query.py:437` 的 surface_nearest 最终也走同一个 `_surface_pair_measurement`，没有另一份已实现层级距离内核。默认、保留 exact-rank 和 closed 三种 cache version 当前分别为 `task-surface-proximity-exact-aabb-v3`、`task-surface-proximity-exact-world-rank-v2`、`task-closed-solid-exact-local-evidence-v2`；候选应统一更新语义版本，防止热缓存掩盖新工作。
- `scene_cache.py:408` 已限定同源、相同有序几何/参数的观测缓存，只缓存 measurement_valid，unknown/异常不缓存。无需增加泛用持久缓存。closed cache hit 不会填 holder；surface miss 时仍须合法准备，不能误用旧 holder 或缓存工作计数。

## 唯一候选的算法边界

候选范围限定为 **成对精测的层级候选、共同精确预判与实际工作计量**，继续在现有几何模块和 task helper 内实现，不扩 M2/Hook/工具 schema/写能力。

1. 距离改为已有 BVH 上的近优先双树或三角对树遍历。节点用精确 AABB 距离下界，叶执行当前完整闭合特征公式；保留一个真实已求值 witness 作为上界，不能用 oracle/名义间隙种子。所有未剪枝节点最终覆盖，不能拿 overlap-only 当距离。
2. 提取一次可共享的平面投影数据：若另一三角的三个有符号点距同号，令最小绝对值为 g，本三角法向平方为 n²，则 `g²/n²` 是两三角距离平方下界。仅 `lower > best` 才可剪枝；用于 closed 时严格同号证明无接触。该投影在后续完整交点公式中复用，避免“做完旧 intersection 再换一种计数”的伪优化。
3. 对 self 候选，允许一个薄的合法共享 simplex 证书：另一三角全处同一闭半空间，平面上零点的顶点集合仅为共享顶点，则交集只能是允许的共享点/边；共面共享边则需严格证明两第三顶点位于该边相反开侧。证书不成立继续原精确交点。仅“拓扑相邻”不能跳过几何自交。
4. closed 的宽相访问仍是待实证解决项。应在同一个候选中检查已有树的遍历/叶分块和可证明批量排除，要求**实际减少节点/叶/完整谓词工作**。本轮没有证明哪一种薄改动能让 Peer 总工作降至262144内，不预先承诺；不得通过删除 self、挪计数或扩大上限将它记为已完成。
5. 新计量分别列出准备/建树、节点、叶候选、AABB/平面证书、完整相交、各特征、self/cross/ray；便宜预判也计工作。距离原 `_Work` 只有计数和 deadline，新增实际上限需在候选运行前明确其单位和停止语义，不能测后按 G508 成绩修改。closed 原262144总工作与ray预算保持，若准入语义将pair门限定为未被廉价证书排除的完整谓词，必须明确为支持范围改变。

这是一项待验证候选，允许明确部分事实仍 unknown；若宽相在固定预算内无法完成，交付可复现剩余工作，不循环调常数。业务完成仍要求三对关系/距离/定位及最近结果都通过，不拿“距离已知、闭壳未知”当整项完成。

## 至少一次有证据的简化审查

候选第一版完成后，检查 `closed→surface` 是否重复执行整数化、三角准备或建树。现有源码明确只共享前四类记录而未共享 root，故优先复用同一 holder 的已有树，而不是新增第二缓存/索引服务。以相同实际结果、少一次准备/树构建和完整成本证明简化；如果第一版已做到单次，则只审计并记录“无需再改”，不制造第二轮调优。

cold/两事实、closed热但surface冷、surface-only、nearest exact-rank、修订仅变/几何变各路径均需说明树创建和复用归属。不可跨 pair 直接重用整数坐标树：局部 origin/factor 取决于当前 pair；跨候选复用目标资格证明需要另有绑定与不变量证明，不作为本批默认新增缓存。

## 验收必须覆盖的正确性

- 固定 G508 及简单控制公开链；原样基线拒绝保留，不下采样；独立 oracle、见证落面、4毫米两侧、最近 complete 状态分别核。
- 两盒正距离但完全不重叠 AABB；真实最近边-边/点-面；共面重叠、接触、包含；开放/点/线退化表面原支持语义。证明不把 overlap-only 漏检当无候选。
- 廉价 self 证书的合法共享边/顶点，以及共面同侧折叠、非共享重合顶点、共享顶点后内部穿越、退化/重复/非流形等反证。不能以生成器保证替代验证。
- 同距界不剪枝、精确排序并列、换三角顺序与对象方向；非唯一见证可以换成另一有效见证，但若声明保持既有第一见证顺序，遍历和 tie key 就必须实现该承诺。
- 4096位界/8193 scratch、次正规小尺度、大平移、不同 factor，保持目前世界点发布失败但距离可知的状态。不要为新增下界直接形成未经约束的 `gap²*denominator` 或 float 平面距离。
- 原期限与取消在建树/队列/剪枝循环中仍传播；动态预算用真实遍历耗尽反例测试，不能只用理论面乘积拒绝；未知不产生完整最近结论、不被缓存或自动重试。

## 原件

- `SOURCE_BINDING.json`、两个 `.py.snapshot`：本轮同字节来源与实际快照哈希。
- `diagnose.py` / `ADMISSION_DIAGNOSTIC.json`：原样复现及仅移除前置乘积门。
- `closed_tail.py` / `CLOSED_TAIL_DIAGNOSTIC.json`：仅为诊断放开 pair cap 后的实际总工作瓶颈。
- `cheap_contact_potential.py` / `CHEAP_CERTIFICATE_POTENTIAL.json`：共享 simplex 证书与原树工作分解，非候选。
- `final_bound_potential.py` / `FINAL_BOUND_POTENTIAL.json`：事后最终 best 下界计数，以及不值得采用的补 slab 方向。
- `DIAGNOSTIC_ONLY_OVERRIDES.md`：所有内存覆盖及其等价差异；这些诊断不属于正式基线收益或产品支持范围。
