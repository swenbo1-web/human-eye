# M6-IMAGE-CALIBRATION-006 交付报告

2026-11-16。固定起点 `644012279d8c0d43e2bee9d8b5d38ea30195e5da`，合同来自 `0b681d1315f99be1856835fa4336e8e852d14a2b`。本次新增目录为 `verification/m6_image_calibration_006/`。单次固定提交的完整身份和提交后回报回执见 HANDOFF。

## 实际结果

固定 005 V1 native 40 点提案的图像最优系数为 α=0.5，独立恢复验收通过。受损支持点 RMSE 下降 35.387732%，227 个可编辑正常点误改 RMS 为 0.008754382mm。固定 005 V2 facts 107 点提案选择 α=0，恢复验收失败。facts 的三个采样系数均失败，连续系数区间保持未测。

首版和优化版各构建六个真实候选。每个候选均实际保存、从磁盘重新读取并渲染三张局部图。12 份候选技术 QA 全部通过。6 组首版与优化版的完整回读数组和载荷逐位相同，21 对 RGBA 逐位相同。两阶段的整数图像目标、归一值、相机和选择完全一致。

新增 Pro 消费者、训练、付费 API、正式部署均为 0。验收入口使用实际本地协议客户端。原 005 模型自评和生成成本以历史来源记录。跨资产、新 LLM 消费和 LLM 端到端提速保持未测。

## 固定输入与图像目标

005 的两份原始载荷按原 session operation 与 manifest SHA 取字节。模型使用同一 004/005 受损初态、原生源 ID、410 个观察点、274 个允许点、相机和八张来源 PNG。源点、方向、相对位移形状及 6.893660856mm 操作/累计预算按合同固定。输入与历史共享文件的完整身份可由来源绑定核验。 [SOURCE_BINDING.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/SOURCE_BINDING.json>) [MIDPOINT_SOURCE_BINDING.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/MIDPOINT_SOURCE_BINDING.json>)

候选严格采用 `V0 + alpha * delta`，α 集合为 `{0, 0.5, 1}`。图像目标覆盖三张 640×640 局部图的全部 3,686,400 个 RGB 标量，以整数绝对误差和除以该分母获得 pooled MAE，再除以实际 α=0 的误差。选择器取技术可用候选的最小整数误差，精确平局取较小 α。四份图像结果先冻结，私有正常几何和真实损伤域随后读取并评分。 [PLAN.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/PLAN.json>) [PLAN_FREEZE.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/PLAN_FREEZE.json>)

下表中的图像值在两阶段相同。几何单位为 mm，正常误改采用可编辑正常 227 点。

|提案|α|RGB 绝对和|MAE DN|归一误差|支持 RMSE|支持下降|410 RMSE|正常 227 RMS|技术|恢复|图像选中|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
|v1_native|0|394578|0.107036132813|1.000000000000|1.697686172|0.000000%|0.574796893|0.000000000|pass|失败||
|v1_native|0.5|176239|0.047807888455|0.446651866044|1.096913539|35.387732%|0.371446430|0.008754382|pass|通过|是|
|v1_native|1|196112|0.053198784722|0.497017066334|1.574921697|7.231282%|0.533390835|0.017508763|pass|失败||
|v2_facts|0|394578|0.107036132813|1.000000000000|1.697686172|0.000000%|0.574796893|0.000000000|pass|失败|是|
|v2_facts|0.5|410903|0.111464572483|1.041373315289|1.088372090|35.890855%|0.384004941|0.145179321|pass|失败||
|v2_facts|1|503674|0.136630316840|1.276487792021|0.947751193|44.173946%|0.386841157|0.290358839|pass|失败||

各视图顺序为 front、side、45°，每视图分母为 1,228,800 个 RGB 标量。

|提案|α|front 绝对和 / MAE DN|side 绝对和 / MAE DN|45° 绝对和 / MAE DN|
|---|---:|---:|---:|---:|
|v1_native|0|173139 / 0.140900878906|115392 / 0.093906250000|106047 / 0.086301269531|
|v1_native|0.5|79705 / 0.064864095052|53991 / 0.043937988281|42543 / 0.034621582031|
|v1_native|1|81805 / 0.066573079427|54494 / 0.044347330729|59813 / 0.048675944010|
|v2_facts|0|173139 / 0.140900878906|115392 / 0.093906250000|106047 / 0.086301269531|
|v2_facts|0.5|206291 / 0.167880045573|94759 / 0.077115071615|109853 / 0.089398600260|
|v2_facts|1|276633 / 0.225124511719|102110 / 0.083097330729|124931 / 0.101669108073|

## 独立几何与保护验收

恢复判据同时要求 47 支持点 RMSE 下降至少 30%、410 观察域 RMSE 严格下降、227 可编辑正常点位移 RMS ≤0.10mm。facts α=0.5 的支持下降 35.890855%，正常 RMS 为 0.145179321mm，因此失败。facts α=1 的正常 RMS 为 0.290358839mm，仍失败。图像选择 α=0 对应初态。

下表逐域列出 RMSE / p95 / max，单位均为 mm。正常 363 与正常 227 使用对正常几何的误差，其初始误差为 0。

|提案|α|支持 47|观察 410|正常 363|正常 227|TP / FP / FN|
|---|---:|---:|---:|---:|---:|---:|
|v1_native|0|1.697686172 / 3.396864123 / 3.871250307|0.574796893 / 1.133684151 / 3.871250307|0.000000000 / 0.000000000 / 0.000000000|0.000000000 / 0.000000000 / 0.000000000|0 / 0 / 47|
|v1_native|0.5|1.096913539 / 2.070713978 / 2.370115698|0.371446430 / 0.856385012 / 2.370115698|0.006922853 / 0.000000000 / 0.128110871|0.008754382 / 0.000000000 / 0.128110871|35 / 5 / 12|
|v1_native|1|1.574921697 / 3.097683404 / 3.823707986|0.533390835 / 1.038745011 / 3.823707986|0.013845706 / 0.000000000 / 0.256221741|0.017508763 / 0.000000000 / 0.256221741|35 / 5 / 12|
|v2_facts|0|1.697686172 / 3.396864123 / 3.871250307|0.574796893 / 1.133684151 / 3.871250307|0.000000000 / 0.000000000 / 0.000000000|0.000000000 / 0.000000000 / 0.000000000|0 / 0 / 47|
|v2_facts|0.5|1.088372090 / 2.152478876 / 2.513287031|0.384004941 / 0.840656832 / 2.513287031|0.114805945 / 0.111633917 / 1.021608115|0.145179321 / 0.203303870 / 1.021608115|47 / 60 / 0|
|v2_facts|1|0.947751193 / 1.761721570 / 1.916082949|0.386841157 / 0.985673174 / 2.043230708|0.229612046 / 0.223276359 / 2.043230708|0.290358839 / 0.406611720 / 2.043230708|47 / 60 / 0|

所有候选保持源 ID、域外原生 float32 坐标、矩阵、拓扑、材质/UV 和其他对象身份。新退化、翻转、额外接触对及关系变化均为 0。每阶段两个 α=0 候选以完全相同的实际几何及三角形数组验证接触保持，每阶段四个非零候选执行精确局部接触对扫描，共 8 份。旧有 11 个退化三角形保留在来源观察中。逐点数组和完整技术记录随评分结果归档。 [CALIBRATION_SCORES_v1.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/CALIBRATION_SCORES_v1.json>) [CALIBRATION_SCORES_v2.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/CALIBRATION_SCORES_v2.json>)

过渡和侧向深度列为观测值。边界及 incident 统计均取完整冻结域。世界 X 是前视深度轴，410 域深度范围在各候选中为 92.304861173mm。下表为 incident 位移梯度 RMS / p95 / max、边界梯度 max、最大位移、支持点世界 X 误差 RMSE。

|提案|α|incident 梯度 RMS / p95 / max|边界 max|最大位移 mm|支持 X RMSE mm|
|---|---:|---:|---:|---:|---:|
|v1_native|0|0.000000000 / 0.000000000 / 0.000000000|0.000000000|0.000000000|1.418380150|
|v1_native|0.5|0.048486716 / 0.093171614 / 0.501046596|0.000215934|2.894968726|0.576960331|
|v1_native|1|0.096973428 / 0.186343206 / 1.002093192|0.000431756|5.789937451|1.268874408|
|v2_facts|0|0.000000000 / 0.000000000 / 0.000000000|0.000000000|0.000000000|1.418380150|
|v2_facts|0.5|0.025909294 / 0.068167195 / 0.131140981|0.131140981|1.658199093|0.825946214|
|v2_facts|1|0.051818512 / 0.136336841 / 0.262283298|0.262283298|3.316384641|0.365881743|

完整记录还包含 879 条 incident 边、119 条域边界边的梯度和应变分布，三轴误差/位移 RMSE、p95、max、三维 bounds 与受影响面法线角。正常最大误改虽可超过 RMS 阈值，判据仍严格采用合同固定的 RMS。

规划中点控制补齐了 22 项完整保护和接触检查，全部通过。native α=0.5 的九个回读数组与规划中点逐位相同，三张 RGBA 相同。该中点原有 3 次 Bpy 为历史共享来源，本批追加数值 QA，新增 Bpy 为 0。 [MIDPOINT_QA.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/MIDPOINT_QA.json>) [CALIBRATION_COMPARISON.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/CALIBRATION_COMPARISON.json>)

## 实际入口、状态与一次优化

实际入口为 JSON-RPC `calibrate` 与 `status`，请求绑定当前状态、固定提案、参考图像及相机身份。每阶段分别完成两次冷请求及两次身份精确匹配的复用请求，共八次实际校准客户端调用。status 与非法引用拒绝另有预检记录。operation、attempt、工作进程身份、缺失回执后的实际状态查询和重试历史均持久化。预检覆盖精确平局、技术失败、变更绑定、部分恢复、活 PID、PID 复用、读失败新 attempt 与已保存输出恢复。 [CALIBRATION_PREFLIGHT.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/CALIBRATION_PREFLIGHT.json>) [BATCH_PREFLIGHT.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/BATCH_PREFLIGHT.json>)

首版使用 18 个独占 Blender 进程，逐候选分别真实写入、独立 fresh 进程回读、渲染。首版源码、模型、图像、结果和成本完成冻结后执行一次优化。优化版为每提案一个拥有的 Blender 进程，每个候选从同一初态重载，每次写/读/渲染前均从磁盘重开实际文件，参考 RGB 按身份缓存。优化版的 fresh 回读发生在同一拥有进程内。两个实际进程各完成 3 次写、3 次读、3 次渲染，stdout 各记录启动加九次显式加载、三次实际保存。

首版 305 份成员加补充的 20 份私有评分成员 SHA 全部保持。两阶段源码档案分别为 18 和 21 个文件。数学比较 86/86 通过，新增优化运行源码为 `calibration_batch.py` 和 `batch_worker.py`。采用优化版用于本合同的冷校准，调用时显式指定 `--stage v2`。冻结的入口默认阶段仍为 v1，保留原调用兼容。 [OPTIMIZATION_PLAN.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/OPTIMIZATION_PLAN.json>) [OPTIMIZATION_RESULT.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/OPTIMIZATION_RESULT.json>)

从仓库根目录运行以下命令可走实际入口，已有相同绑定结果将复用。

```powershell
verification/m6_shape_train_001/private/venv/Scripts/python.exe -I -B -X utf8 verification/m6_image_calibration_006/protocol_client.py --stage v2 --proposal v1_native
verification/m6_shape_train_001/private/venv/Scripts/python.exe -I -B -X utf8 verification/m6_image_calibration_006/protocol_client.py --stage v2 --proposal v2_facts
```

## 成本和优化去留

以下墙钟与 tree CPU/RSS 均来自整个实际客户端及其子进程的监控。冷表示首次本批请求、候选和解码缓存为空，操作系统文件缓存状态保持未测。

|阶段|提案|冷墙钟 s|冷 tree CPU s|冷峰值 tree RSS B|复用墙钟 s|复用 tree CPU s|
|---|---|---:|---:|---:|---:|---:|
|v1|v1_native|25.458320600|22.609375|610369536|0.424926700|0.281250|
|v1|v2_facts|25.500839600|23.015625|615383040|0.423766200|0.281250|
|v2|v1_native|16.253904300|16.093750|646692864|0.656615600|0.468750|
|v2|v2_facts|16.010848200|16.312500|648314880|0.660931000|0.468750|

两份提案冷墙钟合计 50.959160200→32.264752500s，下降 36.685078%。tree CPU 合计 45.625000→32.406250s。冷峰值 tree RSS 615383040→648314880B，增加 5.351438%。复用墙钟合计 0.848692900→1.317546600s，增加 55.244211%，绝对增加 0.468853700s。四次复用请求均新增 Bpy 0。

首版解码 36 张 RGB，44,236,800B，命中 0。优化版冷解码 24 张，29,491,200B，缓存命中 12，每请求 RGB 缓存峰值 14,745,600B。解码墙钟合计约 14.355948→9.629810s。当前两阶段共 20 个新增 Bpy 进程、36 次逻辑写/读/渲染操作。Bpy 进程墙钟合计 36.126510100s，tree CPU 27.625s，峰值 tree RSS 529,330,176B。两个批进程墙钟 11.3244208s，其 18 步墙钟 9.1423098s，层级计时均保留原作用域。

历史两份所选提案的生成墙钟分别约 140.924419s 和 150.432775s，合计 291.357194s，归属 005 共享来源。本批未新增模型消费者。COSTS 保留原 usage 来源身份、所有进程/作业/客户端回执、解码与评分成本。进程、步骤、任务和客户端时间存在嵌套，完整资源累计按进程只计一次。全任务 CPU/RSS、根及协作模型 usage、供应商费用保持 unknown。 [COSTS.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/COSTS.json>)

首次 freeze_v1 因绑定相对路径按仓库工作目录解析而失败，发生在冻结输出和 Bpy 执行之前。路径改为相对本批目录后重试成功，失败与重试日志保留。三次纯 mock 预检均成功，全部实际 Bpy 成功。最终只读审阅附加猜读 `PROTOCOL_PREFLIGHT.json` 时有一次路径错误，随后核对实际协议记录成功。独立只读审计 shell 墙钟另列，CPU/RSS 未采。提交、回报和状态交付尾部成本记录于 HANDOFF。 [FINALIZATION_COST_NOTES.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/FINALIZATION_COST_NOTES.json>)

## 交付与边界

图像度量预检 21/21、协议/状态预检 27/27、批处理预检 30/30、各阶段私有评分完整性 20/20、阶段比较 86/86。最终交付核验 875/875 通过，覆盖输入和源码身份、12 份候选实际写/读/渲染、四份图像先冻结、真实协议入口与进程清理结果。 [DELIVERY_VERIFICATION.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/DELIVERY_VERIFICATION.json>)

本次结果范围为一个开发资产、两份固定历史提案和三个固定系数。候选系数集合 {0, 0.5, 1} 由合同预先固定，规划中点为既有开发可行性信息。facts 的失败结论覆盖本次三个采样值。新资产、新提案、连续幅度和新 LLM 消费保持未运行。

完整本批本地证据由 MANIFEST 清点，旧 005 与规划中点大数据按来源身份引用。MANIFEST 排除自身和提交后 HANDOFF。Git 提交包含本批根层公开源码、计划与结果，小型固定来源文件和全部实际执行证据在本地清单中核验。源码 `session_api.py` 的继承 EOF 空行按执行冻结字节保留。 [MANIFEST.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/MANIFEST.json>) [HANDOFF.json](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/HANDOFF.json>)

下一建议是在新资产和新提案上复用同一有限反馈组件，检验图像选择与独立恢复判据的一致性。

### 选中工件

- v1_native α=0.5，[实际模型](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v1_native_a05/versions/001/model.blend>)，[磁盘回读](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v1_native_a05/batch_attempts/read00/readback.npz>)，[current_forearm_front](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v1_native_a05/batch_attempts/render00/images/forearm_front.png>)、[current_forearm_side](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v1_native_a05/batch_attempts/render00/images/forearm_side.png>)、[current_forearm_45](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v1_native_a05/batch_attempts/render00/images/forearm_45.png>)
- v2_facts α=0，[实际模型](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v2_facts_a0/versions/001/model.blend>)，[磁盘回读](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v2_facts_a0/batch_attempts/read00/readback.npz>)，[current_forearm_front](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v2_facts_a0/batch_attempts/render00/images/forearm_front.png>)、[current_forearm_side](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v2_facts_a0/batch_attempts/render00/images/forearm_side.png>)、[current_forearm_45](<C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_image_calibration_006/private/sessions/v2_v2_facts_a0/batch_attempts/render00/images/forearm_45.png>)
