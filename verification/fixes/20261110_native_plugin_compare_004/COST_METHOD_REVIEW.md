# COMPLEX-004 成本口径有限复核

结论：固定 V2 的成本字段可以用于本轮 18 格对照；未发现把缓存 token、嵌套时间或内部 RPC 重复加入模型消费的计算。需要保持“每格完整生命周期”和“项目总成本”的区别；本轮没有完整项目费用数据。此次只读代码与定向原件核查，没有执行作者分析脚本、模型、Blender 或产品。

固定输入：

- `private/ANALYSIS_ACTUAL_SCHEMA_REVIEW_V2.json`：SHA256 `3ffdd1943a4bae1e97214a636addfb7e1f77e9e8e09591ba2762e24e0e7f85a4`，与被审 `ANALYSIS_PENDING_QUALITY.json` 同字节。
- `private/analyze_ACTUAL_SCHEMA_REVIEW_V2.py`：SHA256 `674c0b1b7bbbcd5fdda5d994bdf52848cf5f005a6a4425fcac7e62b62fde09d0`，与被审 `analyze.py` 同字节。
- 路径基底：`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_004`。

## 口径核查

| 项目 | 核查结论与代码位置 |
| --- | --- |
| prompt→final | 从提示写入 stdin 并关闭后，到最后一个公开 agent_message 完成事件；不是服务商接收时刻，也不是纯模型推理时间。`consumer_transport.py:118–119,167–169,198–199`；分析核对原时间差，`analyze.py:671–673`。 |
| 每格生命周期 | `total_task_wall_ns` 从该格 prepare 之前至 consume 退出清理、owner finish/终态核验/后端关闭之后，包含该格实际设置与清理，结束于最终 CONSUMER 保存之前。`driver.py:131–139`。CLI wall、owner lifetime、QA RPC、finish 是嵌套或重叠区间，不能相加到 whole_cell；`analyze.py:797–812` 已注明，且将误名的 owner_close_ns 清空为 unknown。 |
| 工具时间 | `tool_time_ns` 是所有实际 attempt 的 owner elapsed 之和，包括错误，`analyze.py:385–406`。它包含分派、产品/原生调用及必要 I/O，不等于纯几何计算。它已处于 prompt→final 和 whole_cell 内，不能再加；prompt→final 减此值也不能直接叫纯推理时间。定向 cell02 的三个 owner attempt 区间没有相互重叠。 |
| 实际 usage | 取公开 turn.completed 原始计数，并与 CONSUMER 对照；18 格各一次公开完成，不推断供应商内部请求次数。`analyze.py:227–242`。cached_input、cache_write、reasoning_output 分开披露，不能再加到 input/output 总量；未返回 total_tokens 时保持缺失。没有把字节折成 token 或 Pro 用量折成 API 美元。 |
| 公共与内部字节 | 公共实际 TX/RX 按 tools/list、tools/call、控制/握手分别统计；工具 text UTF-8、完整帧、参数重新编码字节又分别标记。内部 product pipe 包含管理请求与转发查询，单列而不并入模型输入；native-worker TCP 未测。`analyze.py:258–317,813–824,920`。 |
| 分母与失败 | 固定 18 格，每题/路线 3 格；所有实际 attempt 都入账，共 62 次、10 次错误（9 HE、1 原生）。原生回退也在同格成本中，不能删去后只报成功插件调用。`analyze.py:376–407,833–837,867–896` 保留失败/缺失；`merge_review.py:270–285,302–309` 将全样本和正确子集分开，正确子集不能替代原分母。 |
| 未测项目 | provider_request_count、fees、resolved_effort 为 null；requested effort 只是请求配置。模型内部调用次数、准确美元费用、规划/实施/复核对话总 token 与费用均未测。18 个消费者会话、62 个工具 attempt、公开 JSON-RPC 请求是不同数量，不能互换。 |

## 定向原件抽查

抽查 `cells/02/CONSUMER.json`、`events.jsonl` 和其附件桥的全部 6 份 TX/RX 帧：

- 原公开 usage 为 input 29,209、cached input 19,712、output 1,006、reasoning output 0，与作者记录一致；没有重加缓存。
- prompt→final 36.4909689 秒，CLI 至清理 42.0100225 秒，whole_cell 44.1255599 秒；前两项分别由原事件/原时间差核对一致。
- 公共控制 TX/RX 为 273/155 字节，目录为 86/11,018，工具为 4,089/9,585；公共总 TX/RX 为 4,448/20,758，和作者字段完全一致。
- 其中失败 HE 请求的 RX 为 838 字节，仍计入工具总量；成功 HE 为 7,347，原生为 1,400。
- 同格内部 product pipe TX/RX 为 2,923/35,734，包含管理目录/身份数据和两个转发请求；它不是额外模型输入。这项检查核对作者分层字段，未重复另一复核人的完整后端回执审核。

根对 18 份原 CONSUMER 的独立重算另存 `ROOT_RECOMPUTED_RESULTS.json`；本报告不将该工作冒称本人的全量重算。严格正常薄客户端 EXIT 仍缺失，已记录请求结果/后端清理与正常协议退出分开披露，不因该限制抹除实际耗时或错误记录。

## 一次性准备及总成本

| 项目 | 现有记录 | 本轮可报告范围 |
| --- | --- | --- |
| 六格无模型真实入口预检 | `PREFLIGHT.json` 的 wall_ns=40,195,449,200、model_calls=0 | 一次性 40.1954492 秒，单列；不摊进 18 格模型收益，不重复加进每格 setup。 |
| wrapper 检查、CLI 预检、安装来源/普通 schema 比较 | `WRAPPER_TESTS.json`、`CLI_PREFLIGHT.json`、`SOURCE_PREFLIGHT.json`；根 `INSTALL_COMPARABILITY.json` | 有动作/结果记录；所检顶层记录无完整统一耗时或模型 token/费用，保持未测。 |
| 首次预检设置失败与恢复 | `PREFLIGHT_SETUP_FAILURE_01.json`、`PREPARE_RECOVERY.json` | 失败历史保留，前者记录 model_calls=0；耗时无完整计量，不当作零成本。 |
| 构建/安装、固定方案、盲评、独立审计、协调 | 相应工件/会话存在；当前成本表未覆盖完整预算 | 不宣称已计入 whole_cell，合计时间、token 和费用未测。 |

每格启动开销已包含在 whole_cell 中，一次性安装与预检则不在该区间；两者不能相互替代。可给“已测执行成本 + 单列预检 + 其余未测”，不能称端到端项目净费用已经下降。

## 收益归因约束

装配题三组均有正确答案，可以在原始 n=3 的限定下比较实际答题和每格生命周期；工具wall本身不能证明产品引擎快多少。D48 全场题的封存质量结果为 N/C 各 3/3、O 0/3，但没有任何成功的 HE 全场查询，答案计算均由原生路线完成。C/O 时间或正确率差异不能归因于四行整数快路径；O 的更低全样本耗时包含错误答案，不构成同质量收益。最多描述本次自然工具选择、失败纠正与原生计算组合的观测表现。

未对 n=3 声称 p95、稳定普适收益或显著性。没有发现需要重跑消费者的成本计算错误；交付时保留上述范围与未测项即可。

Reviewed UTC: 2026-11-10T11:29:05.138041+00:00
