# M2-DIRECTORY-RESOURCE-REUSE-001 资格收口

## 结论

本批判定为 `not_actionable`。所查既有轨迹中，符合冻结自然任务条件的命中为 0。源码复用机会成立，并保留一条真实宿主的技术重复例子。该例来自预登记的兼容性回归，目录事实没有后续业务消费依据，完整任务净收益仍为 unknown。

本轮完成了是否值得实施的资格核查。产品候选、追加热点优化和正式六槽比较的执行数均为 0。后续主线由管理员结合统一 M1–M5 路线派发。

## 固定起点与工作区

计划 SHA256 为 `19c991d42ac17d0b8e38cfe7286c2c4c28fc4dd554c2e25c29fd52cc41d2cf21`，统一路线 SHA256 为 `df788375fc84ecd5f2008c0f28d4882bdbfff2f8f8f3eeb7ed7825c094a67641`。本批从接受的提交 `8f2a739e789b777358d84a168154bc7c50b929e5` 分支，141 源摘要为 `3748d88b618db7de1347d632f2a68f3ed82a2ebb8a6321586fe756be07ea8148`。

分支为 `codex/m2-directory-resource-reuse-001`，证据写在 `verification/m2_directory_resource_reuse_001/`。原定长工作区名在 Windows checkout 时触发 Filename too long，工具清理失败目录后，使用同一基线创建短名 `m2-dir-001` 成功。原失败回执保留。

## 既有 M2 真实宿主轨迹

| 范围 | 核查数量与结果 |
|---|---|
| 真实任务宿主 | 42 个，包含 36 正式测量、3 预检、2 MCP 功能与 1 typed worker |
| 业务读取 | 368 条，另有 1 条 typed shutdown |
| 显式产品目录 | 139 条，其中 98 缓存命中、41 未命中 |
| 新目录测量宿主 | 12 个，首次业务均为目录，此前资源数均为 0 |
| 资源后目录候选 | 3 个，均已命中原目录缓存 |
| 人工变更后的目录 | 26 条，旧资源 stamp/pose 缺失，兼容性保留 unknown |

两次 `directory_after_full` 的实际顺序均为冷目录、暖目录、selected task、full overview、再次目录。末次 `cache_hit=true`。typed 序列为冷目录、热目录、task、再次目录、full，其 task 后目录与热目录原文件逐字节相同。

测量中的 321 条业务记录逐条绑定实际 WORKER_EVENTS、原始 WIRE 与代码 SHA。含清理的宿主事件和 WIRE 请求各 360 条。旧 lane 实际走 overview，原生 lane 是独立目录脚本，新 lane 才调用产品紧目录。相应代码、回包 schema 和模式分别核对。

旧 M2 4702 文件、83146547 字节在审查前后逐项一致。42 个宿主均为有限脚本工程会话，资产重复情况保留。它们提供工程轨迹分母，自然任务命中仍为 0。

## M4 真实宿主技术例子

有界盘点覆盖 47 个既有 M4 namespace、12 份外部归档索引。按明确实际宿主计算，主动观察有 4 条 owned 会话、24 条 stdio RPC，含 13 次成功主动观察、1 次错误主动查询、1 次目录。旧 capture QA/opt 另有 22 条 owned 会话、44 份真实采集脚本，目录调用为 0。合计 26 条有限工程宿主会话，资产存在重复。

唯一技术例来自 `m4_active_observation_host_bridge_001` 的 acceptance_02。成功 nonplanar_source 捕获之后，依次经过坏查询、ping、old_readonly_regression 目录。目录回包为 `human-eye-directory-v1/scene_directory`、`cache_hit=false`，前后同一驻留模块、host instance、epoch=1、revision=3、对象实例277。捕获中该 mesh 的 revision 为29、含4顶点2三角面；29是版本编号，驻留资源总数未测。

单位、矩阵、局部及世界点有原始记录，目录紧界与前一世界捕获一致。目录入口私有资源 stamp 与 resource.pose 没有直接侧录，兼容性由相邻请求、同一未变场景、只读守卫及源码支持。nonplanar 观察的 unknown 状态同时保留。

历史整体产品 SHA 为 `b12db7282381df800fbd0d44d2f921e332a6b85c2fb3ac77aba51b5cc462b278`，宿主文件 SHA 为 `9a63545aec488cead3be508f97afefc9fa7135beb82e85cff10ca7ad4d3b59e9`，后者与当前基线同名源码一致。当前 3748 整体版本的新增实测为 0。

原 HARNESS_PROTOCOL 的 fixed_requests 登记了该兼容回归，运行器第222至225行仅断言成功与纯文本交付。日志缺少目录随后参与业务结果的证据。因此技术重复例记为 1，自然任务资格记为 0。

成功目录 miss 分支会对该对象执行一次 to_mesh 和四次世界顶点变换。这个数量来自实际规模和确定源码分支。独立运行计数、可删除时延及新旧完整任务净收益未测。

## 支持性盘点与未知项

根补充检查 11 个 M1/M5/residency namespace 的 2221 个 JSON/JSONL 文件。显式 directory 模式及 scene_directory 结果出现数为 0，tools/list catalogue 出现66次。该盘点没有解析任意 execute_code Python 字符串，范围限于可识别的 JSON 证据。

M4 的 1201 份 literal TX 和300份索引映射 TX 有副本重叠。原盘点按单个 JSON 解码失败的14份文件，根补充确认均为逐行 JSON 消息，恢复79条消息、37条 tools/call，解析错误为0，显式 directory 请求与 capture_directory 文本出现均为0。补充记录保留在 FRAMED_TX_REVIEW，原复核保持原字节。文件数、消息、协议副本和 catalogue 出现数均有独立单位，真实自然调用频率仍为 unknown。CAPTURE_REPLAY 和固定 packet 消费单列在排除项中。

判定范围为本次有界旧档资格，覆盖不到的自然历史保持未知。已有目录缓存命中、明确兼容回归和私有资源快照不足分别保留原因。

## 源码分析及实施出口

当前 capture_directory 在目录缓存 miss 后会逐对象展开 evaluated mesh、读取局部顶点、变换世界点并扫描紧界。_resident_capture 已持有世界 mesh、stamp 和 pose。可复用条件需要当前对象运行身份、stamp、evaluated matrix/scale 与物化 world mesh 兼容。

后续若自然任务暴露这一需求，已有 world 顶点仍需一次 min/max 扫描。原目录预算采用 `max(0, loops-2*polygons)`，资源创建时需要保留该上界。prepared_local 等缺少原计数的来源继续属于复用 miss。上述为已核准的候选边界，当前实现与净收益证据仍待自然命中。

本批计划设置了自然命中的前置条件。现有真实技术记录已能说明代码路径可达，只读资格在有界范围内收口为 not_actionable。

## 执行、成本和保留记录

| 本轮工作 | 实际执行 |
|---|---:|
| 产品改动文件 | 0 |
| 产品候选与追加优化 | 0 / 0 |
| 新 owned Blender 启动 | 0 |
| 新产品观察与 raster | 0 / 0 |
| 实验模型消费者 | 0 |
| Google 或其他付费试验 API | 0 |
| 正式六槽 | 未运行，前置自然命中条件未达 |

核查用到 PowerShell、Git、静态 Python 和审核代理。审核及协调的模型 token、现金费用与完整人工成本未测。实验模型 token/费用为未运行，产品性能、内存和完整收益均未测。分析登记后的时段单独写入资格账本，登记前计划读取、委派与工作区创建另行披露。

保留了长文件名导致的首轮 worktree 创建失败。根的 JSON 盘点首稿遇到负例 arguments=null 抛 AttributeError，原脚本保留，修订后支持空 arguments 并单列 malformed 记录。源码审核者两次 WindowsApps Python 别名空输出也已登记，最终静态脚本使用明确 runtime。

agent-learning 前置及完成前查询均为当前聊天未绑定、host_epoch=5、rebind_required=true，任务登记保持 pending_current_chat_host_binding，任务写入数为0。

复核关联已披露。M2 轨迹审核者参与过前批 M1 定向与运行复核，M4 轨迹审核者参与过 M1 产品实现，源码资格由另一代理复核。根直接核读关键原始请求、兼容回归脚本、缓存回包和独立计数，并在最终审核中再次验证来源。

## 审核材料

本目录保留 M2_TRACE_REVIEW、M4_TRACE_REVIEW、SOURCE_ELIGIBILITY_REVIEW、CONTEXT_TRACE_INVENTORY、FRAMED_TX_REVIEW、QUALIFICATION_LEDGER、DECISION、FINAL_AUDIT 和 CONTENT_MANIFEST。最终 Git 提交及远端核验由完成回报提供。
