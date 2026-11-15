# M5 观察与定量接线

产品基线为 c309d7e，交付基线为 bc177d。实施依据为当前完整计划、根独立验收及本批固定 PLAN 与 REQUESTS。本文件记录 V1，实际资格后的唯一优化另按热点证据决定。

## 现有流程

active_observation 经过 query_policy、LiveSpatialService、真实宿主捕获、source_binding、observe_capture、MCP 图像及默认 brief。M4 保留原对象顺序和源面编号，geometry 生成 Fraction 坐标与几何键，图像 MeshEntity 使用 geometry 合成 ID。公开 binding.objects 将图像对象序号映回真实 host_id、instance 和名称。

独立 task 请求重新进入 capture_task_scene、ReadContext 的 task_selected 选择状态、_validated_scene 和 task_result。M2 驻留资源可以避免再次 to_mesh 和 world transform，第二请求仍有宿主往返、选择元数据、选择状态和规范化成本。实际删除的工作由 A 资格的原始计数确定。

ReadContext 已按 instance_id、epoch、revision 切代，选择缓存还包含 entry、完整 selection_key 与查询。M5 保留该全局规则。新增内部选择状态使用派生 selection_key，跨捕获的同代判断只比较前三个字段。

## 公共合同

query.task_query 接受一个原 legacy task 查询，包含 mode、objects 和 requested_facts。PAIR_FACTS 仍要求两个有序 selector。当前附项域没有 target/candidates、set scope 或 geometry 输出请求。原观察和原 task-only 调用继续使用现有路径。

默认 brief 和 full 均增加顶层 task_result，保留 task-query-v3 及其全部已请求数值、unknown 和见证。surface_proximity 最近点位于 facts.surface_proximity.value.nearest_witness。图像覆盖仍只沿原有限视图和原区域域。

task_result.binding.observation_source 使用 active-observation-task-source-v1，measurement_scope 为 whole_objects，capture_scope 为 observation_task_objects。其 parent_binding_sha256、parent_source_binding_sha256 和 parent_capture_scope 指回本次观察。capture_state 代表派生内存视图，同代三元组沿父捕获，selection_key 是派生选择摘要。

objects 为实际定量对象列表。每项含真实 object_id、instance_id、observation_object_index、geometry_id、source_triangle_count、source_triangle_index_ranges 和 ordered_geometry_sha256。完整原面集合使用零起始闭区间，原始面顺序保持。图片外补读对象的 observation_object_index 和 geometry_id 为 null。geometry_id 作为映射别名，映射依据为对象序号与真实 ID、instance。同形对象可以在此映射中共享该别名。

ordered_geometry_sha256 的原像为直接来自已解码捕获的 vertices 和 faces 两字段。列表顺序、原始世界米数值、原始面索引顺序均保留。JSON 使用 sort_keys=True、separators=(',', ':')、ensure_ascii=True、allow_nan=False，UTF-8 后计算 SHA256。该摘要覆盖 canonical geometry 键无法区分的面重排。

## 内部来源

父捕获保持原 scope、host_identity 和原件。新增 observation_task_objects 内存视图携带真实 ID 与 instance 子集、原 task_selection 语义和派生 revision。_validated_scene 的新私有标志复用现有几何及选择校验。普通 task_selected 入口仍拒绝该派生 scope。M3 算法保持原语义。

名称解析先使用父 full scene_directory 的全场名称空间。场外同名对象仍使 selector ambiguous。重复 selector、ID 与名称别名指向同一对象时沿原 pair_reason。选出网格保持父目录顺序、每对象完整原始顶点和面顺序。

已有对象直接取自父捕获。只有已解析且缺失的真实 ID 才通过一次 capture_task_scene 补读。补读发生在图像与测量之前。generation 不可用、三元组变化、document_epoch 变化、instance 变化、返回 selector 不符或对象不可用分别拒绝。不会组合跨代数据后给出当前一致成功。

## V1 与计量

V1 修改 query_policy.py、live_service.py、auto_router.py、task_query.py 和 live_spatial_mcp.py。使用原只读锁、原请求预算、现有 ReadContext 和现有 task_result。主任务两对象已在父捕获中，定量新增详细捕获为0，新增 raster 为0，fresh surface 求解一次。

V1 单独规范化派生网格，并为已观察对象计算显式 geometry 别名。新增计数记录规范化调用、对象/顶点/面、数组载荷、顺序摘要、别名解析、补读及 M3 诊断。内存载荷与实际复制次数分开，由纯检查及资格原件记录。后续只根据资格中的真实热点做一次优化。

当前纯检查使用合成宿主数据和无图片的正常服务入口。真实 Blender、MCP 进程、raster、安装与模型执行均由根控制。
