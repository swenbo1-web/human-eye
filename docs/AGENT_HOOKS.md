# 通过宿主 hooks 自动调用三维引擎

`human_eye_plugin.agent_hooks` 提供 Codex、Claude Code 的命令 hooks 桥接。宿主收到提示或准备执行已登记的三维操作时直接运行引擎，模型不必先决定是否调用 Human-Eye 工具。MCP 工具列表本身不具备这个触发作用。

本文描述通用静态快照桥接及其未安装的配置示例。当前项目另已安装 [Codex 实时路由](CODEX_LIVE_ROUTING.md)，通过 BlenderMCP 读取当前场景，并验证真实动作前后 hooks。Claude Code 及本文静态快照示例仍按本地协议测试范围说明，发行包未更新。

## 接入条件

宿主连接器需要发布真实场景快照，并提供参数明确的变换工具。示例 `mcp__spatial_host__transform` 是连接器应实现的接口名称，当前 Blender 的任意 Python 执行工具并不自动满足这个接口。

1. 配置文件中的 `scene_file`、`state_file` 为显式本地路径，支持相对于该配置文件解析。不能把它们指向同一个文件，也不能指向配置文件自身。模型提供的同名参数不会改变这些路径。
2. 连接器在提示处理前导出当前场景，在操作完成后原子替换场景文件并更换非空 `revision`。场景使用米、世界坐标，包含稳定对象 ID、网格拓扑、轴及其来源信息。`meshes` 必须来自 `MeshEntity3D.to_dict()` 的真实宿主数据；没有场景时不会加载演示物体。
3. `focal_id`、`reference_id` 应对应实际对象。提示前的观察对象由配置指定；动作可显式指定对象，但若与已有观察不一致，运行时会要求重新观察。
4. 登记工具必须确实按相同语义执行：先绕对象 `pivot_world` 应用 `SE3AlignmentMath.euler_xyz_to_matrix` 的旋转，再施加世界坐标平移；单位分别是度、米。缩放、删除、任意脚本以及其他操作字段不会被当成已检查变换。

场景外层格式：

```json
{
  "revision": "host-scene-42",
  "unit": "m",
  "coordinate_frame": "world",
  "source": "your-real-host-connector",
  "meshes": []
}
```

这里的空列表只展示外层结构，不能作为有效场景使用。实际文件需要完整网格；不要用基准测试场景替代宿主场景。

登记工具的输入示例：

```json
{
  "action": {
    "focal_id": "moving-object",
    "reference_id": "reference-fixture",
    "translation": [0.0, 0.0, 0.01],
    "rotation_euler_deg": [0.0, 0.0, 0.0]
  }
}
```

`action_path` 是本地配置指定的点分路径，比如 `action`；不设置时读取整个工具参数对象。至少需要平移或旋转中的一项，省略的另一项视为零。`action` 内有其他字段会拒绝操作。外层工具参数的语义由连接器负责，不能再暗中改变动作的单位、坐标系或目标。

## 启动与示例配置

在源码目录中可以直接运行：

```text
python -m human_eye_plugin.agent_hooks --agent codex --config examples/agents/router-config.json --spatial-tool mcp__spatial_host__transform
```

命令从标准输入读取单个宿主事件 JSON，在标准输出仅返回单个 hooks 响应 JSON。使用 Claude Code 时把 `--agent` 改为 `claude`。

`examples/agents/hook_entry.py` 支持从其他项目目录启动源码版本，不需要先安装或重新打包。`codex-hooks.json`、`claude-settings.json` 使用了当前源码路径 `D:/hefe`，启用前需改成实际解释器和源码路径，并调整对象 ID、工具名称、快照路径。

把 Codex 示例内容按已有配置合并到项目 `.codex/hooks.json`，把 Claude 示例的 `hooks` 表合并到项目 `.claude/settings.json`。保留已有 hooks，不要覆盖整份现有设置。Codex 的 hooks 仍需遵守宿主自身的信任审查；项目文件存在不等于该会话已经启用。此说明与示例不执行安装。

`--spatial-tool` 可重复指定，示例中必须与精确 matcher、`spatial_tools` 键保持一致。这样即使本地配置损坏，桥接仍能识别需拒绝的登记操作；未登记工具原样放行。不要把它替换成通配符或把任意 `Bash` / Python 工具声明成可检查的空间变换工具。

## 事件与验证范围

| 宿主事件 | 路由行为 | 输出 |
| --- | --- | --- |
| `UserPromptSubmit` | 读取当前连接器的真实三维快照，调用 `before_model`；快照丢失时清除观察凭据 | 观察文本或连接器不可用原因 |
| `PreToolUse` | 对精确登记的工具调用 `before_action`，绑定上次观察及当前场景 | 拒绝时返回 `permissionDecision: deny`；通过时只补充上下文 |
| `PostToolUse` | 匹配同一个 `tool_use_id`，要求新场景版本，调用 `after_action` 检查宿主回读 | 新观察或未验证原因 |
| `PostToolUseFailure` | 不认证失败动作，清除桥接观察凭据 | 要求重新读取与观察 |

通过检查时不返回 `permissionDecision: allow`，因此不会替代宿主原有权限流程。`PostToolUse` 发生时动作已经执行，不能撤销其副作用；快照没有更新时也不能把旧快照称作宿主回读。

hooks 的 `additionalContext` 是文本通道。桥接不会把 base64 塞进文本后声称模型看到了图片，每次都会明确说明没有交付引擎图像。需要原生图片时使用 `AgentRuntimeAdapter` 在模型请求前组装图片内容。

快照文件的存在表示这个接入点当前提供三维上下文，不意味着桥接能从任意用户提示自动可靠地分类所有二维 / 三维任务。普通识图应由宿主选择不携带三维上下文的入口，或者使用运行时事件中的 `task_kind=image_2d/ocr/general` 显式走原生视觉。

## 状态、并发与故障处理

状态按 `agent:session_id` 隔离，通过跨进程文件锁和原子替换写入，最多保存 32 份会话元数据。一个连接器状态文件存在未完成动作时，后续登记空间操作会被拒绝，避免不同会话基于同一旧快照并发修改。未完成凭据不会因会话淘汰而消失。

Codex 官方说明子代理 hooks 可使用父会话 ID，因此不能把这里的会话隔离解释成所有 Codex 子代理都有独立感知状态。共享场景的 agent 应使用同一连接器锁；不同真实场景应使用不同状态文件。

配置、场景、状态损坏，或动作参数不明确时，已登记空间操作会被拒绝。未登记工具直接返回空 JSON，不扫描脚本、不读取其文件。快照丢失、完成事件不匹配、动作失败或回读版本未更新时，会隔离整个连接器，清除所有会话的观察凭据，避免其他 agent 用旧状态继续操作。宿主发布新版本快照并完成有效的新观察后才能恢复；单纯重试旧版本不会解除隔离。

若宿主在动作通过检查后没有执行动作、也未触发完成回调，保留的未完成凭据会继续阻止动作。确认宿主真实状态、发布新版本并重新观察可以恢复，不应让模型自行删除状态文件。旧会话恢复时也必须重新读取最新快照。

这里检查的是所供快照中的终态网格几何。没有轨迹碰撞认证；hooks 也不能消除场景检查与宿主实际执行之间的竞争条件。需要强制执行保证时，宿主执行器必须在同一事务 / 锁内核对已检查版本并执行，不能只依赖提示文本。状态文件是可信本地连接器数据，不能提供给模型随意改写，也不是防篡改授权令牌。

本地测试覆盖两种宿主响应结构、真实引擎跨三次进程的观察→动作前检查→新版本回读、三进程并发写入、会话隔离、异常拒绝、未知工具直通和状态上限。这些测试不等于所有 agent 或真实宿主已经适配。

协议依据：[Codex hooks](https://learn.chatgpt.com/docs/hooks)、[Claude Code hooks](https://code.claude.com/docs/en/hooks)。
