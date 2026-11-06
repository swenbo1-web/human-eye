# 真实宿主试跑：发现通过，审批派发失败

2026-11-06，主审027。**ACCEPT_HOST_DISCOVERY_ONLY_REWORK_APPROVAL_PATH**。实际启动了一个自有GUI Blender和两个真实Codex上下文；两项任务均未完成。接收真实MCP协商、工具发现和模型提出正确调用参数的证据，不接收动作执行、结果/图像消费、正常EOF或任务收益。025的独立原生5/5功能资格保持，N/V离线准备不重开优化。

## 独立核对后的实际结果

执行索引SHA256 `8797d35775a781c1a79dabe0a069a82380cfc1623f27b7827f5b8439abacea1a`。主干逐项核对39引用原件、33冻结源ZIP和当前文件，均与计划`22445e963fb685d73611b5670a2504d132ec00ec6cb8fdc9ed5f201158ad879b`一致。没有追加模型、Blender或原生批次。

| 阶段 | 两项实际记录 |
| --- | --- |
| 宿主 | Codex 0.167.0-alpha.3.2，真实协商MCP 2025-06-18 |
| 工具发现 | 得到eye_run、eye_inspect，模型各尝试一次参数正确的eye_run；带图案含SECTION |
| 派发 | 均被宿主拒绝：`MCP tool call requires approval, but approval policy is never` |
| 真实wire | 各409B入、1179B出，只有initialize/initialized/tools/list，零tools/call |
| 场景与图像 | 两案before/after RNA各自逐字节相同；零动作、零渲染、零PNG和对应camera |
| 退出与判定 | CLI和Blender exit0；两个native及summary FAIL、外层runner exit1。没有用进程退出码替代任务验收 |
| 模型回答 | 明确表示未执行，实测与图像未知；未把目标值当实测或编造视觉细节 |

这不是先前“进程创建前”的外层自动审批拒绝。本次外层正常放行并真实运行，内层CLI的有效审批策略在MCP发送前拒绝了写入调用，没有产生可由本收集器回答的批准过程。根侧选定的非交互宿主路线缺少实际审批应答通道，应修宿主接入；不能归因为距离算法、渲染退化或模型选错工具，也不能把eye_run改标只读绕过。

两条连接均记录WinError 10054、peer_eof=0，tap最终凭据缺失，仅留下空tap.json.tmp。entry.close、listener关闭和timer注销已完成，证明reset后的资源清理；不能称正常FIN/EOF及tap终态通过。已有原始帧是完整换行的真实前缀，不因终态缺失就丢弃协商证据；也不反向补造relay退出码。初次GHOST可见、随后仅自有窗口隐藏的限定继续保留。

## 输入成本：保留全量真实用量，不用wire字节代替

| 失败回合 | input_tokens | cached_input_tokens | output_tokens | CLI wall |
| --- | ---: | ---: | ---: | ---: |
| 数值 | 39,371 | 12,544 | 184 | 18.845s |
| 带图 | 39,628 | 25,856 | 270 | 20.327s |

这些是各`turn.completed`原字段，分别总和78,999/38,400/454；cache write与reported reasoning均0。cached不能再次加到input，reported reasoning=0不证明内部没有推理。缺逐请求、消息来源、可见文字和图片token分项；启动请求gpt-6.1-sol/ultra也不是独立服务端快照证明。

本次没有任何HE任务结果或图像进入模型，因此不能归因为PNG、完整AO或网格重复传输。另一方面，1179B握手/目录不是整个模型上下文，不能换算token或宣布极低模型成本。约4万input的具体组成目前无法从公开日志量化；不靠猜测删管理指令、改模型、只报局部字节或扣掉缓存来制造收益。上述时间是失败会话耗时，不能作为成功任务、引擎时延或正式I/N样本。

## 下一步仅准备有审批应答的宿主

OpenAI官方app-server接口支持双向请求/应答；本机离线生成schema也确认thread/start有on-request、user reviewer和read-only字段，且定义了`item/tool/requestUserInput`。选择这条候选路线，先由原实施聊天在新`artifacts/llm_entry/host_recovery_001/`准备最小客户端、runner和假流检查。仍未证明普通local MCP在本机实际会走该审批消息。[官方接口](https://learn.chatgpt.com/docs/app-server#approvals) [配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)

客户端使用冻结的`codex app-server --stdio --strict-config`，线程显式要求原模型/ultra、on-request、approvalsReviewer=user、read-only，并把eye_run设为prompt。保留真实MCP调用意图，关联requestId、thread/turn/item、questionId和实际选项，将待批原文与server/tool/arguments交给主干；不自动选首项、不猜Accept标签、不选整会话信任，不以超时为同意。只有真实请求与具体用户单次授权匹配才应答相同requestId。

app-server没有exec的ignore-user-config。新准备必须列出继承配置、进程级隔离覆盖和最终暴露的工具范围，保存实际instructionSources及返回的审批/sandbox。保留管理要求，不落盘修改默认MCP、HOME/CODEX_HOME或凭证；不能假设空map能清除继承配置。模型turn前无法确认范围就报告具体阻塞，不先发送。产品relay、工具annotations和已验收内核均保持。

当前只做离线假事件/请求关联、拒绝与取消、单次应答和日志/关闭检查，不启动新app-server会话、模型或Blender。完整代码和冻结清单交付、主干复审后，才为最多一个新occluded上下文提出具体授权：原0.00075m、8e-9m、SECTION一目标同时检查实测与图像。原两次额度已用完，不因失败复用额度。未来如实际获准，单独记录审批等待、模型和工具时间，正常关闭stdio并给tap落盘机会；不无限补试。

本次是接入修复，未改变复杂任务完整均值减半、质量不退化、文字token等正式门。接入通过后还必须做原定合理N对照和完整成本验收，不能以本地功能或小回包取代模型任务收益。

两份独立报告、离线核算、CLI帮助/本机schema证据及实际失败原件保存在`llm_host_pilot_failure_evidence.zip`；机器决定见`radical_acceptance_llm_host_pilot_failure.json`。旧025/026档案、外层拒绝、两次离线准备问题和本次真实失败全部保留。实施完成离线准备后主动唤醒主干，不轮询等待聊天。
