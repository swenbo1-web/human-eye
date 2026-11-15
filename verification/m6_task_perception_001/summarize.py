"""Build the final task-facing perception report from fixed evidence."""

from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write
from collect_costs import collect


def main():
    evaluation=read("EVALUATION.json")
    first=read("EVALUATION_v1.json")
    second=read("EVALUATION_v2.json")
    verification=read("VERIFY.json")
    focus=read("FOCUS_QA.json")
    score=read("CONSUMER_SCORES.json")
    author=read("AUTHOR_PLAN_REVIEW.json")
    costs=collect()
    write("COSTS.json",costs)
    v1=evaluation["initial"]["validation"]["methods"]["learned"]
    v2=evaluation["optimized"]["validation"]["methods"]["learned"]
    baseline=evaluation["optimized"]["validation"]["methods"]["geometry"]
    def pct(value):
        return f"{100*value:.3f}%"
    comparisons=[]
    consumer_localization=[]
    for row in score["route_by_entrypoint"]:
        comparisons.append(f"| {row['route']} | {row['entrypoint']} | {row['valid_completions']}/{row['denominator']} | {row['complete_nonempty_geometry_deliveries']}/{row['denominator']} | {row['measured_consumer_wall_sum_s']:.3f} |")
        if row["entrypoint"]=="inspect":
            consumer_localization.append(f"{row['route']} {pct(row['damaged_inspect_primary_mean_recall'])}")
    cold=costs["runtime_entrypoints"]["requests"]
    text=f'''# M6-TASK-PERCEPTION-001

## 本批结论

可运行的当前几何感知原型、两版固定权重、inspect/focus接口、逐例引用、8题三路消费者原回答与成本已交付。优化后的学习定位器未达到冻结采用门槛，按本批合同收口。定向细读的16个正常/受损目标均可读取，298项引用与测量检查通过。此路径直接计算几何，模型调用为0。

固定合同为 `28b44c9db9bdc3a3c8e934c18bd87add6f93fb9c`，基线 `a463116f52cc954812cfb6f54513ecfea0eb46ef`，训练前PLAN提交 `3f79fe14bae4b438a57028122f5defe9b7ee35fd`，首版结果及唯一优化绑定提交 `de2fb746d262d0d0b5c7aa56d7ff2c623d8d950b`。来源用户消息为 `01a1df72-5e51-7802-9c91-5f62e9234d2a`，用户确认明显异常查找与正常部位精修都属于感知前端目标。

```mermaid
flowchart LR
  A[当前完整几何与检查范围] --> B[inspect 多尺度表示与定位]
  A --> C[focus 明确目标与保护范围]
  B --> D[当前测量与区域引用]
  C --> D
  D --> E[大模型理解与操作计划]
```

## 表示、训练与一次优化

每观察一次计算当前全网格集总面积、面积法向及KDtree，批量查询384个F点的最大1024近邻。16、48、128、384、1024五尺度复用近邻前缀，生成法向相对高度、法向变化、PCA形状量、外环二次拟合残差及半径/R16等16通道。R16指包含查询自身的第16返回近邻距离，第一尺度的log比值恒0。外环取距离至少0.6当前半径，二次拟合使用1e-6 ridge。小尺度有1525个查询环带少于6点，最少2点，均按冻结正则解保留。其他尺度最少8、18、34、260点。

共享编码器为 `16→32→32`，GELU激活，对所有点和尺度使用同一权重。五个32维表示拼接后由 `160→64→1` 输出定位logit，总11969个可训练参数。模型从头训练，预训练组件0。输入特征由当前相对几何取得，绝对对象坐标、源ID、原对象bbox、未受损参考和生成参数均不进入网络。设计采用多尺度上下文思路，运行实现与实际通道、源代码及参数身份分别封存。[多尺度点集学习原论文](https://arxiv.org/abs/1706.02413)

直接复用DATA001的600观察、503有效凹陷配对、24正常、三派生组。开发338配对加16正常，迁移验证165配对加8正常。73个无效凹陷保留在清单与预测原件中，评分用途明确标记。每版1200步，batch1024，两状态按原保存配对点索引精确等权。两版相同seed1729、相同初始化、相同归一化与相同抽样。新的开发层次期望正标签先验为0.03994606075984517，pos_weight为24.03375754650697。

首版开发正点配对的间隔1违反比例为62.107%，平均logit间隔1.70725。优化绑定仅依据开发证据，第二版在同一BCE目标上增加0.1配对正点hinge排序项。共执行两次候选训练，优化器训练重放0，后续候选0。优化后开发间隔违反比例为59.689%。实际BCE与排序损失、逐步记录、初始/最终权重和优化器状态均保留。[BCE官方说明](https://docs.pytorch.org/docs/2.15/generated/torch.nn.BCEWithLogitsLoss.html)

最大1024近邻在全部503有效凹陷的所有F查询中均包含未受损支持外点。旧单尺度中心查询完全受损的8/338与55/165差异被独立复算并保留。当前覆盖事实与迁移质量分别报告。欧式邻域仍有跨近邻薄片风险，二次拟合ridge与切平面选择也带来有限数值方向依赖。两个预定查询的刚体变换诊断在1e-4容差内，完整任意旋转不变性保持未证实。

## inspect的全部验证结果

下表均使用冻结165个有效受损观察的等权宏平均。25%面积预算按当前全源三角集总面积分配，三路相同F与相同预算。几何对照为五尺度外环二次面中心残差模的最大值，尺度选择依据在训练前固定。

| 验证指标 | 首版 | 一次优化 | 几何对照 |
| --- | --- | --- | --- |
| 点AUC宏均值 | {v1['AUC']:.6f} | {v2['AUC']:.6f} | {baseline['AUC']:.6f} |
| 点AP宏均值 | {v1['AP']:.6f} | {v2['AP']:.6f} | {baseline['AP']:.6f} |
| 25%面积注意召回 | {pct(v1['area_budget_recall'])} | {pct(v2['area_budget_recall'])} | {pct(baseline['area_budget_recall'])} |
| 注意零命中例 | {v1['zero_attention_hit_cases']}/165 | {v2['zero_attention_hit_cases']}/165 | {baseline['zero_attention_hit_cases']}/165 |
| 严格阈值异常面积召回 | {pct(v1['anomaly_area_recall'])} | {pct(v2['anomaly_area_recall'])} | {pct(baseline['anomaly_area_recall'])} |
| 受损例有阈值报告 | {v1['anomalous_damaged_cases']}/165 | {v2['anomalous_damaged_cases']}/165 | {baseline['anomalous_damaged_cases']}/165 |
| 正常误报 | {v1['normal_false_cases']}/8 | {v2['normal_false_cases']}/8 | {baseline['normal_false_cases']}/8 |

每版阈值取16个开发正常观察最大分数的q95 higher，因此实际等于这些最大值中的最大值。比较用严格大于，概率未做校准。几何对照同类操作点的误报仅作为数值对照，消费者几何事实接口交付注意候选。学习接口另列阈值预测及未确认性质。

优化使注意召回增加{100*(v2['area_budget_recall']-v1['area_budget_recall']):.3f}个百分点，较几何对照差{100*(v2['area_budget_recall']-baseline['area_budget_recall']):.3f}个百分点。60%召回、相对几何提高10个百分点、正常误报最多1/8这三项均未通过。8个ROI等权旁列表中优化召回为36.459%，几何为40.585%，原门槛分母保持165。

按来源，cat为84例，优化召回28.327%，几何34.380%；lion为81例，优化46.350%，几何49.351%。按已有凹陷/旧编码器半径诊断分组，r/R≤0.5的47例优化35.973%、几何19.612%，0.5＜r/R≤1的42例优化28.308%、几何32.318%，r/R＞1的76例优化42.817%、几何60.608%。全部逐例、正常误报、不可用状态和尺度组均保留。此处来源与尺度数据只用于说明，额外模型选择和训练次数均为0。

## focus、引用与运行入口

目标由任务提供的源点ID绑定。预定16个请求覆盖验证8个正常ROI及各自固定受损观察，使用相同的64点拓扑BFS目标，F其余部分为可观察保护背景。全部目标可读、面积/面积重心/bbox/面积法向和当前坐标精确匹配，一环周边可追加读取。引用绑定当前顶点、拓扑、F映射、点集、角色与来源，缓存版本变化会拒绝旧绑定。部位语义识别与美术精修成功仍无验收结论。

全部600观察另行物化了geometry/perception两路共1200份检查报告，覆盖24正常、503有效凹陷及73保留无效观察，12127个不同区域引用均已实际解析。索引为 `INSPECT_REPORTS.json`，结构化原件位于 `private/inspect_reports/`。所有这些调用使用已固定的预测缓存，数值准备与模型推理成本另有原阶段记录。

`prototype.py` 可读取新的当前NPZ，通过 `inspect` 真实准备表面特征并运行固定v2，或通过 `focus` 直接读取任务目标。缓存绑定当前字节、模型及源代码身份，引用可跨进程解析。本批验证了冷调用、缓存调用、直接focus及resolver四个独立子进程入口，预测与批量缓存逐位相同。

```powershell
& 'verification/m6_shape_train_001/private/venv/Scripts/python.exe' -I -B -X utf8 'verification/m6_task_perception_001/prototype.py' --input 'verification/m6_task_perception_001/private/consumer_cases/t02/input.npz' --entrypoint focus
```

当前NPZ采用vertices、faces、F_source_ids或F_ids，并可带target_ids与protected_ids。也可用CLI显式传目标和保护ID。返回runtime.request_directory后，通过 `--request-directory` 与 `--resolve-reference` 追加精确读取。weights与大缓存位于本机私有目录。

## 八题三路完整消费

固定4题inspect、4题focus，均含正常和受损。三路使用相同当前数据、别名、题意、输出schema、gpt-6.1-sol medium配置和6次工具调用上限。通过已有ChatGPT登录CLI入口执行，原生可使用合理NumPy/SciPy算法。事实路线增加当前测量和引用，学习路线在inspect增加固定v2候选输出，focus均为直接几何读取。

| 路线 | 入口 | 有效完成 | 完整非空几何交付 | 会话墙钟秒合计 |
| --- | --- | --- | --- | --- |
{chr(10).join(comparisons)}

完整非空几何交付要求当前定位、预定测量、引用或原生显式点集形式及schema同时成立。空集和无法评分保留，正常是否明确断言异常另列，计划文本审阅也独立于数值定位。每题每路只执行一次，主分母24。原回答、调用、请求/响应、usage、错误和退出清理位于private/consumers。

两道预定受损inspect题的合法预算下消费者选择面积召回分别为{'、'.join(consumer_localization)}。两道正常inspect题三路明确异常断言均为0。四道focus题三路各4/4精确绑定目标并完成测量。两题受损消费者结果与全165例局部评价分别保留，候选采用结论仍依据冻结全量门槛。作者计划文本审阅为23份pass、首题原生1份partial，数值定位与文本计划分栏。

首题t01/native有4/6次工具因自设Python执行器兼容性错误失败，额度耗尽后给出空候选和待补读说明。该单元受基础设施干扰，仍保留在主分母。执行器已修正，原prompt及回答重放0，四个失败及修复前源码完整保存。对修复后的本地原Python片段诊断成功，原消费者答案保持原样。首题三路差异含此干扰，整体结果对候选增益的解释受此限制。

`CONSUMER_SCORES.json` 为作者自动几何/schema/引用与成本核验。`AUTHOR_PLAN_REVIEW.json` 为同一实施作者团队的文本计划判断。全部原回答供规划侧后续盲化独立复核，内部审阅token与费用保持未测。正常focus直接路径单列，其结果对应几何控制能力。

24个CLI父进程和读取线程均已回收，独立CIM检查本批相关活进程为0。MCP最终EOF关闭回执24份均未确认，完整CLI子树CPU/RSS也未测，原状态与未知项保留于 `CONSUMERS.json`。

## 完整成本与恢复记录

受监控数值阶段墙钟合计{costs['numerical_controller_wall_sum_s']:.3f}秒，上限7200秒；树CPU合计{costs['worker_tree_CPU_sum_s']:.3f}秒，采样同时树RSS峰值{costs['maximum_sampled_simultaneous_tree_RSS_bytes']}字节。单线程研究工作进程，非独占主机。全部600观察的共享特征与上下文缓存准备{costs['shared_feature_preparation']['controller_wall_s']:.3f}秒，两次训练含开发诊断{costs['training']['wall_s']:.3f}秒。

单个固定任务的独立进程冷inspect为{cold[0]['wall_s']:.6f}秒，缓存inspect为{cold[1]['wall_s']:.6f}秒，直接focus为{cold[2]['wall_s']:.6f}秒，resolver为{cold[3]['wall_s']:.6f}秒。冷调用包含真实表面准备、Torch首次加载、模型与引用，缓存调用包含版本核验。这是一例本地原型测量，正式插件冷启动保持未测。

消费者24个会话墙钟合计{costs['consumer_sessions_wall_sum_s']:.3f}秒，按路线及入口逐例保留实际token、cached输入、输出与工具次数。费用未暴露，保持unknown。工具、引用读取、Python执行和回退已包含在会话墙钟，细分为嵌套记录，不重复相加。全600观察准备成本单独完整列入，一次共享准备与训练和批量推理分项。8题子集独占准备成本保持未测，缓存读取没有被当成完整冷准备成本。

磁盘快照{costs['total_new_disk_bytes_snapshot']}字节，current/features/model/predictions/request_cache/consumers分别统计于COSTS。权重、大数组、上下文缓存和原回答留在private，Git只提交源码与统计/报告。数据重新下载0、原资产修改0、产品修改0、Blender动作0、Google或其他API恢复0。

通用CLI测试有两次可恢复错误，先是F_ids别名接入，再是Windows长引用路径。原脚本、错误、首次真实特征与预测成本均留档，之后短缓存键加完整身份核对的入口通过9项检查。模型训练共2次；额外验证只重放1200次推理，训练重放和优化器step重放均0。固定推理与证据复核{verification['check_count']}项通过，600观察的两版预测共460800个点概率逐位一致。

## 范围与唯一下一建议

本批学习候选在冻结验收下停止采用。保留无异常门槛的focus几何读取和版本引用原型，提交独立复核后，由规划固定下一项实际感知缺口及单一方案。后续训练、模型搜索、产品集成与资产精修均等待新合同。

当前材料为同一研究集合的3个派生组、6个网格身份，人体内容为头部/面部，独立最终测试缺失。原公开网格带有边界、非流形与形状问题，开放方向依赖已记录视图锚点，全局自交未认证。新候选从头训练；旧Pointfilter预训练与来源重合仍未知。当前输出支持几何绑定和任务计划，解剖部位语义、人类艺术偏好与实际编辑成功仍待各自验收。
'''
    (HERE/"REPORT.md").write_text(text,encoding="utf8",newline="\n")


if __name__=="__main__":
    main()
