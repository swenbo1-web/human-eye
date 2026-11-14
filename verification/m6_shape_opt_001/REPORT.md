# M6-SHAPE-OPT-001 结果与去留

2026-11-15。固定合同提交 `a2d0c9b8dd67ba4da63a0d57a7cd1f4d6f86c818`，首轮提交 `9c29a9f0990421c607ee821e838394e73dcaa9f3`，本批训练前冻结提交 `2a8b9811e5080f3d0f26d14c56edd0a657a3935b`。最终交付提交记于提交后本地 `HANDOFF.json`。工作树为 `C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe`，分支 `codex/m6-model-selection-001`。

**本次唯一优化完成，局部修复质量失败，关闭当前学习候选。** 固定门限下117个验证例均为逐位无操作。首轮加本批累计两次正式训练，本批优化训练一次、1200步，Bunny模型与MLS评分累计为0。当前去留判定为 `close_current_learning_candidate_after_one_optimization`。

## 实际模型与训练

沿用宽24、K12共享cell及原alpha/beta修正头，原6290参数后追加零初始化 `Linear(48,1)` 定位头49参数，总6339。定位输入是最终和初始隐藏状态拼接，输出分数 `p=sigmoid(z)`，条件向量为 `u`。训练输出 `p*u`，最终输出使用固定 `p>tau` 门控的完整 `u`。分数提升到float64后与保存的float64门限比较，等号处输出零。固定和halo顶点硬零，binary64回写只加非零分量。

seed1729下，20个旧状态张量、6290个参数值与首轮step0逐位相同。正式训练从此初态开始。原六项前向输入白名单、18个仅训练数据拟合的归一化量、231训练例及1200批序列逐项核对。每批四成员各一图，其中一个正常对照与三个凹陷。四角色文件仍为一个未知上游来源组。

损失保留原逐图软输出目标与0.05边梯度项，增加0.4支持域条件向量平方误差均值，以及0.05定位BCE。损坏图的支持域与正常自由点组等权，正常图只用自由点负类。空组、各分母、原损失、新增条件项、定位项、总损失、梯度和学习率均写入1200条日志。不同监督目标的总损失值只作为本轮训练记录。

CPU float32、单线程、AdamW及余弦1200步、梯度裁剪1均沿用合同。正式训练失败0次、重试0次，最终权重固定为step1200。step0/400/800/1200软输出及定位诊断全部保留，中途开发集为固定8例，最终开发集为231例，每次验证均117例。结构、旧初态、六输入、零输出、旋转、排列、批隔离、定位及修正头梯度、门控与空分母QA通过。合成QA另有一次独立SGD更新，正式训练计数单列。[训练记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/TRAIN_LOG.json) [QA](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/MODEL_QA.json)

最终权重为106198B，SHA256为 `a82f2d5d4f27e1e7f4be6cf74999f4a488edf5fdcbf38f92fed9264046a153ff`。最终评价和在线调用后继续核对同一身份。[权重](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/private/weights/step_1200.pt)

## 单次校准

固定末步权重后，仅遍历33个训练正常控制的全部10405个自由点，读取观察输入与自由域掩码。NumPy linear 99.5%分位数为0.7364127039909363，因此 `tau=max(0.5,q995)=0.7364127039909363`。严格大于门限的训练正常自由点53个。校准一次、门限候选一次，验证与测试用于校准的点数为0。保存了每个控制的分数、分母及散列。分数用于定位排序，其概率校准性质未知。[校准记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/LOC_CALIBRATION.json)

## 最终硬输出质量

S为真实损伤支持点，A为允许修改域，N为其中原本正常点，N_F为原本正常自由点。每个凹陷例先计算相对no-op误差比及改善，再求中位数、p95和最大值。正常对照的S分母为空。

| 子集 | 凹陷/正常 | S误差比中位 | p95 | 最大 | A改善中位 | 正常点门槛失败 | 正常控制失败 | 逐位无操作例数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 开发中心 | 198/33 | 1.0000 | 1.0000 | 1.6880 | 0.00% | 47/231 | 7/33 | 169/231 |
| Armadillo中心 | 54/9 | 1.0000 | 1.0000 | 1.0000 | 0.00% | 0/63 | 0/9 | 63/63 |
| Armadillo偏心 | 54/0 | 1.0000 | 1.0000 | 1.0000 | 0.00% | 0/54 | 共用中心9控制 | 54/54 |

两个验证子集的支持中位≤0.70、来源中位≤0.85、A改善中位≥20%、相对冻结MLS支持改善≥10%均失败。支持p95/max门槛、正常点保护、固定边界和面质量门槛通过，其实际输出均为零。完整逐例A/S/N/N_F RMSE、p95、最大值、来源、幅度与位置分层均保留。[逐例与门槛](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/RESULTS.json)

开发集26/198个凹陷S误差下降，正常控制最大A RMSE/scale为0.13134876，正常自由点最坏p95/scale为0.44460317、max/scale为0.63102252。开发集出现437个相对输入的面法线翻转，分布于21例，同源面可在不同变体重复计数。新增退化面0。验证中心及偏心新增退化面和法线翻转均0。全部348例的固定、边界和域外坐标逐位保持，incident面覆盖完整，整例推理回退0。

首轮历史结果原样保留。其开发/中心验证/偏心验证S误差比中位分别为0.7951/0.8597/0.7778，A改善中位分别为−53.35%/+4.07%/−25.10%。本批硬门控解决了验证误改，同时使验证修复召回归零。冻结MLS仍沿用原校准tau0.9266132396947365，验证117例全部为no-op。[首轮固定结果](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_train_001/RESULTS.json)

## 定位诊断

| 子集 | TP | FP | FN | TN | 精确率 | 召回率 | FPR |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 开发中心 | 129 | 237 | 5913 | 66556 | 35.25% | 2.135% | 0.3548% |
| 验证中心 | 0 | 0 | 3345 | 16367 | 空分母 | 0% | 0% |
| 验证偏心 | 0 | 0 | 1380 | 15516 | 空分母 | 0% | 0% |

计数域为自由点，源顶点可在同patch的合成变体重复出现。117个验证例所有自由点分数均低于固定门限，4725个受损点全部漏检。中心S分数中位约0.4083、最大约0.6625，偏心S分数中位约0.4116、最大约0.6323。定位分离不足在训练池已存在，固定操作点开发召回仅2.135%。

保存的step1200软输出中心/偏心S误差比中位约0.8229/0.7607，A改善中位约+5.04%/−41.61%。从保存的u计算支持域条件残差诊断，中心/偏心比中位约0.7836/0.6773，但p95约1.631/2.513。此诊断仅描述现有分量，推理门控始终使用固定tau。额外真实前向、门限试探及训练更新均0。[保存分量诊断](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/DIAGNOSTIC_RESULTS.json)

## 实际最坏视图

四行依次为开发最坏支持误差比、验证中心最坏支持误差比、验证偏心最坏支持误差比、正常控制最坏N最大误差。验证支持比全部并列为1，按冻结规则以case ID字典序选择。开发为Yanyite_patch_07/sample_01，正常控制为Chipow_patch_03/sample_00。五列为参考、no-op、冻结MLS、首轮、本轮硬输出。同一行共享相机，所有方法使用共同显示尺度及完整视口。指标使用观察中位边长，显示使用局部平均边长。实际三角形深度栅格绘制，图像及来源散列已核验。

![最坏真实网格对比](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/private/renders/RESULTS/WORST_COMPARISON.png)

## 成本与失败记录

复用已锁CPU环境和公共源缓存，本批安装、wheel下载与源下载均0。训练外层进程wall80.4265秒，进程树CPU73.140625秒，实际Python峰值工作集547983360B，含规定软评价的预算循环74.1441秒。训练main wall79.5380秒、CPU72.3125秒，main计时的导入范围与外层计时分别记录。训练嵌套阶段wall包括前向23.9394秒、损失3.0881秒、反传/裁剪32.6340秒、优化器0.7812秒、检查点0.0110秒、评价12.0395秒。单次校准主体wall0.3736秒、CPU0.234375秒，含启动外层wall1.8235秒。

八次阶段执行含两次失败渲染，按顺序外层main窗口wall合计112.7938秒，阶段进程树CPU合计103.375秒。阶段外层监控进程生命周期CPU在最终写盘前另计16.5625秒。在线阶段树已包含六个worker与其驱动，成本汇总采用嵌套范围避免重复相加。独立审查及合成QA的成本单列。最终打包、交互、全部研究费用、部分合成QA外层CPU/峰值仍有缺测，完整研究总成本未知。[完整成本记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/COSTS.json)

| 方法 | cold次数 | cold中位/p95秒 | warm次数 | warm中位/p95秒 | 实际worker峰值工作集B |
| --- | --- | --- | --- | --- | --- |
| 本轮模型 | 3 | 3.4503 / 3.6196 | 9 | 0.22252 / 0.23756 | 491679744 |
| 冻结MLS | 3 | 1.4060 / 1.4065 | 9 | 0.28250 / 0.29409 | 236474368 |

相同三例按既定顺序交替方法，每次重建完整172974顶点观察网格动态特征，恢复完整源数组，保存并回读完整候选。24个调用的输入白名单及坐标保持检查均通过。cold指新进程，OS文件缓存与其他机器负载未控制。三组cold配对模型减MLS差中位2.0591秒、p95 **2.2151秒**，九组warm配对差中位−56.81ms。首轮cold配对差p95约2.1931秒属于历史账本。跨批绝对耗时缺少相同运行条件，完整产品收益尚未建立。[在线原始记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/ONLINE_RESULTS.json)

渲染入口实际失败两次。首次训练venv缺Pillow，第二次切换已有primary Python后遗漏必需的RESULTS参数。第三次使用已有渲染环境并补齐参数成功，三次渲染worker外层wall分别0.1759、0.5647、1.6544秒，失败记录和CPU/内存均保留。`run_phase.py`的渲染运行时与参数入口已修正。模型、损失、训练、校准、评价和计划继续按训练前冻结身份核对。正式训练重试0次。[恢复记录](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/RECOVERY_LOG.json)

## unknown与交接

公共源继续使用原生坐标，物理单位未知。现有耦合入口要求米制frame，已知不兼容状态沿用，本批新增耦合验证与端点查询均0。完整修复、保留测试与完整任务额外p95≤2秒验收均为unknown。首轮安装后代进程CPU/RSS缺测继续保留。本批共享GUI、原资产动作、正式产品动作和付费API调用均0。

全部新增交付集中在本批目录。原TRAIN001记录、模型、MLS、数据、环境及原始资产身份由旧清单逐项复核。公开清单记录源码、日志与指标，几何、权重、分数、输入输出及图像保留本地私有文件并逐件记录散列。[身份清单](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/EVIDENCE_MANIFEST.json) [独立算术核验](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_opt_001/INDEPENDENT_VERIFY.json)

按首版加一次优化的停止点，当前候选关闭。后续研究仅建议先独立检查现有观察特征对跨源损伤支持域的可辨识性，再由规划复核决定是否重新立项。交付固定提交后一次回报规划对话，结束本批等待独立复核。
