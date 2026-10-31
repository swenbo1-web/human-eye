# Human-Eye 自动路由的 Agent 接入范围

Human-Eye 当前面向有真实网格、对象身份和坐标系的三维空间任务。自动路由由宿主在模型调用前触发；模型收到引擎观测后进行理解和规划。现阶段不把普通图片理解、视频重建或所有 Agent 的无配置接入列为已完成能力。

## 当前已实现的接入层

`human_eye_plugin.agent_adapters` 不依赖模型 SDK，不持有凭据，不发送模型请求。它将统一路由结果转换为下列消息格式，并保留原任务、原有消息和角色：

| `format` | 输出形状 | 调用方接入位置 | 当前验证范围 |
|---|---|---|---|
| `openai_responses` | `role=user`，`input_text` / `input_image` | Responses 请求的 `input` | 本地协议与 PNG 字节测试 |
| `openai_chat` | `role=user`，`text` / `image_url` | Chat Completions 请求的 `messages` | 本地协议与 PNG 字节测试 |
| `anthropic` | `role=user`，`text` / `image.source.base64` | Messages 请求的 `messages` | 本地协议与 PNG 字节测试 |
| `gemini` | `role=user`，`parts` / `inline_data` | generateContent REST 请求的 `contents` | 本地协议与 PNG 字节测试 |
| `mcp` | `text` / `image` 内容块 | MCP 服务端 ToolResult 的 `content` | 本地内容块与 PNG 字节测试 |

OpenAI-compatible 服务可以使用前两种格式，但实际端点、具体模型和中间 Agent 是否接受图片，仍由宿主确认。DeepSeek、Qwen 等名称不自动等于图像能力；纯文本模型应设置 `supports_images=False`。这里的 Gemini 格式明确指 generateContent REST，不代表已实现其他 Gemini 接口或某个 SDK 的对象构造。

上述是**协议格式兼容和本地集成测试**，不是各厂商、各模型、各 Agent 的真实鉴权与完整操作验收。当前适配器没有发起真实 provider 请求，也未证明图像已被远端模型消费。`delivery.image_delivered=True` 表示已将图像放进输出载荷；宿主还应核验实际发送及服务端接受结果。

后续 [Codex 实时路由](CODEX_LIVE_ROUTING.md) 已在当前 Codex 会话中单独验证原生 MCP PNG 交付、动作前自动拦截和动作后实际回读。这项宿主证据不替代上表各厂商 API 的鉴权与模型效果测试，也不推广为其他 agent 已实机支持。

[项目配置入口](AGENT_SETUP.md) 可以为独立项目生成 Codex、Claude Code 或通用 MCP 配置。默认预览，显式写入时合并已有设置并备份。当前 Codex 提示前自动观察也已有真实宿主证据；Claude 仍处于本地格式、启动命令及服务连接验证阶段。

## 通用 Agent 循环

宿主向 `HumanEyeAutoRouter.handle_event(event)` 交付规范化事件，随后使用 `AgentRuntimeAdapter` 在实际模型调用前准备输入。路由器对象也可替换为实现同一协议的自定义同步 callback。

```python
from human_eye_plugin.agent_adapters import AgentRuntimeAdapter

# router、event、messages、invoke_model 由宿主提供。
# event 应包含当前会话、任务及真实场景信息，遵守路由器事件协议。
adapter = AgentRuntimeAdapter(router, format="openai_responses", supports_images=True)
prepared = adapter.before_model(event, messages)

# invoke_model 是宿主已有的调用函数，不属于适配器。
reply = invoke_model(prepared["messages"])
```

`before_model` 返回 `{routing, messages, delivery}`。调用方将 `messages` 放到上表对应的请求参数；原有模型参数、工具定义、凭据和预算仍由调用方维护。异步框架可以在其模型节点之前调用此同步准备步骤，并自行调度耗时的引擎工作。

该方法只接受 `event="before_model"`。`before_action` 和 `after_action` 必须由执行边界另行提交给路由器，避免在准备模型输入时意外改变动作事务。

LangGraph、LangChain、AutoGen、CrewAI 或自定义 agent loop 等，只要允许在模型输入前插入 callback，都可以使用同一边界进行接入。这是接入路径说明，当前未提供这些框架各版本的专用 SDK 插件，也未逐一实机验证。无法插入该边界的封闭 Agent，需要其提供可用的 hooks 或宿主扩展接口。

## 路由与交付语义

- `native`：不追加任何观测消息，原消息按值保持一致；函数返回深拷贝，避免后续宿主修改污染原输入。
- `engine`：追加引擎观测数据及可用的真实图像内容块，保留场景版本、观测身份、测量有效性等元数据。
- `blocked`：追加原因和有效性数据，保留 `allow_action=False`、`requires_reobserve` 等字段；模型仍可解释问题，但执行宿主必须检查并落实动作决定。
- 有图像但宿主不支持图像：明确返回 `image_available=True`、`image_delivered=False`、`degraded_to_text=True`，文本也标记图像已省略。不会声称模型已看见图像。
- 无图像：标记 `image_available=False`，区别于有图像被降级。

观测以 user 数据消息追加，不提升为 system、developer 或 assistant 消息。文本是 JSON 观测文档，场景字符串保持为数据；适配器只转发协议元数据和 `context_text`，不额外传入调用方提供的目标动作、标准答案或评估标签。宿主仍应保证 `context_text` 本身来自可信的观测构建流程，适配器不验证自然语言中的几何结论。

输入消息、事件及路由结果均不原地修改。对格式名、协议版本、路由值、base64、实际图像文件和 MIME 一致性进行校验；异常向调用方报告，不伪造成功观测。当前支持 PNG、JPEG、WebP 和静态 GIF 的转换，路由器正常图像输出为 PNG。使用项目已有 Pillow 依赖校验文件，无模型 SDK 依赖。

MCP 的 `build_agent_observation(..., format="mcp")` 返回真实 MCP `content` 块，同时提供一个 `role=user` 的宿主中立 `messages` 信封，便于统一的本地处理。这个信封不是 MCP wire 消息；MCP 服务端应读取 `content` 并放进 ToolResult，由自身 JSON-RPC 层管理请求 ID 和错误。不得直接将该信封当作某家模型的消息格式。

## 自动触发和执行边界

MCP 工具注册、工具描述或技能说明本身不会保证自动调用。宿主必须在以下位置建立真实调用链：

1. 在适用的模型调用前提供当前任务与场景事件，执行路由并交付观测。
2. 在三维操作实际执行前，调用并强制落实动作检查；不能仅把 `allow_action` 放进模型上下文。
3. 在场景变化或执行后，将真实结果回读为新场景版本，供后续重新观测。

`AgentRuntimeAdapter` 只实现第一项的消息准备，不接管工具执行。仅运行本适配器无法阻止另一条未经过网关的操作路径。没有 hooks 的 Agent 需要宿主修改其模型调用和执行边界；有 hooks 的 Agent 也需验证事件覆盖和图像交付能力，文本上下文 hook 不能被视为图像已经注入。

这能减少模型主动查工具、组织查看参数和再次调用的步骤。它不保证模型一定相信引擎，更不能替代观测准确性、路由准确率、延迟以及最终任务结果的验证。

## 验证及参考

本地回归文件为 `verification/test_agent_adapters.py`。覆盖五种内容块的真实 PNG 解码、原任务保持、输入不可变、native 透传、明确降级、blocked 原因、额外答案字段隔离，以及错误协议与损坏图像拒绝。真实模型验收需另行记录具体 Agent／版本、模型／端点、图片是否被接受、触发率及执行网关覆盖率。

可运行 `python examples/automatic_3d_routing.py` 检查真实引擎与五种适配格式的完整本地连接，也可加 `--report PATH` 保存 JSON 记录。各格式使用相同任务、相同显式网格和相同 PNG；观测完成后仅调用一次明确标注的固定模型 stub，并演示动作检查与内存宿主变更后的回读。该示例不是模型效果测试，也不是实际三维宿主或性能验收。

格式依据以下官方文档核对；这些文档说明消息格式，不构成对本项目实机兼容性的背书：

- [OpenAI 官方图片输入说明](https://developers.openai.com/api/docs/guides/images-vision)
- [OpenAI 官方 Chat Completions 内容块定义](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [Anthropic 官方 Vision 输入说明](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Gemini 官方 generateContent 图片输入说明](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding)
- [MCP 官方工具与内容块规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
