# M6-MATCHED-REFINE-003

2026-11-16，Asia/Shanghai。合同固定于 `99497e8ea6a9f57fd9ac31ad2b98abf80422fba6`，实施起点 `159181eede633063e8a5becbaa33210ebb4223a0`，所有实施文件位于本批新增目录。

## 四次实际恢复

四个真实 `gpt-6.1-sol / medium` 会话全部完成实际计算、稀疏提交、保存及独立新进程回读。固定样本为PAIRS001/sample_05，首版native→facts，优化后facts→native。四次都达到预登记的47点支持域RMSE下降至少30%、410域RMSE同步下降、227个原正常可编辑点误改RMS不超过0.10mm的判据。四份实际保存文件的技术QA也全部通过。

两路都使用了当前坐标中的1/4096米格点线索定位受损点。两次候选达到近精确恢复，另外两次的支持域改善分别为73.90%和34.89%。PNG对恢复精度的因果贡献、跨样本泛化和用户艺术验收尚未建立。

实际受损blend回读后的支持域基线RMSE为 **1.697687mm**，p95为3.396866mm，最大误差3.871265mm，410域RMSE为0.574797mm。下表全部读取最终实际保存文件，经额外的新Blender进程导出后评分。

| 实际顺序 | 会话 | 实际变动点 | 支持域最终RMSE mm | 支持域下降 | 支持域p95 mm | 支持域max mm | 410域RMSE mm | 三项恢复/技术QA |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | v1 native | 44 | 0.000128 | 99.992457% | 0.000249 | 0.000591 | 0.000044 | 通过/通过 |
| 2 | v1 facts | 47 | 0.443070 | 73.901533% | 0.704467 | 0.768615 | 0.150013 | 通过/通过 |
| 3 | v2 facts | 45 | 0.000091 | 99.994639% | 0.000009 | 0.000528 | 0.000032 | 通过/通过 |
| 4 | v2 native | 47 | 1.105442 | 34.885379% | 2.166063 | 2.382708 | 0.374277 | 通过/通过 |

四次的227个原正常可编辑点及全部363个原正常观察点，位移RMS、p95和max均为0。对clean的微小世界坐标残差与受损基线相同，363点RMSE约 `8.99747e-9 m`、p95约 `1.04164e-8 m`、max约 `1.07453e-8 m`，227点分别约 `9.07283e-9 m`、`1.02217e-8 m`、`1.04713e-8 m`。逐点误差、位移及各组完整统计保存在每个最终评分的 `SCORE.json` 和 `SCORE_points.npz` 中。[四份独立核验与评分](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/FINAL_VERIFICATION.json)

## 固定输入与评分隔离

指定三份原始NPY的SHA与规划预检一致，正常目标、受损幅度、样本、相机和评分在四会话前固定。原正常区域410点、边界72点、一环64点、可编辑274点直接复用旧固定域。单次与累计位移预算均为 `0.006893660855829761 m`，取旧正常410域内1158条去重无向边的平均长度。梯度和法向变化作为观测，恢复任务的检查覆盖有限坐标、源ID、域外原生坐标、原生拓扑、矩阵、UV/材质/场景、新增退化/翻转及局部接触。

构造端只写入既定47点损坏，其余原生float32坐标通过逐位校验。随后新Blender进程读取实际受损文件，导出world/local坐标、保存矩阵、源ID和原生/派生拓扑。消费者initial、V0与可选法向全部由该次受损回读建立，法向从受损坐标重新计算。完整公开包采用16个字段白名单，旧clean法向、生成参数及标签保存在构造/评分目录。

PAIRS正常world坐标与原blend回读的最大向量差约 `1.10e-8 m`。构造保留了源矩阵中约 `4.37e-8` 的旋转项。评分采用实际受损保存回读作为不动基线，保存精度差异进入所有后续比较。一次用已知clean候选的隔离控制完成真实提交、保存及两次新进程回读，19/19项API检查通过，支持域恢复RMSE约 `8.49e-9 m`，227正常点误改RMS为0。该控制的3次Bpy与正式消费者单列。[构造绑定](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/CASE_BINDING.json) · [实际控制预检](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/API_PREFLIGHT.json)

消费者获得相同的正常/受损整体、前臂正面、侧面、45度八张PNG，当前完整受损几何、源ID、拓扑、410/274域和合理NumPy/SciPy计算。正常目标3D、真实支持域、逆位移和生成参数由构造与独立评分进程持有。facts额外获得当前几何区域描述及稳定引用。两个事实路线实际各调用一次focus，完整额外引用包的resolve调用为0。

Python工具实施AST/导入限制及CPython文件访问审计，只读当前版本几何包、已验证当前事实包和自有payload。普通open、np.load、np.fromfile、np.memmap的旧clean路径读取，以及跨会话/过期引用和引用写入都有真实拒绝预检。四次正式消费者的执行代码和访问记录只出现当前数据及自有分析/payload操作，未见隐藏clean或旧历史读取。限制属于进程内实现，操作系统沙箱认证未测。输入包、实际CODE、REQUEST、FILE_ACCESS及完整结果均保留。[冻结计划](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/PLAN.json) · [协议预检](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/CONSUMER_PREFLIGHT.json)

## 消费者实际方法

| 会话 | 当前几何定位与修复构造 |
|---|---|
| v1 native | 格点残差定位44点，尝试多项式和RBF后，搜索并联合拟合共同修复方向及逐点振幅，提交positions |
| v1 facts | 格点残差定位47点，用81个当前健康邻域样本做薄板RBF拟合，取0.75倍正向残差并做图拉普拉斯平滑，提交局部lift |
| v2 facts | 格点残差定位45点，整数格点候选搜索并共同方向拟合，提交positions |
| v2 native | 格点残差定位47点，尝试曲面拟合与双调和，采用均匀双调和位移的外法向正分量和幅度平滑，提交displacements |

定位和数值恢复的代码依据都包含可观察格点线索和局部曲面先验。事实工具提供的274点可编辑区域引用用于上下文和产物记录，活动子集由消费者自行计算。指定部位、宽选区与任务语义已经作为共同输入提供。当前结果支持这一固定合成样本的实际恢复链路，自动全场景语义发现、PNG深度重建和跨角色效果仍待验证。

v1 facts自报的曲面残差RMS `2.589→0.960mm` 来自健康邻域插值代理。独立评分的真实三维对应点误差为 `1.697687→0.443070mm`。报告和原始回答同时保留这两个量的来源。v2 native的恢复幅度约1.61845mm，支持域仍有1.105442mm RMSE及2.382708mm最大误差。四个候选完整保存，统一使用固定评价。[实际回答和工具汇总](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/CONSUMER_STATS_all.json)

## 一次预览优化与去留

首版两份回答都指出缺少成品视图。v1 native第二次images调用重复交付原始八图，首版两个会话的实际最终版本可视化为0/2。首版原回答、模型、状态、评分和图像索引已由 `OPTIMIZATION_BINDING.json` 逐SHA绑定。

唯一优化让现有images工具按保存版本提供视图。版本0继续交付原始八图，编辑后按相同冻结相机渲染四幅当前保存模型图，绑定session/version/saved SHA、实际render receipt和PNG身份，重复调用验证后复用缓存。两组获得相同说明和能力。完整图像计量相应区分冻结输入与保存版本预览，数值输入、模型设置、预算、目标与评分保持冻结身份。

隔离控制的30/30项真实预检通过，首次生成四图，第二次缓存复用、额外渲染0次。预检总1.635355秒，实际Bpy渲染1次。第二阶段两次实际消费者都先提交并独立回读，再取得自己的四幅version1预览，随后结束。预览后新增编辑为0。实际预览的8幅RGBA与独立最终渲染逐位一致。[优化绑定](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/OPTIMIZATION_BINDING.json) · [真实预览预检](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/PREVIEW_PREFLIGHT.json) · [8对像素核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/PREVIEW_PIXEL_VERIFICATION.json)

| 两会话阶段观测 | v1 | v2 |
|---|---:|---:|
| 固定最低恢复判据通过 | 2/2 | 2/2 |
| 实际成品预览 | 0/2 | 2/2 |
| Pro wall秒 | 296.286608 | 276.149356 |
| 工具次数 | 21 | 19 |
| 输入token | 514201 | 478516 |
| 其中缓存token | 452992 | 383232 |
| 推导非缓存输入token | 61209 | 95284 |
| 输出token | 7099 | 5808 |
| 公开工具文本字节 | 64399 | 74155 |
| PNG字节 | 9531462 | 9531823 |

第二阶段wall下降20.137252秒、6.80%，输入token下降6.94%，非缓存输入token增加55.67%，公开文本增加15.15%，PNG增加361字节。缓存为输入子项，非缓存输入按输入减缓存计算。费用未测。

按事前绑定的最低质量、技术QA、实际预览和阶段wall判据，本批实验默认采用V2预览组件。native支持域改善从99.992457%降至34.885379%，事实路线从73.901533%升至99.994639%。候选修复在预览前已生成，两阶段采用的修复算法也不同。当前数据没有建立预览对修复精度的因果贡献，同质量整体速度或费用净收益尚未成立。单样本、四会话、路线顺序和缓存变化共同限制泛化。V1和V2的精确工具源码、原始结果及候选补丁全部保留。[最终选择](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/API_SELECTION.json) · [候选补丁](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/OPTIMIZATION_DIFF.patch)

## 保存核验与实际图像

每个消费者的唯一编辑都触发实际保存及新Bpy导出。随后根任务又各开一个全新Blender进程读取最后保存文件，四次共56项身份和坐标检查通过，评分验证实际reader receipt及文件SHA。评价器源码和私有目标在消费者前冻结。独立导出复用了同一技术评价和私有评分实现，异实现评分复算未运行。

四份实际结果都保留原11个退化三角，新增退化、翻转、额外接触和接触关系变化为0。每份605个域相关三角、879条incident边的完整观测及局部精确接触结果保留，119条I边界跨边的位移梯度为0。四份的域外原生坐标、源ID、原生拓扑、矩阵、UV/材质和其他场景结构通过保持检查。梯度、法向、world-X深度、world-Y内侧方向及区域bounds另列于完整QA/评分文件。

正常、受损和最终结果使用相同相机、Workbench灰色材质、光照、比例和姿态。整体图480×800，局部图640×640，局部正交尺度0.285m，几何和位移展示倍率均为1。结果索引包含8张共享输入及16张独立最终after图，共24张PNG，另有第二阶段8张实际消费者预览图。索引指向完整保存blend和独立OBJ。[全部可视产物](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/VIEWABLES.json)

可直接查看相同45度视角下的正常目标、初始损坏、V2 facts及V2 native结果。[正常目标](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/consumer_cases/matched/images/normal_forearm_45.png) · [初始损坏](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/consumer_cases/matched/images/current_forearm_45.png) · [V2 facts](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/results/v2_matched_facts/after_views/forearm_45.png) · [V2 native](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/results/v2_matched_native/after_views/forearm_45.png)

## 成本与失败记录

| 会话 | Pro wall秒 | 输入token | 其中缓存 | 输出token | 其中reasoning | 工具 | PNG块 |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1 native | 146.423083 | 225163 | 195840 | 3484 | 1061 | 10 | 16 |
| v1 facts | 149.863525 | 289038 | 257152 | 3615 | 660 | 11 | 8 |
| v2 facts | 134.269159 | 232828 | 197760 | 2275 | 499 | 9 | 12 |
| v2 native | 141.880197 | 245688 | 185472 | 3533 | 635 | 10 | 12 |
| 合计 | 572.435964 | 992717 | 836224 | 12907 | 2855 | 40 | 48 |

四次均在12工具/600秒预算内，完成及安全退出状态全部成立。reasoning属于输出token子项。全部40工具成功，包含27次Python、4次真实提交、2次focus和7次images。48块完整PNG合计19,063,285字节，含40块冻结输入及8块保存模型预览。base64为25,417,776字节，公开工具文本138,554 UTF8字节，完整stdio回复25,571,060字节。

27个数值worker的executor wall合计21.196706秒，worker CPU12.34375秒，最大worker RSS133042176字节。packet快照冷建5次、命中22次，累计逻辑packet读取字节99,383,680，JSON输入354591字节。该packet量按每次本地文件读取计，完整几何经NPZ路径访问。Bridge self CPU合计11.875秒、self RSS最大180510720字节。四次消费者的已监控本地进程树CPU合计44.375秒，最大采样tree RSS700035072字节，约667.61MiB。

| 全部实际Bpy范围 | 次数 |
|---|---:|
| 构造受损并fresh读取 | 2 |
| 正常/受损八图渲染 | 2 |
| 私有clean恢复控制及读取 | 3 |
| 预览控制渲染 | 1 |
| 四次正式提交及对应读取 | 8 |
| 第二阶段消费者实际预览 | 2 |
| 额外最终独立读取 | 4 |
| 独立最终图渲染 | 4 |
| 合计 | 26 |

26次Bpy均退出0，包括6次写、11次读和9次渲染。作业wall累计33.819649秒、tree CPU25.78125秒，最大采样tree RSS454307840字节。正式四候选关联的18个作业包含消费者包络内10次执行和额外最终读取/渲染8次。Bpy、worker、snapshot、facts和工具时间嵌套于会话或预检，成本账本按唯一launch去重并保留包含关系。[完整成本账本](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/COSTS.json)

准备、真实控制、真实八图/数值协议、数值质量、消费者协议和预览预检均保留独立成本。质量预检23/23、消费者本地协议最终49/49、真实当前case Bridge预检通过、交付helper检查8/8、预览30/30。早期本地导入兼容错误在V1冻结前修复并保留失败记录。质量预检首次命中WindowsApps shim退出1，0.216536秒，查找既有venv后继续。图片路径静态对接曾位于构造case，现有PNG逐SHA复制绑定到消费者case，额外Bpy为0。只读审计中的依赖/路径查找失败与最终一次rg正则错误均有范围和已知成本记录，实际Pro失败为0。

端到端研发/等待墙钟从AL任务登记到 `COSTS.snapshot_UTC` 单列，提交与完成回报后的耗时由提交后HANDOFF记录。主Agent/协作模型usage及费用、全任务CPU/RSS、部分代码编写/检查shell独立资源和提供方内部请求、resolved模型设置、图像预处理及费用未测。50ms本地进程树采样可能遗漏极短后代，Bridge及worker的self指标截至其结果序列化前。四份正式Bridge的末次标记均为closed=false，退出后closed=true遥测回执缺失。四个CLI退出0、安全清理成立，独立CIM快照的本批所属运行进程数为0。

CLI事件把MCP图片结果序列化为文本并在1MiB处中间截断，48块图像分母由完整Bridge回复、逐PNG源SHA及已完成CLI调用共同核验。提供方内部图像编码和注意力分配未测。训练0，Google/API新增付费调用0，既有Pro登录消费单列。[准备审计](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/PREPARATION_AUDIT.json) · [最终来源核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/DELIVERY_VERIFICATION.json)

## 交付与下一建议

公开Git提交包含本批根目录脚本、冻结记录及报告。大体积blend、PNG、NPZ、完整消费者事件、回答和访问审计保存在本地private，MANIFEST逐文件记录全部本地证据。HANDOFF在固定提交后记录提交SHA和一次完成回报回执。

- 原件SHA为 `614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d`。[原模型](<D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend>)
- 指定三NPY的完整SHA和绝对路径保存在绑定文件。[来源绑定](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/CASE_BINDING.json)
- 正常及实际受损模型均可直接读取。[正常复制模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/construction/normal.blend) · [实际受损模型](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/cases/matched/before.blend)
- 四份实际结果分别保存。[v1 native](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/sessions/v1_matched_native/versions/001/model.blend) · [v1 facts](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/sessions/v1_matched_facts/versions/001/model.blend) · [v2 facts](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/sessions/v2_matched_facts/versions/001/model.blend) · [v2 native](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/private/sessions/v2_matched_native/versions/001/model.blend)
- 四份额外独立评分和逐点NPZ的完整路径保存在核验索引。[独立评分索引](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/FINAL_VERIFICATION.json)
- 原始回答、代码和访问审计的路径保存在消费者汇总及详情中。[消费者索引](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/CONSUMER_STATS_all.json)
- 本批根目录 `C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_matched_refine_003/`

下一建议为预登记一个消除格点定位线索的同相机恢复任务，分别检验图像与当前几何事实对定位和恢复的贡献。当前样本、生成参数及评分保持本次固定记录供独立复核。完成一次回报后结束本批，由规划复核及新明确合同决定下一步。
