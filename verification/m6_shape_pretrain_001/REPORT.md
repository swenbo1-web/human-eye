# M6-SHAPE-PRETRAIN-001 预训练迁移筛选

2026-11-15。基线`e2d163159bd9c3110395304b16ac9cd43a0da905`，合同`27e6d5a22569dddf57b032fccc57f09009965cb8`，最终PLAN冻结`da7e2d7ebb784ef67c1cacd4b2d0e6f633b7d5a1`。

**Pointfilter官方预训练直接迁移未通过局部凹陷质量筛选。唯一后续建议是提交一次同架构凹陷领域微调方案供规划者复核。当前模型产品验收状态为未通过。**

## 固定来源与执行

固定官方提交`6e0ec1eac59ca9f81ee9ca6751c5b3f25effeda2`，权重SHA256 `86600e6d57fab7887fbda0cf54292578a52d956c36766a130d1e32a475d18cee`，参数1,360,899。六份官方源码/MIT、权重和两份Tetrahedron数组均核对官方Git blob后使用。Torch2.15.0+cpu/NumPy2.3.5复用旧只读安装，SciPy1.15.3/sklearn1.7.2等装入本批private/deps。[SOURCE_INDEX.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/SOURCE_INDEX.json) [ENVIRONMENT.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/ENVIRONMENT.json)

推理包严格只有完整当前源vertices、原任务F源ID与context源ID三个字段。每步完整当前源bbox对角×0.05半径，官方PCA和500采样，batch64单线程，两次同步只更新F，以第2步为结果。每例每方法重置seed1729，第二步沿用该例RNG，37例首步采样全部一致。网络及逆旋转float32，局部增量加回float64中心。该任务更新F及省略全云float32保存的适配已在官方流程对照中核查。[INPUT_INDEX.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/INPUT_INDEX.json) [MODEL_OUTPUTS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/MODEL_OUTPUTS.json)

7正常、12角色中心凹陷、9Armadillo中心、9偏心共37例全部完成，两新方法74例方法均完成，无遗漏或执行失败。四角色同未知上游组，旧压力选例依据保留。论文训练图可辨认Armadillo/Bunny形状，具体采样重合未知，Armadillo按迁移压力组解释。Bunny数组及评分次数0。

## 官方流程检查

1555项官方预处理/采样/PCA/逆变换及前向等价性检查通过，预处理最大差0。两官方输入各128固定查询单次过滤，另复算4个已有查询。噪声128点到完整干净点集RMSE比值0.401835，干净输入位移RMSE为bbox对角的0.00087566。逐点对应关系未证实，采用有限查询到点集的距离。[TETRAHEDRON_CHECK.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/TETRAHEDRON_CHECK.json)

## 凹陷修复与正常保持

表中S比值为支持区RMSE/同例no-op，正常控制的S为空。A改善为1−候选A/no-op A。各数值为逐例中位，全部原分母、p95/max、幅度与source/patch分层在完整评价中。

| 子集 | 凹陷数 | PF S比值 | 同邻域MLS S比值 | PF A改善 |
| --- | --- | --- | --- | --- |
| development_center | 12 | 1.461277 | 2.002809 | -293.04% |
| validation_center | 9 | 1.046589 | 4.874315 | -87.19% |
| validation_offcenter | 9 | 1.697881 | 7.490257 | -442.04% |
| all | 30 | 1.421579 | 3.856307 | -320.38% |

PF全部30凹陷S比值p95/max为4.935996/6.957320。对同输入MLS支持改善中位46.57%。验证source Armadillo中位1.336359，目标上限0.85。支持中位≤0.70、p95≤1.05、max≤1.25及A改善≥20%均失败。

7正常对照全部失败，A RMSE归一中位0.389059，规定每例≤0.01。37例N/N_F保护全部失败，N_F逐例p95中位0.880287，规定每例≤0.02。23/37例发生面质量失败，逐例翻面计数之和759，新增退化0。固定、边界和全源域外均逐位保持，全A incident覆盖完整。MLS翻面逐例和1502。该计数重复观察中的同源面，独立资产数另列。[EVALUATION.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/EVALUATION.json)

旧门控MLS/TRAIN/OPT的37例保存历史均在逐例评价中引用，原失败保留。source-file门槛按验证source应用，开发source与patch分布另列；相对MLS收益门槛用于Pointfilter候选，MLS自身标不适用。

## 表面量、输入尺度与修正方向

双向有限A顶点到保存context闭三角面覆盖37×3方法、222方向、85248查询。每方向RMSE/p95/max、最近点及边界归因均保存，连续全表面与全源表面最大偏差仍未知。

| 方法 | 双向RMSE逐例中位 | 切割边命中点观察 | 自然开边命中点观察 | unknown边命中 |
| --- | --- | --- | --- | --- |
| no_op | 0.059772 | 0 | 232 | 0 |
| pointfilter | 0.291008 | 0 | 250 | 0 |
| robust_mls | 0.531755 | 246 | 233 | 0 |

边界点数按两方向和37观察求和，裁剪归因和原坐标/保护/incident条件同时保留。接触、耦合、完整交点及艺术认可均为每方法37/37 unknown。

邻域与采样重复统计包含正常对照，各组为16、12、9例。模型/凹陷半径比只含有凹陷半径者，方向统计只含非空S，各项分母在JSON单列。

development_center的模型半径/凹陷半径逐例中位1.367，首步每例邻域数中位的中位580.0，500采样重复数相应中位0.0。S修正与目标位移点积为正的点观察602/888，每例修正RMS/目标RMS中位1.275。
validation_center的模型半径/凹陷半径逐例中位4.286，首步每例邻域数中位的中位2061.5，500采样重复数相应中位0.0。S修正与目标位移点积为正的点观察488/810，每例修正RMS/目标RMS中位0.917。
validation_offcenter的模型半径/凹陷半径逐例中位6.925，首步每例邻域数中位的中位2056.0，500采样重复数相应中位0.0。S修正与目标位移点积为正的点观察154/291，每例修正RMS/目标RMS中位1.037。

这些是保存输出的标签辅助解释统计。官方先验面向噪声点集过滤，当前输入为不均匀网格顶点与成片凹陷；半径尺度、稀疏邻域重复采样、修正幅度和正常区域移动均已实测。上述关系对训练分布差距提供证据，失败根因及可训练性仍无因果结论。[TRANSFER_DIAGNOSTIC.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/TRANSFER_DIAGNOSTIC.json)

## 唯一后续建议

提议同一Pointfilter架构和官方初始化进行一次合成凹陷领域微调。输入保留当前源邻域/PCA/500点与F，监督为配对参考给出的PCA局部位移，训练包含零目标正常样本和正常F点。建议沿现有231开发观察/117 Armadillo迁移验证划分，在下一合同计算前冻结例均衡凹陷位移与正常保持损失、权重和步数预算。原no-op/MLS收益、正常保持、固定域和全部incident质量共同验收。规划者独立复核后决定是否执行。[SUMMARY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/SUMMARY.json)

## 复核、恢复与成本

独立保存结果核验102538项通过，覆盖和最大数值差在核验记录中。新训练0，旧网络重调0，其他模型0，Bunny数组/评分0，Blender/产品/原资产编辑0，Google及付费API调用0。[INDEPENDENT_VERIFY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/INDEPENDENT_VERIFY.json)

初版PLAN后发现跨案例共享RNG会使第二步耗用影响后续首步样本，在任何新数组读取/前向前澄清为每例重置相同seed1729并重新冻结，初冻提交fcb0d4b5留存。准备中一次猜测旧文件路径和Windows rg glob失败已恢复，未执行模型。pip按私有target安装成功，随后补上子进程-B复跑保护，旧site自任务登记以来pyc写入扫描为0，原执行源码已归档。[PREPARATION_INTEGRITY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/PREPARATION_INTEGRITY.json)

成本包含获取/依赖、导入加载、全源构建、索引/PCA/采样、前向/恢复、MLS和评价，各阶段内外包含关系见COSTS。当前为单线程CPU质量筛选，独占窗口未确认；完整产品管线、同质量20%提速及货币成本仍未测。[COSTS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pretrain_001/COSTS.json)
