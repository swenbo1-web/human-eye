# PERF-020-O5-A 时界诊断阻塞报告

## 判定

本批保留 `failed`。唯一实际序列在第一个 8-E 会话完成后，因冻结 QA 账本的区间包含检查失败而停止。实际完成 10 次观察，后五个会话、50 次观察均未运行。完整 E/F 时界归因尚未完成，O4 的 F 未准入结论继续有效。

工作树 130 个产品文件保持接受的 E。独立复核确认 E、F 两份既有隔离安装各 130 个文件仍与原绑定一致。此次交付为诊断证据与报告。

## 固定版本与执行依据

| 项目 | 绑定 |
| --- | --- |
| 分支 | `codex/perf010-direct-task-query` |
| 执行时 HEAD | `d67ff7f735461b284088cc1db4fa43f40ea589ab` |
| E 产品提交 | `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15` |
| E 源码 SHA256 | `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163` |
| F 产品提交 | `b644c79430ced0c710dc9c8c27b2c72598dfe63f` |
| F 源码 SHA256 | `30b28aab341dcec6d7504a95a15089acda506af0a0c11bd14ffd6644ecdb258d` |
| 预注册诊断计划 SHA256 | `f3e16262d370a948babab00aee5ad79104d136b8c345981ea4cd5292cacfd520` |
| 唯一执行 FREEZE SHA256 | `bf6d90d915ede327d26a76595968e2e342e3c09fd5769612b08ee012349cda2b` |
| 独立启动复核 SHA256 | `d84f7ef4f31890a6660182eb5b0b4a27c0cb57c1d6b53670f4e2d2de930c2d85` |
| 测量窗口 | `PERF020-O5A-WINDOW-01`，最终回执明确释放 |

原计划最多六个独立 Blender 会话，顺序为 8-E、8-F、64-F、64-E、256-E、256-F。每会话包含 first、3 static、3 pose、3 geometry，沿用原五项事实、背景控制、精度、期限与尺寸预算。实际第一条业务请求前未执行宿主观察模板。

CLI 中保留的 `formal` 只用于选择旧十请求与背景控制流程。本批 `kind=diagnostic`、正式评分序列为 0、诊断序列为 1。执行源及输入见 [FREEZE.json](D:/hefe/verification/fixes/20261106_perf020_o5a/cost/diagnostic_01/FREEZE.json)。

## 实际分母与质量

| 项目 | 实际记录 |
| --- | --- |
| Blender 会话 | 1，8-E |
| 测量进程实例 | 3，Blender、service、launcher 各 1 |
| stdio 请求与响应 | 11，initialize 加 10 次业务 |
| 客户端 physical exchange / 服务端 accepted request | 10 / 10 |
| 构造 / 几何采集 | 10 / 10 |
| 当前类首次包装 | 10，E 每次源码执行产生当前类 |
| 五项事实 | 10 次全部严格通过原核验 |
| 每次选中几何 | 2 对象、16 顶点、24 三角形 |
| 背景控制 | 6 次，位置、旋转、顶点赋值各 3 次 |
| 产品 setter / 文件保存 | 0 / 0 |
| 资源记录 | 39 份 live 加 3 份 terminal，共 42 份 |
| 未知 live 内存字段 | 0 |
| 实际执行重试 / 补样 | 0 / 0 |
| F、64、256 新观察 | 0 |
| 新模型消费答案 | 0，token 与费用未测，历史 US$0.02 预留原样保留 |

三个测量角色均正常退出，exitcode 均为 0。reader 线程、socket、sampler 及进程句柄均已收尾。service 全生命周期 CPU 为 953.125ms，Blender 为 1031.25ms，launcher 记录为 0。原始观察、身份、内存峰值及 CPU 字段逐项保存在原始文件及独立复审中。控制器属于额外 QA 支撑进程，不计入上述三个测量角色。

宿主启动至 ready 约 782.838ms，服务启动至 ready 约 847.115ms，EOF 至 service 回收约 115.295ms，Blender 关闭约 196.051ms。完整 instrumented QA 周期约 2827.987ms，包含背景控制、STOP 后发布及离线完成检查。这些范围互有包含，分别报告。控制器 `LAUNCH_EXIT=0` 只表示控制器退出，实际失败状态以 `SUMMARY.all_registered_runs_passed=false` 为准。[完整原始汇总](D:/hefe/verification/fixes/20261106_perf020_o5a/cost/diagnostic_01/SUMMARY.json)

## 阻塞原因与审查漏判

冻结 `diagnostic_ledger.py` 将全部 service events 放入成功 readline 至 wire flush 的原区间。实际 10 次业务中，每次均有一条 `audit/request_trace` 在 flush 后执行，其余六条 service spans 和 capture 均位于原区间内。trace audit 在 flush 后 0.2057–0.3066ms 开始，0.5904–0.8613ms 结束，自身持续 0.3765–0.6044ms。

原 MCP 循环将 `wire.write_encoded` 包在 request trace context 中，context 在写出后退出并调用原 `record_event('request_trace')`。worker 对 current 使用浅拷贝，保留同一个 events 列表，终端记录因此完整包含随后追加的审计事件。采集到的时间戳与调用顺序符合原逻辑，冻结账本的包含前提不成立。[原 MCP context 范围](D:/hefe/human_eye_plugin/live_spatial_mcp.py:712) [原审计写入](D:/hefe/human_eye_plugin/live_service.py:629)

实施与独立启动审查均漏判了真实 trace context 在 wire flush 后退出的嵌套关系。离线假对象测试分别覆盖了写出与审计，未覆盖这条组合路径。实际 fail-stop 暴露并保留了此漏判。原完成审查失败及未运行任务保持原始状态。[独立最终复审](D:/hefe/verification/fixes/20261106_perf020_o5a/review/FINAL_REVIEW.md)

## 现有十次记录能说明的范围

下面数据来自失败后的只读派生。派生单独保留写出前区间和写出后审计，没有修改原时间戳、原冻结脚本或失败状态。完整有效诊断账本数量仍为 0。[部分时界派生](D:/hefe/verification/fixes/20261106_perf020_o5a/cost/diagnostic_01/PARTIAL_TIMING_DERIVATION.json)

| 8-E 范围 | 观察值 |
| --- | --- |
| 完整 caller RTT | 22.976–39.729ms，10 次中位 24.621ms |
| 暖 caller RTT | 9 次中位 24.614ms，九次均超过描述性 20ms 筛选线 |
| first caller RTT | 39.7285ms |
| 客户端 connect | 0.2501–0.7703ms，中位 0.32975ms |
| 客户端 recv 累计等待 | 16.1971–20.1035ms，中位 17.19895ms |
| exchange 未细分余量 | 0.0323–0.0544ms |
| QA accepted 至发送完成 | 16.1656–20.0235ms，中位 17.1446ms |
| QA code_execution | 15.5693–18.8117ms |
| 宿主几何 capture | 0.3575–0.5665ms |
| service 写出前、capture 之外 | 6.1627–18.435ms，中位 6.4301ms |

以上客户端、服务端各自在自身时钟上核算。recv 等待包含远端工作，不能与服务端执行耗时相加。E 的执行范围包括原源码装载与模板处理，内部尚未逐项计时，整个 code_execution 与 capture 的差额不能全部归为某一操作。

first 的原 service 跨度包括 identity 0.2839ms、lock_enter 4.0091ms、task_facts 6.8318ms、save 5.2259ms，另有 capture 和明确余量。一次暖 static 的 lock_enter 为 7.9111ms，该跨度同时覆盖锁、状态、runtime 与验证，内部原因尚未细分。

本批未取得 F 观察，且没有完整 64/256 对照。O4 历史约 25ms 桥接额外余量及最慢冷服务外 capture 30.8199ms 的原因仍未确定。冻结 `ANALYSIS.json` 因有效账本为 0 而输出空筛选列表，不能据此宣称没有长尾。当前材料不支持新的 E/F 因果结论、F 准入或产品优化提案。

## 观测开销

| 层 | 新增 clock calls | 新增逻辑记录 | 可见直接记录跨度合计 |
| --- | --- | --- | --- |
| service 七事件 | 210 | 70 | 与 capture 合并观察为 0.0874ms |
| 原 capture timer 补一 stamp | 10 | 0，复用原记录 | 同上一行 |
| bridge 细分及详细 exchange | 250 | 90 | 0.1117ms |
| QA 请求范围 | 310 | 130，另保留原 20 条 | 0.4160ms |
| QA STOP、control、accept loop | 228 | 86，包含 10 条 accepted-loop 引用 | 0.3660ms |

各层记录计数遵循冻结 schema 的逻辑记录定义，不代表 Python 分配对象总数。旧 exchange/capture 原有 clock 单独保留。业务观察典型新增 service/bridge 47 次、server 31 次 clock calls，其中 service 的 3 次属于写出后 trace audit。loop 独立计算，STOP 26 次、control poll 25 次、accept wait 25 次，其 idle 等待不分摊为产品工作。

10 条业务 WORKER 记录的 observer 字段结构差量为 27,410 字节，initialize 为 162 字节，10 条 server 记录为 26,437 字节。WORKER、SERVICE_READY、BLENDER_RESULT 顶层元数据差量分别为 4,652、4,805、6,701 字节。差量在会话结束后按固定 compact JSON 字段移除定义计算。RESULT/SUMMARY 重复引用的证据、脚本快照及整个证据树 IO 另属 QA 产物，此字段差量不是其总量。[收尾数据](D:/hefe/verification/fixes/20261106_perf020_o5a/cost/diagnostic_01/CLOSURE_FACTS.json)

可见 record_done 减 end 仅覆盖部分 RAM 记录工作，遗漏部分 wrapper、clock 本身、缓存与调度影响。原 RTT 保持未校正。这些观测值未从 RTT 扣除。

## 准备阶段更正

原 `live_spatial_mcp` 已在启动导入 `task_query`。此前“首业务冷模块导入”的表述过宽，已记录更正。真正首次宿主源码执行仍位于第一条实际业务请求。

原 server 的 `failed_execution` 已保留构造、采集及类计数。root 初次漏看该字段，本次准备只统一 `partial_execution` 与消费者字段并补已知上下文。独立复审还发现并修正了草稿消费者读取 `capture_rows` 而生产者使用 `capture` 的接口错误。

内存 `None` 与失败分母的离线报告处理已在实际前补齐。服务侧假对象测试 12 项共三次修订运行，传输侧最终 48 项通过，所有首轮记录均保留。以上结果证明范围限于所测组合，真实 post-flush context 路径的漏判已由本轮实际证据确认。[准备阶段复审补充](D:/hefe/verification/fixes/20261106_perf020_o5a/review/READY_TO_FREEZE_V2.md)

## 管理员待审事项

本批产品优化提案数量为 0。下一批必须先校正唯一 QA 时界合同，将原 flush 区间与随后同请求的 trace-finalization 事件分开核算，并用真实 context 嵌套的离线反例验证归属、下一次读取及跨边界未知情况。现有时戳足以显示此问题，该校正不产生产品提速结论。

本批已达到冻结失败停止条件。剩余五个会话维持未运行，由管理员审查本报告及原 O4 结论后安排后续独立批次。最终以 `PERF020_O5A_BLOCKED` 回执释放测量窗口并结束本批。
