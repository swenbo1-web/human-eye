# M6-SHAPE-RING-001 固定外环与簇级证据探针

2026-11-15。基线`96d5249f2a08ead5ecde7e644e9a6b4f1f997c0e`，合同`8c47b6dd225b174edba6a3345c7bafe0bc6410d8`，PLAN冻结`1e9926a126a7d83725a69905a72136f7229376bf`，校准固定提交`ae5f5381905d3158791780f7e6549918f8867ab9`。

**外环深度信号与新定位组合均未达到事前目标。本批关闭这组固定外环/簇构造，唯一下一建议是复核已保留的Pointfilter凹陷领域微调方案。**

## 公式、输入与分母

固定231开发观察与117 Armadillo观察，共348例、42正常、42patch、5来源、109443个F点观察。正常校准只用33开发patch。四角色同未知上游组，patch重叠与幅度变体存在依赖，Armadillo是既有验证来源。[INPUT_WHITELIST.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/INPUT_WHITELIST.json)

两拟合分别使用完整当前源拓扑1–10跳与6–10跳全部点。原观测法向提升float64后单位化，用最不对齐xyz轴构造切向标架，共用1–10跳最大当前欧氏半径R。半径归一的鲁棒二次拟合为加权初值加三次Tukey IRLS，常数4.685/1.4826/1e-4固定，r=fR。所有F都保留，失败残差为0且另列。算法未读取参考、损坏mask、生成中心/半径或参考法向。

10548个唯一源ID的BFS跨patch与观察复用，BFS数组37682023字节，邻接数组29065968字节。两分支各109443次拟合全部可用，观测法向、R和面积无无效值。高条件数和合法曲面形状仍会影响信号，满秩只说明本次线性求解可执行。[RESIDUALS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/RESIDUALS.json)

## 单次正常校准

单点分数为abs(r)/ell。每分支用33开发正常的全部10405个F点计算线性q90种子，严格超过门限的点按F拓扑连接，连通时不先按符号拆分。至少5点的簇使用完整当前源面积，E=sum(A abs(r))/ell³，C=abs(sum(A r))/sum(A abs(r))，T=E C并赋给簇内点，其他0。T为归一化偏离统计。

| 配置 | q90种子 | q95操作点 | 校准正常误报patch | 验证正常误报patch |
| --- | --- | --- | --- | --- |
| solid_point | 1.903414 | 5.100104 | 2/33 | 0/9 |
| ring_point | 5.726252 | 11.036867 | 2/33 | 0/9 |
| solid_cluster | 1.903414 | 354.434737 | 2/33 | 0/9 |
| ring_cluster | 5.726252 | 1429.456261 | 2/33 | 0/9 |

每配置操作点为33正常patch最大分数的线性q95，严格大于才选中，四个校准操作点均为2/33误报。33个正常分数文件在校准后冻结并复用，另外315观察各生成一次分数。同一开发校准目标的比较保留了验证实际误报数。[CALIBRATION.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/CALIBRATION.json) [CALIBRATION_FREEZE.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/CALIBRATION_FREEZE.json)

## 标量深度信息

标签辅助目标d为(reference−observed)与观测单位法向的点积。下表是每组54个凹陷观察的逐例中位。两组有效支持点分别3345、1380，所有比值分母均有效，正常控制S为空。

| 子集 | 实心RMSE/零预测 | 外环RMSE/零预测 | 外环相对实心改善 | 外环RMSE/ell |
| --- | --- | --- | --- | --- |
| validation_center | 1.272073 | 2.380437 | -77.57% | 0.554955 |
| validation_offcenter | 1.487862 | 3.738803 | -152.56% | 0.526398 |

外环两组均未满足误差比中位≤0.85及相对实心中位改善≥10%。偏差、幅度、符号和合法正常F残差尾部全部保存。这里评价的是信号，重建面质量与修复收益仍待未来任务评价。

## 同F分母的定位

patch宏先平均各patch内有效凹陷例的指标，再对patch等权。点池包含该组全部F与正常控制。AUC缺少任一类时为空，AP无正类为空。表中均为普通S任务。

| 子集 | 配置 | patch宏AUC | patch宏AP | 点池AUC | 面积召回 | 零检出凹陷 |
| --- | --- | --- | --- | --- | --- | --- |
| validation_center | solid_point | 0.575948 | 0.320446 | 0.584105 | 0.00% | 54/54 |
| validation_center | ring_point | 0.537906 | 0.272861 | 0.553749 | 0.00% | 54/54 |
| validation_center | solid_cluster | 0.500000 | 0.197862 | 0.500000 | 0.00% | 54/54 |
| validation_center | ring_cluster | 0.500000 | 0.197862 | 0.500000 | 0.00% | 54/54 |
| validation_center | old_p | 0.722465 | 0.388410 | 0.688177 | 历史排序 | — |
| validation_offcenter | solid_point | 0.498471 | 0.143572 | 0.528156 | 0.00% | 54/54 |
| validation_offcenter | ring_point | 0.562720 | 0.141547 | 0.580962 | 0.00% | 54/54 |
| validation_offcenter | solid_cluster | 0.500000 | 0.081435 | 0.500000 | 0.00% | 54/54 |
| validation_offcenter | ring_cluster | 0.500000 | 0.081435 | 0.500000 | 0.00% | 54/54 |
| validation_offcenter | old_p | 0.701052 | 0.192950 | 0.687087 | 历史排序 | — |

外环单点在偏心组AUC较实心单点提高约0.064，AP略降且AUC仍低于0.80。中心组AUC与AP均下降。两种簇配置在中心/偏心分别没有保留≥5点的簇，分数全为0，AUC为0.5。四配置在108个验证凹陷的操作点面积召回全部0，精确率因无选择而为空，漏损面积与正常被选面积照实列出。旧p只读取原保存排序值。

强位移任务另将norm(reference−observed)>0.10ell定义为正类，其余同F为负类，弱损坏点计数单列。普通/强任务每例、patch宏、点池、中心/偏心、source、幅度与合法凹曲分层均保留。三个新配置的全部定位进入条件均失败。[EVALUATION.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/EVALUATION.json)

## 见证与范围

见证按开发正常最大T、验证中心/偏心最大深度误差三类选择。报告将主外环分支和RMSE/ell明确为选择规则的实施细化，PLAN没有单独固定这两个细节，ID并列时固定排序。保存的是当前几何、残差和分数。

| 选择规则 | 观察 | 选择值 |
| --- | --- | --- |
| development normal maximum ring T | Richie_patch_07/sample_00 | 1710.820944 |
| validation center maximum ring depth RMSE/ell | Stanford_Armadillo_patch_03/sample_04 | 3.337210 |
| validation offcenter maximum ring depth RMSE/ell | Stanford_Armadillo_patch_03/sample_07 | 2.313161 |

[WITNESSES.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/WITNESSES.json)

本轮结果限固定1–10/6–10跳、观测法向二次拟合与q90/q95面积幅度簇构造。未来学习型幅度映射和细节保持重建效果仍未测。纯法向零翻面的保证仍缺依据。本批生成修复输出次数0。

## 唯一下一建议

建议规划者复核已保留的一次Pointfilter凹陷领域微调立项，沿已授权合成正常/扰动配对监督、正常F零目标及原完整质量门槛推进。当前外环/簇构造关闭，训练效果交由后续固定合同验证。该建议当前仅供复核。[SUMMARY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/SUMMARY.json)

## 核验与成本

内部独立实现核验1217744项通过，含全10548 BFS缓存、348例几何/评分、2088次重复拟合、33正常校准与全部rank/AP/操作点/深度及判定。最大绝对比较差4.55e-13。另38项合成闭式/失败/混号簇/分位数/ties工具检查通过。规划者的独立复核仍待完成。[INDEPENDENT_VERIFY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/INDEPENDENT_VERIFY.json)

fit完整进程窗口wall 65.587856秒，worker树CPU 60.390625秒。
calibrate完整进程窗口wall 1.012105秒，worker树CPU 0.640625秒。
evaluate完整进程窗口wall 14.193885秒，worker树CPU 8.843750秒。
verify完整进程窗口wall 27.879248秒，worker树CPU 26.781250秒。

成本账本分别列共享源/拓扑/BFS/标架/R/面积与两种拟合边际，再列四配置score/聚簇/校准/评价边际。联合q90/q95、读取与保存窗口保持共享，独立完整成本按已有组件保守组合，独立冷跑实测仍缺失。验证末段指标核对包含在总成本，未单列子阶段。

首试合成QA在报告序列化遇到NumPy bool，原执行源与失败进程记录保留，仅将通过标记转为Python bool后恢复，断言和容差保持固定。另一次提前读取尚未创建的evaluate.py路径已记准备成本。恢复未读取真实标签或生成新拟合结果。交互/货币、部分准备CPU/峰值与最终写盘退出仍有缺测。[COSTS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_ring_001/COSTS.json)

训练、新神经前向、修复输出、Bunny数组/评分、Blender/原资产/产品、Google及付费调用均0。既有环境只读单线程，无新安装，独占窗口未确认。
