# M4-BATCH-OBSERVATION-COVERAGE-001

指定请求在两个离线响应内覆盖所需数据，674项来源与投影检查通过。对等原生批量投影能生成逐字节相同的输出，且本次离线中位数更低。当前材料支持保留接口覆盖结论，直接产品接入的推进条件仍欠缺模型代码负担、真实往返或数据传输改善的证据。

## 可执行交付

`prototype/final.py` 提供 `directory(bundle)` 和 `selected_observation(bundle, request)`。前者返回普通ID、名称、世界AABB、米制和来源。后者接受调用者明确选择的对象、字段和有序关系对，组合世界顶点、标明种类的面索引和已有关系。缺字段、缺对象、缺有序关系与来源不符都有明确输出。实现只使用标准库。

在项目根目录可用普通Python运行两个入口。

```powershell
python -I -B verification/m4_batch_observation_coverage_001/prototype/final.py directory verification/m4_batch_observation_coverage_001/input_02/BUNDLE.json
python -I -B verification/m4_batch_observation_coverage_001/prototype/final.py selected verification/m4_batch_observation_coverage_001/input_02/BUNDLE.json --request verification/m4_batch_observation_coverage_001/input_02/REQUEST_PRIMARY.json
```

实际输出样例保存在 `benchmark/run_01/base/final/DIRECTORY.json` 和 `SELECTED.json`。原型源码没有任务对象名、阈值、角色或标准答案。固定请求来自前批实际调用者的选择，承担这次覆盖验收的fixture角色。

## 六次补查与来源

六次原生末读已逐项映射。五次提供世界顶点，一次提供坐标层级，六次均未返回拓扑。四份首读采用七位小数，另外两份未作额外十进制舍入。账本保留各次代码、原始返回、精度、公共事件及owner指针。

目录中的AABB可供调用方派生中心、导轨中点、横梁后界、双管中点、候选半径与位置条件。主请求提供两个选定对象的几何及三对已有关系。完整参照物形态归入可选请求，三份旧关系缺少横穿定位的事实仍按历史记录保留。拓扑是本次明确增加的通用形态字段。[需求账本与逐项覆盖](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_batch_observation_coverage_001/COVERAGE_MATRIX.json)

输入取自同一P1 actor的 INITIAL、真实关系回包及实际资源捕获。四个关系对象的local顶点、矩阵、单位与初始快照逐值相符。`SOURCE_BINDING.json` 保存真实host ID到离线选择ID的绑定、原context和三角片来源。该输入是两份保存观察的冻结派生视图。活体时效与同次宿主采集仍需真实入口验收。

来源核对期间修正了一个输入差异。早期输入使用原多边形，现有选择性捕获实际提供三角面。`input_02/` 对四个捕获对象采用实际resource.faces并保留原序号，其余对象明确标为source_polygons。主请求的两份几何因此与当前选择性捕获可提供的字段一致。早期 `input/`、准备脚本和未测量的fixture_01全部保留。

## 两阶段与产品接点

现有 `_overview` 已有世界范围投影，`capture_task_scene` 已有四对象选择捕获，`ReadContext.activate/normalized/result` 及host residency已有来源和暂留职责。原型直接投影保存数据，实际产品接点在prototype/README与COLLECTION_PLAN中说明。保存输入缺少可用于这两份记录的共同实时token，因此本轮采用文件SHA绑定，未创建第二份缓存。

主请求的几何对象为2个，连同三对关系端点的底层并集为4个。实际关系捕获已包含这些对象的顶点和三角面。将它们和关系结果一起投影，具备消除后续几何补读的接口位置。目录和选定观察合计两次逻辑响应，计划各一次宿主请求。

现有overview仍获取全场28对象、416顶点的几何。模型侧目录精简后，内部捕获和传输成本仍需计入。八对象可选并集超过当前四选择器合同，其一次选择性采集存在明确集成缺口。模型自行发现对象、选择最小字段以及实际采用两个回合均未验证。[底层采集计划](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_batch_observation_coverage_001/COLLECTION_PLAN.json)

八对象可选请求另作一次编码，两侧目录均5,504字节、选定结果均14,724字节，合计20,228字节。该补充只记录输出规模，性能21样本矩阵继续采用固定主请求。[可选请求编码](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_batch_observation_coverage_001/OPTIONAL_ENCODING.json)

## 正确性与一次简化

固定原件、独立名称/ID置换并重排、精确90度刚体旋转、同形干扰物共四份输入，674项检查通过。期望值来自原始坐标、捕获资源与独立等距变换，生产求解器调用为0。旋转后的事实按新坐标核对。新增干扰物的未提供关系保留缺口。

唯一简化依据需求账本删除目录中可由AABB派生的center。初稿和最终源码、评审及实际前后数据均保留。原始输入中两响应由14,998降至13,174字节，删除1,824字节。投影与编码中位数由367.1降至336.6微秒，单次Python traced峰值由42,718降至38,430字节。[简化实测](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_batch_observation_coverage_001/SIMPLIFICATION_RESULT.json)

## 同信息原生对照

原生对照使用相同保存数据、字段、选择、精度、来源和返回布局，同样允许暂留与合并。已有关系作为两侧共同输入。此测量覆盖关系已存在之后的交付成本，实际原生取得等价关系的计算成本另属未测范围。

每份输入各运行初稿、最终原型、合理原生三个fresh离线Python worker，共12个。每worker先预热一次，再保留21个投影与实际UTF-8编码样本。另一次tracemalloc记录Python分配峰值，Windows记录整个fresh worker生命周期峰值。输入加载、世界坐标准备和关系生成在计时范围外。

| 固定输入 | 最终/原生两响应字节 | 最终/原生中位微秒 | 最终/原生Python峰值字节 | 最终/原生进程生命周期峰值字节 |
| --- | ---: | ---: | ---: | ---: |
| 原始 | 13,174 / 13,174 | 336.6 / 292.0 | 38,430 / 40,222 | 22,429,696 / 22,306,816 |
| 名称与ID置换 | 17,975 / 17,975 | 386.1 / 338.9 | 49,466 / 51,258 | 22,515,712 / 22,708,224 |
| 90度旋转 | 14,219 / 14,219 | 351.8 / 306.6 | 41,793 / 43,585 | 22,204,416 / 22,134,784 |
| 同形干扰物 | 14,159 / 14,159 | 351.8 / 304.6 | 41,435 / 43,291 | 22,368,256 / 22,376,448 |

四份输入的最终/原生输出逐字节相同。原生中位快44.6至47.2微秒，最终原型的traced峰值较低。进程生命周期峰值含解释器、加载、预热和测量，数值方向有波动。原始样本、范围与完整响应保留在成本表和run_01。模型token、宿主采集耗时、缓存命中、模型代码生成及整任务成本均未测。[完整成本表](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_batch_observation_coverage_001/COST_TABLE.json)

实际MCP目录、schema上下文用量与工具选择行为也属于后续入口边界，本轮没有相应测量。

## 已有模型成本

以下仅列前批已封存九格的原始成本，本轮新增消费者为0。

| 路线 | 三格完整耗时合计秒 | 完整耗时中位秒 | 实际input+output合计 |
| --- | ---: | ---: | ---: |
| N | 155.2596501 | 48.3034231 | 143,762 |
| P0 | 148.4847411 | 48.9575438 | 172,454 |
| P1 | 139.6149947 | 47.4155056 | 172,370 |

P1相对P0边际通过原冻结规则，相对N的token增加使净收益门槛未通过。该正式结果独立于本轮离线投影，费用仍为未知。[历史原始成本绑定](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_batch_observation_coverage_001/HISTORICAL_CONSUMER_COST.json)

## 本轮判定

覆盖、明确来源、可执行接口、有限变体和一次简化均已交付。当前同信息交付层没有字节优势，合理原生投影中位更低。可定位的结构机会是复用关系捕获中已有的几何，在同一选定响应提供两类数据。它的真实调用效果与模型代码收益仍欠缺验证，因此作者建议暂缓直接产品接入与扩写，交根深度复核。

当前输入来源修正、最初协议marker读取错误和账本信封比较错误均有记录。产品源码、默认配置、原资产与共享GUI维持既有状态，本轮产品/Blender进程、消费者和新增图片均为0。AL缺自身合法绑定，任务同步待合法句柄。交付COVERAGE_READY后结束本批。
