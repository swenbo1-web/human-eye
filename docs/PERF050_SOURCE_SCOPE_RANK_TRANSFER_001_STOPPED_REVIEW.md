# 选区排序对照首次资格独立复核

固定证据 `5a6bded884fd0869df42a18cfb6fbba5733eaa43`。首批原生资格 QN 失败，插件资格 QP 未运行，正式对照 **0/2**。46 件运行原件与索引逐件相等。唯一 Blender 进程启动后完成初末源读取并正常回收，11 对象、64 点、62 三角、原文件和副本匹配。业务、构图、模型启动均为零。

冻结资格脚本执行 `from runtime import transport` 时失败。已冻结客户端仍可从包装器的 `runtime.previous.transport.StdioClient` 取得，来源文件摘要 `cb91b9b61c7390eaab147d4460c667405fe5a9c9b26711bd7345d9f6fb32c89b`。原预检只进入了分派准备，没执行实际资格诊断。

继续读实际 QP 入口发现，诊断把 `region_ref` 读在 `task_result` 里，而当前隔离安装的选区 brief 将其放于顶层。另一个既有接线缺少转交给 `thin_stdio` 的 `error_result`，运输异常分支可能在初始化修好后再次中断。这两个问题来自源码核查，首批槽未触发。可沿用现有选区简报原图引用与同槽 `read_images` 的本机路径能力，当前候选与本题的实际回包仍待资格。

使用 [恢复计划](PERF050_SOURCE_SCOPE_RANK_TRANSFER_RECOVERY_001_PLAN.md) 重新冻结测试接线。产品、同一题面、资产、判题规则和旧记录保持。当前没有原生／插件的质量或耗时对照结果。

[初批验收报告与失败回执](https://github.com/swenbo1-web/human-eye/blob/5a6bded884fd0869df42a18cfb6fbba5733eaa43/verification/perf050_source_scope_rank_transfer_001/REPORT.md)
