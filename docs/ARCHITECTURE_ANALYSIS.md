# Human Eye 的数据流

桌面 MCP 接受空间查询，向 Blender 读取当前求值场景，在引擎中做几何计算、确定观察方向并生成回包。量测范围和画面可见性分别记录，因此隐藏的参照对象也可以参与明确请求的距离量测。

| 模块 | 职责 | 代码入口 |
| --- | --- | --- |
| M1 接入与交付 | 校验工具参数、选择简报或全文、按当前帧绑定 PNG。Hook 接入宿主事件。 | [MCP](../human_eye_plugin/live_spatial_mcp.py) · [Hook](../human_eye_hook.py) |
| M2 采集与传输 | 获取当前场景与对象身份，按捕获代复用网格和增量。显式启用的闭盒量测可以只传选区与参照的必要几何。 | [Blender 桥](../human_eye_plugin/blender_mcp_host.py) · [驻留与增量](../human_eye_plugin/scene_residency.py) |
| M3 空间求解 | 按请求的整件或选区计算距离、方向和表面点对。按工作预算选择 R3 或 032，并保留源面归属。 | [表面距离](../human_eye_plugin/surface_proximity.py) · [任务求解](../human_eye_plugin/task_query.py) |
| M4 主动观察 | 根据当前视角、选区几何、遮挡和像素证据选择全场或局部图。报告单帧采样或可证明的完整可见性。 | [主动观察](../human_eye_plugin/active_observation.py) · [选区](../human_eye_plugin/source_region.py) |
| M5 观察与量测组合 | 将画面、选区或整件量测绑定到同一次有效捕获，通过工具回复交给调用方。 | [现场服务](../human_eye_plugin/live_service.py) |

同一选区的图像和量测可用 `region_ref` 复读。引用随实例、捕获代与修订核验。局部图中的像素归属可追溯到当前求值网格的源三角。仅有部分面产生像素时，接口保留可见性的未知状态。

全场发现、目标局部取景和闭盒无图量测有不同的传输成本。评估性能时分别记录宿主双向字节、MCP 回包、实际构图数和整题耗时。工程回放与模型自然消费的记录可分别复核。[闭盒实测](https://github.com/swenbo1-web/human-eye/blob/1bf82282685d5335e0682b6174b44e17cc69928a/verification/m1_m2_source_region_scoped_measurement_consumption_001/REPORT.md)
