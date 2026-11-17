# SOURCE-REGION-001 算法、局部相机与发布字节复核

2026-11-17。固定作者交付de884a2a44557fb3d01407c5e7c2883cc4aa749c。审阅产品R0、R0F和R1源码及现存实际原件，接受修正后的局部相机、源subset量测和当前R1的producer proof。源码与保存数学检查11215项通过，另有34项独立proof行为控制及3项发布窗口对照通过。

本轮根任务12549336-db64-4fd0-b8ae-66c7a0f3fbbf revision1已显示为当前parent。本持续子agent的固定历史assignment仍归旧任务740，current=false，已回报根。此复核按根当前明确委派执行，未修改任务记录或借用其它句柄。

## 实际执行范围

source_math.py读取原始native WIRE，复用前轮根独立捕获解码函数重建实际资源与世界坐标。没有导入作者oracle或作者保存检查器。全部20份成功source_region结果及2份whole_objects控制按其当前capture、源面与源点重新验算。安装R1的纯准备、M3精确距离及源归属函数另有定向调用，未执行观察raster。

proof_controls.py在隔离临时目录运行安装R1的实际SceneObservationImages，生产raster替换为固定64px合成数组。程序独立编写，不调用作者测试fixture或测试执行器。封存初稿class仅用于复现已披露的publication反例，未接入运行安装。

新Blender、MCP、生产raster、模型和付费API调用均为0。合成PNG／NPZ编码单独计入下文。

## 区域与整对象的数学差异

| 范围 | 独立精确距离平方 | 实际距离 |
| --- | --- | --- |
| 前4源三角到B | 25/16 | 1.25 |
| 前4源三角到C | 137/16 | 2.9261749776799064 |
| 整对象6三角到B | 1/1024 | 0.03125 |
| 整对象6三角到C | 2305/1024 | 1.5003254855197254 |

独立算法从全部选中源点建立逐轴分离下界。三角内部是顶点凸组合，因此这个下界覆盖全部连续表面。另求能达到下界的源顶点及参考平面点，形成精确最小距离证明。前4面／子集0、1、2、移动与恢复均有独立达到点。100位Decimal开方的正确binary64舍入等于公开距离。

区域最近点为源顶点1，参考平面最近点位于其第二源三角内部。公开nearest_witness_source的三角与顶点集合逐项由另一套三维Gram坐标解重算吻合。compact三角索引经过submesh_to_source_vertex_indices返回后逐行等于实际capture原三角，未将局部行号误作全场或原生polygon编号。

两个whole_objects控制按各自binding的A／B顺序读取真实selected capture，确认距离来自未选斜翼，其结果与区域量测不同。

## 私有exact holder

surface_proximity.py相对原接受版本的变化为清除遗留witness_points，并在已计算的_witness之后保留同一exact点对。坐标仍位于原内核的整数局部参考系，origin和factor由既有pair传递。

本轮直接调用安装R1内核，将holder预置为stale，两个参考对象的调用均生成新的点对。独立验证origin+point/factor等于公开世界点，factor为8，区域点为(6,0,0)，B点为(12,0,-8)，C点为(28,0,-8)。每个exact点的源三角与源顶点集合由独立Gram法重算，与_witness_sources相同。

_contains_exact另有500组平面、反绕序、共线线段及单点控制，全部与独立成员函数一致。该代码只重新验证已有点的归属，没有新增一次最近距离求解。

## 首次R0相机错误及R0F修正

两份qualification_R0原件的距离和源映射正确，但局部fit合同确实未成立。SCENE跨度49.780317395532954米，实际选中样本13像素。独立检查使用每张实际view矩阵的两条XY轴，求选中顶点相对选区bounds中心的最大投影跨度，再核原1.1方形padding。旧R0六方向都不符合该局部fit。

修正后的R0F／R1中心为选中6点bounds中心(35/8,35/8,17/16)，SCENE跨度1.1667261889578036米。全部18份修正结果的六相机均符合选中顶点拟合，所有选中点处于实际NDC XY内部，11个对象各8个AABB角点处于实际near／far深度范围。原始full几何继续作为遮挡数据。正式完整区域为26212实际样本，三面子集为23404，旧13像素记录保留。

该核查验证了局部拟合与深度范围。任意非平面曲面的完整可见性仍按当前结果保留unknown，不能从选中面各有像素推导整个表面完整可见。

## producer proof 与不可变编码字节

独立审阅与控制确认当前顺序为NumPy编码到BytesIO、取得immutable bytes、固定expected SHA、写盘、读回磁盘并比SHA。只有该阶段成功才建立私有proof。proof绑定原frame对象身份、原元数据signature及不可变数组元数据tuple，后续每次validate仍先读NPZ磁盘字节核SHA，再核当前内存buffer和mapping全部内容摘要。

34项独立控制覆盖以下行为。

- 原producer同一frame首次和重复验证均0解码、1次fresh reuse。
- foreign适配器、shallow／deep副本、仅保存frame、路径alias、frame元数据变化均进入原NPZ解码。
- 从NumPy alias修改原数组，或者更改dtype、shape、patch／owner映射，都使proof失效，原路径拒绝不一致数据。
- 实际PNG／NPZ字节替换仍被每次读盘核验拒绝。
- 调用者协调更新NPZ字节、公开hash和buffer时使用原完整decoder。该情形可在原保存帧契约下通过，fresh reuse仍为0。
- 恢复原内容及元数据后，同一原frame重新满足私有proof。
- 旧默认适配器继续decode，原路径未被切换为全局信任缓存。

独立publication拦截器在首次NPZ read前替换为另一个有效archive，只翻转一个color字节。实际对照结果如下。

| 版本 | 结果 |
| --- | --- |
| 旧默认解码 | frame返回后校验拒绝frame_array_payload_mismatch |
| 封存early候选 | 错误接受，复现原披露窗口 |
| 当前R1 | frame返回前拒绝actual_frame_array_bytes_required |

这个对照实际通过各自render_view和validate_frame运行。没有修改作者封存、安装源码或用户资产。

## 合成成本与本轮检查器错误

最终proof成功执行计数为6组合成buffer、6次PNG编码、10次NPZ编码和28次np.load，生产raster调用0。另有一次本轮初稿失败，在owner_mapping_identity变化时误预设0次解码，实际解码后拒绝。原proof_controls_R0.py及PROOF_ERROR_R0.txt保留。该失败前缀的3次PNG、3次NPZ和25次decode由原控制顺序与断言位置重建，未独立profile整个失败进程。两次proof运行的编码合计9次PNG、13次NPZ，decode计数最终28次，失败前缀重建25次。

source_math初版扩展whole_objects验收时误预设capture对象顺序等于A／B调用顺序。到C的原capture顺序为C、A，调用binding顺序为A、C。source_math_R0.py及SOURCE_MATH_ERROR_R0.txt保留，最终按绑定name解析各自源对象。此更正只影响独立checker，产品没有修改。

数学程序先后执行两次通过版本，中间一次扩展后失败。两次通过各调用2次精确内核，共4次纯距离重放，图像构造0。没有以重放成本替换正式实测成本。

## 结论与未运行项

通过所选连续源三角集合与整对象不同距离、源见证数学、修正后的局部相机范围、exact holder复用及当前R1发布proof。旧R0局部fit失败与early publication失败分别保留。当前审查未发现阻止该有限候选采用的实质算法错误。

帧像素逐字节质量、受控来源安装身份、原期限与完整成本由根其它独立复核分别验收。真实骨骼资产原生至求值的来源映射、实际当前姿态与专家接入仍需具体任务证据。
