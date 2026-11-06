# PERF-030-003 Stage A 归因交付

## 判定与交付范围

本批唯一 Stage A 执行完成。48/48 个被测入口、16/16 个原函数 prime 均有保存回执，24 对 normal／diagnostic 的完整响应和支持结果相等。预登记筛选中，同一 case 的 cold_measure 与 cold_task 同时通过者为 **0/5**，要求为至少 4/5。结论为 `qualification_supported=false`，本批结束于归因交付。

方向索引阶段包含仍需保留的数值选择，因此事前采用 topology-only credit。其筛选余量最高为 21.57342%，十个目标 cold 入口均低于 30%。即使把整个混合方向阶段也计入零成本理想展示，同时达到两个 cold 入口 30% 的 case 也仅 1/5。单次配对只能支持本批资格筛选，候选净收益、p95、统计噪声界和全部因果观测税均未测。

本批形成的产品候选数为 0，Stage B、159 回归、新写的两项目标专项、正式 2,880 入口及 2,160 prime 的实际执行数均为 0。旧 001 失败、002 六项 20% 失败及八个非退化分层失败继续列为未通过。本批产品基底为保留双 PT 数值修复的 326，M3 最终准入仍待后续同版本完整／原生比较与独立深审。

## 授权与固定身份

运行窗口为 `PERF030-003-WINDOW-01`，owner 为 M3／`local/01a1afc7-b09d-7272-be04-53b3e76ee71c`。实际工作树为 `C:/Users/Administrator/.codex/worktrees/2c7d/hefe`，分支为 `codex/perf030-003-convex-preparation`。

| 项目 | 固定值 |
| --- | --- |
| 执行 HEAD | `d32cb231ce433f35e2e425f45488fdc951e3896b` |
| QA 提交 | `56ec0b22fc5b33ba2c6024e66324100e6602ed0b` |
| 产品提交 | `326b64c74b2672fd620ddb9cac83bf47dd5355f2` |
| 130 源摘要 | `20fe8507cf3f802bd9471d2e8f7d00470f6013a6236f40e82258bd6aa6e7c5a0` |
| sniffer 源 SHA256 | `c3c891831bb859874b40c69fab204b7fd040ad5b4a292778901f556f91389f0f` |
| geometry_safety 源 SHA256 | `d3b47ed08de23bbf752b01f1ab2a7fe53b636cba5d4aa55621936e79837c384b` |
| 静态方案 SHA256 | `919153a9d8e551be0e464e418b6e422678b1953f9993b57d9c5ac69d8a1e03a9` |
| run_freeze SHA256 | `9b562053d7b8b6d97517784ce4a29771ef04de9cef6ebe771ef9673f6ac8034a` |
| 原 inputs SHA256 | `7026df331441f382dfd78b71e6460074994431f9c1c75bd14840cd7ef921200a` |
| 002 run_freeze lineage SHA256 | `d17fb6b424aa2bca36f4c44ed7d5a9a5652ede253209b32ba97db7f7eb5db88d` |
| 原件 qualification_raw.jsonl SHA256 | `675d86882d510b712e324311040c2edf1e2b462d9bc7d2c8ff028397bd6049cf` |

主线 NEXT_ASSIGNMENT SHA 为 `809b89c648841b08b4f74a81fa5faaa4e9e5a6d8c2f04112878b732a8153375b`，002 REVIEW SHA 为 `a9a8c3bfce3728b5c53ae829ac08ff3fc963b8c69ded7c8e325dc46ed8eedc2f`。主线窗口静态审查 SHA 为 `3224fe982ac8829d5b63768f22efecccf0a22dfae54035ca16a20758fc6e582a`，静态 manifest SHA 为 `9eb5fd4c95796b84034bb4ef84218736e5385bcb3b649415d4e1542d703d59bd`。执行前 STATE 的 granted 记录 SHA 为 `b3924c2d3cded8c3bc54e63db339bc6be3f3c4f034405fd4d9990dacad41b25c`。

Agent Learning 的前两次 003 登记返回 OperationalError。第三次登记成功之前，建分支、阅读、QA 委派和部分静态编写已发生，这些事件保留登记前身份。执行时任务为 `d7316b33-95b9-44f7-a910-eeab92697b5c` revision 2、write_version 8，执行入口在登记成功之后。

## 实际分母与完整性

按原索引 `[0,1,2,3,4,5,6,11]` 固定顺序执行，分别为三种 prism、两种 asymmetric、small_box、ring_probe、budget_reject。每 case 依次为 cold_measure、primed_hot_measure、cold_task，每状态先 normal 再 diagnostic。每个入口使用独立新 pair 和 SceneCache，hot 在自己的同一 pair 上调用一次原普通 326 measure prime。

| 项目 | 实际值 |
| --- | --- |
| 被测入口 | 48/48，normal 24、diagnostic 24 |
| 原普通 prime | 16/16，normal 路径 8、diagnostic 路径 8 |
| 总可见顶层调用 | 64 |
| 入口配对 | 24/24 |
| 完整 payload、diagnostics、prime、support_before、support_results、input_metadata 相等 | 24/24 |
| issues／控制器 errors／入口异常／trace 异常／不完整计数 | 各 0 |
| 已保存响应缺口／已开始而无回执请求 | 各 0 |
| 被测有效结果／预算拒绝或 unknown | 42／6 |
| measure 有效／invalid | 28／4 |
| task partial／observed | 14／2 |
| prime 预算 unknown | 2，已包含于 16 prime |

六个被测预算结果均属 case 11 的既有预算拒绝，两个 prime 预算 unknown 另计。task 中凸路径的 nearest_witness 继续保留既有 unknown。全部 unknown 及完整结构均保存在原件中。

诊断共观察 54 次 `_convex_shells`，28 miss、26 hit，其中 2 个负结果 miss、7 个负缓存 hit。ring 的 cold_measure 和 cold_task 每入口均为 2 miss＋4 hit，含 2 负 hit，hot 为 6 hit，含 3 负 hit。预算 case 的三状态均为 0 次 clone 调用。支持结果读取既有 mesh 缓存中的完整组件数组，额外 support_status 调用数为 0。

## 分段与操作计数

六段互斥时间在每次 clone 调用中均非负，逐调用之和精确等于该函数 function_total，入口聚合与 summary 相等。下表为全部 24 个 diagnostic 入口的函数段聚合，单位 ms。它们属于完整 kernel 的子范围。

| 段 | 实际包含范围 | 聚合 ms |
| --- | --- | ---: |
| token_cache | full token、正／负缓存查找和返回 | 0.3126 |
| closure | faces／verts 准备、result 种子、is_closed_hull | 1.1143 |
| topology_components | parents/find、逐面 roll、边字典、manifold、union、组件分组和结果种子 | 8.1631 |
| numeric_certification | 组内几何、normals／volume／凸投影、unique axes、edge_axes、预算与结果 append | 6.1658 |
| direction_index | global normals、每组件全边扫描及原数值方向选择 | 1.9697 |
| other | 调度、catch、缓存发布及其余互斥时间 | 0.6097 |

28 次完整 topology 段和 26 次完整 direction 段的批量事件支持以下计数。已统计的 topology／direction 计数循环中途异常为 0。find 路径压缩内部读写及迭代数未测。

| 操作 | 聚合次数 |
| --- | ---: |
| np.roll／face rows | 各 1,288 |
| 有向边 key、setdefault、incident append、oriented get、oriented set | 各 3,864 |
| manifold／union 无向边访问 | 各 1,932 |
| find 调用，按完整原循环 2E＋F 导出 | 5,152 |
| 每组件全边访问／membership 检查 | 各 1,836 |
| 数值 angle test，按完整原循环导出 | 1,836 |
| direction append | 996 |

方向索引的 1.9697ms 包括法向点积、阈值判断和向量生成。新表构建仍需付出成本，因此 `(T+I)/max(N,D)` 仅作乐观零成本展示。

## 五目标双 cold 入口原值

N 为 normal 完整 kernel，D 为 diagnostic 完整 kernel，T 为 diagnostic topology_components，I 为混合方向阶段，H 为部分 recorder 窗口加 reset／snapshot 准备。以下时间均为 ms，差值为 `abs(D-N)`。原始 ns 和全部 24 对结果见 summary 与 raw。

| case | state | N | D | T | I | H | 差值 | credit % |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 prism20v36f | cold_measure | 37.3923 | 2.6292 | 0.4812 | 0.1165 | 0.0911 | 34.7631 | 0.00000 |
| 0 prism20v36f | cold_task | 10.8100 | 2.4102 | 0.4715 | 0.1153 | 0.0737 | 8.3998 | 0.00000 |
| 1 prism24v44f | cold_measure | 2.7926 | 3.0880 | 0.6808 | 0.1386 | 0.0860 | 0.2954 | 9.69560 |
| 1 prism24v44f | cold_task | 2.9784 | 3.1302 | 0.5455 | 0.1391 | 0.0792 | 0.1518 | 10.04728 |
| 2 prism30v56f | cold_measure | 3.5656 | 3.5698 | 0.6831 | 0.1739 | 0.0743 | 0.0042 | 16.93652 |
| 2 prism30v56f | cold_task | 3.7070 | 3.8427 | 0.6881 | 0.1723 | 0.0950 | 0.1357 | 11.90309 |
| 3 asym8v12f/64v124f | cold_measure | 3.1349 | 3.3428 | 0.8247 | 0.2557 | 0.0794 | 0.2079 | 16.07634 |
| 3 asym8v12f/64v124f | cold_task | 3.6661 | 3.5540 | 0.8297 | 0.2126 | 0.0761 | 0.1121 | 17.49816 |
| 4 asym8v12f/80v156f | cold_measure | 4.0144 | 3.9031 | 1.0107 | 0.2579 | 0.0758 | 0.1113 | 20.51614 |
| 4 asym8v12f/80v156f | cold_task | 4.1718 | 4.1278 | 1.0174 | 0.2519 | 0.0734 | 0.0440 | 21.57342 |

预登记公式为 `credit=max(0,T-H-abs(D-N))/max(N,D)`。每个 cold 入口同时要求 credit≥30%、差值比例≤10%、H 比例≤10%，同一目标的两个入口均通过才算该目标通过。实际为 0/5。

首个目标的两个差值比例分别为 92.96861% 和 77.70398%，其 normal／diagnostic 时界不足以支持稳定归因。第一 normal cold_measure 的额外耗时原因未测。固定旧 helper 在首个 normal cold_task 内延迟导入 task_query，ready／finish 产品见证增加 task_query、query_policy、measurement_presentation、top1_query、support_plane_discovery 共五个模块，10.8100ms 包含这条导入链。单个 import 耗时和差值因果分解未测。

全部 24 对中，5 对差值比例超过 10%，包括上述两个目标入口、ring cold_measure 和 budget 的 cold／hot measure。2 对 H 比例超过 10%，均为 budget measure，分别约 88.40%／93.18%。目标十入口 H 比例均低于 10%。全部目标的 T 零成本理想比例仍低于 30%。把 T＋I 全部视为零成本时，两 cold 入口同时达到 20% 的目标为 4/5，达到 30% 为 1/5，余量仍不支持预登记门槛。

## 诊断身份与冻结证明

普通入口执行固定原函数，诊断入口执行带可剥离仪表的 QA clone。三处函数引用在 diagnostic kernel 内临时 patch 并恢复，orthogonal_solid 在入口前已捕获原引用。诊断 AST 还原实际在任何被测入口之前通过，ready、finish 和 24 个 diagnostic 记录中的证明相同。

| 证明 | SHA256／结果 |
| --- | --- |
| 原函数 AST 与独立字面锚点 | `9caa7fd57a6d5bfc26f7f7ca018fff55e06602fe46e017104151d2b344b97eba` |
| 剥离后 AST | `9caa7fd57a6d5bfc26f7f7ca018fff55e06602fe46e017104151d2b344b97eba` |
| strip_ast_equal | true |
| 诊断 AST | `ad9cffae8ccc82a794cd1526e071c79273a4340a17c6f8d6ef4c5a08779d3dc6` |
| 实际 clone marshal code | `0f617655acb02d70d248d8fd1d6bccf837f9d49349be441e47b8ba1613be9e43` |

运行后独立只读核查以 stdlib 解析原源及字面锚点并重新计算原 AST SHA，同时审阅剥离语法。剥离相等、诊断 AST 和 code SHA 的运行证据来自已保存回执。运行后的独立核查执行 clone builder／strip／compile 次数为 0。

130 个产品源与 12 个冻结 QA／输入／方案文件的实际字节均匹配 manifest。ready 记录 21 个已执行产品模块，finish 为 26 个，晚导入的五个模块见上文。Python 3.12.14、NumPy 2.3.5、Pillow 12.3.0 及其他外部模块记录路径／版本，外部依赖内容未 pin。外部解释器和第三方依赖的内容冻结仍属证据边界。

## 成本原账

所有数值均按原实测时间保存，RTT 扣减为 0。record、reset、snapshot 和阶段时间存在嵌套，以下分项保留各自范围。

| 入口成本 | normal ms | diagnostic ms |
| --- | ---: | ---: |
| 对象构建 | 8.6781 | 2.9951 |
| 8 次原函数 prime | 27.2353 | 27.7107 |
| 24 次完整 kernel | 118.1638 | 74.9370 |
| 完整 process 范围 | 154.9863 | 107.7645 |
| 仪表 reset 准备 | 0 | 0.1635 |
| trace snapshot 准备 | 0 | 1.0553 |

trace clock 读取共 1,360 次，另有 24×34＝816 次校准读取、384 对裸时钟校准。部分实测 recorder 窗口共 0.4028ms，与 reset／snapshot 合成 H 共 1.6216ms。校准中存在 0ns 间隔，时钟分辨率限制保留。context／generator 派发、参数构造及部分更新的总因果观测税未测。

| 控制器／发布成本 | ms |
| --- | ---: |
| 固定旧 helper 装载 | 37.1111 |
| QA 导出 | 40.1494 |
| 统计初始化 | 1.4180 |
| 产品快照导出 | 127.4024 |
| worker 启动到 ready | 1,367.7103 |
| 48 个 qualify RPC 往返聚合 | 281.9450 |
| finish RPC 往返 | 23.6946 |
| raw 发布 | 6.0872 |
| worker stdout 发布 | 1.3170 |
| summary 计算与发布范围 | 1.6087 |
| finally 清理 | 1.3535 |
| 内层 seal 前墙钟 | 1,906.0000 |
| 外层 Start-Process 至 exit 墙钟 | 2,042.8668 |

九次 JSON 编码／写入／flush 共 193,994 bytes、5.0686ms，terminal timing 自身发布排除于该 ledger。入口整数账可从 48 行重算，逐项等于 finish ledger 和 costs.json。CPU、RSS、累计 allocator、模型 token 费用未测，新增模型答案为 0。报告、离线核查、最终 hash 与 Git 提交在以上执行墙钟之外。

## 进程、输出与回收

外层命令使用既有 `D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe`，实际 argv、UTC 起止、PID、stdout／stderr 文件和 exit code 已保存于 `outer_execution.json`。运行一次，启动修补／重试／补样均为 0。实际参数为 `-I -B verification/perf030_003_qualify.py --freeze .../run_freeze.json --output .../qualification_01 --window-token PERF030-003-WINDOW-01`，各路径完整值保存在原件。

UTC 起点为 `2026-11-06T11:49:43.6547302Z`，终点为 `2026-11-06T11:49:45.7008231Z`。外层 launcher PID 为 23556，父 PID 为 12912，launcher exit code 为 0。一次 CIM 观察记录其直接子进程 conhost 10784 和 base Python 17864。17864 的 argv 同样为控制器 `-I -B`，实际 image 位于 Codex primary runtime 的 Python 路径，它是 venv redirector 的控制器子进程。

产品 worker 的实际 PID 和独立退出码未观察，固定 helper 的实际启动 flags 为 `-I -u -c`，其中没有 `-B`。控制器 finish 协议完成、48 个 seen entry 与账本完整、finally 已回收所登记 worker，run_status 的 all_workers_reaped 为 true。该证据未区分 worker 自然退出和 finally 对仍存活 worker 的 kill，base Python 的独立退出码也未记录。

外层 forced_cleanup 为 false，300 秒 hard deadline／295 秒工作截止及 310 秒外层兜底均未触发。硬截止与失败回收分支本批执行次数为 0，native handle／reader-thread 存量快照未测。外层 stdout、stderr 和 worker stderr 均为空，worker 协议 stdout 原件保存。

执行前／后匹配 Python 标记的列表为空。`cleanup_verification.json` 在 `2026-11-06T12:00:26.8057434Z` 再次查询 23556、17864、10784，结果均为空，匹配本轮标记的存活 Python 也为空。该复查支持本轮清理与窗口释放，完整孙进程树和每个原生句柄的终态仍未测。

## 证据封存与后续状态

批次根目录为 `verification/fixes/perf030_003/`，原件目录为 `qualification_01/`。其中包含 48 行 raw、协议 stdout、ready／finish、summary、errors、registration、完整成本、130 源快照、12 文件 QA／输入快照和实际 manifest。外层执行及清理复查记录位于批次根目录。

`EVIDENCE_MANIFEST.json` 对批次内全部封存文件及本报告、原静态方案、固定执行 QA／输入逐项记录相对路径、长度和 SHA256，自身由最终交付消息给出 SHA。原 run_freeze、QA、产品及运行原件在执行后均保持冻结字节。此次提交只增加报告与运行证据。

交付类别为 PERF030_003_COMPLETE／Stage A attribution-only，窗口 `PERF030-003-WINDOW-01` 可释放。共享 STATE 的更新由主线负责。主线收到封存提交后进入独立深审，本批到此结束。
