# 支撑平面有界执行段

2026-10-28 当前聊天重载验收：已实际载入 v19／9.7.2+20261028.support.discovery.r1（a0198acc…／installed_distribution／68 文件），状态健康、目标账本 0，旧配置快照拒绝已解除。当前 MCP 完整发现唯一支撑面，实测间隙仍为 3.1304261516453477 毫米；回填完整 selector 的 1 毫米目标预览只返回单步限幅候选，未移动。人为改错客户端 revision 的预览被拒绝并要求重新观察；没有实际编辑宿主来制造这条负例。独立 Fraction 真值、768×768 原生 PNG 和全 14 Scene 不变均已核对。

真实用户三维回复已在模型该轮工具调用前触发 v19 UserPromptSubmit，自动交付完整几何文字；五组定义保留。本轮还核对了 clearance_segment 预览的 PreToolUse／PostToolUse 去重，不能当作 execute:true 的动作链或 transform 各事件已通过。自动原生图片仍未证明，Hook 为 text_only。先前独立安装私有场景的 12 次移动是另一阶段证据，本聊天本轮零移动。

只读安装 SDK 边界矩阵 12 组／28 次调用／277 项检查通过；凹体、开放 reference、穿透／接触和有限面外一 ULP 明确 unsupported，几何／有理复杂度和过长 revision 返回 unknown，不放宽门。真实多候选截断未覆盖。下一单点候选先检查审计日志大字节／少行时重复整写和轮转，再考虑纯距离观察的对齐按需；两项均未实现，成本对照仍 pending。既有 27.84%—36.71% 文本字节减少不等于端到端或模型提速。工程构建可继续有限验收，整体公开发布门仍为 false。

[当前重载阶段](../verification/fixes/20261028_v19_reload/REPORT.md)、[当前量测与预览核对](../verification/fixes/20261028_v19_reload/CURRENT_VALIDATION.json)、[真实用户文字 Hook 审查](../verification/fixes/20261028_v19_reload/REAL_USER_HOOK_REVIEW.md)、[只读边界矩阵](../verification/fixes/20261028_v19_reload/MATRIX_REVIEW.md)。接口继续见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)。

本聊天只验 execute:false 预览与失效选择绑定；目标仍未移动到 1 毫米。原面发现、候选与执行授权分别判断，实际动作链后续单独验收。

以下保留此前阶段记录，尤其 v19_activation 的待重启状态仅表示当时阶段；当前状态以上文和本轮重载报告为准。

2026-10-28 最新状态：v19 工程构建 9.7.2+20261028.support.discovery.r1（a0198acc…／68 文件）已离线安装并完成磁盘激活，新注册进程实际验收通过。当前聊天仍为 v16 旧配置快照，返回 stale_configuration_snapshot，需重启后核验；真实新用户 Hook 未通过本版验收。四文件迁移保留五组 Hook、Agent Learning 当前配置与状态，state 仅改配置绑定；磁盘激活不等于宿主信任或当前聊天重载。

显式 query.support_plane_discovery 已实现当前对象对的精简发现，完整 selector 可回填有界执行段。四模板文本字节中位减少 27.8448%—36.7095%，本地服务仍增加约 1.8—8.0 毫秒，不宣称模型或端到端提速；默认 PNG 保持。接口与边界见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)，[新注册入口结果](../verification/fixes/20261028_v19_activation/REGISTERED_ENTRY_RESULT.json)和[配置保留结果](../verification/fixes/20261028_v19_activation/activation/PRESERVATION.json)。

当前推荐从显式发现回填完整 reference_triangle_index＋selection_binding；恢复前重新发现。新 ID 的失效绑定在新账本前拒绝；同 ID 历史回执不表示当前场景重验。下方面号 2 是保留的手工接口示例，不是通用面号。

以下为此前阶段记录，保留当时版本、命令及验收边界；当前状态以上文及精简支撑面发现说明为准。

2026-10-28。v18源码候选已经通过实际Blender倾斜与斜面移动、回读和恢复，仍未安装到当前聊天。当前安装v16继续使用原箱体执行能力。详见[实机验收](../verification/fixes/20261028_support_plane_segment/REPORT.md)。

候选版同一个human_eye_clearance_segment入口新增显式约束分支，工具数与钩子数量保持：

```json
{
  "session_id": "caller-session",
  "request_id": "unique-reviewed-goal",
  "execute": false,
  "include_image": false,
  "request": {
    "solver": "support_plane",
    "focal_id": "current-focal-full-id",
    "reference_id": "current-reference-full-id",
    "reference_triangle_index": 2,
    "direction_world": [0, 0, 1],
    "target_clearance_m": 0.001,
    "clearance_tolerance_m": 0.0000005,
    "max_steps": 8,
    "max_step_translation_m": 0.005,
    "max_total_translation_m": 0.04,
    "max_duration_s": 20
  }
}
```

示例ID和面索引须由当前快照替换，2不是通用上表面。新分支没有axis；旧分支继续省略solver并使用明确的axis。execute默认为false；预览不保留回执、不移动，局部候选也不赋予执行资格。

执行时每步复用[支撑面数学合同](SUPPORT_PLANE_CANDIDATE.md)，并保留完整场景fresh检查、宿主编辑／身份／精度、提交版本、回读、累计实际位移、步数与时间预算、停滞／振荡停止和不明提交隔离。没有连续路径或运行中即时取消认证。支撑面目标签名不能代替形状、实例或外部编辑检查。

首次规划在创建running记录前完成，非法面索引／缺失对象不留下未完成账本，规划耗尽时间也不开始执行。方向原有限向量转float后持久化，仅求解时归一化，保证账本反复载入不会因归一化舍入改变参数指纹。同ID同参数是历史回执，当前场景不会因此重新核验或移动；同ID异参数拒绝。提交不明不自动重试。

v18能读旧箱体回执，旧v16不能解析新增support_plane回执。未来生产升级写入新域后，回退须尊重账本兼容边界，不能删除新回执以让旧版加载。当前测试账本隔离保存，未复制到生产。

当前仍需调用者选择原始面。scene_delta={}可取得绑定当前revision/fingerprint的完整网格以确定索引，但传输成本较高。后续优先提供少量可靠支撑面选择、歧义与失效说明；本轮不声称自然指令已经可以自动选面，也不扩展至任意凹体或旋转闭环。
