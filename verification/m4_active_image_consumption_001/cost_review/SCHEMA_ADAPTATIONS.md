# 离线解析适配记录

首轮复算在 `r/N actual CLI/owner business binding` 处停止。CLI 完成事件将 MCP 结果投影为 content 与 structured_content，原 MCP 结果为 content 与 isError。

随后按真实字段分别校验。content 保持逐项逐字节一致，structured_content 必须为空，原 MCP 的 isError 必须为 false，CLI 的 status 必须 completed 且 error 为空。原始 JSON/TX/RX 和候选源码保持原字节。该解析适配没有新增模型、进程试验或图片。

第二轮在本地 fake CLI 的图片完成事件字节检查处停止。fake_cli.py 使用 Windows Python print，原始 stdout 采用 CRLF，保存的 JSONL 统一为 LF。复算器随后按发出端格式重建本地 CRLF 与真实 CLI 的 LF，图片完成事件按唯一 item ID 计一次。原始记录保持不变。

第三轮在本地 fake CLI 命令检查处停止。本地 argv 明确用 Python -I -B fake_cli.py 替换真实 CLI 可执行文件，其余参数沿用冻结请求。复算器分别检查真实命令完全一致与本地替换的准确性，继续保留合成流程和真实会话的区分。
