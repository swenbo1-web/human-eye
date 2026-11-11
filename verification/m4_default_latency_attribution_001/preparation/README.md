# 固定默认请求的时延归因准备

本批复用 B=e077 和 C=a81 的既有隔离安装。`verify_inputs.py` 只读取安装源、原始复制源、封存 wheel、入口、绑定和共同 Python 文件，重新核对两套 137 源及 canonical。准备读盘记录保存在 `INPUT_VERIFICATION_01.json`。

`INPUT_BINDINGS.json` 绑定本批入口与 QA 源、既有 Peer 和 Windows PID 证明函数。入口直接读取根制定的 `SCHEDULE.json` 和 `WORK_ORDER.json`。冻结提交由根协调者在静态单元通过后提供。

```text
python -I -B -X utf8 entry/run_entry.py --output run_01 --frozen-commit FULL_COMMIT_SHA
```

四会话按 B、C、C、B 串行执行。每会话 22 个业务请求和一个普通 close，worker 序号分别为 1..22 和 23。元数据固定为 initialize、initialized notification、tools/list、ping，共四条 stdio 消息和三份响应，实际宿主 RPC 为零。每个业务调用返回后立即核对 worker 序号、profile 状态、恢复、事实、来源、代际、缓存和工作计数，然后才进入下一调用。首次启动预约开启矩阵，最多四次预约，停止后保留未运行尾项。

ON 使用原计数 callback 的成功路径，并记录 callback 异常。OFF 构造同样的状态与 callback 闭包，Python/C callback 计数为 null 和 not_collected。初始 profile 非空时保留它并停止。结束时仅恢复仍由本次安装的 callback，观察到 foreign callback、callback 消失或恢复错误时记录并停止。contextmanager 覆盖 before、业务和 after 的异常路径，worker 原有 finally 保存事件。

本批 before_probe_elapsed_ns 包含 before 采样和 ON 安装检查。after_probe_elapsed_ns 包含恢复检查与 after 采样。profile_scope_ns 从状态构造开始，覆盖 before 采样、业务和恢复观察，与两个 probe 区间交叠。这套边界按本批固定解释。ON/OFF 的差异同时包含 profiler 状态、计数和自然事件记录路径。

entry_elapsed_ns 保留 Peer 调用的外层区间，stdio.elapsed_ns 继续保存原 Peer 的嵌套区间。随后的即时核验、等待 trace 发布和文件读取计入 verification_elapsed_ns，request_with_checks_ns 覆盖调用及核验。session_wall_ns 包含启动、四条元数据、PID 证明、全部业务、验证和清理。timing_stages_ns 保留各阶段及重叠的验证合计，阶段与父区间按原范围解释。

产品 actual PID 从既有 startup trace 获取，元数据之后通过原 Windows helper 持有其句柄，退出后使用同句柄核对退出与 exit0。该检查加入 setup/cleanup 时间。Blender READY 继续绑定其拥有的 Popen PID。正常 close 要求 closed 响应、exit0、未 poison 的 WORKER_CLOSED 和完整原件。退出证明异常仍进入 NativeSession 清理。

宿主 residency、实际 scene.hash 成功次数、task_work 和 cache flags 在两种模式均保留。callback 的 Python/C 计数仅 ON 采集，既有 bpy C 方法可观测性边界随原件报告。inclusive spans 和 profile_scope 依其重叠范围保存。

本准备阶段的 static compile、单元和文件核对记录由根汇总后冻结。四会话仅在根提交完整合同、源码及通过记录后启动。
