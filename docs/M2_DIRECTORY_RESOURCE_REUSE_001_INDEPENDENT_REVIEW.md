# M2-DIRECTORY-RESOURCE-REUSE-001 独立复核

日期：2026-11-15。结论：接受`not_actionable`，结束本次目录复用资格，不继续实施或性能测量。三个资源后目录候选已经由现有缓存覆盖；唯一真实重复例属于预登记兼容回归，没有目录参与后续业务的证据。这个出口符合原计划，不代表以后没有复用需求，也不是新的性能通过。

## 来源与本轮实际执行

作者提交`fde0e9ab21fb6eaee1750befd64ad1bebdde2961`，分支`codex/m2-directory-resource-reuse-001`，工作区`C:/Users/Administrator/.codex/worktrees/m2-dir-001/hefe`。基线为`8f2a739e789b777358d84a168154bc7c50b929e5`。

本轮根及两个独立复核只执行离线Git、标准库、协议、文件与源码检查。新产品调用、模型消费者、Blender及raster均为0；没有修改作者封存、安装或原资产。

| 独立工作 | 实际核验 | 证据 |
|---|---|---|
| 来源与零修改 | 280断言通过，347唯一文件；27个Git新增路径、26清单项、25直接artifact、12旧pin与141源核对 | [身份报告](../verification/fixes/20261115_m2_directory_reuse_001_review/identity/REVIEW.md)、RESULT.json |
| 轨迹与分母 | 337断言通过，190相关文件，其中187个核对原pin；重计M2业务记录并核读全部决定性候选 | [轨迹报告](../verification/fixes/20261115_m2_directory_reuse_001_review/trace/REVIEW.md)、RESULT_R2.json |

27路径都在本批证据namespace，产品差异0。141源与基线Git、作者树、`D:/he_source_face_001/product`一致，总摘要仍为`3748d88b618db7de1347d632f2a68f3ed82a2ebb8a6321586fe756be07ea8148`。没有新安装或隐含产品升级。

## 决定性证据

从原始M2结果重计为39测量会话（含预检）加3正确性会话，共42工程宿主；368业务读取另加1次typed shutdown。产品目录139次，98 hit、41 miss。321测量业务包含于368，不能再相加；资产重复也没有变成42个真实用户任务。

`entry_01/entry_02`两次directory_after_full之前都已有冷、热目录，后续目录`cache_hit=true`，状态与原目录一致。typed的directory_after_selected与hot保存字节相同。三项全部核查，不是抽样排除。

26次人为变更后的目录缺少旧resource stamp/pose快照，继续标unknown，不能只看同host就断言可以复用。

M4唯一技术例确有“nonplanar捕获→坏查询→ping→old_readonly_regression目录”，目录miss，与先前捕获同host/epoch/revision和对象。原HARNESS_PROTOCOL明确登记兼容回归，运行器222–225行只校验成功与纯文本，其后没有目录业务消费。原nonplanar unknown保留。额外1次to_mesh/4次world forward来自确定源码分支推断，未有独立运行计数或可删除时延。

原14个单文档JSON解码失败文件确为JSONL；本轮独立恢复79消息、37tools/call，无目录请求或capture_directory文本命中。消息数、协议副本、namespace和实际宿主是不同单位。M4全部26工程宿主及其全部归档未在本轮机械重验，所用原件已核对来源。

## 未执行和记录更正

本批初版候选0、追加优化0、正式六槽未运行，原因是事前自然任务门未满足；不是把资格审查充当优化轮。产品性能、内存、模型token与完整净收益未测。作者分析登记后981.312秒不含更早准备，也不能作为完整研发成本。

作者保留长worktree名失败、JSON盘点null参数错误与WindowsApps别名空输出。本轮身份检查曾误读AL字段层级；轨迹检查曾误读faces键、把两份汇总RESULTS计为宿主。修正后的有效结果通过，原脚本/失败结果均保留；这些不是产品失败。

作者AL仍未绑定，登记pending。根任务`f2ac3511-ed05-469e-9a8b-710340bd4bed`已登记；复用子agent的AL assignment仍属于旧任务，报告如实披露当前明确委派与旧归属，不追认已续绑。实际离线工具没有执行保护拒绝。

## 下一项

按[M1–M5统一路线](M1_M5_PROGRESS_AND_NEXT_PLAN_20261115.md)，不再搜索更多目录例子或扩大测试。下一批为[M4目标驱动采集](M4_TARGET_ACQUISITION_001_PLAN.md)：目标决定视窗，以廉价范围排除不可能进入任何目标视窗的对象，必要遮挡物继续详细读取；先完成相同目标合同的全量参考，再做一次选择性采集优化。旧完整扫视模式保留，M6不参与。
