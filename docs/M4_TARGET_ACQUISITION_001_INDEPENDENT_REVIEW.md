# M4-TARGET-ACQUISITION-001 独立复核

日期：2026-11-15。最终作者提交 `03eb4e2971891dfe0160972cbcf974e3dcf1a21c`，A 产品提交 `cbbbd2611031f3c2d469280a71bcd410fb47447a`，基线 `fde0e9ab21fb6eaee1750befd64ad1bebdde2961`。

## 决定

**A 的单目标接线、全场遮挡保留和当前负例语义已核实；A 尚不作为完成验收的功能基线。B 未实现，正式性能矩阵未运行，本批没有新增收益成绩。** 独立源码复核发现一项 P2：目标相机在大平移、小尺寸条件下可能裁剪目标。先执行 [M4-TARGET-CAMERA-RELIABILITY-001](M4_TARGET_CAMERA_RELIABILITY_001_PLAN.md)，再恢复选择性采集。

旧 qualification=`not_realized` 保持：该固定样例实际没有完整可读见证，算法返回 unknown 正确。这个样例不合格与新发现的相机数值缺陷是两件不同的事。根规划时没有先证明输入至少有一张完整正向见证，造成了本次效能测量无法启动；这项实验设计问题由根规划承担。

## 1. A 实现了什么

相对固定基线共七个产品文件变化。明确单目标 `objects` 从入口传到宿主；在一个读取窗口内捕获目标、拟合六个目标视窗、补齐剩余场景。只有目标参加面片划分，其他物体作为遮挡物，所有三角形仍进入遮挡与绘制。未指定目标仍为旧全场路径。

所以 A 已经把“观察谁”的范围接通，但详细几何仍全采。实际 A02 为 14 对象、3474 顶点、6146 三角形，14 次网格展开/三角化。没有 B 的视窗剔除，不能称已经减少外围采集，更不能称全场扫视已经完成按需取数。

141 份源摘要为 `b7868c46119b2f5dcb3ca426e78a2ac9bb45b51167a01d323516c7707eb81e76`；隔离安装 `D:/he_m4_target_001/A/product`。这只是本批候选，不代表桌面默认部署。

## 2. 实际负例为什么正确

独立从 native wire 展开资源及变换，与实际 CAPTURE 逐值核对。目标 M4_Far_00 为 289 顶点、512 三角形、面积 1 的矩形，法向 −X；仅 LEFT 正向。Near 在 LEFT 方向产生严格正面积遮挡：

`73786983304225 / 9223372036854775808 ≈ 8.000000759959239e-6 m²`。

因此 `covered=0`、`complete_witness=null`、有限池未完成正确。API complete 仅表示调用完成。唯一实际 SCENE 图的 91559 表面像素、1127 边界像素与公开回包相符，但它是背面，不能算完整可读见证。没有实际 LEFT raster。

原始 producer audit 没有 NPZ 内容摘要；当前 NPZ 数组与实际交付 PNG、捕获及回包的一致性通过，不能因此补称 owners/depth 在生产时已有内容签收。本轮没有重栅格化深度赢家。

## 3. 新发现 F1 / P2：目标相机数值漏覆盖

`blender_host.py` 的 `_observation_target_cameras` 用局部差值拟合 XY 跨度，但输出全局 view matrix 时使用绝对坐标点积；大数消减使两条计算路径不一致。返回前只有深度范围检查，没有保证最终矩阵仍包含目标。

固定反例的局部点为 `(0, ±float32(0.0001), ±float32(0.0001))`，矩阵为恒等加平移 `(-877075496960, -55016382464, 494971027456)`；各元素均能由 binary32 精确表示。按当前捕获代码运算顺序得到的目标仍为有效非退化矩形，无遮挡。

唯一正向 LEFT 的最终矩阵经 Fraction 精确投影得到 NDC y=1.4452000066471393，核心分类为 outside_frustum。相同捕获顶点减共同原点后 LEFT 为几何 complete。**这是可达的数值漏覆盖/误拒，不是错误完整放行；真实 Blender 和 raster 表现尚未在本轮执行。** 最小修复应处理最终矩阵拟合或明确数值不足，不能修改覆盖容差来掩盖裁剪。

固定反例及来源见 [source/REVIEW.md](../verification/fixes/20261115_m4_target_001_review/source/REVIEW.md) 和 [camera_reachable.json](../verification/fixes/20261115_m4_target_001_review/source/camera_reachable.json)。初次有限探针 384 中有 14 个 accepted-but-clipped，随后只固定一个 binary32 可达反例，没有继续刷随机样本。

## 4. 本轮独立检查与作者记录分栏

| 项目 | 本轮实际独立执行 | 作者记录 / 未运行 |
|---|---|---|
| 源码 | 七文件及相邻绑定/缓存静态审查；固定 Git 字节纯相机与 exact coverage 反例；64 个深度区间检查 | 作者 target pure 29、旧 pure 17，不并入本轮分母 |
| 当前运行语义 | 保存 native wire、stdio、网格、精确遮挡和图片数组 36/36 | 新 Blender、raster、模型均 0；无独立重新光栅化 |
| 来源与账本 | 829/829 保存证据断言，766 路径；141 源五方同字节、346 Git 变更和 272 runtime 归档 | 这些不是 829 个产品场景测试 |
| 控制与性能 | 原时钟、字节、预算复算 | B、正式 12 槽、focal/rack 观察、完整缓存动态控制未运行 |

独立原始结果分别在 [source](../verification/fixes/20261115_m4_target_001_review/source/REVIEW.md)、[quality](../verification/fixes/20261115_m4_target_001_review/quality/REVIEW.md)、[identity_cost](../verification/fixes/20261115_m4_target_001_review/identity_cost/REVIEW.md)。各分母不混合成一个产品通过率。

## 5. 完整成本与历史状态

- A02 业务 request→reply 922.8983ms，完整 session 2778.8254ms；A01 失败 session 2105.2332ms 保留。嵌套时钟不相加。
- 实际 owned 启动 3、实际图片构造 1；B 0、正式 12 槽实跑 0。仅释放 5 个已证未构造预留，已构造 1 张成本保留。
- Host 业务请求/响应 100372/261682B，公开文本 7088B、PNG 3223B。真实 stdio 与 audit 的 1B 差异由 CRLF/LF 精确解释。
- A02 实际 MCP 退出有句柄证据；A01 实际 MCP 退出仍 unknown，不能用 wrapper exit=0 替代。缓存删除被平台拒绝的历史保留，没有绕过清理。
- 无新模型性能调用，模型 token/费用未运行；复核/协调成本未测。没有新原生对照。

## 6. 后续出口

先关闭 F1，保留普通尺度能力和旧遮挡负例。修复完成后，根复核才允许把新的混合正例/遮挡输入固定为下一批：先独立解析证明存在完整正向面及可排除外围，再以真实像素资格确认，之后只比较同合同 A 全采/B 选择采集。旧 001 不重命名为通过，也不拿新输入替换旧失败。

已仅为未来批次准备[一个固定新输入的解析说明](../verification/fixes/20261115_m4_target_001_review/quality/NEXT_CASE_ANALYTICAL_NOTE.md)：保留旧遮挡竖面，在同目标增加高处水平面，TOP 存在无遮挡面；Far11 在六窗均可排除。它尚无真实宿主/像素资格，不是本批收益，也不进入当前相机修复任务。

M1–M5 的完整顺序见 [统一路线](M1_M5_PROGRESS_AND_NEXT_PLAN_20261115.md)。M6 不在本线；本轮不改默认安装、不运行付费 API、不操作原资产。
