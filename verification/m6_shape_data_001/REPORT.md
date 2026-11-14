# M6-SHAPE-DATA-001 训练数据与单一残差专家合同

2026-11-15。实施工作树为 `C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe`，分支为 `codex/m6-model-selection-001`。本批从 `9b016c8720b709a6382438ddd505c7b154d4fac2` 继续，合同固定于规划提交 `d88cf18d1a6cf564c907d980ccf0ef159a954e9f`。来源读取方案先固定于 `465a0894`，分组、采样规则、33个patch和生成脚本在损坏生成前固定于 `bc2dfddb4f0d8d2304a5aa6dcb5c03d076b6f666`。

## 本批结果与用途

已核查四份正式资产，建立33个正常patch及231个观察样本，其中33个正常控制、198个局部凹陷。全部231例通过预定局部退化和翻面门槛。完整宽区域位移标签、观察专用输入、源映射和生成前证据均已交付。

四份文件的几何不同，现有来源记录仍无法确认上游底模相互独立。因此全部保守合为一个来源组，用途为开发及待训练来源池，独立验证和保留测试为空。独立性证据缺口阻止当前数据承担跨来源模型选型验收。数据数组已经可供后续训练使用，模型训练次数为0。

|来源文件|正常patch|正常控制|凹陷|观察总数|允许域源顶点并集|
|---|---:|---:|---:|---:|---:|
|Yanyite|11|11|66|77|3,258|
|Richie|8|8|48|56|2,055|
|Chipow|6|6|36|42|1,762|
|Yunhex|8|8|48|56|2,319|
|合计|33|33|198|231|9,394，按各文件索引分别累计|

33个patch中有19对允许域重叠，最大Jaccard为0.984496。Yanyite的patch03/06共享381/384点，Richie的patch03/06共享367/384点。这些派生样本始终同组。patch数、观察数和程序断言数分别报告，来源分组的分母为一个保守组，已验证上游独立来源数为0。[数据汇总](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/DATA_SUMMARY.json)

## 来源几何与派生关系

Yanyite复用旧批已冻结且raw/evaluated相等的world导出。其余三份源文件先复制到本批private目录，再由三个独立后台Blender进程读取，均使用factory-startup、disable-autoexec、单线程、无GUI和不保存源文件的方式。每份源读取前后的SHA256一致。对象选择统一按raw顶点数最多的mesh，顶点数并列时按对象名。其他对象仅保留inventory摘要，完整几何未纳入当前patch数据。

|来源|选中mesh顶点|三角形|本批静态几何状态|
|---|---:|---:|---|
|Yanyite|27,304|53,264|复用原world数组，raw与求值一致|
|Richie|25,768|49,785|保存帧1求值快照，已有armature修改器，raw到求值最大差约2.4621e-7 m|
|Chipow|28,368|54,636|保存帧1求值快照，与raw几何一致|
|Yunhex|26,819|53,100|保存帧1求值快照，已有NaturalEyeSupport形态键约0.65，最大差约0.64247 mm|

四者scene均为METRIC、scale_length=1。矩阵已应用到world坐标。Richie对象矩阵含约0.01尺度。Yunhex求值后三角划分有6行变化，顶点ID和polygon映射保持。因此本批三角形ID明确指各冻结快照的`calc_loop_triangles`顺序，源polygon ID另存映射。Yunhex求值三角ID与raw三角ID须按各自快照解释。[来源清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/SOURCE_MANIFEST.json) [几何审查](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/SOURCE_AUDIT.json)

文本审查确认各角色内部历史版本链，以及Chipow到Yunhex的交接场景链。Tripo相关命名、不同UUID和贴图关联不足以闭合上游生成来源。Yanyite与Richie当前正式文件SHA还与部分历史交付记录不同，历史记录只承担其对应版本的证据。本次保全以当前实测SHA和导出前后比较为准。[来源证据及散列](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/PROVENANCE_REVIEW.md)

几何核查保存了精确坐标、拓扑、归一边长摘要，并对六对文件做PCA符号/轴置换初始化、允许镜像的尺度归一化点集ICP比较。全形状归一RMSE约0.0368–0.1552。每来源另固定四个空间覆盖中心，共比较96对局部近邻patch。这是近重复诊断，采样和局部优化限制保留，几何差异不足以证明上游独立。[几何审查](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/SOURCE_AUDIT.json)

来源合组先于patch和损坏生成。原Yanyite七例保留为历史开发诊断，本批排除其旧中心24205。当前没有将同组patch移为验证或盲测。[分组及用途](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/SOURCE_GROUPS.json)

## 固定采样与实际缺口

每来源上限12个patch，四层各最多3个。层分别为保存绕序下的自然凹面代理、凸面代理、邻接法向变化高值及距离原开放边界3–6跳的区域。每层先按几何分数取首点，再按欧氏最远覆盖固定最多24个候选，源ID用于确定性并列处理。组件至少512点，中心法向一致性至少0.5。所有规则和候选顺序在生成前冻结，未使用模型结果。

宽允许域固定为中心测地最近384点，上下文为两环halo。预检检查诱导三角域、自由内部、原面质量、两半径支持数量及法向方向一致性。298个候选检查中33个入选，265个拒绝。拒绝原因包括132个诱导域悬挂或非流形、120个支持法向不能定义同一内凹方向、8个支持点不足、1个中心/自由内部不适用、1个中心重复、3个原incident面退化。候选耗尽后按首次规则保留数量。

|正常patch层|实际数量|相对12个上限的差额|
|---|---:|---:|
|自然凹面代理|8|4|
|自然凸面代理|10|2|
|曲率变化|4|8|
|原边界附近|11|1|

实际比48个patch上限少15个，对应少105个观察。部分小组件和非流形/法向不一致区域未覆盖，各来源排除数量已保存。该缺口按当前固定几何规则报告。全部入选、拒绝、候选顺序与重叠关系可追查。[数据计划](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/DATA_PLAN.json) [patch选择](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/PATCH_SELECTION.json)

## 配对、监督和输入隔离

每patch保留一个未扰动控制，另取`r/D=0.35、0.55`与`a/r=0.05、0.15、0.30`的六个组合。D及距离来自原诱导三角边图，复用上批已核验的拓扑与最短路函数。支持满足`d<r`且位于自由内部，权重`(1-(d/r)^2)^2`，位移沿中心完整incident面积加权法向的负方向。保持保存绕序，不通过换符号或替换样本改变结果。

支持点数范围为3–110，最大位移为29.007103 mm。各patch两支持域法向与中心方向均为正对齐。全部231例在其完整允许域incident面中无零面积面或法向点积负值，边界与外部坐标保持，固定拓扑不变。图中的ACCEPTED表示本批局部数据质量门槛通过，源形状的美术质量仍无人工验收标签。

监督包含88,704个允许域顶点观察，其中6,042个受损点、82,662个正常点，正常自由点为66,793。每个样本保存完整context逆位移和明确的正常零标签。以上按观察累计，包含同源变体及patch重叠。训练损失分别处理全部允许域、受损域及正常自由域，避免零标签数量掩盖受损处误差。[逐样本索引及计数](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/DATASET_INDEX.json)

观察准备函数只接受当前异常坐标、三角形和共享拓扑。共享拓扑由原三角形及宽允许域构成。7维node标量、4维edge标量及局部位置/法向向量均来自异常观察。原点为观察固定/halo点均值，尺度为观察context边长中位数。法向、邻接统计在完整当前观察上计算后抽取context行，未来在线成本须包括这一准备。

修复网络输入白名单只含`node_features、edge_features、positions、normals`及局部边/允许与固定mask。origin和scale承担观察反变换。正常内部参考、生成参数、真实支持、角色名、文件名和绝对源ID只留在追踪或监督侧，进入模型的数值特征没有这些字段。source ID仅用于取数和输出映射。[观察准备代码](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/features.py) [训练合同](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/TRAINING_CONTRACT.json)

私有目录中每patch共享`graph.npz`，`mapping.npz`保存源点、源面及polygon映射，`reference_local.npy`保存world参考。各`observed/sample_XX.npy`保存实际局部观察，`inputs/sample_XX.npz`保存观察专用数组，`labels/sample_XX.npz`保存完整逆位移及支持/正常mask。完整源快照每来源保存一次。可用完整源参考副本按context映射替换观察数组，恢复每个完整观察，原context以外按固定存储规则保持源值。当前无需为每例重复导出完整人物OBJ。

生成器和所有输入的字节在运行前固定。当前已从冻结本机源缓存、诱导边距离和参数独立逐点重算并核验全部配对，局部数组与标签均已完整读回，数据生成主入口执行一次。原生成脚本带既有结果保护，其绝对路径绑定当前本机快照。跨路径重生成入口和第二轮字节级重生成一致性尚未实测。verify主入口会更新自己的核验JSON和日志，当前配对数据保持首批内容。[冻结输入散列](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/FROZEN_INPUTS.json) [生成器](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/generate.py) [核验代码](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/verify.py)

## 核验与实际视图

4130项程序断言通过，覆盖231个观察和33个patch，包括冻结文件保全、独立边计数、稠密最短路、逐点公式、源映射、标签及输入白名单、正常点保持、局部质量和完整读回。66例重新计算观察特征，四来源各一个固定重损坏例检查旋转、平移和尺度变换下的标量不变与向量协变。context零法向出现次数为0。

浮点标签回放最大坐标误差为`2.047366257043086e-9 m`。该回放只核验float32归一标签的序列化精度。当前没有模型预测成绩。[完整核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/VERIFICATION.json)

两张图按生成前固定顺序显示正常、浅损坏sample01和重损坏sample06。每图4行，使用相同45°斜视相机约定和统一6000px/m。为看清尺寸较小patch，最终视口固定为参考中心76.6667×55mm窗口，面板间不重新缩放。十字标记参考中心，实际三角形经深度栅格绘制。首次全context宽视图因小patch难以辨认，已保存在private/qa_wide并记录成本，第二次只调整可视窗口。[来源对照图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/private/SOURCE_COMPARISON.png) [正常负例分层图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/private/NORMAL_CONTROLS.png) [两次渲染记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/RENDER_LOG.json)

## 唯一首选与后续比较

首选为6290参数、宽度24、12步共享cell的局部网格残差专家。标量消息传递后，以标量系数组合观察法向和相对边向量输出三维修正，边界和halo硬零。参数量由模块公式复算，实际框架参数张量和完整网络前向尚未实现或测量。旋转协变结论来自构造及观察预处理检查，训练后仍须评价实际模型。[网络合同](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/NETWORK_CONTRACT.md)

输入图含426–578点、2470–3294条有向边。受损点到正常观察最多5跳，到固定/halo最多9跳，因此12步内均能取得正常及固定周边信息。支持域最大直径16跳、完整图最大直径31跳，12步仍缺少部分远端信息。当前只核查可达性，恢复能力须由训练验证。[逐patch图统计](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/VERIFICATION.json)

后续保留no-op，并只预选一种直接比较方法，即残差门控的鲁棒二次MLS局部投影。它在同一观察context图内按测地窗口拟合局部曲面，通过训练正常控制校准残差门限，再逐点同时修正。窗口、IRLS、截断常数和门限规则均具体写入合同，数值不适用点回到零修正并计入分母。MLS的已有研究主要涉及局部曲面和噪声处理，本批连续凹陷的效果尚未取得。[网络与直接基线合同](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/NETWORK_CONTRACT.md)

首轮合同指定PyTorch CPU、float32、单线程、固定种子1729、batch4、AdamW、1200步或30分钟、RSS上限2GiB。当前两个已查解释器均缺torch，依赖准备及其费用计入未来训练批。初版后最多一次有证据的优化，再由验证选择版本并一次打开保留测试。

质量门槛同时约束受损支持恢复、整个允许域、正常自由点与正常控制、尾部最坏例、完整回读及接触。按逐case误差比值汇总，另报来源组和成员文件分母。相对no-op的支持RMSE比值中位数上限0.70，允许域改善中位数至少20%，相对MLS的支持改善中位数至少10%。正常点和控制的误改上限、近零分母规则及完整成本允许值均已具体化。允许完整链路p95相对MLS额外最多2秒属于本批提出的质量型任务预算，待规划复核，当前没有在线延迟或速度收益测量。[机器可读合同](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/TRAINING_CONTRACT.json)

## 已测成本与缺测

本批计量不完整。下表保留各独立主区间。后台采集子进程和生成子阶段嵌套于对应主区间，不能重复相加。

|阶段|墙钟秒|CPU秒|计量范围|
|---|---:|---:|---|
|来源采集控制器|5.574335|0.359375|墙钟含三个子进程，CPU不含子进程|
|Richie后台完整进程|1.498930|0.984375|采集控制器内嵌子项|
|Chipow后台完整进程|2.131652|0.859375|采集控制器内嵌子项|
|Yunhex后台完整进程|1.524310|1.093750|采集控制器内嵌子项|
|来源几何审查|4.475274|4.437500|导入后main区间|
|patch准备|7.394859|7.359375|导入后main区间|
|231例配对与准备|15.042710|11.781250|导入后、结果发布前main区间|
|独立读回核验|8.421230|8.375000|导入后main区间|
|两次实际几何渲染|2.974015|2.921875|渲染函数区间合计|

生成区间中，拓扑准备4.653477秒、损坏与标签0.760236秒、观察特征5.084317秒、质量0.264411秒、数组写出0.862366秒，其余工作留在主区间。Yanyite当前新增导出成本为0，旧批历史采集记录保留。私有数据当前合计69,463,892字节。

三个新采集进程的生命周期峰值working set约299.2、302.8、341.8MB。这些仅是采集进程的指标。来源文本审查、完整编写/元数据/提交/发布区间、非Blender各阶段含导入的全进程CPU及峰值RSS、完整管线墙钟与CPU均缺测，整管线总值在JSON中保持null。冷态、复用态模型及完整耦合成本尚无运行数据。[成本记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/COSTS.json)

来源审查第一次在隔离Python启动时发生`ModuleNotFoundError: geometry`，在main之前退出。已显式加入当前脚本目录后重启审查，首次失败的shell墙钟0.171963秒保留于日志。诱导边距离核对确认33个已选patch的D及支持数量一致。来源分组、生成幅度和首批231个数据没有因此替换。[运行记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/RUN_LOG.json) [诱导边核对](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/PATCH_DISTANCE_CHECK.json)

## 剩余缺口与唯一训练建议

最先需要补齐上游来源证据，使现有四份文件至少可可靠划出三个独立组，或取得两个与当前保守合组及彼此相互独立的新来源组。随后保留训练、验证及测试的组隔离，按本合同只进行这个残差专家的一轮训练和一次有证据的优化。当前33个patch提供开发数据与管线核验，patch重叠、单一平滑凹陷规则和小组件排除限制其覆盖范围。

本批模型训练、候选推理、直接修复基线运行、接触查询、付费API、新产品模块和M5写入计数均为0。单个完整选中mesh内的端点相交、其他scene对象与跨对象接触、实体包含、间距和运动路径均未测。后续候选验收需依据实际任务完整回读和对应影响域执行耦合检查，当前局部面质量通过不能承担这些判定。

完整角色几何、标签和图像均在本机private目录。Git仅收录代码、计划、来源/分组、摘要、报告和散列。最终提交后向规划聊天回报一次，等待独立复核。[交付证据清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_data_001/EVIDENCE_MANIFEST.json)
