# PERF-020-O5-B 静态准备交付

## 本轮状态

本轮完成连接内部归因的静态实现和接线，执行状态为 **UNRUN**。Python、编译、测试、产品、Blender、探针和新增观察均为 0。准备完成后发送一次 `PERF020_O5B_READY` 给管理员主对话，实际执行等主对话签发本批窗口。

管理员已接受 O5-A-R1 的原件、恢复账本和完成状态。本批只处理该报告中尚未拆开的连接跨度。下一测试窗口优先 M3-003，当前 M2 只有静态准备额度。

准备起点为 `55300dae02d8e6df9118f2319c11a377314dc6c4`，工作分支为 `codex/perf010-direct-task-query`。本报告提交后的实际 HEAD、QA 源文件摘要、源副本和验收输入统一由 `verification/fixes/20261106_perf020_o5b/O5B_FREEZE.json`、`SOURCE_COPY_MANIFEST.json`、`PREPARATION_MANIFEST.json` 和 `PREPARATION_SEAL.json` 固定。本报告的提交身份通过 Git 和封存记录查询，避免写入自引用提交号。

本次本地 Git 提交收录本报告。QA 和原件沿项目现有忽略目录保存，由封存清单逐文件固定，并通过 READY 的本地路径交付管理员。

## 固定输入和唯一问题

使用 E 产品 `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15`，130 源摘要为 `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163`。入口仍取 O3 独立安装的 `ENTRY.json`，其摘要为 `45a6db52c6193b24b3e831ee15da5ec3edcbe629158a207e96ac5c003c5cea37`。本轮连接模块 `human_eye_plugin/blender_mcp_host.py` 的固定摘要为 `e3b31d9e1802f1fcb4e67da6702545d22fc450a2482cccd8334efa5e95f688c0`。

问题限定为原 `_connect` 较长跨度落在哪个原操作或剩余间隙。E/F 的该函数同文，包含一次 socket 创建、一次 connect_ex，以及 pending 分支的一次 select 和一次 SO_ERROR 读取。已有证据只能定位函数范围，可移除的等待成本仍未知。

原 tier64 fixture、五事实、请求期限、字节预算、背景控制和退出协议继承 O5-A-R1。新计划在委派和 QA 修改之前登记，计划摘要为 `25b5113a65559d8c6560c14ec10fdd76356a60295def02083f0a111680f1d966`。

## 唯一四会话方案

| 顺序 | 模式 | 产品臂 | 新 nonce |
| --- | --- | --- | --- |
| 1 | normal | A / E64 | f3bc2c95a2654d4dbcfcb774aed461b4 |
| 2 | diagnostic | A / E64 | 6e135611d0bb41e5ab9ac64689dc4e87 |
| 3 | diagnostic | A / E64 | dbbfcea452e941aba524b68790a1543f |
| 4 | normal | A / E64 | ada434765aa5457f9fa333f6d6d07f36 |

每会话固定 first 1、static 3、pose 3、geometry 3，共 40 条新观察，含 4 cold 和 36 warm。未来完整运行对应 44 次 stdio、40 次 physical RPC、4 个 Blender 进程及 12 个测量角色。每会话沿用 6 次背景控制、9 次 QA 赋值，产品 setter 为 0，保存为 0。

控制器使用原 `run_one` 及其资源生命周期，在原完成核验后追加本批嵌套账本。已存在输出目录会阻止重开同一批次，任一真实请求失败或状态不明即保存原件并停止后续。40 条完成或未捕获长跨度后结束本批。此次有限样本只用于归因，p95 和正式准入结论保持空缺。

## 采集实现

`harness/connect_internal.py` 从固定产品源码提取原方法，为两种模式执行同一份启动准备。normal 保留实际导入的原方法对象。diagnostic 选择有限插桩的源码克隆。

插桩只包围地址及目标准备、socket 创建、setblocking、connect_ex、select、SO_ERROR 和末尾 settimeout。实际原有返回值、select 期限及三个就绪列表、SO_ERROR 值保存在 RAM 账本。未执行分支显式保留 `unexecuted`。原来的成功判定、期限检查、异常和 close 路径继续存在。

克隆生成后，验收将剔除已知插桩 AST 并逐项比较固定原 AST，再比较原可执行方法体签名。实际生成源码、原方法和克隆 code object 的摘要由进程启动时记录。当前只固定生成器源码，生成结果及这些运行断言尚未执行。

`entry_worker.py` 在公共 bridge 包装器安装前选择连接实现。同一个 worker、外层 service/bridge/server 采集器、请求和计时边界用于四个会话。11 份未改采集器及输入副本按字节保留来源，worker 的起始来源摘要与实际修改后摘要分别登记。

`connect_ledger.py` 校验请求 owner、nonce、产品臂、源模块路径及摘要、实际选择的 code 摘要和七区间。区间与剩余间隙只分解各自原 bridge connect 父区间。`analyze.py` 读取本批原件、重建该账本，并保留普通模式只有外层跨度的事实。

## 观察成本范围

每次诊断调用新增 4 个基础 clock，以及每个实际执行区间 2 个 clock。预分配 8 个逻辑记录。基础逻辑容器为根字典、七个区间字典、区间列表及详情字典，每请求首次调用另建列表，select 返回后另建三个就绪 ID 列表。真实分配次数、单个对象成本和计时扰动仍未知。

每会话启动准备新增两个 clock，包围源读取、AST、还原、编译和身份构建。两模式都经过该准备，模式选择和记录发布的成本仍需按实际范围解释。请求准备跨度、末尾记录跨度及 worker JSON 的结构字段字节差可以单列，不能代替完整观察开销。

公共采集器保留原有成本记录。父子区间、请求 RTT、会话生命周期和外层命令 wall 有嵌套关系，分析器保留层次。子区间包含邻接的 helper、异常包围和调度开销，无法把区间整体解释为平台独占成本。未测扰动保留 unknown，不从 RTT 扣减。

`execution/run_command.ps1` 继承上轮外层命令记录方式，仅将本批记录根目录改为 O5B。未来每个实际检查、执行和分析命令保存完整 argv、UTC、wall、stdout、stderr 和退出状态。记录文件发布发生在外层计时结束后，子进程 CPU 和未插桩阶段保持未测。当前静态文件操作未生成可用于性能比较的完整端到端成本。

## 必要检查与静态纠正

`checks/test_connect_internal.py` 接好 20 个固定、独立预期的原方法与诊断路径检查。范围包括即时及 pending 成功、错误返回、空或 exceptional 就绪、外来 writable、SO_ERROR、连接前及完成时超时、各平台操作异常、BaseException、close 异常身份、返回对象身份、完整调用序列和单次调用计数。使用从真实固定文件提取的方法体和假的平台依赖。

同一检查入口还将启动真实 `-I -B entry_worker.py --entry-check`，验证其公共导入和 controller 接线。该路径在产品 bootstrap 之前退出。测试脚本和 worker 检查都需要本批主对话授窗记录，后续真实会话另需通过的检查证明。

静态复查已经修正两个准备问题。最初方法体签名构建遗漏原模块的 `future annotations` 编译标志，现已从固定源码获取并应用于原签名和克隆编译。最初账本还使用了与采集器不一致的模块摘要字段，现统一为 `original_module_sha256`。三个 select 就绪列表及对应逻辑对象计数也已对齐。以上均在首次编译或测试之前修正，运行通过状态仍为 UNRUN。

平台异常身份测试以观察器正常工作的条件为范围。clock 或 RAM 记录本身发生异常时，插桩可能改变异常传播，该极端观察器故障尚未覆盖。原函数继续存在并不构成取消能力的实测证据。

子代理初次 Agent Learning 连接出现过 unavailable 或未绑定返回，实际记录保留。静态工作沿固定父任务分工推进，子代理没有使用父对话 handle 写入任务。

辅助独立复核的一条只读 PowerShell 命令曾因 foreach 后直接接管道而出现 ParserError，改为先收集再输出后完成读取。该首错保留在子代理工具记录中，未触发 Python、测试、封存或文件修改。

## 下一次执行入口与验收

先验证独立授窗记录的来源、固定 freeze、四个 nonce、窗口 token 和主写 STATE。必要检查应先得到 `perf020-o5b-required-checks` 的实际通过原件，再以同一 freeze 运行四会话。入口保留 `-I -B`，完整参数模板随静态交付固定，未来 grant 参数由实际接收记录补入。

每条观察继续核五事实、来源、捕获分母、零产品写入和清理原件。PID 与创建时间绑定的进程退出、reader、socket、sampler、句柄清理沿原生命周期记录。当前启动产品及测试进程数为 0，实际清理仍待窗口内验收。

完成后只提出一个由实测区间支持的后继假设。若较长 connect 集中于 select，结论限定在原等待范围。若落在其他操作或 residual，保留该区间及观察器成本边界。没有捕获时明确报告未捕获。

E 的 PT 假零和假目标仍开放，O4 的 F 正式准入失败仍保留。本批新增模型消费答案为 0，token 和费用未测，旧的预算预留不作实际消耗。
