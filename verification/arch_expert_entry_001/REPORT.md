# 局部手臂专家入口验收报告

ARCH-EXPERT-ENTRY-001 已将接受的 M6 来源和专家接入现有 Blender host、worker、owned/shared bridge、LiveSpatialService 和 MCP。显式只读工具 `human_eye_arm_twist_observe` 在 Blender 内获取当前局部手臂并返回合成训练模型的扭转塌陷估计。最终相关 CPU 组 165/165 通过；同版实际入口组的 25 次调用符合预期，其中 14 次真实模型估计、2 次预期域外拒绝、9 次普通读取。另行运行的 M5 零步、一步、四步实际回归均通过。

本报告交付给主线深审。当前模型的输出范围是指定闭合截面上的合成扭转塌陷估计，入口不提供自动选区或角色修复。完整任务相对原生的分档收益仍需单独验收。

## 固定产品和来源

工作树为 `C:/Users/Administrator/.codex/worktrees/2c7d/hefe`，分支为 `codex/architecture-expert-entry`。实际 QA 开始前已固定产品与相关测试提交 `c5116e30024ed12825aea6119c0f5172e6b9b46d`，其后未修改产品。136 个运行来源文件的 canonical SHA256 为 `239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9`；实际入口和 M5 的运行前后来源均一致。证据提交是该产品提交的直接后继，可由 `git log` 确认。

| 接受来源 | 本分支提交 | 用途 |
| --- | --- | --- |
| `76375c0dd4c274120918b9984ec4829ac56740ed` | 原提交 | 已接受 M5 产品和证据基线 |
| `ef84ecc59f107321225d0d832fde119ed0b91e3f` | `f447baef5c56367a5b1d26561832a7016daefe60` | M6 合成训练专家 |
| `9508a1d5cbdcadad80a42c4922501c855d5ae570` | `968436ce5de316bef33ebc47d9147ae584945fd7` | prepared 和批量截面推理 |
| `b2d92bb5802cc86b855f5a7179fdff80812c2e25` | `539c277daa0088e30b0073d40aeb5e4368b44f6c` | 原生局部手臂来源 |
| 本次接线 | `c5116e30024ed12825aea6119c0f5172e6b9b46d` | 入口、相关测试和目录预期更新 |

`3ff76aba2a8f1592a5109ca91430496db57e1773` 是已拒绝来源优化的失败证据，本分支未合入。`human_eye_plugin/arm_twist_source.py` 保留接受字节，SHA256 为 `653eaaa9ee3292a1a490ba4a01637e495977bd9f668e1c584c9649927cf92715`。原 M2/M3/M5/M6 算法和模型权重沿用接受版本；历史验收直接引用原目录，不计入本次分母。

## 入口实现

BlenderSceneHost 按需持有一个 adapter 和当前 selection 的 bound。相同 selection 沿用绑定，`bound.analyze()` 每次只调用一次。绑定已保存脱离调用者的 selection；入口仅用递归的精确类型比较判断复用，避免 Python 中 `True == 1`、`1.0 == 1` 让非法暖输入绕过来源层严格整数检查。该问题由独立审查发现，在固定产品前修正，并增加了顶点和截面两处的回归。

四个依赖 `rig_pose.py`、`arm_twist_weights.py`、`arm_twist_expert.py`、`arm_twist_source.py` 通过既有 `_exec_source_snapshot` 执行。shared 初始 resident 设置仅冻结依赖字节，首次明确专家请求才执行；owned 使用既有 SourceGuard 固定来源。私有包名由根路径及冻结字节导出，防止共享解释器中的不同根相互占用 canonical 包。子模块使用真实来源路径接受现有执行见证；私有父包无 `__file__`，四个相对依赖在执行来源模块前全部放入同一包，避免后续转读磁盘或 pyc。没有新增 finder、注册服务或来源白名单。半初始化失败清理本次创建的模块，后续可重试。

两个 bridge 复用现有较大通道：owned 的专家命令使用既有 64 MiB 行通道；shared 的内外专家载荷使用既有 1 MiB resident 通道。既有小动作和普通读取长度限制保留。bridge 仅核对报告版本、状态和当前对象/骨链绑定；完整 selection 语义仍由接受的来源层负责。CPU 用超过 64 KiB 的稀疏高 ID selection 检查真实编解码器及解析器，实际 Blender selection 为 19,374 B，已跨过旧 4 KiB/16 KiB 限制。

LiveSpatialService 沿用请求上下文、读取锁、来源身份和预算检查，单次调用 host，并在报告 `source.runtime_source_sha256` 附上当前运行来源摘要。该路不进入动作 runtime、账本锁或保存。现有 LiveSpatialMCPServer 追加一个简短显式工具；owned_task_mcp 将同一读取工具委派到原 MCP 实现。estimated 和 unknown 是正常报告，异常沿用现有请求处理，下一次合法查询可继续。原 query_policy、旧 observe/router、窄 relations 目录未新增专家路由。

## CPU 检查和保留失败

本次累计 521 次 unittest 方法执行：517 通过、3 个失败、1 个错误、0 跳过。此数字是重复执行次数，最终不同方法数为 165。

| 记录 | 方法执行 | 通过 | 失败 | 错误 | 来源摘要前缀 | 结果和处置 |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| entry_tests_01 | 13 | 12 | 1 | 0 | 2027bcd5 | fake scene.objects 缺少原生 `.get()`，修正测试夹具 |
| entry_tests_02 | 13 | 13 | 0 | 0 | 2027bcd5 | 通过 |
| entry_lazy_03 | 1 | 1 | 0 | 0 | 2027bcd5 | 加强私有包延迟加载扫描，通过 |
| affected_01 | 164 | 162 | 2 | 0 | 940a5c3c | 两个工具目录断言仍用旧计数，更新维护测试 |
| affected_02 | 165 | 164 | 0 | 1 | 239cc00a | 新回归在稀疏 ID 夹具中寻找 0/1，引起 StopIteration；改用显式 zero_based 测试夹具 |
| affected_03 | 165 | 165 | 0 | 0 | 239cc00a | 最终全部通过，来源前后不变 |

最终组覆盖 host、worker protocol、两种 bridge、readonly loader、service、MCP、owned_task、既有 selection 复用和 M5 local loop 复用。新增 14 个方法覆盖大 selection 通道、报告绑定和错误恢复、无动作账本写入、estimated 返回、真实接受模型的 fake-bpy 单 capture/prepared 复用、调用者修改、场景 epoch、延迟固定来源、晚改磁盘不生效、半加载恢复和暖输入精确类型检查。

所有失败日志均保留。affected_01 的两份旧目录断言另存为 `FAILED_CATALOGUE_01_*.txt`。affected_02 的原始第 14 个测试文件未在修正前抓取；`RECONSTRUCTED_affected_02_test_source.py.txt` 是明确标记的重建，`RECONSTRUCTED_affected_02_notes.json` 声明 `original_bytes_claimed=false`，不能作为原始字节见证。最终 affected_03 和早期 entry 组保存了执行时测试文件。后续 runner 已增加执行时快照。

## 实际 Blender 入口

实际执行只在主线交付 Blender 窗口、固定 c5116e3 和来源摘要之后开始。使用生成的双骨 LBS 手臂和刚体盒，无用户资产、模型 API、网络训练或全局设置变更。手臂全 mesh 为 24,804 顶点、9,866 三角形；局部选择 1,602 顶点、3,200 三角形、25 个截面，原始顶点 ID 为 `20000 + 3*i`。选择保留高稀疏原始 ID，输出截面仍返回这些原始 ID。

首轮 `actual_run_01` 保留失败：普通 task 成功，随后 nearest 遇到既有 `acquisition_static_triangle_source_required`，因为同一场景中仍存在 Armature。此轮两次工具尝试，主 RESULTS 记录了一个成功，第二次失败在 stdio raw、metrics 日志和 traceback 中；专家调用与 setter 均为 0。未扩大产品域。仅修正验证控制：普通读取前从 scene unlink 手臂/rig，专家请求前再 relink 同一数据对象，控制操作在测量工具之外。

第二轮 `actual_run_02` 一次完成，25 次工具尝试全部符合预期。

| 入口 | 专家成功估计 | 预期域外错误 | 普通 task/nearest | 专家状态覆盖 |
| --- | ---: | ---: | ---: | --- |
| owned 默认 worker | 6 | 1 | 3 | 首次、重复、变姿态、静态变化、错误恢复、load 生命周期均 estimated |
| shared socket resident | 6 | 1 | 3 | 同上 |
| owned_task 既有委派 | 2 | 0 | 3 | 首次、重复均 estimated |
| 合计 | 14 | 2 | 9 | 23 次正常成功加 2 次预期负例 |

14 次成功均执行真实 MLP；直接 oracle 基于当前原生 RNA pose 构造输入，交给同一冻结模型，独立于产品 bound.capture。逐次比较输出严重度、flags、25 个截面和原始 ID，350 个截面分数与直接结果完全相同。unknown 的正常报告语义由静态代码审查确认，本批 CPU 和实际 Blender 均未单独动态覆盖该状态。两次域外拒绝之后均有成功恢复及后续普通读取。

三入口在首次专家前的普通 task/nearest 后均无 Blender 侧 NumPy、权重或专家模块；首次专家时才加载。父 MCP 旧 core 自带 NumPy，未对旧依赖作额外改造。owned/owned_task 沿用默认 worker，shared 通过真实 socket 执行 bridge 生成代码；冻结载荷及 raw 传输均保留。

成功请求的 product capture 工作计数各加 1，共 14；两个域外请求进入 capture 方法后拒绝，工作计数 captures 不增长。因此方法入口计数为 16，成功 capture 工作计数为 14。三个 repeat 请求的静态读取和 prepare 均为 0；owned/shared 的 pose 和 recovered 会重新核验静态数据，但 prepare 为 0、prepared 对象保持；static 和 load 请求各重新 prepare 一次。读取量、完整调用时间及字节见 [实际成本报告](ACTUAL_QA_REPORT.md) 和 [逐次成本数据](ACTUAL_COSTS.json)。

## 同版 M5 实际回归

专家进程关闭后，在同一 136 来源摘要下调用既有 `m5_local_loop_opt_001/run_owned_qa.py`，使用单独生成的刚体夹具运行零步、一步和四步任务。这里的 3 个 scheduler 调用与专家 25 次工具调用分开；实际物理 setter 为 0/1/4，未把验证捕获或方法入口计作动作。

| M5 情形 | 实际 setter | loop ms | loop bridge 请求 | loop TX B | loop RX B | worker 退出码 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 零步 | 0 | 343.8256 | 15 | 1,952 | 83,802 | 0 |
| 一步 | 1 | 457.7133 | 19 | 4,840 | 96,113 | 0 |
| 四步 | 4 | 786.3029 | 28 | 11,186 | 132,717 | 0 |

各任务完成后另有 task/nearest/task 共 3 次读取，三情形合计 9 次，不计入 loop 时间、请求和字节。原生 RNA 核对最终间距和位移，其余三对象保持；任务完成后读取前后账本摘要相同，生成 fixture 文件前后 SHA 相同。3 个任务均完成、持久化并关闭 worker。原始 receipt、请求帧、计数、完整生命周期时间和原生状态见 `actual_run_02/m5_same_source/`。

## 成本和覆盖边界

实际入口 runner 序列为 19,534.3209 ms，包括夹具生成、验证控制、oracle 和 M5 等，并非完整 Python 启动耗时或性能保证。完整工具 RTT 包含 profiler、工作快照、直接原生 oracle 和 JSON 写入等未单独扣除的验证开销；`product_method_ms` 在调用 oracle 前截取。两类时间不可互相替代，inclusive profile 也不可相加作为总时长。具体分项保持在成本数据中。

来源层 Python 读取行计数区分当前顶点、rest、weights、bone 和 topology；BMesh 的 `from_mesh` 和 lookup 仍可能遍历全 mesh。局部选区行数和 prepared 复用不能支持 O(selected) 总成本结论。本批只验证新增接线，不重跑已拒绝拓扑优化，也不据这些组件数据推导完整任务对原生的收益目标。

shared fixture 以 controlled terminate 后 wait 关闭，返回码为 1；owned/owned_task stdio 和 M5 worker 返回码为 0。原 QA 进程均已结束；Windows 已将 PID 37792 复用给 VSSVC.exe，清理原件保留进程身份核对，见 [进程核对](PROCESS_CLEANUP.json)。本批运行来源无变化，未触碰用户场景或全局配置。

## 证据与复核

本目录保存测试 runner、各轮日志/结果/来源摘要、产品 diff、实际传输原始字节、Blender observer、直接原生 oracle、生成 fixture、失败尝试和 M5 同版回归。`RESULTS.json` 汇总分母及结论；`REVIEW.md` 保存独立只读审查范围与发现；`EVIDENCE_INDEX.json` 列出除自身以外所有封存文件的字节数与 SHA256。封存核对同时比较磁盘文件与 Git 暂存 blob，保留原始二进制和换行字节。

主线后续深审可基于固定产品及本证据判断新增接线是否存在值得处理的实际热点；本批不再打开既有算法优化。
