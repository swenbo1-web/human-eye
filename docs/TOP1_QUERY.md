# 显式最近对象查询

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
