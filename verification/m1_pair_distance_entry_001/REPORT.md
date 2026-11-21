# M1 整件距离工具入口

**文案工程验收通过。** `human_eye_scene_observe` 首个量测例现在是无图的有序 `objects: [A, B]`，只请求 `surface_proximity`。说明同时指出该事实包含世界最近点，以及正距离时的世界 A→B 方向。候选集合的关系事实组合随后介绍。

候选 `c8f87c540f802fe7b85caae95a8ac86b0f43518f` 直接派生自 `95fd44bb8c4b6b992d8849f38ffbe5d778b0ac5a`。143 个运行源经 Git、wheel、隔离安装逐件核对，唯一变动为 `live_spatial_mcp.py` 的观察工具描述常量。工具描述 **3,255 → 3,254 B**。实际 `tools/list` 线包 32,693 → 32,688 B，整个握手加目录的 stdout 34,963 → 34,934 B，包含各自运行源标识。实际目录的输入 schema 和另外四个工具定义逐项相同。运行源 `0e85052a0a4dec4ee42f8f9f62729a416b57445783224b303723b515ada0a147`，wheel `319b419852ecd1e7af84f773e3ef2a27fdb5737ae2a186c00e242e9f1d95c503`。

## 三次实际拒绝

| 历史调用 | `target/candidates` | `requested_facts` | 原派发至 CLI 收到回包 |
| --- | --- | --- | ---: |
| N15 P1 #4 | N15→N23 | `surface_proximity` | 51.502 ms |
| N15 P3 #4 | N15→N23 | `surface_proximity` | 56.214 ms |
| M09 P2 #2 | M09→M03 | `surface_proximity, nearest_witness` | 43.530 ms |

三条原错误为 `task set requires surface_proximity with closed_solid_relation or spatial_relation and optional aabb`。每条历史正文 718 B、内层 RX 879 B、外层 RX 857 B。实际原请求从 ZIP、内外线包、Owner TCP 和 CLI 事件逐层绑定。基线与候选各用实际 MCP 入口回放三条内层原请求，三条响应均逐字节等于各自原件，观察服务进入次数为零。原执行、重试授权和写入状态共同保留。

## 合法有序请求及兼容性

| 整件对象对 | 最短表面距离 | A→B 世界单位方向 | 直接请求正文／回放线包 |
| --- | ---: | --- | ---: |
| N15→N23 | 165.245261560 mm | (0, −0.962206108, +0.272322246) | 1,413／1,643 B |
| M09→M03 | 234.375 mm | (0, 0, +1) | 1,296／1,526 B |

重放实际安装的观察服务和 MCP 序列化，宿主读数来自封存的当前选中对象及完整场景。N15 来源有 28 对象、416 点、744 三角，M09 有 21 对象、148 点、184 三角。两套整件几何均独立验证最近点在对应的原表面上，倒序距离相同且方向反转。

每版在两套资产各复放正向、倒序、关系集合的两种组合、严格 `nearest_witness` 和独立 AABB，共 12 项。排除各请求独有的 trace ID 和真实运行源标识后，回包逐项相同。N15 的严格见证量测有效，M09 的开放表面保持 `unsupported_solid_geometry`。M09 的闭体关系仍为 unknown，表面距离和对应世界点继续可测。

一次隔离构建和安装。新增 Blender、模型、构图、资产重建、替补、Google、额外 API 或费用均为 0。N15 与 M09 的历史任务保持封存。本轮验证了说明与现有接口契约一致，模型自然选用该首例和减少拒绝的效果尚未实测。

- [真实拒绝与逐层核验](checks/REJECTS.json) · [合法回放、点对与兼容性](checks/POSITIVE_REPLAY.json)
- [基线工具目录原输出](evidence/positive_replay/A/CATALOGUE_STDOUT.bin) · [候选工具目录原输出](evidence/positive_replay/B/CATALOGUE_STDOUT.bin) · [安装绑定](install/PRODUCT_RUN_BINDING.json)
