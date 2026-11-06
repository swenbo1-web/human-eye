# PERF-030-003 阶段 A 静态预登记

## 基底与当前状态

派单为主线 `20261106_perf030_002_independent/NEXT_ASSIGNMENT.md`，SHA256 为 `809b89c648841b08b4f74a81fa5faaa4e9e5a6d8c2f04112878b732a8153375b`。主审报告 SHA 为 `a9a8c3bfce3728b5c53ae829ac08ff3fc963b8c69ded7c8e325dc46ed8eedc2f`。

工作树为 `C:/Users/Administrator/.codex/worktrees/2c7d/hefe`，本线分支为 `codex/perf030-003-convex-preparation`，从交付 `4ad4e3a345e32b3f5b1e97c212b71c1f3538d83c` 开始。产品基底固定为 `326b64c74b2672fd620ddb9cac83bf47dd5355f2`，130 源摘要为 `20fe8507cf3f802bd9471d2e8f7d00470f6013a6236f40e82258bd6aa6e7c5a0`。双 PT 修复保留，002 的六项 20% 失败及八个非退化分层失败仍独立有效。

当前产品、NumPy 探针、Python 编译、测试及性能采样全部为 0。当前实际交付范围为阶段 A 的方案和可审阅 QA。此阶段产品差异为空。

Agent Learning 自身句柄绑定有效。初两次 003 新任务登记返回 OperationalError，核对后确认仍为已交付的 002。随后一次在新鲜 session_context 版本上登记成功，任务为 `d7316b33-95b9-44f7-a910-eeab92697b5c`，revision 1、write_version 7。此前的建分支、阅读、QA 子任务委派及部分静态编写早于登记，作为登记前事件保留，不补称已归入新阶段。

## 唯一路线和资格分母

唯一预选产品范围为 `submodule_1_4_spatial_sniffer.py::_convex_shells` 内的单次有向边关联／组件准备表。阶段 A 先归因，资格成立后才形成一个候选。

固定读取原 inputs.json，SHA 为 `7026df331441f382dfd78b71e6460074994431f9c1c75bd14840cd7ef921200a`。按原顺序选以下八对。

| 原索引 | case |
| --- | --- |
| 0 | prism_20v_36f_each |
| 1 | prism_24v_44f_each |
| 2 | prism_30v_56f_each |
| 3 | asymmetric_8v12f_vs_64v124f |
| 4 | asymmetric_8v12f_vs_80v156f |
| 5 | small_box |
| 6 | ring_probe |
| 11 | budget_reject_40v76f_each |

每对依次为 cold_measure、primed_hot_measure、cold_task，每状态先 normal 再 diagnostic，各一次，共 48 个被测入口。16 个 hot 入口各用原普通 326 measure 先 prime 一次，总可见入口为 64。状态和输入固定，资格不计算 p95，也不追加样本。

每个 normal／diagnostic 入口独立新建 pair 与 SceneCache。hot 在自己的同一 pair 上 prime，诊断只覆盖被测入口，prime 按普通函数执行并单计。cold_task 保存完整 task_result 和 diagnostics，其 pair cache 必须 miss。

原 326 凸认证中的 token 正／负缓存仍被实际走到。hot 用于确认支持缓存行为，预算拒绝用于确认未触达凸认证，ring 保留负缓存与正交路径。支持结果从入口结束后的 mesh 缓存只读提取完整组件 points／normals／edge_axes，额外 support_status 调用数为 0。

## 实际入口和固定装载

`verification/perf030_003_qualify.py` 为唯一阶段 A 控制器。它从冻结 QA 提交读取并核验旧 002 controller bytes，编译复用 Git snapshot、Worker、发布账本和清理函数。产品只导出一次固定 326 的 130 源，源摘要必须匹配上述 20fe 值。

`verification/perf030_003_worker.py` 核验并编译旧 002 worker bytes，复用原 SourceGuard／QA finder 初始化。Stage A 最小实际闭包为八个 QA 脚本，另将已写的两项目标回归源码作为条件阶段 B 数据冻结。原 inputs 和 002 run_freeze 的 d17 摘要作为 lineage 输入核验。活动工作树只用于读取固定 Git 对象和运行 freeze。

启动时加载 orthogonal_solid 的原函数引用，进入诊断 kernel 时临时替换 sniffer、geometry_safety 和 orthogonal_solid 的三处 `_convex_shells` 引用，ExitStack 退出即恢复。该准备避免延迟导入捕获 clone 后污染后续 normal 入口。普通 kernel 同样包含空 ExitStack 的开销，诊断 kernel 另含三处 patch 的绑定／恢复。

控制器按 case、state、normal／diagnostic 顺序发 48 个请求，worker 拒绝重复请求。只开放 qualify 和 finish 两个操作。启动和 finish 保存原 guard 见证、QA 来源及诊断证明。Stage A 没有调用 159 回归或目标评估。

## 诊断 clone 与互斥阶段

`verification/perf030_003_diagnostic.py` 从 guard 持有的原 source bytes 读取函数，先与固定全文 AST 锚点核对，只插入 QA with span 和循环完成后的批量记录。独立剥离器移除这些语法后，函数 AST 必须等于原函数，成功后才编译 clone。运行时证明列出源 SHA、原／剥离 AST SHA、诊断 AST 和实际 code SHA。

这条路径执行 QA 归因副本。原 guard 的 326 源身份与诊断 clone 的身份分别记录。

| 互斥阶段 | 范围 |
| --- | --- |
| token_cache | full token、缓存查找、命中判断和返回 |
| closure | faces／verts 转换、result 初始值、is_closed_hull 及其可能触发的原准备 |
| topology_components | parents/find、逐面 roll、有向边字典、manifold、union、组件分组及结果种子 |
| numeric_certification | 每组面／点／法向／体积／凸投影、edge_axes、轴预算和结果 append |
| direction_index | global_normals／directions 与每组全边扫描，包含原数值方向选择 |
| other | 外层循环调度、catch、缓存写回和其余互斥时间 |

方向阶段混合了仍需保留的法向点积、阈值判断和向量生成。为避免逐 edge 时钟污染，本批整段单计，并采用更保守的 topology-only credit。其与 topology 的合计只展示乐观的零成本理想比例。

计数在完整 topology 循环结束后一次记录，在每个完整方向组结束后一次记录。包括 F 次 roll、3F 有向边 key／setdefault／append／oriented 更新、E 次 manifold／union、F 次分组以及各组全边扫描。find 调用由完整原循环导出为 2E+F，路径压缩内部读写／迭代标未测。异常中途的计数标 incomplete，缓存命中标 not_entered。

每个诊断入口 reset 有 16 对时钟校准，共 34 次读，所有 trace clock 次数另外记录。measured_bookkeeping_windows 为部分实测仪表窗口，可能与阶段时长重叠。参数构造、context／generator 派发等总因果观测税未测。reset、trace snapshot、patch 和完整诊断进程成本另入账，原 RTT 保持实测值。

## 事前资格算法

N 为普通完整 kernel 时间，D 为诊断完整 kernel 时间。T 为诊断 topology_components 互斥时长，I 为混合方向时长。H 为实测 recorder 窗口加 reset 与 snapshot 准备时间。

固定筛选量为 `credit=max(0,T-H-abs(D-N))`，分母为 `max(N,D)`。只有同时满足以下条件才允许在本路线形成一个候选。

- 全 48／16 分母完整，完整响应、prime 响应、支持结果和输入摘要相等，解析答案与 cache 语义一致。
- 诊断 AST 还原证明成立，互斥阶段加和成立，实际计数覆盖完整，零计数误记和未解释异常均不存在。
- 在同一目标 case 的 cold_measure、cold_task 两入口中，`abs(D-N)/max(N,D)≤10%`，`H/max(N,D)≤10%`，且 `credit/max(N,D)≥30%`。
- 五个目标中至少相同四个 case 同时满足两个 cold 入口条件。

该量用于保守资格筛选。单次普通／诊断差异与部分仪表窗口没有统计置信下界含义。T 本身的零成本理想比例、(T+I) 的乐观比例、H、clock 数和差值均原样保存；任何带仪表份额都没有被宣称为无偏 self-time。

理想比例不足 20%、只在 20% 附近、扣税后余量不足 30% 或观测差超过上述界限，均结束于真实归因。资格不足是有效科学结论，控制器只保存结果并退出。

## 成本、截止与异常

控制器复用 002 的逐 JSON 编码／写入／flush 账本，另记录 raw 与 stdout 发布、源码导出、引导、worker ready、请求往返和完整墙钟。worker 记录 object、prime、kernel、process、仪表准备和 trace snapshot。嵌套范围分列。

每个结果保留完整 payload、diagnostics、prime payload、前后支持缓存结果、输入摘要、诊断 trace 和实际异常。失败前的部分 trace 尽可能保存。输出目录排他新建，原件不覆盖。

Stage A 总截止 300 秒，第 295 秒停止工作请求，最后五秒回收和封存，一次性 timer 在绝对第 300 秒 kill 已登记 worker 并退出。正常 finish 和 finally 记录进程回收，部分记录保持 flush。token 费用、CPU/RSS 和累计 allocator 没有相应观测时标未测，新模型答案为 0。

## 条件阶段 B 和保留回归

当前没有拓扑候选。资格成立后才沿唯一表方案实现，并在固定新产品及新 QA 上做正确性和一次正式对照。原数值认证、阈值、轴选择、first-seen 顺序、组件顺序、SAT、326 双 PT 和 token 正／负缓存语义是验收边界。

保留原十叶核、唯一 0.25m measure／task／私有 witness、大平移、旋转、近界和原 159 项。新增 `test_perf030_003_goal.py` 的两项回归，独立预期为 target0 不达成、target0.25 达成，场景保持相同。它们沿主线已实际证明的同一构造写成，本线当前执行次数为 0。

只在该文件影响范围补面／边顺序、反向／重复／非流形、断开组件和原地修改失效反例，并纳入凸认证、空间索引等必要既有回归。条件阶段 B 的实际验证分母和候选 source／QA 在资格之后再锁定。

正式对照为 326 与唯一 topology 候选，原 12×4×2×5×3×2=2,880、2,160 prime 及六项 20%／4-of-5／非退化门限沿用。验证 worker 与正式 worker 分开，或两 arm 完全同等前置准备，具体执行入口届时随候选固定。相对 326 的增量与旧 E／002 失败分列。

## READY 和授窗

当前只提交固定 Stage A 方案和实际 QA，未运行分母为 48 个被测入口、16 prime、诊断 AST 还原检查和目标回归各 0 次。运行 freeze 逐项列出源／QA／输入 SHA、case IDs、状态、门限和时界。实际运行命令使用既有 Python 执行 `verification/perf030_003_qualify.py --freeze ... --output ... --window-token ...`，token 必须与 STATE 的 M3／PERF-030-003／granted 记录一致。

一次 READY 送达后结束静态批次，等主线在 M2 排队窗口之后主动授窗。
