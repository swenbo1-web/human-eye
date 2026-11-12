# Surface scan OPT1：独立质量、输入绑定与复用映射复核

2026-11-12。结论：固定 33 次观察的全部 9108 对分区、2354 条公开最短距离、4708 次见证端点出现均通过独立核验。五个 B 主序列及 Process 序列均证明 cold 空测量缓存、112 次新核，repeat 0 新核，EDIT 104 个未变对象对命中与 10 个移动相关/新候选未命中。未发现本固定输入的陈旧结果、遗漏、误报或假 complete，可以进入有界模型消费对照。

本子审使用 learning-worker 工作规则，已以自身 Hook 句柄核对 assignment `4dde9f53-d63b-4df8-9151-7da5c242cf60`，父任务 `2ceda2c3-5d8c-4544-8471-d6807eb70579` / revision 1 / write_version 607。未修改父任务、实施源码/原件或 Git。新增产品进程、Blender、模型消费者和业务 API 调用为 0。

## 证据与复用

固定交付 `860b87138d40de9cc08b01c947dd864d58da9295`；B 产品 `c1cb2da32034e056a270384e691a2cde8dddbc0d`、源码 `c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943`；A 为初版 `c6355a01a4c6ee204a0d676cd9309f02428fe3ba`、源码 `b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314`。资格沿用 `96fce78b98cb749885792112e039a406744d282b`。

复用本根上轮独立质量脚本的有理数几何函数、输入资格检查和已经完整独立求解的 552 对最小值。复用的 `check_saved.py`、`ORACLE_RECOMPUTE.json`、`INPUTS.json`、`RESULTS.json` 均先逐字节核根提交 `dd11f1aa97ad0bf8bb314a86cd91b32ff0123874`；记录在 `REUSE.json`。本轮没有重新做一次完整最小值求解，也没有把上轮计算当作新增独立样本。

新写 `check_opt1.py`，只导入上述根独立检查脚本的函数，不执行其 main；重新适配本轮 A/B、30+3 计划分母、原始 stdio/audit/快照绑定及逐 pair 缓存映射。没有执行或导入作者 oracle、audit、summary 或产品几何模块作为验证器。代码复用边界可直接从 import 与函数调用审计，未复制作者验收逻辑。

最终 47564 条断言通过，读取并核对固定 Git blob 的 262 个原件（安装 worker 对其 B 产品提交核字节）。包含 20 份主几何快照和 2 份 Process 快照、33 份请求响应与原 audit、10 个主 RESULTS、Process RESULTS、封存真值、资产、wrapper 和相关工程脚本。全套 138 源/安装和1110交付文件由根完整性复核负责，本子审不声称语义通读全部文件。

第一次脚本运行通过 47561 条断言；随后明确补上 Process body 直接等于原始 RX content 解码和 query 合同的 3 条检查，再执行通过。两次都是离线原件核验，没有增加产品样本。最终运行约 17.92 秒，仅为复核成本。

## 全体质量与输入对应

每次都要求完整 276 对、唯一 canonical pair、合法分区。bound exclusion 必须严格大于实际 binary64 阈值且不超过独立最小距离；实测阴性也核最小距离和分类。全部公开匹配集合恰好等于真匹配，不只核返回项。

| 状态 | 全 pair | 严格排除 | 实测匹配 | 实测非匹配 |
| --- | ---: | ---: | ---: | ---: |
| BASE（cold/repeat） | 276 | 164 | 71 | 41 |
| EDIT | 276 | 162 | 72 | 42 |

主 30 次核 8280 对，Process 三次核 828 对，总计 9108。公开距离总计 2354 条；全部要求 `witness_status=measured`，与冻结最短值直接比较，而不只是验证给出的端点相距那么远。公开和私有实测距离最大误差 `1.0842021724855044e-19 m`，低于既定 `1e-10 m` 展示核验容差。阈值集合仍按精确平方值判定，不用该展示容差放宽匹配。

4708 个端点出现以独立点到实际三角表面的距离求解核归属；相同状态/对象/端点只求解一次，共284个唯一键。端点间距与公开最短距离相同。所有观察均无 unknown、deferred、scope issue、unsupported、重复或未交付匹配；公开实体语义保持 `solid_relation=not_evaluated`。

20 份主实际快照及2份Process快照，仅忽略 PID/文件路径后，与对应冻结 BASE/EDIT 逐字段一致。11份实际打开的 `.blend` 输入摘要等于资格资产。资格本身仍为24对象、530点、978三角形，只有 Obj_008 世界姿态改变，本地顶点和拓扑不变。

全部主请求都与保存的 TX/RX 一一对应，公开 body 等于真实 RX content 解码；每个产品序列只有三次 scene_observe，其余为 initialize/initialized/tools-list/ping。每条 audit 以唯一 trace_id 匹配诊断，Process 也做同样核对。没有用 RESULTS 内的作者 PASS 替代原件绑定。

## 缓存映射和没有提前填充的证据

A 每序列为112/0/114新核；B及Process为112/0/10。B cold 的 `measurement_entries=0`、`measurement_computations=0`，所有 cold 候选均新算；容量一直为2 MiB/256项。此前只有元数据与QA快照步骤；源码所见QA导出只读取实际几何，不调用产品测量器。A没有新增逐请求cache.stats，本审通过其112新核、仅三次观察及相同无预填的工程顺序核对，不虚构旧版telemetry。

五个B和Process各完整核114个EDIT pair：

- 104个不含Obj_008的对象对都出现在本序列cold中，依赖对象摘要和pair键相等，`surface_pair_cache_hit`及`surface_dependency_cache_hit`为true，新核数0。
- 10个含Obj_008的关系为新候选或键已改变，命中为false，新核数1；没有用旧世界见证冒充新姿态。
- 名称与实际几何对应由快照和公开id/name绑定另外核验；不只相信诊断里的“unchanged”标签。

全部映射保存在 `CACHE_MAPPING.json`。这证明保存的真实调用路径和几何状态下，测量复用达到了机制门；typed token防伪、decoder资源版本冲突、任意plain capture及通用solid回退的源码正确性由缓存代码子审负责，不能用本固定映射替代其通用反例。

## Process QA wrapper 的实际含义

实际 stdin 顺序为 `capabilities → qa_snapshot → scan → scan → qa_advance → qa_snapshot → scan → shutdown`。wrapper只消费三个QA命令，将普通原始行原样交给安装版 `blender_worker.run_worker`。其固定导出器、登记姿态patch、资产和worker都按配置哈希核查；运行副本wrapper字节等于冻结工程wrapper，安装worker字节等于 B 产品提交。QA_CLOSED记录完整严格顺序、一次改动、最终指纹和文件未保存，正常命令列表为caps/三次scan/shutdown。

本审读了 wrapper 与 run_process 源码：QA快照没有产品测量预填；结果字段由真实安装版service/worker处理。它是有明确QA外壳的Process宿主三状态检查，不是桌面默认MCP激活或真实模型消费者验收。两份Process快照与对应冻结状态相等，cold空缓存及104/10机制与主路径一致。

## 后续消费者公平性和边界

赞成先用同一冻结 BASE 做6个fresh上下文 N/P 冷态任务，验证“没有预给对象时模型是否自然使用全场事实”；不需要为本轮另建连续对话框架。当前约91%的EDIT局部请求改善不能直接作为该冷态模型任务收益。

共同提示保持“列出全部表面最短距离≤2mm的对象对和距离，并说明完整性”，不透露对象数、候选数量、匹配数、oracle或答案。可共同要求至少0.001mm显示精度，评分前固定显示误差上限（例如0.0005mm）；对象对匹配集合仍由独立精确阈值定义，不能因为显示值舍入到2.000mm就改变纳入规则。距离、全匹配集合、完整性与表面/实体语义分别评分。

原生可一次批量读全部网格，使用NumPy、BVH和本格脚本缓存；插件可用正常工具声明但不额外获得实验者预选候选。启动/schema/目录/错误自纠/完整回答全部计入同一成本口径。先封匿名质量，再解封组别/usage；只保留完整正确时的速度并同时披露全部计划格失败/未运行分母。后续若测连续状态，两组都应保留各自进程、脚本和缓存，不让原生反复从零而插件热态。

本审未重跑224项作者定向测试，未核实全部性能公式或生命周期上界；分别由其他子审/根负责。旧g06、传输等待、隐藏来源异常仍保留。本次只覆盖一个合成装配的两个状态，没有图像、复杂来源或专家模型收益证据。

产物：`check_opt1.py`、`RESULTS.json`、`INPUTS.json`、`CHECKS.json`、`CACHE_MAPPING.json`、`REUSE.json`。
