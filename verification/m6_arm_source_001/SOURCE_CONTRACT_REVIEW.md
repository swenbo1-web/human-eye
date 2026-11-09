# M6-ARM-SOURCE-001：局部来源合同独立复核

范围：只读本仓库、现有真实日志与本机 Blender 随附 Python 脚本。未启动 Blender、训练、模型、GPU 或新进程探针；未改产品/共享文件。本子任务未建立或使用 Agent Learning 绑定，未借用父会话句柄。

## 可以实现的最小入口

显式指定 mesh、同一个 Armature 的 2–4 节连续父子骨链、有序闭合 section 的原生顶点索引，以及明确的 patch 顶点集合。先检查所选数量与索引范围，再读原始 `mesh.data.vertices[i]` 的坐标/全部权重与当前 evaluated mesh 的同索引坐标。不要把旧整资产 128/256 点准入上限搬到局部入口；整资产只做原生 collection counts/身份与 modifier 域检查，不先展开 Python 全数组。

本批 section-only 选择的边界需明确：原 25×16 tube 的 sections 包含 400 环点，两个 cap 中心不属于 section。若要验收 402 点/800 三角形，选择合同必须显式包含 cap 顶点；否则应如实称 400 点及所选闭合面子集，不能用隐式邻居扩选冒充原始明确选择。

首版可限制为单 Armature、顶点组 LBS、无 shape key、无其他 modifier、无 DQ/包络/全局 mask/多 modifier 混合。不能为接受样本而移除依赖、归零通道或修改源对象。当前帧 evaluated 读取与整段动画正确性分开；旧 FK/source 的准入证据不能自动转移到新局部入口。

## 统一坐标和对应关系

对每个原始索引 i，令 u 为 scene.unit_settings.scale_length：

- rest[i] = u · (rig.original.matrix_world⁻¹ · mesh.original.matrix_world · raw_vertex[i])。
- current[i] = u · (rig.evaluated.matrix_world⁻¹ · mesh.evaluated.matrix_world · evaluated_vertex[i])。
- 骨 rest_matrix 使用 Bone.matrix_local，pose_matrix 使用当前 evaluated PoseBone.matrix；均在同一 armature 坐标中，平移列乘 u，旋转部分保持。

这一映射复用 skin_source 中 mesh→rig/rig→mesh 的数学，但不搬运其整资产数组。mesh→rig 相对变换变化影响静态 rest，因此必须参与重准备判断。mesh/rig 共同刚体运动可以保留 prepared。若 rig 世界基底含非均匀缩放/剪切，仅乘 u 不会得到欧氏物理米；首版需明确拒绝/unknown，不能把变形度量当作刚体坐标换算。不要用 inverted_safe 静默替代不可逆矩阵。

只检查原/求值顶点数量相等不足以证明同索引。首版应在明确保索引的 Armature 域内，对所选点做实际骨 rest/pose、全部有效权重的独立 LBS 回放并比对 current。成本是 O(所选点×有效影响数)，不必读取整网格。匹配容差须沿用已声明的坐标精度含义；不宣称物理误差认证。

## 权重不能被局部骨链截断

逐个所选顶点读取其全部正权重，并通过 mesh.vertex_groups 的 index→name 映射到 Armature 骨。实际 use_deform=True 且参与当前 modifier 的骨组才是有效蒙皮影响；普通非骨语义组可以按 modifier 语义忽略。任一有效影响落在所给 2–4 骨链之外，必须明确退出，不能丢掉后再归一化。零有效权重和不满足当前有限 LBS 合同的权重和也要明确出口。

整角色可以有更多骨和 group，不应仅因整角色骨数大于 4 拒绝一个有效局部链。所给局部根骨实际可有链外父骨；其绝对 rest/pose 已包含祖先作用。若 packet 首骨 parent=None 代表的是局部链根，来源记录需保留其真实父引用，不能误称整角色根骨。

## 邻接：冷路径原生全构建，Python 只展开所选邻域

现有 MeshVertex 不能假定拥有 BMesh 的 link_faces。候选冷路径为 fresh bmesh.new → from_mesh(mesh.data) → verts.ensure_lookup_table，再访问所选 BMVert.link_faces，去重并仅保留完全落入明确 patch 顶点集合的面。只接受本版可处理的三角面，避免为准入静默改写原始拓扑。

from_mesh 是原生端**整网格构建/内存工作**，不是 O(局部) 采集；报告必须单列。优势只是避免在 Python 中全量展开全部顶点/面。可以在静态准备后仅保存局部整数拓扑，并在 finally 中 bm.free；不要长期保留可能在 undo/load 后失效的 BMVert/RNA 引用。只读入口不得 bm.to_mesh 或修改原 datablock。

原生索引映射仍需真实版本验收：fresh from_mesh 的 lookup 顺序应与原 native vertex 顺序核对；不能把可能 dirty 的 BMVert.index 当作永久全局 ID。可用所选 BMVert→已知原始索引映射构建局部面，并在 QA 中与原 Mesh 顶点/面独立直接读取比较。不要通过 Python 遍历所有 BMVert 并写自定义 ID 来掩盖全量工作。

## 驻留与失效：现有 dirty 是提示，不是独立静态版本

scene_residency.SceneResidency.updated 对每个 update 增加 serial，仅按 is_updated_geometry 给 original ID 增 dirty。blender_host._resident_capture 的 stamp 同时含 object/data dirty、modifier guards 和动态 frame。它用于求值资源失效；并没有证明 mesh pose-deformation dirty 与原始 rest/weights/topology 编辑可区分。

所以不能直接把“mesh geometry dirty”当 prepared 静态版本，也不能只看 rig pose 变化就忽略同时发生的权重编辑。保守首版可对疑似静态变化只重读所选 raw 静态行/相关 group 与局部拓扑，逐值比较后决定重准备；这保住 pose-only 不重 prepare，但应如实计为所选静态读取，不宣称静态零读取。只有真实 5.2 用例证明确有可靠区分的通路，才能把该通路作为更快分流依据。

静态身份至少关联：当前 host instance/epoch、mesh object/data 实例、rig object/data 实例、选择及骨序、unit、mesh→rig 原始相对变换、骨 rest 和相关 group/weight/局部拓扑。undo/load/替换对象要重取实际引用；同名不是同实例。动态每次读取当前 evaluated 点、pose、frame/来源版本。开始/结束使用既有 epoch/serial 检查，不另建逐帧全量哈希或审批平台；来源在采集中改变就明确退出。

## 证据及待验收

- 本仓库 skin_source_worker.py 已有 evaluated_get 后直接读取 em.data.vertices 的路径，并逐项保留所有权重；不必再额外 to_mesh 制造第二份完整 mesh。
- small_skin_source_worker.py 已把原生 count/dependency 检查放在 Python 数组展开前，可复用这一顺序，不复用其整资产上限。
- scene_residency.py 和 blender_host.py 的 dirty/stamp 如上，没有 pose-only/raw-edit 语义分离承诺。
- 已有 arch_resident_001/run_04/blender.log 记录 Blender 5.2.1 LTS，build hash 9e2066aef7ef；这不是本批重新探测的实时版本。
- 本机 D:/Tools/blender5.2/5.2/scripts/templates_py/bmesh_simple.py 使用 bmesh.new/from_mesh/free；其 to_mesh 是写回示例，本只读方案不能调用。随附 bpy_extras/bmesh_utils.py 的 link_faces 接收 BMesh 顶点。
- 公开 API 文档本次未成功取回，不将其当当前二进制证明。以上仍不能替代真实 5.2 索引映射、pose 与权重同轮变化、相对刚体变换/单位、undo/load 的验收。该窗口由 M5 当前持有，未启动 Blender。

轻量 fake 反例应集中于：chain 外有效权重拒绝；非骨组不误拒；索引选择越界/重复；同名替换与 epoch 改变；pose-only prepared 身份保持；选中 rest/weight/topology 真变化重建；相对变换及单位变化重建。真实 QA 再验证同一局部选择位于大资产上时 Python 展开量仍受选区限制，同时公开 native bmesh 全构建成本。
