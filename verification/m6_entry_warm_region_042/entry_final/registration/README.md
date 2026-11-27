# 042 E 最终注册准备

**H0、H1 的最终注册已准备，每个项目恰好两条精确定义。尚未授予项目或 Hook 信任，尚未启动模型回合。** 本目录与先前已封存的 `entry/` 发现脚手架分开；不要信任或继续使用旧脚手架中的用户层定义。

## 本人需要查看的两个项目

H0（原 PowerShell 包装）：

`D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/H0`

H1（直启同一个受控启动器）：

`D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/registration/workspaces/H1`

每个目录只在 `.codex/hooks.json` 注册以下两条命令；没有用户层 Hook，没有 TOML 内联 Hook，也没有 `PreToolUse`、`Stop` 或 `Interrupt` 注册。

| 事件 | 数量 | 匹配 |
| --- | --- | --- |
| `UserPromptSubmit` | 1 | 正常提交事件，无 matcher |
| `PostToolUse` | 1 | `^mcp__human_eye_live__human_eye_connection_status$` |

因此需要原生审阅的精确定义合计 **四条**，不是两条。H0 的两条只增加 041 原有的 PowerShell 编码包装；解码后的参数与 H1 的同事件参数完全相同。两边均使用相同的 R3 安装、解释器和下面同一配置，不含测试专用执行包装：

`D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/E_FINAL_001/direct/CONFIG.json`

该文件 SHA-256 为 `1a416026a191a6b6f535fcd25c1acf55a2168cf8ca72aba98a7c7947f512ea2e`，固定连接 `127.0.0.1:48142`。完整命令与 H0 的逻辑参数见本机 `registration/REGISTRATION.json`，其 SHA-256 为 `cf09e6c3b00874fe4282d280de1b8e7f6c0380b67ea4e165768d87e8c6f2ae9c`。

在桌面中分别打开这两个项目，先完成正常的项目信任，再使用输入框的 **Review hooks** 或 **Settings > Hooks** 审阅各自项目文件中的两条定义。以当时宿主实际显示的来源、命令和哈希为准。不复制任何 `trusted_hash`，也不把下述用户层镜像的状态带入桌面。审阅阶段不发送业务提示；后续须先恢复获授权的 G60 实例。正常审阅入口见 [OpenAI Hook 文档](https://learn.chatgpt.com/docs/hooks)。

另有 `workspaces/OFF` 对照项目：同样的私有 MCP 配置，空的项目 Hook 文件，零个 Human Eye 定义。它没有额外的 Hook 审阅项。正式使用 OFF 前也必须按宿主正常流程启用其项目配置，并核实没有其他启用的同名 Human Eye 定义。不得用关闭全部 Hook 的全局功能开关代替只关闭 Human Eye 的对照。

## MCP 与指定只读事件

三个项目的 `.codex/config.toml` 完全相同，只注册私有 stdio 服务器 `human_eye_live`，启动命令为原 041 R3 `serve --config`。`enabled_tools` 仅允许 `human_eye_connection_status`；模型侧不暴露观察或写入工具。此字段已被真实本机配置解析器识别，公开定义见 [配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。

必须保持这个服务器名称。冻结的 R3 Hook 只识别 `mcp__human_eye_live__human_eye_connection_status`；另取别名会失去实际 PostToolUse 路由。本回合只读工具参数应为 `{}`。它读取服务状态，不产生新的几何观察；不能把它返回的 `host_connectivity_checked: false` 当作宿主连接失败或成功的证据。实际端口与 GUI 连通另由 direct 原件的正常队列 ping、源身份和端口复用检查证明。

现有桌面可能另带同名工具来源，不能假定其受管理或自动指向本批端口。在任何正式回合前，必须从实际桌面加载后的配置及 MCP 库存核对：本项目的 `human_eye_live` 指向此 R3 命令与共享 CONFIG，只允许状态工具，规范工具名没有含糊别名或重复来源，实际运行身份是本批 R3。只读状态与实际端点证明须互相吻合。若项目覆盖或实际来源不能证明，停止该回合；不能把单独直连 stdio 成功当作桌面工具选择成功。

## 已取得的真实元数据

| 探针 | 实际结果 | 范围 |
| --- | --- | --- |
| `metadata_project_H0/H1/OFF` | `hooks/list` 为空；明确项目未信任警告；原生 `config/read` 保留被禁用的项目层与状态工具 allowlist；有效 MCP 配置和库存为空 | 证明项目信任门存在，未证明信任后的覆盖 |
| `metadata_user_mirror_H0/H1` | 每组恰两条精确命令，事件为 `userPromptSubmit` / `postToolUse`，匹配规则正确，均启用但未信任 | 单独的用户来源解析证明，不是桌面项目注册资格 |

用户镜像只在独立探针 HOME 放 `hooks.json`，其工作区为空；没有项目副本、内联 Hook、认证文件或已有信任。不要打开这些 HOME 来代替最终桌面项目。本批五次元数据探针均仅使用初始化、发现和配置读取，不创建回合、不写信任、不调用 Blender，所有所属 Job 进程与管道已结束。

固定 G60 端口的独立直接预飞由 `direct/preflight_02/RESULT.json` 单列，包含状态工具、原始 G60 几何核对及同端口关闭后重开。其 SHA-256 为 `33a07b23e3140d818fa82caa73d9a4a8942f37e5a0a4f5edfbad40984b1fd734`。直接预飞和手工 Hook 探针都不是自动上下文交付证据；预飞结束时实例已关闭。任何正式提示前都需要新的同端口实际拥有实例就绪回执。

首次准备因代码错误假设 CONFIG 含 `build_id` 而失败；实际配置按完整 `source_sha256` 绑定。失败源码与五次依赖性启动前拒绝均保存在 `registration/failures/prepare_001/`，没有启动宿主。修复只改准备检查，CONFIG 与已冻结 R3 均未变。

## 资格与复核

当前状态为“最终定义准备完成，等待正常原生审阅及实际桌面来源核验”。自动派发、请求 ID 的模型消费、同回合工具结果保留、三组计时和实际在途取消均未运行。本轮没有用用户镜像、直接预飞或静态正则代替这些资格。

本机原件索引是 `E_FINAL_001/registration/INDEX.json`；仓库中 [INDEX.json](INDEX.json) 只含来源描述、摘要与本地原件指针。运行 `verify.py` 可只读复核四条精确定义、H0 解码参数、共享配置、状态工具 allowlist、五份真实元数据及资源收尾，不启动宿主或模型。
