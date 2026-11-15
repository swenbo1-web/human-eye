# M6-DEGRID-004 实际修复归因报告

2026-11-16。固定基线为 `c58e464d454c83b90b3c9baa026478c590e578e6`，合同与规划预检来自 `f974cf88ecdb0ccc3677aa204d7bba02521841ec`。本批交付位于 `verification/m6_degrid_004/`，提交身份及一次完成回报收据记录在提交后生成的 `HANDOFF.json`。

## 实际结果

固定新正常目标上的两个真实消费者均未通过预登记恢复质量判据。facts 覆盖全部受损点，同时移动129个正常点，恢复幅度不足。native 的活动区域完全落在正常点，47个受损点的实际位移均为0。两路实际提交、保存、独立回读与保存版本预览均完成，技术 QA 均通过。此次两会话的结果支持继续解决活动点定位和修复幅度问题，同质量成本收益尚无通过实例。

| 最终实际结果 | facts | native |
|---|---:|---:|
| 恢复质量通过 | false | false |
| 技术 QA | pass | pass |
| 47点支持域 RMSE，mm | 1.447417498 | 1.697686172 |
| 支持域 RMSE 下降 | 14.7417513% | 0% |
| 410点观察域 RMSE，mm | 0.499908860 | 0.576753017 |
| 观察域 RMSE 下降 | 13.0286078% | −0.3403156% |
| 正常可编辑227点误改 RMS，mm | 0.132691846 | 0.063784998 |
| 实际活动点数 | 176 | 21 |
| TP / FP / FN | 47 / 129 / 0 | 0 / 21 / 47 |
| 活动点精确率 / 召回率 | 26.7045% / 100% | 0% / 0% |
| 最大实际位移，mm | 0.928201802 | 0.478171159 |

三项判据同时成立才通过，分别为支持域 RMSE 下降至少30%、观察域 RMSE 严格下降、正常可编辑227点误改 RMS 至多0.10mm。facts 对应 false / true / false，native 对应 false / false / true。所有数值来自最后保存文件的独立新进程回读。逐点证据包含实际位移及目标误差。[独立最终验证](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/FINAL_VERIFICATION.json)

## 固定构造与评分目标

源为 PAIRS001/sample_05 的指定三份 NPY，27,304个源顶点、29,073个原生多边形、53,264个派生三角形。观察域410点、编辑域274点、旧受损支持域47点。正常编辑域227点，观察域正常点363个。源点顺序、ID与域数组采用固定003字节。

使用 `np.random.default_rng(2026111604)`，按原有410源点顺序生成三轴独立 Uniform[−1/8192,+1/8192]m偏移，同一偏移同时加入正常与受损数组。完整 float64 C-array 噪声SHA256为 `cd8e84d38618d3de642a7023ea02d3244a61d3353a94582747130fd12118e5fb`。理想噪声 RMS 为0.122134318mm，最大0.202807781mm。实际保存后相对原正常模型的410点变化 RMS 为0.122135265mm，最大0.202823744mm。

先从原模型副本建立新正常模型，保存并独立 fresh readback，再从新正常副本写入固定旧47点损坏并保存、fresh readback。两状态之间原生坐标变化恰为47点。理想损坏向量最大浮点差为1.735e−18m，实际保存后的损坏向量最大差为5.0841e−8m。正常与受损请求各自保存误差最大为3.0138e−8m。评分目标逐字节等于新正常模型的实际回读 world 数组，消费者 V0、n0 与 facts 由实际受损回读重建。单次和累计位移预算均为6.8936608558mm。[构造身份](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/CASE_BINDING.json)

构造后正常与受损两状态的21项技术检查各自通过。原生拓扑、矩阵、源ID、派生三角形顺序与稳定键保持，新增退化、反转和额外接触均为0。两组前后接触比较完整完成，共四份单状态精确扫描。原模型已有退化三角形在沿用003的自适应容差下计11个，规划固定容差1e−14计10个。梯度和法向变化按观测记录。实际新正常目标通过既有提交入口完成一次控制提交、保存及独立回读，证明该目标在入口和预算下可达。[构造几何 QA](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/CONSTRUCTION_GEOMETRY_QA.json) · [真实入口控制](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/API_PREFLIGHT.json)

## 冻结旧程序迁移诊断

四条旧消费者格点定位式保持冻结参数，在新当前模型274点编辑域上均选择274点。各自 TP47、FP227、FN0，精确率17.1533%、召回率100%。定位式覆盖旧1µm三轴残差、两份X轴残差规则和旧偏移修正后的三轴残差规则。

两份旧反演程序使用当前 V、域及预算运行，`save_edit` 仅在内存捕获数组。全部程序结束并写入未评分执行记录后，评分端才读取目标。

| 冻结反演程序 | 执行结果 | 支持域 RMSE，mm | 正常227点 RMS，mm | 最大拟议位移，mm |
|---|---|---:|---:|---:|
| V1 native | 原断言失败，捕获提交0次，另评断言前中间数组 | 3.654095115 | 3.988188305 | 6.908172460 |
| V2 facts | 内存捕获1次 positions_world | 3.318207 | 4.100519 | 7.318182915 |

两份数组的三项恢复质量判据均为false，最大拟议位移均超出6.893660856mm预算。它们属于内存迁移诊断，实际保存模型提交数为0。诊断墙钟0.5324924s、CPU0.40625s，六段程序执行墙钟0.4233650s嵌套其中。固定构造只生成一份，参数和旧程序字节保持冻结。这些结果覆盖四条定位式和两份已审旧程序的迁移能力。[诊断及逐点证据](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/DIAGNOSTICS.json)

## 消费者输入、方法与访问

实际顺序为 facts→native，各一次 `gpt-6.1-sol medium`，每路12工具、600秒预算。两路取得同一正常/当前整体及局部正面、侧面、45度PNG，当前完整受损几何、410/274域、Python、编辑与V2保存版本预览。facts 另有从当前几何计算的既有focus/引用。两次之间实现、任务、图像、几何、评分与工具归档的字节身份一致。

两份任务PROMPT相同，SHA256为 `f48347ec2d0414f19f4fe81986bcc8fa81717ff51c4b96d7470827d4348c50ca`。公开数组限定16个字段，当前/初始包均为实际受损几何，SHA256为 `755a1cbba7595a1e5ab6263eebc8c8002336ba63a71d54e592a648ea06aa0e19`。公开任务和路径使用中性repair身份，完整真值、噪声、损坏标签、旧程序保留在构造/评分端。中间阶段只检查传输与退出状态，独立真值评分在两次消费者终态后执行。[冻结计划](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/PLAN_FREEZE.json) · [公开输入审计](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/CONSUMER_PUBLIC_INPUT_AUDIT.json)

facts 先检查镜像对应和拉普拉斯，再以当前V/n0进行局部二次MLS拟合。最终使用32mm邻域、排除10mm内点、法向点积大于0.55的样本，正偏移减0.1mm后截断，执行两轮邻域平滑、纵向及边界渐隐，沿当前法向移动。提交 `forearm_mls_outward_repair_v1`，模式为 `displacements_world`。它移动176点，覆盖47个受损点及129个正常点。facts 调用一次focus、零次resolve_ref。focus记录 `computed_from_current_geometry`，数值代码直接使用当前几何与n0。[facts 最终代码](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/consumers/run/repair/facts/bridge/tool_08/python/CODE.py)

native 先尝试Y=f(X,Z)四次多项式拟合，一次语法错误后修正，随后自行计算面积加权法向和局部二次MLS偏移。最终选当前输出中的24272号源点为中心，使用椭球窗口、边界渐隐和法向Y分量筛选，拟合单一幅度0.47817mm，提交 `repair_forearm_local_fill_01`，模式为 `displacements_world`。最终21点均为正常点。其局部拟合代理 RMS 约0.702→0.670mm，独立实际受损点误差保持原值。最终回答自行标记修复未完成。[native 最终代码](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/consumers/run/repair/native/bridge/tool_08/python/CODE.py)

共13次Python调用，均绑定version0。12项显式文件访问仅涉及各自payload目录，拒绝次数0。代码和路径审计未检出隐藏目标、旧程序或控制会话读取。隔离使用进程内导入/AST限制与CPython文件审计，OS沙箱认证状态未测。两路各10工具、一次提交、一次提交后的4图实际version1预览，预览后结束。PNG完整Bridge字节与CLI完成事件核对通过，CLI自身大图序列化日志存在中段截断。provider内部图像编码、注意力与真实解析设置未测。[完整会话统计](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/CONSUMER_STATS_run.json)

## 连续误差与技术质量

以下误差单位均为mm。正常点的初始目标误差均为0，最终误差同时表示正常点误改。p95按各自完整点域计算。

| 域与状态 | RMS | p95 | max |
|---|---:|---:|---:|
| 支持47，初始 | 1.697686172 | 3.396864123 | 3.871250307 |
| 支持47，facts | 1.447417498 | 2.873575781 | 2.974988695 |
| 支持47，native | 1.697686172 | 3.396864123 | 3.871250307 |
| 观察410，初始 | 0.574796893 | 1.133684151 | 3.871250307 |
| 观察410，facts | 0.499908860 | 1.046235624 | 2.974988695 |
| 观察410，native | 0.576753017 | 1.133684151 | 3.871250307 |
| 正常227，facts | 0.132691846 | 0.255195342 | 0.882814553 |
| 正常227，native | 0.063784998 | 0.072736545 | 0.478171159 |
| 正常363，facts | 0.104931010 | 0.210725623 | 0.882814553 |
| 正常363，native | 0.050440358 | 0.019658180 | 0.478171159 |

两路域外27,030点原生坐标逐位保持，源ID、矩阵、原生多边形、派生三角形顺序与稳定键保持，材质、UV及场景结构身份通过。最终payload经实际矩阵逆变换和float32保存重建，与模型实际原生坐标逐位一致。新增退化、反转均为0。接触检查覆盖至少一面关联允许域或实际变化点的全部无序三角面配对，构造允许域为410点，最终检查允许域为274点。该范围内新增额外接触及关系变化均为0，扫描完整，unresolved为0。单次与累计预算检查均通过。

| 观测项 | facts | native |
|---|---:|---:|
| 受影响三角形法向变化最大值，度 | 6.280069121 | 2.599870793 |
| 受影响三角形法向变化p95，度 | 3.342981473 | 1.286020853 |
| 关联边数 / 跨界边数 | 879 / 119 | 879 / 119 |
| 关联边位移梯度最大值 | 0.098736772 | 0.039134375 |
| 跨界边位移梯度最大值 | 0.042944962 | 0.006648400 |

两个最终独立导出的全部数组与各自消费者回读一致，14项身份检查各自通过。16个独立PNG路径包括8张共享初态图与8张最终图，相机、尺寸、原生几何哈希和PNG字节核对通过。消费者提交后的8张预览与独立最终渲染逐像素RGBA相等。[最终独立验证](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/FINAL_VERIFICATION.json) · [图像清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/VIEWABLES.json) · [8对像素核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/PREVIEW_PIXEL_VERIFICATION.json)

## 成本与失败保留

| 真实Pro观测 | facts | native | 合计 |
|---|---:|---:|---:|
| 会话墙钟，s | 137.7865701 | 132.6182316 | 270.4048017 |
| input tokens | 243150 | 228437 | 471587 |
| cached input tokens | 211200 | 179840 | 391040 |
| output tokens | 2749 | 2837 | 5586 |
| reasoning output tokens | 585 | 521 | 1106 |
| 工具数 | 10 | 10 | 20 |
| 实际PNG块 | 12 | 12 | 24 |
| PNG原始字节 | 4766633 | 4766460 | 9533093 |
| 会话监控树CPU，s | 11.609375 | 11.296875 | 22.90625 |
| 会话监控采样树RSS峰值，bytes | 688164864 | 683638784 | 688164864 |

cached input属于input子集，reasoning属于output子集。非缓存input为80,547 tokens。两次会话实际输出图像为16个初态块及8个保存版本预览块。工具公开文本合计63,850 UTF-8 bytes。一次focus公开事实6,672 bytes，Bridge墙钟0.1653322s，事实内部计算0.1557928s。Python执行13次，包含native一次语法失败，worker墙钟7.3287310s、CPU5.40625s，executor墙钟8.8584629s。快照冷创建2次、同版本缓存命中11次。相同版本的传输和计算计数保留在原始记录中。

实际Blender共20作业，5次写、8次读、7次渲染。构造4次、初态渲染2次、真实恢复控制3次、保存预览控制1次、正式编辑2次、正式回读2次、正式预览2次、独立最终读2次、独立最终渲染2次。20进程均正常退出，作业内墙钟合计27.9301596s，监控进程墙钟27.8967008s、树CPU19.734375s，最大采样树RSS450,547,712 bytes。这些作业成本嵌套在相应消费者或准备根进程内。

| 准备与交付检查 | 最终结果 | 已记录墙钟，s |
|---|---|---:|
| 固定两状态构造，含4次Bpy | 完成 | 7.5258180，监控根 |
| 初态图像与消费者输入准备 | 完成 | 4.0248922，监控根 |
| 构造几何检查 | 两状态各21项通过 | 5.4426605，监控根 |
| 数值质量预检 | 25/25 | 4.8931770，监控根 |
| 交付帮助程序静态预检 | 18/18 | 两次shell 0.1718783 / 0.1759129 |
| 真实编辑入口预检 | 19/19 | 8.5139908，监控根 |
| 消费者协议预检 | 57/57 | 最终内部11.7366348 |
| 实际案例隔离预检 | 24/24 | 最终内部2.4690024 |
| 实际版本预览控制 | 10/10 | helper内部1.7321545 |
| 最终独立读回及评分 | 两路完成 | 6.3977797，监控根 |
| 最终独立图像渲染 | 两路完成 | 3.2084535，监控根 |
| 完整会话分析 | 完成 | 0.7157450，监控根 |

初次协议夹具位置错误保留53/54结果和13.1105881s内部墙钟，修正后预检通过。首次案例预检在PLAN尚未生成时停止，0.0115198s，无Bridge消费。公开输入审计初次将私有FILE_ACCESS路径纳入公开扫描，修正扫描范围后6/6通过。诊断的错误技能路径与旧路径查找、交付帮助程序的两处只读路径查找均保留。最终分析曾误传 `--stage all`，退出2，0.5285922s；修正为run后完成。首次收集器调用的路径重复前缀导致退出2，0.0683366s，修正调用后完成。

初次COSTS快照还发现Windows复用PID34360，导致恢复控制与最终分析被互认作嵌套父子。初快照保存在 `private/accounting/COSTS_INITIAL_PID_ALIAS.json`。最终收集器要求不同根PID、树成员证据及原始stdout创建时间推导的观测生存区间包含，恢复全部根成本。补充失败与收尾观测单独保留。[完整成本](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/COSTS.json) · [补充成本及恢复记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/FINALIZATION_COST_NOTES.json)

最终COSTS记录AL注册起点至成本快照的全程墙钟。提交、清单和一次回报的后续时间记录于HANDOFF。所有嵌套计时按作用域列出，RSS使用最大值。root与子代理模型用量、费用、provider隐式请求/重试、全任务CPU与峰值RSS保留未测。两消费者Bridge终态字段 `closed=false`，CLI退出0、reader停止且safe_to_continue为true，独立CIM进程核查见PROCESS_CLEANUP。执行时冻结的session_api.py承袭003的文件末尾空行，字节身份和格式例外记录于HANDOFF。实际训练次数0、Google/API调用0、新增付费API调用0。

## 归因边界与下一改进建议

此次固定共享扰动后，四条旧定位式失去精确定位能力，两份旧反演程序迁移失败。两个新消费者都从当前局部几何估计活动区和位移。facts 的活动范围过宽并欠修复，native 把完整活动区放在正常点。当前facts能够交付结构事实和稳定引用，此例的恢复成功证据仍为空。

建议下一合同优先验证同相机正常/当前PNG差异能否绑定为可审计的候选源点集合，要求在位移计算前建立图像位置与source_id的对应证据，再评价修复幅度。该建议直接针对本次定位误差，后续实施由规划明确。

样本范围为一个固定新正常底模和两次模型会话。算法选择的随机性、focus及图像各自对方法选择的独立影响、跨资产收益、其它潜在线索仍在未测范围。最低判据通过与同质量比较需要各自的连续误差和正常点影响证据。本批保持沿用003的V2组件和冻结特征。

## 003提交模式勘误

固定003报告把V1 native实际提交写为positions。实际最终CODE和载荷元数据均为 `displacements_world`。旧CODE SHA256为 `4f78b35a0fc33c6a41b48b0c7de862afbe89807a5d3a47d172eadbe859017f07`，匹配c58固定MANIFEST。004附上旧固定报告、CODE和载荷身份依据。[勘误及旧字节证据](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/PREVIOUS_ERRATUM.md)

## 可复核产物

- [facts 实际最终模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/sessions/run_repair_facts/versions/001/model.blend) · [facts 最终回答](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/consumers/run/repair/facts/PUBLIC_FINAL.txt) · [facts 45度图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/results/run_repair_facts/after_views/forearm_45.png)
- [native 实际最终模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/sessions/run_repair_native/versions/001/model.blend) · [native 最终回答](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/consumers/run/repair/native/PUBLIC_FINAL.txt) · [native 45度图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/results/run_repair_native/after_views/forearm_45.png)
- [实际新正常模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/construction/normal.blend) · [实际受损初态](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/private/cases/repair/before.blend)
- [最终完整性核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/DELIVERY_VERIFICATION.json) · [全部本地证据SHA清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/MANIFEST.json) · [固定提交及回报收据](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004/HANDOFF.json)

Git交付根目录脚本和报告。大体积私有模型、原始会话和逐点证据保存在本地，MANIFEST逐文件记录字节数与SHA256。
