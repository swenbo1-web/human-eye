# 双路真实图片消费 001

## 本轮判定

原生读取 N 与主动观察实验出口 P 的三层图片资格均通过。服务端各构造两张原始 PNG，实际 Codex CLI 的 completed MCP 工具事件各保留两个 image content，最终回答均正确区分两幅图的特征。两路实际工具调用中没有 Python 像素计算。

真实分母为两个 fresh CLI 会话、各一个用户轮次。N 调用两次 read_image，P 实际调用一次 human_eye_image_observe。共三次工具调用、四个实际 CLI image content，原 PNG 载荷共 13,398 B。两路执行完成，失败及未运行为 0，均在各自原绝对 450 秒期限内完成。准备提交为 `1088b491a5051a2e2135670c79e67fb228a12575`，管理员终审待完成。

生命周期证据分开保存。CLI 与 actor 的原始持有句柄回收均已确认。两路真实 stdio client 缺少 EXIT.json，正常 EOF 仍为 unknown。事后只读查询两个已登记 PID 均不存在，结果在 EXIT_OBSERVATION.json，仅表示查询时无残留。

## 输入与接口

两路收到同样的 view-a、view-b，均为 512×512、image/png 原字节，顺序一致。view-a 为 1909 B、view-b 为 4790 B。公有工具文本仅给 opaque 引用、尺寸和媒体类型；源视角名称、原始路径、owner/depth/ROI、期待答案和评分器均未进入模型可见上下文。

共同 image_content() 函数负责 PNG 校验、尺寸、摘要和原字节 base64。N 的普通 read_image 和 P 的实验 observe 入口均调用该函数。通用 execute_python 保留 Python 执行、读取和自行计算语义，本地协议检查实际执行 print(6*7) 并返回 42。本次真实会话选择了图片入口。

该出口回放已封存图片，当前传递的是实验 helper 中的 512 原 PNG。它的资格涵盖本地图片传输与当前模型回答。原图片生成成本继续保留在 002/003 的历史账本中，本批新光栅、Blender 和付费 API 调用均为 0。

最小调用如下。

```json
{"name":"read_image","arguments":{"ref":"view-a"}}
{"name":"read_image","arguments":{"ref":"view-b"}}
{"name":"human_eye_image_observe","arguments":{"refs":["view-a","view-b"]}}
```

前两个展示 N 的普通读取，最后一个展示 P 的实验出口。完整纯函数和持有服务调用示例在 PUBLIC_INTERFACE.md，已与源程序一并冻结。

## 三层证据

| 层次 | N | P |
| --- | --- | --- |
| 服务端构造 | 2 个标准 image 块，原 PNG 6699 B | 2 个标准 image 块，原 PNG 6699 B |
| 实际 CLI 工具结果 | read_image 两次，各一个 image | observe 一次，包含两个 image |
| 原始字节与引用顺序 | 两图摘要匹配，view-a 后 view-b | 两图摘要匹配，view-a 后 view-b |
| 最终回答 | view-b 大面积灰色几何，view-a 深色背景仅极小亮点 | 同样正确区分并描述实际差异 |
| Python 像素计算 | 0 次 | 0 次 |

N 的公开回答为下段。

> view-b 有清晰的大面积几何轮廓：深色背景上分布着许多浅灰色菱形，组成横跨画面中部的几何排列。view-a 则几乎是纯深色空白背景，仅中央附近有极微小的亮点，没有明显的大块轮廓。

P 的公开回答为下段。

> view-b 有清晰的大面积几何轮廓：深色背景上分布着许多浅灰色菱形，形成明显的几何排列。view-a 则几乎是空白的深色背景，中央附近仅有极微小的亮点。

原始构造回执、TCP 请求响应、stdio TX/RX、实际 CLI 事件及公开回答全部保留。派生视觉判定依据这些已观测层。原始 CONSUMER 的 provider_delivery_confirmed 与 model_view_confirmed 字段仍为 null，服务端内部请求体和编码后模型输入未公开。

## 模型与生命周期限制

实际使用已冻结 CLI 0.152.1，沿用当前 ChatGPT 登录，命令请求 gpt-6.1-sol、medium、default 服务配置。两条线程 UUID 不同，没有 resume。没有读取或导出 auth token 正文。

两路均有相同的两条 CLI 警告，原 item.type=error 事件保留。

- skip_host_skill_discovery 为开发中功能。
- CLI 未找到 gpt-6.1-sol 的模型元数据，使用 fallback metadata。

两路随后正常 turn.completed、exit0 并给出实际图片回答。服务端最终 resolved model、resolved effort、provider 内部请求次数、图像 token 和现金费用未直接观测。模型元数据警告的影响未量化。

两路 stdio STARTED 回执分别记录 PID24020、23948，EXIT 回执缺失；原 bridge_cleanup.confirmed 保持 null。CLI 与 actor 的句柄确认和外层沿用原规则的完成状态分别保存。新资格并未把 stdio 的正常退出方式改记为已证。

## 实际成本

| 项目 | N | P |
| --- | ---: | ---: |
| fresh CLI 会话／用户轮次 | 1／1 | 1／1 |
| 工具调用 | 2 | 1 |
| 实际 CLI image 块 | 2 | 2 |
| 原 PNG 字节 | 6699 | 6699 |
| base64 字符数 | 8936 | 8936 |
| image block JSON 字节 | 9034 | 9034 |
| 图像标签文本 UTF-8 字节 | 54 | 54 |
| 服务端发送 MCP JSON 字节 | 10412 | 10858 |
| 外层 TCP JSON 字节 | 10688 | 11065 |
| 收到的 TCP 请求字节 | 2914 | 1770 |
| 包含启动、关闭、归档和结果回读的完整时间 | 27.9140274 s | 15.9587049 s |
| 提交题面至最终回答 | 24.6625095 s | 12.0036746 s |
| CLI 报告 input_tokens | 16161 | 10907 |
| 其中 cached_input_tokens | 10112 | 4992 |
| CLI 报告 output_tokens | 120 | 120 |
| CLI 报告 reasoning_output_tokens | 0 | 0 |

N 两图读取／校验解码／base64 编码的记录窗口之和分别为 0.1561／1.8522／0.1366 ms。
P 两图读取／校验解码／base64 编码的记录窗口之和分别为 0.1415／1.7505／0.0751 ms。

usage 按两个 fresh 单轮 CLI 的实际 turn.completed 原件分别记录。未知的图像 token、内部模型轮数和费用保持未测。两个单次资格及工具接线的差异仅作事实列账，当前未建立插件任务收益的配对结论。

真实阶段含协议元数据的 stdio TX/RX 分别为 3731／21270 B，外层 TCP TX/RX 为 4684／21753 B，分别记录各层。带图片的唯一 CLI completed 事件字节为 N 9594 B、P 9393 B；P 两个 image 同属一个事件，只计一次。两个完整路线窗口合计 43.8727323 s，首 start 至末 close 为 43.8732994 s。

准备阶段纯 helper 另构造两块；本地协议两 synthetic CLI 另构造并接收四块，provider 会话为 0。真实阶段四块单列，本批总构造十块、server 实际发送八块，准备与真实模型计数分别保存。所有构造与传输字节由 source receipt/METRICS 追溯。本地模拟采用真实 stdio/TCP owner，并在实际 Codex CLI 之前完成了 13 项原件回读检查；真实图像层由本次两个实际会话单独验收。

## 交付与下一步边界

源码与配置入口为 image_content.py、actor.py、consumer.py、driver.py、PLAN.json 和 PUBLIC_INTERFACE.md。inputs 保存 opaque 原图与共同题面。local/a01 保存准备协议原件，r/N 与 r/P 保存真实模型请求响应、实际 image 事件、原始 ZIP、usage、最终回答及 FINAL_TIMING。

作者侧对真实三层的 53 项回读检查通过，结果在 review/FINAL_REVIEW.json。生命周期 unknown 和两类警告已分列。成本回读另在 cost_review，1016 项检查通过，三个离线解析适配记录在 SCHEMA_ADAPTATIONS.md。原始模型记录、源文件和准入条件保留。管理员终审状态独立保留。

后续正式任务可给原生和插件共同完整几何、同样的完整相机集合与共享图片出口，两路均自主选择视角、按需读图、使用普通计算及保留会话状态。在固定任务与预算下先核质量，再核完整时间和实际 usage。当前这轮完成的是双路本地 PNG 回放消费资格。

本地配置参考采用官方 MCP stdio 文档，实际能力依据本批冻结版本的事件原件。[OpenAI 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

CLI JSONL 与 usage 的采集参考官方非交互说明，实际字段保留本批原值。[OpenAI 官方非交互文档](https://learn.chatgpt.com/docs/non-interactive-mode)
