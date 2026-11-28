# Agent 接入

首次配置开发项目时，从已装好依赖的 Python 运行仓库配置工具。以下示例在仓库根目录执行，目标目录需已存在。

```powershell
python -B examples/agents/configure.py --agent codex --project 'D:/my-project'
```

默认输出预览。核对连接器、解释器、服务与事件命令后，添加 `--apply` 写入项目。使用 `--python` 或 `--engine-root` 可以显式选择解释器与源码根。已有桌面发行的受控迁移另有带身份绑定的管理入口。[配置工具](../examples/agents/configure.py) · [安装版核对](INSTALLED_RELEASE_ACTIVATION.md)

| 接入目标 | 配置位置 |
| --- | --- |
| Codex | 项目的 `.codex/config.toml` 和 `.codex/hooks.json` |
| Claude Code | 项目的 `.mcp.json` 和 `.claude/settings.json` |
| 通用 MCP 客户端 | `.human-eye/mcp-client.json` 配置参考 |

`project_root` 标识引擎根目录，连接配置决定 `state_file` 和 `audit_file` 的位置。应用计划前会备份即将修改的文件。同名服务冲突、配置变化或未完成动作需要先核查现有状态。工具目录可通过 MCP 的 `tools/list` 验证。自动事件交付还依赖对应宿主实际加载并信任项目 Hook。[Hook 接口](AGENT_HOOKS.md)
