# M6-SHAPE-TRAIN-001 唯一残差专家首轮

2026-11-15。工作树为 `C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe`，分支为 `codex/m6-model-selection-001`。本批从 `efce450c1da372642010871994588a69799e268c` 继续，任务合同和前批复核固定于 `5fd3c3eb1668812515fd6504895a39590376e9c8`。来源用途、框架、模型、MLS及首轮程序在训练前固定于 `074104b5`。

## 首轮判断

唯一6290参数、宽24、12步共享消息传播的残差网络已按seed1729完成1200步。训练外层墙钟68.185468秒、进程树CPU67.359375秒，实际训练Python进程峰值working set为520,589,312字节，满足30分钟和2GiB研究预算。首轮固定使用末步权重，优化训练次数为0。

**首轮未通过质量门槛。** 支持域恢复有改善，正常区域误改和面朝向变化阻止当前候选承担完整修复。最值得优化的问题是保持原本正常的自由点，同时保留受损点恢复能力。当前数据中的偏心支持误差表现优于中心支持误差，主要失败证据指向正常点保持。[逐例结果及判据](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/RESULTS.json)

|子集|损坏/控制|方法|支持RMSE/no-op中位数|p95|最大|允许域改善中位数|
|---|---:|---|---:|---:|---:|---:|
|开发中心|198/33|模型|0.795063|1.176010|3.828148|-53.35%|
|开发中心|198/33|MLS|1.000000|1.000000|1.032016|0.00%|
|Armadillo中心|54/9|模型|0.859680|0.937289|0.957324|4.07%|
|Armadillo中心|54/9|MLS|1.000000|1.000000|1.000000|0.00%|
|Armadillo偏心|54/0|模型|0.777769|0.880195|0.931728|-25.10%|
|Armadillo偏心|54/0|MLS|1.000000|1.000000|1.000000|0.00%|

比值与改善先逐case计算，再取分位数，控制样本的支持域指标为null。No-op的损坏支持比为1、允许域改善为0，正常点误改为0。两个验证损坏子集中各54例的支持RMSE均有下降。中心支持域中位改善约14.03%，偏心约22.22%，均低于支持比≤0.70对应的30%改善目标。两组允许域改善分别为4.07%和-25.10%，均低于20%目标。MLS在117个验证观察上全部保持输入，其门限按合同由训练控制一次校准。[完整对照](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/BASELINE_RESULTS.json)

## 正常点与面质量

模型正常点保持门槛在开发231/231例、验证中心63/63例及偏心54/54例失败。正常控制门槛在开发33/33例、验证9/9例失败。验证偏心沿用中心组的9个控制，没有新增控制。

模型正常控制的允许域RMSE/观察尺度在开发最大0.110754、验证最大0.062284，目标上限为0.01。验证中心和偏心的正常自由点p95误改最坏分别为0.138773、0.133176个观察尺度。对损坏case，正常点占最终平方误差的比例中位数在开发为79.83%、验证中心17.18%、偏心64.04%。这些比例按各case计算，保留源和幅度分层。

所有方法的固定边界和域外保持检查通过。模型无新增零面积面，相对输入的面法向点积负值按case累计为开发647个、偏心4个，分别涉及38例和4例，验证中心为0。MLS开发累计137个，涉及55例，验证为0。该计数描述相对输入的面朝向变化，重复变体中的同一源面可重复计数。[A/S/N/N_F与逐面记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/RESULTS.json)

模型全部348个最终case前向均有限，整例no-op回退为0。MLS在开发72,835个自由点观察中有7个因邻域点数不足回退，验证36,608个自由点观察均适用。全部不适用点保留在分母。开发MLS正常点门槛失败63例、控制失败9例，完整尾部事实同时保留。

## 数据、用途与量纲

旧训练池原样复用33patch、231例，四个本地角色仍为一个未知上游来源组。每批四图分别来自四个成员文件，含一个正常和三个损坏观察。成员文件等权，patch和六种半径/幅度组合按固定循环取样。1200批中每个成员恰有300个正常与900个损坏图，来源分组没有因此拆分。

新来源从规划者已校验原件复制，本批没有再次下载扫描源。Armadillo的big-endian PLY及其face intensity字段、Bunny的ASCII额外顶点属性均已正确读取，两份独立解析及散列检查通过。两者用于重建网格上的合成凹陷研究，扫描对象分布与人物美术修复有差异。来源署名为Stanford Computer Graphics Laboratory。[Stanford资料与研究使用说明](https://graphics.stanford.edu/data/3Dscanrep/)

|来源及用途|patch|正常控制|中心损坏|偏心损坏|观察总数|
|---|---:|---:|---:|---:|---:|
|Armadillo验证|9|9|54|54|117|
|Bunny保留测试|12|12|72|72|156|

四层采样、384点允许域及两环context沿原规则。封闭Armadillo的source-boundary层留空。21个patch均有第一个有效偏心中心，全部273个观察局部质量通过。偏心候选顺序、拒绝和宽域不变规则在生成前保存，未追加训练损坏。两份新源坐标以native unit保留，物理单位尚未证实。结果同时保存native误差及观察边长尺度归一值，未给扫描源标注毫米。[来源](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/PUBLIC_SOURCES.json) [选择与偏心顺序](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/PUBLIC_PATCH_SELECTION.json)

公共数据3480项格式、公式、映射和读回核验通过。Bunny仅执行这些构造核验，模型和MLS评分数均为0。训练的18个标准化量只从231个训练观察拟合，MLS门限只从33个训练控制拟合。独立只读审查逐值核对标准化、1044个最终候选及其误差统计，结果一致。[公共数据核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/PUBLIC_VERIFY.json) [标准化](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/NORMALIZATION.json)

## 模型、实现与固定权重

实际PyTorch参数张量计数6290，模块维度与前批合同一致。节点7标量、边4标量，观察位置与法向仅用于向量残差构造。alpha末层和beta初始为零，边界/halo输出硬零。初始预测为逐位no-op。非零头、节点和边排列、任意轴proper rotation、两图批处理隔离及一次合成梯度更新检查通过。合成QA更新使用独立实例，正式训练仍只有这一轮。[模型源码](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/model.py) [模型QA](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/MODEL_QA.json)

加载器通过可指定输入根目录取得局部数组。只把观察白名单和局部图索引传给前向，源ID、标签、支持、中心/幅度和角色/文件名留在取数、监督与追踪侧。重新定位根目录、损失分母和保留测试入口锁定检查通过。零修正分量保留原binary64值，包括signed zero。[加载及反变换](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/data_io.py) [联调QA](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/INTEGRATION_QA.json)

CPU float32、单线程，AdamW与余弦计划、batch4及损失权重沿冻结合同。第0、400、800、1200步都评价117个验证观察，中间开发观察固定8例，最终全量231例。验证支持比中位数如下。末步固定策略保留，中途快照只供核查。

|步数|中心|偏心|
|---:|---:|---:|
|0|1.000000|1.000000|
|400|0.884735|0.789339|
|800|0.870562|0.785396|
|1200|0.859680|0.777769|

末步权重为103,390字节，SHA256为`3f843b0153f1c63d95f7122d6ef68e2df151bcecc8705377596c7940665adc0f`。后续冷暖测量前后散列一致。[末步权重](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/private/weights/step_1200.pt) [训练全记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/TRAIN_LOG.json)

## 唯一直接基线

门控鲁棒二次MLS按固定观察同时拟合全部自由点。测地半径8个观察尺度、法向点积≥0.5、至少12点、满秩二次设计、初次加权最小二乘及三次Tukey IRLS均按合同实现。MAD取未加权有符号残差对其中位数的偏差，截断常数4.685、尺度下限1e-4。实现的12项合成QA通过。

33个训练控制共10,405个自由点，10,404个适用残差的一次99.5%分位校准得到`tau=0.9266132396947365`。门限在验证和在线测量保持不变。33个控制拟合缓存只在开发重用，计算成本计入首次校准。较高门限在当前Armadillo全部观察上产生no-op，训练中的少量高残差正常点仍有误改与面朝向问题。[MLS源码](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/mls.py) [QA](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/MLS_QA.json) [校准身份及分母](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/MLS_CALIBRATION.json)

## 冷态、复用与完整成本边界

隔离venv使用Python3.12.14、PyTorch2.15.0+cpu及NumPy2.3.5。11个wheel及依赖锁定SHA，Torch来自官方CPU发行源，NumPy来自PyPI。wheel共150,223,859字节，安装时venv为715,215,830字节，没有安装GPU栈或改变正式MCP。[环境锁](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/ENVIRONMENT_LOCK.json) [依赖散列](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/requirements.lock.txt) [官方安装入口](https://pytorch.org/get-started/locally/)

|阶段|墙钟秒|CPU秒|范围|
|---|---:|---:|---|
|框架准备|174.363703|缺测|venv、官方wheel下载、散列锁与安装|
|公共源准备及首次核验|81.888032|77.062500|脚本入口开始，含导入与首核验|
|两次追加数据核验|41.662767|41.484375|已保留两次记录|
|MLS校准与348例对照|51.196663|45.406250|完整外层进程|
|训练及规定评价|68.185468|67.359375|完整外层进程树|
|native接触域检查|0.586040|0.546875|完整外层进程，未启动表面扫描|

训练内嵌阶段墙钟为batch构建0.414391秒、前向23.314339秒、loss2.185394秒、反向及梯度裁剪31.149647秒、优化器0.699212秒、规定评价6.480745秒。它们包含在训练外层内。公共源准备与框架安装曾并行，所有嵌套/重叠区间不能直接相加为总任务耗时。[完整成本与范围](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/COSTS.json)

冻结的三个Armadillo输入为首patch正常00、中心06、偏心12。两方法各3个新进程cold、9次warm，共6进程24调用。每次完整重算法向/邻接动态特征，恢复全部172,974点候选并保存、完整读回。24次白名单、origin和scale重算均与冻结数组相同，边界及全部域外逐位保持。Cold表示新进程，OS文件缓存未控制。Warm复用源、图和已加载模型，动态部分每次执行。

|方法|cold中位/p95秒|warm中位/p95秒|worker峰值working set|
|---|---:|---:|---:|
|模型|3.546045 / 3.567303|0.199886 / 0.219270|486,330,368 B|
|MLS|1.340329 / 1.610232|0.275497 / 0.297938|231,219,200 B|

模型warm动态准备中位0.175791秒、前向0.005304秒。MLS动态准备中位0.153307秒、拟合0.104872秒。完整读回约0.0052秒，核对和散列约0.0063–0.0069秒，均计入各调用。在线监测driver自身CPU为2.890625秒，墙钟20.693357秒包含六个worker区间。不同阶段的CPU存在15.625ms粒度，小值0不表示免费。上述是少量首轮研究测量，质量门槛仍失败。[完整配对与各阶段](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/ONLINE_RESULTS.json)

框架安装最初的监测仅抓到了Windows venv启动代理，实际安装子进程CPU/RSS缺测，COSTS保留null。后续监测已跟踪进程树并保留实际Python生命周期峰值。除已记录的在线driver外，其余监测控制器CPU/RSS、全研究交互CPU、编写/审核/token费用、完整打包回报成本及全局pip缓存增量也未测，没有用代理的低CPU/RSS替代安装成本。

## 接触域与保留项

既有002入口要求`coordinate_frame=saved_world_binary64_m`。Armadillo仅有native坐标，物理单位未证实。一次使用正确native标记的域检查返回`invalid / coordinate_semantics`，端点表面查询数为0。同源其余两个预选检查未重复执行。评价器和坐标没有改写，接触接受为unknown。冷暖测量包含完整数组回读，耦合检查部分明确不包含，完整任务额外p95≤MLS+2秒的门槛仍为unknown。[接触域事实](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/COUPLING_STATUS.json)

原资产写入、Blender、M5、产品激活、付费API、第二网络或优化训练均为0。源内数据和权重留本机private，公开Git只含代码、计划、数值记录、身份和散列。本批的原生单位、扫描对象分布、局部合成问题族和缺失完整耦合仍限制结论。

## 实际最坏视图与交接

图中按冻结规则选取开发最坏支持比、验证中心最坏支持比、验证偏心最坏支持比及正常控制最坏误改，四列为参考、no-op、MLS和模型。采用实际三角形深度绘制，同一行固定相机，所有行以各自局部平均边长归一后共用尺度。图中文字指标使用观察中位边长归一。完整源保留native坐标，不通过显示归一化改变评分。[真实最坏对照图](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/private/renders/RESULTS/WORST_COMPARISON.png)

首轮事实支持把唯一一次优化聚焦于**正常自由点误改及其面质量后果**。验证偏心正常点占最终平方误差的比例中位数为64.04%，所有验证观察的正常点保持门槛均失败。该问题优先于完整性能选型。当前保持首轮权重和阈值，交规划者深审后再派一次优化，Bunny首次模型/MLS评分继续保留。[交付清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/EVIDENCE_MANIFEST.json)
