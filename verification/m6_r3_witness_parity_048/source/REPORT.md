本项只审计冻结 A/C 源码，不运行案例。合同为 `fc36530cdedd3db65ee55010b7f2a90a89fa87d6`；安装与 047 的源引用完全相同：A `a72aefd8…0a62d`，C `b8c8bcd7…402e`。`SOURCE_REFS.json` 绑定实际绝对路径、文件 SHA 和下列函数行。不能把这份静态审计写成 G60、独立家族或两个控制的执行结果。

**合同有三个层次，不能合并。**

1. 普通独立距离求解的实现规则是：先取最小精确平方距离，再取字典序最小的**有序输入三角行对**。A 树分支 `surface_proximity.py:825–841` 对较早行对用 `best=None` 重新求该对，再按距离/行对更新；C:1684–1743 用 `tie_accept=(pair < best_pair)`，在较早行对中只接纳第一个等距特征，后续严格改善仍可更新。两版线性路径 A:424 / C:875 都按原行顺序枚举，首个零距可立即返回；树路径不可据贪心首答宣称规范行已确定。输入换序后字典序作用于换序后的行对，不能默认规范行只是转置。
2. 同一选中行对内，没有“全局字典序最小世界点”规则。特征顺序是左点对右面/边、右点对左面/边、边对边；正距等值保留先到的有效特征。全三角接触优先返回 `contact[0]`；共面多点接触的首点来自原顶点与凸裁剪顺序。普通公共语义承诺当前三角表面的有效最近点/方向及明确的未知，不声明多个有效最近点必须按一个独立的世界坐标排序。因此“不同但都有效的显示点”“破坏已编码的规范行”“可用字段变未知”须分开评价。固定同序输入的版本兼容检查仍应保留完整点；缺少全局点规范不等于已证明 A/C 点会不同。
3. **共享闭壳接触是明确例外。** `classify_closed_solids` C:1072–1074（A 同函数）保存最先遇到的 `boundary_contact`。`_boundary_witness` A:1056 / C:2067 验证它属于同一 prepared pair 和两原三角；`measure_surface_proximity` A:1103–1123 / C:2484–2509 直接返回该零距点，若要求原生行则使用接触自带的行，不作全局最近行搜索。这个路径只证明有效接触见证，不证明字典序最小的零距行对。`closed_solid_relation + surface_proximity` 与普通 fresh 距离、surface-first spatial bundle 必须分别标共享状态；不能用此例外解释普通 G60 距离的规范行变化。

**首次可能分歧与保留并列的条件**

最早的结构性差别在树建设与种子，早于发布：A `_distance_roots:445` 使用原中位 BVH；C:902 使用 SAH/较小叶并编译节点，C:1767 起先沿一条贪心路径算种子，再入队兄弟子树。A:783 从根堆遍历。C 的中心距离、包含根盒下零键 FIFO 和初始贪心都会改变首次实际特征及当时上界；这只是中间态可不同，不能直接推出最终点不同。

C `_compile_bvh_node:921–937` 为每节点保存真实最小原生行。`_nearest_tree` 用两侧最小行组成当前节点对的字典序下界：若还能有更早行对，`strict=True`，AABB、面界和投影必须保留等号；若所有后代行对都不早于当前胜者，可以排除等距候选。具体为 C `_aabb_exceeds_best:758`、`_plane_exceeds_best:781` 以及当前投影的 strict/tie cutoff；A:353、367 只作严格距离排除，再在实际求值处处理行对。C 全局堆 break 仅在未缩位且严格最小 AABB 键大于当前上界时成立。改变访问顺序不应使较早的等距原生行被筛掉；这是需要原生行/首分歧证据的检查点。

| 几何情形 | 从源码能确定的规则 | 不能直接推出的结论 |
|---|---|---|
| 正距、几何见证唯一 | 所有有效最小特征应还原同一对点；两版保持左右对象方向 | 不能只因标量相等，就认定位宽、舍入、方向和来源发布全部可用 |
| 正距并列 | 普通完整求解先规范输入面组合，再按面内固定特征次序保留见证 | 没有独立的全局点排序；也不能跨有序输入、共享准备或调用选项归并 |
| 零距单点 | `_nearest_pair` 优先使用接触；`_witness('contact')` 返回同一点两次，方向 not_applicable | 共享接触返回的行不一定是普通最近搜索的全局规范行 |
| 零距多点/共面 | `_clip_coplanar` A:91 / C:133 的函数字节相同；结果按原顶点与裁剪顺序，取首点 | 不承诺世界字典序最小交点；必须先核选中原行、准备的顶点次序及进入的接触分支相同 |

退化三角在 A:245–249 / C:452–465 均化为字典序端点的闭线段或点，保留原三角行身份。穿面线段的 `_segment_face_contact` 函数字节相同；端点和共面接触继续走闭特征。C 的 fast face/edge 计算、预存面距/重心系数和局部特征 AABB 拒绝是 A 没有的求值路径；等值是否可接受必须沿 `tie_accept` 一直传入，不能只查看外层行对更新。

在相同选中行对、相同精确准备/接触输入以及完整未拒绝求值的条件下，保留的特征顺序意图一致。一般性 A/C 见证等价还缺各 fast 特征公式、预拒绝与原位宽停止在所有输入上的对应证明；尤其不能用共用发布器填补这一缺口。本项未发现并执行一个确定的 A/C 数值分歧，亦未宣布无分歧。

**发布与实际公开字段**

`_witness` A:866 / C:1877、`_rounded_distance` A:894 / C:1905、`_publish_points` A:932 / C:1943、`_witness_triangle_provenance` A:1032 / C:2043 都是逐函数字节相同。这是直接函数正文证据，不能替代整个调用闭包的等价证明：辅助 `_add/_sub/_mul/_dot` 并非全部逐字节相同，仍需对应精确算术与原停止前提。即便发布闭包已证相同，也仅能对相同输入推出相同处理；上游描述符、精确点、预算状态不同不能由此推出公共输出相同。

标量先作正确舍入；点按原绝对容差与距离一致性检查，正距点若舍入成同一点则拒绝发布。故可能存在 `measurement_valid=True`、正标量及方向已测，而点/见证 unknown，带 `original_surface_witness_precision_exceeded`。`task_query._surface_proximity_fact:175–196` 会保留 distance value，但给公共 fact unknown/reason；“标量有效”“完整 fact measured”“点可用”不是同一布尔量。原生来源成员检查还可因预算或精确编码字节上限缺项，不能将缺项填为任意原生行。

| 层/入口 | 实际可见 | 未默认公开/额外条件 |
|---|---|---|
| 支持的精确内核返回 | `measurement_valid`、distance、A/B world points、direction、witness/direction status 与各 reason、topology、method、work | `_exact_distance_sq` 需 retain_exact_rank；原生行需 retain_witness_triangles 且来源发布可成立。私有 holder 的精确局部点不是普通 wire 字段 |
| 普通 task surface fact | distance、nearest_witness A/B/方向、topology、status/reason、witness/direction status | `_surface_proximity_fact` 不默认拷贝原生行或精确有理点 |
| G60 nearest | 最近对象/并列组语义、best-known evidence 的点、方向与状态、覆盖/未决、绑定 | 默认不含规范三角行。精确对象距离排序不证明所有见证字段可用；不可把离线观测的内部行说成原 wire 已公开 |
| G60 scan | exact-key 的距离阈值判定，match 的点/见证状态、覆盖与未决；5 mm 等号属于 match | `_threshold_state:140–148` 按标量 exact key 判阈值，不要求点已测；无默认原生行。点状态仍须单独判断 |
| scoped source-region measurement | `point_a_m/point_b_m`、distance、direction/status、`source_triangle_a/b`、输入行域及可选 exact points | `project_scoped_measurement:901–952` 强制已测点/正确方向状态及原生行成员。无法发布时是拒绝，不能沿用旧点或假造规范行 |

`_witness_sources:658–673` 返回给定精确点的**全部**源面成员列表，和内核胜出的规范面组合不是同一概念；scoped 投影验证胜出行确实在成员列表中。成员正确不自动证明该胜出行是所有最小组合中字典序最早，后者需要求解/共享路径的独立核对。

结论范围：已完成的是两个原安装的源码/公开字段/分支口径审计，调用数 0、Blender 0。048 的主例、独立家族和两项固定控制由各自原件评估；本报告不增加第三例，也不把 129 的既有域外失败改写为本批见证差异。
