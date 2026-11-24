# Human Eye 本机目录

Windows 集中入口为 `D:/HumanEye`。主仓库使用 `D:/hefe`，新建的手工工作树和实验输出从集中入口下创建。Git 分支继续由主仓库和 GitHub 管理，一个独立任务对应一处明确的 checkout。

| 位置 | 内容 |
| --- | --- |
| `D:/HumanEye/worktrees/<short-id>` | 新的手工 Git 工作树。路径用短任务名，便于 Windows 上深层证据目录写入。Codex 管理的工作树由应用登记，用本机目录索引记录。 |
| `D:/HumanEye/runs/<batch-id>` | 一批实验的工作区、冻结输入、分段计时、失败记录和原件。 |
| `D:/HumanEye/releases/<version>` | 新的隔离构建和安装。启动绑定引用这一固定路径。 |
| `D:/HumanEye/publish/<batch-id>` | 清理后的待发布证据、回读摘要和远端提交核对记录。 |

本机入口内已有主仓库和常用历史工作树的快捷方式。完成的 `b32g-whole-release-001` 发布暂存已归入 `publish/`。早期工作树 `he_m4svc_e`、`he_m4svc_p` 和 `hm1rtfp` 仍由各自封存脚本引用。已绑定的验收原件、虚拟环境及正式桌面发布保存在原路径。历史引用以本机目录索引定位。

开始新批次时，先核对[唯一主计划](PRODUCT_ROADMAP.md)和[项目进度](PROGRESS.md)，登记基线、分支、工作树、实验输出目录和验收出口。建隔离安装时记录版本与源码摘要。关闭批次时记录真实分母、原件索引与 SHA-256，公开资料从 `publish/` 发布，公布证据提交与复核结果。公开文档使用 GitHub 固定提交链接。
