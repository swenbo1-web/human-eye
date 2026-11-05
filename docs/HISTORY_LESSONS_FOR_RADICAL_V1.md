# 历史报告教训与本端执行约束

2026-11-05，用户要求自动推进且吸取GitHub历史报告经验。已用GitHub API核对远端：main=`8eace8bb9ca20d647007bc384e14d10fe3fb2c0d`，architecture-review=`284699285c349bd4124bf8c863c4546df1c6d033`；本端起点=`70febee9f71b68e8429601920af1c740e7166191`。相关报告与对应Git blob逐字节核对；历史原始实验未在本轮重跑，旧数字只按报告记载引用。

| 已暴露的问题与来源 | 本轮必须落实的检查 |
| --- | --- |
| [TF-01](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/TRUST_FOUNDATION_ACCEPTANCE.md#L15)：孤立顶点曾把闭盒1m表面距离变成0m | BC只对三角索引定义的表面测距；孤立点、面重排、对象交换必须保真；不删除或重写原始输入 |
| [规格反例](https://github.com/swenbo1-web/human-eye/blob/70febee9f71b68e8429601920af1c740e7166191/docs/RADICAL_V1_SPEC_REVIEW.md#L25)：越界投影、漏边边最近点、Top32漏全局解 | 完整三角窄相、可证明下界的完整搜索；独立oracle和点/原始面归属检查；表面距离不冒充有符号穿透深度 |
| [见证错域](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/MEASURABLE_OUTER_EXTREMUM_ACCEPTANCE.md#L55) | 不能只比距离数；对象、帧、面ID、两端点及其所属表面都核对 |
| [NV-D小场景失败](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/NONPLANAR_DENSE_ACCELERATION_ACCEPTANCE.md#L25)、[M1 r2配对p95失败](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/M1_RELEASE_COST_AND_DEADLINE_ACCEPTANCE.md#L29) | 大场景或中位数改善不能抵消预登记的小场景尾延迟门；组间p95比、p95差、配对增量p95分别说明，不能测后换统计量 |
| [插桩与生命周期退化](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/SOURCE_GUARD_COST_ACCEPTANCE.md#L23) | profiler只用于归因；用未插桩完整边界判收益；冷建、更新、查询、输出及完整路径分账，局部百分比不相加 |
| [合理原生基线](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/M2_ENGINEERING_BASELINE_ACCEPTANCE.md#L7) | 对手允许合理缓存、批量计算、紧凑事实及局部视图；不拿局部函数成本除完整任务成本，不拿快速拒绝作有效结果分母 |
| [相机RNA揭示失败](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/M2_ENGINEERING_BASELINE_ACCEPTANCE.md#L39) | VG读取实际相机矩阵并检查实际PNG像素、遮挡和投影；配置、截图存在或纯色图均不能证明目标可辨 |
| [公开定位信息缺失](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/M2_ENGINEERING_TRANSPORT_ACCEPTANCE.md#L53) | VG/AO消费者只能使用公开输出选区；私有见证不能替消费者补答案；错帧、漏位置、失效引用计入失败 |
| [紧凑输出与native持平](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/B3E_PRO_TASK_QUALIFICATION.md#L25) | AO比较等价任务字段与合理紧凑基线；字节、token、费用、补查次数分别测，不互相推算 |
| [编排时序错误](https://github.com/swenbo1-web/human-eye/blob/8eace8bb9ca20d647007bc384e14d10fe3fb2c0d/docs/REGION_WITNESS_CONTROL_ACCEPTANCE.md#L7) | AO/CF检查基础观察→选择→执行→真实回读→结果标签；终止后不得继续派工；实际模型消费与脚本消费者分栏 |
| [模块收益路径复核](https://github.com/swenbo1-web/human-eye/blob/284699285c349bd4124bf8c863c4546df1c6d033/docs/MODULE_BENEFIT_ACCEPTANCE_ROUTE.md#L16) | 代码存在、入口可达、实际触发、消费者受益是四项证据；正确性、收益、未测分栏，旧路径成绩不能套给新默认入口 |

最后一份报告仅在architecture-review分支及其后继，main同名文件不存在；不能将错误分支的404解释为整个项目没有该报告。以上约束进入实现外的测试与计量，不恢复用户已经要求移除的来源哈希、权限配额、隐式重试与保守回退链。

## 本端已纠正的报告漂移

RB-B在70febee通过后，README和验收台账已更新，但PROGRESS仍写待验，工作流仍把RB-B当环境阻塞，架构初稿还把所有新模块称为未实现。另有“更新后旧视图无效”与已验借用数组生命周期不符。本轮同步修正当前入口，并保留明确标注的历史报告原状态。

后续每次交付核对README、PROGRESS、架构当前状态、竞争工作流及验收台账；只提交本端明确拥有的改动。测试数、生成报告或提交成功均不单独作为收益证据。已验模块不重复扩大测试，只有新改动、失败或未解决疑点触发必要复验。
