# 精简支撑面发现与执行入口

2026-10-28 当前聊天重载验收：已实际载入 v19／9.7.2+20261028.support.discovery.r1（a0198acc…／installed_distribution／68 文件），状态健康、目标账本 0，旧配置快照拒绝已解除。当前 MCP 完整发现唯一支撑面，实测间隙仍为 3.1304261516453477 毫米；回填完整 selector 的 1 毫米目标预览只返回单步限幅候选，未移动。人为改错客户端 revision 的预览被拒绝并要求重新观察；没有实际编辑宿主来制造这条负例。独立 Fraction 真值、768×768 原生 PNG 和全 14 Scene 不变均已核对。

真实用户三维回复已在模型该轮工具调用前触发 v19 UserPromptSubmit，自动交付完整几何文字；五组定义保留。本轮还核对了 clearance_segment 预览的 PreToolUse／PostToolUse 去重，不能当作 execute:true 的动作链或 transform 各事件已通过。自动原生图片仍未证明，Hook 为 text_only。先前独立安装私有场景的 12 次移动是另一阶段证据，本聊天本轮零移动。

只读安装 SDK 边界矩阵 12 组／28 次调用／277 项检查通过；凹体、开放 reference、穿透／接触和有限面外一 ULP 明确 unsupported，几何／有理复杂度和过长 revision 返回 unknown，不放宽门。真实多候选截断未覆盖。下一单点候选先检查审计日志大字节／少行时重复整写和轮转，再考虑纯距离观察的对齐按需；两项均未实现，成本对照仍 pending。既有 27.84%—36.71% 文本字节减少不等于端到端或模型提速。工程构建可继续有限验收，整体公开发布门仍为 false。

[当前重载阶段](../verification/fixes/20261028_v19_reload/REPORT.md)、[当前量测与预览核对](../verification/fixes/20261028_v19_reload/CURRENT_VALIDATION.json)、[真实用户文字 Hook 审查](../verification/fixes/20261028_v19_reload/REAL_USER_HOOK_REVIEW.md)、[只读边界矩阵](../verification/fixes/20261028_v19_reload/MATRIX_REVIEW.md)。接口继续见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)。

[注册进程结果](../verification/fixes/20261028_v19_activation/REGISTERED_ENTRY_RESULT.json)、[配置与状态保留](../verification/fixes/20261028_v19_activation/activation/PRESERVATION.json)、[激活时旧聊天拒绝（历史）](../verification/fixes/20261028_v19_activation/CURRENT_CHAT_AFTER.json)、[独立安装入口审查](../verification/fixes/20261028_v19_activation/INDEPENDENT_ENTRY_REVIEW.md)。

## 作用与流程

明确 focal/reference 对象对后，调用者可显式请求少量当前支撑面选择器，无需先传完整网格给模型或手算三角面索引。流程是 fresh 捕获 → 精确支撑面发现 → 回填完整 selector → 预览／有界执行段 → 每步重新门检、提交和读回。引擎负责已授权目标内的局部纠偏；调用者仍明确给出对象对、移动方向、目标和预算。

算法只接受既有闭合凸体和原始有限三角面的受支持情形。两网格只准备一次精确有理表示，参考原面按精确有向平面分组，每组保留确有有限三角垂足见证的最小原面索引，并与严格几何距离核对。不以拟合面或凸包替换原几何，不扩展为任意凹体、多壁语义或连续路径认证。

## 显式查询

通过现有 human_eye_scene_observe 工具调用，不增加工具或 Hook 数量：

~~~json
{
  "session_id": "caller-session",
  "focal_id": "current-focal-full-id",
  "reference_id": "current-reference-full-id",
  "include_image": false,
  "response_detail": "brief",
  "query": {
    "alignment_evidence": false,
    "support_plane_discovery": {
      "direction_world": [0, 0, 1],
      "max_candidates": 4
    }
  }
}
~~~

support_plane_discovery 是可选对象，只接受 direction_world 和 max_candidates。上限必须是整数 1—6，默认 4；布尔值不作为整数。方向可省略，省略时只做几何发现，不推断动作方向；提供时须为三个有限数字且范数有限非零。方向用于判定支撑面是否适合所给移动方向，不代表已批准动作。

默认查询不增加发现计算，默认原生 PNG 行为保持；include_image:false 才显式关闭图片。省略 scene_delta 可避免传完整网格；确实需要完整几何时仍可另行显式请求，但不是使用 selector 的前置要求。

结果位于 support_plane_discovery。检查 status、measurement_valid、enumeration_complete、all_candidates_returned、ambiguous、候选数量和 reason_codes。没有候选、截断、歧义、资源不足或 unknown 时，不猜一个“上表面”。局部可用 selector 也不覆盖全场 unknown 或执行门的拒绝。

## 完整 selector 与失效规则

每个候选的 selector 保持完整直接可读：

~~~json
{
  "reference_triangle_index": 2,
  "selection_binding": {
    "scene_revision": "current-captured-revision",
    "scene_fingerprint": "current-64-lowercase-hex-digest",
    "focal_id": "current-focal-full-id",
    "reference_id": "current-reference-full-id"
  }
}
~~~

2 仅展示返回值形状，不是通用面号。应直接回填所选候选的完整 selector；不要只复制面索引、丢掉绑定或手写绑定值。绑定覆盖当前完整场景 revision/fingerprint 和对象对，不是授权、人类意图证明或跨重建的语义面身份。

以下 Python 只构造请求；observed_metadata 代表刚收到的当前工具 metadata：

~~~python
discovery = observed_metadata["support_plane_discovery"]
assert discovery["status"] == "complete"
assert discovery["all_candidates_returned"] and not discovery["ambiguous"]
assert len(discovery["candidates"]) == 1
selector = discovery["candidates"][0]["selector"]

segment_arguments = {
    "session_id": "caller-session",
    "request_id": "unique-reviewed-goal",
    "execute": False,
    "include_image": False,
    "request": {
        "solver": "support_plane",
        "focal_id": discovery["focal_id"],
        "reference_id": discovery["reference_id"],
        **selector,
        "direction_world": [0, 0, 1],
        "target_clearance_m": 0.001,
        "clearance_tolerance_m": 0.0000005,
        "max_steps": 8,
        "max_step_translation_m": 0.005,
        "max_total_translation_m": 0.04,
        "max_duration_s": 20.0,
    },
}
~~~

调用现有 human_eye_clearance_segment 预览；目标、方向和预算经调用者确认后，再按同一意图执行。多候选时需要明确选择依据，不能把返回顺序当作意图。

新请求 ID 在首次 fresh 捕获后、规划和创建新账本前核对绑定；场景改变时返回 support_plane_selection_stale_revision 等明确拒绝，executed:false、requires_reobserve:true，不预留新执行回执。执行段自身的受控移动不反复要求最初 revision，但每步的全场、宿主实例、精度、提交版本和读回门保持。恢复目标须先重新发现当前 selector。

相同请求 ID、相同参数优先返回历史回执，即使当前场景已变化；这是防止重复执行的幂等性。检查 replayed:true、historical_receipt:true 和 current_scene_revalidated:false，不能把历史成功当作当前目标仍满足的证据。同 ID、不同参数拒绝；不明提交不自动重试。旧手工原面索引和世界轴箱体请求继续兼容；使用发现结果时应保留完整绑定。执行合同见 [SUPPORT_PLANE_SEGMENTS.md](SUPPORT_PLANE_SEGMENTS.md)。

## 文本编码与实测收益

显式发现响应可按声明对完全相同的主要事实使用同工具引用；客户端须遵守 support_plane_value_encoding 等编码声明。JSON Pointer 以本次工具 metadata 为根，不能跨响应、指入 JSON 字符串或把 context_text 内引用误当作字符串内部路径。null、unknown、完整对象 ID 和 selector 不被删除；保留字、未知编码或矛盾副本不自动修补。普通默认 MCP 响应不因此切换编码。

四个固定快照模板，比较 A：scene_delta:{} 全网格、B：精简发现，均为无图 brief。96 个正式本地 MCP 请求另加 16 个预热，使用复制快照的 synthetic fresh host；不是实时 Blender 网络或模型计时。

| 模板 | A 文本字节中位 | B 文本字节中位 | 减少 | 纯发现 P50/P95 毫秒 | B−A 服务中位差毫秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 平行箱体 | 25538 | 18427 | 27.8448% | 4.6096 / 4.7782 | +4.2497 |
| 1°倾斜 | 29764 | 20729 | 30.3555% | 4.37965 / 4.5074 | +2.3421 |
| 16 边棱柱近似 | 31782 | 20115 | 36.7095% | 16.1468 / 16.5391 | +8.0184 |
| 封闭楔形 | 29252 | 20166 | 31.0611% | 4.3232 / 4.5843 | +1.7825 |

收益是这些模板的文本字节减少，本地服务仍增加约 1.8—8.0 毫秒。字节不等于 token、账单或模型整任务耗时；B 不发送全部网格，也不能重建 A 的完整几何。主要事实引用展开一致，不代表 A/B 所有信息完全等价。详见[正式收益](../verification/fixes/20261028_support_plane_discovery/BENCHMARK_RESULT.json)和[独立收益审查](../verification/fixes/20261028_support_plane_discovery/INDEPENDENT_GAIN_REVIEW.md)。

## 已验证范围与后续顺序

源码完整回归 2476 项：2475 通过、0 失败、0 错误、1 项既有 Windows 符号链接权限跳过。独立安装定向回归 237 项全通过；两套有重叠，不累计为额外覆盖数。

实际安装 production stdio 在自有 12_TiltAction／13_SlopeAction 各完成到 1 毫米和恢复，各 6 次、共 12 次 verified 移动。完整 INITIAL/FINAL 快照精确一致，全 14 Scene 的 LAB_BEFORE/AFTER 逐字节一致，原主场景 1° 倾斜保留。两个私有账本各 2 条 satisfied 回执，没有复制到生产。两张实际原生 PNG 已核对。独立 Fraction 真值以捕获网格为基础，不是独立实物计量。

上一激活阶段只改四个受审文件，保留五组 Hook、Agent Learning 当前配置与状态，state 只改配置绑定。本轮包含 discovery 缓存的同一份最新完整 state（SHA256 e55bd335aa8898581d83638ecc1a6e823aca84b830e387e226ee1683e407ffff）已分别通过新 v19 与旧 v16 的实际 runtime.import_state 和显式 ledger 校验，生产目标账本为 0；没有导出、回退 apply 或宿主操作。此结果不保证未来 support-plane 目标回执或其它新状态仍兼容。每次回退仍须针对同一份最新完整状态验证旧 runtime 和 ledger，保留 journal／回执，不得删缓存、清账本或复制旧 state 制造兼容。

当前重载与真实文字消息入口已通过上述范围；下一步成本核对 pending，之后单独验当前聊天 execute:true 动作链、更多资产和同题多 Agent 收益。现有封存包 D:/hefe/dist/human_eye_engine_9_7_2_v19_support_discovery.zip 保持不变（SHA256 21aa1ea9a1848f45791ae384fb2184b0c89c33d3641dd52e1d1b2837a2713004）；这次文档更新没有重打包或云上传。

## 历史激活时点

2026-10-28。工程构建 9.7.2+20261028.support.discovery.r1（v19，68 个运行文件，build sha256:a0198accd9e5b5449122ebb8999275a6d9e88081e0309df63c28f7a0a1a6f9e5）已离线安装并完成磁盘配置激活；新注册进程已实际返回该身份。当前聊天仍持有 v16 配置快照，返回 stale_configuration_snapshot，需要重启后重验；真实新用户 Hook 尚未通过本版验收。这是有限范围工程构建，整体公开发布门仍未通过。

此状态已由上述重载验收推进；[原激活报告](../verification/fixes/20261028_v19_activation/REPORT.md)保持封存，源码和安装阶段证据不与当前聊天实际入口混同。
