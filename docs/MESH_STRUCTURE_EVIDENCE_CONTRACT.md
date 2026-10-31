# 单对象结构证据合同 v1（M1-01）

状态：2026-10-31 **验收合同已冻结；M1-02首批三类结构事实与owned私有通路已实现为候选，大网格成本门失败，尚未发布**。本文件是[唯一主计划](PRODUCT_ROADMAP.md)中M1的接口和验收依据，不创建另一条任务队列。正式运行版仍为22fb；旧MCP尚不支持新增查询。

## 1. 两个任务与最小共性

`spatial-readonly-task-v1`包含`kind/task_id/object_ids/read_only/categories`。`mesh_structure`恰好一个目标；`clearance`恰好两个不同对象。任务ID只关联证据，`read_only=true`固定；模型参数不能携带授权、续期或额度。原`task_context`继续只作计量关联。既有`ClearanceTaskSpec`、TaskAuthority、四个MCP工具和V1/V2/V3合同不改名、不放宽。

间隙回归锚点：原有精确对象对量测和单对象概览的成功/拒绝语义。新增任务：静态源网格的结构事实与定位。首批只选解析夹具中有完整真值的检查类别；未请求或未具真值的类别明确not_checked，不能将局部得分当作全任务准确率。

**来源读取资格、结构检查资格、原生取景资格和动作资格独立。** 真实开放薄片、零面网格、孤立顶点可只读，不需要伪造第二物体或闭合实体。全部读取都不修改几何；建夹具发生在独立factory Blender进程内，属于测试准备。

## 2. 原始来源与映射

首批支持一个本地静态Mesh数据块，Object Mode，无求值修饰器、shape keys、实例化、动画、骨骼、父级/约束或外部写入。数据不足/读取竞争返回明确unknown；不自动焊接、修复或转为求值网格。未来扩域单独验收。

源载荷保留原始顶点坐标、每条原始边的顶点索引、每个多边形的完整有序顶点索引；数组位置就是该次快照的源索引。保留松散边、孤立点和重复位置。若需要三角形辅助，另带`triangle_to_polygon`和三角角点到原始顶点映射；不能把三角化对角线当原始边，也不能把三角面编号当多边形编号。

`SourceSnapshot`绑定document_epoch、object_instance、object_id、capture_id、完整raw内容摘要、数量与capture_scope。raw摘要覆盖所有坐标/连接、坐标系、单位换算与变换信息，不能仅对顶点数量或AABB做hash。原始值使用Blender可读取精度；位置换算为米时保持binary64计算，不预先取整。对象改名不是唯一身份；同名重建、更换数据块、位置/拓扑/单位/矩阵变化均使旧patch失效。内容hash不证明编辑历史。

目标采集声明`target_mesh_only`，**不证明全场景完整或自然可见**。局部图所需遮挡几何必须另走完整场景来源与预算；未知/不支持的遮挡物不能丢弃后声称自然观察。读取了目标原始数据也不能宣称已验证求值后显示网格。

边界验收使用无向原始顶点对，连接结果必须可解析回同一快照的唯一source_edge_index；当前域拒绝重复端点的歧义源边，不任意选一个。生产patch另保存实际原始索引/快照绑定。夹具中的端点对是独立oracle的稳定写法，不是省略源映射的理由。

## 3. 事实、范围和拒答

报告版本`mesh-structure-evidence-v1`：task、source、checks、not_checked、execution_authority=false、natural_visibility=not_checked。可执行验收器位于`verification/mesh_structure_contract.py`，**目前不在生产调用链**，只核验字段一致性，不能证明生产者真的扫描了几何。

| 检查类别 | 首批语义与边界 |
| --- | --- |
| boundary_edges | 原始多边形边的面关联数为1；按源顶点连接成簇。合法开口仍有边界事实，不自动判损伤 |
| nonmanifold_edges | 面关联数大于2；0关联属于loose_edges，不与开口混淆 |
| nonmanifold_vertices | 局部face-link非单连通环/路径等结构事实；必须覆盖只检查边次数会漏掉的bow-tie。退化/重复面导致link不可靠时单列原因，不伪判正常 |
| isolated_vertices / loose_edges | 顶点没有边/面使用、源边无面使用；不能在重新生成边时遗漏 |
| duplicate_positions | 不同原始索引的精确相同位置组；不等同于应当焊接或损坏；近重合不在本类 |
| degenerate_polygons | 重复索引/零面积及明确数值阈值内近退化分开。M1-02先覆盖解析零面积三角形；非平面/自交ngon无法可靠判断时保留该类unknown，不拒绝其他可读结构事实 |
| duplicate_polygons / winding_conflicts | 循环旋转/反转的重复多边形组和共享边的方向冲突分别记录；两者不是同一类 |

M1-02实现每一类前须冻结它的数值阈值/算法子版本；未经独立真值验证不得把已列类别全部广告为已实现。self_intersection、near_coincident_surfaces、surface_damage、rig_pose、skin_deformation固定not_checked。未请求的M1类别也显式not_checked。

每类报告：`state`（complete/partial/unknown/unsupported/not_checked）、`scanned`（V/E/P/corners覆盖数量）、`found`（已发现簇数）、`total`（仅完成扫描时为已知）、`regions`、`omitted`、`reason`、`omission_reason`。部分扫描的实际扫描区间/位图引用在M1-02原始结果中保留；计数本身不能定位已查范围。展示可以有界，但大簇不能只取前64个成员却称完整簇；须省略整簇并保留回查引用，或另立明确分页合同。

完整扫描与完整交付不同：输出省略可保留正确总数，但不等于定位验收已完成。中止扫描时总数为null，即使已发现0项也不能说正常。部分结果的已发现事实仍可用；未知原因不隐藏。

## 4. 跨层接入与责任组件

| 层 | 当前事实 | M1执行位置与约束 |
| --- | --- | --- |
| MCP / query | 旧observe只接受既有query，新增mesh_structure会拒绝 | M1-04在既有observe中新增显式版本能力与只读分派，旧query默认值/错误行为保持；不新增写工具 |
| LiveSpatialService | 单对象概览可用，精确原生策略仍要求pair | M1-02提取小的diagnostic分派；M1-04绑任务与额度。旧pair策略不共用新拒绝/放宽规则 |
| typed宿主 | 一般capture给求值三角形；native校验原始对应但丢多边形/松散边映射 | M1-02加独立`raw_mesh_diagnostic_v1`能力和typed方法；owned worker与默认桥各自显式支持后才开放 |
| 传输 | 默认桥64MiB响应，owned native 2MiB、process按字符限长，适用于不同路径 | 新载荷独立4MiB UTF8限额，编码前数量预检+编码后字节检查；不借旧native方法绕过其2MiB/对象对条件 |
| consumer | `_public_query`/readonly native校验对象对 | M1-04新增只读结构结果校验与投影；M1-03单对象图使用新能力，不放宽旧原生合同 |
| 快照/patch | 当前缓存不能提供新增raw映射保证 | M1-02绑定完整raw快照；M1-03读取前复核同一来源；缓存淘汰不复活旧引用 |

原生通道可行性结论：Blender源API能读单对象及零面网格；现有pair原生消费协议不够，需要独立能力版本。真实默认MCP/Hook单对象诊断仍待实现与验收，不能把本轮脚本读取算作已接入。

刚体任务入口只读核查结论：`TrustedTaskAuthority`依赖受信嵌入方approve_callback；默认MCP分派仍是四个工具，没有等价的完整任务登记/自动scheduler入口。现有owned路径证明调度器可复用，不证明默认共享GUI可独占。M3-A先实现用户可核对的本机受信登记、固定owned宿主和原预算；若无可信事件则停在预览/单段能力，不把模型JSON当批准。本轮未改任何执行资格。

## 5. 资源合同：限额、实施责任、当前状态

这些是**新诊断路径的候选额度**，不是已经执行的全产品保证。超额须停止/明确unknown或省略，不能续建任务重置额度。

| 项目 | 冻结额度/口径 | 执行责任与阶段 |
| --- | --- | --- |
| 单目标raw | 16384 V、32768 E、16384 P、65536 corners，完整源载荷≤4MiB UTF8 | M1-02宿主先数量预检、分批读取检查deadline；传输/consumer再验字节与索引；各项均须成立 |
| 结构工作 | 262144 primitive visits；分别记顶点/边/面角/link遍历，隐藏二次循环也计入 | M1-02算子；到期/超额返回partial，排序/分配另计总时长 |
| 摘要 | ≤64KiB UTF8；总共≤128簇，每簇≤64完整成员 | M1-02投影，M1-04编码后复验；大簇省略整簇，索引回查亦计查询额度 |
| 任务累计 | 2次查询、4张图、30秒原始单调期限；每调用仍≤2张384² | M1-04受信服务端登记/串行预留/提交账本。task_id或task_context本身不授权/续期；重连无法恢复计数时拒绝继续旧任务 |
| 图像/射线 | M1-03预登记具体采样工作门后才能开放；当前新诊断图0张 | 完整遮挡来源和真实相机核验，不能以当前文本验收代替图片验收 |
| 缓存/内存 | 既有保留预算8MiB；新增Python临时分配峰值≤64MiB的验收门，单独trace，不混入计时样本 | M1-02分别测临时分配与进程峰值；不能把Python计量或缓存保留计数当RSS硬限制。没有OS限制不宣称硬内存隔离 |

任务账本绑定服务端生成的登记ID、来源/目标、初始绝对deadline与剩余额度；请求重试不能重复赠送额度，未知完成保留预留，缓存命中也计查询。跨进程恢复需要持久原状态/可信时钟；不具备时fail closed，不以删除状态清零。此设计在M1-04实施并测故障；本轮没有实装跨调用配额。

## 6. 基线、质量门与数值成本门

独立真值在`verification/mesh_structure_fixtures.py`，14个解析源夹具；各夹具只对expected中明确列出的类别给完整真值，其余不评分也不称正常。另有8/32/96网格读取梯度。全部在三个新factory Blender进程中读回，原顶点/原多边形顺序和源边集合与构造真值一致；记录0几何/选择变化。它们是解析代表，不冒称未见真实生产资产。

当前读取基线为raw读取→结构格式校验→JSON编码；legacy为原生/求值双证据，字段更多。两者不是等价功能方案，**禁止据耗时比直接宣传引擎提速**。9次/组的经验p95只作初始成本登记，不是总体置信区间。完整MCP等待/渲染/模型时长未测，不写成0。

本机基线：grid_8（81 V）raw中位约0.24ms；grid_32（1089 V）约3.58ms；grid_96（9409 V）约40.14ms，p95约56.44ms，载荷755745字节。legacy分别约1.25/15.54/182.67ms，承担不同证据内容。零面/空网格在legacy被拒绝，在直接raw读取中可保留；这支持独立诊断采集，不证明算法已能识别缺陷。

候选优化之前冻结`verification/fixtures/mesh_structure_acceptance_v1.json`：

- 正确性：固定域内任务类别/完整簇一对一匹配，TP/FP/FN、索引和簇拆并分别计算；有限验收集要求FP=FN=0且回答覆盖100%。域内unknown/unsupported仍在漏检和任务失败分母。域外正确拒绝另表，不能用于稀释域内失败。
- 正常负例：合法开口不产生损伤断言；结构事实与语义损伤分开。零面不等于所有专业正常，仍有not_checked项。
- 新诊断成本：各组原始读取经验p95 + max(20ms, 0.5×原始读取p95)，作为**新增采集/校验/结构扫描/摘要编码整段**的p95上限；上限不得跨组抵消。此为愿意支付的新增功能开销，不是“优化收益”。超过则记录失败，不能事后放宽。
- 保留基线：本批78运行源字节不变；后续一旦改旧路由，简单间隙任务须做配对同质量比较，额外p95≤0.5ms；若是必要正确性开销，另记理由而非报性能通过。
- 完整任务：从服务接收到结果编码/传输返回计时，包含首次准备、冷/热、缓存失效与超时；30秒是硬停止窗口，不是性能达标SLA。M1-04先测真实接口基线再冻结传输/原生图的分组数值成本门，未测前不宣布端到端价值。M1-02允许在已冻结的无图算法门内推进。

## 7. 本次交付边界

M1-01冻结合同、有限支持域、独立oracle、跨层责任和原始读取成本门；新增生产诊断、任务账本、patch/图片、真实Codex消费分别属于M1-02至M1-05。验收器只检查报告一致性；读取脚本只证明来源可读。正式模型试次仍为0。下一项按主计划执行M1-02，不能将本合同登记为已完成诊断功能。

## 8. M1-02首批候选的历史支持域

`mesh_structure.py`独立读取目标raw并验证索引，首次覆盖boundary_edges、loose_edges、isolated_vertices；同一次校验构建边面关联，后续扫描直接复用。不是使用求值三角形重建原始边。零面积三角形的连接仍可读，但面积/损伤不在本批判定；重复索引多边形及歧义重复源边当前明确拒绝，不能先修复再声称原结构正常。

`BlenderSceneHost`加载固定SHA的helper；`BlenderProcessHost`固定worker新增typed只读命令；`LiveSpatialService.observe_mesh_structure`是私有入口；独立consumer检查任务/来源、覆盖、计数、patch及原deadline绑定。旧对象对、写入、原生图与公开query均不改准入。默认共享BlenderMCP桥目前没有新typed方法，因此私有服务在该宿主返回unsupported，不回退对象对路径。

来源读取在Blender主线程同步执行，读取前后检查对象/数据块身份、计数、guard、矩阵与单位；这不证明第三方本机扩展不会非法跨线程修改内存。来源转换不会编辑几何。目标以外资产不作为自然可见性证明。

输出仍为本合同的report；外层提供实际源索引patch、扫描前缀、已完成分组类别及计量。验证阶段已扫描面角，分组预算耗尽时可出现全量源前缀但分类partial，不能由前缀推断分类完成。大簇/字节额度省略整簇，保留来源绑定的再次检查描述，明确`retrieval_endpoint_available=false`，不伪装已可回查。任务累计2查询/4图账本尚未实现，仅单次协作deadline和工作量有效。

第一轮与一次明确优化后的大网格成本门都失败；原门限与失败分母不变，不能把已有结构正确性或中位下降当发布通过。数值门、原baseline和14类独立oracle文件保持原始字节。后续任务以主计划为准。

## 9. M1-02六类候选与位置协议v2

默认请求仍是原三类；显式请求增加`nonmanifold_edges`、`nonmanifold_vertices`、`degenerate_polygons`。外层改为`raw-mesh-structure-v2`，包含固定`algorithm`策略、`coverage.unclassified`及每个patch的`classification`和`position`；内部报告仍遵守原`mesh-structure-evidence-v1`。helper固定摘要与consumer同时升级，旧v1不会被误认作v2。私有能力尚未安装或公开，旧四工具/对象对query不变。

- 非流形边：同一原始边关联超过2个不同面索引。重复面仍是不同源面；不先去重再计算。
- 顶点link：每个面角向其前后相邻顶点建立多重图；一个连续环或开口路径接受。混接松散边作为额外节点；纯线网/孤立点由各自类别处理。触及旋转或反向等价重复面的顶点保留未知。异常顶点只通过异常顶点之间的原始边聚类。
- 退化：对原始局部坐标的实际二进制数值使用精确有理运算；全共线为`exact_zero`。非共线三角形的叉积平方≤`2^-80 × 最大边长平方的平方`为`relative_near`，不受正单位比例变化影响。该质量判定属于raw局部域，不把世界非均匀/奇异变换后的质量当作已检查。
- 非三角面：全共线可判零；其余只在≤64角、精确平面、简单多边形内判定。相邻边回折与非相邻边相交均排除；非平面、非简单和超角数保留未知，近退化ngon质量另列未查。异常面按共享原始边聚类。
- 未知：`coverage.unclassified`给该类别未知总数、最多64个源索引前缀及原因；分类记录为partial、总异常簇数为null，已知异常仍可交付。预算中止同样不能给出完整总数。位置未知单独使外层partial，不抹掉已完成的分类。
- 位置：覆盖该patch全部源元素的全部顶点；局部米坐标为`raw × unit_scale`，世界米坐标为`(M_linear × raw + translation) × unit_scale`。提供两套包围界及一个源索引见证点；binary64前向计算不是认证测量误差界。非有限计算或预算耗尽保留明确unknown。

新规则与11个独立夹具已在修改源码前冻结于`verification/fixtures/mesh_structure_topology_acceptance_v1.json`、`verification/mesh_structure_topology_fixtures.py`。原14类fixture与原数值门未改；本批25个owned场景和公共回归只支持声明域的正确性，不证明新六类计算已达到成本门、真实资产全覆盖或公开Codex已消费。重复位置、重复面、方向冲突尚未作为独立诊断类别交付；自交/参考损伤/骨骼继续not_checked。

## 10. M1-02九类候选的当前语义

上述第8、9节保留对应批次历史；当前在原v2字段结构上推进固定`algorithm.revision`至`raw-topology-nine-facts-v1`，能力声明和helper SHA同时更新。默认仍请求原三类；九类必须显式选择。新增算法不增加旧采集的求值/执行准入，也不开放公开MCP或Hook查询。

| 类别 | 有限事实与聚类规则 | 不作的推断 |
| --- | --- | --- |
| `duplicate_positions` | 三个原始局部坐标逐值精确相等；正负零及数值相等的int/float等价，每组至少2个原顶点索引 | 不先转float/米制、变换、取整或容差合并；无近邻重复、焊接或损伤结论 |
| `duplicate_polygons` | 原顶点索引环允许换起点或整体反向；每个完整等价类单独成组，即使两组共边也不合并 | 同顶点集合但不同环不是重复面；不同顶点索引的重合曲面不是此类事实 |
| `winding_conflicts` | 恰有2个不同原面索引沿共边同向绕行；异常原边按自身连通性聚类 | 不判断应翻哪面、整体朝外或全局可定向性；零面积面也只报告索引方向事实 |

边关联超过2个面时，该边方向归`unclassified`，原因`nonmanifold_edge_orientation_ambiguous`；0/1关联无成对冲突。已知冲突可与未知边共存，category为partial、总异常数null。未知边的前缀是原始edge索引，不是顶点/面索引；consumer按类别检查范围，并拒绝已知patch与未知索引重叠。重复面引起的顶点link未知，不抹掉该面的重复事实或可定义的共边方向事实。

三类patch分别用vertex、polygon、edge源索引，沿用全部源顶点包围界及见证点。超过64成员的等价类整组省略，不返回前64个冒充完整组；计数、工作、输出字节及原deadline上限全部不变。新增14个独立oracle及规则在改运行源码前冻结于`verification/mesh_structure_completion_fixtures.py`、`verification/fixtures/mesh_structure_completion_acceptance_v1.json`；原始与上一批fixture不改。

39个owned解析场景与实际固定worker私有消费支持声明域正确性；总架构M1仍缺问题区域图像、公开消费、任务累计账本及完整成本门。本批不提供几何写入、修复、学习模型或真实资产全域保证。下一项仅由主计划裁定。
