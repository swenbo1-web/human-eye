# 支撑平面只读纠偏候选

2026-10-28 当前聊天重载验收：已实际载入 v19／9.7.2+20261028.support.discovery.r1（a0198acc…／installed_distribution／68 文件），状态健康、目标账本 0，旧配置快照拒绝已解除。当前 MCP 完整发现唯一支撑面，实测间隙仍为 3.1304261516453477 毫米；回填完整 selector 的 1 毫米目标预览只返回单步限幅候选，未移动。人为改错客户端 revision 的预览被拒绝并要求重新观察；没有实际编辑宿主来制造这条负例。独立 Fraction 真值、768×768 原生 PNG 和全 14 Scene 不变均已核对。

真实用户三维回复已在模型该轮工具调用前触发 v19 UserPromptSubmit，自动交付完整几何文字；五组定义保留。本轮还核对了 clearance_segment 预览的 PreToolUse／PostToolUse 去重，不能当作 execute:true 的动作链或 transform 各事件已通过。自动原生图片仍未证明，Hook 为 text_only。先前独立安装私有场景的 12 次移动是另一阶段证据，本聊天本轮零移动。

只读安装 SDK 边界矩阵 12 组／28 次调用／277 项检查通过；凹体、开放 reference、穿透／接触和有限面外一 ULP 明确 unsupported，几何／有理复杂度和过长 revision 返回 unknown，不放宽门。真实多候选截断未覆盖。下一单点候选先检查审计日志大字节／少行时重复整写和轮转，再考虑纯距离观察的对齐按需；两项均未实现，成本对照仍 pending。既有 27.84%—36.71% 文本字节减少不等于端到端或模型提速。工程构建可继续有限验收，整体公开发布门仍为 false。

[当前重载阶段](../verification/fixes/20261028_v19_reload/REPORT.md)、[当前量测与预览核对](../verification/fixes/20261028_v19_reload/CURRENT_VALIDATION.json)、[真实用户文字 Hook 审查](../verification/fixes/20261028_v19_reload/REAL_USER_HOOK_REVIEW.md)、[只读边界矩阵](../verification/fixes/20261028_v19_reload/MATRIX_REVIEW.md)。接口继续见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)。

只读求解器、已安装 SDK 与当前 MCP 的候选证据分列；当前预览证明候选受支持，不证明宿主已执行或目标已完成。

以下保留此前阶段记录，尤其 v19_activation 的待重启状态仅表示当时阶段；当前状态以上文和本轮重载报告为准。

2026-10-28 最新状态：v19 工程构建 9.7.2+20261028.support.discovery.r1（a0198acc…／68 文件）已离线安装并完成磁盘激活，新注册进程实际验收通过。当前聊天仍为 v16 旧配置快照，返回 stale_configuration_snapshot，需重启后核验；真实新用户 Hook 未通过本版验收。四文件迁移保留五组 Hook、Agent Learning 当前配置与状态，state 仅改配置绑定；磁盘激活不等于宿主信任或当前聊天重载。

显式 query.support_plane_discovery 已实现当前对象对的精简发现，完整 selector 可回填有界执行段。四模板文本字节中位减少 27.8448%—36.7095%，本地服务仍增加约 1.8—8.0 毫秒，不宣称模型或端到端提速；默认 PNG 保持。接口与边界见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)，[新注册入口结果](../verification/fixes/20261028_v19_activation/REGISTERED_ENTRY_RESULT.json)和[配置保留结果](../verification/fixes/20261028_v19_activation/activation/PRESERVATION.json)。

v17 只读数学合同经 v18 执行段承接，v19 增加精简发现与初始选择绑定；下方 v17/v18 未安装描述保留当时状态。

以下为此前阶段记录，保留当时版本、命令及验收边界；当前状态以上文及精简支撑面发现说明为准。

最新：v18已将此候选接入有界执行，并在独立新建的真实Blender场景完成倾斜／斜面1毫米目标及精确恢复；当前安装与聊天仍为v16。见[执行段接口](SUPPORT_PLANE_SEGMENTS.md)与[实际验收](../verification/fixes/20261028_support_plane_segment/REPORT.md)。下述v17纯SDK合同继续适用，其中“后续接入”为该只读阶段的历史说明。

2026-10-28。源码候选v17新增纯SDK `human_eye_plugin.support_plane_candidate`。已安装并正在使用的v16继续负责实际MCP与自动观察；本阶段没有接入或扩大动作入口。报告及计时见[源码验收](../verification/fixes/20261028_support_plane_candidate/REPORT.md)。

新函数 `solve_support_plane_candidate(scene, request, *, expected_feature_signature=None)` 消费世界米制快照，提出最多一次零旋转平移，既不读写Blender，也不创建执行段。旧 `solve_clearance_candidate` 的世界轴箱体合同保持。

```python
from human_eye_plugin.support_plane_candidate import solve_support_plane_candidate

result = solve_support_plane_candidate(scene, {
    "focal_id": current_focal_id,
    "reference_id": current_reference_id,
    "reference_triangle_index": selected_original_triangle_index,
    "direction_world": [0.0, 0.0, 1.0],
    "target_clearance_m": 0.001,
    "clearance_tolerance_m": 1e-7,
    "max_step_translation_m": 0.01,
    "max_total_translation_m": 0.04,
})
```

对象与面索引必须属于输入快照；没有固定通用的“第2面”。参考面是调用者明确选择的原始有向三角面。函数不会拟合包围盒面、补凸包或自动切换到相邻三角／凹槽内壁。方向必须是三个有限非布尔数字，非零有限长度，由SDK归一化；允许计算结果沿相反方向纠偏。两个限额约束本次候选欧氏长度，max_total只是本次上限，不意味着已实现累计执行账本。接口没有max_steps或max_duration。

## 距离与候选证明

两个网格须通过精确原始半空间凸性、闭合有向单壳拓扑、单连通面邻接和正体积检查。每对网格分别最多64顶点/128三角面，整个输入最多2048顶点/4096三角面；另保留原有几何工作准入门。Fraction输入分子／分母位长上限512，中间精确运算由这些输入及网格上限有界，不能把512解释为所有中间量的位数。

使用已表示binary64坐标的精确有理数叉积、点积和重心符号。参考全部点须处于所选面的内半空间，焦点最低支持点须严格在外侧，且至少一个最低支持顶点的正交垂足位于该原始有限三角闭域。边和顶点上的见证可合法；面外一个ULP也不会被目标公差抹平。距离下界因此有原始表面上的可达见证。

令该单位法线为n、当前间隙g、归一化方向d，理论纯平移满足g(t)=g+t(n·d)。充分非平行时求t=(目标-g)/(n·d)，再按限幅裁剪。近平行阈值为abs(n·d)<1e-8；目标0在本阶段明确unsupported，另留专门接触合同。

理论值不代替候选验证。函数对返回平移生成虚拟binary64顶点与pivot，重新检查精确凸性／半空间／垂足和支持顶点集合，并用原严格几何内核分别核对当前与候选距离。一致性容差由局部几何ULP推导，硬上限1e-10米，独立于用户目标公差和巨大的世界原点。每个虚拟顶点的浮点位移也受硬预算限制；舍入超限最多8轮保守收缩，无法改善则停止。

`candidate_clearance_m`和`actual_max_vertex_translation_m`描述虚拟候选的浮点几何，不是Blender真实提交或回读。候选端特征切换、垂足越界、无法数值认证或严格内核未知均不会返回可用候选。goal_satisfied表示输入局部几何已在调用者公差内，零候选；不认证完整用户任务。

## 结果与限制

- `current_certificate`／`candidate_certificate`：所选原始面、最低支持顶点集合、见证、精确重心权重及浮点间隙。对外见证点是有理几何的浮点展示，不声称其坐标没有舍入。
- `current_strict_geometry`／`candidate_strict_geometry`：既有严格内核结果，不能与独立物理真值混同。
- `directional_derivative`、`predicted_plane_clearance_m`：理论线性模型；实际候选间隙另列。
- `feature_signature`：绑定参考完整几何和面索引、焦点拓扑和最低支持顶点、方向。它不绑定焦点形状、对象实例或外部编辑，不能充当跨步执行门。
- `candidate`仅在通过上述检查且虚拟残差确有减少时给出。invalid request仍抛ValueError；超出几何支持域为unsupported，资源／严格内核未知为unknown，数值无进展为precision_floor，特征改变为feature_changed。

所有结果的execution_authority、whole_scene_collision_certified、swept_path_certified及task_success_certified恒为false。第三个障碍、宿主精度／实例／版本和连续路径不由局部距离证书解决。任意多轴旋转后的近共面折面可能因实际浮点坐标并非严格凸而被拒绝；本阶段不通过放宽谓词来提高支持率。

后续才把此候选接入现有有界执行段：保留旧双箱路径、MCP/Hook请求合同、全场fresh门、版本核对、精度门、每步累计预算、真实回读和幂等账本。真实倾斜零件的动作测试必须在这一层实现并验收后进行，本轮封存快照回放不能计为实际运动成功。
