# M1-TASK-ENTRY-001 校验去重独立复核

结论：GO，可冻结 `7411ac7aa9338f17355ffe5cdf4df113ce862aed`，本次一次优化结束。未发现实质缺陷，不建议新增代码改动或新优化轮次。收益仅为确定的适配层重复工作减少；模型收益仍由后续固定对照验证。

## 范围与证据

父版本 `b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3`。候选137源 canonical `0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a`；唯一产品改动是 `human_eye_plugin/live_spatial_mcp.py` 的 `_validate_arguments`，+6/-5行。本轮独立读取固定Git diff、源码、比较器和两版本原记录；以AST静态比较核实函数外语法树相同，使用纯JSON重算24参数案例、5整合案例以及1独立service检查的一致性。未运行产品、测试、Blender或模型；未修改作者证据/默认配置。本报告是唯一新文件。

自身AL句柄已恢复，仍为parent_read_only/旧assignment；未借根句柄或写父任务。

## 代码审查

- 显式 query 在371行首次校验并赋给局部 `selected_query`，仍先于373–374行 include_image 类型检查。坏 query 与坏 include_image 同时存在时，原 query 错误仍先发生。显式 null 是现有默认归一化，false/空数组不被误当缺省。
- 缺省 query 仅在375–376行、原 include_image 类型检查后赋值。故坏 include_image 的缺省路径不会调用 query 校验；正常 observe 路径无论是否显式 query，都在377/384/408行读取前得到字典。不存在正常JSON请求可达的未赋值读取。
- 非 observe 的短路保持：简洁relations/nearest在355–359行已返回；clearance在395–403行返回；status/arm等到408行时先判断工具名，and短路不会读 selected_query；transform跳过404–412分支继续原 action 校验。其他工具不能带query，因为原字段白名单先行拒绝。
- 后续 mode、目标互斥、session要求、alignment及task限制只复用同一次规范化结果；各条件、原错误消息及相对顺序不变。局部值不写回arguments，不带出函数，不作为trusted标记传入service。函数返回合同仍是None。
- `LiveSpatialService.observe:1046` 的独立 query 验证没有修改；新/旧两个profile的映射、默认session、采集、几何、缓存、预算、trace和发布路径均无diff。不存在新增路由层或绕过。

## 29条配对证据是否充分

本轮独立从 `compare_02/baseline/RESULTS.json` 与 `candidate/RESULTS.json` 复算，24参数案例的异常类型/消息、原输入不变及预登记调用次数全部对应；5实际service代表的输出、固定fixture、service校验/调用次数、采集次数逐字段相等。另1次直接service坏query拒绝相等，校验1次、采集0次。故应表述为29条配对结果 + 1独立service检查，每版本30项，不重复计为额外模型样本。

调用计数支持限定结论：普通显式overview/nearest/task从4次到1次；缺省query从3次到1次；surface_nearest的selector/focal两种形式从5次到1次；S两个简洁入口维持1次。早拒绝案例按其实际到达位置保留0或1次，不能说每个坏请求必定校验一次。5个service代表始终保留1次服务校验；overview为disabled路径，不能扩称完整overview几何回归。

比较器使用wraps调用原验证器和service，没有把验证结果替换为预置答案。几何代表使用既有实际采集/计算代码与有限RNA fixture，预期2米来自简单解析几何。输出只归一化本轮不同的runtime source/build和明确trace/request关联ID；最近查询在采集前用case_id固定合法document epoch，来源、revision、fingerprint等字段仍留在对比中。原始MCP输出raw_output保留，可与规范化输出分开检查。本轮没有重新执行这些作者检查。

`compare_01` 的3条聚合不等（disabled overview及两条nearest）保留为失败；`compare_02` 修正的是随机测试输入/关联ID配对，产品候选未改。复核确认首轮passed=false，不能覆盖或改写为通过。原14项回归的作者结果为14/14，本复核没有新跑这一矩阵。

这些定向证据结合此次局部控制流足以支持冻结；不构成生产安装、实际Blender、完整旧模式或模型耗时验收。后续C/S必须使用此同一候选源字节的ordinary/简洁profile，C称“大入口控制”，不与005旧安装版标签混用。不扩大测试范围来填满优化轮次。

## 摘要

- `human_eye_plugin/live_spatial_mcp.py`：`babbb88e4ee044e753798c81f78866aaa193642d7408ac4cd7c6ea7216e65928`
- `verification/m1_task_entry_001_optimize/compare_validation.py`：`4eae40867c41ab9ee87b7029c1a7d65f1f5e6ddab02ec0d69273ba0c670523d0`
- `verification/m1_task_entry_001_optimize/compare_02/EXPECTED_CASES.json`：`4bd27f2a9fca24821b7adbccbbbe9458d46104467ec4c87f927fffe0cc30e948`
- `verification/m1_task_entry_001_optimize/compare_02/RESULTS.json`：`558b9aad1e0215ce5cdedb63ab6cad7ea390c1e345e6c30b056f4bb909d19425`
- `verification/m1_task_entry_001_optimize/compare_02/baseline/RESULTS.json`：`0df7457663db8014d1deac92b886ebe3e2c7ae5088d0c05669f4fc272a998b14`
- `verification/m1_task_entry_001_optimize/compare_02/candidate/RESULTS.json`：`9e6e2e3e5e6a34235f94956ff83ddd5f10f189e8ecf8ba18d5f8f89b340db37c`
- `verification/m1_task_entry_001_optimize/compare_01/RESULTS.json`：`4051e92c30abac6d47887ad7e2ddeb72572f3c1c75df731691aea635504f652c`
- `verification/m1_task_entry_001_optimize/offline_01/RESULTS.json`：`fffb8ee59979137640d0fb2dc9dd059b01bd09bb04f6f05ce2fc6f1c2810f2ec`

首轮保留不等案例：overview_disabled, ordinary_nearest_actual, compact_nearest_actual。
