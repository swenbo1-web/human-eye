# M4-B1：原始绑定与求值网格来源

2026-11-02。候选`9.7.2+20261102.skin.source.r1`，115运行源，摘要`aad9ffba6faaefc5d96e17577db0ee64212162a6d68e42df1f21553e3e912b00`。独立只读合同/worker/固定CLI已隔离安装并由当前Codex实调用。默认MCP/live/Hook不变；排期仅见[唯一主计划](PRODUCT_ROADMAP.md)。

## 来源和逐点回放

捕获保存文件当前帧的原始mesh坐标/三角索引、顶点组与逐点权重、rig原始rest/求值pose/原始通道、use_deform/包络乘法、rig/mesh变换及单Armature设置，再读depsgraph求值对象的结果网格。文件SHA、帧/子帧、文档epoch、两对象及原始数据实例、全部权重和几何、RNA前后摘要共同绑定来源；同顶点数/拓扑不是充分条件。

设A为rig世界矩阵，M为mesh世界矩阵，B=A⁻¹M，Dᵢ=PᵢRᵢ⁻¹。逐点回放`p′=B⁻¹ Σᵢ[(wᵢ/Σw)DᵢBp]`，每个索引与原生结果的绝对误差不超过预登记2e-5网格单位，三角索引/顺序一致；不按最近点重新配对。无权重点回放原坐标，但单列partial/unweighted，不能因零位移就认定绑定正确。

B是当前物体间坐标变换，不是另存的历史绑定意图。合同证明有限域中当前几何的同索引回放符合，不认证重合点的语义身份、不签发编辑对应或动作权限；SHA绑定字节，不证明作者意图。测试另用原生传播POINT索引标记核对，产品不添加或依赖该标记。

## 有限域

128顶点、256原始三角面、64骨、每点8条组记录、64组、场景32对象、512KiB；原始/求值mesh局部坐标绝对值≤10，刚性正行列式rig/mesh物体平移绝对值≤100。静态FK、默认继承/单段B-bone、原始骨位移0/尺度1，完整FK位置也须符合；旧FK/约束源码和定义保持。

只支持一个启用的Armature、确切rig、顶点组LBS。有权重顶点总和须在1±1e-6内，并按实际总和归一化；正权重组须属于启用形变的骨骼。无权重和空未用组分别处理。未知/非形变正权重、DQ、modifier包络、骨层包络乘法、mask、多/其他/禁用modifier、shape key、父级、linked、动画/driver、非刚性、非三角原面或拓扑变化拒绝。

骨层`use_envelope_multiply`也是权重影响来源，不能只检查modifier开关。语义见[官方Bone API](https://docs.blender.org/api/current/bpy.types.Bone.html#bpy.types.Bone.use_envelope_multiply)；实际5.2.1另有非中性/中性负例，均明确拒绝。本域仍是小规模、无对象父级的静态LBS，不代表大型角色、任意层级、IK/DQ或组合modifier已适配。

## 输出、入口和只读性

输出原始/求值世界点、位移、权重覆盖与完整计数，最多16条，先缺权重、再按位移。`assessment=source_facts_only`、`damage_classification=not_inferred`；未检查局部伸长/塌缩、体积Jacobian、碰撞、连续动作及可见性。“来源有效”不等于几何正常。

当前Codex固定CLI实读取：收缩资产8点/12面，双刚性骨Y轴±90°且各半权重，结果顶点落到Y轴，最大位移约0.353553390593声明米单位，回放残差约1.09e-8网格单位；另例7/8点有权重，顶点0无权重、位置不变且明确partial。此批取得坐标和来源，尚未自动定性损伤。两次0产品setter、不保存、图像0；约629ms的原CLI记录不是性能对照、费用或模型成功率测量。

新release的`admin/skin_source_entry.py`固定相邻bootstrap、解释器/release/115源；参数仅`--operator-profile <绝对路径> --output <新绝对目录>`。profile绑定binary/file及SHA、mesh/rig、当前帧/子帧和runtimeSHA，无动作或续期字段。原30秒含启动/捕获/回放/报告，16次终身读取；读前复核profile/源码/磁盘scene。transport复用原RigPoseProcess的single-flight、等待和自有worker清理；worker仅接受inspect/shutdown、严格原期限，无RNA setter/切帧/模式/保存/外部代码参数。

直接读`evaluated_object.data`，不调用to_mesh或分配/清理用户mesh。Blender5.2.1 LTS modifier结果Mesh可以is_evaluated=false且无original链接；求值对象仍链接原对象、结果mesh不同于原始mesh。实际RNA见证后采用对象来源关系，仍逐点/逐索引核验，不把临时Mesh ID标志当对应证明。独立入口不需要重启Codex，默认MCP未热更。

## 验收与纠错保留

公开脚本为`run_skin_source_preflight.py --builder/--controller`、`run_skin_source_checks.py`、`test_skin_source.py`及外部wrapper`fixtures/skin_source_rna_audit.py`，均在verification。原始证据根`verification/fixes/20261102_m4_skin_source`，机器profile/blend/原始日志不入公共Git。

- 最终`fixtures_r4`49资产，在源码`native_r5`与安装`installed_r2`同矩阵核验：18可观察，其中无权重2例partial；31拒绝。不累计复验为98种覆盖。含正常/单骨/混合弯曲/收缩、不同rest/父链、独立物体变换、毫米/子帧、无权重/空组、128/129点、256/257面、64/65骨、8/9记录、坐标10/越界与物体平移100/越界。独立NumPy按作者参数构造LBS，原生索引标记另验；支持例最大残差约2.10e-7，原2e-5门限不动。
- 源码和安装各6组真实来源/传输检查、6场景原始/求值RNA审计；错frame/mesh/rig、延长期限、move、第17读取拒绝。中性同进程权重0.5/0.5→0.25/0.75，输出点完全相同，旧source仍拒绝。变更来自固定测试actor，产品reader0setter、文件SHA保持；普通只读审计原始坐标/权重/modifier、rest/pose/骨标志、选择/模式、求值点/索引及主数据块数不变。
- 19新单测覆盖错点/错索引、同几何不同权重、source/实例/帧/文件、未知/非形变组、两层包络/DQ、strict bool、容量/期限/single-flight及无写API。完整127模块2115项：本地2112过/3条件跳过，干净Git暂存源码导出2102过/13跳过，额外10项仍为旧私有历史依赖，无新增跳过；旧约束43组在新安装保持。原112源仅版本身份更新，其余111及旧FK/约束文件字节保持；115源与安装一致，122成员wheel哈希/确定性验证。项目配置和82份旧封存manifest摘要保持，不冒称重哈希全部历史payload。
- 早期native_r1错误要求结果Mesh ID标志，原生EVAL_ID_WITNESS核对后修正对象来源判据，数值门限未放宽。原未知组例同时总和1.1，后将总和固定1以隔离未知组原因，期望仍拒绝。复审补骨层包络与中性负例，再补既定数值边界，新增前登记。旧夹具/日志/源码快照保留，未删失败或移门限。

下一M4-B2建立局部表面伸长、面积变化/退化事实及刚体/正常弯曲褶皱负例。不把大位移当损伤，不推断完整体积Jacobian，不开放骨骼/蒙皮修复。旧IK5失败、旧成本/整体发布和模型价值条件保持；正式模型试次及合格HE学习数据仍0。
