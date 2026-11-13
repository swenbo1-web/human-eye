# 本批实际 usage scope 核对

本批白名单与正式 RUN_RESULT 的 SHA256 绑定一致，六条真实 consumer 记录分别属于六个 UUID，全部为首轮。记录中的 `turn_index` 均为 1，`expected_thread_id` 均为空，实际冻结的 CLI argv 均未请求 resume。

实际 resume 轮数为 0。本批无法证明续接时 `turn.completed.usage` 的逐轮或 session 累计语义，usage scope 继续为 unknown，aggregation 保持 null，token 门继续未测。

核对只使用本批白名单、正式 RUN_RESULT 与白名单精确列出的 consumer 元数据，逐条源码及记录 SHA256 保存在 `BINDING.json`。没有打开 session 日志、其他聊天或凭据，没有输出推理或消息正文，没有计算分组 token 总量、成本或胜负。成本继续封存。

冻结的准备审查文件未改动。
