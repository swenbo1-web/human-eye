# 两阶段离线观察原型

`draft.py` 消费一份根协调者固定的 bundle。调用方先读取空间目录，再明确选择对象、几何字段及已有关系字段。两个函数均返回可序列化的字典。

## 输入

bundle 包含以下字段。

- `source` 保存原始几何、关系回包及其同一来源记录的绑定。具体文件 SHA、宿主 context 和离线 ID 映射由输入固定。
- `unit` 为 `m`，`coordinate_frame` 为 `world`。
- `objects` 中每项包含 `object_id`、`name`、`vertices_world`、`faces`、`face_kind`。
- `relations` 中每项包含 `target_id`、`candidate_id`、`facts`。facts 中的值沿用原关系回包。

`object_id` 采用输入给定的离线快照标识。输入来源记录保存已有宿主对象 ID 与该标识的对应关系。对象名与 ID 可以分别变化。原始 `faces` 使用 `face_kind=source_polygons`。每个多边形的数值是 `vertices_world` 中的零起点顶点索引，有效范围为 0 到顶点数减一；多边形数组的顺序沿用本次原始捕获。关系证据的捕获三角片编号随原事实保留。

所需 world 坐标可从同一记录的 `vertices_local`、`matrix_world` 和单位尺度派生。当前宿主实现位于 `human_eye_plugin/blender_host.py` 的 `_resident_capture`，逐坐标公式是矩阵前三列点积加平移后乘米制尺度。根输入准备过程负责固定该派生及逐值对照。

## 调用

`directory(bundle)` 返回所有对象的 `object_id`、`name`、世界 `aabb.min` 和 `aabb.max`。初稿另外提供 `center`，其含义是 AABB 中点，调用方可通过 `(min + max) / 2` 派生。根响应包含原 source、单位、坐标系及 gaps。

`selected_observation(bundle, request)` 的 request 包含与 bundle 相同的 `source`、显式 `objects` 与 `relation_pairs`。对象选择项包含 `object_id` 和 `fields`，当前字段为 `vertices_world`、`faces`。关系选择项包含 `target_id`、`candidate_id` 和 `fields`，字段名对应已保存的 facts 键。

选定响应只组合这些字段。faces 同步携带 face_kind，关系 facts 深拷贝原值。缺对象、缺字段和缺有序关系对各自进入 gaps，并使整体状态成为 partial。source 不匹配时返回 unknown 及 source_mismatch。原关系字段中的 unknown 状态继续沿用。

CLI 可分别执行以下两条命令。输出为紧凑 UTF-8 JSON。

```text
python final.py directory BUNDLE.json
python final.py selected BUNDLE.json --request REQUEST.json
```

## 现有产品接点

当前 `live_service.py` 的 `_overview` 已组织对象名称和世界 AABB。`_observe_task` 在一个读取锁内调用 `host.capture_task_scene`，随后经过 `ReadContext.activate`、`normalized` 和 `result`。宿主的 `_resident_capture` 按选择保留捕获，并按资源和物理姿态复用世界坐标。

后续实际入口的预期为目录一次宿主请求、显式选定观察一次宿主请求。第二次请求可在该选定捕获上取得现有 task 关系与所需原始几何。同代际复用依赖真实 capture_state、资源和姿态一致。该入口的实际采集、求解与缓存计数待入口验收。

本原型实际宿主请求数为 0，生产 helper 执行数为 0。它直接投影已固定数据，局部对象索引只在单次函数调用中构造。ReadContext 的真实代际、选择与归一化契约保留为接入位置；离线运行使用原始 source 绑定。

## 一次简化评审

初稿 SHA 固定为 `e101bb32c9a9582f596f2e41d3d3ce02864b0f8865513b666396bb2fec1e220f`。根协调者根据补查账本批准删除正常与缺失两处 center 赋值，形成 `final.py`，SHA 为 `4faa9a915fc4e139978496cf53505be248e98dc058493c2649d5e2a864a9ac73`。选定观察和 CLI 函数的 AST 保持一致，目录函数的 AST 差异只有两处赋值。初稿原件用于统一前后测量，唯一评审记录保存在 `SIMPLIFICATION_REVIEW.json`。真实字节、时间与内存结果由根协调者统一测量。
