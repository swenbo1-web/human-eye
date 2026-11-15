# M6-PERCEPTION-001 冻结编码器定位与区域事实

2026-11-15。基线`7ae143a6b062ac3c9fedcbf50939b79082884963`，合同`9f0d2cc3dcd9d7c0213c4fe62ad24af7b85ac077`，PLAN`cf9ad6c5ac2c64915fb883dfac41d91272d9ce3f`，开发训练/校准固定提交`6fa798646795d17081c1cf2cc7ce66f34dd7e53d`。

**新头的A检查注意力和B阈值异常判定均未通过预定质量目标。348例可读区域与引用契约核验通过。当前权重未形成可用的插件感知候选。**

## 范围与固定模型

完整分母为231开发训练、117既有Armadillo迁移验证，共348观察、42patch、42正常、109443个F点观察。四人物同未知上游组且重叠patch/幅度变体相关，Armadillo已在多轮研究使用并与官方预训练图形状重合。当前范围为指定F的合成凹陷定位，整场景扫描、人体部位语义及人/动物全类型覆盖仍待验证。[INPUT_WHITELIST.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/INPUT_WHITELIST.json)

官方Pointfilter固定提交`6e0ec1eac59ca9f81ee9ca6751c5b3f25effeda2`。只执行702464参数encoder，1024维输出，参数与BN全冻结eval。唯一新头为1024→64 GELU→1，共65665可训练参数，活跃总计768129。官方完整checkpoint另含未调用的decoder，文件中总参数1360899。编码器实际提取1816批，开发中12个F点观察不可用，以0保留，验证不可用0。[FEATURES.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/FEATURES.json)

完整当前源bbox对角×0.05半径，官方PCA及500采样，每case重置RandomState1729，按F源ID升序，邻域≤500有放回，其他无放回。输入仅当前观察坐标及任务查询ID，参考、损坏mask和生成参数进入encoder次数0。特征float32，开发231的全部F用于float64两遍mean/std，std<1e-6除数置1，标准化后转float32。验证标签与统计参与训练次数0。

一次seed1729训练1200步、batch1024、AdamW 1e-3/1e-4，每样本先均匀case再均匀F。case等权π=0.0832036021，正类权重11.0187104196，BCEWithLogits保留弱损坏与正常负例。唯一评价权重为最终1200步。[TRAIN_LOG.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/TRAIN_LOG.json)

encoder初终canonical tensor SHA均为`9f33d63beccc4a25a5e7d64be910632e761c39fd08a41d58933d71936fcefe31`，含BN缓冲。head初态文件SHA `43bcf62567d2740c5e17d391f00a1ab98a26e0730dda86dad332db74231dc603`，最终文件SHA `8fcfb1d3ee90e074ad0510202926608e9634b771a4f06a8b1979601cd1ade602`，最终tensor SHA `c908509fcfebe98d0be3f7802eefbba28e1abdf466360eef259d0979b5d59932`。归一文件SHA `b603b2368e2c018880c5c671175b829ad2097b1a03c20b6e883fe1732363c145`。[MODEL_IDENTITY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/MODEL_IDENTITY.json)

## A 同25%面积预算的检查排序

四分数在同F用当前完整源lumped面积，score降序、source ID升序，取面积≤25%的排序前缀，下一点超限即停止。正常例也给检查候选，候选性质为待核查。下表为普通S的patch等权宏，先平均patch内有效例再平均patch。点池、每例及面积/ell²汇总另存。

| 组 | 分数 | 宏AUC | 宏AP | 宏面积召回 | 零命中凹陷 |
| --- | --- | --- | --- | --- | --- |
| development_center | perception | 0.993425 | 0.902288 | 96.67% | 0/198 |
| development_center | old_p | 0.682505 | 0.245121 | 42.94% | 20/198 |
| development_center | solid_point | 0.520531 | 0.135262 | 23.96% | 59/198 |
| development_center | ring_point | 0.551878 | 0.139936 | 23.93% | 56/198 |
| validation_center | perception | 0.604910 | 0.273536 | 26.88% | 1/54 |
| validation_center | old_p | 0.722465 | 0.388410 | 47.29% | 0/54 |
| validation_center | solid_point | 0.575948 | 0.320446 | 33.15% | 0/54 |
| validation_center | ring_point | 0.537906 | 0.272861 | 26.14% | 1/54 |
| validation_offcenter | perception | 0.510580 | 0.148940 | 28.63% | 21/54 |
| validation_offcenter | old_p | 0.701052 | 0.192950 | 45.87% | 0/54 |
| validation_offcenter | solid_point | 0.498471 | 0.143572 | 24.36% | 3/54 |
| validation_offcenter | ring_point | 0.562720 | 0.141547 | 30.33% | 8/54 |

中心与偏心各自的AUC≥0.80、AP较旧p增加0.05、宏面积召回≥0.60并较旧p增加0.10均失败。新头开发排序与召回较高，迁移验证明显下降，现有记录未确定编码器、头容量、损失或来源分布中的唯一失败原因。旧p与几何分数均只消费保存结果，未重新训练。

强损坏任务使用norm(reference−observed)>0.10ell作为正类，其余同F为负类，5740个强正例与5027个弱损坏负例均保留。普通/强任务的每例、patch宏、点池、source、幅度、合法凹曲分层、最大漏检片区及并列情况都在完整评价中。[EVALUATION.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/EVALUATION.json)

## B 固定阈值异常报告

只用33开发正常patch最大新score的线性q95得到0.9995625138，严格超过才选择。开发正常复用训练数据，校准误报为依赖样本上的描述。验证正常误报1/9，正常误报门槛通过。score为未校准异常分数。[CALIBRATION.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/CALIBRATION.json)

| 组 | B宏面积召回 | 零命中凹陷 |
| --- | --- | --- |
| development_center | 2.71% | 140/198 |
| validation_center | 1.17% | 48/54 |
| validation_offcenter | 1.49% | 48/54 |

中心和偏心B宏面积召回均未达0.60。空结果、无选择时精确率为空、正常误报及漏检面积完整保留。A与B各自未通过，当前候选的感知消费与可靠异常判定均缺达标证据。

## 可读区域与稳定引用

已输出348例精简事实、全部A/B区域和2324个可回读引用。A区域按sum(area×score)降序、最小source ID并列，文本最多3个区域并列其余数量与覆盖。B阈值预测单列。几何量由当前点实际求得，疑似凹陷标为模型预测，身体部位名与原因故事生成次数0。原始embedding未作为普通事实文本。

| 固定抽查观察 | A区域 | B区域 | 文本 |
| --- | --- | --- | --- |
| Chipow_patch_00/sample_00 | 3 | 1 | [facts.md](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/private/region_reports/Chipow_patch_00/sample_00/facts.md) |
| Stanford_Armadillo_patch_00/sample_01 | 3 | 0 | [facts.md](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/private/region_reports/Stanford_Armadillo_patch_00/sample_01/facts.md) |
| Stanford_Armadillo_patch_00/sample_07 | 4 | 0 | [facts.md](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/private/region_reports/Stanford_Armadillo_patch_00/sample_07/facts.md) |

引用绑定来源、观察SHA、F源ID、encoder/head/归一身份与区域源ID。resolve_region.py可回读同版本当前几何。质心采用当前lumped面积加权，零面积时显式回退顶点均值，bbox实算。三例文本已实际查看，其余字段与所有引用机器核验。普通事实保留原生坐标、面积平方单位和物理尺度unknown。[REGION_REPORTS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/REGION_REPORTS.json) [MANUAL_REPORT_QA.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/MANUAL_REPORT_QA.json)

区域契约核验45890项通过，覆盖2324引用。A选中点观察27012，B选中点观察415，其中两用途可能重复。B空观察273。当前LLM消费者评测、产品/MCP接入与完整任务净收益均未运行。[REGION_VERIFY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/REGION_VERIFY.json)

## 内部复算与完整成本

内部公式复算通过，含1044个已有查询的官方encoder重放、37例PRETRAIN首次采样对照、全部109443个head logit、开发双遍统计、1228800采样对、首批初态BCE和全部A/B指标。额外optimizer step与完整训练重放均0。逐元素比较及检查计106399703，最大绝对差3.34e-06。规划者独立复核仍待完成。[INDEPENDENT_VERIFY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/INDEPENDENT_VERIFY.json)

特征缓存402486421字节、采样/PCA缓存602056843字节，首次提取成本保留。17项合成引用I/O与空结果检查通过。
features完整窗口wall 626.171168秒，worker树CPU 616.578125秒。
train完整窗口wall 17.021304秒，worker树CPU 15.015625秒。
predict完整窗口wall 4.112271秒，worker树CPU 3.031250秒。
evaluate完整窗口wall 11.242239秒，worker树CPU 9.140625秒。
regions_final完整窗口wall 11.930658秒，worker树CPU 3.781250秒。
verify完整窗口wall 40.607747秒，worker树CPU 39.500000秒。
verify_regions_final完整窗口wall 2.762861秒，worker树CPU 2.640625秒。

COSTS保存逐case取数、索引、PCA、encoder、cache、head读取推理与区域报告，以及共同加载、1200步训练、校准、评价和核验。缓存供训练重复使用的首次代价继续计入，头耗时只是一部分。现有CPU单线程、共享机器，正式提速与LLM端到端净收益仍未测。[COSTS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/COSTS.json)

报告呈现修正将空余区域面积改为直接求和，使空集合精确0，并补单位状态。原348份报告/目录、原执行源码与成本保留，2324条引用及几何记录前后一致。另一次只读比对误用references字段后改为实际regions字段，未新增模型或评分。准备阶段工具字符上限与未建目录读取、子agent线程上限均已恢复并记缺测。[REGION_REFINEMENT.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/REGION_REFINEMENT.json)

## 唯一下一建议

建议先定义来源独立的感知定位数据与留出验收合同，纳入新来源正常几何、合法自然凹曲负例及合成异常配对区域标注，并冻结来源组划分。当前首版权重停止进入感知消费，候选后续由规划者根据新证据决定。合成正常/扰动配对监督持续有效，真人艺术修正记录对应另一层艺术验收。[SUMMARY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_perception_001/SUMMARY.json)

本批学习候选与训练仅1次、1200步。encoder/BN更新、decoder调用、修复输出、Bunny评分、LLM消费、原资产/Blender/产品、Google Key/API及付费调用、新依赖均0。
