# PERF-030-002 执行结果

## 本批判定

唯一冻结运行完成。候选的有限数值正确性通过，性能非退化失败，M3 的 20% 模块目标失败。候选留待主线独立深审。

旧 PT 错值已在原私有叶核和受支持的公开测距路径复现。唯一封闭构造的解析间隙为 0.25m，接受 E 的 measure 和完整 task 将其报告为 measured 0；326 候选报告 0.25m。碰撞关系在两者均为 not penetrating。该构造没有执行动作或 verified 放行测试。

159 个 unittest 方法通过。正式 2,880 条记录、1,440 组完整响应对照、2,160 次显式 prime 全部完成。正式有效输入的 2,640 条解析复核通过，另 240 条预算拒绝控制保留。六个目标收益均未达 20%，88 个有效分层中有 5 项中位、3 项 p95 非退化失败。

## 固定版本与窗口

| 项目 | 固定值 |
| --- | --- |
| 聊天 | `local/01a1afc7-b09d-7272-be04-53b3e76ee71c` |
| 工作树 | `C:/Users/Administrator/.codex/worktrees/2c7d/hefe` |
| 分支 | `codex/perf030-002-pt-dual` |
| 接受 E | `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15` |
| 固定产品 | `326b64c74b2672fd620ddb9cac83bf47dd5355f2` |
| 固定 QA | `474e0e39591a4495991183643b5f14309f297568` |
| 运行时 HEAD | `5a2d148615b9799c5bcaa874d117f3bf61d9f932` |
| 授窗 token | `PERF030-002-WINDOW-01` |
| 原 static_freeze SHA256 | `71dfa0fe73c109f234ce6d554e313503d879f520dd474234ea4a9366481f5ec2` |
| run_freeze SHA256 | `d17fb6b424aa2bca36f4c44ed7d5a9a5652ede253209b32ba97db7f7eb5db88d` |
| E 的 130 源摘要 | `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163` |
| 候选的 130 源摘要 | `20fe8507cf3f802bd9471d2e8f7d00470f6013a6236f40e82258bd6aa6e7c5a0` |
| 候选 geometry SHA256 | `d3b47ed08de23bbf752b01f1ab2a7fe53b636cba5d4aa55621936e79837c384b` |
| 正式 raw SHA256 | `978affc75c4788bd5ec56a421da901d866d7186e9f0fb7c101a979f9d70636e7` |

运行前已读授窗文件与 STATE，并核对上述提交和三个冻结摘要。外层以现有 Python 加 `-I -B` 执行原控制器。原全新 `run_once` 目录只运行一次，结束后封存结果。产品与 QA 固定字节均保留，001 原件继续按原提交核验。

## 实际源码与 QA 装载

两个 runtime snapshot 各 130 个源文件从固定 Git 提交导出。已核验的 loader bytes 编译执行后安装原 SourceGuard，再导入产品。16 个 QA 脚本及其他原件共 22 项从固定 QA 提交导出，QA finder 编译已核验的 verification bytes。原测试 ROOT 实际指向 QA snapshot，其输入 SHA 为 `7026df331441f382dfd78b71e6460074994431f9c1c75bd14840cd7ef921200a`。

运行后的 260 个产品源和 22 项 QA 数据哈希逐项与 manifest 匹配，执行见证的源 SHA 全部在相应清单内。E 完成时有 26 个不同产品源的见证。候选为 64 个模块见证、63 个不同源，loader 的 bootstrap 和规范模块名共用一个源。130 是冻结源库存，实际执行范围以上述见证为准。

E 的显式检查点为 ready、finish。候选为 ready、tests_complete、finish。正常导入及延迟导入保留原 guard 校验。短名来源检查覆盖本轮正常链，没有任意异常文件回退的全域执行证明。

两者 source_kind 为 unregistered_runtime，范围是本地受控 snapshot 入口。外部依赖为既有 Python 3.12.14、NumPy 2.3.5、Pillow 12.3.0，版本和路径保存在 ready/finished 原件。三个 BLAS/OMP 线程环境变量均设为 1。本批范围为本地测量与 task_result，真实 host、MCP、GUI 和默认安装验收未测。

## 原错误与唯一封闭构造

两项原始叶核各执行一次，候选的另外八项变体按已冻结规则执行。下表为距离平方。

| 原输入 | 独立 Fraction 真值 | E 实际值 | 候选实际值 |
| --- | ---: | ---: | ---: |
| h=2^-30，P=(2,h,1) | 2 | 1 | 2 |
| 同一薄面，P=(2,0,0) | 1 | 0 | 1 |

候选十个保存输入的 Fraction 真值、精确重心和面内标志已用独立标准库算术复算。十个产品距离平方均等于独立精确值转 binary64，包括旋转远平面、薄面高度控制、容差两侧及可表示大平移。该有限结果没有覆盖所有条件数。

唯一封闭构造严格沿用预登记的左盒与右侧六盒加三棱柱。右体 54V/80F，薄帽面从索引 72 开始。预算通过，SAT 估计为 541,384 元素，两侧支持判定分别为 1 和 7 个凸组件。首次构造即进入公开支持路径，没有修改拓扑或搜索其他资产。

| 入口／检查 | E | 候选 |
| --- | --- | --- |
| measurement_valid | true | true |
| is_penetrating | false | false |
| measure clearance | 0m | 0.25m |
| 完整 task surface_clearance | measured 0m | measured 0.25m |
| task nearest_witness | unknown | unknown |
| 私有 scalar | 0m | 0.25m |
| 私有 witness | (2,0,0) → (2,0,0) | (2,0,0) → (1.75,0,0) |
| 两 witness 点的独立原表面距离平方 | 0、1/16 | 0、0 |

两份完整 task 均为 partial，原因是 convex-components 路径按原合同不提供公开 nearest witness。其 scalar clearance fact 明确标 measured。原件保存了 binding、单位、pair_order、schema、facts、status、execution_authority 和诊断。数值修复的已知变化单列于该构造，原 12 对的正式差分另列。

## 正确性门控和实际分母

候选的 159 项 unittest 方法全部通过，failure、error、skip、loader_error 均为 0。模块方法分母依次为新专项 4、concave 40、surface scope 6、strict execution 17、local SAT 13、scene cache 25、mesh mutation cache 19、task query 35。

候选诊断含十次叶核调用，冻结专项测试明确再次检查相同十个输入。E 原始叶核诊断为两次。每 arm 还在原 case 2 执行一次 PT 工作量诊断。叶核复测和算子诊断分别计量，没有把它们计为新对象对或正式速度样本。

专项同时检查原 12 个解析对的距离和 witness 原表面归属、跨 64 点块首 witness 以及 ring near-tie。现有动作 preview/readback/goal 反例使用隔离宿主 double。唯一封闭构造的动作可达结果未测。

正确性 gate 通过后才进入正式序列。正式 96 个 case／mode／entry 分层，每 arm 各 15 点，顺序与冻结的 5 block 逐项一致。720 组完整 measurement 字典、720 组完整 task 响应及诊断均相等，共 1,440 组。序列中异常、未解释响应差异、解析错误、cache 诊断错误和输入摘要错误均为 0。

48 份 case／mode 输入记录的两 arm 摘要一致，全部 miss 均有真实顶点变化。有效 task 的 cold／pose／geometry 为 miss，hot 为 pair-cache hit。预算拒绝始终保留 unknown 且不缓存，其 240 条记录独立保留。直接 measure 的 hot 仅复用同对象支持信息。

独立标准库复算重建了 96 份双 arm 顶点摘要、逐对象 SHA 和真实变换，并对 2,640 条有效标量按 Fraction 支撑面／ring 内壁复核，最大绝对误差约 5.20417e-18m。公开 measure 为 valid 1,320／invalid 120 条，task 为 observed 480／partial 960 条。

## PT 工作量资格

原 30V/56F 对的单次 PT 诊断为 30×56=1,680 个组合。实际 einsum 调用 16→13，其中每面 Gram dot 减少 3 个；cross 1→3，全部记录算子 17→16。scalar 与 witness 保留原投影，使用投影坐标点积叉积 dual。

tracemalloc peak 为 356,960→331,776B，current 为 4,428→4,732B。诊断包含操作日志的分配。包裹后的单次调用为 517.2→540.7μs，整个诊断为 580.9→600.3μs。这些单次带观察器结果仅供工作量归因。累计分配次数和 RSS 未测。

## 正式性能判定

每 case 以 15 点中位数比较，五个目标 case 改善率再取中位数。下表为百分比，正值为改善。每 case 的五个 block 配对改善和获益数完整保存在 summary.json。

| 入口 | cold | pose miss | geometry miss |
| --- | ---: | ---: | ---: |
| measure_pair_geometry | +0.487404% | -0.407791% | -2.004622% |
| task_result | -2.712902% | -1.575238% | -2.152384% |
| measure 获益 case 数 | 3/5 | 2/5 | 2/5 |
| task 获益 case 数 | 1/5 | 2/5 | 1/5 |

六项均未满足 20% 和至少 4/5 获益条件。数值修复的非退化也失败。88 个有效分层中有以下八个不同分层超限，预算拒绝的尾部控制没有超限。

| 超限项 | case／mode／entry | E → 候选 ms |
| --- | --- | ---: |
| 中位 | 20V/36F 双体／cold／task | 2.3782 → 2.6234 |
| 中位 | rotated ring／cold／task | 10.6060 → 11.0134 |
| 中位 | rotated ring／geometry miss／measure | 10.2287 → 10.5425 |
| 中位 | rotated ring／pose miss／measure | 10.0668 → 10.4446 |
| 中位 | 1pm boundary／geometry miss／task | 10.2256 → 10.4315 |
| p95 | ring/probe／geometry miss／measure | 10.38487 → 12.07107 |
| p95 | ring/probe／pose miss／task | 10.79095 → 11.94804 |
| p95 | large-shift ring／geometry miss／measure | 9.88741 → 12.21065 |

原门限分别为中位 `max(0.2ms,2% E)` 和 p95 `max(1ms,5% E)`。p95 使用 15 点线性插值。没有剔除离群值或重跑。候选源保留用于主线取舍，性能失败原件完整封存。

## 完整执行成本

以下时间均来自本轮实际账本，具有包含关系。

| 范围 | 时间 |
| --- | ---: |
| QA 导出 | 0.0744328s |
| 两 runtime 导出 | 0.2420918s |
| 两 arm 启动／ready 合计 | 2.4432991s |
| 候选测试 request 往返 | 3.5170055s |
| 其中 unittest runner | 3.3723737s |
| 正式对象构造合计 | 0.4212787s |
| 正式输入修改合计 | 0.0716790s |
| 2,160 次 prime 合计 | 11.0606913s |
| 正式 kernel 合计 | 12.2823603s |
| 正式 worker process 合计 | 23.9464911s |
| 正式 sample RPC 合计 | 24.4865722s |
| formal_raw 发布 | 0.1120434s |
| 两份 worker stdout 发布 | 0.0691880s |
| 17 份 JSON 的编码／写入／flush | 0.0121511s |
| summary 计算及发布 | 0.0385566s |
| worker 清理 | 0.0012855s |
| 控制器至结果封存 | 31.1100000s |
| 外层观察至控制器退出 | 31.3740780s |

每 arm 正式 prime 为 1,080 次，成本字段已逐整数与 raw、finish ledger 和 costs 复核。RPC 含 worker process、通信及编码发布，不能再与内层时间相加。JSON 发布明细共 511,162B，formal_raw 为 5,866,341B，两个 stdout 合计 5,353,062B。

外层 stopwatch 包含运行前的 CIM 进程枚举和解释器启动，退出后的 CIM 枚举位于该计时外。终端 completion_timing 文件自身发布明确排除。后续原件复算、报告编写、哈希封存与 Git 提交也在上述执行计时外。token 费用未测，新模型消费答案为 0。

正式序列复用完成诊断后的同两个 worker。候选另执行 159 项验证，前置工作量不对称且已入账。本轮速度范围为已加载进程中的本地请求，fresh-process、host/MCP 和模型原生收益未测。15 点线性 p95 没有置信区间，尾部回退的系统调度或算子自耗时因果未单独测量。

## 清理与封存范围

控制器正常完成，错误列表为空，all_workers_reaped 为 true，两个 stderr 为 0B。stdout 分别为 1,443 和 1,444 个事件，覆盖 ready、probe、各 1,440 sample、finish，候选多一个 tests 事件。外层命令退出码为 0。

运行前、退出后和封存前的只读 CIM 查询均没有匹配本批标记的 Python 进程。管道和读线程的证据是固定 close 路径完成且没有回收错误、控制器已退出和 worker 进程消失。单独的 native handle／线程快照及两个 worker 逐一退出码未保存。300 秒硬截止和异常回收分支本次没有触发。

运行原件位于 `verification/fixes/perf030_002/run_once/`。E、候选、QA 的源快照、manifest、ready/finished 执行见证、probes、159 测试日志、完整 raw、修改输入摘要、统计、成本及发布明细均保留。外层与清理记录位于本批目录。原 001 失败继续独立保留。

本批报告和固定提交回报送达后释放 `PERF030-002-WINDOW-01`，进入主线待审队列。
