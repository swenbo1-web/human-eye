# M1-TASK-ENTRY-001 独立质量与测试复核

复核者：`/root/scale_diag_quality_review`。日期：2026-11-10。
固定候选：`b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3`。
候选工作树：`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`。
候选产品：137份源码，canonical `347ec4e52b24ff77239c5540caac52cdc6031e3542c0359798f821538ef4e3ea`。

**结论：本轮质量范围内未发现阻断或实质语义差异，可进入根已确定的一次重复校验精简。本结论不是模型收益、安装或发布验收。**

本文归档已经完成的只读复核。归档时未再追加检查。本子审没有运行 Blender、模型、产品、作者测试运行器或几何求解器，没有修改产品、作者证据或正式配置。实际操作是读取源码、原始JSON及测试日志，以标准库解析、哈希和Decimal算术核对已有记录。根另行报告其固定副本14/14回放通过；这项执行不记成本子审的独立运行。

## 1. 源码与离线测试

审阅产品diff：新增 `human_eye_surface_nearest` 的target-only目录、参数映射、observe trace归类及目录模式隔离；`production_server.py` 改动是模式帮助文字。没有在该diff中发现求解算法、预算或结果筛选规则变化。

已读 [定向测试](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001/tests/test_task_entry.py)、[离线运行器](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001/run_offline.py) 及其直接使用的有限宿主fixture。14项测试不只是检查函数名称或mock最终答案：

- 最小name/id参数确实映射到原 `surface_nearest`，保持一次observe调用、默认session和无图设置。
- 新旧nearest事实除顶层trace以外逐字段相等；完整、partial及unknown由实际采集/几何路径产生。
- partial/unknown反例向有限RNA fixture加入触发既有精确计算位宽预算的几何，实际内核返回 `surface_exact_bit_budget`；不是直接伪造最终状态。但这仍是离线fixture，不是真实Blender异常资产回归。
- 缺失和歧义名称在网格展开前拒绝；显式ID可消除名称歧义。relations保留歧义行、缺失目标、有效候选及不完整集合。
- 检查来源拒绝、采集绑定损坏、revision/epoch/instance/selection变化，以及几何实际改变后的距离更新。
- 原动作账本不进入观察链；检查原期限延续至编码阶段、非法参数后后续调用和ping继续处理。

作者 `offline_03` 日志是14运行、14通过、0跳过；本子审未将读取日志冒称重新执行。实际核对 `offline_02/EXECUTION_IDENTITY.json` 与 `offline_03/EXECUTION_IDENTITY.json` 的137项manifest，均与本次候选文件哈希吻合。两次runner摘要一致，产品字节未因测试预期修正而改变。

### 早期失败的解释和限制

[offline_01/BOOTSTRAP_FAILURE.txt](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001/offline_01/BOOTSTRAP_FAILURE.txt) 仅保存失败说明：原guard拒绝仓库根下预加载的 `__main__`，随后改用隔离产品源目录。它不是完整的原始异常/执行身份记录，本子审不据此重建该次执行或宣称独立复现。

[offline_02/RESULTS.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001/offline_02/RESULTS.json) 保留11通过、2失败、1错误。三项修正与已存在的合同一致：

1. trace中的 `session_id` 属于correlation，而非annotations；依据 `telemetry.py` 的 `_CORRELATIONS` 和分类写入逻辑。
2. 原期限耗尽返回 `expired`，并非泛化的 `error`；依据 `RequestBudgetError` 和MCP错误字段合并逻辑。
3. 缺失目标、无可用事实时为 `unknown`；歧义候选与有效候选并存才为 `partial`。原task-set状态逻辑如此。

[BASELINE_CONTRACTS.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001/BASELINE_CONTRACTS.json) 给出原合同位置；本子审也读取相应源码。早期失败记录未被最终14/14覆盖或删除。offline02旧测试只保存其哈希、执行身份和失败trace，不能把这些资料当作旧测试全文的独立逐行diff。

## 2. 两个真实Blender案例：独立原件核对

证据目录：[blender_equivalence_01](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001/blender_equivalence_01)。

本子审直接解析每场景的 `ordinary_RESPONSE.json`、`S_RESPONSE.json` 与对应FACT，确认FACT等于真实RPC text内容，且两边 `isError=false`。逐场景的两个 `host_rpc/*_RESPONSE.json` 内完整response精确相同，而不仅仅是作者提取的binding摘要相同。

### 装配：独立重建，未使用产品投影作为答案

作者运行器在第569–570行使用产品 `_project_spatial_relations` 生成普通输出的比较形态。这个比较能证明两入口沿用同一投影，但单独不能排除投影函数共同丢字段。本子审因此未执行该函数，而直接从已保存S结果重建普通结果的语义字段。

具体完成60组值/字段树断言；其中一次断言可包含整个嵌套事实树，不将其宣传为60个独立样本：

- `result_kind`、status、coverage及execution_authority；scope、unit、coordinate_frame、pair_order。
- 普通binding中所有非对象/宿主字段，包括source、source status/check scope、disk status、currentness、capture scope、scene revision/fingerprint、runtime source和数量。
- 四个对象行的name/object_id和AABB；把S行上的instance_id还原为原host_identity.object_instances，恢复共享capture_scope并比较其余宿主身份。
- 三个candidate的索引及object_id；将 `measurement_contracts` 与每行三类事实合并，完整比较closed_solid_relation、surface_proximity、separation_gap，包含内部见证/状态/方法字段。
- 将集合中的candidate_indices映射回真实object_id，比较完整穿插集合、已知穿插集合、最近分离集合、best-known集合、距离及未决项。

这些检查全部相符。S新增的schema名称及identity/certificate scope说明另行识别；顶层trace属于请求关联差异。没有在trace以外采用递归删字段或宽泛忽略规则掩盖数值、来源或状态差异。

使用原 [003 TRUTH.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_003/private/TRUTH.json) 重算已有输出：Object_02分离、Object_03穿插、Object_04分离；穿插项的分离间隙保持not_applicable/null。两条距离按 `abs(actual-ideal)+原距离误差界` 计算：

| 对象 | 原始输出距离（米） | 含原误差界的最大误差（米） |
|---|---:|---:|
| Object_02 | 0.010000049869218474 | 2.5433528473175212e-7 |
| Object_04 | 0.039999960660935814 | 3.4076239824958355e-7 |

均小于1e-6米。Decimal重算显示位数与作者binary64加减结果的末尾差异属于计算表示差异，不影响既定阈值。

完整初末快照与 [author_mesh_snapshots.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_003/private/author_mesh_snapshots.json) 中initial精确匹配：四个对象全部局部顶点、世界矩阵、带方向三角面及单位均核对。

### D48：完整事实只差顶层trace

直接比较普通与S的全部解析字段，仅删除顶层 `trace_id` 后精确相等，没有产品投影或其他字段忽略。

结果为Target的最近对象Peer_000，距离 `0.0030000059049562493 m`；coverage为47个target-excluding候选、47个有效距离、0严格排除、0未决。

以既有独立 [ORACLE.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/scale_diag_001/ORACLE.json) 的外向区间 `[0.0030000059049561864, 0.0030000059049562497]` 核对，最大端点误差为 `6.29e-17 m`。没有使用历史半宽字段，也没有运行生产算法生成答案。

完整初末快照与 [D48.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/scale_diag_001/fixtures/D48.json) 的48对象局部顶点、世界矩阵、三角面及单位精确匹配。

### 原始事实摘要

| 原件（相对上述blender_equivalence_01） | SHA256 |
|---|---|
| assembly/ordinary_FACT.json | b1e088d31e1ef81164c6720e22e104a023e6bb0058c709e400feb4a8c929af20 |
| assembly/S_FACT.json | ce40eccd64b06193f4cd3c3afd4a8cdcf5d70ba8562dc1b6df30802d3665dfb3 |
| D48/ordinary_FACT.json | 2a61ae4750a24e54f3d88bdbfcc9c92bf03208577bfc381e09f3689c23bb5834 |
| D48/S_FACT.json | 6471b3af312d47743bd8b2a813d103cefcb8f967e097cba54309644bce82907e |

## 3. 未测和结论边界

- 两个真实Blender案例都是成功路径；partial、unknown、歧义和失效路径主要由离线fixture验证。场景RESULT中的 `unknown_and_partial_fields_preserved=true` 不能解释为两个真实场景实际执行了这些异常状态。
- 初末几何相同本身不能证明任意瞬态写入不存在。本轮结合固定只读采集命令、源码与RPC路径判断，不把清理收据单独当作连续只读证明。
- 未在本子审重新运行14项测试；根报告的独立14/14另列。未重跑历史193项矩阵、真实Blender或模型。
- 此次未验收隔离安装、真实CLI启动、其他agent适配、图像入口、未知目标发现、旧AB001完整观察/严格引用任务或任意复杂资产。
- 尚未证明模型自然选用入口、首次调用成功率、直接消费、减少重复求解或完整时间/token净收益。原有失败与未测保持原样。
- 子代理当前Agent Learning assignment仍指向旧任务且current=false；未借根句柄、未覆盖父任务。归档依据根明确的本轮只读复核及报告写入委派，不将旧assignment冒称当前完成回执。

## 4. 唯一质量建议

后续等价检查保留独立字段重建，不仅以产品自身投影函数生成期望。当前实际输出已由本子审补查相符，因此这不是要求新增Blender运行的阻断项。

质量侧不另开性能优化。按根已选定的同次重复 `validate_query` 精简继续，保留service独立校验；下一候选应沿原语义与既定验收边界复查，不扩大本批范围。
