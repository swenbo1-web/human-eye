# M1 区域任务简报客户端恢复独立复核

2026-11-22。实际装配预飞通过，唯一一次正式本地资格 **0/1**。正式 QA 取得真实 Codex CLI 工具目录，但未取得该次 thin 子进程的可绑定退出凭据。依[恢复方案](M1_REGION_TASK_BRIEF_CLIENT_PROFILE_RECOVERY_001_PLAN.md)收口，无替补。

## 固定版本和原件

复核固定产品 `8cf3fabc1a735b7ff5849b3c63c49cf932df4b6b`，143 源摘要 `65bd1ec8009f8024e85ef1cd30c1229957cceb1c1766c8e5b62f2ef2489ce48c`、wheel `97053290d96270fefeff95d681efaf5222a64ef136a084267be5d7c707d6813d`。恢复冻结 `f7db1dd00`、835 项，清单 SHA-256 `7d28244640492fd9550701f05202384f3da707564a586dde57f6244f13b18abc`。从证据提交的 Git 对象逐一核对压缩包的 616 个唯一成员、大小和 SHA-256。ZIP 2,131,179 B，SHA-256 `d6f4cd6b4e2f811b1d3fa7be7816592d1b73da85b05ac3f47d4f7866defb34a2`。历史首次 `6778775f` 装配失败、零业务和原判定保留。 [恢复报告](https://github.com/swenbo1-web/human-eye/blob/107f716ffb7040230f82a36f7905122c85170947/verification/m1_region_task_brief_client_profile_recovery_001/REPORT.md) · [原件索引](https://github.com/swenbo1-web/human-eye/blob/107f716ffb7040230f82a36f7905122c85170947/verification/m1_region_task_brief_client_profile_recovery_001/RAW_INDEX.json)

## 真实装配预飞

原失败在加载保留的 `FrameDevice` 时缺少 `SOURCE_REGION`，复核还确认缺少 `load`。恢复桥透传原依赖，预飞实际经过同一设备和 Owner、thin 以及隔离实装 MCP。A 在 thin 层 7 次业务尝试，实装派发 7 次。B 13 次尝试、8 次实装派发。实装收到的参数与原请求逐项一致。B 显式 `full` 和 `null` 被参数校验拒绝，均无产品派发，之后合法请求成功。thin 的第 13 次无 Owner 传输，另用独立的真实 Owner 请求验证第 13 次也拒绝且零产品派发。预飞两臂的 thin 有正常 EOF 和退出码 0，Owner 和实装 MCP 均确认关闭。 [预飞线包](https://github.com/swenbo1-web/human-eye/blob/107f716ffb7040230f82a36f7905122c85170947/verification/m1_region_task_brief_client_profile_recovery_001/evidence/PREFLIGHT_WIRE_REVIEW.json)

同一份历史生产记录，A 的 `full` 正文为 335,179 B。B 的显式简报与省略参数均为 7,521 B，逐字节一致，较全量少 97.76%。三份原 PNG 同序同字节，共 8,671 B。简报保留三片区域、两份局部见证、六条具名遮挡证据，在三个工具头和两个固定 CLI 阶段均保全文字与原图。公共读图按各自作用域读回两张同名 SCENE 和 LEFT。预飞守卫 10 个样本中位 1.0 µs（0.5–2.1 µs）。这些计量来自本机回放，无新增构图。

## 正式资格

| 检查 | 实际结果 |
| --- | --- |
| 两臂装配 | 两臂 Owner 和隔离实装 MCP 均启动，各登记三张原图。两侧目录差分仅为 B 新增的 218 B 条件。 |
| 真实 CLI 注册 | 仅 QA 执行。Codex CLI 0.152.1 的目录回执 23,817 B，六工具与 QA Owner 一致。thin 的 `tools/list` 线包 23,422 B，读入到刷出约 2.878 ms。 |
| 正式关闭 | QA app-server 退出码 0，读线程和监控线程已回收。该次 CLI thin 有同次 PID 和启动标识，`OpenProcess` 返回空句柄。缺 Windows 错误码、正常 EOF 和可绑定的退出码，thin 状态未确认。两臂 Owner 正常关闭，两份实装 MCP 均退出 0。 |
| 正式业务 | QB CLI 未运行。两臂正式业务、对应产品派发和辅助 P2 回放均为 0。 |

正式分母保持 **0/1**。预飞的真实业务及退出原件、正式 QA 的注册成功、正式 QA 的 thin 退出证据缺口分别记账。缺失回执无法确定原因或判断该进程是否仍存活。 [正式线包复核](https://github.com/swenbo1-web/human-eye/blob/107f716ffb7040230f82a36f7905122c85170947/verification/m1_region_task_brief_client_profile_recovery_001/evidence/FORMAL_FAILURE_REVIEW.json) · [QA 关闭回执](https://github.com/swenbo1-web/human-eye/blob/107f716ffb7040230f82a36f7905122c85170947/verification/m1_region_task_brief_client_profile_recovery_001/evidence/QA_CLI_PROCESS_CLOSE.json)

本次隔离试验收口。产品、安装、正式默认配置均无差分，Blender、模型、构图、Google、额外 API 与费用为零。提供方对目录条件的支持、模型自然采用和正式任务成本未测。[PERF050 密集盲扫](PERF050_DENSE_MICRO_SURFACE_HOLDOUT_RECOVERY_001_INDEPENDENT_REVIEW.md)的质量与 token 门限沿原判定。若后续新任务依赖真实 CLI 子进程回收证据，启动入口需持有实际子进程句柄并绑定同次启动标识，失败时保留 Windows 错误码。
