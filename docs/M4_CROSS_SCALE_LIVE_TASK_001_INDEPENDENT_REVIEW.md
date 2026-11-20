# M4 复杂全场对照 001 独立复核

2026-11-20。固定实施 `b28155028b47b762d920aa79bd533485c8d9a4d5`，启动前 `8a54aa32dee48ac98bbd5d00c0d7f8f96a0376c7`。两个资格槽均在 Blender 启动阶段失败。正式原生与插件各一槽均未运行，评分、实际取数、构图、模型用量和完整任务收益均未测。固定资产已经构建，不需要重新生成。产品差分 0。本轮独立复核仅检查保存的源码和原件，新增 Blender 与模型调用均 0。

固定场景 `D:/he_m4_cross_scale_live_task_001/fixture/main.blend` 的 SHA256 为 `f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce`，21 个对象、148 点、184 个求值三角。保存后重开数组逐项一致。从 Blender 重开数组独立以有理数复算得到 87 平面分量、84 矩形，任务目标 M02、M06、M09 各为 `[0,1]`。对其余三角投影并裁剪深度和目标矩形，得 M02 六向无正面积遮挡，M06 六向受遮挡，M09 只在 LEFT/BACK 无正面积遮挡。实际局部像素和回包仍待资格。

## 失败复核

1. `harness/runtime.py:58` 复用 `m4_live_source_region_task_003/harness/owned_blender.py`，后者启动和执行都有 `visual004` 双网格专用清单。`display_steps_enabled=False` 控制 QA 写入开关，库存判定仍被执行。两槽的 Blender stderr 都记录了启动前的 `visual004_native_display_fixed_mesh_inventory`。实际产品握手的离线预检通过，启动失败发生在任何场景业务请求之前。
2. 两份启动失败回执中的 `cleanup_errors` 均为空，原副本与固定 `.blend` 字节一致。上层 `run_slot.py:51` 要求成功启动后才具备的 `Blender_close`，导致次生 `KeyError`。先发生的失败及次生失败都保留。
3. 通用 `m4_global_local_qualification_001/harness/reused/owned_native.py` 已在上轮真实 Q1 上通过。它提供同样的 `NativeSession.run` 协议，以及源文件、几何指纹、退出和超时守卫。其默认 `qa_vertex_patch=None`，返回 `initial_geometry_fingerprint` 与 `final_geometry_fingerprint`，没有源面专用的 `display_restored` 字段。修复需要同时调整装载和收尾解释，正式评分也有同一旧字段依赖。

| 原始时钟 | 资格原生 QN | 资格插件 QP |
| --- | ---: | ---: |
| Blender 启动到失败处理 | 0.789 s | 0.709 s |
| 完整资格窗口（失败） | 1.329 s | 1.183 s |
| 业务请求／栅格／模型 | 0／0／0 | 0／0／0 |

场景构建完整窗 0.924 秒，内部构建、保存和重开核验 0.152 秒。独立逐字节核对 47 个 Git 路径、387 项冻结输入和 112 件运行原件（905,374 B）。ZIP 为 `D:/he_m4_cross_scale_live_task_001/ORIGINAL_RUNTIME.zip`，SHA256 `619625cb05409ce46be57aa8159df9021ca76375a4df6234866f3f1710169f0d`。旧的两次资格失败及两条正式未运行记录维持各自状态。

下一[宿主恢复批](M4_CROSS_SCALE_LIVE_TASK_RECOVERY_001_PLAN.md)使用同一 `.blend`、真值、两边共同工具权限与固定产品。先让两路具备真实的只读进入和退出凭据；原空间任务资格通过后直接执行一对正式对照。
