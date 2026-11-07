# EVIDENCE-CONSUME-001-R1：计时归因及最终用量勘误

原 `run_01/RESULTS.md` 与 `analysis/INTERPRETATION.md` 将 `BINDINGS.dispatch_utc` 后的父流程时间称为派发等待或排队，这一归因不成立。该字段实际是 **registration（父预登记）**，早于真正的 spawn 请求。登记到 spawn 的20.305605–30.583382秒属于父流程准备/提交开销，不能算 provider 排队；spawn 到 task_started 的0.903–0.978秒也只表示可见宿主启动区间，不能进一步识别 provider 排队。

原文件和两份晚答标记全部保留。**冻结登记门仍为6/8；真实 spawn→公开 final 的8/8均小于150秒，是另一个诊断口径，不能追溯替换原门。** A05、A02不是消费者实际执行超150秒。

|答案|登记→spawn 秒|spawn→task_start 秒|spawn→final 秒|原登记门|
|---|---:|---:|---:|---|
|A04|30.583382|0.972|66.765|通过|
|A05|20.440303|0.943|145.375|未通过，原标记保留|
|A02|21.322205|0.978|138.720|未通过，原标记保留|
|A01|29.035973|0.972|37.438|通过|
|A07|28.779341|0.913|49.446|通过|
|A08|20.305605|0.903|95.197|通过|
|A03|20.632839|0.947|101.847|通过|
|A06|27.808947|0.972|75.655|通过|

[TIMING.json](TIMING.json) 与 [TIMING.csv](TIMING.csv) 独立从公开 spawn 元数据、各子任务的 task_start/final/complete 及原登记记录提取八行，完整保留六个时刻与原始行号锚点，不读取或导出受保护提示及隐藏推理正文。宿主 duration、实际 spawn→final、父记录与链占用分别保留，不互相替代。

150秒答预算没有独立硬中断 watchdog，父轮询也未在两个登记截止及时中断；owner 的 **600秒链 watchdog** 是另一机制，不能证明150秒硬限制已实现。父 close 记账点在 task_complete 后13.342089–80.239807秒，增加链占用，不能归为模型或产品延迟。四配对原 token/调用数字不变；原模型任务时间与链wall继续分栏，不用链占用夸大产品收益。

## 已结束旧实施 turn 的最终 usage

旧 turn `01a1b4e2-2a3b-7f61-9607-1b6d9e6e80ee` 的宿主最终时长为 **2,886,540 ms**。按原逐段数值 counter 口径补齐至结束，结果如下；缓存输入、推理输出均为子集，不再加总。

|成本范围|total token|
|---|---:|
|八个消费者，原值不变|629,307|
|夹具准备 Agent|2,173,595|
|适配准备 Agent|2,953,688|
|审计准备 Agent|12,067,113|
|原实施者，现已完整|21,775,848|
|上述已结束实施批次合计|39,599,551|

原实施者最终为输入21,710,314、输出65,534；缓存输入子集21,631,744，推理输出子集32,095。原截至审计的实施者19,647,049及旧部分合计37,470,752仍保留；此次补齐2,128,799 token。完整实施批次合计39,599,551 **不是全项目最终总成本**，不含当前R1及协调方复核成本，也不等于独特输入或美元费用。

[FINAL_USAGE.json](FINAL_USAGE.json) 将消费者、三个准备 Agent、旧实施者最终、当前R1部分和协调方未完整成本分栏，附首尾 counter 与逐段一致性检查。当前R1仍未结束，协调方成本未测；provider调用数与费用继续未测。

未来 CLI 说明只建议明确一条：`query-literal` 接受 query 字段，文本 CLI 在外层自动设置 `include_image=false`，不能把它放进 query。本R1不改旧提示、CLI、校验或产品，也不重试消费者。

根独立复核见 [REVIEW.md](D:/hefe/verification/fixes/20261107_evidence_consume/review/REVIEW.md) 和 [TIMING_COST_RECOUNT.json](D:/hefe/verification/fixes/20261107_evidence_consume/review/TIMING_COST_RECOUNT.json)。本次只新增 `review_r1`，[UNCHANGED.json](UNCHANGED.json) 核原619证据及原索引未变、checkout/安装131源仍为 `fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509`。无新子Agent、消费者、产品运行、Blender、性能或API试验。
