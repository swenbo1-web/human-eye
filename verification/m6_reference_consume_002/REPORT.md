# M6-REFERENCE-CONSUME-002

2026-11-16，Asia/Shanghai。合同固定于 `7dbcc26e0cdc0bbe8ae984f9d56f00e43300d93d`，实施起点为 `9a759efd7d4acdbc7917fad709d350bd86b33ae2`。本批在独立目录内完成真实带图消费、编辑链路预检、保存副本回读及一次优化实验。

## 实际结果

四个实际 `gpt-6.1-sol / medium` 会话全部完成。首轮依次为 native、facts，第二轮依次为 facts、native。每次实际工具交付相同九张 PNG，包含完整原画、模型整体正面、前臂正面/侧面/45度及两套既有标注，共36个完整服务端 ImageContent 块、15,365,788 PNG字节。每个会话都给出了部位判断、两种腕点层位、轴线与宽度分析、局部方向建议和具体保留理由，并调用新 Blender 进程读取自己的隔离模型副本。

四次决策均为 `no_edit`，版本均为0，变动点均为0。技术保持检查通过，双定义的几何改善均未成立，艺术质量尚无用户验收。模型之间一致意见没有艺术正确率分母。额外API隔离预检完成过一次约 `1e-6 m` 的真实稀疏位移、保存和独立回读，该操作单列于预检。

| 实际顺序 | 会话 | wall秒 | 输入token | 其中缓存token | 输出token | 其中reasoning | 工具 | 图像 | 决策/独立读回 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | v1 native | 98.6787483 | 109971 | 80768 | 2901 | 91 | 4 | 9 | no_edit / 完成 |
| 2 | v1 facts | 80.0246867 | 122607 | 87808 | 2419 | 118 | 4 | 9 | no_edit / 完成 |
| 3 | v2 facts | 93.3875258 | 153393 | 118016 | 2720 | 62 | 5 | 9 | no_edit / 完成 |
| 4 | v2 native | 106.2548542 | 138899 | 108416 | 3370 | 155 | 5 | 9 | no_edit / 完成 |
| 合计 | 4个完成 | 378.3458150 | 524870 | 395008 | 11410 | 426 | 18 | 36 | 4个保留副本 |

完整回答、工具顺序、实际图片身份和保存文件引用均保留。输入缓存token属于输入token子项，reasoning属于输出token子项。提供方收费未测。[完整消费汇总](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/CONSUMER_STATS_all.json)

## 两路共享条件与真实判断

两路从同一原模型的独立副本开始，获得相同完整几何、九图、任务、两套对应、Python计算及提交/回读能力。facts额外获得focus、稳定引用、引擎截面和投影事实，native可以自行计算同类量。599点为选区，端点保护252点，实际可编辑347点，全模型其余26957点受保护。消费者可自行选择活动段和过渡，单步及累计位移上限均为 `0.0008492444888147518 m`。该预算和输入在首个消费者前冻结。[冻结计划](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/PLAN.json)

四次消费者都采用现成B对应评价前臂轴段收束，同时保留A作敏感性结果。A的腕点靠腕部凸起和掌入口，B的腕点位于更近端的窄轴段。两者EW长度和方向不同，同一百分比对应的实际截面也不同。消费者使用整体图定位画面右侧、模型正Y侧前臂，并结合正面、侧面、45度图描述近端体积与远端连续收束。

保留理由在四次回答中可以逐项核查。B在55%和75%处的宽度残差仅为 `+0.000931` 和 `+0.000074 EW`，而两侧轮廓同时偏移，中心线残差为 `+0.016708` 和 `+0.007387 EW`。A的两侧残差同时为负，外侧五站均不足。B近端宽度相对参考多4.63%和2.43%，中远端已经接近或偏窄。模型侧面及45度图呈连续收束，现有原画只提供正面外观。消费者据此保留当前体积，并把潜在调整定位于B约15%至35%的近中段外侧轴段，提出向轴线内收且在可编辑域内平滑衰减的条件性建议。

本批控制器允许实际消费和可编辑域选择。原画/模型对应的不确定性进入四个消费者的判断。首版事实引用曾超出50000字符公开限额，接线阶段将可选法向/面积转为带完整SHA和dtype/shape的只读NPZ描述，实际引用从95118降至43456字符。源ID与精确世界坐标仍内联，完整原始事实保留。该修复在首版冻结前完成。[事实交付预检](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/FACTS_DELIVERY_PREFLIGHT.json)

## 双定义固定评价

下表为实际保存文件相对参考的残差，按各自EW长度归一化，内侧为有符号横向位置，外侧为正向位置，宽度为外侧减内侧，中心线为两侧均值。四个正式副本的before与实际读回一致，所有改善量为0。完整参考值、before、after和源三角引用均在消费汇总及各 `QUALITY.json` 中。

| A站位 | 内侧残差 | 外侧残差 | 宽度残差 | 中心线残差 |
|---|---:|---:|---:|---:|
| 15% | -0.021405 | -0.009558 | +0.011847 | -0.015481 |
| 35% | -0.018725 | -0.017687 | +0.001038 | -0.018206 |
| 55% | -0.006514 | -0.011108 | -0.004594 | -0.008811 |
| 75% | -0.007631 | -0.014035 | -0.006405 | -0.010833 |
| 90% | -0.000722 | -0.011364 | -0.010642 | -0.006043 |
| MAE | 0.010999 | 0.012750 | 0.006905 | 0.011875 |
| 最大绝对误差 | 0.021405 | 0.017687 | 0.011847 | 0.018206 |

| B站位 | 内侧残差 | 外侧残差 | 宽度残差 | 中心线残差 |
|---|---:|---:|---:|---:|
| 15% | +0.009305 | +0.029051 | +0.019746 | +0.019178 |
| 35% | +0.005140 | +0.015219 | +0.010079 | +0.010179 |
| 55% | +0.016242 | +0.017173 | +0.000931 | +0.016708 |
| 75% | +0.007350 | +0.007423 | +0.000074 | +0.007387 |
| 90% | +0.007982 | +0.003382 | -0.004599 | +0.005682 |
| MAE | 0.009204 | 0.014450 | 0.007086 | 0.011827 |
| 最大绝对误差 | 0.016242 | 0.029051 | 0.019746 | 0.019178 |

EW相对图像向下的轴线角度，A参考/模型为14.420773°/13.715903°，B为15.600838°/16.720019°。已有参考边缘3像素不确定度分别相当于A的0.016603 EW、B的0.018763 EW，有限锚点敏感性结果保留。两套定义均属于任务约定，解剖真值和姿态误差仍待独立判断。

## 保存回读与可视材料

四个消费者各完成一次真实新进程读回。随后另用四个全新 Blender 进程再次读取实际文件，80/80项文件与数值核验通过。额外复核复用了同一评价器，数值内核的独立实现未运行。544/544项结构化回答数值与实际测量一致，8张双定义叠图及固定五站通过211项来源核验。最终冻结、原件、默认源码和语法身份核验见 `FINAL_VERIFICATION.json`。

四个正式会话的实际读回原生float32坐标、矩阵及派生三角数组逐位一致，变动点为0。新增自交依据几何身份一致判定，正式会话精确相交扫描次数为0。预检中的精确扫描单列。本批质量阈值下原模型已有11个退化三角，新增退化和翻转均为0，可编辑域关联的744个三角的法向变化为0。

结果共32张before/after PNG和8个局部OBJ，其中16张after视图由四次真实Bpy渲染生成。before复用前已核对模型、相机、渲染脚本身份，16对RGBA像素逐位相等。显示的几何和位移倍率均为1.0。8张轮廓叠图另有8张逐字节相同的盲化副本，路径和随机映射分别保留。没有采集用户或第三方盲评评分。[结果索引](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/VIEWABLES.json) · [独立回读核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/RESULT_VERIFICATION_all.json) · [双定义叠图索引](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/CONTOUR_OVERLAYS.json)

可直接查看一组实际保存模型的正面、侧面、45度及A/B轮廓叠图。[正面](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/private/results/v2_forearm_facts/render_v2/after_views/forearm_front.png) · [侧面](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/private/results/v2_forearm_facts/render_v2/after_views/forearm_side.png) · [45度](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/private/results/v2_forearm_facts/render_v2/after_views/forearm_45.png) · [A叠图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/private/contour_blind/pair_01_A.png) · [B叠图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/private/contour_blind/pair_01_B.png)

## 一次优化与最终选择

首版两次真实读回的重复before/after表占公开工具文本50.11%。`OPTIMIZATION_BINDING.json` 绑定了首版实际回答、会话状态、汇总和工具源码SHA。唯一变更为共享 `session_api.short_quality` 在零变化且双表精确相等时保留完整after表并添加 `before_equals_after=true`，非零变化、未知或不等表沿用完整首版回复。完整原始QUALITY及检查不变，55项预检通过。两轮prompt、图像、资产、可编辑域、模型和预算身份相同。

| 两会话阶段比较 | v1 | v2 | 变化 |
|---|---:|---:|---:|
| 实际读回文本字节 | 46547 | 29877 | -16670，-35.81% |
| 全部公开工具文本字节 | 92881 | 81386 | -11495，-12.38% |
| Pro wall秒 | 178.703435 | 199.642380 | +20.938945，+11.72% |
| 输入token | 232578 | 292292 | +25.67% |
| 输出token | 5320 | 6090 | +14.47% |
| 工具次数 | 8 | 10 | +2 |
| 正式形变/成立的改善 | 0 / 0 | 0 / 0 | 0 |

第二阶段额外Python调用均发生在最后读回回复之前，归因需保留该时序。单任务、四会话、相反路线顺序及缓存差异限制了因果判断和泛化。组件文本节省成立，整体净收益未建立。

按合同保留首版默认API。当前 `session_api.py` SHA为 `74bd32bdc352cbd47909bc420fb0477da19a137c9afe17ab63b9b23872636785`，与真实执行V1归档逐字节一致。V2源码和候选补丁均保留。`RESULT_VERIFICATION_all.json` 的V2 `current_exact` 字段属于恢复前历史快照，恢复后当前身份由 `API_SELECTION.json`、`FINAL_VERIFICATION.json` 和最终manifest核验。[最终选择](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/API_SELECTION.json) · [候选补丁](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/OPTIMIZATION_DIFF.patch)

## 预检恢复及成本口径

真实API首次预检把图片前的元数据块误作图片，0.240972秒、tree CPU0.15625秒、Bpy0，退出1。第二次完成5次真实Bpy操作后，报告序列化遇到NumPy bool，13.766006秒、tree CPU12.546875秒、退出1。两份失败回执保留。随后只读恢复重新核对已保存输出并验证协议，1.108379秒、parent CPU0.59375秒、额外Bpy0。最终API预检25/25通过。`API_PREFLIGHT_PROCESS.json` 保留第二次原始失败状态，`API_PREFLIGHT.json` 记录恢复后通过。

本地消费者协议预检两次各22/22通过，外层shell合计3.972564秒。评价预检21/21，3.898721秒。事实交付12/12，0.453841秒。事实描述符6/6，0.184243秒。优化55/55，0.045346秒。补充分析首次字段名错误退出1、0.197571秒，修正后通过。终检审核另一次像素复算因所选数值环境缺少PIL，在计算前退出1、0.164726秒，审核者消息与已完成的16对像素核验回执均保留。上述支持检查实际Pro和Bpy新增均为0。准备、图像裁切、像素核验、分析、叠图及恢复的已测body时间和来源身份在成本账本逐项保留。[API预检](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/API_PREFLIGHT.json) · [全部成本](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/COSTS.json)

| 实际Bpy类别 | 次数 | 作业wall秒 | tree CPU秒 | 最大采样tree RSS字节 |
|---|---:|---:|---:|---:|
| API隔离预检 | 5 | 5.5197448 | 4.109375 | 278982656 |
| 消费者真实读回 | 4 | 4.2816517 | 3.375000 | 260194304 |
| 独立再读 | 4 | 4.0911316 | 3.421875 | 260993024 |
| 实际结果渲染 | 4 | 6.0917899 | 4.906250 | 444862464 |
| 合计/最大 | 17 | 19.9843180 | 15.812500 | 444862464 |

17个Bpy均退出0，包括1次预检编辑、12次读取和4次渲染。另两个预留目录没有执行记录。Bpy单线程，最大观测工作集约424.25 MiB。四个Bridge self CPU共3.90625秒，self RSS最大125026304字节。六个Python worker self CPU共0.5625秒，execution wall共1.051750秒，self RSS最大43151360字节。

四会话公开工具文本共174267 UTF8字节，完整工具文本174427字节，含图片base64的stdio回复共20677300字节，PNG原始字节和base64字节分列。数值packet创建/命中、NPZ读写和JSON处理按会话记录。会话、工具、Bridge、worker、snapshot和Bpy计时互相嵌套，外层预检及独立核验tree CPU已包含对应Bpy，成本账本保留包含关系。V2渲染与独立核验并行，wall均为非独占。不同嵌套范围没有合并为单一CPU或wall总量。

`COSTS.json` 记录从AL任务登记到最终成本快照的端到端墙钟，包含准备、代码编写、四会话、复核与等待，提交和完成回调发生于该快照之后。CLI整树及全任务CPU/RSS、部分写代码/检查shell的独立耗时、主Agent/协作模型token与费用均未测。Bridge指标截至末次工具序列化前，worker指标截至写结果前，退出尾部未捕获。50ms进程树采样可能遗漏极短后代。费用、提供方内部请求数、重试、resolved模型设置和内部图像编码/分辨率均未测。

四个Bridge原始 `closed=false` 保留，缺少退出后的closed=true遥测回执。四个CLI均退出0，父进程已回收、读取线程停止。独立CIM快照确认8个所属consumer/bridge PID及带本批路径的Python/Blender/Codex进程均已消失。CLI日志将图片结果序列化并在1 MiB中间截断，完整图片分母来自Bridge逐块SHA核对加实际已完成images调用事件。完整服务端回复和截断日志均保留。[最终来源核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/FINAL_VERIFICATION.json)

## 交付及后续建议

原模型和原画仍分别位于下列路径，SHA核验通过。训练次数0，Google/API调用0。本批新增目录内包含所有实施变更。大体积blend、NPZ、PNG、原始消费者/完整RPC记录保留于本地private，公开Git提交包含根目录脚本与交付摘要，MANIFEST逐文件记录全部本地证据。提交后的忽略文件HANDOFF绑定固定提交及一次完成回报回执。

- 原模型 `D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend`，SHA `614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d`
- 原画 `D:/Projects/fps/outputs/character-design/Yanyite/Yanyite_Front_v1.png`，SHA `5a261d83fee2c4a49dc59f6d1fb1ba5090b91ad301902986d089541d103caba6`
- 四份实际模型 `private/sessions/{v1_forearm_native,v1_forearm_facts,v2_forearm_facts,v2_forearm_native}/before.blend`
- 原始回答 `private/consumers/{v1,v2}/forearm/{native,facts}/PUBLIC_FINAL.txt`，同目录保留实际事件、usage、PROMPT及Bridge完整回复
- 本批根目录 `C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_reference_consume_002/`

后续建议聚焦同姿态/同相机比较下，现成B近端两站的宽度超量能否持续成立，同时保留A敏感性、内侧和深度检查。本批真实图像、事实与保存回读链路已可供独立复核，现有数据能够支持上述比较的准备。新增人工锚点或用户手工点选没有列为继续研究的前提。按合同一次回报后结束本批，由规划独立复核并下达下一份明确任务。
