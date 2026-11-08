# 真实 MCP 消费入口：有界准备建议

状态：只读设计，未启动模型、Blender、MCP 服务或新聊天；未读取 auth.json、API Key、令牌内容。2026-11-08 本机帮助实查版本 codex-cli 0.152.1。固定产品为交付 b821407 中的 17db41c，131 源摘要 01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de。

结论：可以直接准备 4 个既有资产 × N/P 共 8 答。P 正常注册现有生产 stdio；N/P 共用一个中性的原生 MCP 适配器，完整保留 bpy、数学、脚本和可选图片。当前同用户主机条件只能支持非盲工程诊断，不能声称对答案文件、历史经验或插件源码实现了硬隔离。没有必要先建隔离平台，也不应通过关闭 N 的原生能力制造隔离或收益。

## 1. 最短执行链

每答一个新鲜的非持久 Codex exec 进程、一个 owner 持有的 NativeSession、一份私有资产副本。N 与 P 不能复用同一个 Blender 状态或测量缓存。用原 chain_owner 的 owner/deadline/reap 机制，不复用它硬编码旧源 fb5a 的命令及旧 P observe 分支。

共同路径：Codex 注册 `native` stdio MCP → 一个薄中性适配器 → 已有 NativeSession.run / 原生 worker → 真实 bpy。适配器只把 `execute_blender_code(code, deliver_paths=[])` 调用和实际 stdout/error/图片转成 MCP 内容，不内置几何答案、不限制候选到指定对象、不替模型写求解器。模型可保存脚本、使用 Python/mathutils、遍历网格、批处理、复用同答的 namespace 和缓存。N/P 的原生 tool schema、说明、权限、输出预算和图片能力逐字一致。owner 关闭不暴露为答题工具。

P 额外路径：Codex 正常注册 `human_eye` stdio MCP → 已通过的 qa_prepare/stdio_bootstrap.py（每答新 PLAN、source_root、run_root、endpoint 和显式 live config）→ 原 production_server.main → 原 connector/socket → 同一答的 NativeSession 端口。保留既有核验源字节 loader；不使用 -B 或目录核对替代。不能启动上一轮 controller.run，因为它自动执行三态验收；不能把旧的 observe CLI、直接 handle_jsonrpc 或预制结果冒充注册工具。

P 服务只向 Codex 开放 `human_eye_scene_observe`；工具 schema 来自实际 tools/list，不能手写一份更容易消费的替身。`enabled_tools` 是宿主过滤，与服务端全部 tools/list 的物理字节成本分开记录。工具可选，P 可以只用原生。两组题面相同，不出现“优先插件”“相信插件”“不要原生核验”等条件提示。

可选图片不能复用 perf000_scene_tool.py 的交付路径：其 _request 明确拒绝 include_image。应复用已有 ImageLedger、NativeSession 的渲染记录和 OwnerBroker._native 的 deliver_paths 处理，在中性薄适配器里返回真正 MCP image block；或者两组均用相同的本地 view_image 路线。构造与交付分别计量，失败不退构造额度。不要增加自动视图选择或图像求解模块。

## 2. CLI 入口与登录

本机 exec --help 已确认 --ignore-user-config、--ephemeral、--json、--strict-config、-c、-C、--skip-git-repo-check。明确写有“auth still uses CODEX_HOME”。保留当前 CODEX_HOME；不复制凭据、不新建 API Key、不改全局配置、不运行 codex mcp add。用进程 argv 列表传递 -c，避免 shell 字符串拼装。

命令形状（占位参数，尚未生成或执行）：

```text
codex exec --ignore-user-config --ephemeral --json --strict-config
  --skip-git-repo-check -C <本答中性工作目录>
  -m <预登记同一模型> -c model_reasoning_effort="<同一档位>"
  -c model_provider="openai" -c forced_login_method="chatgpt"
  <共同配置逐项 -c> <本答 MCP 注册逐项 -c>
  -o <本答 final 文件> -
```

任务原文从 stdin 传入并保留确切字节。固定模型/effort/provider/tier，不因时间或成绩换模型。当前用户配置的 model_provider 为 openai_http；--ignore-user-config 后不能假设这个自定义 provider 仍存在。建议显式使用内置 openai + forced_login_method=chatgpt。如果现有订阅登录不可用或额度不足，停在该事实，不改成 API，不读取凭据内容，不自动回退其他服务商。子进程不传入 API Key 类环境变量；只沿用运行时本身的登录能力。

MCP 注册字段用官方支持的 command/args/cwd/required/enabled_tools；P 的示意：

```toml
[mcp_servers.human_eye]
command = "<已有固定 Python 绝对路径>"
args = ["-I", "<已核验 stdio_bootstrap.py>", "<本答 RUNTIME_PLAN.json>"]
cwd = "<本答私有运行目录>"
required = true
enabled_tools = ["human_eye_scene_observe"]
startup_timeout_sec = 20
tool_timeout_sec = 30
```

具体超时与输出上限最终随任务预登记冻结，不因哪组失败而调大。required=true 防止 P 在服务启动失败后被误计成正常 P 消费。N/P 的 native 服务都 required=true；正常完成不强制实际调用 HE。旧 state/audit/config 不复用。

## 3. 自动上下文污染：能关什么，不能承诺什么

--ignore-user-config 只承诺不读用户 config.toml；--ephemeral 只承诺不持久化会话。二者不等于关闭全局 AGENTS、用户 skills、系统/云配置或所有插件。实际白名单检查发现全局 AGENTS.md 存在，agent-learning 插件当前启用，并有 agent_learning/blender/node_repl 等全局 MCP 配置。

两组共同显式设置：features.hooks=false、features.apps=false、features.memories=false、memories.use_memories=false、features.multi_agent=false、features.goals=false、features.remote_plugin=false、plugins._default.enabled=false，并明确禁用当前安装的 agent-learning 及其他非本试验插件。配置来源仍可能有管理约束，不能绕过。关闭 bundled skills/自动 skills instructions，并按确切名称或路径禁用本机 Agent Learning skills；不要假设 skills.config 的 name 支持通配符。保持 features.shell_tool=true 和 features.view_image=true，以免 N 丢失正常求解能力。

中性 cwd 放在工程仓库及其 AGENTS 祖先链外，里面只放该题输入、允许的 scratch 和说明。project_doc_max_bytes=0 可作为关闭 AGENTS 注入的候选配置，但本轮只读文档不能据此保证全局 AGENTS 已被去除；验收看实际渲染输入。不要修改全局 AGENTS、启停用户服务、删缓存或更换 CODEX_HOME 来凑干净环境。

本机还存在 `codex debug prompt-input`（已查 --help，未调用），可渲染 model-visible input JSON；但它没有 --ignore-user-config 参数，不能直接把默认 debug 输出当成 exec 的有效上下文证明。准备阶段可以用完全匹配的覆盖项进行无模型输入检查，记录其与 exec 装载路径的边界；正式调用的公开工具清单/可见输入再核一次。不得为了观测去读隐藏推理。有效 N 工具集必须没有 HE、Agent Learning 或无关共享 GUI 入口；如果管理层强制注入无法消除，则报告“配置污染未排除”，不把它包装成干净 N。

## 4. 硬隔离判断

目前 NativeSession 的 Python namespace 能执行完整代码，同用户进程可读文件；模型 shell 也能读同机路径。fork_none、新工作目录、随机文件名、隐藏目录、不给答案路径以及“请不要读取”都不是 OS 级隔离。原 helper 自己也把保护范围写成终态指纹/文件 hash，而不是 Python sandbox。

关闭 shell_tool 不能堵住 bpy/Python 的文件读取，而且会改变原生能力。只对 Codex shell 加 deny_read 也不能自动约束外部 MCP/Blender 进程。因此本批建议明确标为“已清理自动注入的非盲工程诊断”。可独立盲化最终答案评分，但不得把评分盲化称为消费者硬盲化。需要真正硬盲评时，应在后续单独保证 Codex 和 native worker 的 OS 访问边界同时生效，隔开 oracle/作者代码/历史答案，同时保留完整数学与 bpy；本批不为此建平台。

## 5. 八答的最低可交付证明

冻结四资产 hash、四份问题及独立真值；每题 N/P 任务正文一致；交错顺序预登记，8 答不补跑。原生模型全部工具能力相同，唯一新增为 P 的 HE 工具。若产品要求 known focal ID，双方题面都给同一名称/ID 映射，并明确这批不含 ID 发现收益；不能在 P 侧免费预查再省略这次成本。

复用已有每答150秒、每链600秒的上界时，从统一边界开始计时并保留原绝对期限；同时记录资产启动、MCP 握手、工具目录、模型首个工具与最终答复、cleanup 的分段时长。P/N 每答新进程与冷产品缓存；模型服务端缓存单列真实 cached tokens，不能称为完全冷模型。NativeSession 的控制调用、图片构造和所有失败也计入。

保存真实 MCP initialize/list/call TX/RX、Codex JSONL 中公开 tool-call/final/error/usage、实际 argv/config 的脱敏白名单、源绑定与 owner wait。hide_agent_reasoning=true，分析脚本只读公开事件白名单，不读取隐藏推理。每个新 exec 的终态 usage 按其会话计一次，勿再叠加累计快照；实际费用或缓存指标未提供就记未测。ephemeral 不留 rollout，不等于 stdout JSONL 可以丢弃。MCP/schema 物理字节、模型实际 token 和服务端缓存是三个不同口径。

评分同时看几何正确、unknown/partial 保留、目标遗漏、来源采用、是否有必要补查、完整耗时和 token。先冻结答案评分，再看 N/P 成本。模型不调用 HE 是结果，不补跑到调用。原生先查后插件不归因为插件 unknown。

停止点：准备不能证明正常注册和共同能力时先报告入口缺口；登录/额度失败不切 API；出现真实未恢复状态不重试动作。工程准备通过后按批准范围执行一次8答，结果不足以显示收益也如实关闭，不增加题量或改题刷过。

## 依据

- [官方非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)：exec、ignore-user-config、ephemeral、JSONL 与 required MCP。
- [官方 MCP 配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)：正常 stdio 注册、enabled_tools、required 与超时。
- [官方配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)：ChatGPT 登录限定、hooks/memories/plugins/skills、shell/view_image 及配置能力边界。
- 本机 0.152.1 的 exec/debug prompt-input --help；只读 config 白名单（模型/feature/plugin enabled/MCP 名称，未输出 env 或密钥）。
- 既有代码：surface_nearest_entry_001/qa_prepare/stdio_bootstrap.py；visual004_native.py；visual004_session.py；perf000_scene_tool.py；evidence_consume_001/run_01/qa/chain_owner.py。本轮未导入或执行这些文件。
