# 接口兼容修复独立审查

本轮只审 `M4-SURFACE-SCAN-CONTINUOUS-INTERFACE-FIX-001` 的窄兼容函数、新 runtime 接线、相关错误政策与下一正式批停止建议。计划 SHA256 为 `ece9040ed2553687d54ba57b3d4d6acaeaf30610ec526a9353adf95d66a51ae5`，质量 seal 为 `7f90243826c1a113d0365282517899902cc9aa2f1b163b67c43d6c644d2a51c6`。

## 兼容与实际接线

`compatibility.py` 的成功判据要求 owner 无 RPC error，result 只有 content 与明确的 `isError=false`，CLI 为 completed 且 error 键显式为 null。它接受同表示成功，以及已有真实记录中的 content 加 `structured_content=null`。正文列表及成员按原值和顺序比较，嵌套 JSON 文本保持字符串。其他 result 字段、非空结构数据、缺正文、数值 0 或空字符串冒充 false 均被拒绝。

AST 对照证明新 `archive_turn` 只在旧整表示比较不等时增加这条成功判据，其余请求名称、参数、次数、顺序、错误记录和归档代码保持同一 AST。真实 consume 函数的 `archive_turn` 全局指向新函数，原 coordinator 的 transport 指向新 transport。进程循环与 summary 函数复用原实现。

## 错误政策边界

源码审查发现，若用成功判据完全取代旧匹配，原同表示 tool error 会新增绑定失败。这会改变既有后续自纠行为。作者已采纳最小修正，保留旧整表示相等分支，仅对旧比较不等的记录调用窄成功判据。

三份真实历史错误为 owner `isError=true`、CLI failed 且 error=null，跨表示原匹配仍失败，新成功判据也拒绝。对应的合成同表示错误控制继续通过旧回执绑定，同时保留 owner 错误位及 CLI failed。回执绑定通过不能作为工具成功结论。原 summary 不会仅凭 MCP tool 的 failed 状态强制判整轮失败，本轮没有改动该行为。

旧 same-representation 分支的既有宽度继续保留。本轮没有将旧 malformed exact 输入的一般验证计为已修，也没有加入新的错误、自纠或重试政策。

独立检查及逐文件 SHA256 见 `CHECK.json`。五十二项检查覆盖实际成功、三份真实错误、同表示成功与错误控制、结构/文本/类型变体及实际函数全局接线。脚本只执行文件读取、AST 和纯函数，不启动子进程。作者的真实本地 consumer 进程回放另有 integration 记录，实际模型 resume 仍未测。

## 下一正式批的最小 stop_reason 建议

`stop_recommendation.py` 只给出纯条件，当前正式 driver 没有导入它。供后续合同冻结的建议限于以下组合。

- 现有绑定原因明确为 CLI_result_differs_from_owner 或 CLI_request_differs_from_owner。
- owner 无 RPC error，结果包含 list 正文及明确 false 错误位。
- CLI 有 list 正文，明确 completed，error 键显式为 null。

满足后可使用既有 stop_reason 结束当前批，完成当前 owned cleanup，保留真实动作、final、错误和成本，将尚未开始的固定槽置为 not_run。普通答案错误和三份正常 tool error 均不满足此条件。只看 business_original_binding 阶段不足以判共享故障。

离线反例逐项列于 `STOP_CASES.json`。该建议未增加调度层、自动修复或替补，也未追溯改动旧001策略。

## 失败成本与限制

`accounting/LEDGER.json` 和 `accounting/REPORT.md` 已完成六个首轮的原 outer、turn、prompt-to-final、十四次工具尝试与原始 usage 账本。144 个旧交付清单成员加 manifest 本身共 145 文件保持绑定，关键短目录记录逐项与 outer ZIP 字节一致。

共享准备、离线检查、freeze/commit、质量打包、独立复核、完整端到端耗时、费用和不可见服务开销保持 unknown。十二个未运行轮次不估算。没有实际 resume，usage scope 为 unknown，aggregation 为 null。账本没有给连续收益、分组胜负或费用推算。

本子任务新增内容只在新批 accounting 与 review 目录，旧源码和失败原件未改动。没有新增 provider、模型、产品、Blender、API 或 Git 操作。
