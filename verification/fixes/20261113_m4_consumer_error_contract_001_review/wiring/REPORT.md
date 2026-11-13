# 独立接线复核：cb5c33a1

结论：候选的离线接线成立，未发现需要再开一轮协议修复的实际缺口。可以进入一次新的固定六会话／三配对在线验收。当前结果证明调用路径和导出完整，尚未证明该路径在真实 CLI 中运行成功，也不是完整任务收益结论。

候选：`cb5c33a158a9dea06c8151248cc42d2b87c5697b`，作者目录 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_consumer_error_contract_001/`。

## 本轮实际验证

- 只读检查候选 `consumer.py`、`driver.py`、`CONNECTIONS.json`、`DEPENDENCIES.json` 与继承的原始执行函数；离线导入候选一次。
- 本轮 47 个身份、接线、导出和字节码断言全部通过。这是独立接线断言数，不是作者的 47 个离线案例矩阵；本轮未重跑该矩阵。
- 导入阶段阻止进程、联网和写入的 Python 审计钩子没有收到被阻止操作。未调用 matcher、archive、consume、route、batch、CLI、actor、模型或渲染器。
- 三个克隆保持原 code、defaults、closure 对象；kwdefaults 内容不变。它们使用独立 globals 字典，差异恰好为 `archive_turn`、`consumer/common_image_faults`、`run_route`，分别 1／2／1 项。递归字节码引用未发现缺失全局名。
- `run_batch → run_route → consumer.consume_turn → archive_turn → result_contract` 和 `run_route → common_image_faults → result_contract` 指针全部指向候选。
- 原模块的四个关键 globals 指针没有被替换，原 `outer_accepted`、`terminal_service_faults`、`publish_route`、`safe_environment` 对象保留。
- AST 核查原 `run_route` 使用的 consumer 成员仅为 `consume_turn`、`packer`、`safe_environment`；候选均明确导出。`packer.capture_cell`、两个入口及环境函数可调用，不存在之前漏导出 `safe_environment` 的问题。

证据为同目录 `RESULTS.json`、`INPUTS.json`、`audit_wiring.py`。三个候选源码 SHA 与登记相同：

| 文件 | SHA-256 |
| --- | --- |
| consumer.py | 34e5190d45dedd8df4b3132c14d9b202a7c4022865c7dad3c147e0333e932809 |
| driver.py | c9f8026116f06ed10e9abd4f8c44cfc7d37d0940b35554e385c0a1b961af2940 |
| result_contract.py | 5da53bbbfee51f1c07fde32ecf0e1ab1e79a73ef68feff388f709931840cd638 |

本子任务未重做父任务负责的完整冻结清单核验。作者矩阵、ZIP 校验和历史回放结论属于作者证据，不能与这里的独立断言混作同一测试分母。

## 对下一批入口的具体要求

候选故意没有在线 main，也未导出 `source_files/check_frozen/input_checks`。保留下来的旧 `source_files` 与 `check_frozen` 使用旧 HERE、旧 FROZEN，只覆盖原来 176 项来源；它们没有自动包含这三个候选源码。直接执行旧 driver main 会绕开候选。这不是本离线补丁的接线缺陷，而是下一批必须完成的最小入口工作。

建议下一批仅增加显式 launcher、新 PLAN、新运行目录和新冻结清单。launcher 自己读取计划并核对本批冻结，最后调用候选 `run_batch(plan, new_runtime_root)`。冻结清单包含候选三个源码、原 176 项依赖及实际新 launcher／plan／本地 fixture；原 actor、输入核对和发布／退出门保持原函数。

正式运行前各做一路 N/P 的零渲染 fake-CLI 接线验证，让正常绑定的 `isError` 业务回执按 `status:failed/error:null` 归一化，实际经过 consume、archive 和 outer。旧 `fake_cli.py` 在 P 组故意 kill thin，测试缺少 EXIT；不能原样将它用作新的正向 outer 验证。新 fixture 应正常 EOF，旧 fixture 和旧失败保留。此处需要新 fixture，不需要修改 bpy、核心算法、actor 或完成门。

随后一次固定原顺序 N1/P1/P2/N2/N3/P3，保持同场景、核心、提示词、模型、预算和网络完成门。没有充分理由再次运行 47 案例矩阵、旧 49 QA、换题或调整算法。正式槽位失败不补样；原批四完成／两失败以及 N3 的重连失败继续原样保留。

## 范围与状态

源码接线：通过。导出完整：通过。导入无进程／联网／写入尝试：通过。真实在线消费：未运行。新三配对收益：未运行。

Agent Learning 子会话探测返回 `context_bound:false`／`rebind_required:true`，没有获得自身句柄；未借用父任务句柄、未更新父任务状态。全部输出仅位于本授权 wiring 子目录，未改候选、旧业务源码或历史结果。
