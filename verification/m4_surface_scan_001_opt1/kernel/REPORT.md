# OPT1 扫描对象依赖缓存

## 实施

本子任务修改 `scene_cache.py`、`task_query.py` 和 `surface_scan.py`。`read_context.py` 保持原字节。

扫描 reducer 先完成既有 packet 校验、来源和端点 union 校验，再调用 `_bind_surface_scan_meshes`。该函数只接受 `SceneDeltaDecoder` 生成的 `SurfaceScanDependencies` 精确类型，并要求 `matches_capture` 核对当前原始 packet。字典、缺失绑定、旧 token、复制 packet 或绑定后的 capture_state 变化均回到既有测量键。

每个当前规范化 mesh 的依赖摘要覆盖桥接提供的宿主源码、decoder owner、宿主实例和 epoch、document epoch、对象 incarnation、resource id/revision/admission、实际矩阵和单位尺度，再加入当前 runtime source SHA。绑定表只保存当前最多 256 个 mesh 对象引用和短摘要。它不保留 token、原始 packet、几何副本或运动历史。

`_bind_read_meshes` 在每次选择绑定及 reset 时清空当前扫描映射，reducer 在当前计算中重新绑定。已有 ReadContext 的 generation、规范化、完整结果、未完成进度和覆盖规则继续沿用。已有 measurement store 跨 generation 保留，命中以每对实际依赖决定。

只有扫描调用 `_surface_pair_measurement(..., _surface_scan=True)`，继而使用 `pair_measurement` 的私有开关。完整 pair 键继续包含既有 algorithm_version、source、单位、坐标系、见证容差和 exact-rank 参数，并保留 focal/reference 顺序。普通 task、nearest、solid 和 support 路径使用原 metadata 键。

公开返回结构不增加字段。私有每 pair 诊断增加 `surface_dependency_used`、`surface_dependency_key`、有序 `surface_dependency_objects` 和 `surface_dependency_cache_hit`。这些值可与 cold 原件逐对比较。

## 容量

复用同一 `_measurements` OrderedDict、序列化结果、字节计量和 LRU 淘汰。ReadContext 仍为 2 MiB、256 个 measurement slot。新增的当前 mesh 引用和摘要是有界元数据，其解释器内存由主任务实际内存记录披露，不将 measurement payload 计量解释为完整 RSS 上限。

默认 256-slot 实验插入 257 个不同参数键后，最旧结果确实被淘汰。较小的 2-slot 实验也发生真实重算。1024-byte 实验拒留超额结果。所有案例的维护计量与独立重新计量一致。

## 定向验证

18 项新增定向及 104 项相关旧回归，共 122/122 通过。记录为 `UNIT_03_FINAL.txt`。本子任务未启动 Blender、主 fixture 性能、模型消费者或业务 API。

新增案例覆盖局部移动仅重算受影响 pair、当前名字输出、同面数几何变化、同名重建、删除再进入、单位和 host/document epoch、runtime 和 decoder owner、阈值 A/B/A、有序见证、source unknown 恢复、测量 unknown 后重试、实例范围 unknown、低 cap 续算、命中免预算、缺失和伪造绑定、旧 token 和复制 packet、默认与受限容量淘汰、普通 metadata 键独立性。

三对象机制例中 cold 为 3 次新核，静态复问为 0 次新核，移动一个对象后为 2 次新核和 1 个未变 pair 命中。未变 pair 的完整 measurement key 与 cold 一致，受影响 pair 的 key 改变，见证点方向仍与有序输入一致。主装配的 112/0/10 与 104 次复用由主任务冻结候选后的真实入口验收决定。

## 连接状态

本子任务自行查询 Agent Learning，连接为 unbound、host epoch 5，未使用其他会话句柄或旧任务 assignment。计划字节 SHA256 已与派单核对。
