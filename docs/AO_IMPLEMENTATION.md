# AO 联合观察与真实动作回读

本页先冻结本实现的接口与补充动作矩阵。固定 20 道公开题和评分门沿用 [AO 事前协议](AO_ACCEPTANCE_PROTOCOL.md)。

## Python 接口

`human_eye_fast.fast_affordance_out.encode(package)` 返回一次传输所需的 UTF-8 JSON 字节。调用端保留该结果即可冻结旧观察。输入是以下可信事实视图，调用端在编码完成前保持借用的 RB、TD、VG 数据稳定。

| 类型 | 字段和来源 |
| --- | --- |
| `AffordancePackage` | `observations` 是一个或多个按时间顺序的 ObservationFact，`outcome` 可选，来自真实动作执行。 |
| `ObservationFact` | `observation_id, frame_id, objects, clearance, deformation, image`。后三项独立可选。 |
| `ObjectFact` | `object_id, topology_generation, center_m`。中心可选，图像内的对象使用实际 RB 世界包围盒中心，供投影定位。 |
| `ClearanceFact` | `target_ids` 是依 BC A/B 次序的两对象 ID，`surface` 是 BC 的 SurfaceDistance。 |
| `DeformationFact` | `object_id, reference_frame, sample_frames, metrics, triangles, position_frame, position_vertices_m, selected_face_ids`。metrics 是 TD 的原返回；triangles 是相应拓扑的原始三角行；position_vertices_m 是 position_frame 的 RB 世界米制数组；selected_face_ids 是调用端显式要求的面。 |
| `ImageFact` | `path, rendered`，其中 rendered 是实际 VG Observation。路径相对公开包文件，调用端按原字节发布 rendered.png。 |

`human_eye_fast.control` 负责 AO 和 Blender/RB 的同步接线。`Goal(moving_id, reference_id, distance_m, tolerance_m)` 表示目标表面距离。`Action(action_id, before_observation_id, command, predicted_delta_m=None)` 绑定已交付观察和显式命令，命令是 `Translate(delta_world_m)` 或 `SetShapeKey(key_name, value)`。

`BlenderControl(scene, objects, goal)` 在指定 scene 的视图层执行。`observe(observation_id)` 采集并返回 `ClearanceReadback(observation_id, frame_id, target_ids, surface)`，目标顺序为作用对象、参考对象。`execute(action, after_observation_id)` 返回 `Outcome(goal, action, before, after, control_before, control_after, measured_delta_m, goal_reached)`，或在已达到目标时返回 None。实际控制对 Translate 是已求值世界平移列（米），对 SetShapeKey 是已求值键值。真实回读距离之差为 measured_delta_m。距离未定义时增量为 None。调用端串行执行，保持场景在观察和动作之间稳定，并在拓扑变化时新建控制会话。动作后重新采集两个对象的求值顶点和变换，以纳入父子或其他场景依赖。`bridge` 只借出最新一次采集的数组。最近点对可能因写入发生变化。公开包的对象顺序不改变 Action 的作用对象。

## 公开版本与列

候选顶层是固定列 JSON 数组 `[version, length_unit, object_ids, observations, outcome]`，版本 `he-ao/1`，长度单位 `m`。基线是同字段同值的紧凑描述性 JSON 对象，版本 `he-ao-json/1`。对象 ID 在包级表中去重，所有 object_index 引用该表的零基索引。Observation ID 在该包唯一，可由宿主持久引用。帧是实际整数帧。原始三角行号零基，作用域为对象 ID、观察帧和该观察对象行的 topology_generation。字段级机器可读列映射随证据发布。

| 行 | 固定列，基线用相同描述性键 |
| --- | --- |
| Observation | observation_id, frame_id, objects, clearance, deformation, image |
| Object | object_index, topology_generation, center_m |
| Clearance | status, target_object_indices, distance_m, witness_a, witness_b |
| Witness | original_face_id, point_m |
| Deformation | object_index, reference_frame, sample_frames, reduced_face_count, top_face_ids, position_kind, position_frame, faces |
| Face | original_face_id, max_principal_stretch, min_principal_stretch, max_area_strain, max_normal_angle_deg, max_centroid_displacement, score, position_m |
| Image | path, width_px, height_px, meters_per_blender_unit, mode, target_object_indices, mesh_object_indices, section, global_view, local_view |
| Section | point_m, normal, kept_side |
| View | viewport, camera_type, matrix_world_blender, ortho_scale_blender, clip_start_blender, clip_end_blender, shift_x, shift_y, projection_blender, gpu_view_m, gpu_projection_m, gpu_view_projection_m |
| Outcome | action_id, before_observation_id, after_observation_id, goal, command, control_before, control_after, distance_before_m, distance_after_m, measured_delta_m, predicted_delta_m, goal_reached |
| Goal | moving_object_index, reference_object_index, target_distance_m, tolerance_m |
| Command | kind, delta_world_m, key_name, target_value |

Clearance 的状态为 positive_gap、zero_distance 或 empty_surface。空表面时 distance_m 和两见证为 null，两个对象仍按 A/B 次序保留在 target_object_indices。witness_a 与 witness_b 分别关联该有序对的两个对象。无 clearance、TD、图像或结果的行整体为 null。TD 指标中的 null 表示该指标 undefined。TD top_face_ids 保持 TD 返回的顺序，faces 先选 Top-K，再追加未重复的显式选面。position_kind 为 face_centroid，位置由指定帧的实际三顶点计算。世界法向角单位为度，位移为米，面积指标是 max(abs(area_ratio−1))。参考帧和采样帧分别给出。图像继承所属 Observation ID 与帧，PNG 的左 512×512 为全局视图，右 512×512 为局部视图。SECTION 的全局仍为自然画面，局部裁去平面正侧。相机的矩阵按行存放，GPU view-projection 将米制世界点投影至 NDC，viewport 使用 PNG 内面板像素范围。命令 kind 为 translate 或 set_shape_key，未使用的命令字段为 null。测量和预测独立。有限数使用 Python JSON 双精度最短往返表示。

## 补充的真实动作矩阵

事前协议的第 19、20 题直接执行，其余动作矩阵单列，公开 20 题、字节分母和原门保持冻结。下面 20 个独立场景编号以矩阵顺序确定。所有距离按宿主浮点精度评分，要求实际宿主写入、更新 RB/BC、目标判定、独立几何核验和达到后再次提交零写。

| 组别 | 4 个固定场景 |
| --- | --- |
| T01–T04 世界平移 | 01 的平行盒以 +0.025 m（公开 19）、−0.025 m、+0.125 m 沿世界 X 改变间隙；第 4 例从面接触显式沿 +X 移出 0.025 m。 |
| T05–T08 父级变换 | 03 的毫米单位、90° 父级、子级反射非均匀缩放；分别沿世界 Y +0.00025 m 与 −0.00025 m；第 3、4 例改用 0.01 m/BU，以相同宿主矩阵和 ±0.0025 m 世界 Y。 |
| T09–T12 近面变化 | A 为单位闭盒，B 为 x 方向 [2,3]、y/z 为 [0,1] 的闭盒；B 沿 +Y 分别移动 1.25 m、1.5 m、2 m，实际距离为 hypot(1, dy−1)。第 4 例先以 dy=1.25 m 布置，再沿 −Y 移回 1.25 m。 |
| T13–T16 尖点形变 | VG 无遮挡四面体，旋转 0、g=0.004 m。A 尖点的 Shape Key 只沿 +X 偏移 0.003 m；实际目标键值 0.5（公开 20）、0.25、0.75、1。 |
| T17–T20 反向及零距控制 | 相同四面体与偏移，键值从 0.75→0.25、0.5→0、1→0.5；最后 g=0.003 m，键值 1→0.5，从零表面距离用显式控制打开间隙。 |

编码性能测试使用两套真实事实状态。状态在每次配对间切换，按每两对翻转先后顺序，使两套状态分别覆盖 AB 和 BA。每样本完整编码 20 道任务的 22 次发布。第 01–18 题各发布一次，第 19、20 题各先发布动作前观察，随后发布前后观察及动作结果。每次计时都从同一套未投影事实新建动作前包并编码，旧字节只用于计时后核对。公开测试另检查序列化后在 RB 更新下保持字节和事实。GPU 与性能测量按主干协调窗口串行启动。

## 复现和证据边界

```powershell
& 'D:/human eye/venv/Scripts/python.exe' -B verification/benchmark_fast_affordance_out.py `
    --blender 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' `
    --output-dir artifacts/ao/<new-run>
```

输出目录必须是新目录。三个 Blender 进程使用 factory-startup 依次运行，每进程保存 5 次预热和 31 对正式样本。计时包含按题选择传输行、组装、序列化和 UTF-8 编码。候选用固定列，基线直接组装同字段的描述性键，并用同一标准 JSON 编码器。候选和基线共享事实输入与 schema。每题字节取该题全部发布之和，再比较 20 题的字节中位数。保留 22 次发布及 20 题的字节数，池化的批次时延按线性插值算 p95。PNG 按实际引用去重，和共享 schema 分别记账。

`process-*/state-*/` 包含任务、两种编码和相同的实际 PNG。`process-*/private/` 只给评分者，包含原生几何、解析预期、动作证据和 RB 更新前后冻结包。`consumption.json` 记录每题脚本消费及负例，`worker.json` 记录设备、原始时延和分段成本。`chain_stage_sum_ns` 是已计量采集、求解、VG、动作和发布段之和。它排除夹具创建、评分和磁盘，和另列的夹具墙钟时间及完整批量编码门是不同的测量。图像读取计入脚本消费耗时。
