# 凹槽六格：独立实际机制复核

结论：原始轨迹支持 P 三格在普通接口下自然请求并直接消费引擎事实，且没有消费者原生补算；A 的必要闭壳回退与 B/C 的额外闭壳分类均可从原始 audit 和固定源码交叉定位。B/C 的 **6 次分类、15,276 work_units、12 次 world-tree 构建**可以独立汇总复算，但不能据此宣称删除字段已经获得等量时延、token 或费用收益。该指定三对旧题应收口，后续转向无预给对象的全场发现与覆盖停止。

本复核不重发质量结论，沿用此前已封存的 e9479871 质量阶段；不以作者 PASS 作为机制证据。产品、Blender、消费者、业务 API 新运行均为 0；未导入或执行产品模块，未写实施 tree 或 Git，也未联系实施者。

## 实际读取范围及固定来源

实施 HEAD 为 `ea70339772159e5f0279784ebe18b1bf16e70439`，原件为 `4a90bbe95ef46c6666050ef1a1096fc6719c3b97`，产品为 `e836e03f4b3821f869c72ac3e50df5204f28b50f`。独立脚本读取 298 个唯一文件，包括 6/6 consumer、6/6 最终答案、13/13 请求及响应、13/13 attempt、3/3 P audit（7 条 request trace，含 3 条启动及 1 条拒绝）、6 份 worker 事件、24 份历史脚本及其 stdout/stderr 共 72 个文本文件，以及来源与接口声明。所有请求参数、响应 content 都与消费者实际收到的记录一致，六格输入哈希与冻结任务一致，最终文本与消费者 final 一致。

原件 914 文件清单中，本子任务实际使用的 157 文件逐一比对原件 Git blob 与索引 SHA；157/157 相符。不声称语义通读全部 914 文件。137/137 产品文件同时满足当前磁盘 SHA＝冻结 source manifest SHA，且字节＝e836e03f Git blob。代码机制语义审读集中于 task_query、surface_proximity、surface_geometry，以及 actor、consumer_transport、accepted_native 的相关函数；其余产品文件仅用于身份校验。

| 核心源码 | SHA-256 |
|---|---|
| task_query.py | `82fee8bbd5925f566198e7dd06c8090a9d2888243c0decb7e4238d6b1d1732ad` |
| surface_proximity.py | `e310e6c81b284efe0e0070297d298359ea5a0c3c71b62a250e855eed2b4cb66b` |
| surface_geometry.py | `a7f4375b2e4552a93ddfd2253184cda92b51c1212f55b3768d3f745e23cfee95` |

运行绑定 source SHA 为 `2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390`。完整实际读取清单、字节数、SHA 和用途在 [SOURCES.json](D:/hefe/verification/fixes/20261112_m4_grooved_rail_cost_review/mechanism/SOURCES.json)；逐步请求代码、响应、trace、逐对计数及 Git 校验在 [RESULTS.json](D:/hefe/verification/fixes/20261112_m4_grooved_rail_cost_review/mechanism/RESULTS.json)。

## 13 步实际轨迹

以下 handler 为 actor 包含式窗口，wire 为 compact UTF-8 JSON-RPC 包络加 LF；不是文件 pretty-print 字节，也不是纯几何计算耗时。

| 格/步 | 组 | 实际作用 | handler ms | wire bytes | 宿主脚本执行 |
|---|---|---|---:|---:|---:|
| grc01/1 | N | 名称、类型、单位、modifier、点数 | 146.2828 | 545 | 1 |
| grc01/2 | N | 首次四网格求值与 float64 世界变换，缓存 geom 并输出点面边 | 36.1093 | 3397 | 1 |
| grc01/3 | N | 复用 geom，首次距离/见证、相交及双向 winding | 251.6764 | 2075 | 1 |
| grc02/1 | P | spatial＋surface＋显式 closed，三对完整事实 | 120.8277 | 7997 | 1 |
| grc03/1 | P | 多请求独立 nearest_witness，合同拒绝 | 4.1135 | 857 | 0 |
| grc03/2 | P | 去掉无效事实名，三对事实及额外四份 aabb | 93.8695 | 9041 | 1 |
| grc04/1 | N | 场景对象名称、类型 | 20.6709 | 217 | 1 |
| grc04/2 | N | mathutils 世界乘积后装入 float64，缓存 geometry、输出 bounds | 84.7739 | 858 | 1 |
| grc04/3 | N | 重新读取、改为 NumPy float64 乘积，首次完整距离及关系求解 | 234.2212 | 2178 | 1 |
| grc05/1 | N | 世界矩阵、modifier、单位、名称 | 19.8686 | 1577 | 1 |
| grc05/2 | N | 首次四网格 float64 求值缓存 geo，边面关联计数 | 65.1358 | 914 | 1 |
| grc05/3 | N | 复用 geo，首次距离/见证、相交及双向 winding | 116.6029 | 1980 | 1 |
| grc06/1 | P | spatial＋surface＋显式 closed，三对完整事实 | 92.2369 | 7997 | 1 |

消费者原生调用 N=9，P=0；P 成功请求内部宿主采集=3，因此业务宿主脚本合计12，另有每格前后 QA 共12，保存的脚本执行共24。worker 还保存6条无脚本 SHA 的末尾 `unknown` 事件；源码 close 分支先回 `closed` 再由 finally 写默认事件，六份 CLOSE 回执亦为 `closed`，这些是关闭事件，不是额外几何执行，也不能与 grc03 的工具 unknown 混同。

“自然请求”的证据是原任务仅要求三对间隙、见证、阈值及最近者，没有点名算法或字段；三名 P 消费者实际选了 spatial_relation＋surface_proximity，并没有后续原生调用。普通工具声明本身明确推荐该组合，同时示例仍列 closed_solid_relation＋surface_proximity；因此这是**普通接口中的自主选用**，不是无提示发现字段的证明。不能从这些记录单独断言额外 closed 是由哪个声明句子导致。

三份 P 最终答案的距离和所有端点数字均能与收到的 measured surface 事实匹配，关系/排序文字也与返回一致。但 spatial 与 closed 都返回同值 `separated`，无法知道模型实际依据了哪个关系字段；仅能确认无需原生补算就能回答。

## A 必要回退、B/C 额外分类及复用边界

[task_query._closed_surface_facts](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:367) 先计算 spatial/surface bundle。显式请求 closed 时，只有 `bundle['closed'] is None` 且没有预算停止，才再调用 `_closed_solid_pair_measurement`。

[measure_spatial_relation](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_proximity.py:841) 先求最近表面，再以公开见证差方向检查全部 referenced vertices 的严格支撑分离。A 的原始 `support_work.reason=spatial_support_not_strictly_separated`，实际回退 `bounded_exact_closed_shell_v1`，证书是 `disjoint_boundaries_with_exact_parity`。这只证明当前提案失败并需要现实现的回退，不证明所有可能分离算法都必须闭壳。显式 closed 输出直接复用这份 bundle.closed，第二次 A closed 分类为0。

B/C 的 spatial 已通过 `strict_all_referenced_vertex_support`，方法为 `exact_sufficient_spatial_relation_v1`；其 bundle.closed 尚为空，额外请求 closed 才触发独立闭壳分类。

| 每个成功请求的候选 | closed 用途 | work_units | pair/self/cross tests | rays/point queries | world trees |
|---|---|---:|---|---|---:|
| A | 必要空间关系回退；显式字段复用结果 | 2618 | 26 / 26 / 0 | 8 / 2 | 2 |
| B | 已充分分离后的显式分类 | 2594 | 32 / 26 / 6 | 8 / 2 | 2 |
| C | 已充分分离后的显式分类 | 2498 | 28 / 26 / 2 | 2 / 2 | 2 |

三份原始 audit 独立给出同样计数：B/C=`3×(2594+2498)=15276`，6次分类×2棵=12；A=`3×2618=7854`、6棵；全部 closed=23130、18棵。surface 工作总数24999已经包含支撑方向检查351，不能再加一次351。这是对保存计数的独立重算，不是重新执行几何算法来重建每个基本操作，也不是 CPU 指令数或成本金额。

九对均 `prepared_pair_reused=true`，其含义是查询内复用已准备的几何与整数坐标结构。[nearest 分支](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_proximity.py:522) 因每对24×4=96≤256走线性枚举，surface `tree_builds=0`；没有已建距离树可交给 closed。[closed 分类器](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:729) 因而每对新建2棵 world tree，`prepared_trees_reused=false`。所有记录的 pair/result cache-hit 为false或0。必须区分 prepared pair 复用、同请求 A 结果复用、树复用、跨请求缓存命中四件事。

A 的 cross_pair_tests=0不表示没有闭壳工作：实际仍有候选遍历、self嵌入校验、精确预检查及双向奇偶查询。源码在预检查排除之后才递增 cross_pair_tests，原始183次 cheap_pair_tests、26次 self_pair_tests、8次 rays 与此相符。

## 拒绝、刷新与分类口径

grc03/1响应明确为 `tool_outcome=unknown`、`executed=false`、`execution_status=not_executed`、`host_mutation_started=false`；拒绝 trace 仅有 wire_encode/stdio_write，无 host.capture/task_facts，worker 时间窗内执行数0。nearest_witness 虽列于通用 schema enum，但不属于该 task-set 允许集合；它是请求合同误用，不是几何未知后的补证。修正后的 grc03/2是首次成功获取几何事实，不能算原生重复验证。

该拒绝 handler=4.1135ms、wire=857字节；到下一次请求开始有3.8852853s空档，不能把空档归为该错误的净损失或归于闭壳。删除错误请求后的完整消费者过程未测。

grc04/2先做 mathutils 世界乘积再转 float64；grc04/3重读局部坐标和世界矩阵，在 NumPy float64中完成乘积，重读4网格、26点、36面。此前只有计数和界，没有完整距离/见证/关系答案；第三步首次完成这些事实，并检查边面计数。因此“已完成事实后原生重算0”成立，但不能据此否认刷新造成重复采集。旧 mathutils 缓存的距离答案未保存，无法证明刷新对冻结精度的必要性，也没有独立刷新耗时。

作者目录3＋新增10＋未知补证0＋重算0，作为**请求意图主分类**可以接受；作为**成功取得新几何信息**统计需明确修正为：目录3、成功新增/首次求解9、未执行合同拒绝1。`new_information=10`不应不加说明地宣称10步都新增了几何事实。“重算0”也只指消费者在完整事实之后的原生重算，不覆盖 B/C 的6次额外引擎分类或 grc04 的几何重读。

## 可删工作与尚未证明的因果收益

在当前固定源码、同一成功输入下，仅请求 spatial_relation＋surface_proximity会保留 A 必要回退，跳过 B/C 显式 closed 分支。由此可定位15276 work_units和12次建树属于可避开的额外工作；A 显式字段仅重复表达已有结果，删字段不会省掉 A 的必要计算。额外 aabb 输出和无效请求也是可定位的既有信息负担。

原trace只有 `observation.task_facts` 包含式时段：grc02=39.164ms、grc03=38.5432ms、grc06=37.8813ms；没有独立 closed 时段。不得用工作单位比例拆分这些时段，不得把 actor、RPC、host.capture、task_facts 相加。请求变短之后模型的选择、生成、重试、总token、完整任务时延及费用均没有消融证据，本报告不估算收益百分比。

应停止对这个小型指定三对题继续调门或堆重复运行。当前分母只有一个4对象、26点、36面的场景，以及预给 Target 和三个候选；它没有无预给对象发现、全场候选漏检分母、覆盖停止或大场景收益证据。下一项工作的验收应明确这些新分母，保持必要回退与 unknown 语义，并完整记录质量和成本；旧题可保留为回归样本，不能充当新能力的发现证据。

独立复算入口：[review_saved.py](D:/hefe/verification/fixes/20261112_m4_grooved_rail_cost_review/mechanism/review_saved.py)。仅用指定 Python 的 `-I -B -X utf8` 执行标准库读取、哈希、不可变 Git 对象比较及数字汇总；输出仅写本复核目录。
