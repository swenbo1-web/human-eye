# 连续三轮匿名质量材料

本包固定六个 episode，每个保留三轮，共十八槽。随机 episode ID 按字典顺序排列，各 episode 内保留首次查询、未变重查、登记变化后的查询顺序。输入题面逐字保留，独立真值及实际几何按 BASE、BASE、EDIT 对应。

每轮 `answer.txt` 保存 consumer 实际确认的公共 final 原字节。`cli_output_unconfirmed.txt`、`consumer_final_unconfirmed.txt` 和 `unconfirmed_public_message_*.txt` 分别保留其他输出来源，是否确认由 `TURN.json` 明示。已开始但未完成的轮次保留错误、部分文本和业务证据，未运行槽也保留。

`tool_evidence.json` 复用 FIX1 既有业务投影，独立保留实际 owner 请求、成功或错误响应、尝试异常，以及模型可见工具事件。原生代码、stdout、未知字段、重复尝试和 JSON 字符串按原值保留。owner 响应与模型可见事件的存在分别记录，缺失交付保持未知。

`EPISODE.json` 的整体执行状态使用新 outer 完整时界。每轮的执行状态及完整 final 另外保留。旧 coordinator 的期限与关闭状态作为独立执行事实，管理员 QA 仅用于输入和执行绑定。当前场景依据应由本轮模型的实际业务证据判断。

`SCORING_CONTRACT.json` 固定完整当前列表主项、明确上下文引用展开辅助项、本轮状态依据及执行状态四个维度。沿用精确真值、数值容差、标签和显示精度规则。打包工具没有评分内容，所有十八槽交由独立审核。`score_answer.py` 是既有离线解析辅助，无法解析的自由文本需要人工审核。

分组映射、真实全局线程标识、行政路径、argv、时间和 usage 保存在私有原件。公共续接记录采用 episode 内稳定 context 代号及绑定布尔值。工具正文与原始错误消息可能透露路线，因此匿名具有局限。业务文本及错误消息保持原样。

私有绑定对全部 owner、consumer、raw archive 和 outer 原件清单建立摘要联系，并将公共每个文件与固定映射、PLAN 和正式 RUN_RESULT 绑定。公共 ZIP 仅包含本目录材料。
