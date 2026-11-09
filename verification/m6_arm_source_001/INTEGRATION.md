# 待共同固定版本的薄接线

此分支只交 `arm_twist_source.py` 与验证，没有修改 M5 的 host／worker／service。已在独立 Blender 5.2.1 后台对默认 BMesh 的 capture→prepared 做七状态检查，见 `native_01/RESULT.json`；最终 worker／stdio／MCP 入口尚未安装或验证。

入口用法：

```python
from human_eye_plugin.arm_twist_source import ArmTwistSource

adapter = ArmTwistSource(scene_host)
bound = adapter.bind({
    "mesh_name": "ArmMesh", "armature_name": "Rig",
    "bone_names": ["upper_arm", "forearm"],
    "vertex_indices": patch_native_indices,
    "sections": existing_ordered_native_sections,
})
capture = bound.capture()  # static_patch 仅首次／重新准备时非 None
report = bound.analyze()   # 复用已有 prepare，报告附当前 source
```

sections 与 vertex_indices 都是原始 mesh 顶点索引；显式 vertex_indices 可以包括不属于任何截面的 cap 顶点。本轮 402／800 fixture 使用该方式。省略 vertex_indices 仅使用截面点并集，不自动扩选或发明截面。三角形只收纳顶点全在所选 patch 内的面，按保方向循环等价规范化，再映射到 caller 的局部顶点顺序。

## 固定提交后需加的现有入口

1. 在现有常驻 `BlenderSceneHost` 上按需持有一个 adapter 与当前显式选择的 bound。复用现有 host transaction／scene residency。选择改变时重新 bind，其他请求按相同选择复用；不能每次请求都重新构造 bound，也不需要另建注册服务。已有 source 捕获会 fresh resolve 名称，检查对象／data 实例与 epoch、版本，因此同名替换或重载不会沿用旧 prepared。
2. 使用原 verified-source／常驻初始化方式，只在第一次明确专家请求时加载 `arm_twist_source`、`rig_pose`、`arm_twist_expert`、`arm_twist_weights`。这些均为 manifest 内的 `.py`；不能用未验证的 path import／pyc 取代已经冻结的源码。若用轻量 package namespace，沿现有 `SourceGuard.allow_namespace` 和 canonical 模块 loader；不要简单执行包 `__init__` 导致整套默认 facade 被加载。MCP 的首次来源快照也要包含这些按需依赖，暖请求不得重读或重新编译。
3. owned worker 和 MCP fixed read-only command 增加一个 `observe_arm_twist(selection)` 的薄分支，调用同一 bound.analyze；parent wrapper 仅转发固定参数并校验返回 schema／当前选择与 source 绑定。不复制 worker／stdio 服务，不增加任何 setter 或批准表单。若传输仅需 source 数据，可使用 capture 的静态／动态分离包，但不要对同一 patch 在两侧重复 prepare。
4. 原 `capture_task_scene`／nearest 和 M5 活动线语义不变，普通只读任务不会加载模型。M6 仍是显式实验调用；区域报告保留 synthetic scope／无执行权限，不因为来源适配通过就把模型输出升级为损伤证明。

## 共同固定版仍待验收

- 在独立生成副本创建单 Armature、vertex-group LBS、无 shape keys／DQ／包络／mask 的已知 402 点／800 三角形 patch。显式列出 2..4 骨及截面／cap 原始索引，首次调用走真实新入口，直接原生读取逐项核对点／权重／矩阵及全局 ID。
- 同一 bound 多姿态，记录真实依赖图通知。本轮已确认：稳定重复零静态读取，纯姿态实际触发所选静态复查但不重新 prepare。pose 也更新 Armature datablock，不能由 fake 的 revision 约定推断零读取；本轮权重操作还显式调用 `mesh.data.update()`，不能据此保证所有权重编辑入口的事件可分。后续先核对真实工作量再细分复查，不直接移除 object dirty 守卫。
- 在更大原始 mesh 上选择同一局部 patch，核对 Python 读取仍局部。默认 topology reader 的 `bmesh.from_mesh`／lookup 是原生全 mesh 构建，需单列成本；本轮已在小型三角网格运行该路径，未消除或分开计时这部分，更未实测大资产。真实 5.2 非三角面的 triangulate 仍需核验。
- 真实修改 rest、有效权重、局部拓扑及骨 rest，验证重新准备；运行中改单位／mesh→rig 相对矩阵、同名对象替换、undo／load／scene switch，验证当前来源和旧 prepared 失效。源矩阵统一为 armature-local metres；rig world 非刚性明确拒绝。
- 选中顶点全部有效 deform 权重均检查：链外有效骨、无权重、明显非单位和、DQ／包络／mask、改变对应关系的 modifier 精确拒绝。普通非骨顶点组可按 modifier 语义忽略，不把它当额外骨权重。current 与所选 rest／权重／当前骨姿做同索引 LBS 回读；非 LBS 保截面对照不能冒充合法本来源。
- 本轮直接 native capture／prepare 通过，未在 native 脚本调用 analyze／MLP；完整专家报告仅由 fake-host 测试覆盖。同版安装、真实专家与工具入口确认前，结论维持 READY_FOR_INTEGRATION。此次后台进程已关闭、handler 已清理，独占窗口释放。
