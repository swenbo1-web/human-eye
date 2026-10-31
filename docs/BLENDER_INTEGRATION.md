# Blender 三维宿主接入

2026-10-28 当前聊天重载验收：已实际载入 v19／9.7.2+20261028.support.discovery.r1（a0198acc…／installed_distribution／68 文件），状态健康、目标账本 0，旧配置快照拒绝已解除。当前 MCP 完整发现唯一支撑面，实测间隙仍为 3.1304261516453477 毫米；回填完整 selector 的 1 毫米目标预览只返回单步限幅候选，未移动。人为改错客户端 revision 的预览被拒绝并要求重新观察；没有实际编辑宿主来制造这条负例。独立 Fraction 真值、768×768 原生 PNG 和全 14 Scene 不变均已核对。

真实用户三维回复已在模型该轮工具调用前触发 v19 UserPromptSubmit，自动交付完整几何文字；五组定义保留。本轮还核对了 clearance_segment 预览的 PreToolUse／PostToolUse 去重，不能当作 execute:true 的动作链或 transform 各事件已通过。自动原生图片仍未证明，Hook 为 text_only。先前独立安装私有场景的 12 次移动是另一阶段证据，本聊天本轮零移动。

只读安装 SDK 边界矩阵 12 组／28 次调用／277 项检查通过；凹体、开放 reference、穿透／接触和有限面外一 ULP 明确 unsupported，几何／有理复杂度和过长 revision 返回 unknown，不放宽门。真实多候选截断未覆盖。下一单点候选先检查审计日志大字节／少行时重复整写和轮转，再考虑纯距离观察的对齐按需；两项均未实现，成本对照仍 pending。既有 27.84%—36.71% 文本字节减少不等于端到端或模型提速。工程构建可继续有限验收，整体公开发布门仍为 false。

[当前重载阶段](../verification/fixes/20261028_v19_reload/REPORT.md)、[当前量测与预览核对](../verification/fixes/20261028_v19_reload/CURRENT_VALIDATION.json)、[真实用户文字 Hook 审查](../verification/fixes/20261028_v19_reload/REAL_USER_HOOK_REVIEW.md)、[只读边界矩阵](../verification/fixes/20261028_v19_reload/MATRIX_REVIEW.md)。接口继续见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)。

当前注册与当前聊天均为 support.discovery.r1 的安装 Python；下方入口命令继续适用。真实用户窗口本轮只读观察／预览不保存文件，也没有关闭 Blender。只有实际捕获证明该时点宿主在线，status 握手本身不探测宿主。

以下保留此前阶段记录，尤其 v19_activation 的待重启状态仅表示当时阶段；当前状态以上文和本轮重载报告为准。

2026-10-28 最新状态：v19 工程构建 9.7.2+20261028.support.discovery.r1（a0198acc…／68 文件）已离线安装并完成磁盘激活，新注册进程实际验收通过。当前聊天仍为 v16 旧配置快照，返回 stale_configuration_snapshot，需重启后核验；真实新用户 Hook 未通过本版验收。四文件迁移保留五组 Hook、Agent Learning 当前配置与状态，state 仅改配置绑定；磁盘激活不等于宿主信任或当前聊天重载。

显式 query.support_plane_discovery 已实现当前对象对的精简发现，完整 selector 可回填有界执行段。四模板文本字节中位减少 27.8448%—36.7095%，本地服务仍增加约 1.8—8.0 毫秒，不宣称模型或端到端提速；默认 PNG 保持。接口与边界见 [精简支撑面发现](SUPPORT_PLANE_DISCOVERY.md)，[新注册入口结果](../verification/fixes/20261028_v19_activation/REGISTERED_ENTRY_RESULT.json)和[配置保留结果](../verification/fixes/20261028_v19_activation/activation/PRESERVATION.json)。

当前注册入口（stdio，不是 HTTP；启动和状态握手不证明 Blender 在线）：

~~~powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -m human_eye_plugin.production_server --config 'D:/hefe/.human-eye/live-connector.routing-spatial.json'
~~~

本版实际安装场景动作已通过，新注册入口常规只读观察通过；当前聊天未重载。BlenderMCP 默认回环 127.0.0.1:9876，不由引擎关闭或保存用户窗口。

以下为此前阶段记录，保留当时版本、命令及验收边界；当前状态以上文及精简支撑面发现说明为准。

2026-10-28。稳定安装与当前聊天均已核验为 `9.7.2+20261028.query.evidence.r1`（v16／e06beb38…／66文件），旧配置快照错误已消失。当前MCP的top1、无图可选对齐及原生PNG通过；真实三维用户消息也已在模型首次回复／工具调用前触发自动文字量测：BluePart／GreyBase当前最小间隙3.130426毫米，fresh捕获、未移动，已有1°倾斜保留。泛化“继续”按规则跳过。五组钩子定义与Agent Learning配置保留；不据此推断其余动作钩子和各类Agent已全部验收。见[重载与非双箱实测](../verification/fixes/20261028_v16_reload/REPORT.md)；安装迁移历史见[前轮](../verification/fixes/20261028_v16_activation/REPORT.md)。

以下保留此前阶段说明；当前安装与聊天状态以上述进展为准。

2026-10-28。当前项目稳定安装为 `9.7.2+20261028.loopback.connect.r1`（v14，build `sha256:17e313ea836512bd293b92d0665b7226415807ee0cecfa3d651c13acd68ba344`）。优先通过安装版 MCP 连接用户已经打开的 BlenderMCP 窗口；也可由 agent 的模型调用前回调自动触发引擎。不需要在 Blender 自带 Python 中安装 NumPy/Pillow 等完整引擎依赖。

## 当前安装版与用户窗口

当前注册入口使用以下命令；它是 MCP stdio 服务，不提供 HTTP 地址，启动或状态握手成功均不证明 Blender 已在线：

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -m human_eye_plugin.production_server --config 'D:/hefe/.human-eye/live-connector.routing-spatial.json'
```

这条命令对应本项目已安装版本，用于核对现有注册；其他项目需使用各自受信的绝对配置路径与已验收安装环境。无需另起相同服务来证明当前聊天重载；以当前工具实际返回的 `runtime_identity` 为准。不要用 `--demo` 或源码启动器替代安装版验收。

`BlenderMCPHost` 通过配置中的回环地址（当前 `127.0.0.1:9876`）使用已有 BlenderMCP 服务；它不安装／启动 addon，不拥有或关闭用户 Blender，也不保存用户文件。配置中的 `project_root` 指向可信引擎安装根目录，保证 Blender 能载入相同的固定 `human_eye_plugin/blender_host.py`，不是用户 `.blend` 所在目录。

当前四项工具为 `human_eye_scene_observe`、`human_eye_transform`、`human_eye_clearance_segment`、`human_eye_connection_status`。Codex 配置有五组 Human-Eye hooks：提示前一组、两个执行工具各自的动作前与动作后四组；Agent Learning 已开启。hook 是否受信、实际触发和输出是否进入模型上下文仍须使用真实事件证明。

只读验收顺序：

1. 在实际 Blender 窗口打开目标工程，启用并启动现有 BlenderMCP 连接器。若当前没有 Blender 进程或回环监听，真实资产验收仍待宿主就绪。
2. 用 `human_eye_connection_status` 核对身份、状态绑定、隔离和未完成操作；`host_connectivity_checked=false` 明确表示没有探测 Blender。
3. 用 `human_eye_scene_observe` 捕获当前工程，核对真实对象名／完整ID、单位、revision、指纹与捕获范围，再用本次返回的对象对核对一项独立已知尺寸或间隙。只观察时不调用变换或间隙段执行，观察会正常更新引擎状态与审计，不改变或保存 Blender 几何。
4. 由真实用户发送明确对象名的只读三维指令，关联原始 `UserPromptSubmit` 输出和实际 audit／trace，验证在模型首次回复与工具调用前完成自动观察。手工probe、配置文件存在或仅服务status不能替代此项。

2026-10-28已有一次当前Codex／自有双箱场景的真实自动文字量测通过，约4毫米、零移动；该独立后台进程已关闭。它不证明用户窗口／实际复杂资产或其他Agent已验收，也不证明自动原生图像或模型任务增益。见[真实自动观察验收](../verification/fixes/20261028_v14_auto_message/REPORT.md)；完整接入流程见[Codex实时路由](CODEX_LIVE_ROUTING.md)。

## 低层宿主与独立后台环境

`BlenderSceneHost` 在 Blender 主线程中访问 `bpy`。独立载入 `human_eye_plugin/blender_host.py` 时只依赖标准库，变换时使用 Blender 的 `mathutils`；不会经包初始化导入 NumPy/Pillow。已有 Blender 窗口可以通过其 MCP Python 执行入口载入该模块。

`BlenderProcessHost` 在外部 Python 中启动独立后台 Blender，载入调用方明确指定的已有 `.blend` 文件，使用持久进程接收结构化读取和变换请求。它不连接已经打开的窗口，变更保留在子进程内，不保存原 `.blend`。子进程禁用自动运行文件内脚本，Windows 下不弹出新窗口。关闭连接会结束自己创建的进程。

```python
from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.host_runtime import GuardedHostRuntime

with BlenderProcessHost(blender_executable, existing_blend_file) as host:
    runtime = GuardedHostRuntime(host)
    # 调用 host.capture_scene() 获取连接器提供的真实 object_id。
    prepared = runtime.before_model(
        session_id="agent-1", task_instruction=user_task,
        focal_id=part_id, reference_id=base_id,
        messages=original_messages, format="openai_responses",
    )
    # 在宿主实际请求中使用 prepared["messages"]。
    # 模型输出动作后，在执行边界调用：
    result = runtime.execute_action(
        session_id="agent-1",
        action={"translation": [0, 0, 0.01], "rotation_euler_deg": [0, 0, 0]},
    )
```

外部引擎也可以通过 `ExternalRouterProcess` 从 Blender 的 Python 进程启动。这个轻量客户端本身只依赖标准库，向已安装 NumPy/Pillow 的外部 Python 传递结构化事件。引擎图像和数值由外部进程生成；场景采集及实际变换始终在 Blender 主线程。示例 `examples/blender_live_test.py` 使用此方式测试已打开的 Blender。

独立后台进程桥的 worker 可显式指定 `worker_path`；源码用法默认位于 `examples/`，从安装包调用时不要假定源码示例随 wheel 一同存在。它与当前已安装的 `BlenderMCPHost` 用户窗口入口是不同运行方式；独立工厂或既有文件的后台测试不等于操作了用户已打开的窗口。

## 空间数据和变换语义

- 导出全部场景网格，包括隐藏网格。使用依赖图求值后的网格，包含可支持的修改器效果；无法求值的隐藏或排除物体会阻断，避免遗漏碰撞体。
- 使用稳定的名称和库路径派生对象 ID；重命名会改变身份并使观测失效，不向用户物体写入自定义属性。
- `scene.unit_settings.scale_length` 将顶点和枢轴转成米；局部轴由世界矩阵列向量转换为引擎要求的轴行向量。镜像或剪切的轴可信度保留歧义。
- 场景版本同时覆盖几何、身份、单位缩放、帧和影响变换的约束信息。连续相同读取保持相同版本。
- 变换先绕对象原点旋转，再施加世界坐标平移。输入为米和 XYZ 欧拉角度数；执行前再次读取场景，核对版本与完整指纹。
- 操作范围暂限独立、静态、刚性网格。实例、其他几何类型、修改器/形变、父子依赖、动画/驱动、刚体、锁定及非均匀缩放等不满足执行约束时拒绝，不把部分支持称为完整执行能力。

`BlenderSceneHost.apply_transform` 是低层宿主边界，本身不授予碰撞许可；生产入口应通过 `GuardedHostRuntime` 或等价的“真实快照 → 引擎动作检查 → 宿主版本校验执行 → 实际回读”流程调用，不能只看模型上下文里的建议。

新 MCP 连接器和后台 worker 启用版本化 `host_execution` 能力声明，在操作前给出不支持原因，避免把可读取但不可执行的场景当作一次不确定写入。直接构造 `BlenderSceneHost(execution_metadata=True)` 可启用相同声明；默认关闭元数据以兼容旧常驻客户端的快照指纹，低层执行限制始终生效。

## 执行与故障

`GuardedHostRuntime` 只从绑定宿主采集场景，不接受模型提供的场景、来源或待执行版本覆盖。多会话共享同一宿主运行时；一次动作后清除其他会话的旧观测。执行异常、失去回读、意外变换、拓扑变化、其他物体变化或新碰撞会使整条宿主连接进入隔离状态。

隔离后的重新观察不会自动恢复执行。`reconcile_after_host_review()` 只供宿主操作员核查实际状态后调用，不应暴露为模型工具或自动重试步骤；它不认证前次动作，并要求后续重新观察。

Blender 变换存在有限精度。通用路由仍默认使用 1e-9 米比较读回；宿主运行时显式使用 1e-6 米的变换读回误差界，上限限制为 1e-5 米。该值只用于请求变换和读回变换比较，不放宽几何碰撞判定，也不代表传感器精度或设备安全公差。实际碰撞始终对实际读回顶点重新检查。

`execute_action(..., goal=...)` 可额外对真实回读验收间隙、原点位置与接触姿态。`execution_verified` 与 `task_succeeded` 分开：未提供目标不声称任务完成，目标未达不重放已成功的动作。新接口、实际装配微调结果及版本重载说明见 [第一版流程](THREE_D_V1_WORKFLOW.md)。

进程超时、响应 ID 不符、损坏输出或可能的部分执行会使连接失效，禁止复用或自动重放动作。后台连接关闭后不保存原文件；UI 连接器发生错误会尝试恢复原矩阵并校验恢复结果，但仍应向运行时报告异常。

## 验证边界

本地契约测试覆盖单位、轴、完整场景、有限数值、版本与指纹、执行回滚、异常隔离、跨会话、有限精度读回、进程超时和响应错误。真实 Blender 验证与模拟宿主测试分别记录，不用模型 stub 结果代替真实模型效果。

已打开窗口的测试入口 `run_live_test(project_root, engine_python)` 会创建独立测试场景，验证自动观测、候选穿透/第三物体碰撞拒绝、外部场景编辑失效、真实旋转与平移、单位换算及实际回读，最后恢复原场景并删除自己创建的测试数据。它不保存用户文件，不发起模型 API 请求，也不会安装或升级 Blender add-on。

这些入口覆盖经过它们的结构化操作。原有 Blender 任意 Python、终端等执行路径仍需 agent 宿主另行接入或限制；本轮实测不等于已启用 Codex 的全局视觉 hooks，也不证明模型一定采纳引擎判断。
