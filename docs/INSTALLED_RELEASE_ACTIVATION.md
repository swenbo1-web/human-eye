# 已安装版本的接入与升级

2026-10-28 当前聊天重载验收：已实际载入 v19／9.7.2+20261028.support.discovery.r1（a0198acc…／installed_distribution／68 文件），状态健康、目标账本 0，旧配置快照拒绝已解除。当前 MCP 完整发现唯一支撑面，实测间隙仍为 3.1304261516453477 毫米；回填完整 selector 的 1 毫米目标预览只返回单步限幅候选，未移动。人为改错客户端 revision 的预览被拒绝并要求重新观察；没有实际编辑宿主来制造这条负例。独立 Fraction 真值、768×768 原生 PNG 和全 14 Scene 不变均已核对。

真实用户三维回复已在模型该轮工具调用前触发 v19 UserPromptSubmit，自动交付完整几何文字；五组定义保留。本轮还核对了 clearance_segment 预览的 PreToolUse／PostToolUse 去重，不能当作 execute:true 的动作链或 transform 各事件已通过。自动原生图片仍未证明，Hook 为 text_only。先前独立安装私有场景的 12 次移动是另一阶段证据，本聊天本轮零移动。

只读安装 SDK 边界矩阵 12 组／28 次调用／277 项检查通过；凹体、开放 reference、穿透／接触和有限面外一 ULP 明确 unsupported，几何／有理复杂度和过长 revision 返回 unknown，不放宽门。真实多候选截断未覆盖。下一单点候选先检查审计日志大字节／少行时重复整写和轮转，再考虑纯距离观察的对齐按需；两项均未实现，成本对照仍 pending。既有 27.84%—36.71% 文本字节减少不等于端到端或模型提速。工程构建可继续有限验收，整体公开发布门仍为 false。

[当前重载阶段](../verification/fixes/20261028_v19_reload/REPORT.md)、[当前量测与预览核对](../verification/fixes/20261028_v19_reload/CURRENT_VALIDATION.json)、[真实用户文字 Hook 审查](../verification/fixes/20261028_v19_reload/REAL_USER_HOOK_REVIEW.md)、[只读边界矩阵](../verification/fixes/20261028_v19_reload/MATRIX_REVIEW.md)。接口继续见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)。

本次已经完成当前聊天 v19 重载，不需要因本次文档更新再次安装或重启。原 v19_activation 的 stale_configuration_snapshot 和 host_trust_review_required 是当时记录，保留在原阶段；真实本轮 Hook 的有限通过范围以上文为准。现有封存 ZIP 保持原字节，不把文档更新视为重新打包。

以下保留此前阶段记录，尤其 v19_activation 的待重启状态仅表示当时阶段；当前状态以上文和本轮重载报告为准。

2026-10-28 最新状态：v19 工程构建 9.7.2+20261028.support.discovery.r1（a0198acc…／68 文件）已离线安装并完成磁盘激活，新注册进程实际验收通过。当前聊天仍为 v16 旧配置快照，返回 stale_configuration_snapshot，需重启后核验；真实新用户 Hook 未通过本版验收。四文件迁移保留五组 Hook、Agent Learning 当前配置与状态，state 仅改配置绑定；磁盘激活不等于宿主信任或当前聊天重载。

显式 query.support_plane_discovery 已实现当前对象对的精简发现，完整 selector 可回填有界执行段。四模板文本字节中位减少 27.8448%—36.7095%，本地服务仍增加约 1.8—8.0 毫秒，不宣称模型或端到端提速；默认 PNG 保持。接口与边界见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)，[新注册入口结果](../verification/fixes/20261028_v19_activation/REGISTERED_ENTRY_RESULT.json)和[配置保留结果](../verification/fixes/20261028_v19_activation/activation/PRESERVATION.json)。

本次目标入口（用于核对新注册进程，不代替当前聊天重载）：

~~~powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -m human_eye_plugin.production_server --config 'D:/hefe/.human-eye/live-connector.routing-spatial.json'
~~~

完整 build 为 sha256:a0198accd9e5b5449122ebb8999275a6d9e88081e0309df63c28f7a0a1a6f9e5。管理 helper 为对应 release 的 admin/installed_release.py，SHA256 2641e21be8e9602012c12594e4c1b9409b8a7e5da4358c8aa18c8ff03e50b89b。受审 plan 4a0e98cc6723915a464ab97c9329cbee36cbf52449650af7bbc9f2fd1206dc76，备份 89923496e4644144a49c85b55eba7169 已 committed；APPLY.activation 仍为 host_trust_review_required。

当前生产目标账本 0，最新常规非发现缓存已由旧 v16 runtime 与 ledger 核对。反向计划只读未执行；未来发现缓存或 support-plane 回执可能超出旧版兼容域，每次回退须验证同一份最新完整状态，不能删缓存／回执或覆盖旧 state 制造兼容。计划 ZIP：D:/hefe/dist/human_eye_engine_9_7_2_v19_support_discovery.zip；本条不是已生成或上传证明。下方旧版本命令仅属历史固定示例。

以下为此前阶段记录，保留当时版本、命令及验收边界；当前状态以上文及精简支撑面发现说明为准。

2026-10-25单项消融收尾：8源码版本完成2560正式/480热身观察，部分注意力剪枝和多物体LUT有限定收益，完整组合未证明稳定加速。144诊断定位权重图/风险ROI等阶段；固定112000次helper微测否决低可见数分流。Z仅减少临时索引，但唯一480正式对没有稳定收益组，多物体持续更慢且冷观察采用47→46，已拒绝，源码仍f668、安装仍c949。末尾配置保护失败原样保留；唯一外部变更为AL启动路径1.4.25→1.4.26，已审查并保留，不重采样、不改原失败、不打包安装。实际多物体场景为23mesh（43只为合成维度），详见[本轮报告](../verification/fixes/20261025_component_ablation/REPORT.md)。

2026-10-25源码成本/遮盖候选更新：`f66816bf…` 已完成按收益触发布局与保守视角剪枝，密集Q1覆盖1368→933，8类回放没有owner遮盖增加；最终1490项（1489通过/1历史跳过）、新cohort240对和61805项独立核验通过。性能目标仍部分失败：5/10组更慢、thin持续+0.777ms、3次配对采用丢失，因此不默认推广。源码未打包/安装，当前聊天仍使用c949。见[本轮报告](../verification/fixes/20261025_cost_occlusion_repair/REPORT.md)。

2026-10-25源码候选补充：接触视线/标签优先e09cf93d…已按“实现→算法架构解析→测试”验收，新增两种1mm接触特写和总览参考标签，同时存在耗时/采用率/标注遮盖负项。候选未打包或安装，以下操作身份与当前聊天仍是c949，无需因本轮重启。见[源码候选报告](../verification/fixes/20261025_contact_view_priority/REPORT.md)。


2026-10-25当前聊天实战验收：恢复预览版 `9.7.2+20261025.recovery.preview.r1 / c949150a…` 已完成8类真实独立Blender只读场景、4→1mm受控变换、真实Pre放行/碰撞拒绝与Post、9张原生工具图交付。用户真实结构化空间回复另触发自动文字观察，约4mm、0移动，首条公开回复前收到上下文。**无需重启或重新安装。** 见[本轮实战](../verification/fixes/20261025_recovery_current_practice/REPORT.md)。

自有工厂已正常退出0，未改用户工程；当前状态无未完成操作或隔离。Human-Eye配置保持，state只由真实请求正常更新。外部Agent Learning入口1.4.22→1.4.23的单字段变更已精确核对并保留，根代理没有回写生产配置。

自动prompt交付仍为文字几何上下文，工具调用的原生图片另有本轮证据；不能据此声称首次推理前自动原生图、跨agent普适性或模型任务收益。孔槽等部分图仍依靠量测字幕，未证明可直接看见空隙。性能混合预览定位及旧负项保留。

此前重连检查见[重连报告](../verification/fixes/20261025_recovery_reconnect/REPORT.md)，注册/回退见[受锁提交](../verification/fixes/20261025_recovery_activation/REPORT.md)；这些报告中的待验/端口未在线保留其原时点记录。

管理工具为 `examples/agents/installed_release.py`，独立于引擎包部署；它不在引擎 ZIP 内，也不安装依赖、启动 Blender、调用模型或批准宿主权限。使用目标版本 venv 的 Python，以 `-I -B` 运行它，不能通过插入源码目录来代替安装版。

本说明的命令和身份对应恢复预览版，当前聊天已核验载入。后续切换其他版本才需再重连；状态握手未检查Blender在线性。

本说明固定参考以下版本，部署其他版本时应替换为该版本经过验收的路径和身份：

| 项目 | 固定值 |
| --- | --- |
| 目标安装版本 | `9.7.2+20261025.recovery.preview.r1` |
| 目标安装 build | `sha256:c949150a8c79957b80d870c5a9db0c83c4c5a92006e73f1136525867a7e512f3` |
| 独立管理工具 SHA-256 | `6eb5d309afe57f0e2c76829ab57ccb3fe9c9e0297af47d62f3b17a556e6d1674` |

## 操作前提

- 目标版本已经安装，其模块来源和身份符合预期。只在该版本的功能、安装及接入验收通过后应用计划。
- 明确现有项目和实际 connector 路径。工具不会猜测默认 connector；未传 `--config` 时，仅从对应宿主已注册、能够严格识别的 Human-Eye MCP 启动参数发现路径。
- 必须已有能够被目标版本导入的 state。state 的 schema 和旧配置指纹必须匹配；`inflight`、`runtime.quarantine` 及每个 router session 的 `pending` 必须为 `null`。已有普通观察 sessions 可以保留，无需删掉它们。
- 缺少 state 会返回 `state_initialization_required`。这个窄升级工具不创建空 runtime，也不能通过更换空 state 路径绕过旧状态。
- 配置文件输入及计划输出上限为 **8 MiB（8,388,608 字节）**；state 上限为 **32 MiB（33,554,432 字节）**。上限本身允许，超过上限拒绝；配置升级后增长超限也会在应用前拒绝。
- 配置、state、audit、锁及宿主配置不得相互重合或通过链接指向同一文件；state/audit 不得落入 `releases`、`setup-backups` 或工具保留路径。不要把安装目录作为状态写入目录。

`doctor` 和不带 `--apply` 的 `plan` 只读取文件，不创建目录、锁、audit 或新 state。它们读取的是未加锁的快照；应用时会重新加锁并校验全部前置条件。

## PowerShell 操作流程

在同一个 PowerShell 窗口中执行。以下示例沿用本项目实际 connector 文件名；其他项目应先修改路径。

```powershell
$HePython = 'D:\hefe\.human-eye\releases\9.7.2+20261025.recovery.preview.r1\.venv\Scripts\python.exe'
$HeTool = 'D:\hefe\examples\agents\installed_release.py'
$HeProject = 'D:\hefe'
$HeConfig = 'D:\hefe\.human-eye\live-connector.routing-spatial.json'
$HeBuild = 'sha256:c949150a8c79957b80d870c5a9db0c83c4c5a92006e73f1136525867a7e512f3'
$HeToolSha = '6eb5d309afe57f0e2c76829ab57ccb3fe9c9e0297af47d62f3b17a556e6d1674'

if ((Get-FileHash -LiteralPath $HeTool -Algorithm SHA256).Hash.ToLowerInvariant() -ne $HeToolSha) {
    throw '管理工具身份不符，停止操作。'
}

$HeCommon = @(
    '--agent', 'codex',
    '--project', $HeProject,
    '--config', $HeConfig,
    '--expected-build', $HeBuild
)

& $HePython -I -B $HeTool doctor @HeCommon
if ($LASTEXITCODE -ne 0) { throw '预检失败，保留输出并先处理原因。' }

$HePlanText = & $HePython -I -B $HeTool plan @HeCommon
if ($LASTEXITCODE -ne 0) { throw '生成计划失败，停止操作。' }
$HePlan = ($HePlanText -join "`n") | ConvertFrom-Json
$HePlanText
```

审阅该次输出，确认：

1. `target_runtime.identity` 的 build、revision 和 `source_kind=installed_distribution` 正确，Python 与模块路径属于目标 venv。
2. `connector_path`、state/audit 路径及待改文件属于预期项目，`changes` 不包含第三方配置清除。
3. MCP 和三个事件命令使用同一目标 Python、同一 connector；connector 的新身份 pin 与目标版本一致。
4. `state_migration` 只迁移 `config_fingerprint`，保留 runtime/journal 字节；状态健康检查已经通过。

审阅完成后，使用**刚才这份计划返回的** `plan_sha256` 应用，不能填入旧记录里的计划 hash：

```powershell
& $HePython -I -B $HeTool plan @HeCommon --apply --plan-sha256 $HePlan.plan_sha256
if ($LASTEXITCODE -ne 0) { throw '应用未完成；保留错误与备份，按恢复流程检查。' }
```

若配置或 state 在审阅后改变，工具会拒绝旧计划。先核实变化来源，再重新生成并审阅计划；不要只删除 `--plan-sha256` 重试。归档输出时使用新的文件名，保留先前失败记录。

可选的 `--current-status <已保存状态结果.json>` 接受操作者保存的状态 JSON，包括 MCP `content[text]` 形式。输出会标为 `operator_saved_file`，记录来源文件 hash，且 `live_probe_performed=false`；它不能证明当前连接仍然相同。没有该文件时，当前连接状态为 `unknown`。

## 宿主范围与三个事件

| `--agent` | MCP 配置 | Hook 配置与范围 |
| --- | --- | --- |
| `codex` | `.codex/config.toml` 的 `human_eye_live` | `.codex/hooks.json` |
| `claude` | `.mcp.json` 的 `human_eye_live` | `.claude/settings.json`；使用 Claude 事件协议及直接参数启动 |
| `mcp` 或 `genericmcp` | `.human-eye/mcp-client.json` | 仅生成 `.human-eye/installed-hooks.json` 命令清单，`registration=host_integration_required`；不代表宿主已注册或触发 hook |

三个事件为 `UserPromptSubmit`、`PreToolUse`、`PostToolUse`。注册命令固定调用 `-I -B -m human_eye_hook --event <事件名>`，事件 pin 来自可信启动参数。Pre/Post 的 matcher 限定为 `^mcp__human_eye_live__human_eye_transform$`；MCP 调用 `-I -B -m human_eye_plugin.production_server`。

generic 清单默认给出 Codex 协议模板，其他 agent 仍需实现事件格式、调用时机和结果注入的适配。配置文件存在不能证明实际宿主触发；hook 文本输出也不能证明模型已经消费 MCP 图像。

工具保留第三方 MCP、Agent Learning 等设置，以及原有 `enabled=false`、用户环境字段和 hook 超时。它只替换严格识别出的 Human-Eye 入口。未知 shell 包装、冲突 connector、重复入口或错误事件 pin 会拒绝并保留原文件；不要为通过检查而删除不明第三方命令。

## 备份、围栏与失败处理

应用持有项目 setup 锁和现有 live-service state 锁。完整备份及事务 manifest 写入新的 `.human-eye/setup-backups/<事务 ID>/` 后，依次执行：

1. 仅把 state 顶层配置指纹换成随机事务围栏指纹；runtime、journal 及其他字节保持原样。
2. 更新宿主入口、三个事件或 portable 清单，以及 connector 的代码根目录和身份 pin。
3. 再次校验后，把围栏指纹提交为新配置指纹。

围栏存在时，旧、新配置的 worker 都不能匹配该 state。每个文件使用原子替换，但整个多文件事务不保证断电原子性，manifest 和备份用于识别中断阶段。

普通异常会先回滚配置；只有确认所有配置恢复且 state 仍符合本事务预期，才最后恢复旧 state 绑定。发现并发编辑时保留他人的修改。`rollback_incomplete`、中断后未提交的 manifest 或 `recovery_required=true` 必须进入人工审核：

- 停止依赖该连接的新动作，保留 state、audit、锁文件、manifest 和所有备份。
- 不清 `inflight`、pending、quarantine，不删除日志或 state，不换空路径，不手工改指纹来解除围栏。
- 不盲目重跑 `--apply`，也不把观察/预检结果当作此前未知动作已经完成的证明。
- 根据 manifest 阶段与文件 SHA 核对配置、state 和宿主实际状态，再制定受锁的恢复操作。当前工具没有自动解除围栏或恢复未知动作的命令。

## 应用后重启与身份核验

保存成功回执中的 `backup_manifest` 和目标身份。管理工具不会热重载已运行的 MCP 或当前聊天；旧 worker 在新 state 指纹提交后会被拒绝。

通过宿主提供的重启/重新连接方式建立新的 Human-Eye MCP 进程，并在当前聊天中取得新的 initialize 或状态工具结果。核对其 `runtime_identity.build_id`、revision、`source_kind`、`production_mode` 和 `identity_check.compatible`；本说明对应的安装 build 应为上述 `c949150a…` 完整值。磁盘配置、管理工具自身的目标身份或旧的保存结果不能代替这一步。

确认新连接后，重新观察实际场景，再进行后续任务。旧观察 token 不应作为新版本的执行资格。宿主是否真实触发三个 hook，应另以真实事件与日志关联验证；本工具不认证所有 agent 的内置 hook 能力，也不证明模型任务收益。

## 已提交后的受控回退

本次备份manifest为 `.human-eye/setup-backups/4dd68ccc7a4e4269babcff2befb6b28a/manifest.json`，状态为committed。旧caption.layout.r1安装与ZIP保留。工具没有独立rollback子命令；本轮已用旧解释器生成只读逆向计划，尚未实际回退。

如果需要回退，使用旧安装的Python `D:\hefe\.human-eye\releases\9.7.2+20261024.caption.layout.r1\.venv\Scripts\python.exe`，目标build为 `sha256:04655fdcd54ad3d248ab7de65806a53bacd501ed9916a3000d98112e8c5f2456`，重新执行上方doctor、plan、审阅、带当次plan_sha256的apply流程。每次均以当时最新state生成计划，提交后还需重连核验。不能直接复制历史备份state覆盖后续journal；本次保存的逆向计划也可能因后续观察而过期。

## 前序发行的历史记录

上一轮r2的当前聊天加载证明属于历史。请求追踪修复版安装／升级时的当前聊天待重连记录保留于[发行报告](../verification/fixes/20261024_request_provenance/REPORT.md)。2026-10-24用户重启后，当前聊天已实际返回 `request.provenance.r1 / 7eecd445…`，真实Pre放行／碰撞拒绝和Post保留工具结果均复测通过，原生MCP图已转交当前对话。随后真实普通三维消息已在assistant工具调用前自动观察，完整场景不变，自有测试宿主已正常关闭；无需再次重启。自动prompt交付仍为几何文本，见[最终实测](../verification/fixes/20261024_restart_validation/FINAL_REPORT.md)。

## R3接入历史与可选预算

2026-10-24用户更新后，当前聊天实际MCP已返回 `9.7.2+20261024.precision.deadline.r3 / 40b09dd3…`，50个运行源、安装来源和固定身份校验通过，无未完成操作或隔离；旧R1配置快照问题已不再出现。真实UserPromptSubmit已返回同一R3身份，本条无空间观察意图的消息正确跳过观察。三事件注册均指向R3，配置及state与升级后逐字节一致，无需再次重启或重置状态。本次未连通Blender接口，没有重新观察或移动；R3真实Pre/Post与原生图片交付的当前聊天复测仍单独待验，见[重连核验](../verification/fixes/20261024_r3_reconnect_check/REPORT.md)。

随后用户要求本地实测，当前聊天已完成R3真实观察、2条成功Pre→MCP→Post、碰撞Pre拒绝，以及宿主精度明确拒绝后继续合法执行。6张原始MCP图片与本轮模型输入字节匹配，独立审查90项通过；25µm缓存、22障碍排名和0.4mm特写自动转移均有本轮证据。精度拒绝isError=true没有Post事件，未冒充成功链。生产配置保持不变，state仅由正常观察/动作更新，自有Blender已正常关闭。当前特定空间消息的UserPromptSubmit自动观察及首次推理前自动图片仍未在本轮重验。见[本地实测](../verification/fixes/20261024_r3_live_practice/REPORT.md)；上段未连通/待验是较早的重连检查时点。

`request_budget_s`是可信本地connector的可选正有限秒数，缺省/null维持旧行为。当前生产没有启用此字段；实测在独立连接启用0.06秒并验证争用拒绝。预算从服务方法入口开始，仅覆盖检查点，含锁等待，不覆盖导入/启动、audit writer或正在运行的计算/原子写入。已提交宿主操作仍完成读回或保留未知隔离，不能自动重试。已有绑定连接的配置变更必须保留原状态并经过受锁迁移，不能手改fingerprint或换空state。

独立wheel现在自带默认Blender子进程worker并纳入运行源身份；SDK默认选择包内helper，显式worker_path仍可供可信调用方使用。实际固定worker已验证nonce拒绝后同连接继续合法操作。详见[本轮报告](../verification/fixes/20261024_precision_deadline/REPORT.md)。

## 正交凹体源码与安装版r1

2026-10-24继续优化后，源码候选 `sha256:f0469622…`（52个运行源）已完成回归、独立反例和隔离真实Blender实测，支持有界世界轴闭合正交孔槽，并将微间隙旧显示别名移入legacy_display。当前聊天实际安装仍为上表R3 / 40b09dd3…；本轮没有打包、安装或迁移人眼配置/state。全局TOML中的Agent Learning启动参数出现外部更新，人眼段、hooks和connector保持原样，第三方变化已保留。

该源码标识不等于安装build：后续打包与隔离安装已重新计算为b9e9ab08…，新唯一发行、安装版Blender和受锁升级均通过，当前聊天重连核验仍待完成。上段“未打包/未迁移”保留为源码阶段历史。旧观察合同已升级，旧顶层显示别名消费者需读取严格clearance_state或明确的legacy_display诊断；不能复用旧观察资格。详见[源码候选报告](../verification/fixes/20261024_concave_presentation/REPORT.md)与[安装升级报告](../verification/fixes/20261024_orthogonal_release/REPORT.md)。
