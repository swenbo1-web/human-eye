# EXACT-RANK-001：已有精确平方距离的私有排名

**COMPLETE：8组新反例、128项相关回归全部通过。** 内核只求解一次，在有效距离发布后保留 world 平方距离的私有键；相同发布float而精确不同的距离现可区分，精确相等才合并，组内ID稳定排序。这里只排名提供的内核结果，不处理host采集包或证明全场景nearest完整。

分支 `codex/nearest-exact-ranking` 从固定 `aaa7d881e5e369f486ea789fad1cf38b3a2bd594` 出发。原 `codex/perf030-003-convex-preparation` 仍指向 `c899da0c8e9d06730120bedfb5d3d0e6703ab126`。基线131源2ef16…已逐源核对；唯一候选仍131源，摘要 **cca99f96f11259aa22eb8b0df1610ce42519ca8e46175127f1d4f495694e2502**，版本 `v22-exact-world-surface-ranking-20261107`。[CANDIDATE_IDENTITY.json](CANDIDATE_IDENTITY.json) 保存完整清单，测试加载身份与磁盘摘要一致。

## 实现与边界

[surface_proximity.py](C:/Users/Administrator/.codex/worktrees/2c7d/hefe/human_eye_plugin/surface_proximity.py) 新增默认关闭的 `retain_exact_rank`。由原 `_nearest` 已返回的 `n,d,factor` 直接生成 `_exact_distance_sq=[odd_n,odd_d,e]`，其中 `e=v₂(n)-v₂(d)-2log₂(factor)`，值为 `(odd_n/odd_d)×2^e = n/(d×factor²)`；零规范化为 `[0,1,0]`。没有第二次几何求解，也不先计算巨大的factor²。

键在 `_rounded_distance` 成功且 `measurement_valid=true` 后、见证/方向工作前保留。见证发布失败仍有有效距离键；准入、精确算术或距离发布失败继续原原因且没有键。默认查询不生成该键。

私有 `_rank_surface_results` 仅接收ID→已有内核结果。比较先约去分子/分母共有因子，再比较交叉积的有效位长加二次幂指数。有效位长不同时直接判断；相等时才对齐，移位后的交叉积仍在原 `2×MAX_BITS` 宽度内。零单独处理。每个候选、每次距离比较和完成位置均调用现有checkpoint，期限异常直接传播。缺键/原unknown进入未决，状态为partial或unknown；有效子集可排序，scope始终是provided_kernel_results_only，没有全场景complete。

[task_query.py](C:/Users/Administrator/.codex/worktrees/2c7d/hefe/human_eye_plugin/task_query.py) 抽出原有缓存调用为私有 `_surface_pair_measurement`：默认路径保留原v2、原参数与求解调用；opt-in使用 `task-surface-proximity-exact-world-rank-v1` 和retain参数，避免命中旧缺键条目。键就在实际返回值中，由原cache JSON序列化、解码和字节计费，cache hit不依赖compute旁路字典。原loose-vertex/工作预算的缓存绕过保持。原调用方继续在cache调用前后检查预算；私有排名本身也检查预算。

`scene_cache.py` 未改。公共 `_surface_proximity_fact` 的原字段投影未改，私有大整数不进入模型事实；公共距离、见证、方向、unknown原因和MCP/schema均保持原义。另只改 `runtime_identity.py` 的候选版本，共3个运行源，另128源不变。

## 固定8组真实内核/Fraction/cache反例

| 组 | 独立预期与结果 | kernel / _nearest |
|---|---|---:|
| 1 相同发布float、不同精确距离 | 端点平方 `1` 与 `1+2^-54` 都发布1.0；严格分为a、b两组 | 2 / 2 |
| 2 不同pair factor、局部比较反向 | factor分别为2^200和1；局部n/d更大者的world平方反而更小，按world正确排序 | 2 / 2 |
| 3 正距离精确并列 | 平面法向(1,1,1)与高度1给出独立平方1/3；不同factor仍精确并列，ID为a,z | 2 / 2 |
| 4 精确零并列 | 重合/相交三角集合，键均为[0,1,0]，稳定并列 | 2 / 2 |
| 5 见证发布失败、距离有效 | 大世界坐标反例；独立Fraction角点到XY多边形边距离平方吻合；见证unknown不抹掉排名键 | 1 / 1 |
| 6 保留unknown | 保留候选的退化面仍为surface_degenerate_triangle，无键、未进入_nearest；与已知结果混合时partial | 2 / 1 |
| 7 旧/新cache、命中与字节 | 原v2 miss/hit无键，排名unknown；rank版本另一次miss后hit保留真实键，修改返回值不污染已缓存字节 | 2 / 2 |
| 8 公共投影与比较期限 | 私有字段不会进入公共fact；比较checkpoint抛出的原RequestBudgetError直接传播，未重新求解 | 2 / 2 |

新增测试实际共 **15次kernel调用、14次_nearest**。唯一未求解调用在退化面准备阶段拒绝；每次进入求解的量测只有一次_nearest。排名、cache hit均增加0次求解。第7组两次求解对应明确不同的legacy/rank缓存身份各一次miss，不从旧float补造键。其两份序列化payload为625/672字节，原cache独立计费公式与慢速盘点均为2213字节。

[new_01/RESULT.json](new_01/RESULT.json) 保存8组真实结果、独立Fraction预期、实际factor/局部比值及调用计数；[new_01/unittest.stderr.txt](new_01/unittest.stderr.txt) 是原runner流。计数包装器都调用原内核，没有用模拟几何替代结果。

另运行原 `test_surface_proximity_001`、`test_surface_proximity_pruning_001`、`test_scene_cache`、`test_cache_accounting`、`test_task_query`，共 **128执行，0失败/错误/跳过**。[regression_01/RESULT.json](regression_01/RESULT.json) 与 [原runner流](regression_01/unittest.stderr.txt) 保留结果。回归的kernel调用总数未插桩，不把新组计数冒充整套总数。控制台出现未改的foveated renderer极值加法RuntimeWarning，测试仍通过；原提示的工具转录保存在WINDOW，不冒称原始stderr文件。

新组与回归各执行一次，无失败后重跑或追加病例。首次apply_patch因旧函数名上下文不符而原子拒绝，测试前已纠正，没有部分产品写入或测试失败。一个只读子审核对实现，无写入、测试或额外病例。

## 交付范围与未运行

只修改3个运行源并新增 `verification/exact_rank_001`；原报告分支、旧证据、其他实施分支、root STATE、host、公共schema、安装、默认入口及原资产未改。0Blender、性能采样、消费者实验、外部API、安装；没有后台worker。cache原始统计自带的计时估计不是性能样本或速度收益，本批只验正确性与实际工作次数。

host来源资格、排除覆盖、完整nearest接线和模型自然消费留给根后续同版本整合，本函数不产生这些结论。全部本批计划内测试已运行，费用/模型usage未测。宿主turn起点12:57:06Z，完整turn截止13:40Z、根复核13:55Z；完整终点由根在本turn结束后读取，见 [WINDOW.json](WINDOW.json)。索引见 [EVIDENCE_INDEX.json](EVIDENCE_INDEX.json)。
