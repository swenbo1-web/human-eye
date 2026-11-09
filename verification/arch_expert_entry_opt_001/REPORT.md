# 手臂专家选择修复与静态副本优化验收

ARCH-EXPERT-ENTRY-OPT-001 修复了显式顶点超集切换到默认截面并集时错误复用旧绑定的问题，并停止在内部 analyze 路径构造无人消费的 static_patch 深拷贝。固定候选的窄 CPU 组一次通过 27/27；实际 Blender 组一次通过 19 次工具调用，包含 18 次 estimated 和 1 次正常 unknown。公共 capture 的默认隔离副本契约保持。

采用依据是正确选区和少做无用工作。单组旧新对照中 static/load 的产品方法时间各减少约 6.7–7.0 ms，repeat 略慢；这些观测不支持普遍或统计意义的端到端提速保证。本轮到此关闭入口热点，等待主线深审。

## 固定版本和范围

工作树 `C:/Users/Administrator/.codex/worktrees/2c7d/hefe`，分支 `codex/architecture-expert-entry`，从干净证据提交 `27785b3f40716b71cfbc8326590a751cccdf9138` 继续。该基线中的产品为 `c5116e30024ed12825aea6119c0f5172e6b9b46d`，旧 136 来源摘要为 `239cc00a3cf09e9c18874cf0071e811e3244695c93590f806048fab97129b3b9`。

实际 QA 前固定新产品及两份 CPU 测试文件为 `fa096c1e4172e216d567a0f8b2d13c651573284d`。新 136 来源摘要为 `46ee6672b23a9df9b2bdd13dde5edb6f2e8eb9f65aab2cc77209f8577b8ca24e`，新旧运行前后各自身份不变。两个产品文件总差异仅 6 行插入、4 行删除：

| 文件 | 当前 SHA256 | 变更 |
| --- | --- | --- |
| human_eye_plugin/blender_host.py | `4d9040d580a57bc90981de09bbaaadcd91d7343b1731aa1dd39dfbb492eab5c9` | 记录当前 bound 原请求是否省略 indices |
| human_eye_plugin/arm_twist_source.py | `5cd8f002b264e0f07753794f360e01766b77470f92ac9b6f7346613160ab2b58` | analyze 不导出静态交付副本 |

数值计算、LBS 一致性检查、拓扑路径、模型参数、训练和 M5 动作逻辑未调整。普通 task/nearest、旧 25 工具组、历史 165 方法及 M5 0/1/4 矩阵按本轮范围直接引用先前证据，未重跑，也不计入本轮分母。新增修改局限于明确专家路径；独立 AST 逆转三个副本控制编辑后，来源模块整体与基线一致。

主线新反例及任务文件的路径、SHA 和本轮范围保存在 `TASK_INPUTS.json`，任务原文保存在 `TASK_SPEC.md.txt`。主线此前 16 个行为方法的 1 个真实 P2 属于发现来源，不混入本轮 27 次执行。

## 选择语义修复

旧入口在当前请求省略 vertex_indices 时，总会删除旧 bound._selection 中的该字段再比较。若旧请求显式包含超集、当前请求仅使用同样 sections 的默认并集，这会把不同选区误判成相同：主线反例应从 402 点切换为 384 点，旧入口仍读 402 点并返回旧 selection_key。

入口现在在成功 bind 后，与该 bound 同步保存 `_arm_twist_bound_default_indices`。仅当旧绑定本来也是默认 indices 时，比较才忽略由来源层补全的索引。缺少标志时保守不复用；bind 失败不改变旧 bound 或标志。原有递归精确类型比较及来源验证器沿用，因此 bool/float 不能借 Python 等值关系跳过严格整数绑定。入口没有新增请求深拷贝、默认并集计算或验证器。

CPU 证明 402→384、384→402 两方向选区及 source key 正确，各自暖重复保持 bound/prepared、每次采集一次、静态读取和 prepare 不增长；调用者添加 indices 或修改原列表不能改写已绑定请求。实际高 ID fixture 对应 1602→1536→1602：owned 与 shared 均恢复正确原始索引及 selection_key，owned 的两种输入及返回显式输入各自暖重复也正确。

## 内部副本优化和公共契约

`BoundArmPatch.capture` 仅增加默认 True 的私有关键字参数 `_export_static_patch`，返回时的深拷贝条件增加该开关；`analyze` 调用 capture 时传 False。capture、静态核验、prepare、当前顶点/骨姿读取、LBS 回读和 source 的更新次序保持。

公共 `capture()` 默认仍在 changed 时交付独立 static_patch，暖请求仍为 None。CPU 修改返回副本的 rest、weights、骨 rest 矩阵、triangles、sections、vertex_ids 六类嵌套字段后，内部 static/prepared 及下一次结果均未污染。内部 analyze 不返回缓存引用，而是根本不构造该交付副本。

CPU 与实际旧新 first/repeat/static/load 配对均记录副本次数 `[1,0,1,1] → [0,0,0,0]`。每侧四次 capture、三次 static read、三次 prepare 保持，报告保持一致。副本计数只拦截 schema 为 arm-twist-patch-v1 的 deepcopy，notice 等必要复制不计作被删除工作。

## CPU 结果

`cpu_run_01` 一次执行 27 个不同 unittest 方法，27 通过、0 失败、0 错误、0 跳过，约 1545.9467 ms。来源前后不变，无 sys.setprofile、Blender 或网络端点执行。

| 组 | 方法数 | 覆盖 |
| --- | ---: | --- |
| 新增优化回归 | 7 | 两方向选择与暖重复、调用者隔离、公共深副本、旧新副本/工作/报告、unknown 恢复 |
| 既有相关入口 | 14 | 精确类型拒绝、单 capture、默认选择、两种编解码通道、延迟固定来源及异常恢复 |
| 既有相关来源 | 6 | 局部公共 capture、pose 复用、dirty 无静态变化、静态变化、undo/load、inflight 失败 |

新增 unknown 回归使用真实接受的来源、prepared 和专家，在 fake-bpy 的独立 LBS 输入上经过直接 service/MCP、owned 编解码/MCP、shared 编解码/owned_task 三路，共 6 次工具调用。unknown→estimated 均正常 `isError=false`、账本不变；这 6 次是上述两个 unittest 方法内部的调用，不能额外计作 6 个方法或原生 Blender 实测。

本轮 CPU 无失败尝试。执行时的四份新旧测试/runner 源、旧来源 Git 字节、产品 diff、方法集合、原始日志及两份 identity 均保留在 `cpu_run_01/`。

## 实际调用和原生对照

主线明确交付本轮 Blender 窗口后，由 QA 在固定 fa096c1e 上执行 `actual_run_01`，首轮一次完成 19 个 tools/call，无意外错误或补采样本。旧 runtime 从 27785b3 的 136 manifest 文件及 pyproject 导出到证据内独立副本，来源身份与旧版完全相同，未改当前 checkout 或新建 worktree。

同一份已有生成 fixture 的 SHA256 为 `29922da194a8a05b0399b670282e87d38db8f82007e040518e64d54f3df45cb9`；三份测试副本前后均保持。原 mesh 24,804 顶点、9,866 三角形，原局部 patch 为 1,602 顶点、3,200 三角形、25 个截面，稀疏原始 ID 为 20000+3*i。选择转换保留 24 个截面时，显式集合仍为 1,602 点，默认并集为 1,536 点。全部为生成资产，没有用户场景、训练、模型 API 或正式配置变更。

| 入口和版本 | 工具调用 | 正常报告 | 内容 |
| --- | ---: | --- | --- |
| 旧默认 owned | 4 | 4 estimated | first、repeat、static、load |
| 新默认 owned | 12 | 11 estimated、1 unknown | 同四阶段、六次选择/重复、unknown 后 load 恢复 |
| 新 shared socket | 3 | 3 estimated | 显式超集→默认并集→显式超集 |
| 合计 | 19 | 18 estimated、1 unknown | 全部 isError=false |

每个工具响应结束后，另发一次 inspect 控制请求，从当前原生 RNA 独立构造输入交给同一模型 oracle，未再调用产品 capture。18 个 estimated 合计 441 个截面的严重度、flag、截面号与原始 ID 一致，分数最大绝对差 0。unknown 的 reason 为 bone_twist_branch_unknown，regions 为空、没有 max_severity，后续 load 恢复 estimated；此实际恢复重新 prepare，不声称 prepared 保持。oracle 是同模型的来源与接线一致性对照，不评价模型准确性。

19 次 capture 和 predict_prepared 入口均各一次；只有 18 次进入严重度评分，unknown 在报告分支提前返回。静态读取、prepare 各 14 次，current_vertices 共 30,240 行，rest/weight 各 22,296 行。旧 owned 的三次 changed 各交付一个静态副本；新 owned/shared 的 15 次调用交付副本为 0。所有工具前后 opaque 账本字节不变，产品没有 setter。

## 无 profiler 的旧新成本

客户端、MCP 进程和 Blender 均断言 `sys.getprofile() is None`。产品方法时间只包围原 host 方法；完整调用时间从写入工具请求到收到完整工具响应，包含轻量计数 wrapper 和 wire 复制。大型事件 JSON、原生 packet 和 oracle 写入在随后独立 inspect 控制中完成，全部排除在这两类时间之外。控制请求及其字节、时间单独记录，不混入 19 次工具分母。

| 阶段 | 旧产品方法 ms | 新产品方法 ms | 新减旧 ms | 旧完整调用 ms | 新完整调用 ms | 新减旧 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| first | 102.6097 | 90.7759 | -11.8338 | 114.7616 | 102.1650 | -12.5966 |
| repeat | 11.8172 | 12.0602 | +0.2430 | 21.6810 | 22.1035 | +0.4225 |
| static | 48.2573 | 41.2248 | -7.0325 | 58.9208 | 51.6048 | -7.3160 |
| load | 47.8603 | 41.1324 | -6.7279 | 58.3654 | 51.8115 | -6.5539 |

每阶段仅一个旧样本和一个新样本，旧组先运行，未平衡操作系统缓存或后台调度。first 包括依赖冷装载等工作，无法把全部差值归因于副本。repeat 本来没有该副本，方法和完整调用均略慢。保留这些结果，不追加最快样本，不由旧 profiler 的 82–87 ms 残差推算复制成本，不承诺每次更快。完整 19 次成本包括 implicit_repeat 的 33.7548 ms RTT，见 [逐次成本](ACTUAL_COSTS.json) 与 [实际报告](ACTUAL_QA_REPORT.md)。

整个 QA runner 序列约 16,927.1201 ms，含旧 runtime 导出、进程启动、独立控制/oracle 和关闭，不等同于工具或产品方法耗时。BMesh 保留全 mesh C 层成本，局部行数不支持 O(selected) 总成本结论；本轮没有重新定位或修改 LBS、拓扑或模型热点，也不推导完整任务相对原生的收益目标。

## 清理和证据

旧 owned、新 owned 的 Blender PID 分别为 29420、6496，新 shared fixture 为 28636；stdio 均返回 0，shared fixture 以 controlled terminate 后 wait 关闭、返回 1。已记录的三个 Blender 进程和任务 Blender/python 命令行均无残留。stdio 客户端 PID 未单独记录，保留正常退出原件。详见 [进程身份核对](PROCESS_CLEANUP.json)。

本目录保存本轮原文/来源引用、27 方法 CPU 原件、四个实际 harness 及执行快照、导出的旧 runtime、真实传输原始字节、19 次工具及后置 oracle/control、生成 fixture 副本、前后 identity、成本和清理。`RESULTS.json` 记录汇总分母；`REVIEW.md` 保存独立只读审计。`EVIDENCE_INDEX.json` 列出除自身和 Python 缓存之外的全部文件字节数/SHA256，封存核对磁盘与 Git blob 的同字节。

本批产品及证据交付后，发送一次 ARCH-EXPERT-ENTRY-OPT-001_COMPLETE 并停止，等待主线深审。后续角色修复闭环属于另一任务。
