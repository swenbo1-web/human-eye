# M4-TARGET-CAMERA-RELIABILITY-001 独立源码与数值复核

复核者 `/root/camera001_source_review`。自身 AL assignment `70cfa06b-2a0d-4ada-94ea-48aae1c6e3a5`，current=true，父任务 `a7a6442d-90bc-4559-8dc2-726fd4a5885f` / rev1 / write720。固定 final `4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6`、产品 `691f7b78ed89ccf30df47847fc1e99ad51a1dc64`，基线 `03eb4e2971891dfe0160972cbcf974e3dcf1a21c`。

## 结论

本轮范围内**未发现新的正确性缺陷**。最小修复关闭了“拟合返回成功却不能可靠包含目标”的已证路径：原 binary32 可达极值现在明确 numeric_insufficient；固定普通控制继续可靠拟合，三个可支持矩形均保留完整几何候选。它是数值可靠性修复，**不是大坐标完整观察能力恢复**。

两个产品文件的修改范围与计划一致；实际 span、覆盖容差、六视角方向、renderer 和全采路径保持不变。独立数值验证没有执行作者 oracle 或数值评分器。真实 Blender、像素和完整 MCP 会话由主复核另线检查，本报告不替代这些证据。

## 1. 为什么新检查针对实际缺陷

原缺陷发生在局部 `(point-center)` 拟合与绝对 world view translation 的大数消减之间。新代码保留局部跨度，另外计算最终 view 行的平移 `T` 和 `shift = fl(dot(a,center)+T)`；以最终实际 projection 的 inverse_half_span 投影包络后才返回相机。

对每个屏幕轴 a，生产代码的正数向外总量覆盖以下量：

`Σ |a_i| (relative_extent_i + |center_i| + max|world_i|) + 2|T|`。

分别对应局部差值/点积、中心点积与平移、raster 的全局点积与平移。这里把**已经计算出的轴与矩阵系数**当作输入；不需要假设轴恰好等于理想无理正交基，也不借理想 camera 代替真实矩阵。

在当前 binary64 最近舍入、逐渐下溢模型中，三项乘积/归约与平移的各项累计误差可用远小于 gamma32 的有限 gamma 界覆盖；相减的误差也由 relative_extent 包含。gamma32 给分项叠加留有余量，两个平移绝对值覆盖构造 shift 和实际全局求值；32 个最小 subnormal 的绝对项覆盖有限运算中的下溢误差。正数 magnitude 的乘积与求和、局部端点加 shift、减/加 error 均向外扩一浮点值；最后投影乘法也向外取整。非有限端点与超出 [-1,1] 的结果明确退出，没有扩大 span 或覆盖容差。

`attention_raster.py` 的实际路径是 `vertices @ view[:3,:3].T + view[:3,3]`，再乘 projection 并加平移；XY projection 为实际对角系数。exact coverage 则将发布的两个矩阵系数转 Fraction 后精确组合。新包络同时考虑两者，不是仅检查一条近似的局部路径。深度仍沿原 whole-scene affine interval 计算；本次不把旧深度实现扩大为任意坐标域证明。

上述是源码误差分解审查。下面的独立离线区间检查提供有限输入证据，不将 384 个样本称为普遍数值证明。

## 2. 本轮独立执行的数值检查

`check_fixed_camera.py` 从固定 Git blob 提取实际 camera AST，先核 final/产品提交/作者树/安装相同字节，再执行。active_observation exact coverage 核心与基线逐字节相同。

独立 oracle 使用 Fraction 区间：每个乘法或加法节点同时包含精确结果和 binary64 舍入结果；枚举四个仿射项的全部二叉归约分组，再贯穿真实 view/projection 两阶段。保留“不发生中间舍入”的区间分支覆盖融合运算。这套检查**不用作者 Gamma6 公式、不调用作者 oracle**，也未运行 raster。

六个冻结输入结果：

| 输入 | 本轮结果 |
|---|---|
| reachable_binary32 | 专用 numeric_insufficient，未返回相机，能力未恢复 |
| origin_quantized_control | 精确 XYZ / 独立舍入区间均包含；1 矩形，LEFT 几何 complete |
| prior_target_fit | 六相机精确 XYZ / 独立舍入区间均包含；只作为相机控制 |
| prior_rotated_target | 六相机精确 XYZ / 独立舍入区间均包含；只作为相机控制 |
| ordinary_translation | 1 矩形，LEFT 几何 complete，矩阵与区间通过 |
| slender_translation | 1 矩形，LEFT 几何 complete，矩阵与区间通过 |

五个返回相机的输入各检查 4 点×6视图=24 个点视图组合。没有把几何 complete 当作真实像素完整见证。

旧 384 输入只按根原探针的 seed=101511、原范围/次数重建，逐点核对保存 replay 的输入；没有后续 64-box/negative-X 搜索，也没有新随机范围。当前 helper 得到 273 接受、111 numeric_insufficient；273 个接受结果的精确 XY/XYZ 裁剪和独立二阶段舍入树 XYZ 包络失败均为 0。

| 原坐标 magnitude 档 | 接受 | numeric_insufficient |
|---|---:|---:|
| 0、1e6、1e8 | 各64 | 各0 |
| 1e10 | 42 | 22 |
| 1e11 | 23 | 41 |
| 1e12 | 16 | 48 |

111 个退出是能力范围代价；不能把它们记作 111 个成功观察，也不能把无错误接受等同于支持全部 384 输入。原旧版 14 个精确 XY 裁剪及作者记录的 67 个 Gamma6 XYZ 不保证分别保留；本次未重复运行作者 Gamma6 口径。原纯 tight-bounds y=1.4452 与实际 outward-directory bounds y=1.2560 由不同输入边界产生，不能交换使用；实际值由另线原始捕获审查。

## 3. 错误映射与执行状态

`_error_result` 只匹配：精确本地 BlenderHostError 类型及完整专用字符串；或者 HostRemoteError 内精确普通 dict、恰好 type/message/mutation_uncertain 三字段、专用类型/字符串及布尔 False。普通同文 ValueError、其他异常子类、额外 receipt 字段和 mutation_uncertain=True 均不被新分支改写。

原 host transport 已对 apply/native mutation 或 mutation_uncertain 路径作不确定执行处理；此专用相机错误产生在读取阶段。新 metadata.update 只更改 status/reason/observation 标识，不删除 executed/verified/operation_status/提交账本字段，保留 isError 和 automatic_retry=False。

独立 `check_error_boundary.py` 执行固定源码的真实 `_error_result`、`_request_error_fields` 与 `_tool_result` serializer；仅注入保存的请求字段与替代 telemetry recorder，不启动 server。6 种边界×executed False/True/None 共18项通过：状态与提交/unknown 信息逐值保留，禁止重试保持，正确匹配转 numeric unknown，其余仍 error，仅交付一个文字块、0图片。它不模拟真实动作执行，不替代 live MCP 测试。

## 4. 实质优化与剩余方向

静态工作减少成立：旧 helper 每视图每点为两个轴分别重算三维 point-center，六视图总计36N次标量相减；现在相对顶点只算一次，3N次。点积数量仍为12N，投影范围复用，后续不再额外遍历 pair-list 生成同一边界。新增误差检查是每视图两个轴的固定工作，不新增全场 capture/hash/raster；代价是保留一次 O(N) 相对顶点列表。

本轮没有重跑计时。作者冻结微测的4点+约6.7µs、289点约−38.66%由成本线另审；本源码分析只支持“删除了重复运算”，不自行宣称完整任务收益。无需为凑优化次数再做一轮相机微调。

未来若真实任务要求恢复本次拒绝的大坐标能力，共同局部参考需要贯穿几何/覆盖/raster 表达，或有具体证据支持更紧包络；这不属于本次最小修复的必做项，也不应阻塞正常尺度的选择性采集A/B。

表述注意：新版极值“0主capture”只能表示未形成完整主捕获回包/保存记录。调用 camera 前已经读取目标几何，不能解释为零网格读取；成本应由实际宿主事件核对。0 raster/图片/见证可另由运行证据成立。

## 5. 范围与产物

独立脚本首跑均通过，无新增 fuzz/Blender/图像/模型/默认部署调用；未改作者工作树（终检干净）、安装、原证据或竞争分支，未提交 Git。产物为 `NUMERIC_RESULT.json`、`ERROR_RESULT.json` 及两个独立检查脚本。作者29/17/16/16等纯检查计数不并入本轮分母，真实六槽/七帧及端到端成本不在本报告的实际执行范围。
