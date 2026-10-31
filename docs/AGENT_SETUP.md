# 在其他项目中接入 Human-Eye

2026-10-28 当前聊天重载验收：已实际载入 v19／9.7.2+20261028.support.discovery.r1（a0198acc…／installed_distribution／68 文件），状态健康、目标账本 0，旧配置快照拒绝已解除。当前 MCP 完整发现唯一支撑面，实测间隙仍为 3.1304261516453477 毫米；回填完整 selector 的 1 毫米目标预览只返回单步限幅候选，未移动。人为改错客户端 revision 的预览被拒绝并要求重新观察；没有实际编辑宿主来制造这条负例。独立 Fraction 真值、768×768 原生 PNG 和全 14 Scene 不变均已核对。

真实用户三维回复已在模型该轮工具调用前触发 v19 UserPromptSubmit，自动交付完整几何文字；五组定义保留。本轮还核对了 clearance_segment 预览的 PreToolUse／PostToolUse 去重，不能当作 execute:true 的动作链或 transform 各事件已通过。自动原生图片仍未证明，Hook 为 text_only。先前独立安装私有场景的 12 次移动是另一阶段证据，本聊天本轮零移动。

只读安装 SDK 边界矩阵 12 组／28 次调用／277 项检查通过；凹体、开放 reference、穿透／接触和有限面外一 ULP 明确 unsupported，几何／有理复杂度和过长 revision 返回 unknown，不放宽门。真实多候选截断未覆盖。下一单点候选先检查审计日志大字节／少行时重复整写和轮转，再考虑纯距离观察的对齐按需；两项均未实现，成本对照仍 pending。既有 27.84%—36.71% 文本字节减少不等于端到端或模型提速。工程构建可继续有限验收，整体公开发布门仍为 false。

[当前重载阶段](../verification/fixes/20261028_v19_reload/REPORT.md)、[当前量测与预览核对](../verification/fixes/20261028_v19_reload/CURRENT_VALIDATION.json)、[真实用户文字 Hook 审查](../verification/fixes/20261028_v19_reload/REAL_USER_HOOK_REVIEW.md)、[只读边界矩阵](../verification/fixes/20261028_v19_reload/MATRIX_REVIEW.md)。接口继续见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)。

本机 Codex 的真实文字消息入口已通过本轮有限验收；其他 Agent 的配置生成、服务连接、事件实际派发和输出消费仍须分别验证。自动原生图片与当前聊天 execute:true 未因本次文字 Hook 通过而取得资格。

以下保留此前阶段记录，尤其 v19_activation 的待重启状态仅表示当时阶段；当前状态以上文和本轮重载报告为准。

2026-10-28 最新状态：v19 工程构建 9.7.2+20261028.support.discovery.r1（a0198acc…／68 文件）已离线安装并完成磁盘激活，新注册进程实际验收通过。当前聊天仍为 v16 旧配置快照，返回 stale_configuration_snapshot，需重启后核验；真实新用户 Hook 未通过本版验收。四文件迁移保留五组 Hook、Agent Learning 当前配置与状态，state 仅改配置绑定；磁盘激活不等于宿主信任或当前聊天重载。

显式 query.support_plane_discovery 已实现当前对象对的精简发现，完整 selector 可回填有界执行段。四模板文本字节中位减少 27.8448%—36.7095%，本地服务仍增加约 1.8—8.0 毫秒，不宣称模型或端到端提速；默认 PNG 保持。接口与边界见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)，[新注册入口结果](../verification/fixes/20261028_v19_activation/REGISTERED_ENTRY_RESULT.json)和[配置保留结果](../verification/fixes/20261028_v19_activation/activation/PRESERVATION.json)。

下方 configure.py 是源码接入指南；现有安装升级走 [受锁安装激活](INSTALLED_RELEASE_ACTIVATION.md)，不以源码生成配置覆盖安装状态绑定。其他 Agent 客户端需理解本次 metadata 引用声明，分别验证真实消息、动作 Hook 和图片交付。

以下为此前阶段记录，保留当时版本、命令及验收边界；当前状态以上文及精简支撑面发现说明为准。

当前入口面向 **Human-Eye 源码目录 + 本机 BlenderMCP**。配置目标项目可以与引擎源码分开放置；运行环境需要 Python 3.10+、NumPy 和 Pillow。合并已有 Codex TOML 配置时使用 Python 3.11+。这里生成的是源码接入配置，旧发行包尚未更新。

## 先预览，再写入项目

在 PowerShell 中指定安装了依赖的 Python，以及已经存在的目标项目目录：

```powershell
$eyePython = 'C:/你的环境/python.exe'
$eyeProject = 'D:/你的项目'
& $eyePython -B 'D:/hefe/examples/agents/configure.py' --agent codex --project $eyeProject
```

默认只输出预览，不创建目录或文件。预览包含将新增或修改的路径、修改前后哈希、本引擎的配置，以及可读的 hook 参数。Windows Codex 的启动命令使用 PowerShell 编码；预览同时给出解码后的脚本，便于检查实际运行内容。

确认预览符合预期后，在同一命令后加 `--apply`：

```powershell
& $eyePython -B 'D:/hefe/examples/agents/configure.py' --agent codex --project $eyeProject --apply
```

运行脚本所用的 Python 默认就是配置中的解释器。需要指定其他解释器时加 `--python 'C:/另一个环境/python.exe'`；引擎源码移动后，可通过对应源码中的脚本生成新项目配置，也可显式指定 `--engine-root`。当前工具不会自动改写已有、指向其他引擎或解释器的同名服务。

## 三种配置目标

| `--agent` | 生成或合并的项目文件 | 自动触发范围 |
|---|---|---|
| `codex` | `.codex/config.toml`、`.codex/hooks.json` | 提示提交前观察、目标变换工具调用前检查、调用后复核；需要宿主加载并信任相应定义 |
| `claude` | `.mcp.json`、`.claude/settings.json` | 生成对应的三类 hooks，使用直接执行参数；需要 Claude Code 加载并批准项目配置 |
| `mcp` | `.human-eye/mcp-client.json` | 通用 MCP 启动配置参考；客户端需要导入，不保证自动观察 |

三种目标都使用项目内的 `.human-eye/live-connector.json`。它的 `project_root` 字段在当前协议中表示**引擎源码根目录**；`state_file` 与 `audit_file` 相对于该配置文件解析并留在目标项目内。已有且兼容的连接配置会逐字节保留，避免改变持久化状态绑定的配置指纹。

生成配置不等于宿主已激活。当前 Codex 会话已有真实提示前、动作前和动作后 hooks 的独立证据。Claude 配置已通过本地格式、生成命令和服务启动检查，但尚未通过 Claude Code 实机事件验收。通用 MCP 配置也未逐一在其他客户端验收。

## 合并、备份与状态保护

工具保留其他 MCP 服务、其他 hooks、权限设置以及已有的 `agent-learning` 启停配置，不修改用户全局配置或代替宿主批准信任。重复执行相同配置不重复增加条目。当前项目的 agent-learning 已按用户新要求恢复，旧双盲记录中的禁用状态仍是当时的实验条件。

写入前在 `.human-eye/setup-backups/<编号>/` 保存修改前文件和 `manifest.json`；过程失败时尝试恢复已写入的文件，结果记录为 `rolled_back` 或 `rollback_incomplete`。备份不是自动切换到旧运行状态的入口，工具不会重置空间状态或清除未完成动作。

同名服务或 hooks 冲突、预览后配置变化、状态指纹不匹配、未完成动作，以及配置路径跨项目链接等情况会报错并保留现有配置。不要通过删除状态文件来绕过这些检查；应先检查真实宿主场景及运行状态。

## 运行条件与能力边界

Blender 中需要运行可用的 BlenderMCP 连接器，当前默认地址为 `127.0.0.1:9876`。配置生成过程不连接 Blender，不发起模型请求，也不验证目标解释器中的所有依赖；启动服务后仍需做连接验收。

hooks 当前交付文字观测；实时 MCP 服务能交付 PNG。没有对象对的场景仅提供总览，不据此认证间隙或允许动作。执行网关检查候选终态并读取实际结果，不认证运动路径。其他绕过该网关的 Blender 操作不受这些 hooks 覆盖。

需要其他 agent 在推理前接收图片时，应使用其宿主的模型调用前回调接入 [统一适配器](AGENT_COMPATIBILITY.md)。仅注册 MCP 工具无法保证该 agent 自动调用引擎。

参考：[Codex hooks](https://learn.chatgpt.com/docs/hooks)、[Claude Code hooks 的直接执行形式](https://code.claude.com/docs/en/hooks#exec-form-and-shell-form)、[Claude Code 项目 MCP 信任](https://code.claude.com/docs/en/mcp#project-server-approvals-and-workspace-trust)。这些文档说明宿主接口，不替代本项目的实际验收。
