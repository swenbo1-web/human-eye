# C1 来源包合同失配与纯离线复核

2026-11-13。原 C episode 的失败完整保留。它实际调用一次 BASE，资格阶段失败一次，REPEAT、EDIT 两次未运行。新报告仅解释原件并验证最小适配候选，新增 live、模型、API 和工程重试均为零。

## 已复现的失配

冻结 verify_c_turn 将 owner/INITIAL.json 传给原 qualification 的 bind_snapshot。owner 包只包含完整网格几何投影，原 bind_snapshot 要求整个 rich qualification schema 相等，仅忽略 pid 和 blend_filepath，因此实际 C1 按原冻结代码必然被拒绝。

本次对实际原件精确复现了 `actual geometry or source fields differ from qualified state`。离线准备曾只回放旧工程的完整 rich snapshot，遗漏了本轮 owner 真正输出 schema 的接口测试。这是资格适配和测试覆盖缺口。

owner 顶层只有 unit_scale_m 和 objects。相对 rich snapshot，缺少以下顶层字段。

```text
blend_filepath, blender_version, coordinate_frame, counts, frame_current,
local_coordinate_unit, pid, scale_length, scene_custom_properties, schema,
unit, unit_length, unit_system, world_vertex_evaluation
```

每个 owner 对象只有 name、vertices_local、matrix_world 和 faces。相对 rich 对象，缺少以下字段。

```text
animation_present, constraints, edges, evaluated_bound_box_local,
hidden_render, hidden_viewport, location, material_names, matrix_basis,
matrix_local, mesh_attributes, mesh_custom_properties, mesh_name, modifiers,
object_custom_properties, parent, polygons, rotation_mode,
rotation_quaternion, scale, shape_keys_present, topology, triangles, type,
vertices_world
```

已有字段没有观察到几何差异。实际 INITIAL 和 FINAL 都包含全部 24 网格、530 顶点、978 三角面。对象名称、全部本地顶点、每个完整世界矩阵、面索引和单位逐项匹配固定 BASE，INITIAL 与 FINAL 几何包也完全相同。

## 捕获原件补核的范围

C1 的实际宿主 wire 响应保留 human-eye-scene-delta-v1。其中 24 个资源的顶点和面、24 个 mesh 的资源引用及完整世界矩阵，与 owner 的实际几何逐项一致。捕获还记录 frame=1、scale_length=1、world/m 单位、same_main_thread_read=true、24 个对象的完整 coverage，以及与最终业务结果相同的 document_epoch 和 directory_sha256。

这些记录足以把本次实际求解几何与冻结 BASE 真值绑定。缺少的 rich 来源字段没有从参考包复制到实际包，也没有被重构为“当时已采集”。source_status=supported 是固定宿主资格门的声明，无法替代逐字段 rich 来源原始记录。完整顶点与世界坐标输入可测，未记录的动画、约束、parent 等原始字段继续属于未证范围。

## 未应用的最小修复候选

source_snapshot_candidate.py 保留冻结 C 入口的请求、trace、宿主、图片、几何事实和 kernel 检查。唯一功能调整是将整包 rich 绑定改为显式来源适配。

- owner narrow 包要求准确的两顶层字段和四对象字段，完整 24 网格名称唯一、单位、本地顶点、全部拓扑及完整世界矩阵与冻结参考逐字节规范编码一致。
- rich 包继续使用原 bind_snapshot，并增加相同的几何核对。旧 rich 来源字段变化仍会被原条件拒绝。
- 返回值保留原 C 核验报告字段，额外给出来源 schema、已核几何摘要和缺少的 rich 字段。它可以供未来修复使用，但本次未安装或替换冻结入口。

该候选没有放宽距离、数量、kernel、deadline、缓存或工程成功条件，也不把 narrow 包伪装为 rich snapshot。

## C1 事实复核结果

在同一实际 C1 请求、返回、私有 audit、宿主事件和原几何上，候选纯离线核验通过。

| 项目 | 结果 |
| --- | --- |
| 实际普通 default scan | 通过，缺省 response_detail |
| 实际宿主捕获 | 1 次，完成且无新图片和渲染 |
| 对象对分母 | 276 对全部对应固定真值 |
| 匹配事实 | 71 对，FP=0、FN=0、无重复 |
| 新 kernel | 112 |
| 单位、阈值与原米值 | 与固定真值及私有处置一致 |
| rich 参考包正例 | 接受 |
| rich parent 改动反例 | 按原来源绑定理由拒绝 |
| narrow 单位、缺对象、顶点、拓扑、矩阵五反例 | 各按预期具体理由拒绝 |

这建立 C1 已交付内容与实际几何一致的后验事实。原工程 episode 仍为 false，原 attempted=1、completed=0、failed=1、not_run=2 保持。C 的三轮复用、EDIT 失效和真正模型连续消费仍无本批完整证据。

## 原件保护与复放

review_c1.py 的两次纯离线运行均通过。它逐项检查冻结 qualification 和 episodes 下 297 份文件在读取前后摘要相同，冻结 verify_continuity.py 摘要仍为 `b92ec978d739ee0311144316d7e606a8ab8de2b7970bf8b01d2d8af074b9aa55`。实际原错误、未运行分母、清理和期限记录保持原件。

REVIEW.json 保存字段差异、具体来源报告、完整 C1 事实报告、反例理由和输入摘要。脚本只在本 postrun 子目录写派生结果。

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 verification/m4_surface_scan_continuity_001/postrun/qualification_review/review_c1.py
```
