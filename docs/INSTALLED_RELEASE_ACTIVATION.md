# 检查和切换已安装的桌面版本

当前桌面发行版为 `9.7.2+k049final`。在已连接的客户端调用 `human_eye_connection_status`，核对 `distribution_version`、运行源数量和摘要。检查生产服务目录时应能列出五项工具。连接状态反映已加载的引擎身份，几何采集需另用实际宿主验证。[发行身份](PROGRESS.md)

## 已安装的固定入口

桌面注册使用该次安装的 `admin/target_runtime_entry.py` 和相邻的 `RUNTIME_BINDING.json`。绑定中记录解释器、发行目录、管理脚本及逐件源摘要。入口用绑定的 Python 以 `-I -B` 运行，支持 `identity`、`serve`、`hook` 和 `admin`。仓库中的脚本保留本次桌面使用的固定路径；其他部署应使用其安装时生成并核验的绑定。[入口实现](../examples/agents/target_runtime_entry.py)

## 审阅安装切换

在目标安装上以 `admin doctor` 检查状态，以 `admin plan` 预览迁移。两者使用对应的 `--agent`、`--project`、`--config` 和 `--expected-build`。审阅输出中的服务、Hook、状态和备份路径后，管理工具接受 `plan --apply --plan-sha256 <本次计划摘要>`。它会在锁内重新检查前置状态。回退同样基于当时最新状态生成计划。[管理工具](../examples/agents/installed_release.py)

桌面切换记录验证了真实 MCP 和手动注入的提示事件。五条 Hook 的宿主审阅状态由桌面管理。在设置中查看当前定义及信任状态，可以区分手动调用和自动触发。
