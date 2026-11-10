最值得实施的一项是：**在已有 `transverse_boundary_interiors` 成功分支，交付实际触发判定的两片三角形及横向交叉位置。** 保持同一工具、同次场景采集、同次闭体求解。此处需要让求解器保留当前丢弃的局部变量，再投影到现有结果；不是只改 MCP 字段，也不需要新求解器。

本轮只读核查固定 HEAD `a5f9da9cdb66f95d8a4393f29362c18d5be366b4`。产品源仍为 `107641ec19919d56aa843c1949261590fc338148`、137源、canonical `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1`。未运行产品、Blender、模型或几何测试。

已经算出什么、在哪里丢掉

1. [classify_closed_solids，第449行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:449) 遍历实际候选三角片，当前就持有 `i,j,ta,tb,points`。`points` 是精确局部坐标中的相交线段端点。
2. [_closed_transverse，第338行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:338) 已验证线段非零、两片不平行，并计算精确中点，检查它严格落在两片三角形各自的相对内部。因此不是“只找到一个零距离点”。第459行判定成功后只返回 `relation` 和 `certificate`，三角片与中点没有进入结果。
3. [_closed_solid_fact，第257行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:257) 当前只投影关系、证书类别及合同。[_project_spatial_relations，第601行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:601) 会保留事实中的额外非共用字段，故无需新增一层协议；第614行固定的“仅证书类别”说明需要随实际证据更新。
4. 配对求解已有同次准备复用：[_closed_surface_facts，第269行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:269)。新增证据可以随闭体结果一起缓存；[pair_measurement，第408行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/scene_cache.py:408) 缓存的是完整 JSON 结果，并绑定有序网格对和算法版本。需更新闭体结果版本键，保证暖态不会返回缺少新字段的旧结果。

建议的最小交付

只覆盖上述横向穿越成功分支，每对最多一份局部证据，包含：

- 类型 `transverse_triangle_crossing`，含义为“两物体的这两片边界表面发生横向穿越”。
- 两片三角形在当前捕获中的序号及世界米坐标顶点，沿现有 target→candidate 顺序。直接从本次 `mesh.faces`／`mesh.vertices` 提取，不发送完整网格。
- 已算出的交线中点作为定位点；保持简短、明确的坐标状态。浮点坐标只是位置表达，不能把舍入后的坐标重新宣称为精确严格内点。可沿用现有点发布的精度处理；无法可靠表达时保留三角片和已成立的关系，定位点留空并给原因。
- 一句直接语义：“这里是相交表面的位置；该点位于两物体边界上。横向穿越与已通过的闭壳条件共同支持实体内部重叠。”不称为穿透深度、全局最小重叠区或共同内部点。

具体改动限于 `surface_geometry.py` 保留该分支的证据、`task_query.py` 投影及缓存版本、`live_spatial_mcp.py` 的结果说明与定向测试。世界坐标三角片本身来自已捕获的 binary64 顶点；不增加宿主调用，不重新做成对相交或点在实体内查询。若为定位点增加转换，只是常数规模序列化工作。

不能复用错的证据

- 第455行的 `prepared_holder['boundary_contact']` 只保存**遇到的第一处边界接触**，可能早于最终横向穿越三角片。它不是闭体证书的位置。必须在第458行成立的当前分支保留当前 `i,j,points`。
- [surface_proximity._boundary_witness，第512行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_proximity.py:512) 只证明点属于两片闭三角形；接着可复用为零表面距离。这不能区分相切和内部重叠，不能把已有 `nearest_witness` 改名当成新证据。
- “严格内点”目前也没有现成的双方共同体积内点。[第471行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/surface_geometry.py:471) 检查的是源实体的顶点或面中心是否在另一实体内部，点本身仍在源实体边界上；第480行无边界交点时亦查询双方各一顶点。获得一个严格位于两实体内部的点，或给出内球半径，需要额外构造和验证，不属于这批字段保留。
- 当前一般任务捕获使用 `temporary.loop_triangles`，见 [blender_host.py，第867行](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/blender_host.py:867)。这里的三角片序号属于本次捕获，不是原始 Blender polygon ID；不能承诺跨重拓扑稳定，也不应顺带新增原始面映射采集。

它能解决多少

任务第20行要求每一对有局部几何依据，允许见证点含义、局部表面、量测或充分空间关系，不强制孔结构重建。这项改动能让本次穿越判定有可指认的局部表面证据，减少模型为“到底在哪里穿过材料”再次读原生顶点的理由。

它不直接提供孔边界、通孔轴、材料分区、墙厚或自然语言角色识别。分离与近接对已有距离和最近点；本次不重新扩展它们。模型仍可能为了“穿过孔”的解释追加原生读取，因此**不能提前承诺3次调用会降为2次**。这一轮只验证该单项证据能否被直接采用；若追加读取仍是孔形状信息需求，记录该实际缺口，不继续堆字段直到旧题通过。

必要验收

1. 固定现有孔框任务及独立解析真值：每份返回的三角片确实来自同次目标/候选捕获，交线非零且横向；点的标签正确。普通顺序与对象交换均匹配，不能把两边或面序号颠倒。
2. 一个“先遇到边界接触，之后才遇到真正横向穿越”的例子，证明交付的是最终判定分支，未偷用第一处 `boundary_contact`。纯相切、分离、严格包含和 unknown 不伪造横向证据。
3. 冷暖态事实一致；几何改动后沿现有缓存键失效；检查同次捕获/闭体求解/宿主 RPC 的次数不增加。大平移下定位点无法可靠发布时，三角片来源和关系不被错误包装成精确共同内点。
4. 普通公开工具输出与内部结果同源，完整归档新增字节和序列化成本。一次受控消费对照检查模型是否直接引用新证据、是否减少额外局部几何读取，同时保留正确性和完整任务成本。字段增多或模型主观更信任都不能代替这项验收。

建议进入上述单项实现；不建通用证据服务，不增加新的采集入口，也不研究孔洞识别器。工程验收通过后进行一次消费验证，若没有减少实际工作且输出成本上涨，就停止继续扩写这一候选。
