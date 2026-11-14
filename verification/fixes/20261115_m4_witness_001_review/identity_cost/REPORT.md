# WITNESS001 独立身份、封存及成本复核

本项结论：固定身份和原件一致，已有成本数值可由原始记录重算。没有发现混版、补跑或实际内容丢失。原自动 QUALITY 的 KeyError 继续按失败保留，不能改写为自动通过；答案质量及直接采用是否成立由另一个语义复核负责。

本轮仅离线读取 JSON、原始 CLI/TCP、Git blob 和文件字节；未导入产品、评分器或启动器。新产品、模型、Blender、raster 调用均为 **0**。只写本目录。

## 固定身份与封存

- 作者树 HEAD `8baad59ac6da01f14e1eb87c3e1f4f0687eb2b7d`，相对 `a9dd9490d1817630e090975362591ce232d881ae` 的 202 个变更路径都在 `verification/m4_complete_witness_consumption_001/`，逐项与固定 Git blob 一致；当时作者树干净。
- CONTENT_MANIFEST 列举 201 文件，加其自身共 202；文件长度和 SHA256 全一致。
- FROZEN 2216 项、QUALITY_SEAL 191 项逐项实际 hash 一致。
- 136 个运行原件和归档副本逐字节一致，总计 **1,572,334 B**；实际 runtime 文件集合与归档清单一致。
- 产品 141 个源文件：作者树、`D:/he_view_reuse_001/product` 与固定产品提交 `d12c7ab248452ff253452007d0635f2d662f0191` 字节一致。离线按实际 identity 源码公式重算得到 `d8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02`。
- 原 `admin/QUALITY.json` SHA256 仍为 `272f925f1f46b4140b7483fbeceb1ff0a2b58285d3b5c9cab6c417cbb6cb3a87`。原 `final_quality_passed=false`、`direct_product_adoption=null`、分母 1 均保留。`execution_state` 实际位于 RUN_RESULT 顶层，原 scorer 误读 records[0]。这属于原评分程序失败，不能据此推导答案错或直接采用通过。

## 原运行和构造次数

- Q1：唯一 qualification，actor PID 15324，1 次业务调用、0 模型、2 raster，无外层重试。
- F1：唯一正式 route / CLI，actor 29536、CLI 6356、thin runtime 29156，原完整 stdout 有一个 turn.completed；3 个业务工具，2 个实际图像块。
- 全部 raster INTENT 共 4，global_attempt 为 1–4，preparation 2、formal 2，均 product 来源。正式 TOP 重复读取命中已有帧，新增 raster 为 0。
- qualification / actor / CLI 清理记录 exit 0、已回收并关闭 handle、无强杀。thin 原持有 handle 确认已退出且关闭，exit 1；其 EXIT 回执缺失，bridge receipt_status=unknown。进程已退出和回执未知分别保留，不改成全部回执正常。

## 时间与成本原口径

| 项目 | 独立重算 | 边界 |
|---|---:|---|
| qualification | 2.7234349 s | 原 Q1 时钟相减，结果文件发布前结束 |
| formal route | 62.8451825 s | 输入检查/actor 启动前至原 CLI/actor handle、thin handle、原 ZIP、输入回读及 RESULT 写入关闭回读 |
| launch | 64.5498345 s | 来源/qualification 检查前至唯一 route、清理、后检和结果写入关闭；不含解释器 import 和 timing 自身发布 |
| wrapper route call | 62.8456317 s | launcher 调用 route 的包围时钟；与 route 内时钟边界不同 |
| 3 个工具 handler 合计 | 0.2148098 s | receipt started/closed 相减；不包含后续响应序列化、发布和 TCP 往返 |

原 450 秒 deadline 未改变。原 `slot_timing` 字段和 SLOT_TIMING 文件均不存在，本轮没有补造。没有把上述不同范围的时间相加成新的“全流程时间”，也没有据其推出纯模型推理时长。

原始 CLI usage：input **42,627**，其中 cached input **28,160**；output **1,331**，reasoning output **20**；input+output **43,958**。cached/reasoning 是原字段，不能重复加到总和。现金费用、图片 token 拆分、provider 实际请求次数均未测，不用估算填充。

5 个原 TCP 请求/回复逐项重算：请求 **5,212 B**，外层回复 **30,828 B**，MCP JSON **30,483 B**。MCP 长度按原编码方式含结尾 LF。三次业务工具实际 content 中共 2 图：PNG **5,127 B**、base64 **6,840 字符**，文本 UTF-8 **18,075 B**。这些是各层不同口径，不能与 token 混为一项。

## 本轮复核自身失败与收口分母

原检查产物全部保留，未把失败记录擦成全绿：

1. `RESULT_R1.json` / `RESULT.json`：大矩阵 **3149** 条，**3148 通过、1 失败**。唯一失败 `raw_event:9` 是审计脚本对 raw stdout 使用 `splitlines()` 去掉 LF，而既有 producer 明确定义为 `readline` 原字节 hash/count。producer `consumer.py:287,340–341` 已核对。
2. `COST_ADDENDUM_RESULT.json`：窄核 **35** 条，**32 通过、3 失败**。其中原 14 个事件核查全部通过；reasoning 行原字节含 LF 为 106 B、SHA256 `02a282fd1ce6558f7342fa501a5fc5aff355e87e991f14453e07796ac5650e2e`，与公开脱敏 hash/count 完全一致。未输出 reasoning 正文，也未任意 normalize 内容。这个证据解除第 1 项的审计脚本误报。
3. 窄核的 3 个失败来自“整个 MCP envelope 等于 CLI envelope”的额外审计假设。逐项原始比较已完成，结果见 `COST_ENVELOPE_REVIEW.json` 和 `CONTENT_COMPARISON.json`：**3/3** 的 `content` 完全相等，wire 键为 content/isError(false)，CLI 键为 content/structured_content(null)。`CONTENT_COMPARISON.json` 记录每条输入路径/原始 SHA256、每个 content 元素的精确值比较与指纹；完整 envelope 相等为 **0/3**。差异被逐项明确记录，未宣称完整 envelope 相等。

组合记录分母为 **3149 + 35 + 3 = 3187 条观察/检查**，包含重叠核查，不能称为 3187 个独立场景或测试能力。原 4 个失败判断仍保留；其来源均为本轮审计假设，不是原件差异。最终身份/封存/成本结论使用实际适用条件和补充原字节证据，未解决的实际差异为 0。没有重复跑 2216 项身份矩阵，也没有重跑产品或模型。

## 范围限制

- 本项不判定答案语义质量、直接采用是否成功或相对原生的性能收益。
- 当前仅一个正式模型消费样本，不能据此推导稳定均值、p95 或泛化收益。
- 原评分程序失败、缺失 slot_timing、thin 回执 unknown 和未暴露费用指标均保持原状态。
- 读取输入及 SHA256 留在 INPUTS_R1.json / INPUTS.json 和 COST_ADDENDUM_INPUTS.json；R1 脚本、R1 结果和窄核结果全部可追溯。`FINAL_RESULT.json` / `FINAL_RESULT_INITIAL.json` 保留窄核首版，最终解释另列 `FINAL_RESULT_R2.json`；不把首版的失败字段改成通过。
