# 凹槽迁移六格的实际消费机制

本次使用固定六格原件。质量引用已封存的6/6完整正确、78/78事实正确结果。机制审读覆盖全部请求代码、响应及最终答案，模型消费者、Blender、产品和业务API新增运行计数为0。

## 实际机制

P三格均自然请求spatial_relation和surface_proximity，直接使用完整事实形成正确答案。P原生工具调用、必要原生补完和已完成事实后的原生重算均为0，冻结机制条件达到3/3。三对关系均measured，正确答案在本题上由引擎事实独立支持。最终文字同时与spatial及closed返回值一致，现有记录无法区分模型读取了哪个同值关系字段。

## 完整调用轨迹

| 格/步 | 组 | 主分类 | handler毫秒 | 响应包络字节 | 作用 |
|---|---|---|---:|---:|---|
| grc01/1 | N | directory_or_identity | 146.2828 | 545 | 核对象类型、位置、点数、modifier 与单位。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc01/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc01/owner/tool_01/RESPONSE.json) |
| grc01/2 | N | new_information | 36.1093 | 3397 | 求值四份网格，以 float64 世界矩阵运算缓存几何，并输出全部26世界顶点、36三角和54边。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc01/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc01/owner/tool_02/RESPONSE.json) |
| grc01/3 | N | new_information | 251.6764 | 2075 | 复用 geom，首次计算三对点面/边边距离、边面相交及双方全部顶点 winding。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc01/owner/tool_03/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc01/owner/tool_03/RESPONSE.json) |
| grc02/1 | P | new_information | 120.8277 | 7997 | 请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三对完整事实。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc02/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc02/owner/tool_01/RESPONSE.json) |
| grc03/1 | P | new_information | 4.1135 | 857 | 首次请求把 nearest_witness 作为独立事实名，合同验证拒绝。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc03/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc03/owner/tool_01/RESPONSE.json) |
| grc03/2 | P | new_information | 93.8695 | 9041 | 请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三对完整事实。 同时获取四份额外 aabb。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc03/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc03/owner/tool_02/RESPONSE.json) |
| grc04/1 | N | directory_or_identity | 20.6709 | 217 | 遍历当前场景的对象名与类型。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc04/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc04/owner/tool_01/RESPONSE.json) |
| grc04/2 | N | new_information | 84.7739 | 858 | 用 mathutils 矩阵乘积读取世界点，再存入 float64 数组；输出计数、界与单位。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc04/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc04/owner/tool_02/RESPONSE.json) |
| grc04/3 | N | new_information | 234.2212 | 2178 | 重读局部点和世界矩阵，改用 float64 乘积，首次求三对距离并检查相交、全顶点 winding 和边面流形。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc04/owner/tool_03/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc04/owner/tool_03/RESPONSE.json) |
| grc05/1 | N | directory_or_identity | 19.8686 | 1577 | 核四对象完整世界矩阵、modifier、单位和名称。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc05/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc05/owner/tool_01/RESPONSE.json) |
| grc05/2 | N | new_information | 65.1358 | 914 | 求值四份网格并做 float64 世界变换，缓存点面，同时检查全部边的面关联计数。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc05/owner/tool_02/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc05/owner/tool_02/RESPONSE.json) |
| grc05/3 | N | new_information | 116.6029 | 1980 | 复用 geo，首次计算点面/边边距离、相交及双向全顶点 winding。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc05/owner/tool_03/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc05/owner/tool_03/RESPONSE.json) |
| grc06/1 | P | new_information | 92.2369 | 7997 | 请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三对完整事实。 [请求](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc06/owner/tool_01/REQUEST.json) [响应](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cells/grc06/owner/tool_01/RESPONSE.json) |

全部13步的请求参数、源代码、原始业务响应、stdout、host执行、产品trace和最终答案均在RESULTS.json中，源文件SHA见SOURCES.json。目录3步、新增信息10步，单独未知补证0步、已有完整事实后重算0步。每格前后QA共12次单列，业务host execute共12次，其中N原生9次、P内部采集3次。

## A闭壳与B/C充分分离

A的候选支撑方向未严格分离，support_work.reason为spatial_support_not_strictly_separated。空间关系实际调用bounded_exact_closed_shell_v1，返回disjoint_boundaries_with_exact_parity。B/C的空间关系采用exact_sufficient_spatial_relation_v1及strict_all_referenced_vertex_support。

| 每次成功P请求 | 空间关系分支 | closed work_units | pair/self/cross tests | 射线/查询 | 显式closed的作用 |
|---|---|---:|---|---|---|
| Part_A | bounded_exact_closed_shell_v1 | 2618 | 26/26/0 | 8/2 | reuse_required_spatial_fallback_bundle |
| Part_B | exact_sufficient_spatial_relation_v1 | 2594 | 32/26/6 | 8/2 | additional_explicit_closed_classification |
| Part_C | exact_sufficient_spatial_relation_v1 | 2498 | 28/26/2 | 2/2 | additional_explicit_closed_classification |

三次成功请求共记录closed工作23130 units。其中A必要空间关系回退为7854 units，显式closed直接采用同一bundle.closed，第二次A闭壳调用为0。B/C因额外closed字段进入独立分类，共15276 units。

源码task_query._closed_surface_facts先取空间关系bundle，仅当bundle.closed为空才调用额外closed测量。A已有闭壳结果，B/C充分分离后仍因显式请求closed而追加分类。三对每请求的closed_solid_pair_count均为1。

记录的pair/result缓存命中均为false或0。A的同请求结果直接复用与缓存命中分别描述。三对均prepared_pair_reused=true、prepared_trees_reused=false，每对闭壳工作新建2棵world tree。A的cross_pair_tests=0表示候选已被精确预检查排除，分类器仍执行树遍历、自体嵌入检查和双向奇偶检查。

trace只保存observation.task_facts包含式时段，没有独立closed时段。全部task_facts耗时与独立闭壳耗时分别列账，删除额外字段后的完整耗时和token变化为未测。

## 拒绝请求与精度刷新

grc03/1请求nearest_witness独立事实名，原响应tool_outcome=unknown、executed=false、execution_status=not_executed、host_mutation_started=false。该步host执行0，actor窗口4.1135毫秒，响应857字节，产品stdio发送/接收1269/869字节，产品RPC窗口1.7232毫秒。

至修正请求开始的空档为3.8852853秒，归因保持未测。grc03/2删去nearest_witness后成功，其余requested_facts包括aabb。四份AABB值组件的紧凑JSON为987字节，字段投影差994字节。该投影仅量化已保存数据的组成。

grc04/2先经mathutils得到世界点再装入float64，grc04/3重新读取局部点和世界矩阵并在NumPy float64计算。重读4份几何、26点、36面，发生在首次距离求解之前。步骤3同时首次给出距离、见证、相交、包含及边流形数据，因此归类为新增信息。初始mathutils缓存的距离答案没有保存，刷新对冻结精度的必要性、独立刷新耗时及删去旧读取后的整题变化均未测。

N三格最终求解均同时给出边界相交及双向全顶点winding数据。当前质量已由封存评分确认，其算法在本题之外的适用范围未测。

## 有据简化与归因边界

| 项目 | 可定位的既有记录 | 时延/因果边界 |
|---|---|---|
| 额外B/C closed | 6次分类，15276 work_units，12次world tree构建 | 独立closed耗时及完整任务节省未测 |
| 显式closed输出值 | 9个已测值组件，共2295紧凑JSON字节，其中A字段共765字节复用既有结果 | 组件大小与实际删字段后wire分别解释 |
| 无效事实名请求 | 1次，857字节，host执行0 | 自纠空档及整题后果未归因 |
| 数值精度刷新 | 4网格、26点、36面的一次重读 | 首次求值前，独立刷新成本未拆分 |

仅请求spatial_relation和surface_proximity时，源码仍会为A运行必要闭壳回退，B/C的显式closed分支可跳过。上述15,276 units是已发生的可定位分支工量，真实请求删减后的完整时延、token和费用仍为未测。此项分析使用现有控制流及审计，消融运行计数为0。

唯一后续方向沿管理员主线转向无预给对象的全场候选发现、按需精查和覆盖停止。当前结果限定该小规模凹槽装配，后续广泛发现能力与成本需由该主线证据判定。

## 计量与可重放性

handler是包含式actor窗口。内部RPC、host采集与task_facts属于嵌套区间，各层保持原计量。空档保持未归因。响应预算使用compact UTF-8 JSON RPC包络加LF，SOURCES保存原始文件字节SHA；private product stdio帧按RPC.json另列。

[完整结果](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cost_review_01/mechanism/RESULTS.json) [输入SHA](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cost_review_01/mechanism/SOURCES.json) [分析脚本](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/cost_review_01/mechanism/analyze_trajectories.py)
