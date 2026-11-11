# Hook 方案独立复核

日期：2026-11-11。对象：`D:/下载/CODEX_HOOK_OPTIMIZATION_PLAN.md`。本轮只读检查源码、已封存试验、当前 Hook 注册与官方协议；仅运行 `codex --version` 元数据命令，没有运行 Blender、模型消费、API 或 Hook 业务调用，没有改产品、配置、AGENTS 或实施工作树。

## 结论

采纳“先取得足够的场景发现事实，再按需精测，减少模型补查轮次”的方向。**不采纳把 Hook 改造当成当前九格试验慢的根因，也不直接照抄 Fast Scout 配置。** 当前最有价值的工作是补齐同一批量观察 API 的发现与解释覆盖；Hook 是该 API 后续可选的提前交付入口，不应再复制一套采集、候选排序、版本和缓存体系。

报告提出的 55%–70% 时间收益、30% token 收益、25 ms 总 Hook、3 ms Blender 采集、2 ms 参数修复，全部是待测假设。当前材料不能把这些数字写成已实现收益。

## 证据基线

- 根目录 `D:/hefe`：HEAD `ec20790fdf9a99d9f4ad0f3906906a94d8a6052d`，130 源产品分支。
- 实施工作树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`：固定提交 `06d1b4b4cadd880884a0a3c0927a3095ea761f30`，对应候选产品 `e077fce38b5951efff8166b3b688d05ffa2ebf04`，137 源摘要 `53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732`。
- 根与实施树的 `human_eye_hook.py`、`task_intent.py`、`live_hooks.py`、`agent_setup.py` 四文件 SHA256 全部相同。当前 Hook 架构结论可跨这两份固定源码核对；产品总文件数及新只读服务行为不可混用。
- 本机 CLI：`C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe --version` 返回 `codex-cli 0.152.1`。版本号本身不证明某项 Hook 协议已在本机成功执行。
- 固定九格：实施树 `verification/m4_local_relation_consumption_001/cells/lrc01..lrc09/CONSUMER.json`。逐格读取 `argv`，**9/9 含 `features.hooks=false`**；还关闭项目文档输入，原始目录/工具序列不受本机 AGENTS/Hook 指引影响。
- 作者日志及已有根复核记录：N/P0/P1 各 3/3 正确；中位时间 48.3034 / 48.9575 / 47.4155 秒；总 token 143762 / 172454 / 172370。P0/P1 各格仍为 3 次工具调用。此次没有重新执行这些消费或独立重新评分，不能把读取日志写成新一轮性能实测。

## 五个“串联堵点”逐项判定

| 原报告判断 | 当前源码/证据 | 复核处理 |
|---|---|---|
| 状态问题漏判，模型多花 15–25 秒 | `task_intent.py:32` 操作词包含“有没有/是不是/是否”，但不含所有疑问表达；`146–157` 状态几何词也缺项，漏判确实可能发生。`human_eye_hook.py:199–202,323–329` 未命中会走轻路径。 | 采纳补分类；“多花 15–25 秒”未测。漏判路径不会同时进入后面的重型导入和全捕获，不能称五项串联累加。 |
| 每个提示词完整导入、130 文件哈希、343 次路径核验 | 命中空间意图才加载重型入口；非空间提示已有标准库轻路径。根130源、当前候选137源。`agent_setup.py:172` 与实际注册仍使用 Windows PowerShell 包装。 | 采纳测量和简化命中路径启动成本；固定 450–800 ms 等数字不能迁移成当前版本承诺，更不能解释 Hook 关闭的九格。 |
| 全捕获后才能发现没有明确目标对 | 实施树 `live_service.py:1087–1104` 确实先 `capture_scene` 再 `resolve_prompt_pair`；Hook 调用此旧观察入口。 | 是可优化结构缺口。但当前 task 路径 `1056–1060,1345–1359` 已直接选中对象采集，不能说所有新读取仍全场采集。也不能把有限语法描述成所有非指向性题“100% 必然失败”。 |
| Overview 缺少发现事实，导致原生补查 | `_overview` `999–1007` 主要输出名称/标识/bbox，缺少任务要用的材质、内部开口、形状解释。九格消费补查确实读取此类事实。 | 采纳“交付不足”的方向。缺口不只是邻接图，更不是已证明模型不信任精确关系；P1 局部证据已被采用，仍需补目录和解释。 |
| PreToolUse 不拦读参数错误、原生几何脚本 | 当前注册确实仅匹配两个写工具。最新九格没有把参数拒单列成现行根因；历史 COMPLEX_005 与当前批量接口、消费轨迹不同。 | 不列为当前 P0。先用更简单的公开 API 降低出错机会。增加读 Hook 校验是第二份验证逻辑，也有额外进程/模型轮次成本。 |

## Fast Scout 中必须修正的数学与来源语义

### 1. `bound_box × matrix_world` 不是一般几何的 tight 世界 AABB

局部包围盒八角点变换后的 AABB 包住变换后几何，但一般比世界顶点极值更松。无需 Blender 即可构造反例：底面顶点 `(0,0),(1,0),(0,1)` 的三角柱绕 Z 转 45°。真实世界 Y 范围为 `[0,√2/2]`，变换局部矩形角点会额外包含本来没有的 `(1,1)`，得到 `[0,√2]`。用后者计算的“中心”也不同。

因此可称 `conservative_world_bounds`，可以用于下界筛选；不能标为 exact vertex AABB，也不能用它直接回答“按真实世界包围盒中心满足位置条件的对象是谁”。更不能混用 `obj.bound_box`（原对象）和 `evaluated.matrix_world`；变形修改器、shape key、动画可能改变求值几何，矩阵不携带这些变化。

当前已有 `blender_host.py:1128` 的 `capture_nearest_candidates` 明确把 API bounds 定位为采集选择工具；`1214–1239` 使用 **evaluated** bounds 和真实三角形见证构造可达上界。可复用这套思想，不能把其静态三角网格前提静默删掉后仍宣称相同结果。

### 2. AABB 最小下界的 TopK 不等于真实最近对象

`distance(AABB_A,AABB_B) <= distance(surface_A,surface_B)` 成立的前提是两个 bounds 覆盖所声明的几何，且数值计算没有把下界向上误报。它只能用于排序探索和排除，不能靠 TopK 本身证明最近。

例如许多空心框的 AABB 包住目标，均有下界 0，真实表面却很远；一个真实最近实体在外侧，下界为 0.1。固定 K 个零下界框会把真正最近实体漏掉。正确的剪枝依据是 `candidate_lower_bound > 已取得有效表面点对的距离上界`，并按所承诺的并列规则处理等号；“另一个候选的较小下界”不能充当这个上界。

原报告 86 行示例把 N16/N28 写成 AABB 下界 0.023 m。九格固定响应显示两者三轴 AABB 均重叠，下界是 0；0.023000000044703484 m 是精测表面距离。不能把该答案提前写进廉价 scout，或据此宣称 scout 已解释通孔。

### 3. 可见范围、实例与完整性的定义不能被省略

原报告仅遍历“当前视图层可见 Mesh”。当前完整捕获 `blender_host.py:675–690` 包含隐藏 mesh，检查不支持几何与实例；选中读取有自己的明确范围。可见目录可以是合理产品功能，但不等于“完整场景目录”，不能据此禁止所有原生补查。

目录至少说明 scene/document/frame、view-layer/visible/all-scene 范围、对象数量和遗漏原因。实例需要实例身份和实例世界变换；Geometry Nodes、curve、modifier 等不能只从原始 mesh 计数就宣称完成覆盖。包围盒与面数都不变的内部编辑也能改变碰撞/通孔；廉价 scout 代际不能冒充完整几何 revision。

### 4. 输出和复杂度预算不相容

200 个对象各含名称、身份、中心、尺寸，再加全部重叠对，不可能普遍装进 400–900 token。密集图最坏有 n(n-1)/2 个重叠对；“NumPy 计算全部两两关系”还与“无 NumPy 冷导入”目标矛盾。

正确顺序是任务作用域→候选空间索引→需要的事实/摘要，完整证据另存引用。缺少明确目标时先交付可用于识别目标的批量事实，而不是默认输出全场所有关系。节点数、候选数、截断标识、模型实际输入 token 应独立计量。

## 方案补丁和配置不能原样执行

1. **分类修改不完整。** “这里面有没有穿模或者悬空的物体？”已有 `operation=true`，原失败点是 weak_object 分支里的 `geometry=false`。仅改为 `(operation or spatial_state_query) and (physical or weak_object and geometry or scene_query)` 仍失败。应一次修清意图条件，回归实际状态问句、否定、引用和代码讨论，不把扩充词表写成“绝不误触发”。
2. **示例 ID 用错。** `task_query.py:18–19` 的 `solid_relation/surface_clearance/nearest_witness` 是现有合法字段，不能说这些字段不存在。但 `bind_objects:181–198` 明确 ID 不回退名称，`{"id":"N16"}` 无法绑定当前九格中的 `name=N16, object_id=blender:<hash>`。应使用真实 ID 或 `{"name":"N16"}`。若 scout 创造短 ID，则必须实现快照内映射，而不是仅改 JSON 标签。
3. **示例走回旧双对象 strict 路径。** 该三字段由 `task_query.py:556–589` 的旧有符号 clearance 测量导出，不等同当前批量 `closed_solid_relation` 与 `surface_proximity`。当前 `human_eye_spatial_relations(target,candidates,include_aabb)` 支持一个目标、1..3 候选；方案所谓“所有目标对一个批次”超出此契约。不能仅写推荐调用文本就获得任意批量能力。
4. **参数选项不存在。** 当前 `human_eye_hook.py:307–313` 没有 `--mode fast_scout`。复制示例 command 只会 argparse 失败，不会启用快路径。
5. **扩 matcher 仍会拒绝读调用。** `_parse_event:278–279` 对声明为 PreToolUse 的事件只接受写白名单；还须同步调整分派，不是新增 matcher 即可。
6. **当前无 observe PostHook 可删。** 实际 `D:/hefe/.codex/hooks.json` 和 `agent_setup.py:256–268` 均只有 transform、clearance_segment 的 Pre/Post matcher。源码保留 `duplicate_delivery_omitted` 兼容分支不代表生产注册了 observe。原报告所称每次只读省约300 ms，在当前配置下收益为零。
7. **deny 不等于零轮次修正。** Hook 提前返回模板能省服务工作，却仍将失败交回模型，让模型重新构造调用；不能把 2 ms Hook 计算时间当作消除一轮 LLM 推理。正则看到 bmesh、loop_triangles、两个 for 也不能证明低效/错误：它可能是必要的材质/内部形状补查。不要加“0-ULP、<20 ms 对所有表面”的无范围广告。
8. **短 AGENTS 也计入上下文。** 限制模型“不得原生补查”会把能力不足隐藏成行为遵从；对照试验应分别衡量充分信息和完成规则的贡献，不把不同初始信息量造成的收益算作几何算法收益。

## 官方协议与本机能力边界

读取了 [OpenAI 官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks)（原入口 `https://developers.openai.com/codex/hooks` 重定向至此）。当前文档提供 `commandWindows`、PreToolUse `allow + updatedInput`，以及复用已连接 MCP 的 `type:mcp_tool` handler；deny 会阻止本次调用，自动改参需另外的输出契约。这些说明允许设计更薄入口，但不能证明本机命令引号、MCP handler 和改参已验收。本机仅确认 CLI 0.152.1 与现有 PowerShell 注册；以上三项业务行为、直接启动 12 ms 等性能全部未测。文档也明确 Hook 定义更新有宿主信任流程，不能把改配置等同成功加载。[同一官方协议](https://learn.chatgpt.com/docs/hooks)

若后续确需前置交付，应先在隔离配置做无模型成本的本机协议探针。优先检查现有 MCP 连接能否直接调用已实现目录接口，再考虑单独命名管道 daemon；不要仅因为 `router_server.py` 存在，就宣称完整 Hook stdin/stdout、取消、代际与连接生命周期协议已可复用。若仍需 command，先验证空格路径、Unicode、stdin/stdout、退出码及加载身份，再实测去 PowerShell 的冷/热成本。

## 给统一推进计划的建议

顺序建议：

1. 完成当前已获授权的批量观察覆盖实验，固定 API 能提供的目录、目标识别、材质/开口解释与关系证据；以能否省掉原生补查为因变量。
2. 把 scene discovery、粗筛、精测整合为共享读服务。明确保守边界与真实顶点事实各自使用位置，按需选择；MCP 和 Hook 共用结果与缓存，不发展两套算法。
3. 在接口本身可完成任务后，独立比较“模型主动调用”与“相同结果 Hook 提前注入”。只改变交付时机，计入预采集、注入 token、失败/闲置预读、用户提示到最终答案时间；不能只从模型首条工具以后开始计时。
4. 只有确认 Hook 启动占比值得投入，才做一个启动优化候选；禁止同时更换意图、目录算法、消息模板、daemon、AGENTS 后无法归因。主线不是不断调正则强迫模型相信插件，而是交付足够、准确、直接可用的信息。

本轮状态：源码/固定日志/当前注册复核完成；数学反例为独立推导；官方协议已检索打开；Blender 业务、Hook 真触发、模型对照、延迟数字全部未运行。没有把作者既有通过项记成此次独立执行通过。
