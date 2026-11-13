# 首个授权线程的实际 usage 范围

核对范围限于 `USAGE_WHITELIST_EPISODE_01.json` 授权的一个已关闭 UUID、三份固定 consumer 记录及同 UUID 的 session 文件。固定 CLI 为0.152.1，实际同线程 resume 为两次。

三轮均出现独立 task_started／task_complete 边界。每轮首条 token_count 的 total_token_usage 与 last_token_usage 完全相同，形成零起点。该轮后续每次 total 均逐字段等于前一个 total 加本次 last，终值等于该轮各次 last 的和。CLI 原 turn.completed usage 的全部字段又逐值匹配各自边界内的 total 终值。第二、第三轮均重新从零起点计数。

这组证据支持这三次 CLI 调用按各自轮次累计 usage。判定依据包含边界、零起点、完整字段对应和加法恒等式，没有从数值递增猜测累计范围。结论仅限这个已授权线程，其他线程留待各自实际证据核验。

原数值、所选行号和 SHA256、session 文件 SHA256、consumer 及 CLI 原事件绑定均保存在 `EPISODE_01_NUMERIC_PROOF.json`。没有复制推理、消息正文、rate limit 或其他聊天，没有读取凭据或调用 provider。

成本继续封存，usage_aggregation 保持 null。本核对没有求分组总量、完整 episode 总量或胜负，也没有费用推算。原准备审查文件未改动。
