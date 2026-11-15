# M4-TARGET-ACQUISITION-001 — 独立源码复核

复核者：`/root/target001_source`，自身 AL assignment `ee9361c2-ec5d-4d32-8a63-845d1f35dbb1`（current=true），父任务 `cd683dda-67f4-4252-aa0f-83be9a1e9627`。复核对象为基线 `fde0e9ab21fb6eaee1750befd64ad1bebdde2961` 到最终 `03eb4e2971891dfe0160972cbcf974e3dcf1a21c` 的七个产品文件；A 产品提交为 `cbbbd2611031f3c2d469280a71bcd410fb47447a`。未修改作者树、安装、原资产或竞争分支，未提交 Git。

## 结论

发现一项可复现 P2 数值正确性缺口：新 target camera 的 XY 拟合使用局部差值求跨度，但最终发布的全局 view matrix 平移项存在大数消减；返回前仅验证深度，没有验证实际输出矩阵仍包含目标。大平移下，一个可由 float32 局部顶点及 float32 平移矩阵生成的有效非退化矩形，其唯一前向视图被误判为 `outside_frustum`。这是相机拟合造成的漏覆盖/误拒，**不是错误完整放行**。覆盖核心仍保守返回 unknown。

其余本轮重点的静态合同核查未发现另一个已证缺陷。当前源码明确只实现 A 全采，没有 B 视锥剔除；作者登记的实际 A 案例仍为 `not_realized`，不得以本复核替代 B 或端到端收益验收。

## F1 / P2：已接受的 target camera 无法包含可表示目标

位置：作者树 `human_eye_plugin/blender_host.py:551` 的局部差值跨度、`:564` 的全局 view translation，以及 `:573` 只检查深度的返回前路径。

固定最小反例（详见 `probe_camera_reachable.py`、`camera_reachable.json`）：

- local 顶点为 `(0, ±float32(0.0001), ±float32(0.0001))`；面为 `[0,2,1]`、`[0,3,2]`，法向 -X。
- world 矩阵是恒等旋转加平移 `(-877075496960, -55016382464, 494971027456)`。矩阵及 local 顶点的全部元素均可由 IEEE binary32 精确表示。
- 使用现 `_resident_capture` / `_capture` 相同的 `sum(matrix[r][c]*p[c]) + translation`、再乘单位比例的顺序生成 binary64 world 点。
- 独立载入固定源码的纯覆盖核心，将目标识别为 **1 个有效矩形**；所有遮挡物为空。
- 唯一前向视图 LEFT 的实际输出 binary64 矩阵，按 Fraction 精确投影得到最大 NDC y **1.4452000066471393**，目标超出 `[-1,1]`。产品分类为 `outside_frustum`，无完整几何候选。
- 将同一份捕获 world 点减去共同原点，保持相同量化后矩形，LEFT 分类变为 `complete`、`first_blocker=null`。其余视图两组都为 back_facing/edge_on。

这不是外部任意 binary64 点冒充 Blender 输入：上述 local 和 matrix 均进行了 binary32 往返相等断言，世界变换重现了产品代码顺序。未启动真实 Blender，因此实际宿主操作、光栅图片表现仍是未运行；反例已闭合到实际 camera helper 和实际 exact coverage classifier。

机制：跨度基于 `(point-center)`，但 view translation 由 `-dot(axis,eye)` 构造；两种浮点求值路径在巨大原点、小目标条件下不等价。当前 `target_vertices_checked` 只说明顶点用于跨度计算，不证明输出矩阵逐点拟合通过。深度区间边界不覆盖 XY。

建议最小修复：在同一函数内基于实际发布矩阵确保目标 XY 拟合成立，或者在不能可靠表达时明确返回数值不足原因；无需本批重构整个 renderer。验收保留本固定反例及原点控制，禁止仅放宽 exact coverage 容差而把被裁剪目标变成完整。若选择精度不足退出，应明确区别于真实 `outside_frustum` 场景原因。

## 本轮实际执行

1. 七产品文件 diff 与相邻绑定/驻留缓存源码阅读；最终作者树 `git status --short` 为空。
2. 从指定最终 Git blob 提取 camera helper 的 AST，确认执行来源与作者树和 A 安装逐字节一致；执行对象不来自 Python 字节码缓存。
3. 固定种子、有限 **384** 个纯函数目标拟合探针：384 接受、0 拒绝、14 个实际输出矩阵裁剪了目标。该探针用于定位，不是收益/真实场景测试。全部记录保留在 `camera_probe.json`。
4. **64** 个 affine interval 框的 Fraction 角点极值检查全通过。该结论仅限这些样本，不宣称一般数值证明。
5. 收敛到上述 **1 个** binary32 可达固定反例及 **1 个**平移到原点控制，使用固定源码 exact coverage 核心。未继续扩充随机搜索，也未用反例修改作者预登记 fixture。

新 Blender 进程 0、raster 0、模型调用 0。没有执行完整产品回归，也没有触碰 live MCP、真实用户资产或正式安装。

## 七文件静态合同核查

| 范围 | 核查结论 |
| --- | --- |
| query_policy / live_spatial_mcp 的 objects | 仅单个 id/name selector；无 objects 保留原模式。MCP schema 上限与服务校验一致，非目标参数没有顺带开放。 |
| blender_mcp_host 新 host command | 请求走现有只读调度、deadline 和 scene decoder；不是独立未经绑定的几何通道。 |
| blender_host 同次读取 | 一个 graph、scale、frame、evaluated 对象目录；target+unknown 与 remaining 为不相交集合，同一 evaluated_by_id；末尾核对身份/矩阵/guard/counts。 |
| A / B | `retained = objects`、`retained_ids = ids`、`excluded_ids = []`；无 B 的 viewport object exclusion。暂存 `viewport_selection` 阶段没有剔除工作。 |
| target partition / occluder | 仅 target 建 region；其他对象标 occluder_only，完整 triangles 仍送 coverage index 与 image meshes。没有把非目标物体从遮挡计算移除。 |
| source / brief / source faces | target 实例、selector、目录摘要、full identity、retained order、camera 摘要绑定；target 源面范围保留原 object-local face 索引。brief 的 unsupported 分母只针对 target，occluder 不冒充 unknown target。 |
| 无 objects 旧路径 | live_service 仍 capture_scene；bridge 仍 freeze_cameras、全对象 partition、patch-support-v1；target 分支使用 v2。没有静态发现旧分支被切到 target。 |
| 缓存新鲜性 | read-context key 包含 capture_state generation/token 及完整 source binding；target 身份/目录/camera/source revision 均参与；include_image 与 selector 另在 query key；work timing 不进入 binding。继承 residency 对修改/撤销/加载的失效机制，没有改写其合同。 |
| include_image=false | bridge 不构造 ActiveObservationImages、无 raster loop，返回 predicted、没有 witness。服务缓存键区别 image 请求。仅静态审查；本轮未把该路径报告为实际 MCP 回归。 |

## 作者证据与独立证据的区别

作者记录包括 29 项 target pure、17 项已有 pure 检查、数值及质量接口测试，以及 A_peripheral_02 的一次实际 SCENE 光栅。作者的真实案例无完整 witness，结果为 not_realized；B 与正式对照矩阵未运行。以上为作者记录，本轮没有重复执行或将其计入独立测试数。

本轮独立证据仅为上一节列出的固定源码、纯函数/精确几何反例及源码合同审查。新 F1 不推翻作者原 fixture 的 `not_realized` 记录，也不把其改成性能失败或错误完整放行。它应先以一个最小修复处理，然后再决定合格的新目标任务及 B 的验收。
