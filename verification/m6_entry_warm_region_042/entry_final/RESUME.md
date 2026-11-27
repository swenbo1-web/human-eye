# M6-042 E 正式入口恢复指引

本页对应最终项目级定义。固定的两个提示、事件顺序与判定条件见 [FORMAL_PROTOCOL.json](FORMAL_PROTOCOL.json)。

## 一次桌面审阅会话

1. 在同一正常 Codex 桌面会话中依次打开 [H0 工作区](D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/H0) 与 [H1 工作区](D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/H1)。若宿主提示项目未信任，先通过工作区的正常信任界面审阅该隔离目录。
2. 在每个工作区从输入框的 **Review hooks** 或 **Settings > Hooks** 审阅两条项目级定义。每个工作区批准一条 UserPromptSubmit 和一条 PostToolUse，共四条。按列表中的项目路径、事件与精确命令匹配，并记录这个项目来源实际显示的当前哈希。PostToolUse 应只匹配 mcp__human_eye_live__human_eye_connection_status。H0 有 PowerShell 包装，H1 直启同一个 R3 启动器。两个项目的用户级发现镜像是独立探针，只审阅当前项目的定义。 [Codex 原生审阅流程](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks)
3. [OFF 工作区](D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/OFF) 保留同一只读 MCP 配置，项目级 Human Eye Hook 注册为零。启用这份项目 MCP 时也走正常的项目确认。沿用同一桌面会话和其他 Hook。若实际宿主库存出现其他来源的重复 Human Eye 注册、错误启动器或连接身份，先把它作为准入阻塞记录。

审阅前可读取配置和原件。此时无需启动 Blender 或发送提示。四条命令均围绕同一固定端点，正式试验开始时再拉起普通 Blender 副本。

## 正式运行的人机边界

- 原始 G60 文件通过 SHA-256 重新校验。启动实际端点后记录新副本、进程、IPv4 回环端口、原版 Blender 插件及无图读的身份。复用 [直连预飞与端点入口](direct/README.md)。
- 每臂开始前保存实际宿主身份、项目来源和启用的 Hook 清单。H0 或 H1 必须看见正好两条本臂可运行定义，OFF 本臂 Human Eye Hook 为零。核对 human_eye_live 只读工具来自这份 R3 连接，记录实际 Pro 模型和配置并保持一致。
- 使用 [冻结协议](FORMAL_PROTOCOL.json) 的轮换和提示，不把任何预飞的网格名、结果或动态请求 ID 带入提示。对正例，在首次模型工具开始之前核对本回合 Hook 上下文已交付，且动态 correlation.request_id 与本次 Hook 审计一致。随后只调用一次 human_eye_connection_status，保留原工具结果与 PostToolUse 的同一工具调用标识。用请求与实际审计确认额外几何捕获为零。
- 取消控制在 H1 的真实只读 UserPromptSubmit 已开始且仍在途时，通过宿主的正常停止动作执行。保存启动、取消、晚到处置、进程退出和场景前后证据。若没有观测到可中断窗口，将此格记为未取得实际取消证据。直接预飞的超时、终止或空响应只用于准备诊断。
- 最后停止本批拥有的副本并核对进程、端口、原始文件和私有副本。实际时段的宿主记录使用自身时钟保留，模型等待单列。

本补交只做正式审阅准备。工作区信任、命令批准及真实桌面自动试验均留待上述正常步骤。
