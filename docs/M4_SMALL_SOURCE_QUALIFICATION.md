# M4-B3a 小型原样来源准入与预检

本批完成唯一主计划要求的来源合同、独立回放、失效反例和完整读取成本资格检查。结论是：**值得进入固定文件、当前保存帧、有限小型来源的产品候选实现**。本批工具均在verification，不更改生产116源e6b55e91、原128点上限、旧拒绝、默认MCP/Hook或写入域；预检qualified不等于产品已支持。

本机证据根为`verification/fixes/20261102_m4_b3_source_qualification`。14472e7基线、85份旧封存清单、配置和原始作者文件保持；新准入边界在执行前登记，附加第25帧也先登记再制作。

## 为什么不能只提高上限

原样RiggedSimple导入快照有160点、188面、2骨及Z_UP→Armature→Cylinder父链；单一Anim_0动作同时出现在active action与静音NLA stash中。旧入口还会因parent、animation及原始通道非精确0/1拒绝。应验证父逆、局部/世界矩阵和动作slot实际影响，不能删动画、归零通道或仅扩大cap。

实际原始通道最大位移约4.77e-7、scale偏差约1.19e-7；矩阵最大Gram残差约4.77e-7、条件数约1.00000018。这两帧的偏差与导入数值误差相符，不支持把全部非零通道判为真实缩放，也不支持开放任意非刚性。所有原始值保留；数学中按四元数定义求方向、按权重总和重放，不是把源scale改成1或location改成0。

## 拟进入产品候选的最小合同

| 项目 | 有限边界与验证 |
| --- | --- |
| 来源 | 固定独占.blend、二进制与脚本摘要；原文件只读，当前保存帧/单位/mesh与rig角色固定；每包核对可信profile和epoch来源 |
| 规模 | 预检256点/256三角/16骨/16对象/父深8/32组/每点8影响，完整包≤512KiB；这些是新候选建议，旧生产128/256/64合同不变 |
| 对象层级 | 仅OBJECT parent；完整父引用、basis/local/parent_inverse/world、原始和求值身份及矩阵一致；无骨/顶点parent或未闭合依赖 |
| 骨骼 | 完整rest/pose/basis、端点和原始通道独立重放；默认继承、B-bone1、正定向近刚性；Gram≤2e-5、条件数≤1e4；非刚性、反射或病态分别拒绝/unknown |
| 坐标 | 保留原B1原始/求值坐标abs≤10、物体world平移abs≤100；不从有限值或矩阵条件数推出任意大坐标支持 |
| 蒙皮 | 单Armature、vertex-group LBS、完整权重/原点/面索引；DQ、包络、mask、其它modifier和shape key拒绝 |
| 动作 | 唯一匹配rig action/slot/channelbag、单layer/KEYFRAME strip；REPLACE、influence1、非tweak；NLA轨道全静音且不solo；数据及未生效轨道仍入源 |
| 插值与依赖 | 仅当前固定帧的exact-key/CONSTANT/LINEAR独立标量求值，路径白名单与原始通道一致；非精确key的BEZIER等保持unknown，不用原生evaluate自当真值；driver/constraint/linked/override/未知语义字段拒绝 |
| 时间与副作用 | 一个原30秒窗口、最多16个原请求；无frame_set/save/任意代码命令；读取、传输、分析、关闭及报告保存/发布/编码后期限检查，拒绝或unknown不能报成功 |

动画动作的准确RNA以实际Blender 5.2.1 build为准。ActionLayer只有name/strips，KEYFRAME strip只有type/channelbags；没有臆造layer influence/mix_mode。读取器固定RNA签名，包和检查器拒绝未知字段，不把单layer自动当成任意版本无混合语义。参考[Blender Action API](https://docs.blender.org/api/current/bpy.types.Action.html)；5.2完整页面抓取限制及实际RNA见证都保留。

这是一份待产品实现的合同，不把verification工具当正式可信执行边界。任意第三方自制packet、恶意同账户producer、任意活文档、未覆盖modifier和动画时序均未认证。

## 独立事实与对应关系

1. NumPy用完整父矩阵乘积与parent inverse、rest/pose/basis回放FK；用3D仿射逆矩阵重放`B⁻¹ Σ(w/Σw) P R⁻¹ Bp`，不调用生产算法作真值。
2. 动画独立求CONSTANT/LINEAR及精确key的当前帧值，对照原始通道；不通过切帧或调用Blender curve.evaluate产生答案。第一个key约0.9999988675，不能误当frame1的精确key。
3. 另直接读取原始GLB的POSITION、索引、命名权重、节点/TRS、IBM和动画轨道，以[glTF规范](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)与[旋转插值说明](https://github.khronos.org/glTF-Tutorials/gltfTutorial/gltfTutorial_007_Animations.html)独立重放。固定Y-up→Z-up转换`(x,-z,y)`，160点原始误差约5.96e-8，188面索引逐项完全相同、命名权重误差0。
4. frame25由测试作者在独占新副本仅设置一次当前帧并另存；网格、权重、rest和完整动作数据哈希前后一致，原GLB/import文件未改。reader没有切帧命令。该帧相对frame1最大顶点变化约2.713，覆盖了明显形变。

资格检查器与原生reader的来源、身份和矩阵回放分层核验：完整LBS成立不代替动作依赖完整；同一错误世界矩阵同时放进mesh/rig会让相对B不变，因此还须独立核对原始/求值世界矩阵与父链。

## 有限实测结果

| 验收 | 结果与限制 |
| --- | --- |
| 最终完整运行 | frame1三次＋frame25一次，均qualified、退出0、进程回收；冻结reader SHA 4626fb83…，检查器SHA c01eb9cc… |
| NumPy→native完整回放 | 160点最大LBS误差≤2.827e-7；FK最大≤4.56e-8；动作10曲线当前值误差≤9.01e-8；未放宽2e-5门限 |
| 原GLB→native独立见证 | 四包在两个固定帧最大误差≤3.21e-6<2e-5；这是两个静态时刻见证，非动画轨迹认证 |
| 完整成本 | 初始三次含启动/两读传及存盘/资格/关闭约0.722/0.740/0.710秒；第25帧约0.747秒。含最终REPORT发布最长约0.750秒；外层工具墙钟另记，不混用 |
| 数据预算 | 最大200959字节，小于512KiB；不是200.95KiB，也不等同于模型输入token或OS峰值内存 |
| 真实来源失效 | future key改变、父逆/basis补偿两测试actor均保持当前eval点逐字相同，source改变；旧源精确拒绝，新的自洽源仍qualified；测试actor1/2次写源字段与reader0setter分别计数 |
| 原生协议 | 错期限、frame_set命令精确拒绝；两个错误也占原slot，之后14读，第17请求不能越过16上限；没有续窗口 |
| 专项测试 | capture10、资格13、依赖合同20，共43项；每个反例匹配预定原因，正常/边界正例保持 |

2e-5是LBS/矩阵一致性接受窗，不是RNA坐标测量精度，也不证明健康、损伤、完整体积、骨骼意图或模型显著收益。三次初始运行只用于有限工程资格，不估计长尾百分位，不替代旧M2成本或正式对照门；未测OS峰值内存和真实生产资产广泛覆盖。

## 完成判定与后续

本批已具备实施一个有限固定文件当前帧候选的依据。下一项由唯一主计划安排M4-B3b：复用现有原生生命周期和几何算子，通过显式新来源合同接入，不放宽B1默认拒绝；产品读取器、隔离安装、原负例、来源失效和实际Codex消费仍须重新验收。

完整139模块2265项：本地2262通过、3项既有跳过；干净公共源码2252通过、13跳过，额外10项仍是旧私有历史依赖，没有新增跳过。509份公共Python文件与测试导出一致；原116运行源与基线Git、隔离安装和导出逐字相同，85份旧seal清单摘要与项目配置保持。新证据另行封存，原型失败和修正记录保留。

当前生产原样外部支持仍为0/2，真实生产资产0；预检只验证一个外部作者testing样本的两个固定帧。CesiumMan继续作为域外参照，通用NLA混合、BEZIER中间时刻、动画时序、大型角色、自动编辑和训练后置。没有重新打包或切换现有引擎。
