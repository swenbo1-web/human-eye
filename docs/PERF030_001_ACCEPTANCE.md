# PERF-030-001 首批候选验收

## 批次结论

本批完成归因、一个调用内 AABB 候选和一次正式序列。性能准入失败，候选留在本线等待主线独立深审。167 项定向测试通过。M3 后续实质优化与再审仍待主线安排。

五个有效目标组在 cold、pose miss、geometry miss 的两个完整入口中均有中位收益，六个入口／模式的跨对象组中位改善仅 3.50%–6.41%，低于冻结的 20%。按 25 个配对 block 中位数复算为 4.25%–5.99%，结论相同。另有六个有效分层和一个预算拒绝分层的 p95 回退超限。小例与 hot 的中位回退均通过原容差。

## 工作树与身份

| 项目 | 固定值 |
| --- | --- |
| 聊天 | `local/01a1afc7-b09d-7272-be04-53b3e76ee71c` |
| 工作树／Git 根 | `C:/Users/Administrator/.codex/worktrees/2c7d/hefe` |
| 分支 | `codex/perf030-001-surface-pruning` |
| 接受 E | `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15` |
| 基线 130 源摘要 | `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163` |
| 资格预登记提交 | `399c24d5a8b8b040e20b8fe1110373f323a64c84` |
| 正式候选提交 | `f87b7a6f7330f44b378145dbda9e93b6aeaebf29` |
| 候选 130 源摘要 | `2ee2f318d63b3545cb2aea56a0d692da1974a53dd6ace6b08fedaed4b1d13567` |
| 候选 geometry 文件 SHA256 | `81328d11e1cfcc2b634fbdf3937c4d93f1360488a4960df42e14412b8d913b33` |
| 性能窗口 | `PERF030-001-WINDOW-01`，授予消息与 STATE 的 M3 持有状态一致 |
| 输入 SHA256 | `7026df331441f382dfd78b71e6460074994431f9c1c75bd14840cd7ef921200a` |
| 正式原始记录 SHA256 | `e5d578de286fab55912253aa130216cda7b9e8db211ce29179e1dd4d492a0cd7` |

初始 HEAD 为接受 E，工作区干净。产品变更仅涉及 `human_eye_plugin/geometry_safety.py`。正式候选之后仅封存报告、统计与证据，产品字节保持候选提交版本。D 盘主工作区仅用于读取三份协调文件和调用现有 Python。当前安装、宿主、资产及共享协调记录均由其原持有者管理。

## 冻结方法与分母

输入顶点、三角面、显式边、单位、姿态、身份、解析真值和事实请求均保存在 [inputs.json](../verification/fixes/perf030_001/inputs.json)。一共 12 对，包括五个有效目标、盒体、ring/probe、旋转、大平移、明确边—边最小值、1pm 边界和一个预算拒绝控制。

指定事实为 `surface_clearance`、`solid_relation`、`nearest_witness`。七个有效凸体例的 nearest witness 按原合同为 unknown，task 状态为 partial。四个 ring 例能够给出 witness，task 状态为 observed。预算拒绝保留 partial 和原原因，未进入有效加速统计。

正式冻结见 [formal_freeze.json](../verification/fixes/perf030_001/formal_freeze.json)。每个输入为 5 个交错配对 block，每个 arm／输入／模式／block 为 3 次测量，两个入口和四个模式共 2,880 条记录。序列按 case、block、mode、entry、repeat 排列，arm 先后随 block 奇偶交替。原始文件采用排他新建，序列只运行一次。

cold 使用新的 pair 和 SceneCache。miss 先明确测原始 pair，再创建有真实顶点变化的新 pair。hot 明确准备相同 pair。准备时间在测量外，miss 后的求解、AABB 和 pair key 构建均在测量内。task 的计时边界含 `task_call` 内 scene/query 字典的构造和 `task_result`。直接 measure 的 hot 仅代表 mesh 支持缓存热态，只有 task hot 表示请求级 pair 缓存命中。

正式序列前修正了两个夹具细节，完整记录在冻结文件中。1e12m 世界坐标下固定 1μm 平移会被舍入吞掉，因此 pose 位移取 1μm 与两倍输入 ULP 的较大者。geometry miss 以本体最低 z 为原点缩放，并按输入 ULP 设最小可表示变化。每次 miss 均断言顶点数组确实改变。对象对、门限、分母保持首次冻结值。

这属于正式前对初版 mode 定义的补充修订，geometry 缩放锚点也由世界原点移至本体最低 z。1e12m 例的 pose 位移约 244.14μm，geometry 顶部变化约 488.28μm。两 arm 采用同一修订。

Python 为本机现有 3.12.14，NumPy 2.3.5，Windows 11。OpenBLAS、OMP、MKL 线程数固定为 1。基线模块仅从固定 E 的 geometry 文件读取并在内存加载，共用其余未修改的 E 源。候选和基线按 arm 切换 task_query 的既有 measure 绑定，采用相同 fixture 和缓存实现。

cold 指同一已导入 Python 进程中的新对象和新缓存。计时范围不覆盖 host 采集、MCP 传输、真实 fingerprint 生成及对象反序列化。五个 block 按固定交替顺序执行，其中三次 baseline 先行、两次 candidate 先行。每分层 p95 使用 15 点的 NumPy 线性插值，没有随机化和置信区间。

## 资格归因

下表为改算法前独立计时的中位数，单位 ms。SAT 列为原预算的保守投影元素估计。V/F 为各目标实际顶点／三角面数量。

| 输入规模 | SAT 估计 | 完整 measure | scalar 表面 | witness 表面 | pair key |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20V/36F 对 20V/36F | 469,440 | 2.0682 | 0.8407 | 0.8740 | 0.0782 |
| 24V/44F 对 24V/44F | 840,576 | 2.7177 | 1.3446 | 1.4092 | 0.0941 |
| 30V/56F 对 30V/56F | 1,700,160 | 3.3585 | 1.8148 | 1.8415 | 0.1079 |
| 8V/12F 对 64V/124F | 974,016 | 2.9526 | 1.2555 | 1.3306 | 0.1289 |
| 8V/12F 对 80V/156F | 1,497,408 | 3.6355 | 1.6885 | 1.7259 | 0.1560 |
| 小盒体 | 21,120 | 1.1549 | 0.3697 | 0.5133 | 0.0391 |
| 原 ring/probe | 84,000 | 9.8754 | 0.4866 | 0.6063 | 0.0514 |
| 40V/76F 对 40V/76F | 4,170,880 | 0.0049 | 未运行 | 未运行 | 0.1374 |

30V/56F 的独立 scalar 时间约为独立完整 measure 时间的 54%，据此将表面精算认定为可尝试的主要成本之一。该比值来自不同调用的独立计时，不能解释为一次调用内的精确自耗时份额。

[qualification.json](../verification/fixes/perf030_001/qualification.json) 同时保存一次 cProfile 的预算、支持判定、SAT 轴／投影、表面及凹体分解调用树。在 30V/56F 上，带 profiler 的支持判定为 2.6811ms，表面为 2.1554ms，SAT 轴与投影分别 0.1608ms、0.0686ms。支持判定也是主要成本。Profiler 显著增加 Python 层开销，其时间与上表独立计时分列。

ring/probe 的 witness 仅约为独立完整时间的 6%，cProfile 主成本为原正交凹体分解。预算与 pair key 均未解释有效凸体的主要成本。40V/76F 双体在精算之前被原 SAT 投影上限拒绝。完全相同的有效 task 热请求原本已有 pair cache，本批收益统计仅针对 cold 和真实 miss。

首份资格 JSON 的 `aabb_potential` 使用过小的绝对余量，ring 平局出现过计数偏差，原记录保留。经保守坐标尺度余量修正后的 `corrected_potential` 以及真正叶子组合数存于 [candidate_attribution.json](../verification/fixes/perf030_001/candidate_attribution.json)。理论候选率未用于性能验收。

## 唯一候选与实际工作量

候选保持原 64 分块及块序。每个块用 feature AABB 下界筛选仍可能改善当前最小值的行列，保留原递增索引。保留行列的笛卡尔积交给原数值核，因此仍包含一些无法改善的组合。witness 保持面投影、三条边、原 EE 的 phase 顺序。scalar 使用原世界坐标，witness 使用原公共局部原点。没有调用间几何状态。

非有限界、下界计算溢出、平局及余量内的比较保留精算。余量为 `128 * eps * scale²`。该余量经过已列反例验证，尚无全支持域任意细长面与近并行条件数的数值证明。主线深审应保留此限制。

| 固定 cold 输入 | 原 PT 组合 | 候选 PT | 原 EE 组合 | 候选 EE | 原／候选 traced peak bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20V/36F 双体 | 1,440 | 1,000 | 2,916 | 1,369 | 607,060 / 310,524 |
| 24V/44F 双体 | 2,112 | 1,464 | 4,356 | 1,965 | 772,796 / 423,778 |
| 30V/56F 双体 | 3,360 | 2,325 | 7,056 | 3,249 | 778,772 / 463,958 |
| 8V/12F 对 64V/124F | 1,760 | 888 | 3,348 | 1,564 | 277,876 / 215,196 |
| 8V/12F 对 80V/156F | 2,208 | 972 | 4,212 | 1,861 | 269,316 / 208,654 |
| ring/probe | 448 | 256 | 864 | 72 | 293,663 / 179,272 |

PT 和 EE 为进入原 scalar 叶核的笛卡尔组合数。scalar EE 还执行四个端点—线段阶段。witness 的实际候选组合另逐块记录，最终世界点归属复核沿用原逻辑。1e12m 输入的 scalar 因保守世界尺度余量保留全部组合，witness 在局部坐标仍能剪枝。

分配证据包含资格测量的 tracemalloc current/peak，以及独立候选归因的 traced peak，未记录累计 allocator 调用总数。tracemalloc 数值不代表进程 RSS。其独立记录没有混入正式计时。

## 正式性能结果

下表为五个对象组各自 15 次中位数之比的中位改善，获益对象组均为 5/5。

| 入口 | cold | pose miss | geometry miss | 20% 门限 |
| --- | ---: | ---: | ---: | --- |
| measure_pair_geometry | 3.63% | 5.49% | 5.37% | 全部失败 |
| task_result | 3.50% | 6.41% | 4.30% | 全部失败 |

| cold 输入 | measure 原／候选 ms | task 原／候选 ms |
| --- | ---: | ---: |
| 20V/36F 双体 | 1.9809 / 1.9163 | 2.1476 / 2.0821 |
| 24V/44F 双体 | 2.6902 / 2.5196 | 2.8887 / 2.6455 |
| 30V/56F 双体 | 3.4217 / 3.0694 | 3.6060 / 3.2824 |
| 8V/12F 对 64V/124F | 3.0418 / 2.9315 | 3.3207 / 3.2600 |
| 8V/12F 对 80V/156F | 3.7027 / 3.5914 | 4.0002 / 3.8603 |

按冻结的 `max(1ms,5%)`，六个有效分层 p95 失败，分别为非对称 64V 对的 task pose miss、ring/probe 的 measure pose miss 和 task geometry miss、旋转 ring 的 measure cold、大平移 ring 的 task pose miss、1pm 边界的直接 measure hot。另有预算拒绝的 task geometry miss p95 失败，保留在控制分母中。所有原始值、15 次分位数、状态和逐层门限见 [summary.json](../verification/fixes/perf030_001/summary.json)。未剔除离群值，也未重跑选择成绩。

预算拒绝分层没有执行表面剪枝核，其 p95 超限无法归因于新算法。补充的 25 block 统计只对同一原始记录作诊断，冻结门限仍按初版定义判定。

## 正确性与未测边界

167 项定向测试全部通过，日志见 [final_tests.log](../verification/fixes/perf030_001/final_tests.log)。其中 155 项来自任务指定的 concave、surface scope、strict execution、local SAT、scene cache、mesh mutation cache 和 task query 回归。新增 12 项覆盖解析盒、明确 skew EE 最小值、ring 间隙、旋转、大平移、1pm、跨原 64 块平局、后续 face 块重新考虑 point rows、非有限／溢出界和退化公开 unknown。

正式记录共 1,440 组已记录语义载荷相等。measure 保存的完整 measurement 字典相等。task 保存的 facts、status 和 diagnostics 相等。clearance 与已记录 witness 坐标最大差为 0。没有保存并比较完整 task_result 的 binding 等其他字段，也未比较其序列化字节。正式测量无异常。

对正式变更后的输入另作解析复核，覆盖全部 2,640 条有效记录。凸体和 skew bars 以实际浮点输入的平行 z 支撑面间隙为真值。ring 各模式仅改变 z，验证 probe 仍处于 ring 竖向范围后沿用独立水平间隙。全部通过 1e-14m 的检查，复核只读取正式成绩，未重跑求解或性能序列。

有效样例 task 的全部非 hot 均为真实 pair-cache miss，hot 均为 hit。预算拒绝在全部模式继续 miss，因为 unknown 本来不缓存。其 240 条双 arm／双入口拒绝记录保留。表面近距、witness 数值与支持域仍由原核／原校验决定。

未运行项包括 Blender、GPU、真实 GUI、默认安装、API 或模型消费测试。preview/readback/action 相关现有反例以本地独立宿主 double 验证。

## 剩余成本与后续边界

固定有效凸体的支持认证仍占重要成本，ring/probe 的正交凹体分解仍占绝大部分时间。候选减少了约一半 EE 叶组合，但逐块 AABB 的 reduction、矩阵、索引和复制吃掉了大部分完整链路收益。当前证据不能把剩余时间细分为每项 AABB allocator 的自耗时。

本批更简单的可用选择仍是保留接受 E。若主线安排同一假设的下一轮实质优化，可先把调用内重复 feature bounds 构建收敛为一次并保留原数值叶核，独立验证收益后再定候选。支持认证／凹体分解需要另行归因和明确派单。

本线完成报告与固定提交回报后释放 `PERF030-001-WINDOW-01`。下一批由主线独立复核后安排。
