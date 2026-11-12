# COMPACT-FACTS-001 五次实际观察：独立语义与成本复核

2026-11-13。结论：**本子审的实际语义、10 KiB 正文目标及计数门通过，没有阻塞工程收口的问题。尚无新模型消费收益结论。**

固定产品 `452b44d2dcf231d6675bef54e568db0431a29261`，交付 `6ab4e53409e539c71a377f48708f2f8725db6dde`，运行源码摘要 `4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6`。输入来自实施树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_compact_facts_001`。

本轮只在根复核目录写独立脚本与结果，不修改作者树、产品、Git、默认入口或资产；没有启动 Blender、消费者或 API。没有导入/执行作者核验程序。`recheck.py` 使用 Python 标准库独立解析原件，最终 **5,397 个断言通过，0 个失败**。断言数是核查条数，不能当成独立场景样本量。

## 作者记录与本轮核查的关系

作者报告用于确定原件位置，`RESULTS.json`、receipt 中的成功布尔值不作为几何正确性的答案。本轮从普通 stdio TX/RX、宿主 WIRE、原始 audit、快照、历史 truth 独立还原后，再与作者汇总交叉比较。

共 60 个输入留有字节数和 SHA-256。当前批被读取的证据同时匹配交付 manifest 和固定 delivery 的 Git blob；旧资格与旧 full 也绑定 delivery 中的实际 blob。完整源码/wheel/全部 manifest 的审计由另一个子审承担，这里不重复声称完成。

几何答案复用已固定资格 BASE/EDIT truth，核其 SHA-256 为 `a0f14b1a…b656c7` / `ccbc66e4…b1e91`，快照为 `f8a578f7…9884b` / `beb4e441…ffd80`。再逐一核对 552 个精确平方距离与根历史独立有理数重算 `ORACLE_RECOMPUTE.json`，后者绑定固定根提交 `dd11f1aa97ad0bf8bb314a86cd91b32ff0123874`。这属于**复用经独立核实且同几何的精确答案**，不是本轮重新求解全部三角形对。本轮另写了点到三角形的投影/线段最短距离检查，实际验证 full 见证点。

自身 Agent Learning `session_context` 显示子 assignment 仍归旧任务，`current=false`，新 parent task 为 `785ae4e9…`；本轮依据父 Agent 明确新派单完成离线复核，没有借父句柄或回写父任务，也不把旧 assignment 记为新绑定。

## 五次实际结果

| 实际观察 | 匹配行 | 完整业务正文 UTF-8 B | 客户端完整请求 ms | 新核调用 | 宿主捕获 | 纯投影 ms | inclusive content_encode ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| BASE default | 71 | 7,911 | 1761.1765 | 112 | 1 | 0.6506 | 0.9540 |
| BASE brief | 71 | 7,911 | 40.6833 | 0 | 1 | 0.6268 | 0.9348 |
| BASE full | 71 | 34,754 | 47.0880 | 0 | 1 | — | 0.2425 |
| EDIT default | 72 | 7,912 | 159.8546 | 10 | 1 | 0.6347 | 0.9338 |
| EDIT full | 72 | 35,209 | 42.3963 | 0 | 1 | — | 0.2465 |

- 三份紧凑输出共 **214 行**全部恢复 object ID/name、原 `distance_m` binary64 位、顺序与逐行 metadata。22 个对象表条目均被引用，索引与宿主 24 个对象的完整身份目录一致；表声明为匹配端点子集，没有将 22 误写为场景总数。`distance_mm` 等于原米值的派生乘积，不用于重新判断阈值。
- 两份 full 共 **143 行**；五次共 **357 行**。全部 top-level 原字段与同状态 full 一致，仅每请求 trace 可以不同。`binding`、覆盖数、scope、source envelope、unit、未知列表、delivery 范围及 `execution_authority=false` 保留。每次实际输出的 unknown 都是 0，这五次本身不构成非空 unknown/partial 的运行案例。
- 独立核对每次全部 276 对分类，共 **1,380 个对象对分区**、**564 个已测距离**；无漏配、误配、重复对。BASE 为 164 排除 / 71 匹配 / 41 非匹配；EDIT 为 162 / 72 / 42。原始浮点与 private dispositions 位一致；对精确答案的最大距离误差为 `1.0842021724855044e-19 m`。
- full 的 **286 个见证点**用本轮新实现验证在所属对象三角表面，最大残差约 `4.316e-15 m`；两见证点间距与公开距离最大误差约 `1.4095e-18 m`，均小于既定 `1e-10 m` 门。
- BASE full 对旧消费 P1 full、EDIT full 对旧工程 sequence_01 edit：除 binding/trace 外**所有字段及浮点位相同**。不是只比较行数或摘要。
- 每状态的实际快照与资格快照仅排除 pid、临时 blend 路径后完全一致，均为 24 对象 / 530 顶点 / 978 三角面。BASE→EDIT 的 binding 只改变 directory SHA、scene fingerprint、scene revision；document epoch 和来源保持一致。

BASE default/brief 正文相对 full 减少 **77.2372%**；EDIT default 减少 **77.5285%**。计入对象表、说明、身份绑定的完整普通 MCP 文本，不是仅量 matches 数组。三份紧凑正文都小于 10 KiB。外层 stdio RX 则分别为 8,670 / 8,668 / 37,270 / 8,675 / 37,757 B，与正文口径分开。

## 成本与时界

五业务观察全部尝试并完成，失败/未尝试/自动重试均 0。原始 WIRE 中每次恰好一个 `capture_surface_scan` 请求，ID 对应捕获回复，audit 恰好一个 host.capture span。几何核调用 112/0/0/10/0 与逐对 work 及可用测量缓存计算计数增量一致。这里核的是已封存遥测的一致性，没有另运行 profiler。

业务宿主请求共 **104,520 B**，宿主响应 attempted 共 **538,172 B**；每个实际原件长度都与 WIRE index 相符且 sendall 完成。完整九次宿主 RPC 包含 BASE 快照、姿态修改、EDIT 快照、close，合计请求 **113,760 B**、响应 attempted **1,471,309 B**。不能用 7.9 KB 业务正文取代内部采集量。

首个业务捕获新构造 530 顶点、978 面、1,469 边的资源数组，后四次新数组均 0；measurement cache 已计 bytes 从 BASE 181,984 到 EDIT 198,307。该计数自身声明不含临时工作，不能当完整进程内存或峰值。

全部五客户端请求 wall 总和为 **2,051,198,700 ns**；每个值直接由各自整数 `ended_ns - started_ns` 复算。完整 session 从 owned 启动前到五请求、QA、回收、RESULTS 写入关闭，共 **4,862,992,900 ns**。这是一个顺序 session 的总成本，不能再加五请求总和。最后计时回执 publication 为单列 **772,400 ns**，其自身 receipt 的写入成本仍被原口径排除；原期限仍满足。隔离构建/安装 **4,094,500,700 ns**来自绑定的作者安装回执摘要，作为外部准备成本单列，本子审未独立重做安装。

投影 650,600 / 626,800 / 634,700 ns **已经包含**在对应 content_encode 954,000 / 934,800 / 933,800 ns 内；核过 parent_span 和起止包含关系。不得把纯投影再加一次，也不得把 inclusive service/capture/geometry span 直接求和。单次 cold default 与后续 hot full 的 wall 不具有性能 A/B 可比性。本批只证明展示投影的直接成本很小且没有额外宿主/几何调用，不能从这些顺序值计算稳定整任务收益。

## 原异常、未运行与结论边界

原始 worker 事件实际有 **9 条**：第 9 条 close 的通用 event 仍写 `status=unknown`。单独 WIRE/009 回 `closed`，launcher wait/reap、runtime exit 与 FINAL_TIMING 完成证据齐全。保留此日志不一致，不能将其擦成 completed；也不将其算成五业务观察中的未知动作或几何失败。

本独立脚本第一次误将 worker 事件分母设为 8，因此一项断言失败；该次 `ATTEMPT_01_RESULTS.json`、`ATTEMPT_01_CHECKS.json`保留。检查第 9 条确为 close 后改为分别验收九条分母与关闭证据，最后 5,397 项通过。作者历史的初次 38 errors、投影异常回退修复、runtime proof 标签勘误不因本子审通过而消失；本子审未重跑其 180 方法或 13 schema 项，不把作者测试计入本轮分母。

未运行：新消费者、三路任务对照、真实 token/费用、provider 实际收到输入、非空 unknown/partial 实际宿主案例、全三角对精确求解重跑、fsync/瞬时外部编辑检测。没有声明通用大场景、动态来源或跨模型收益。

**建议父复核：此子审可关闭紧凑展示的实际工程门，完成其他源码/边界子审后冻结同一候选开展预登记消费对照。不要继续仅优化字节；真正待验证的是模型是否直接消费 71/72 完整事实、是否减少原生重算，以及同质量的完整时间与 token 成本。**

重跑：

```powershell
& 'D:\hefe\.human-eye\releases\9.7.2+20261028.support.discovery.r1\.venv\Scripts\python.exe' -I -B -X utf8 'D:\hefe\verification\fixes\20261113_m4_surface_scan_compact_review\engineering\recheck.py'
```

结果文件：`RESULTS.json`、`CHECKS.json`、`INPUT_HASHES.json`；独立审计实现：`recheck.py`。
