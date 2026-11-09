# ARCH-READ-CONTEXT-001 初版

产品提交 `0414a9af8e74fe29df2e420fedb53700be94aaec`，分支 `codex/architecture-read-context`，从已审产品 `bd1c2e4ed3be550cde8e096a9970ebc5e592463d` 创建。旧 `codex/nearest-integration` 与历史证据保留。本批仅改live_service.py、task_query.py、scene_cache.py，新增63行read_context.py；没有修改host/MCP/process/worker、正式配置或原资产。

task与surface_nearest现在使用服务进程内的一个ReadContext：RLock、独立SceneCache、规范化scene/MeshEntity、最多16个当前版本query结果。它们不再调用动作_locked，不新建GuardedHostRuntime，不读动作账本、不import/export动作状态、不做全状态JSON比较或_save。纯读不再清除旧prepared/pending/committed/quarantine；动作路径仍自行加载、检查与管理账本。已有动作回归通过，真实prepared及opaque/corrupt动作文件在纯读前后字节不变。

每次仍调用既有capture接口，从本次capture取四字段capture_state；不读host.last_token。入口、有序selector、instance/epoch/revision/selection_key共同限定规范化缓存，完整query限定结果缓存。nearest的令牌在packet.capture。缺令牌/字段类型不符的旧host逐次新鲜规范化，仍用原内容memo；没有额外NeedInfo循环。令牌本身不进入普通答文。

同版本同query直接返回隔离的结果副本；partial/unknown和精确并列不提升置信度，不按显示float重新排名。新facts问题复用规范化和已有测量，只补缺失精算。SceneCache由上下文把私有MeshEntity引用绑定当前capture版本，热查询不再to_dict/重编码整个网格；旧调用者仍用原exact-content键。初版按整版本/选择变化失效，尚未分离每资源/姿态版本。

readonly源检查在服务初始化时执行一次，载入source/host/mode代际变化才刷新；暖读取不再逐次完整读盘/hash。代际变化会重建只读测量cache。动作的旧identity检查保持。nearest冷/新query仍保留既有packet协议、来源、目录、严格排除和实例绑定资格检查；暖复用依赖M2明确承诺的当前不可变令牌覆盖整个capture语义，不再对同令牌整包重验。

只读审查发现并在初版提交前修复两处边界：代际变化不能沿用旧数值memo；冷结果也必须detach，避免调用方经binding.host_identity修改常驻规范化scene。新反例验证这两点。结果缓存不保留请求trace，外层每次仍绑定当前trace；原编码与发布预算继续生效。保留既有轻量audit/trace写入，没有新增审计平台或预算计时平台，不能把本批说成所有磁盘IO均为零。

| 已执行验证 | 最终产品结果 |
| --- | --- |
| 常驻task、版本四维/选择/query、补缺失事实、legacy、返回隔离、production暖源检查、动作账本隔离 | 12/12 |
| 常驻nearest、并列/精确次序/partial/unknown、旧host、selector/packet拒绝、代际与冷别名/网格编码反例 | 9/9 |
| 既有SceneCache、普通服务动作、task数值/禁图/期限及nearest独立oracle/目录资格 | 50/50 |

最终71个不同方法通过。完整历史101次执行＝100通过＋1失败：首次task12通过；nearest首轮9中8通过1失败，修fixture后9通过；最终task12、相关回归50、最终nearest9均通过。原失败log和FAILED_NEAREST_TEST.py.txt保留。失败由旧fixture预期把退化面当unknown引起，当前v3数值核已支持该退化输入；改用真实surface_exact_bit_budget场景测试partial/unknown，没有为测试改几何核或支持域。没有隐藏或覆盖首次失败。

实际少做的工作由禁用重复路径的断言确认：同令牌暖task/nearest仍取1次逻辑当前capture，但normalize、MeshEntity重建、精算和动作ledger读写均0；暖task还跳过task_result，暖nearest跳过完整summarizer。完整三候选冷task有1次规范化、4实体、3对closed/surface helper；增加AABB问题不重规范化/精算/全网格编码；只增closed fact时只补1次closed求解。没有用单测运行秒数作为延迟收益或宣称physical capture/传输已在本线减少；后者由M2负责。

本线仅离线fixture与fake host，无Blender、实际host RPC、模型或Google/API。一个子Agent编写/执行新task测试，一个只读Agent审代码；产品改动由本线实施者完成。PLAN和更新STATE已核；STATE实际位于原20261106_parallel_coordination目录，本次architecture_completion目录只有PLAN。

下一实缺是合并M2同版，验证实际capture令牌在编辑/重连/场景切换/名称/单位/帧变化时更新，并贯通真实入口冷/暖/改变路径；随后根深审后做一次有依据的实质优化。现在还没有资源/姿态分离失效，也未接OwnedGoalScheduler/M5本地反馈，不能称已完成小脑或整体架构。源码身份及全部日志SHA在RESULTS.json。初版回报后结束等根深审，不等待或自行占用M2独占Blender窗口。
