# M6-042 E 最终审阅准备

**最终定义已准备，正常桌面信任与自动入口验收待运行。** H0、H1 各有两个项目级命令，分别对应 UserPromptSubmit 和匹配只读连接状态工具的 PostToolUse。H0 使用 041 的 PowerShell 包装方式，H1 直启同一 R3 启动器。两臂和 OFF 共享固定 MCP 配置。OFF 的项目级 Human Eye Hook 注册为零。正式项目没有用户级或 TOML 内联的同名注册。

| 用途 | 待用工作区 |
|---|---|
| PowerShell 包装 H0 | [H0](D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/H0) |
| 直启 H1 | [H1](D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/H1) |
| 仅关闭 Human Eye Hook | [OFF](D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/OFF) |

正式连接使用本机 127.0.0.1:48142 上的普通 G60 副本。配置 SHA-256 为 1a416026a191a6b6f535fcd25c1acf55a2168cf8ca72aba98a7c7947f512ea2e。工具名为 mcp__human_eye_live__human_eye_connection_status，参数为空。PostToolUse 使用该规范工具名的精确匹配。[Codex 原生工具匹配与信任文档](https://learn.chatgpt.com/docs/hooks)

## 实际预飞

- 桌面随附的真实 app-server 做了五次独立发现。三个项目探针显示未信任项目配置被宿主隔离，项目 Hook 和生效 MCP 清单尚未加载。两个单独的用户级镜像各交回两条启用且未受信任的定义，宿主识别了精确命令与 PostToolUse 匹配。镜像是解析与发现证据，批准仍发生在实际项目来源。
- 直连预飞先实际启动普通 G60 副本，再用另一个 PID 重开同一端口。原插件、两次端口、源摘要与只读快照均核对。生产 stdio 实例确认注册的只读工具，并验证 Target 的最近对象为 Peer_000，11 个候选的业务字段与 041 冻结回执一致。G60 的完整几何读是独立直连控制。
- 正例提示经原 R3 规则判为空间读取。独立手工正例返回了一次实际观察，且额外上下文保留本次动态 correlation.request_id。H0 和 H1 的最终 PostToolUse 命令也分别收到实际只读工具回包作为手工载荷，均返回空 JSON，记录 tool_result_delivery_retained 与 duplicate_delivery_omitted，额外场景读取为零。
- 两个直接预飞的成功副本及首个未填必需会话标识的失败副本均正常退出。固定端口在手工 PostToolUse 检查前后可重新独占绑定。另保留注册制备、提示和直接工具预检的原始失败与恢复。未修改日常配置、旧原件或正式产品。

## 本人需要做的步骤

可在同一桌面会话依次打开 H0、H1。按正常 UI 确认各自工作区，再在 **Review hooks** 中逐条审阅项目来源和命令，合计四条。OFF 无新增命令需要批准。正式运行前重新绑定 G60 端点、核对项目来源的实际清单、同名 MCP 来源和只读工具，再按冻结提示与顺序开始。本轮没有发送模型提示。桌面派发、上下文消费、实际工具结果保留、耗时对照和在途取消均未运行。[原生审阅与恢复指引](RESUME.md)

[固定协议](FORMAL_PROTOCOL.json) · [原件索引](EVIDENCE.json) · [结果清单](RESULTS.json)
