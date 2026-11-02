# M4-B3d 公开锚点选区合同与验收

更新：2026-11-02。排期仅由[唯一主计划](PRODUCT_ROADMAP.md)决定。本批在[B3b可信来源](M4_SMALL_SOURCE_PRODUCT_ACCEPTANCE.md)与[B3c空间区域查询](M4_DEFORMATION_REGION_QUERY_ACCEPTANCE.md)上建立“公开原生锚点目录 → Codex选择身份及尺度 → 引擎重核并构框 → 区域事实”的有限闭环。模型不接收隐藏答案坐标、目标面ID或先验区域结果。

当前为**已完成有限原生关系选区及实际任务闭环的隔离候选**。源码/安装各28组、旧275组原生回归、新52专项与公共集均通过；一个新上下文先冻结8项选择，再消费5项真实查询结果，明确拒绝3项无唯一可信目标的任务。给定半尺寸和原生关系的成功不代表解剖识别、最优尺度或模型收益。

## 固定版本与来源边界

| 项目 | 固定合同 |
| --- | --- |
| 发行 | `9.7.2+20261102.deformation.anchor.r1`，121个运行源 |
| 运行源SHA | `4230d343ae71f895b792dfd658cab6b2c9992460035e0499549421c5f0bcda3b` |
| wheel SHA | `3b64a4e86d3b09e81f4b4798e3ecceff6149b9a5dc208fad7d105910bd80b738` |
| 来源域 | B3b固定文件、mesh/rig、保存帧、单位、完整父链/动作slot/LBS与所有外部pins保持；256点/256三角/16骨及旧B1拒绝不变 |
| 新数据 | 仅在完整校验后的内部proof增加`rig_world`与`bone_landmarks`，从已验原始/求值字段deepcopy；不增加producer准入schema，不裁掉动作或层级 |
| 入口 | `small_skin_source_entry.py --anchors-only`与`--anchor-query FILE`；两者及旧`--region-query`/`--triangle-query`互斥 |
| 原预算 | 每次独立调用保留原30秒、16请求、512KiB包/报告与4096字节选择文件，零产品setter、不切帧、不保存原文件 |

目录与选择都必须先经过完整来源验证。操作者profile、运行源码/worker/consumer/math/二进制摘要、PID/epoch、角色实例、帧与单位仍来自可信入口及实际握手，模型传入的目录、JSON标志或自洽摘要不能签发来源资格。默认MCP/live/Hook不因本候选自动切换。

## 公开目录与原生含义

目录schema为`surface-deformation-anchor-catalog-v1`。最多16骨、32个可选择端点，完整返回原生bone name、parent、connected、use_deform及head/tail锚点ID；不按位置合并。锚点ID固定为`bone-anchor:`加`sha256([rig_stable_object_id,bone_name,head_or_tail])`，骨名排序后每骨head在tail之前。

锚点表示**已捕获的求值骨head/tail，经当前rig世界矩阵和单位派生的位置**。它不是解剖关节、肘部、表面接触点或损伤中心。`connected`是原生声明字段；父子关系和端点接近也不自动证明解剖意义。两个端点即使共址，身份仍不同，选错身份不能因最终框相同而算通过。

每个端点保留`anchor_id`、`bone_name`、`endpoint`、`position_world_m`、`position_interval_world_m`、`state`及`reason`。`available`只表示该目录坐标在本合同内可用于选区，不等于三角形指标measured、区域健康或源包可以跳过校验。不可用端点保留身份，位置与区间为null，不能被自动替换成另一个点。

mesh bounds仅作为上下文：对所有三角形引用的当前顶点求完整世界米制包围界，含退化三角凸包，排除并计数loose顶点。`vertices_total`、`surface_vertices_total`、`loose_vertices_excluded`与`triangles_total`明确其范围；不提供可选择的mesh中心锚点，不把包围界解释成实体体积。

`completeness`报告骨与锚点总数、可用/不可用数、完整父图以及`anchors_omitted=0`。完整目录、某点坐标不可用、后续区域中指标unknown分别表达，不能互相覆盖。

## 数值投影与构框

先将输入二进制矩阵、端点及单位转为精确有理数，完成完整仿射表达，再给出nearest binary64位置及`[lower3vector,upper3vector]`向外包围区间。非零有理数若舍入为零，返回`coordinate_underflow`；精确位置超`abs<=1e9`区域坐标域时返回`outside_region_coordinate_domain`。不归零、不夹值，也不把不可用端点从目录中抹去。

区间只包围**冻结输入数值的有理仿射表达**，不是物理误差范围、统计置信区间或原生骨骼解剖精度保证。B3b的LBS/矩阵一致性接受窗也不是物理坐标误差。展示位置与完整来源中的原始字段分开，不能据展示舍入重写源数据。

模型只选择公开`anchor_id`与三轴`half_extents_m`；半宽必须为有限、非bool的3向量，各轴`1e-6<=h<=1e6`。引擎围绕**已公开的binary64位置**做精确`Q(center)±Q(half)`，将下界向下、上界向上舍入，生成B3c的`current_world_m`闭AABB。没有任意epsilon；超域或无法保持正范围直接拒绝，不能平移或夹框后伪装原任务。

逐循环核查原期限，有理结果分子/分母各不超过16384 bits，最终报告不超过512KiB。预算或期限失败不发布有效成功，也不能写成空区域。

## 稳定目录与每次live capture分层

稳定payload严格只有9项：`schema`、`source_ref`、`operator_pins`、`coordinate_model`、`graph`、`anchors`、`bounds`、`completeness`、`scope`。`catalog_sha256`只对这9项计算；其中operator pins完整包含scene/profile/worker/module/math/binary/runtime source SHA，profile摘要保留。

另置的`live_capture`、顶层当前`source_sha256`和只读状态不混入稳定摘要。目录摘要是公开选择数据的对应检查，**不是完整依赖摘要**；公开目录没变不证明动作或历史依赖没变，完整源SHA与独立校验仍负责来源失效。

`surface-deformation-anchor-selection-v1`严格有5项：schema、固定file/roles/frame的`source_ref`、catalog摘要、锚点ID和半宽。新进程先完整验证新capture、重新生成目录并核对稳定摘要与锚点，然后绑定`surface-deformation-anchor-query-v1`；recipe严格保存schema、**新**`expected_source_sha256`、catalog摘要、锚点ID与半宽。分析时再次重算并校验，不能用模型改写的目录、旧recipe或同坐标的新来源自行重绑。

目录调用和查询调用是两个各自完成、关闭并发布的只读调用。模型在两者之间思考，不占用或续借已经结束的原窗口；查询使用新的完整原30秒窗口和新epoch。稳定的文件级选择可以重新核对，旧目录的capture SHA始终不能冒充当前源。

查询结果保持B3c的`region_query`，另附`surface-deformation-anchor-query-result-v1`的`anchor_query`轨迹：原生身份、稳定目录摘要、当前源SHA、公开中心与区间、半宽和实际闭框，以及坐标和指标scope。它用于核对实际执行了哪个选择，不授予编辑权。

## 任务选择、歧义与指标边界

本批任务先注册：真实作者样本两个固定帧中的唯一非根骨head、明确名称的根骨tail，以及QA副本中的共址身份、两个根骨歧义、缺失名称和无语义映射的“肘部”。任务给原生关系/名称及尺度，不给答案坐标或面ID；模型只读公开目录、任务与schema，决定`selected`、`ambiguous`、`not_found`或`unsupported_semantics`。

选择决定在工具结果前冻结。操作者将模型决定原样组成selection，不纠正错误身份；独立评分按预注册关系解析目标，不能拿生产选择器结果当答案。多个结构候选时保留歧义；无来源支持的解剖词义不能猜最近点。这里认证的是有限原生关系选区，不是通用自然语言部位理解或自动发现故障。

区域结果仍是**命中整原始三角形的事实**，不是闭框内裁剪积分、面积或损伤。完整成员和状态计数、最多4详情及明确省略、仅measured/collapsed子集极值保持；unknown不能补零，empty不证明体积无物或健康。目录完整、区域observed和全局partial可以同时出现；当前世界区域也不是材料片动画轨迹。

## 同版本最终验收

已通过的新52项专项包含24项目录/数值、22项正式入口/生命周期和6项独立oracle检查；root合并旧流程的128项通过。它们不替代原生资产、隔离安装或实际模型消费；以下最终记录必须对应同一候选，保留失败与修正，不累计重复运行作为新资产。

| 验收项 | 最终记录 |
| --- | --- |
| 固定源码/隔离安装/wheel/公共导出一致 | 121源 `4230d343ae71f895b792dfd658cab6b2c9992460035e0499549421c5f0bcda3b`，源码/隔离安装/wheel/受测导出逐字一致；旧120源中116不变、4修改，新增1个锚点模块。530份公共Python与干净导出一致；producer schema与worker保持，只有已验内部proof增加rig_world/bone_landmarks |
| 源码与安装原生目录、查询、来源失效及准确拒因 | 源码28/28、隔离安装28/28，共56组；每套5目录+7查询+1来源unknown及15合同组。独立Decimal仿射/向外舍入、NumPy pose端点交叉、完整SAT/SVD均过，端点交叉残差最高约1.79e-7。共址身份不合并，新epoch目录摘要稳定、旧live recipe拒绝；profile仅增加空白也令旧catalog失效；全部原文件保持、进程回收 |
| 真实Codex从公开目录选择，决定冻结与独立身份评分 | 一个全新Codex上下文仅读取4个实际安装CLI公开目录、自然关系任务与schema，8项决定一次冻结：5 selected、ambiguous/not_found/unsupported_semantics各1。未给隐藏答案坐标、目标面ID或区域结果；独立预注册关系评分8/8符合，原JSON及冻结副本SHA保持。两共址端点即使得到同一框，仍按不同原生ID评分 |
| 实际查询、区域事实与新上下文结果消费 | 4次实际--anchors-only完成关闭后，原样执行5项模型选择的--anchor-query，3项拒绝无查询。同一新上下文随后仅看实际报告；16个极值百分比与25项边界判断独立核对通过。原样子骨head框frame1命中117面、frame25命中128面，均区域observed而全局partial/12unknown；原样根tail合法empty；两共址任务各命中2面但身份不同。未把空区、原生端点或整面指标误判为表面位置、解剖或损伤 |
| 完整耗时、字节及模型/调用范围 | 实际目录4次：接收到编码约2.38–2.60秒、完整CLI墙钟3.09–3.41秒、stdout4378–5077字节；实际查询5次约2.21–2.40秒/2.88–3.01秒、5629–10514字节。一个新上下文2轮模型交互，目录阶段增加独立读取成本，可在相同固定来源中复用目录但query仍完整重验。模型等待、完整任务token/费用及公平速度比较未测，不宣称总成本下降；native QA控制器成本另记 |
| 公共与干净源码、旧来源/区域/安全回归 | 149模块2428项：本地2425通过/3既有跳过，干净公共源码2415通过/13跳过；额外10仍为旧私有冻结源码依赖，无新增跳过。旧B3c源码/安装各20、B1/B2各66、B3b各22、约束43、恢复13、dyadic查询3，共275组保持。两个本地旧汇总器异构字段适配错误单独保留并修正，未改产品或验收预期，也未重跑原生任务冒报修复 |
| 原资产、配置、旧seal、Git同步与新证据封存 | 88份旧seal清单摘要及项目配置保持；另逐文件重核旧B2 2027、任务1137、B3a717、B3b1567、B3c1677份文件均一致，原作者GLB/.blend未改。代码、合同、公共反例与重放工具同步Git，本批原始记录单独封存；机器profile、原作者资产、包体和完整本机日志不进源码仓库 |
| 有限完成判定、未通过边界和唯一后续项 | B3d有限原生关系锚点闭环通过：一个外部作者testing样本两个静态帧，另2个独立QA构造场景；不扩来源、modifier、动画、语义解剖或编辑。下一门仅做选区质量与有收益的有限回退资格：显式识别空区/过宽/全unknown，先注册任务允许的候选及收益/完整成本标准，不静默换目标或盲目增图，再按真实失败补最小策略 |

独立真值采用另一套仿射/向外舍入及NumPy检查，端点另与pose matrix的原点/长度端点交叉核对；完整区域成员用独立SAT、指标用独立QR/SVD。一个外部作者testing样本两个静态时刻与QA构造副本，不代表真实生产角色广泛覆盖或整段动画认证。

本批不做骨骼/权重修改、IK、DQ、任意modifier、动画时序、训练或新Agent适配。模型选择原生端点的成功也不等于显著模型收益；正式质量、往返、完整耗时/token/费用比较仍须原公平对照准入，后续只按实际失败选择一个最小扩展。

原始证据在本地 `verification/fixes/20261102_m4_b3d_anchor_query/`。这批证明原生关系选择与确定性几何构框可用，不能把8项有限决定当模型统计准确率、把固定0.5米半尺寸当自动尺度优化，或把合法empty当定位到表面的成功。下一项沿唯一主计划建立选区质量出口；正式M2公平对照、默认发布和旧成本条件继续保留。
