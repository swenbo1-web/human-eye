# TASK-SCOPE-IMPL-001

本地离线候选已完成，待根独立深审；未部署。产品提交 `8b065e21d97e0fae84f26cf8b88b2adcbee3cb2d`，起点为干净 `70c5a19dad5cfcee110646bd9bafcf6b2315216a`。131 源摘要 `70a57e7f655f647b12287ccb73eb0b56c66cfe4bbd2b56fc6908d0ea73e1b7b3`；131 个 Git blob 与工作树源字节一致。仅改 task_query.py、live_spatial_mcp.py，以及 live_service.py 一处 task trace 兼容判断。未改 host、loader、transport、几何算法、域、精度或预算。

现有 observe/task 增加以下公开分支；旧 objects pair 和多对象 aabb 保持原契约：

```json
{"include_image":false,"query":{"mode":"task","target":{"name":"A"},"candidates":[{"name":"B"},{"name":"C"}],"requested_facts":["closed_solid_relation","surface_proximity","aabb"]}}
```

候选限 1–3，两核心事实必需，aabb 可选。内部 canonical 形状使用 `scope=explicit_target_candidates` 和完整 objects；严格区分公开形状与 canonical，JSON 往返再校验幂等，单候选仍是集合。服务沿原路径一次捕获、一次验证、一次完整绑定，不切片/伪造二对象 capture。每 pair 使用独立 holder/diagnostics 和原 helper；聚合原顶层计算计数，避免最后一次命中覆盖此前计算。rank 使用既有独立 cache key，旧非 rank 缓存不冒充命中。

返回逐请求候选行和一份完整 binding，目标/候选顺序取自 binding。缺件、同名歧义、别名重复、自配对保留明确行；重复候选行均 unknown，互不相关的合法 pair 继续计算。完整穿插集合只依赖全部关系确定；最近分离集合还需全部已证分离件的合法距离和精确 rank。保留已知集合、未决原因及最佳已知项；全已知且无分离件时 complete=true、ids=[]。穿插的正表面距离不成为分离间隙；有效距离、未知见证点/方向分字段保留。有部分测量时 partial/isError=false，全无测量时 unknown/isError=true；发布仍经过原 deadline 检查。私有 rank key/网格不进入公共响应。

| 内存 selected host 的直接对照（各自冷缓存） | 旧三次 pair | 新一次 set |
| --- | ---: | ---: |
| observe/capture/validate/bind | 3/3/3/3 | 1/1/1/1 |
| MeshEntity 构造 | 6 | 4 |
| closed/surface 内核计算 | 3/3 | 3/3 |
| 完整 JSON-RPC 编码 B | 5552 | 4923 |

三候选新请求另核定 helper 入口 closed=3、surface=3、rank=1。全绑定、host instance、trace_id 与当前 fingerprint 保留。上述唯一几何构造承诺限支持 selected capture 的 host；通用 fallback 仍走原完整捕获，未声称只展开四件。冷内核计算并未减少。

同一 cache、三个唯一合法有序 pair、结果可缓存且未逐出、rank 参数和完整 mesh 元数据不变时，实测冷态 6 计算；未变 6 命中/0 计算；只改一候选几何且另两对 key 不变时 4 命中/2 计算；改目标 0 命中/6 计算。每次仍重新捕获/绑定。改名、ID/mark 变化、淘汰、unknown 等不作普遍命中承诺；相应边界已测。原装配离线初态/未变/变化态也记录了 6/0/6 计算。

原装配三态重放的新 set 完整 wire 分别为 6129/6129/6126 B；等价必要事实的旧三个 pair 合计 6872/6872/6860 B。工具目录完整 JSON-RPC 编码从 19625 增至 21241 B（+1616）。这些包含 JSON-RPC envelope、嵌套文本转义及换行，不是内层 JSON/源码字符数或 token。原题关系、独立距离区间、全部穿插件和最近分离件均通过；零距离见证点允许非唯一，并独立核验在原三角面上及点间距离误差 ≤1e-9 m。未新增 64KiB 拒绝层；合法长名称案例实际完整 wire 为 152719 B，未截断。

最后源码修改后已固定上述产品提交：综合回归 88 项通过，再补直接旧/新计数测试 1 项通过，共覆盖 89 个当前方法（18 新、71 旧）；另有 12 项已安装 Test-Json 的公开 schema 检查通过。覆盖旧 task/selected-capture/MCP、既有孔洞/无顶点入内交叉/微小间隙反例、原三态几何、单/三候选、别名/缺件/歧义、unknown、无分离件、精确并列、两项显示值均 1.0 而真实平方距离分别为 1+2^-60/1+2^-58 的闭壳实例、rank 缺失/隔离、缓存/淘汰、engine_invoked 汇总和到期发布拒绝。当前方法均通过后停止扩大回归。

完整历史分母是 201 次 unittest 方法执行：199 通过、2 失败；未抹除历史失败。首个失败错误要求两条零距离路径返回逐坐标相同的非唯一见证点，改为事实等价和独立表面核验。第二个失败是计数测试把前一 service 的旧审计行也合计，限定当前调用对应行后通过。两份失败测试源码与日志保留；这些修正未改变内核/门槛。目录原文本写入多一 CR 的副本保留为 catalogue_response.textio.json；改为直接写原编码字节后仅重检该例，正式 catalogue_response.json 与记录的生产编码 B 数一致。初始 62 项旧回归还包含一次既有 CLI `serve --help` 子进程，打印帮助后退出，未启动服务/监听器；这是预期外的子进程检查，已如实分列，最终回归明确排除。没有 Blender/Native owned session、真实 MCP 服务/host RPC、模型消费者、网络/API/key 调用或性能试验；所有协议/host 结果均是进程内或 fake-RNA 模拟，不能称真实入口验收。

机器计数、逐态值、源摘要、测试分母和保护原件核验在 RESULTS.json；各轮 unittest 日志、最终用例参数、公开 schema 与 Test-Json 结果同目录。正常导入本工作树源码及现有测试环境；没有新 runner、manifest/ZIP/封存平台或子代理。原装配、旧失败证据及上一批报告/索引与起点 Git 字节相等；默认配置/GUI/竞争分支未写入。此批未测 Native 补查、端到端模型交付、token/费用或净收益，未自动第四轮消费。

任务书 SHA `33dd2a52e2acb066247effc0a04c45700cc40f9bbbfd2d42302f7ad5eb0be46a`；根设计复核 SHA `7773e1af374a45d9a166927ba07a9a9660d70c4c576f46bceffab11313bf9bad`，优先于设计原稿中的 64KiB 建议。完整 app turn 从 2026-11-08 20:28:12Z（上海 11月9日04:28:12）计，35 分钟截止 21:03:12Z。RESULTS 记录阶段累计 1,062,478ms；最终回执另报包括报告/证据提交在内的完整累计，不拿数秒测试时间替代工程成本。完成回执后结束，等根深审。
