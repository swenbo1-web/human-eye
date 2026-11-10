# COMPLEX-005 真实目录公平性复核

只读检查 H=`9.7.2+20261103.scene.trace.r1`、C=`9.7.2+20261110.scale.opt.r1` 的已安装源码与受控入口；没有启动 serve/Blender、导入执行产品、改目录或给消费者提示。N 继续使用共同的普通 `execute_blender_code`。

建议最小名单：

| 路线 | 消费者可见工具 |
| --- | --- |
| N | 共同原字节 `execute_blender_code` |
| H | 共同 native + **H 自己的** `human_eye_scene_observe`、`human_eye_connection_status` |
| C | 共同 native + **C 自己的** `human_eye_scene_observe`、`human_eye_connection_status` |

`connection_status` 保留真实只读状态发现能力，避免因共同试验包装而裁掉旧版原有读取。两个插件的名称可以相同，但 description、inputSchema 以及各子字段必须从各自真实 tools/list 原样转发。公平条件是相同任务、规则、资源和可用原生能力，不是强行让 H/C schema 相同。目录字节差异是版本差异的一部分，计入004现有目录/调用成本账本。

## H 实际具备什么

H 的固定入口 `admin/target_runtime_entry.py:206–209` 调用 `production_server`；其 `production_server.py:92–116` 在普通模式创建 live service 并进入 LiveSpatialMCPServer。`live_spatial_mcp.py:116–187` 列出四个默认工具：scene_observe、transform、connection_status、clearance_segment；`646–647` 返回这一真实目录，`581–613` 是对应分派。

- 观察工具原有模式是 `overview / exact_pairs / nearest / top1 / mesh_structure / mesh_surface`（`live_spatial_mcp.py:56–82`）。保留整个 schema：ID选择、task_instruction、object_ids、max_exact_pairs、support_plane_discovery、scene_delta、full/brief 等不能再裁掉。调用可自然使用概览返回的ID继续读取。
- 旧版没有 `task` 或 `surface_nearest`，也没有 C 的 target/candidates/requested_facts 名称选择参数。`query_policy.py:39–64` 的实际验证与此一致。
- `nearest/top1` 针对已支持、精确、非穿入的 clearance 排序；`query_policy.py:138–175` 会保留未解决候选，穿入深度未认证也可能使排序未知。这不是 D48“所有网格的全局无符号表面最近”的同义接口。旧版能给什么由原接口实际结果决定，不能把未知改成分离或完整最近。
- 两题所需的普通空间观察都由 scene_observe 返回。本次沿真实生产目录/分派检查，未发现必须额外开放的独立 report/evidence 检索工具。`full` 明确是一次新观察而非历史观察检索（`live_spatial_mcp.py:192–198`）。

H 仓库安装内另有模块，但不应把它们误当默认 live 目录：`llm_tool_schemas.py` 的六个旧工具属于 `production_server.py:31–54` 显式 `--demo` 合成演示，不能连到本题当真实读取；`surface_owned_mcp.py:13–21,131–140` 的 owned_reference_inspect 针对固定单网格参考偏差场景，不是此两题通用报告；`owned_task_mcp.py:31` 的额外只读集合仍只是 scene_observe/status。没有理由为本轮另开这些场景/执行器。

## C 的真实增量与排除项

C 普通目录保留旧模式并新增 `task`、`surface_nearest`（`live_spatial_mcp.py:57–102`），已有文字说明与条件 schema 应原样暴露。装配 task 支持目标加最多三个候选的实体关系和表面距离；surface_nearest 针对全场表面最近，原说明要求 session_id、include_image=false，并使用一个 query.objects selector 或 focal_id（`138–173`）。这些是版本原有能力，不给 H 回填，也不替 C 修正文案或补路由。

C 的 `human_eye_spatial_relations` 是独立 `--spatial-task-only` 模式（`production_server.py:101–122`、`live_spatial_mcp.py:269–285,779–786,859–860`），普通 serve 目录不会同时列出它。本轮延续普通实际入口，因此不额外拼入该任务专用入口。C 普通目录新增的 arm_twist_observe 处理手臂骨骼局部，并不读取装配关系或全场最近；按两题相关性排除。两组 transform、clearance_segment 及 owned goal 的写/动作工具也不属于本轮只读答题名单。clearance_segment 即使支持 execute=false，仍是目标间隙动作求解/历史动作回执接口，不是遗漏的原始证据读取接口。

## 预检验收点

1. 各自固定 entry、私有 config/state、同轮依赖解释器启动普通 serve，分别核 initialize 的源摘要、源数量与安装 pin；H=a045a800…b60d8f/125，C=3fc2651e…0193bd/137。原始 tools/list 整份保留，再按上述只读名单过滤；被保留的单工具 JSON 对象与原目录精确相等，H/C 不要求相等。
2. 用当轮各自输出的目录实际发普通只读请求，验证 current fixture 和 default session 连接；状态工具只返回该格真实服务状态，不泄漏其他格。观察调用不硬塞 C mode 给 H，不在桥里改 include_image、补 session、改参数或重写错误。管理员预检案例只留管理证据，不能成为额外消费者指引。
3. 复用004同一 native、题目、session rules、450/570秒、32次、1MiB、30秒及0图预算。若 status 被调用，同样计 attempt、wall、TX/RX；目录、握手、内部RPC单列，错误与原生回退留在原分母。
4. 不把 H 的 unsupported/unknown 当工具包装故障，也不把 C 有新能力等同于模型一定正确调用。实际输出和最终答题照原质量标准评分；本轮衡量的是两代真实安装的整体效果，不是单一4行优化消融。

本结论是静态目录/代码复核，实际握手、动态 schema 与场景来源由实施者无模型预检验证。无需重做004的生命周期、隔离和计量架构。

Reviewed UTC: 2026-11-10T11:49:58.193789+00:00
