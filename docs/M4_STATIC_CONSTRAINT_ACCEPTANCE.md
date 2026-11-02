# M4-A2b：静态复制旋转的独立只读产品域

2026-11-02。候选`9.7.2+20261102.rig.constraint.r1`，112运行源，摘要`7b12f417e7d00ff676c41dcd9f76dd0a6fbbec5c7f1801696e044366accd4d03`。新增独立合同、worker、固定本机入口和隔离安装；默认MCP/live/Hook不变。排期仅见[唯一主计划](PRODUCT_ROADMAP.md)。

## 新增行为与有限范围

固定当前保存帧，观察单一全轴、全影响、WORLD/WORLD、REPLACE的Copy Rotation，目标必须是无父级、无约束、无动画/driver的本地Empty。约束须enabled/valid、AUTO Euler order、无offset/反向轴/骨subtarget/自定义空间。rig及其数据无动画/driver/对象父级，所有骨骼使用默认继承、单段B-bone、刚性rest/pose/basis；原始骨骼位移通道为0、尺度通道为1。rig和目标的世界变换须为正交、正行列式的刚性变换，可有平移。

新输出逐骨骼分开`input_channel`与`evaluated_local`，优先显示被约束骨骼，最多16条，保留全部计数与省略数。支持最多64骨、场景32对象、512KiB快照；65骨及域外配置明确拒绝，不移出测试分母。报告为姿态事实，`assessment=unassessed_no_rules`、`rule_registered=false`、`damage_classification=not_inferred`；本域尚未接入角色规则。原FK入口及其角色规则仍独立保留。

当前Codex实际通过隔离安装的固定CLI读取：Tip输入约20°，求值后的Y扭转约94.999999939°，头尾仍为(0,1,0)/(0,2,0)；非交换的物体/父级组合中，输入仍约20°，最终局部旋转约83.669918°。两次均0setter、不保存、0图像。它们证明新入口在当前Codex可消费，不证明模型整任务收益，也没有自动接入默认MCP或Hook。

## 来源合同与算法

复用A1原始rest/求值pose格式、父/rest相对矩阵及swing/twist数学，旧三份FK模块逐字节不变。约束域采用新的外层schema，绑定文件SHA、完整rig来源、rig对象basis、原始骨骼通道、目标身份/实例/通道/basis/求值世界矩阵、约束语义设置及RNA前后摘要；capture UUID不作为状态变化。目标、帧、文档epoch、实例、控制表示或已登记依赖变化，均不能复用该进程第一次读取的来源。

验证分两条：

- 被约束骨骼的世界旋转必须与目标世界旋转一致；其位置仍满足无骨骼平移通道的FK关系。
- 其余骨骼必须保持当前父pose/rest关系与原始basis的静态FK一致性，包括约束骨骼的后代。

随后计算根骨`R⁻¹P`、子骨`(R_parent⁻¹R_child)⁻¹(P_parent⁻¹P_child)`，分别报告输入和求值后的角度。不能要求被约束骨骼结果等于输入basis，也不能为了读出角度而跳过一致性检查。刚性矩阵容差2e-5、一致性旋转容差6e-5、原生端点相对容差2e-6；角度分支沿用预登记0.001°守卫。近180°swing或twist符号分支仍为unknown/partial，不能用0代替。

来源捕获只覆盖这一已证明的固定依赖集合，不扫描全场景的无关属性，不宣称任意rig的通用闭包。SHA绑定内容，不是来源真实性证明；生产信任还依赖固定启动器、模块和文件pin。当前通道与求值输出分开；动画/driver整体拒绝，不能把其已求值通道误称为作者常量。

## 有界入口和生命周期

`rig_constraint_process.py`复用原RigPoseProcess的single-flight、期限等待和自有子进程清理，只为新合同固定profile、worker及响应验证。profile固定Blender二进制及SHA、scene及SHA、runtime源码SHA、rig/目标/约束骨骼名和当前帧/子帧。没有policy、动作、任意代码或续期字段。每次读取复核profile、运行源及磁盘scene pin，原30秒包括启动/验证/诊断；最多16次读取。

worker仅接受inspect/shutdown，要求请求期限严格等于启动时原期限；关闭autoexec，无RNA setter、切帧、模式切换或保存命令。固定编译加载的只是经SHA校验的两份内部数学/合同源码，不提供外部代码执行参数。启动ready绑定真实PID、worker/数学/合同/profile/file摘要及原期限；未知Blender可写约束选项不静默忽略。本机已验Blender 5.2.1 LTS（构建9e2066aef7ef），不宣称其他版本兼容。

安装后的固定入口位于新release的`admin/rig_constraint_entry.py`，使用相邻bootstrap的确切SHA和runtime binding：

```text
--operator-profile <固定profile绝对路径>
--output <新的绝对证据目录>
```

只读无需动作授权表单。INPUTS、双快照、REPORT或FAILURE排他保存；错误不发出编辑命令，不改宿主审批设置。安装包和当前聊天默认MCP分别验收，不要求为本入口重启Codex。

## 验收与保留的失败

公开复现入口为`verification/run_rig_constraint_preflight.py --builder/--controller`、`run_rig_constraint_checks.py`及`test_rig_constraint.py`；外部观察wrapper在`verification/fixtures/rig_constraint_rna_audit.py`。本地证据根为`verification/fixes/20261102_m4_constraint_product`，factory资产、机器profile与原始日志不进入公共Git。

- 43个不同资产：15个支持场景，28个域外拒绝。最终源码`native_r3`、固定隔离安装`installed_r2`跑同一矩阵；复验不累计为86种覆盖。包含X/Y/Z、三维组合、非交换父/物体变换、rest roll、根约束和后代、64/65、四元数符号、子帧、毫米、对象平移与奇异swing。独立NumPy用作者rest/Euler构造完整矩阵，另用trace、Y轴投影及矩阵反对称项独立核对交付的旋转/swing/twist，不用候选角度生成期望。
- 域外包含部分影响、mute/disabled、轴/offset/空间/Euler设置、缺目标、多约束、rig/target约束或父级、非均匀尺度、原始骨位移、继承/B-bone、两端动画/driver、REST、IK及32/33对象边界。读取成功不代表这些域被支持。
- 源码及安装各有5组真实传输/拒绝检查；请求延长期限和move被worker拒绝，16次读取来源保持，第17次被阻断，错帧/目标/约束骨骼拒绝。6个场景的外部RNA审计在两端均通过，原始rest/channel、求值pose、对象/目标/帧/选择/模式前后一致，文件SHA保持。wrapper为测试仪器，普通精确worker另有完整矩阵。
- 原FK旧28组在新安装上通过，仍将约束/动画/driver等判为旧域unsupported。22新单测覆盖来源/实例/帧/文件变化、重哈希篡改、端点/目标/FK不一致、strict bool、512KiB、64/65、原期限/single-flight/16次与无写API。完整126模块2096项：本地2093通过/3条件跳过，干净Git暂存源码导出2083通过/13跳过；额外10项仍为旧私有历史依赖，无新增跳过。
- 初次原生矩阵在`bone_translation`负例发现：连接骨骼忽略非零location，basis位移仍为0，旧准入检查错误接受。`native_r1`及当时源码保存；最终外层合同补原始骨骼通道和严格0位移/1尺度，原夹具重测正确拒绝，没有移动门限或改写夹具。
- 补raw binding后，一个FK篡改单测先被更早的raw一致性守卫拒绝；将该负例的两份basis同步篡改，使它继续检验独立FK关系。未放宽产品检查。旧记录保留。

112源与隔离安装逐字节一致，119成员wheel逐项哈希验证且确定性重建；原109运行源中仅版本身份修改，三份FK及其他108份旧源保持。旧81份封存manifest摘要、项目MCP/Hook配置保持。A2a的5项IK端点失败仍是失败；没有开放IK、骨骼/蒙皮写入或训练，正式模型试次与合格HE学习数据仍0。后续按唯一主计划进入M4-B原始绑定网格、求值网格、索引和权重来源；旧成本与整体发布条件不改判。
