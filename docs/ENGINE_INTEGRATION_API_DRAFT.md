# 统一 Blender 生产会话接口草案

本文件提议生产接线、支持域和交付契约，等待主干冻结。现有数组 `FastSession` 仍服务数组调用。统一入口沿用已验收的 RB、BC、TD、VG、AO 和 CF V+A。形变展示继续使用精确 TD。

## 公开接口

生产 Python 对象建议命名为 `BlenderRadicalSession`，不持有全局会话。调用者提供 scene、该 scene 的 view layer、稳定 ID → Blender 对象的有序映射、有序目标 pair、Goal、各网格的拓扑代、显式 TD 参考和可选 CF 部署参数。目标 pair 取 Goal 的 moving/reference 顺序。其余对象为本会话的 VG 上下文，允许是零个。会话不遍历任意 GUI 场景来猜选对象。

```python
reference = ReferenceFrame(frame_id, topology_generation, moving_world_m)
with BlenderRadicalSession(scene, view_layer, objects, goal, generations,
                           reference=reference, deployment=deployment) as session:
    before = session.observe(ObservationRequest("before", "NATURAL", "L"),
                             context_changes=before_context_changes)
    planned = session.predict_action(before.observation_id, "command-1", command,
                                     predictor="L")
    if isinstance(planned, PreparedAction):
        result = session.execute(planned, ObservationRequest("after", "NATURAL", "L"),
                                 context_changes=after_context_changes)
        session.action_feedback(result.action_ticket)
        session.view_feedback(before.view_ticket, consumer_feedback_for_before)
        session.view_feedback(result.view_ticket, consumer_feedback_for_after)
        next_result = session.observe(ObservationRequest("next", "NATURAL", "L"),
                                      context_changes=next_context_changes)
```

该示例的评分反馈由调用者从实际返回的 PNG 得到。无图或 F 时无 view ticket，无学习 A 或无有限实测时无 action ticket。调用者仅提交存在的票据。会话串行在同一 Blender 主线程/GPU 上下文使用，调用之间由调用者管理场景变化。不同会话的状态、索引和资源分别持有。

| 调用或返回 | 约定 |
| --- | --- |
| `observe(request, *, context_changes)` | 用场景当前帧做一次实际观察。每个需要的对象最多一次 RB capture。返回观察 ID、帧、AO bytes、有序 PNG 附件、清晰的图像状态和可选 V 票据。 |
| `ObservationRequest(observation_id, image_mode, view_arm)` | `image_mode` 为 `NATURAL`、`SECTION` 或显式 `None`。F 为现有 active 默认顺序，R 为检索，L 为学习重排。没有部署模型的请求显式用 F。R/L 均为现有 16 候选全排列，语义等同实际 VG。 |
| `predict_action(observation_id, action_id, command, *, predictor)` | 使用当前已观察状态与一条显式 `Translate` 或 `SetShapeKey`。预测臂为 `NONE`、`G` 或 `L`。返回绑定观察和命令的 `PreparedAction` 或 `NoAction(reason)`。预测不写宿主。 |
| `execute(plan, after_request, *, context_changes)` | 调用现有控制器完成一次写入及后回读。复用真实 `Outcome.after` 及同次刷新网格做后 TD/VG/AO。返回一个包含 before、after、Outcome 的 AO 包、对应附件和可用反馈票据，不另编码 standalone after。 |
| `action_feedback(ticket)` | 学习 A 只用成功执行后实际 `Outcome.measured_delta_m`，与动作前的合法特征和米制尺度一起形成一次更新。调用者不提供任意 delta。 |
| `view_feedback(ticket, feedback)` | 反馈绑定观察 ID、附件键、实际方向的规范候选 ID 和消费者的像素判断。安全标签为 VG 实际提前停止且消费者判像素合格。只写实际方向及其实际探测 ray 数。R 写库，L 按已验收规则写库及更新。 |
| `replace_reference(reference)` | 显式替换同一拓扑代的世界米制参考并撤销当前观察的可执行性，下一次真正观察使用新参考。参考切换不回写过去观察。 |
| `close()`、上下文管理 | 清除 controller 持有的 bridge/index/current、会话 TD 参考、临时准备数据和 CF 参数/经验库，在所属 GPU 上下文释放 VG offscreen 和相机。关闭后引用旧返回包仍可消费其 bytes。 |

调用者使用本次会话内唯一观察 ID。同帧可有不同观察 ID，禁止以 frame number 代替动作绑定。当前捕获与已计划动作之间场景稳定，执行用绑定当前观察的计划。迟到的 V 反馈通过相应票据仍可作用于实际呈现。一次更新消耗票据。票据由调用者持有，包含会话身份对象、操作绑定和必要特征，小票据本身标记已消费，不设未决字典、散列、TTL 或等待队列。复制或重放相同票据属于调用错误。用于冻结正式质量评估时，基准直接从同一部署参数启动独立状态，把计时更新写入独立 shadow；真实闭环使用同一活动会话更新后再查询。

## 最小共享捕获接缝

控制器是唯一的目标 `BlenderResidentBridge` 和两份目标 `SurfaceIndex` 的所有者。生产会话调用其 `observe` 或 `execute` 并从同一 bridge 借用最新 target/context mesh。两者各自在现有依赖图和米/BU 下运行。

建议只在 `human_eye_fast/control.py` 增加两个可选构造关键字，以及内部捕获阶段标识。语义示意如下。

```python
BlenderControl(scene, objects, goal, *, view_layer=None, capture_context=None)
# capture_context(phase, bridge, depsgraph, scale_length) -> None
# phase 为 "observe" 或 "after"，只采集显式非目标网格
```

- `_view_layer` 采用显式参数，否则沿用原 `scene.view_layers[0]`。在 `_capture` 原目标 capture、索引建/更新和真实 BC 查询后，在同一 temp override 和 graph 调用可选回调，随后返回原 `ClearanceReadback`。显式 phase 由 `observe`/成功 `execute` 调用点传入。默认无回调的分支保持既有返回和可见行为。
- 目标初次加入时仍读拓扑、顶点、变换和外观。每次显式观察用原 `VERTICES|TRANSFORM|UNITS`，动作成功后的两目标用原 `VERTICES|TRANSFORM`。已持有上下文可由调用者显式声明 `MeshChange.NONE`；动态上下文声明所需变更位，包括拓扑和外观。回调不再次取 graph、不捕获目标、不运行第二次 BC。目标外观和目标拓扑在单会话代内固定，外观或拓扑替换通过关闭旧会话并显式新建代，且给出匹配新原面的参考。
- `execute` 获得 `Outcome.after` 后直接发布，不调用 `control.observe(after_id)`。下一次显式 `observe` 是反馈后的新查询。它可在同一 Blender 帧重新观察，也可以由调用者先改变帧。其新捕获单列，不计成前一次动作后回读的第二次捕获。
- VG 仍可按现有实现为相机投影取得自己的 evaluated graph。该获取不重复读取目标网格，不另建目标索引。图像在同一 scene/view layer、稳定帧和相同米/BU 下生成。首版无需修改 VG 的入参。任何新增 camera seam 另由主干审定。

替代方案是提取公开的通用 CaptureState。它会扩大已验收控制器状态边界，只有上述回调被真实接线证明不够时才重新审定。预检用验证侧薄适配模拟接缝，不作为生产继承方案。

## 坐标、参考和动作支持域

设 `s = scene.unit_settings.scale_length`，由真实 RNA 读取，`M=[A|t_BU]` 为 evaluated world matrix。列向量表达的 RB 变换为 `x_m=A(s x_BU)+s t_BU`。代码用行数组 `(x_BU*s) @ A.T + t_BU*s`，单位不重复换算。父级、父逆和旋转、平移、非均匀尺度都体现在完整 evaluated matrix 中。模型与 TD 不直接使用 authored `location` 代替求值世界变换。

参考是调用者显式提供的匹配拓扑代的 **世界米制顶点快照**，有独立参考帧 ID。若参考从宿主采集，应使用参考时刻求值点、变换和单位按同一公式转一次，并立即拥有该数组。会话持有一份 moving 对象的参考，首版 TD 对本次 moving 世界数组计算相对参考的单样本事实。AO 参考帧、采样帧和位置帧分别明确。原始面指 evaluated loop-triangle 行号，三角行到原 polygon 的映射由 RB 保留为单独身份。参考和当前同时做同一世界坐标重表达，与固定世界参考下的真实运动不同，后者可以贡献世界法向角和位移。变更单位后若物理参考语义变化，调用者显式提供新参考。

已知有限动作 G/L 的预测域如下。

- `Translate(delta_world_m)` 使用明确世界米位移。当前控制取借用的 `world_from_local[:3,3]`。有限几何假设 moving 的求值形状及世界线性部分不随写入改变，reference 的求值几何在该命令下独立。静态可逆父变换可支持，需真实探针对照写入后矩阵和顶点。接线主验收对平移显式使用 G，已封存的学习 A 收益只对原 shape 主集主张。若 reference 依赖 moving、驱动/约束改变形状或父级使实际有限变换不同，调用者显式使用 `NONE`，仍使用原生回读给真实结果。
- `SetShapeKey(key_name, value)` 从真实 RNA 取选中 key 与它声明的 `relative_key` 的 authored 坐标，读取 evaluated q，而非把 Basis 或请求目标当当前控制。已知世界米形变基为 `B=(key_co_BU-relative_key_co_BU)*s @ A.T`，仅线性部分乘以差分。有限位移为 `(target-q) B`。要求 relative 模式、活动可写的单个未遮罩 key、当前及目标 q 在支持区间、其他影响和世界线性部分保持不变、求值顶点行与 authored key 对应。固定父级下的旋转和非均匀尺度适用该公式。诊断需含实际相对 key 指向非 Basis 的例子。绝对形态键、vertex-group 掩码、改变行或非线性形变的 modifier、改变结果的驱动及超范围写入在 G/L 合同外。明确 `NONE` 可交给现有控制器执行其支持的真实命令。实际 q 和几何只从回读得出，超范围诊断仅以实际 q 与实测计。

静态 RNA 基可由调用者为明确的 key 预备，加载成本单列。G 的最小计算只需要当前见证三角三行世界位移及局部窄相。L 计算同语义 G 和完整合法特征，复用特征中的 G，不再重复窄相。

空表面由统一入口发布 `empty_surface` 与空见证，无 PNG、无动作计划和标签。这是会话的明确任务政策。独立 `BlenderControl` 原本允许对空面执行显式命令并产生无有限 delta 的 Outcome，保留该直接调用行为。有限零距保留真实 AO 和自然图像，VG 无搜索 ray、无 V 标签。零距且已经达到 Goal 时不写入。零距目标未达时可明确命令打开间隙。SECTION 只在正间隙生成，非适用时建议保留 AO/Outcome 并返回 `section_requires_positive_gap`，无替代图像。正式接线质量用预定有效 mode；非适用状态另作控制。执行后若成像或发布失败，应让错误携带已经实测的 Outcome，调用者可以区分命令是否已执行，无自动重试。

## 所有权和公开消费

会话内部的 RB 网格借用仅有效至下一次可能改写它们的捕获。TD 当前归约结果独立拥有。完成首次发布后，当前内部事实可借用 moving 点直到下一次写入。执行开始前，只在联合 AO 包将重新使用前观察位置时，保存 moving 的一份米制位置快照。它和已拥有的 TD 摘要维持前后事实的正确绑定，发布联合包后即可释放。参考快照独立常驻，不保持完整历史。后观察内部事实在下一次操作前可借用当前数组。外部结果只交付不可变 AO bytes、PNG bytes 和轻量绑定，不泄露借用 mesh。动作前 23 维及 V 16×5 特征只在各自反馈票据或当前计划中拥有必要数据。

附件使用逻辑相对键 `<observation_id>.png`，调用者提供的观察 ID 在本会话唯一且为路径单段。AO 原 `image.path` 等于该键，消费者通过返回附件映射直接读取 bytes，无落盘要求。一次联合包的两个图像键分别绑定 before/after；复用已有 before PNG bytes，不重渲染。图像仍使用现有公开 schema、实际相机、PNG 和原始可用剖切语义。无图时 `image=null`。方向、selected ray、原生 stop 等审计字段可放轻量返回元数据，不能由消费者推测成功。阶段二应提交仅使用公开包、公开 schema 与附件的消费者示例。

## 部署输入和后续文件

部署输入可直接由调用者构造不可变参数对象，或显式提供 NPZ 路径给 `load_cf_deployment(path)`。NPZ 用 `np.load(..., allow_pickle=False)`，只在加载边界解释版本和形状。加载与模型创建独立于 Blender scene，普通包导入不触发 bpy 或 gpu。运行时不 import 验证模块或读取项目目录，不以 scene、seed 或文件路径自动选模型。

部署格式 v1 提议如下。float 数组为 float64，mask/开关为 bool，版本为标量整数 1。V/A 特征顺序、二次积顺序及截距沿已验收 CF。每个库 N 可为 0 至 4096，并按存活写入从旧到新排列。v1 用于启动部署会话，无训练/评估标签清单或消融权重。

| NPZ 键 | 形状或语义 |
| --- | --- |
| `version` | 标量 1 |
| `v_mean,v_scale,v_weights,v_quadratic,v_lambda` | 均值和标准差各 (5,)，权重为 (6,) 或 (21,)，后二者是标量 |
| `a_mean,a_scale,a_weights,a_quadratic,a_lambda` | 均值和标准差各 (23,)，权重为 (24,) 或 (300,)，后二者是标量 |
| `retrieval_scale` | (16,5)，冻结 R 的逐坐标标准差 |
| `v_keys,v_values,v_known` | (Nv,16,5)、(Nv,16,2)、(Nv,16)。值依次为安全标签及该方向探测 ray，mask 区分已观察 |
| `a_keys,a_values,a_known` | (Na,23)、(Na,1)、(Na,1)。值为已经有真实结果的归一化残差 |

加载结果是只读部署参数。会话实例创建私有两头和两环，按部署行序填入，以保留最近邻等距的最早顺序。用冻结的三个模型离线导出并逐字段核对。导出器位于验证侧，可以读取既有封存 NPZ；生产加载器只读上述契约。无部署时显式 F 和 `NONE`/G 可用，不分配经验库。L 或 R 必须明确提供部署参数。没有由失败触发的隐式模式切换。

阶段二拟新增 `human_eye_fast/blender_radical_session.py`、`human_eye_fast/cf_deployment.py` 和公开示例 `examples/blender_radical_session.py`，在 `control.py` 加上述最小 seam，包 `__init__.py` 追加新接口出口并验证普通 NumPy 环境仍可导入。示例用独立后台 Blender，调用者明确提供 .blend、scene、view layer、对象 ID、参考帧、部署文件、mode 和命令。示例可将公开结果及附件写到明确输出目录，写盘属于示例边界。下一阶段的验证导出、正式 benchmark 和公开消费者入口由主干冻结范围。无需修改既有 RB、BC、TD、VG、AO 或 CF 计算逻辑。
