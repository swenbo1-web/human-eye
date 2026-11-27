本审计只读取原 A、C 安装源码，不执行产品、求解器或宿主。面数和来源可以在求解前取得；这不等于已经证明完整工作合同。最早可用的普通面数是当前捕获中的原始有序三角行数，不能替换成对象数、潜在对象对数、去重面数、已算过的窄相数或上一轮低水位。

冻结依据是合同 `a303b53c8c69ef2ac24283bc515888dc5fd0cdbd`。两版各 143 个安装源码文件已逐字节核对并重算运行摘要。A 为 `a72aefd8…0a62d`，C 为 `b8c8bcd7…402e`。仅 `surface_proximity.py`、`surface_geometry.py`、`task_query.py`、`surface_scan.py` 四文件不同；服务、宿主、源码身份和缓存管理代码相同。完整绝对路径、文件 SHA、每个函数的起止行与片段 SHA 在 `SOURCE_REFS.json` 和 raw `entry/SOURCE_AUDIT.json`，不是从工作目录里的另一份实现推断。

**实际入口和判断位置**

下表行号默认指 C；A 的不同位置另列。共同模块的行号两版相同。

| 路径 | 当前来源、面数何时已可知 | 在此之前已经付出的工作；与求解的关系 |
|---|---|---|
| 普通单对 `task/surface_proximity` | `live_service.py:2113–2166` 取得选中捕获，`auto_router.py:266–430` 验证当前身份、有限世界坐标和原三角行；`task_query._surface_pair_measurement` 的 A:281 / C:283 直接取两侧 `len(faces)` | 宿主捕获、传输、JSON、通用验证、数组复制、场景指纹和缓存选择已发生。尚未创建该对的表面 `_Work`，也尚未产生该对的 R3 三角/BVH。这里的形状计数不是有效输入、精确位宽或工作上界证明。 |
| G60 最近 | `live_service.py:2048–2111`；`task_query.surface_nearest_result` A:549 / C:551；先校目录、实例、保留集合，再得到保留对象的完整规范化网格。C:627 在进入有序对循环前才建查询局部 mesh-cache 字典 | 捕获已经执行宿主保守下界和真实三角顶点上界见证，可能合法排除对象；被排除对象不进入内核。目录没有每个被排除对象的完整三角数组，不能把目录对象数当面数。已保留对象的完整原三角行在首次 C 专用几何准备之前可读。 |
| G60 扫描 | `live_service.py:1983–2046`；`surface_scan.py:193–237` 校协议、全部对象对处置、保留端点并规范化；C:237 建查询局部 mesh-cache | 先区分整结果命中、进度摘要命中、测量缓存命中、严格下界排除、未知来源及真正新算。`reserve():229–233` 只在测量缓存未命中后增加本次新内核配额，默认 512，和每次表面 16,384 窄相上限不是同一个数。66 是 G60 可能对象对数，不是新的窄相数。 |
| **已测 Yanyite 高/低盒** | 原 043 PLAN 的实际 mode 是 opt-in `source_region_measurement`。`live_spatial_mcp.py:2613–2624` → `live_service._measure_selective_source_region:1620–1666` → `source_region.measure_selective_region:835–881`。紧凑包验证后，在 `source_region.py:846–849` 已知完整所选三角行及参考网格行数 | 原宿主已经完成闭盒选择/紧凑映射或验证实际 residency/lease。以紧凑所选行数乘参考面数，不以源对象全量 `source_triangle_count` 代替。每次仍构造两份 NumPy 网格，再调用 `_measure_region_surfaces:676–688`；该实际路径没有 `context.result` 或 `pair_measurement`，暖宿主租约不代表距离求解命中。 |
| 另一个普通 `source_region` API | `live_service._observe_source_region:1669`；`prepare_region:252–340`、`measure_region:955–986` | 此路径确有当前 region prepared/result/pair 缓存，也可能做全场验证、闭盒选择、数组/相机准备。它不是上行已测 Yanyite opt-in 路径，不能用它的缓存解释替代实际原件。 |
| 复合 `closed_solid_relation + surface_proximity` | 两版 `task_query._closed_surface_facts` A:387 / C:389，原面数在 `_closed_solid_pair_measurement` A:323 / C:325 已知 | **闭壳先算**。未命中时在 `classify_closed_solids` A:729 / C:1013 已调用本版 `exact._admit/_integer_frame` 并可能建本版树，之后表面才能复用 prepared pair/trees/contact。到表面入口才选择版本已晚；闭壳命中则 holder 未被填充，不能据此假设可复用准备。 |
| 复合 `spatial_relation` | `task_query._spatial_pair_measurement` A:347 / C:349 → `measure_spatial_relation` A:1220 / C:2602 | 表面先算，再用**同一个**表面 `_Work` 做支持方向/全部引用顶点投影；表面已知不保证支持尾项能在剩余预算完成。若支持未证且未资源拒绝，闭壳用独立 `_ClosedWork`，保留同一绝对期限。 |

**缓存、准备和预算状态**

1. `scene_cache.pair_measurement:434–486` 先构造依赖键，再查实际 LRU。命中返回已编码的有效结果，不创建表面 `_Work`；未命中后才执行 `before_compute` 并进入内核。未知和异常不入该测量缓存。键的来源是绑定的 read resource / scan dependency，或完整 `mesh.to_dict()` 的规范 JSON 与 SHA；后者会复制/编码整个网格。已有键、当前合法命中和本次可能命中不能混称，查键/编码/锁/解码也不是免费或表面 Work 单位。
2. `read_context.py:42–69,95–121` 管当前捕获、八个选择、每选择十六结果及扫描进度。整结果命中可以早于逐对求值；扫描不保留不完整 terminal result，但保留同一绑定下的进度摘要。编辑、重新连接和源码代际必须按现有 reset/绑定规则处理。`live_service.py:350–364` 的源码检查采用已加载代际，可能明确标 `disk_not_checked`；不能将它描述为每次请求重新哈希安装。
3. C 的 `_mesh_cache` 是另一层、查询内的本地帧/三角/树缓存；A 没有此参数。C:2105–2133 明确要求深层 tuple，拒绝所有 ndarray。通用 `_validated_scene` 的 `MeshEntity3D.from_dict`（共享 `human_eye_foveated_renderer.py:705`）生成 NumPy 数组；因此 G60 只传入带 `__sealed_query_meshes__` 的字典并不使数组可走该路径，`scene_cache._bind_read_meshes:172–177` 也只绑定依赖、不改数组类型。冻结源码没有消费该 sealed 字段的分支。
4. 真正 tuple 输入可进入 C:2256–2441。缓存需同一 mesh、顶点/面 tuple 对象身份、长度及 admission；冷检查逐面/引用顶点。即使本地帧命中，仍记引用顶点数；admission 命中仍记面数；三角命中仍计准备；树命中仍消费保存的 `bvh_units`。`_CacheBuildBudget:2092–2102` 把冷树建设费用转发到同一原 `_Work`，不是另开无上限预算。局部帧/三角/树一旦已产生便是 C 专有准备，不能宣称这些工作发生前才选择 A。
5. 实际 Yanyite 的 `_measure_region_surfaces` 总传 `_prepared_holder`。C:2474–2475 明确只在 holder 为 `None` 时尝试 mesh-cache；故该路线每次距离调用拥有新账本。其后 `_witness_sources` 还有源面/点成员核验及映射工作，不能把距离内核计数当作整个局部响应的全部成本。

**真实剩额与第一个未证条件**

普通新表面对在 A:1087 / C:2453 构造 `_Work`，初值 0，原上限 1,179,648；之前的宿主/通用准备/缓存开销不会转成该 `_Work` 的已花单位，但已经消耗请求墙钟。进入精确准备后，真正剩额只能是 `MAX_WORK_UNITS - budget.counts['work_units']`。C `_pair_from_mesh_cache` 的真实费用、表面之后的支持费用、闭壳独立费用均应保持原账，不能用一次实测低水位替代最坏界。

同查询 prepared pair 复用不是“此前无成本”：闭壳分类拥有独立 262,144 Work / 16,384 pair / 16,384 ray 限额；它可能先用 C 的几何实现做了 admission、精确帧和树。后续表面建立新 `_Work`，可以共享准备或用 `_boundary_witness`（A:1056 / C:2067）验证真实同 pair 接触而直接发布零距。此时不是重新执行所有原生三角对，更不能把该零距复用和未知待求值混在窄相分母里。

对 `spatial_relation` 则相反，表面与严格支持共用 `holder['work']`（C:2611–2634 / A 对应函数）；后续闭壳仍是独立 `_ClosedWork`。043 低盒内部反例的预占 1,171,292、剩余 8,356 是被固定 `_Work` 初始化器制造的内部已花账，非普通公开 caller 参数。它说明预占时必须看真实剩额，不能将所有调用假设为新账本；本审计不改写原拒绝。

本源追踪**没有证明完整工作合同**。即使父任务另证每个原生面至多一次窄相且面数乘积不超过 16,384，还需证明 admission/引用顶点/帧与树/堆节点/平面过滤/投影结算/支持或闭壳/规范排名和发布的总账，以及精确位宽。`measurement_valid=True` 后还可能存在 witness precision/source-evidence 缺项；请求要求完整点与原生面时不能只检验标量已知。已缓存成功也不是 fresh 求解可完成的证明。

**绝对期限与图纸上的后备单位**

`run_stdio_mcp_server:2806–2861` 在 tools/call 外层打开原请求预算；`LiveSpatialService._request_budget:367–385` 复用同 service 的已有 deadline，不重置。宿主最近/扫描/选择性局部捕获进一步用 min(原剩余, socket timeout) 约束子读，原回调继续贯穿原内核。最终 `before_stdio_write:2841` 在编码后再次检查原期限；到期只发布一次 terminal error。Work 单位不能保证墙钟、取消或当前来源不变，版本资格证明应显式排除此类外部失效，不能承诺它们必答。

保守图纸选项是**整次请求**：在共同的当前捕获/身份与规范化处，对所有待求值对及复合尾项判资格，须早于首次版本专属几何准备或查询 mesh-cache 的使用；任何一项不能证明就保留 A。共同 `ReadContext.activate` 和合法缓存检查可能已发生，不把这些工作抹掉；后备方案仍需为选定版本保持独立的绑定、结果命名空间和同一原期限。其理由是单对、最近、扫描、局部和复合的缓存状态、准备对象及截止是不同的；到 C 已准备/已算未知之后再用 A 会成为被禁止的双跑/重试，不能借 C 树或已花信用拼接 A。此为保守发布单位建议，不是既有已实现路由；当前两版仍独立对照。本入口审计不实现混装、不用结果选路，也不按面数推算混合入口加速。

原始来源索引已写；新增内核调用、Blender、普通宿主和性能轮次均为 0。父任务的数学上界和已有矩阵决定最终可证范围，不能由这份调用链替代。
