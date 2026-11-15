# M2 目录资源复用源码及资格复核

基线为 `8f2a739e789b777358d84a168154bc7c50b929e5`。本复核仅读取源码和已归档记录，没有执行产品、Blender、模型或 raster。

## 当前判定

源码存在明确的重复工作机会。真实宿主归档中也找到 1 个技术例子。符合本批自然任务准入的例子为 0，建议按本批计划收口 `not_actionable`。完整任务收益仍为 `unknown`。

真实技术例子来自 `m4_active_observation_host_bridge_001/external_archive/run/acceptance_02`。实际 `nonplanar_source` 完整捕获已传出实例 277 的 resource29，含 4 个顶点和 2 个三角形。之后 `old_readonly_regression` 明确发送 `query.mode=directory`，实际目录 `cache_hit=false`，同驻留模块、instance、epoch、revision。HARNESS_PROTOCOL 已将该请求登记为兼容回归，运行器只断言成功与纯文本。归档没有证明业务任务需要该目录，因此技术例子不能转为自然需求。

目录入口的私有 stamp 和当前 pose 没有直接序列化。资源连续性由原始 delta、相邻请求、固定静态刚性来源、相同代际及源码失效逻辑支持。额外 1 次 to_mesh、4 个顶点 world forward 是确定分支的源码推断，归档没有这些操作的独立运行计数和可删除耗时。

## 源码流程

`blender_host.capture_directory` 取得当前依赖图、对象和 residency 后，先查目录 selection cache。命中则返回已缓存目录。未命中对每个对象重新 `to_mesh`、读取局部点、计算世界点并求紧界。目录只缓存自身 packet，不创建 mesh resource 或 delta baseline。

`_resident_capture` 已保留局部点、面、边、stamp、世界 mesh 和 `pose=(evaluated matrix, scale)`。兼容复用需要当前运行对象身份对应的资源仍在、stamp 匹配、当前 evaluated matrix/scale 匹配且世界点已物化。`resident_resources>0` 无法证明指定对象符合这些条件。

场景上下文变化及 undo/redo/load 会清空资源。普通 signature/serial 变化主要清除 capture 与 nearest，仍可保留兼容资源。资源预算驱逐和八项 capture 上限也可能清除目录缓存。目录 cache miss 是可删除工作的实际条件，首次目录只是本批冻结的更窄需求域。

MCP 接线按 project root 的 sys.modules slot 和源码 tag 复用 `_mcp_resident_host`。新建 connector 仍可能接回同宿主。owned typed worker 则在分发循环前创建单一 host。PID、名称或 public scene revision 单独不能代替这些关系。

## 旧记录的判别

旧 M2 `measurement/sample.py` 的 old lane 发送 `overview`，其 `directory_facts` 来自 `routing.context_text`。只有实际 `mode=directory`、对应 host command 和 `human-eye-directory-v1/scene_directory` 回包才能证明紧目录调用。

旧 typed_01 原始结果顺序为 directory、directory、task、directory、full。后续目录实际 `cache_hit=true`，已有缓存已消除这项工作。fake-host 控制证明紧界、失效和接口接线，也能证明源码路径可达，但不代表自然任务需求或实机收益。

根补充盘点覆盖 11 个 namespace 的 2221 个 JSON/JSONL 文件，显式目录请求与结果均未发现，tools/list catalogue 出现 66 次。文件数及 occurrence 不是独立任务数。该盘点没有搜索二进制、SCRIPT.py 和任意 execute_code 字符串，因此结论限定在显式 JSON 证据范围。

## 资格与误判边界

- 自然命中需要原任务确实需要先前捕获和后续紧目录，完整请求与输入可绑定，同宿主资源连续且兼容，实际目录 miss，完整业务窗口可恢复。
- 实际 `cache_hit=true` 可判已有缓存覆盖。明确的兼容性回归可判本批自然任务条件不满足，同时保留技术重复事实。
- 缺原始 arguments、宿主连续性、对象资源绑定、stamp/pose 支持或完整成本时保留 unknown。正数资源计数、decoder baseline、相同目录摘要均不够。
- scene residency revision 改变时资源仍可能兼容。不能把 revision 相等变成产品的额外复用限制。
- 首次之外的目录 miss 可能仍有机会，本批按原计划单列范围，避免扩大实验。
- 后续若授权实现，必须保留原 loops/polygons 三角上界、有限期限与预算。prepared_local 缺原计数时走原路径。world 顶点复用仍需一次紧界 min/max，不能宣称零遍历。

精确源码锚点、证据 SHA、直接观察、源码推断和缺失证据均列于同名 JSON。当前只建议关闭本批资格，下一模块由根另行派发。
