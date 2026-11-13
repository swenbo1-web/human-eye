# 正式002全部授权线程的 usage 范围

按 `private/THREAD_WHITELIST.json` 核对六份已关闭 outer 的固定 SHA256、十八份 consumer SHA256 及其 CLI 原事件归档 SHA256。六个精确 UUID 均完成三轮，实际同线程 resume 共十二次。

六个线程的十八轮均建立相同的数值范围证明。

- session_meta 的 UUID 与白名单一致，CLI 版本为0.152.1。
- 三轮按 task_started／task_complete 边界逐次对应实际 consumer 及显式 resume 请求。
- 每轮首条数值 total 与 last 完全相同，形成零起点。续接轮的首状态也区别于上一轮终值。
- 后续每个不同数值状态均满足本次 total 等于前次 total 加本次 last。原始重复状态若出现仍保留在所选事件中，只在加法核验时识别为同一状态。
- 本轮各次 last 的逐字段和精确对应该轮 total 终值，CLI 原 turn.completed usage 全部字段又与该终值完全对应。

因此，本批实际观察到的六个线程均为各 CLI 轮次内部累计，十八轮范围确认，未知线程数为零。结论只适用于这些已授权、已关闭的实际调用，没有依据递增数值猜测 session 累计，也没有外推所有 CLI 使用场景。

`ALL_NUMERIC_PROOF.json` 私有保留筛选后的数值、任务边界、原行号及 SHA256，并绑定全部 outer、consumer、CLI 事件和精确 session 文件。`ALL_RESULT.json` 只给线程、轮次和范围确认计数。第一份 EPISODE_01 证明、白名单及冻结准备审查未覆盖或改写。

只打开白名单内六个精确 UUID 的 session 文件，没有复制推理、消息正文、rate limit、其他聊天或凭据。未调用 provider，未新增模型或其他实验。

成本继续封存，usage_aggregation 为 null，没有求分组或 episode 总量、胜负或费用。轮内加法仅用于证明计量范围。
