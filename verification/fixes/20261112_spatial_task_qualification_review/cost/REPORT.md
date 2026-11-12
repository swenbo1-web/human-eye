# SPATIAL-TASK-QUALIFICATION-001 独立成本与执行分母复核

复核者 `/root/discovery_scope_review`，2026-11-12。结论：固定证据内的请求数、原始字节、时间锚点、业务未知和退出记录一致。资格核验可收口，装配任务仍未完成。本轮未运行产品、Blender、消费者、作者 verify_saved.py 或任何几何求解模块。

固定证据提交为 `93121974595badc90944d5353d23ae7897feda54`；产品为 `fac9b4373575d653cc96f39f1dcb225300cd5977`，137 源摘要 `6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb`。独立脚本读取 Git blob，逐字节核对 125 个资格档案及 5 个既有 runner/生命周期依赖，共 130 文件；另独立核对 INDEX 的 123 文件及 COMPLETE 摘要。最终 RUN05 为 544/544 数据检查通过，原件未修改。

## 实际分母与结果

- 仅一份 `FORMAL_STARTED`、一份实际 `run_01`、一次正式序列；未发生产品重放。正式独立 oracle 的保存数据回放不属于产品重放。
- stdio 为 7 条 TX、6 条 RX。其中 initialize、initialized notification、tools/list、ping 共 4 条元数据消息及 3 条响应；notification 无回执。元数据阶段没有宿主 RPC。
- 业务为目录、装配 task、控制 task 各一次，三份实际原始回复均收到。宿主另有一次 QA evaluated 快照和一次 close，总计 5 RPC。
- 目录 14/14 对象完成；装配 4 个 AABB 可测，3/3 对的 surface 与 closed relation 均 unknown。3 项 4mm 要求、三候选最近关系及定位仍未解决，装配完成数为 0/1。
- 控制 1/1 完成，原始公开事实为 separated、距离 1m。公开见证两点均是实际快照顶点，点距平方精确为 1；76B 是紧凑 JSON 见证值，不是完整 escaped MCP 回包长度。
- 装配 `unresolved_distances={}` 与 3 项 `unresolved_relations`、`nearest_separated_complete=false` 同时存在。不能只看空 distances 误判完成。
- 原始 observe 工作记录的 surface/closed 入口数各 3；三对已发布 surface 计数全 0、closed 仅每对 work_units=1。入口数不是完成精测数，也不代表未发布内部工作全部为 0。

## 原始传输与时间

下表字节来自 REQUEST.bin / RESPONSE.bin 的实际长度，再核对 wire sendall 回执；业务时间来自 RESULTS 的 started/ended。每个宿主事件只落入一个对应窗口。

| 窗口 | 外层 ms | Host RPC | TX B | RX B | 模型可见事实文本 B |
|---|---:|---:|---:|---:|---:|
| QA evaluated 快照 | 54.9257 | 1 | 2,912 | 127,753 | QA，不交付消费者 |
| 目录 | 57.4132 | 1 | 88,787 | 6,697 | 6,448 |
| 装配 task | 45.9290 | 1 | 1,555 | 70,247 | 5,374 |
| 控制 task | 37.3674 | 1 | 1,573 | 3,603 | 3,087 |
| close | 独立关闭窗口内 | 1 | 17 | 62 | 无 |

宿主合计 TX **94,844B**、RX **208,362B**、总 **303,206B**。stdio 合计 TX **1,647B**、RX **42,288B**、总 **43,935B**；stdio 与宿主桥是不同链路，不能把桥接大回包直接称为模型输入 token。元数据的 tools/list 也已计入 stdio 总额。三次业务外层总时间为 **140.7096ms**。

首次目录请求含两段压缩宿主源码字面量，分别 3,928B 与 59,736B，总 **63,664B**；解压源码分别 9,506B 与 199,768B，总 **209,274B**。这些字面量已包含在目录 TX 88,787B 中；解压结果是离线核对所得，不能再次当作线上传输相加。后两次 task 没有这些源码字面量。没有独立计时可把源码建立从该次目录窗口剥离。

完整 owned 会话为 **2,992.0426ms**。不重叠的记录阶段（Blender 启动 1,068.6467、产品启动及元数据 1,313.3557、QA stage 54.9293、独立绑定 26.2717、关闭计量发布 295.7640ms）与业务窗口合计 **2,899.6770ms**；会话内其余 **92.3656ms** 没有单独分项，应保留为未分配协调工作，不臆测归因。stdio receipt、worker elapsed 都是这些窗口的子窗口，不能再次加总。

正式 launcher 进程计时 **3,220.628ms** 包含完整 owned 会话；派生资产构建 **2,755.9164ms**、正式离线 oracle **539.2215ms** 是另外的准备/核验窗口。不能把这些选定窗口之和称为从任务接收到最终交付的完整工程成本，后者未测。

通知中的 **54.9293ms** 与 REPORT 的 **54.9257ms** 没有矛盾：`run_entry.py` 先保存 QA row 的 `ended_ns`，再调用一次 `perf_counter_ns()` 写 stage。两者相差 **3,600ns / 0.0036ms**。`NativeSession.run()` 内层 receipt 为 **54.3821ms**，末端计时在其后续源文件哈希字段构造之前，属于第三个、更窄的边界。

## QA 工作和生命周期边界

原始工作计数与增量独立核对：额外 QA 快照 14 次 to_mesh/三角化；产品目录 14 次 to_mesh、848 次目录顶点 forward、0 次三角化及 0 完整网格 resource 数组；后续装配新增 4 次、控制新增 2 次 to_mesh/三角化，装配新资源为 576 顶点、1,136 面、1,704 边。

固定 `owned_native.py` 的 `_scene_state` 还读取原始 mesh 的 vertices、edges、polygons，`execute_code` 前后各调用一次 `_scene_fingerprint`。四次 execute_code 均受此 QA 全场检查约束；启动、关闭还有各自检查。因此产品目录“0 三角化/0 完整资源”不等于本次 QA 链路没有全场原网格读取。现有计时没有隔离这些扫描，无法把整个工具窗口称为纯采集/几何内核成本。

实际 Blender PID 21360 的 raw close 回复为 closed；拥有该 Popen 的记录确认 reaped、exit0，初末几何指纹一致且未 poisoned。产品 launcher PID 37576 和实际 Python runtime PID 33812 是不同进程；保留的 Windows 进程创建时间/父链与 retained handle 证明后者归属，真实 runtime 的 exited、exit_code=0、handle_closed 均成立。不能只用 launcher exit0 替代 runtime 退出证明。

close 的通用 worker event 留有 `status=unknown`：固定 worker 的 close 分支没有重写通用事件状态。该字段不是实际退出未知；原始 close 响应、WORKER_CLOSED 和拥有者 Popen 等待结果共同确认正常退出。报告不得把该历史原值改成 completed。

## 失败历史与解释限制

测前 harness 的两处缺口和 prepared02→03 差异均保留：完成判断要求实际三份回复且无 transport/harness exception；实际 runtime 退出须 exited 且句柄已关闭。准备历史是测前代码缺口，不是正式产品执行失败。正式 harness errors 为 0，三对装配的真实能力缺口完整保留。

本复核自己的 RUN01–03 失败记录保留，原因分别为 Windows 归档 CRLF 与 wire LF 的错误等同比较、误将带协议标记的 stdout 当作裸 JSON、将 run_entry.py 误收为 run 目录。只修正独立解析脚本；RUN04 和最终含工作计数检查的 RUN05 均成功，没有重跑产品来改变结果。

没有发现成本记录的阻断性错误。这是单次资格与瓶颈定位，不能推出稳定性能收益、原生对照胜负、用户资产泛化或模型 token/费用收益。几何证书的完整数学复核由本批另外的独立审查承担；这里核的是实际分母、公开事实状态、原始成本和生命周期。

本报告支持下一项针对已观察到的准入前门缺口开展有限 M3 改造；它没有证明删除面数乘积门之后 G508 必然完成，也没有授权扩大未测矩阵。

复算入口：`audit_saved_cost.py`；结果：`RESULTS.json`；逐项检查：`CHECKS.json`；Git 来源：`SOURCES.json`；最终运行记录：`RUN05.txt`。全部位于本报告同目录。
