# 显式最近对象查询

2026-10-28 当前聊天重载验收：已实际载入 v19／9.7.2+20261028.support.discovery.r1（a0198acc…／installed_distribution／68 文件），状态健康、目标账本 0，旧配置快照拒绝已解除。当前 MCP 完整发现唯一支撑面，实测间隙仍为 3.1304261516453477 毫米；回填完整 selector 的 1 毫米目标预览只返回单步限幅候选，未移动。人为改错客户端 revision 的预览被拒绝并要求重新观察；没有实际编辑宿主来制造这条负例。独立 Fraction 真值、768×768 原生 PNG 和全 14 Scene 不变均已核对。

真实用户三维回复已在模型该轮工具调用前触发 v19 UserPromptSubmit，自动交付完整几何文字；五组定义保留。本轮还核对了 clearance_segment 预览的 PreToolUse／PostToolUse 去重，不能当作 execute:true 的动作链或 transform 各事件已通过。自动原生图片仍未证明，Hook 为 text_only。先前独立安装私有场景的 12 次移动是另一阶段证据，本聊天本轮零移动。

只读安装 SDK 边界矩阵 12 组／28 次调用／277 项检查通过；凹体、开放 reference、穿透／接触和有限面外一 ULP 明确 unsupported，几何／有理复杂度和过长 revision 返回 unknown，不放宽门。真实多候选截断未覆盖。下一单点候选先检查审计日志大字节／少行时重复整写和轮转，再考虑纯距离观察的对齐按需；两项均未实现，成本对照仍 pending。既有 27.84%—36.71% 文本字节减少不等于端到端或模型提速。工程构建可继续有限验收，整体公开发布门仍为 false。

[当前重载阶段](../verification/fixes/20261028_v19_reload/REPORT.md)、[当前量测与预览核对](../verification/fixes/20261028_v19_reload/CURRENT_VALIDATION.json)、[真实用户文字 Hook 审查](../verification/fixes/20261028_v19_reload/REAL_USER_HOOK_REVIEW.md)、[只读边界矩阵](../verification/fixes/20261028_v19_reload/MATRIX_REVIEW.md)。接口继续见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)。

本轮当前 MCP 验收聚焦支撑面发现和预览，并未重跑全部 top1 对照；既有 top1 合同和此前证据保持，不把源测试或别的接口重载泛化为本轮 top1 新效果证明。

以下保留此前阶段记录，尤其 v19_activation 的待重启状态仅表示当时阶段；当前状态以上文和本轮重载报告为准。

2026-10-28 最新状态：v19 工程构建 9.7.2+20261028.support.discovery.r1（a0198acc…／68 文件）已离线安装并完成磁盘激活，新注册进程实际验收通过。当前聊天仍为 v16 旧配置快照，返回 stale_configuration_snapshot，需重启后核验；真实新用户 Hook 未通过本版验收。四文件迁移保留五组 Hook、Agent Learning 当前配置与状态，state 仅改配置绑定；磁盘激活不等于宿主信任或当前聊天重载。

显式 query.support_plane_discovery 已实现当前对象对的精简发现，完整 selector 可回填有界执行段。四模板文本字节中位减少 27.8448%—36.7095%，本地服务仍增加约 1.8—8.0 毫秒，不宣称模型或端到端提速；默认 PNG 保持。接口与边界见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)，[新注册入口结果](../verification/fixes/20261028_v19_activation/REGISTERED_ENTRY_RESULT.json)和[配置保留结果](../verification/fixes/20261028_v19_activation/activation/PRESERVATION.json)。

既有 top1 合同保留；本轮未改变其精度、完整候选证明和 unknown 边界。下方 v16 当前聊天通过属于历史，v19 当前聊天需重启后另验。

以下为此前阶段记录，保留当时版本、命令及验收边界；当前状态以上文及精简支撑面发现说明为准。

2026-10-28。稳定安装与当前聊天均已核验为 `9.7.2+20261028.query.evidence.r1`（v16／e06beb38…／66文件），旧配置快照错误已消失。当前MCP的top1、无图可选对齐及原生PNG通过；真实三维用户消息也已在模型首次回复／工具调用前触发自动文字量测：BluePart／GreyBase当前最小间隙3.130426毫米，fresh捕获、未移动，已有1°倾斜保留。泛化“继续”按规则跳过。五组钩子定义与Agent Learning配置保留；不据此推断其余动作钩子和各类Agent已全部验收。见[重载与非双箱实测](../verification/fixes/20261028_v16_reload/REPORT.md)；安装迁移历史见[前轮](../verification/fixes/20261028_v16_activation/REPORT.md)。

下列源码阶段的版本状态保留为历史；新参数现已在安装版和当前聊天实际MCP通过，下述接口合同继续适用。

2026-10-28。v15源码候选已验证，尚未安装。当前稳定安装v14仍只支持overview、exact_pairs和nearest。下例用于候选SDK／后续验收过的安装，不应直接发送给当前v14工具。

```json
{
  "mode": "top1",
  "object_ids": ["current_full_id_1", "current_full_id_2"],
  "max_exact_pairs": 2
}
```

对象ID必须来自当前场景；示例是占位符。省略object_ids时查询已捕获的全部非焦点对象；显式列表只证明该集合。显示／控制reference始终先测，占一个精算槽；它不在请求集合内时不参与最近对象选择。此选项不自动切换默认路由、不增加标签预算、不改变reference或移动物体。

引擎按向外扩展AABB的可靠距离下界排序，保留当前最优非穿透精确距离。只有受支持对象的下界严格超过保守比较上包络，才省去其精确计算。上包络使用场景尺度的数值guard与向上ULP，作用仅是减少剪枝；平局依据相同未舍入引擎值，不用guard吞并相近值。精算数量与累计几何work都受原预算约束。

`query_result.top1` 返回：

- `status`：complete或unknown。
- `nearest_object_ids`：完整最近集合；unknown时为null，不把当前候选冒充最终最近。
- `unique`与`signed_clearance_m`：仅完成证明时提供，单位米。
- `excluded_by_lower_bound_ids`：被严格下界排除的对象，仍保留lower_bound事实。
- `comparison_guard_m`与`pruning_threshold_m`：本次比较包络；不改变测量值或碰撞阈值。
- `tie_scope`：相同未舍入引擎距离，不证明物理等价；`execution_authority`恒为false。

top1的`ranked_object_ids`始终为null，因为它不证明请求集合的完整排序。原nearest完整排序合同保持。`exact_pair_count`与`measured_pair_count`仍统计实际结果，不能把剪枝对象算成精算。full、brief和Hook结构事实保留该回执；同一次有图MCP交付保持原生PNG，文字Hook仍不承诺图片自动注入。

任何仍可能更近的未知／unsupported、穿透、资源或预算未决对象会使最近集合为unknown；无对象对时明确query_pair_required。全场其他unknown和风险仍在contacts／scene_assessment中，即使请求子集已经完成。该查询不认证运动路径，不减少动作前后全场fresh检查。

固定无图本地对照：24候选精算24→1，P50约下降72%；无可剪枝的密集12候选P50增加4.63%，4格原成本门通过。此为有限工程收益，不代表真实Blender／模型整任务提速。详细证据见[候选验收](../verification/fixes/20261028_top1_query/REPORT.md)。
