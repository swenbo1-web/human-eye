# 成本复算解析记录

首次离线执行在 N1 的 raw stdout 与 JSONL 全字典比较处停止。原始字节数和哈希一致，JSONL 对 reasoning 类型事件保存脱敏标记、原始行哈希及字节数。

复算器随后按既有脱敏结构核验对应原始行的哈希和长度，其余事件继续逐项相等比较。复算结果继续仅输出成本、状态及公开错误事件。原始证据和正式候选源码保持原字节，没有新增模型或渲染。

第二次执行在错误封装数量处停止。原始 CLI 的失败工具仍保留 content，status 为 failed、error 为空。复算器原先只把 result 为空的情况计为失败封装。随后增加对原 owner isError 和实际 CLI status 的独立检查，同时保持 content 逐项一致校验。冻结的 N1/N3 失败结论继续保留。

最终文字复查修正了将两例统称 SyntaxError 的表述。原工具 error 字段分别为 N1 的 SyntaxError 与 N3 的 ValueError。生成器现从各自原始工具 JSON 提取 type/message，避免按概括性描述填入错误类型，正式结果保持不变。
