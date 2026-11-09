# M6-ARM-SOURCE-001：READY_FOR_INTEGRATION

从 `9508a1d5cbdcadad80a42c4922501c855d5ae570` 建立 `codex/architecture-arm-source`，新增独立 `human_eye_plugin/arm_twist_source.py`，没有改 M5 的 host／worker／service、专家、权重、训练数据或阈值。薄接线位置与共同版本验收项见 `INTEGRATION.md`。

## 已完成来源连接

显式 mesh、2..4 骨链、已有有序截面与原生顶点索引绑定后，仅读取所选原始／求值点和实际有效骨权重，构造统一 **armature-local metres** 的静态 patch 及动态 current／pose。rig world 要求刚性；mesh→rig 相对仿射和场景单位共同换算，骨矩阵只换算 translation 列。

局部数量在任何几何展开前检查。402／800 patch 显式带入不属于截面的 cap 点；不猜截面、不自动扩选、不通过旧 whole-asset 256 点入口。每个选中顶点的全部正有效 deform 权重都检查，链外有效骨拒绝，非骨或非 deform 普通组可忽略；无权重、明显非单位和、DQ／包络／mask／其他 modifier 等有准确出口。current 与所选 rest／权重／当前骨姿做同索引 LBS 回读。

复用现有 host transaction／SceneResidency 的实例、epoch、dirty 和版本，fresh resolve 对象／data 身份。静态变化重建 prepared，纯版本／姿态更新保持 prepared；source 记录当前对象、版本、frame、选择与原生全局 IDs。可疑 dirty 时只重读所选静态候选并比较，不做每帧全资产哈希。缓存仅在完整采集、LBS 回读与版本检查成功后发布；失败不会返回旧成功。

默认 topology reader 用临时 BMesh 的选中顶点 incident faces，不生成全资产 Python 顶点／面数组；三角形循环等价规范化后映射到局部顺序。**`bmesh.from_mesh`／lookup 本身仍是原生全网格构建**，没有宣称整个来源过程只需 O(selected)，也没有把既有 host 的零 to_mesh／triangulations 计数当作没有 BMesh 成本。

## 已测：31 项 fake-host 与一次真实后台检查

`final/result.json`／`unit.log`：**31 项零失败／错误**。稀疏 indexed collection 禁止全顶点迭代、foreach_get 和不在选择内的读取；在大于百万的虚拟全资产中，冷读取仍为 402 rest／402 weights／402 current、800 三角形、两骨、一次准备。fake 稳定通知条件下，四个后续 LBS 姿态仅新增 1,608 current 和八个 pose 矩阵。dirty 无实际变化重读候选但不重 prepare。

11 资产、77 姿态尝试中，**55 个 LBS 数学构造样例通过，22 个非 LBS 保截面对照以 `same_index_lbs_readback_mismatch` 准确拒绝**；未把对照假装成当前来源的支持范围。还覆盖局部 budgets、rest／weights／topology／bone-rest 变更、对象替换、scene／epoch／undo/load、同 RNA 不同 wrapper、过期 evaluated.original 拒绝、中途版本变化不提交、坐标／单位与原始 IDs。完整 `bound.analyze` 与专家报告的一致性在 fake-host 中通过。

根释放短独占窗口后，`native_01/RESULT.json` 用 **Blender 5.2.1 LTS、单独生成的 402 点／800 面两骨三角网格**，实际运行默认 BMesh 与原生 capture→prepared。没有打开／保存任何 blend 文件或触碰用户 GUI。

| 真实步骤 | 新静态读取 | 新 prepare | 新 current 点／pose 矩阵 |
|---|---:|---:|---:|
| initial | 1 | 1 | 402／2 |
| stable_repeat | 0 | 0 | 402／2 |
| pose_5_lbs | **1** | **0** | 402／2 |
| raw rest 点编辑 | 1 | 1 | 402／2 |
| 有效权重编辑、和保持 1 | 1 | 1 | 402／2 |
| 局部面翻向 | 1 | 1 | 402／2 |
| mesh／rig 相对变换＋单位 | 1 | 1 | 402／2 |

每次静态读取实际含 402 rest、402 weights、两骨 rest、一次 topology。七次累计：7 capture／6 静态读取／5 prepare／2,412 rest＋weights／2,814 current／12 rest-bones／14 pose-bones／6 topology。独立复算差量与累计一致。

与直接原生 NumPy 读取对照，点／权重／骨矩阵最大差通常 0，相对变换／单位场景最大 `2.78e-17`；LBS 回读残差约 `1.03e-7 m`，不是 0，在既有守卫内。与保存的高精度合成 current 的差另为最大 `1.71e-7`，不混称逐位一致。

## 原生证据对静态复用的判定

真实 pose 更新同时产生 Mesh Object、Rig Object 和 Armature datablock 的 geometry dirty；因此实际会重读所选静态数据，**不能把 fake 的姿态零静态读结论写成真实 Blender 结果**。当前 prepared 确实复用。rest 点／权重／翻面测试出现 Mesh datablock 更新，但权重脚本显式调用了 `mesh.data.update()`，不足以保证所有原生编辑入口都能按事件区别。

本版保留保守复查，不以“LBS 位置吻合”推断静态权重没变；rest pose 下多种权重本就可给相同坐标。最大的实际成本缺口是细分所选字段复查和避免无谓 BMesh 全网格重建，交根深审后按真实工作量做下一次 helper 优化。此处没有提前刷模型分数或新增平台。

## 当前结论与待共同入口项

此次真实检查止于 **native capture→prepare**，脚本没有调用 native analyze／MLP；worker／stdio／MCP 薄入口尚未接通。真实大资产、非三角面 triangulate、bone-rest 编辑及完整来源生命周期还需共同固定版本核验。模型仍是原有有限合成域估计，不能因来源通过而宣称真实人物诊断、通用体积或损伤／修复能力已完成。

唯一后台进程 **PID 18044 已退出、returncode 0**，`process_exit.json` 为 closed；probe handler 与 host residency handler 已清理，**短独占窗口已释放**。

产品 SHA `653eaaa9ee3292a1a490ba4a01637e495977bd9f668e1c584c9649927cf92715`；本分支 135 源 fingerprint `7faa14ad6d967540df3cedb25465a16261c06189d61d440ca4e5122f8426133d`。单测、native 运行前后产品／专家／权重／数据字节未变。native 结果 SHA `61610ecbef91a7716adb9239885061eda3655fcff58dba46d8689ecbf632e56f`。

初次独立测试的两处 fixture 预期已修正：同名 replacement 需刷新 evaluated.original，旧 original 应被准确拒绝；来源包装器的 source_binding 与手工 patch header 本就不同。没有放宽产品校验来通过。源码/数据不变的已有专家与内核结果复用，未重跑历史大矩阵。

没有训练、GPU、Google／模型 API 或全局配置更改。自身 AL 未绑定、epoch 5／需重绑定，未借根句柄。结论为 **READY_FOR_INTEGRATION**，等待根协调共同固定版，先不修改共享文件或增加审批。
