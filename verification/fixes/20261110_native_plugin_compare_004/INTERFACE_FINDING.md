# COMPLEX-004 共同观察接口：可发现性核查

独立只读核查，2026-11-10，复核者 `/root/scale_opt_design_review`。

**结论：全局 `surface_nearest` 能力已在共同工具目录中明确公开，不能归因为引擎藏在未介绍的模式里。接口的实际问题是把多种模式、新旧事实名和条件参数放在一个工具定义中，需要使用者正确组合。`nearest_witness` 确实是公开枚举中的合法事实名，但仅适用于其中一条旧双对象路径；把它用于新的 target/candidates 集合路径会被拒绝。**

这构成下一轮接口简化的候选解释，不证明模型内部为什么选错或为什么回退。没有读取 cells、RUN_RESULT、匿名答案、组别映射、调用成本或最终收益；也没有运行模型、Blender、产品查询或修改目录。父复核提供的“若干答案提到参数错误并回退原生”只用于确定核查问题，不视为已核实的具体调用轨迹。

## 范围与同版依据

读取共同目录 [O_schemas.stdout.json](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/native_plugin_complex_004/O_schemas.stdout.json:1)，文件 SHA256 为 `5b1eb33b5796d202473eecd8900a0a2114ce9929cbd7ac073e7fc8144ecb9130`。该文件为一行 JSON，因此以下结构定位同时给出 JSON 路径。

以 `git show` 只读比较固定 `d01d49bc0ec82583b24a8faf22e622e6f6ea8c5d` 与 `df016079b0265ee327f884c90dd4815c392016b6`：`live_spatial_mcp.py`、`query_policy.py`、`task_query.py`、`live_service.py`、`blender_mcp_host.py` 五个文件逐字节相同，当前工作副本也与固定字节相同。因此下面的接口与分派判断同时适用于两个固定版本，不是此次四行算术优化带来的接口变化。

## 目录实际上展示了什么

目录位置：`tools_list.result.tools[name="human_eye_scene_observe"]`。

| 项目 | 目录及源码的实际内容 | 判断 |
| --- | --- | --- |
| 全局最近表面模式 | 主 description 明说 `Global surface_nearest`，使用一个 `query.objects` selector；另一形式是顶层 focal_id 加 `query={"mode":"surface_nearest"}`；要求 session_id 和 include_image=false。 | 已介绍，不是隐藏模式。 |
| 模式枚举 | query.mode 明列 task、surface_nearest、overview、exact_pairs、nearest、top1、mesh_structure、mesh_surface。 | 新旧多种检索模式同时可见。 |
| 全局模式参数 | query 条件分支只允许 mode 和至多一个 objects selector；工具顶层条件要求 session_id、include_image=false，并禁止同时使用 focal_id 与 query.objects。 | 有机器可读的参数组合要求。 |
| 显式集合查询 | candidates 的描述和 maxItems 都写明 1..3；必须请求 closed_solid_relation 与 surface_proximity，aabb 可选。 | 三候选上限是该查询形式的真实限制。 |
| 全局事实枚举 | requested_facts 上层列出九种事实，包括 nearest_witness。 | 该名称不是模型凭空发明。 |
| 集合专用事实枚举 | target/candidates 分支把枚举进一步限制为 closed_solid_relation、surface_proximity、aabb，并强制前两种出现。 | nearest_witness 不能放入这一分支。 |

对应行证据：

- [live_spatial_mcp.py:139](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:139)：主工具描述；第 141 行是完整 task-set 例子，第 143–145 行介绍全局模式、参数与 complete/partial。
- [live_spatial_mcp.py:59](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:59)：query 的介绍先解释旧 exact_pairs/nearest/top1；第 61 行列八种模式。
- [live_spatial_mcp.py:62](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:62)：objects 的文字描述只讲 Legacy task；第 65–69 行给 candidates 上限及事实描述。
- [live_spatial_mcp.py:91](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:91)：surface_nearest 仅 mode/objects；第 95–100 行是 task 两分支及集合事实白名单。
- [live_spatial_mcp.py:160](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:160)：全局模式的顶层必需字段与选择器互斥条件。

## 请求错误与实际能力必须分开

| 请求形式 | 固定实现的行为 | 不能据此推断的结论 |
| --- | --- | --- |
| task + target/candidates 超过 3 个候选 | 在查询校验时拒绝。 | 不能推断插件无法搜索 47 个候选。 |
| task + target/candidates + nearest_witness | 不在集合事实白名单，拒绝整个请求。 | 不能推断插件没有最近见证点能力。 |
| task + objects 恰好两个对象 + nearest_witness | 参数形式合法，进入旧 strict pair 几何路径；结果仍可能因几何能力/证据不足返回 unknown。 | 不能仅凭这个事实名判定“参数错了”。 |
| surface_nearest + requested_facts/target/candidates | 不符合该模式仅 mode/objects 的参数合同。 | 不能推断 surface_nearest 未实现或未公开。 |
| surface_nearest + 一个合法目标 selector + 必需顶层参数 | 分派至当前场景的候选采集和全局表面排序路径。 | 不保证任意资产都会 complete；真实来源、数值、预算与未解决候选仍决定状态。 |

严格区分以上情况需要实际请求 JSON 与原始错误回执。本报告未读这些记录，不给匿名答案中的每次回退作具体归类。

实现依据：

- [task_query.py:18](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:18)：FACTS 含 nearest_witness，SET_FACTS 只有三个集合事实。
- [task_query.py:57](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:57)：集合查询 1..3 candidates 校验及错误字符串；第 73–76 行限制集合事实。第 78–89 行的另一分支允许完整 FACTS，但 pair facts 要求恰好两个 selectors。
- [task_query.py:543](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:543)：旧 nearest_witness 调用 measure_pair_geometry；第 575–576 行形成对应事实，不是新集合/全局表面查询的额外开关。
- [task_query.py:157](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:157)：surface_proximity 的结果本身已包含 distance_m 和 nearest_witness（两点及方向），并保留见证/方向状态。无需再往集合 requested_facts 添加同名旧事实。
- [query_policy.py:48](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/query_policy.py:48)：全局模式纯参数校验只接受 mode 或 mode+单个 objects selector；第 55–57 行才是另一个 task 分支。
- [live_spatial_mcp.py:356](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_spatial_mcp.py:356)：全局模式必须提供 session_id、目标与 include_image=false；同时拒绝 reference、goal、scene_delta。第 388–391 行另行限制 task 的顶层字段。
- [live_service.py:1046](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_service.py:1046)：两个模式分别分派，第 1055 行调用 `_observe_surface_nearest`，第 1060 行调用 `_observe_task`。
- [live_service.py:1296](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/live_service.py:1296)：按目标调用 capture_nearest_candidates，而非要求调用者枚举三个候选；第 1321 行计算全局结果。
- [task_query.py:420](C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/human_eye_plugin/task_query.py:420)：要求 complete_scene_meshes 目录绑定；第 436–449 行验证严格下界排除，第 464–475 行精算保留候选并排序，第 487–495 行给 complete/partial、最近对象与覆盖计数。

## 目录可用，但存在可以简化的组合负担

从共同目录提取**单个 human_eye_scene_observe 工具对象**（包含 name、description、完整 inputSchema，而非整个 tools/list、运行身份或 source_files），使用 `json.dumps(tool, separators=(',', ':'), ensure_ascii=False).encode('utf-8')`，无末尾换行，得到 **10,442 字节**。这只是明确编码下的工具定义大小，不是实测模型 token，不证明宿主最终向模型传递的表示有同样字节数。

基于目录和源码，可提出三个具体的接口候选问题：

1. 一个工具容纳八种模式。query 的公共文字以旧 nearest/top1 开头，而全局表面模式的解释在主描述另一处；objects 的字段说明也只写 Legacy task。使用者必须跨几处合并规则。
2. 上层 requested_facts 确实列出 nearest_witness，嵌套 target/candidates 分支又排除它；新 surface_proximity 输出内恰好也使用 nearest_witness 这个字段名。语法是有定义的，但同名项在请求枚举和输出内容中的角色不同。
3. task-set 有完整可复制的 JSON 例子，surface_nearest 只有文字和一个省略顶层参数的片段。错误提示会指出集合上限或必需事实，但不会在同一错误中给出全局查询的正确替代形式。

这些是**基于接口结构的候选解释**。本轮未做目录消融或同题修正请求对照，因此不能断言它们已经导致某个模型的内部选择，更不能由此解释尚未揭盲的时间收益。

供后续接口设计讨论的正确全局调用形状如下，仅作源码合同说明，本轮没有执行或发送给消费者：

```json
{
  "session_id": "current-scene",
  "include_image": false,
  "query": {
    "mode": "surface_nearest",
    "objects": [{"name": "Target"}]
  }
}
```

下一步若选择接口优化，可只处理“把任务意图直接对应到有效请求组合”：补这个完整例子，明确集合上限不等于全场景检索上限，并让旧 pair facts 与新集合 facts 的适用分支直接可见。不要把本轮结果倒推成模型“不信任工具”或“已知道正确入口却拒绝使用”；当前证据支持的是接口公开但组合复杂，具体行为因果仍待核对。本轮产品、目录、评分和消费者样本均保持不变。
