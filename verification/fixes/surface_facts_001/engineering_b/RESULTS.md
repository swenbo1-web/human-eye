# SURFACE-FACTS-001-B

B 的唯一优化尝试达到预登记质量、算法及完整查询门，建议进入协调方独立终审。固定控制资产的闭合体冷查询窄阶段由 144 对减至 84 对（减少 41.67%），完整 CLI 中位数由 283.5131 ms 降至 266.56705 ms（改善 16.94605 ms，5.98%），四个固定配对均改善。热态中位回退 1.4915 ms，低于预设容许量。每版每类只有四样本，不能据此承诺总体性能、p95 或模型净收益。

唯一产品候选运行源：131 文件，`fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509`。分发版本 `9.7.2+surface.facts.b.1`，新隔离安装在本目录 `venv`。A 固定提交 `e053683ddc785d8b07366cfa8be68b9a03ac15c0`，其 131 源 `0155c5509901ed85dbf255c98a71e81187cbd3b60ef7bd49adcbfa1b663af578`、安装和历史证据均保留。没有升级默认安装。

证据入口：[EVIDENCE_INDEX.json](EVIDENCE_INDEX.json)、[FINAL_SOURCE_VERIFICATION.json](FINAL_SOURCE_VERIFICATION.json)、[MEASUREMENTS.json](MEASUREMENTS.json)。原始一次比较与判定：[comparison/RESULT.json](comparison/RESULT.json)、[comparison/ANALYSIS.json](comparison/ANALYSIS.json)。

## 单变量实现

只改数学模块与必要缓存版本：每个原已准备的三角形增加整数 AABB，沿原遍历顺序比较三轴区间距离的平方和下界。若有 incumbent `n/d`，只在整数下界严格大于该值时跳过相交及特征求解。等号不剪，保留同距首见证；零下界继续相交检查，真实零才提前返回。全输入、退化与拓扑检查仍在所有裁剪前，被剪对仍经过原 pair checkpoint。

比较利用整数下界 `L2 > n/d` 等价于 `L2 > floor(n/d)`，逐轴从 `remaining=n//d` 扣除平方。先用 `gap > isqrt(remaining)` 判断，再只对不超过该阈值的 gap 求平方，避免 `L2*d` 大乘积。4096 位保留量、8193 位临时量预算不变；最大坐标差可暂用 4097 位，但超阈值时不会被平方。坐标与 incumbent 均为同一整数框架的平方量，无 float 或世界 factor 转换。[MATH_PLAN.md](MATH_PLAN.md) 给出证明。

`triangle_pairs` 仍是访问数。新增 `aabb_bound_tests` 是有 incumbent 时实际下界比较数，首对无 incumbent 不比较；`aabb_pruned_pairs` 是实际跳过数。METHOD 为 `exact_binary64_triangle_surface_features_v2`，缓存算法键为 `task-surface-proximity-exact-aabb-v2`。除这两个必要身份差异，事实字段、数值发布、旧实体与动作语义、工具说明、捕获/缓存架构及检查点频率不变。没有加入法向/边预计算、BVH、持久索引或其他微调。A 的另外 129 个运行源保持原字节。

## 质量检查与真实错误

固定定向选择为原 A 的 41 方法加新增 11 方法，共 52 个唯一方法。首次完整清单：51 通过、0 assertion failure、1 测试构造 error、0 跳过；完整原件 [UNIT_RESULT.json](UNIT_RESULT.json)、`targeted.stderr.log` 与 `targeted.process.json` 均保留。

错误是新增测试用 `RequestBudgetError('request_deadline_exceeded')` 漏传必需 stage，尚未进入被测 checkpoint。使用唯一必要 QA 恢复额度，仅改为 `RequestBudgetError('expired', 'surface_proximity_pair')` 并补验这一方法；1/1 通过，没有重跑 52 清单。合计 53 次方法执行、52 个唯一方法最终完成验证，产品运行源从冻结至验收始终未改。见 [UNIT_RECOVERY.json](UNIT_RECOVERY.json)、[UNIT_ACCEPTANCE.json](UNIT_ACCEPTANCE.json) 及 `targeted_recovery.stderr.log`。这不是“首次 52/52 全过”；恢复额度余量为 0，实际 Blender 比较未发生恢复或重采样。

恢复前测试源另存 `qa/test_surface_proximity_pruning_001.before_recovery.txt`。冻结前 QA runner 字节也已精确恢复在 `qa/surface_comparison.before_recovery.txt`，其 SHA 与 FREEZE 一致；`qa/RUNNER_RECOVERY_DIFF.json` 证明仅 unit preflight 适配为读取原始错误与恢复聚合结果，没有变更性能计量、门限或样本顺序。

新增 11 方法覆盖严格大于/等于/小于、双向穿面与共面零界、AABB 重叠但真分离、同距首见证、晚退化先验证、微小/大平移单位、4096/8193 位边界、被剪对 checkpoint 异常、旧缓存键污染隔离及当前绑定/热态零新工作。检查点异常传播包含原 RequestBudgetError；没有测试实际 MCP 在途取消。

另有合法 binary64 反例解释 A unknown→B known：YZ 三角边长 `s=2^-1074`，A 位于 x=0，B 近面 x=s、远面 x=2^1023。近面解析达到 d=s；远面的精确 AABB 下界足以证明其不可能更优，B 安全跳过其可能导致旧窄阶段中间量超限的计算。输入全部已验证，预算未扩大。此项不计性能成绩，实际固定控制在 A 本来均已知。未跑原 83 方法或全项目矩阵，未追加随机数学批次。

## 固定实际入口比较

门限和样本在执行前保存于 [PREREGISTRATION.json](PREREGISTRATION.json)。只用 A 原 `author/control/scene.blend`（SHA `4e62bdd23a4a3c27185be864ce25d7eab4a97e0eb723bc63bfa4c348e1d26a17`）及原解析真值。顺序为 **A B B A B A A B**，四配对为 1A/2B、4A/3B、6A/5B、7A/8B。每会话新副本、新服务状态，依次 edge 冷、closed 冷、closed 热。没有顶点更新、新资产或可选停止。

8/8 会话、24/24 observe 通过，每版每类 4 样本；8 次资格原始回读。两安装使用同字节五个 helper 与原 A 计数包装。全部几何值、拓扑、方向状态和原表面见证逐项完全相同，仅 METHOD 身份不同；各返回绑定其自身真实安装源。冷态有实际求解，热态新求解与几何工作为 0，每次仍只有一次 selected capture 和一次编码。

以下按各版本实际出现顺序列四个原始样本，单位 ms；完整 CLI 包括 Python 启动、真实请求、计数器写入和返回回收，不含 runner 的结果断言与归档。

|类别/版本|原始四样本|中位数|范围|
|---|---|---:|---|
|edge 冷 A|302.4929, 304.8284, 274.9568, 296.0946|299.29375|274.9568–304.8284|
|edge 冷 B|278.7077, 283.9294, 290.6953, 280.1634|282.0464|278.7077–290.6953|
|closed 冷 A|304.3321, 283.4818, 283.5444, 279.6650|283.5131|279.6650–304.3321|
|closed 冷 B|269.9644, 258.6364, 276.1362, 263.1697|266.56705|258.6364–276.1362|
|closed 热 A|236.4044, 233.4746, 235.6835, 240.4000|236.04395|233.4746–240.4000|
|closed 热 B|236.3863, 238.6846, 230.7229, 245.1709|237.53545|230.7229–245.1709|

预登记采用门逐项结果：closed 冷改善 16.94605 ms ≥ max(5 ms, A 中位数的 5%)=14.175655 ms；四配对改善为 34.3677、24.8454、7.4082、16.4953 ms，4/4 ≥ 所需 3/4。edge 冷中位数无回退；closed 热回退 1.4915 ms ≤11.8021975 ms。三道门均通过，没有事后调阈值。edge 冷并未减少窄阶段工作，其 CLI 变化不归功于几何裁剪。

|closed 冷单样本实际工作|A|B|
|---|---:|---:|
|访问三角对|144|144|
|实际 AABB 比较/剪除|旧 A 无该字段|143/60|
|相交检查|144|84|
|点面候选|864|504|
|点边候选|2592|1512|
|边边候选|1296|756|
|共面裁剪加权循环检查|144|144|

窄阶段减少 60/144=41.67%，超过 25% 门；访问数没有减少。zero 案例两版均只做 1 对相交，特征候选均为 0；B 首对无 incumbent，AABB 比较为 0。两版全部热态均没有新几何工作。原 A 无新增 AABB work 字段，没有补造零值。`predicate_steps` 仅指共面裁剪循环的加权检查数，不能称为全部整数运算数。

## 完整成本、身份与清理

24 响应合计 31,432 字节，两版各 15,716；CLI wall 合计 6.4277257 s，A 为 3.2753585 s、B 为 3.1523672 s。每版实际 8 次 surface 求解、12 次 selected capture、12 次 task 编码；合计 16/24/24，strict、SAT、full capture 均为 0。热态历史 result.work 不计为本次工作。

内部比较 batch 为 23.0586141 s，其中八会话 startup-to-reap 合计 22.9771264 s，外部预备/最终分析 0.0814877 s。会话不重叠阶段合计：准备 0.0588110 s、含资产复制的启动至 ready 13.5635776 s、资格读取与核对 0.6636148 s、查询及断言/审计归档 6.8434509 s、清理回收 1.8476721 s。外层完整 runner 进程 wall 23.2399595 s。各层包含关系明确，不将 CLI、helper、service 与这些阶段重复相加。

本批定向初次 wall 0.9818128 s、单项恢复 0.5520176 s；唯一构建约 0.8266 s，新 venv 3.8100 s，本地 `--no-index` 安装约 1.5977 s，显式安装身份核验约 1.8508 s。准确进程原值与逐观察 service/helper 原始四样本、中位数、范围保存在 MEASUREMENTS 及 ANALYSIS。没有纯数学核计时或去计数器性能实验。

最终字节封存核对 checkout、B 安装、wheel 三处各 131 源；原 A 安装与 183 项历史证据未变。FREEZE 源、唯一 suite、恢复、build、install 与 12 个 B 实际返回均同源；另 12 个 A 实际返回保持 A pin。工具描述相对 A 字节差为 0。源差异、wheel 哈希和同字节 helper 记录均在 FINAL_SOURCE_VERIFICATION 与 QA_COPIES。

8 会话 launcher/worker 均正常退出回收，watchdog 均 joined，强制清理 0，源资产与受保护文件未变。最终清理快照核对 49 条历史身份记录、42 个唯一 PID，全部不在场。检查按创建时间区分 PID 复用，未终止任何复用或无关进程，未发现本批 Python/Blender 遗留。CLI 子进程均由成功的 subprocess.run 返回回收，原包装未留其 PID。见 [CLEANUP.json](CLEANUP.json)。

## 边界与交付

本批只完成一个 B、一次构建/安装、8 会话/24 observe/8 资格原读、0 更新、一次必要夹具恢复。消费者答案与新增付费 API 均为 0。未改 A 历史报告；协调方已确认 A 最终宿主完整 turn 为 2,660,992 ms，而 A 的回报前时刻 2,632,434 ms 不是最终时长。

B 宿主 read_thread 给出的起点为 2026-11-07T06:41:03Z（秒精度，保守采用更早整秒），45 分钟截止 07:26:03Z；整路线截止 08:12:45Z 未重置。所有实验已于 06:56:21.475Z 前结束。交付前封存累计时间见 [DELIVERY.json](DELIVERY.json)，一次回报另附截至回报前的累计时间；真正最终宿主 duration 需完成 turn 后由协调方读取，不用回报前时刻冒充。

代码与原始证据提交本分支，最终 HEAD 见完成回报。A 的旧源/安装保持可选，B 仅建议进入独立终审，没有自行合并或激活默认版本。会话与实施窗口已释放，根 STATE 未写。回报后结束等待终审，不追加样本、B2、消费者或 API。
