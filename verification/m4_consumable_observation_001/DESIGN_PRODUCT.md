# 可直接消费的观察事实

产品触点为 `ActiveObservationSession.short_facts()` 与 `project_active_observation_brief()`。Host沿原入口调用一次short_facts，并沿原来源绑定补充host身份和域外scope。现有覆盖索引、覆盖状态及实际receipt提供全部新字段。

## 核心事实

`short_facts()` 保留既有regions、observations、coverage和世界位置字段，增加以下两项。

- `inspection` 使用 `active-inspection-v1`，包括注册池view_names、有限池scope、state、stop_reason，以及supported、covered、unobserved、pending_geometric_candidate、no_geometric_complete_candidate、pixel_insufficient、covered_without_witness计数。
- `region_evidence` 按既有region顺序逐项记录roi_id、complete_witness、unobserved_reason和view_reasons。complete_witness引用实际receipt的view_name与该receipt的pixel_row_index。view_reasons仅为未观察区域分组视角理由。

见证按实际receipt既有登记顺序选择第一个符合条件的像素行。必须同时位于当前view_masks的完整几何位、receipt readable集合，且实际行front_facing/readable为true并满足行内像素门限。readable本身不建立几何完整性。世界向量、范围、owned anchor仍从原regions和pixel rows读取。

一次遍历现有receipt像素行同时构造既有observations与见证。一次覆盖查询和已有view_masks/classifications同时供巡检摘要、区域状态及未观察理由。新的派生过程不访问顶点/三角形，不调用投影、遮挡或renderer，也不创建持久Store。

## 未观察与停止语义

- 没有完整几何候选时保留 `no_front_facing_candidate`、`positive_area_occlusion_all_front_views` 或一般 `no_complete_geometric_candidate`，逐视角理由来自现有classifications。
- 仍有未观察完整几何候选时使用 `unobserved_geometric_candidates`，对应视角组直接标记 `unobserved_geometric_candidate`。候选不承诺未渲染像素必然可读。
- 完整几何候选已观察但未达到可读条件时使用 `pixel_evidence_insufficient`。
- 无实际receipt为prediction_only。尚有候选为observation_required。有限池没有可补完整候选而仍有剩余为finite_pool_exhausted。全部支持面有见证为all_supported_regions_observed。covered状态缺少完整可读见证时显式evidence_incomplete。

scope始终为注册有限相机池。域外组件继续位于原scope.patch_support。finite_pool_exhausted保留unobserved计数，不代表域外组件解决。

## 默认投影

新事实投影标识为 `active-observation-brief-v4`。保留原表及其位置/像素/来源语义。

- regions表增加 `complete_witness_pixel_index`、`unobserved_reason`、`unobserved_view_group_indices` 三列。见证直接引用既有pixels表的零基行号。
- 顶层 `unobserved_view_groups` 使用columns `[reason,view_indices]`。相同分类与视角列表在本包内复用一个组，view_indices引用inspection.view_names。
- 顶层inspection保留上述小摘要。covered区域不重复输出逐相机分类矩阵，见证位置/法向和图片通过原region/pixel/image索引连接。

旧v1/v2/v3输入缺少新事实时沿原投影，full/debug保留原内容并携带新增事实。默认工具结果仍只有一个JSON text块，其后为原生图片块。桥接直接保存这一text原字符串。

## 离线验收

仅使用已有同源SERVICE_RESULT/收据、已冻结独立几何真值及最小CoverageIndex元数据。覆盖138/115见证、23剩余分类、漏报面、三位置、readable但不完整、prediction、像素不足、scene/camera/patch失效及旧格式。所有几何求解和raster入口在离线检查中禁止调用。既有零raster投影/协议子集另行记录，依赖renderer的项目列为未运行。
