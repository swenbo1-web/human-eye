# M6-SHAPE-PAIRS-001 局部凹陷配对与恢复结果

2026-11-14。唯一工作树为 `C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe`，分支为 `codex/m6-model-selection-001`。本批从 `8a99c344caf4560ee87fbb9f7540bf67ff3f2469` 开始，执行规划合同 `cf81e1e74a358f52c3ef3223f0807a22ae1661da` 中的 `docs/M6_SHAPE_PAIRS_001_TASK.md`。计划、生成器和唯一方法在实际生成前固定于 `ce5b2fd38e0a362ecc90df03586dbc139c9dc8ef`。

## 交付判断

六个局部凹陷与一个未损坏控制已生成，恢复标签、源 ID、原拓扑与完整可读副本均可用。七例属于一个资产、一个区域和一个中心的开发机会探针。原始未扰动网格只承担合成恢复参考，原有美术质量尚无验收标签。

唯一双调和基线在六个损坏样本上全部增大恢复误差，并使正常控制产生 5.436319 mm 的区域 RMSE。338 个自由顶点在每例中均被改动，真实损坏仅覆盖 19 或 47 点。本批淘汰这项纯位置双调和重建作为该组数据的修复方法，保留保持不动的比较结果。当前证据支持进一步研究正常点保持与逐点修正，学习方法的有效性仍待验证。

全部损坏与修复端点的有限接触查询完成，新增额外接触均为零。本组数据未展示恢复精度和接触约束之间的冲突，接触结果无法解释或抵消形状误差。

## 来源、配对和划分

- 原资产为 `D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend`，SHA256 为 `614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d`。
- 读取既有冻结 world 网格，共 27,304 点、53,264 三角面。统一允许域含 410 点，其中边界 72 点、自由点 338。统一接触影响域含 898 个 incident 三角面。
- [DATA_INVENTORY.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/DATA_INVENTORY.json) 记录三个源数据文件的字节数和 SHA256。坐标采用已保存的 binary64 米制 world 坐标，顶点、三角形和源 polygon ID 保留。附加核验确认参考坐标、三角形、polygon 映射和允许域与原始输入一致。
- 全部七例归入原资产 SHA256 对应的单一 `asset_group`。development 含七例，train、validation、test 均为空。独立资产数为 1，跨资产泛化尚未评价。

中心固定为源顶点 `24205`。沿原始选区边长度到边界的最短距离为 `D=0.04692432699433448 m`。支持条件为 `d<r`，权重为 `w=(1-(d/r)^2)^2`，位移为 `-a*w*n`。`n` 来自中心原始 incident 面的面积加权法向，数值为 `[0.8354787250, 0.4731384894, 0.2794910908]`。其与中心相对区域质心向量的点积为 `+0.0182627411 m`。两个支持域中，中心方向与各原始支持点面积加权法向的最小余弦分别为 0.619248、0.210387，均为正，因此本组负法向扰动可解释为局部内凹。

|样本|r/D|a/r|半径 mm|最大实际位移 mm|真实支持点|实际损坏 incident 面|
|---|---:|---:|---:|---:|---:|---:|
|sample_00 正常控制|—|0|—|0|0|0|
|sample_01|0.35|0.05|16.423514|0.821176|19|59|
|sample_02|0.35|0.15|16.423514|2.463527|19|59|
|sample_03|0.35|0.30|16.423514|4.927054|19|59|
|sample_04|0.55|0.05|25.808380|1.290419|47|126|
|sample_05|0.55|0.15|25.808380|3.871257|47|126|
|sample_06|0.55|0.30|25.808380|7.742514|47|126|

原始边界、外部顶点与拓扑逐例保持。[LABELS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/LABELS.json)、各 `*_reference_displacement.npy` 保存恢复标签，图像和完整几何留在本机 private 目录。

## 方法与标签隔离

保持不动直接返回观察坐标。唯一修复函数为 `method.reconstruct(abnormal_vertices, triangles, allowed_region_ids)`，七例传入相同允许域，通过同一入口执行。函数只导入 NumPy 和 time，函数内部无文件读取。观察坐标与拓扑在调用期间设为只读，并核验调用后内容一致。

生成器和评价器可读取参考。修复函数仅接收异常坐标、原三角拓扑和统一允许域。中心、半径、幅度、实际支持、case ID、参考内部坐标、逆位移、参考 Laplacian 和参考因子分解均未传入。这里采用代码依赖与显式三参数调用隔离，生成和评价与方法运行在同一个 Python 进程。

在全网格原始邻接图上，令 F 为允许域去除边界后的自由点，R 为 F 与其一环邻居，C 为 R 与其一环邻居。固定 C 中 F 以外的观察坐标。所有 case 都得到 |F|=338、|R|=403、|C|=480，固定列 142。883 个 incident 原三角形用于装配 R 行。

异常输入上的 cotangent stiffness 矩阵 K 使用每个对角半余切权重，保留负余切。对角质量 M 的每项为相邻面面积之和的三分之一。求解固定位置约束下的能量

`min ||M_R^(-1/2) K_(R,C) X_C||_F^2`。

使用 `numpy.linalg.lstsq(B_F, -B_fixed X_fixed, rcond=None)` 直接求解三个坐标列。运行前固定了算子、质量、边界邻接行和求解器。该离散能量属于常用平方拉普拉斯能量家族，纯位置插值会平滑原有细节，固定边界也不足以使未扰动输入自动成为该能量的极小值。[libigl 能量最小化与双调和曲面说明](https://libigl.github.io/tutorial/#quadratic-energy-minimization)

## 恢复误差

下表单位为 mm。保持不动等同于损坏输入误差。恢复比例定义为 `1 - 修复RMSE/保持不动RMSE`，负值原样保留。正常控制的除零比例和空支持域指标在 JSON 中记为 null。

|样本|保持不动区域 RMSE|修复区域 RMSE|保持不动支持 RMSE|修复支持 RMSE|区域恢复比例|
|---|---:|---:|---:|---:|---:|
|sample_00|0.000000|5.436319|—|—|—|
|sample_01|0.079352|5.451970|0.368616|8.356050|-67.705971|
|sample_02|0.238057|5.481302|1.105848|8.480232|-22.025205|
|sample_03|0.476113|5.518017|2.211696|8.609785|-10.589716|
|sample_04|0.191599|5.490881|0.565895|7.926170|-27.658207|
|sample_05|0.574797|5.601699|1.697686|8.294581|-8.745531|
|sample_06|1.149593|5.763490|3.395371|8.798895|-4.013503|

恢复比例列使用无量纲小数，例如 -67.705971 对应 -6770.5971%。原始区域平均边长为 `0.006893660955022447 m`。正常控制修复后的归一化区域 RMSE 为 0.788597 个平均边长，sample_06 为 0.836057。

[RESULTS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/RESULTS.json) 对每例、每个方法均保存 410 点区域和真实支持域上的 RMSE、p95、最大误差及各自的平均边长归一化值。r/D=0.35 时仅 19/410 点受损，比例小于 5%，因此保持不动的区域 p95 为零，应结合支持域误差解读。正常控制修复后 p95 为 9.704101 mm，最大误改为 10.877914 mm。sample_06 修复后的区域 p95 为 10.452940 mm，最大误差为 11.091079 mm。

## 质量、保持约束和接触

所有 case 的修复实际改动 338 点，实际 incident 面数为 741。72 个边界点和全部外部点逐位保持，原拓扑与 ID 映射保留。对统一 898 面、1,386 边的局部评价，损坏和修复均未产生零面积面或相对参考的法向点积负值。

正常控制修复后的面面积比 min/p05/median/max 为 `0.489430/0.534721/0.855575/1.201392`，边长绝对相对变化 p95/max 为 `0.390311/0.514111`，面法向夹角 median/p95/max 为 `9.333970/20.920739/32.954326°`。sample_06 修复后的面积比中位数为 `0.840863`，边长绝对相对变化 p95/max 为 `0.412840/0.568919`。可见的表面收缩与细节丢失同这些数值一致。

接触评价器逐字节核对为 002 提交版本，统一使用 410 点允许域的完整 898 面闭包。每例分别评价参考到损坏、损坏到修复，共 14 次 evaluate、28 次端点查询。全部 `query_complete=true`、unresolved=0，新增、移除及改变既有额外关系均为零，after extra pairs 均为零。原网格全局有 10 个既有退化面，相关候选对均由严格 AABB 分离作出判定。本批接触含义限定于有限端点三角形关系，运动路径、实体包含和间距尚未评价。

## 求解和独立核验

七次求解矩阵均为 403×338，rank 均为 338，条件数约 149.24–149.83。正规方程相对残差约 `8.30e-15` 至 `1.06e-14`。[verify.py](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/verify.py) 用余弦定理和独立边聚合重装配已有输出的驻点条件，最大残差为 `1.0642789502576272e-14`，核验阶段增加的算法求解次数为零。

独立核验还采用稠密最短路核对生成器的堆最短路，标量方式核对误差统计，核对每例标签支持和位移，并将 14 个完整 OBJ 全量读回比较顶点与面。[VERIFICATION.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/VERIFICATION.json) 记录 499 项检查通过，其中 410 项属于最短路顶点检查。该检查数量的统计单位是程序断言。

浏览器使用独立临时 profile 运行本机无头 Edge。HTML 初始化并绘制成功，14 个状态选项均完成初始化，实施者已查看截图，临时 profile 已清理。拖动旋转和滚轮缩放的人工交互尚未测试。

## 实际图像与可读副本

下列路径均位于当前工作树。所有比较使用实际源三角形、深度测试和共同相机尺度。局部显示 488 点、898 面，其中 748 面完全位于允许域，150 面跨边界。固定视角相对参考中心法向倾斜 45°，detail 使用共同的中心 ±0.036 m 窗口。

- 完整局部对照为 [COMPARISON.png](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/COMPARISON.png)，2784×990。
- 放大对照为 [DETAIL.png](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/DETAIL.png)，2784×990。
- 可旋转查看器为 [VIEWER.html](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/VIEWER.html)，内嵌全部局部状态，外部依赖数为零。
- 浏览器绘制证据为 [VIEWER_BROWSER.png](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/VIEWER_BROWSER.png)。
- 完整 world OBJ 为 [reference.obj](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/reference.obj)、[sample_01_abnormal.obj](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/sample_01_abnormal.obj) 至 [sample_06_abnormal.obj](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/sample_06_abnormal.obj)、[sample_00_repaired.obj](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/sample_00_repaired.obj) 至 [sample_06_repaired.obj](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/sample_06_repaired.obj)，共 14 个唯一几何副本。控制输入与 reference 相同。
- NPY 包含参考、七个观察输入、七个修复输出、七个参考恢复位移、原始 triangles 和 source_polygon_ids。OBJ 的顶点顺序对应原始 source vertex ID，面顺序对应原始 triangle ID，OBJ 索引为该 ID 加一。polygon 对应关系由 [source_polygon_ids.npy](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/private/source_polygon_ids.npy) 给出。
- [EVIDENCE_MANIFEST.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/EVIDENCE_MANIFEST.json) 保存交付脚本、报告、数据清单和所有 private 产物的字节数及 SHA256。完整几何、恢复标签和图像均存放在本机 private 目录。

## 成本与运行记录

科学主运行仅一次，七例使用相同固定方法。导入完成后到结果发布前墙钟为 36.381615 s，CPU 为 34.437500 s。读入和来源检查 0.186541 s，生成 0.032994 s，七次方法调用合计 0.684561 s，其中装配 0.184537 s，最小二乘求解 0.067012 s，OBJ 导出合计 1.159048 s，接触评价 30.506931 s、CPU 29.296875 s，实际图像与 HTML 产出调用 2.100215 s。接触共尝试 172,576 次精确对判定。结果和日志写出 0.003122 s，主程序到发布完成为 36.387146 s。

后续独立核验墙钟 5.122256 s，其中浏览器检查 2.763934 s。各子阶段嵌套于对应总区间，不能把子项再与总项相加。QA 后 private 文件合计 59,666,920 字节，单例统计到的选定 NumPy 矩阵字节为 4,184,752。峰值 RSS、含导入及子进程的完整 CPU、Agent 总耗时缺失。坐标与质量指标计算包含在主区间，邻接和域准备包含在方法区间，这些步骤的独立耗时缺失。当前计时只提供单次运行记录。

元数据整理首次使用结果摘要字段名读取生成标签时出现 `KeyError: max_damage_displacement_m`，已改为生成标签字段 `max_actual_displacement_m`，事件保留于 [RUN_LOG.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/RUN_LOG.json)。生成、求解和接触评价的次数保持上述记录。完整成本见 [COSTS.json](C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_shape_pairs_001/COSTS.json)。

本批待评模型推理调用、训练、付费 API、新 Blender 进程及 M5 写入计数均为零。

## 剩余缺口与唯一条件候选

数值求解已经达到固定目标的驻点。本次纯位置平方拉普拉斯能量缺少正常形状保持项，统一可疑区域也缺少逐点损坏识别机制，导致全部自由点随重建被修改。本批仅实现了重建函数，独立损坏定位器的性能尚无实验结果。当前上下文约束允许多种内部形状，参考曲面中的细节需要额外的恢复先验。三维原始网格已支持该曲面表示，本轮失败无需归因于平面高度图近似。

只保留一个条件性学习候选，即局部网格消息传递残差回归器。输入采用观察到的局部坐标、边和邻接关系、统一允许域与固定上下文，输出每顶点三维修正，边界与外部输出强制为零。正常控制以零修正监督，逐点残差监督同时约束未受损内部点。该表示直接利用现有三维拓扑和逐点标签。网格消息传递已有公开研究依据，其在本任务上的收益需要单独验证。[MeshGraphNets 原论文](https://arxiv.org/abs/2010.03409)

进入该候选的训练验证之前，需要多个独立资产或独立来源区域、多个损坏中心及各自的未损坏控制。按资产和派生链先划组，再确定训练和验证数据规模，确保同源变体留在同组。评价应同时要求受损点恢复和正常点保持，并沿用完整影响面端点接触检查。当前单资产七例提供管线与机会证据，候选的训练、架构收益和泛化验收仍未开展。本批提交后等待规划聊天独立复核。
