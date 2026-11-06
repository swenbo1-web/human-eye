# PERF-030-002 静态预登记

## 当前状态

本批依据主线 NEXT_ASSIGNMENT.md，SHA256 为 `372b77b48bb539460ec8b2a5a2a2cc928a3ec32558a63db9b1465236039cda64`。本线使用 `C:/Users/Administrator/.codex/worktrees/2c7d/hefe`，分支 `codex/perf030-002-pt-dual`。

恢复提交 `5e976db` 已将 geometry_safety.py 恢复为接受 E 的字节，并将 001 专用剪枝测试移至 `verification/fixes/perf030_002/archive/test_perf030_001_pruning.py`。归档文件 SHA256 为 `dea2680f207b337e72d05f304f3e6c7dffca815ce30202b1bafb7a11c098b05d`。001 的 18 项原件继续通过固定提交 `2aeb7a770f4f40f119f51c021f09efd07e38139f` 核验。

当前仅静态阅读、推导、编辑、Git 提交及文件哈希。产品调用、NumPy 探针、CPU 测试、微基准和正式测量计数均为 0。M2 持有 `PERF020-O5A-WINDOW-01`。本批在一次窗口申请确认送达后结束准备阶段，待主线明确授窗且 STATE 一致后执行。

## 唯一候选

固定 E 为 `11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15`，130 源摘要为 `e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163`。

两个 PT 路径均采用同一公式。令 `n=ab×ac`、`dual_u=ac×n`、`dual_v=n×ab`，以原法向投影后的相对坐标点积 dual，再除以 `n·n` 求 u 和 v。scalar 和 witness 都保留原投影。这样消除 Gram 分子的近等大数相减，并先去除远离平面的法向分量，降低直接使用 offset 时浮点非正交性引入重心误差的风险。

给定 `h=2^-30`，原反例投影为 `(2,h,0)`，dual 分别为 `(h²,-h,0)`、`(0,h,0)`，精确重心为 `u=v=1`。这只是有限独立推导。旋转后叉积、投影与法向的条件数仍需按最终浮点输入验证。

产品 diff 限定两个 PT 重心表达式。原块、phase、严格最小值更新及其余数值核沿用恢复后的 E。

静态工作量动机为删除每面 3 个 Gram dot 数组，以及每个点／面组合的 4 次乘法和 2 次相减。新增每面 2 个叉积，对偶向量共 6F 元素。点／面点积和投影仍存在。窗口内将以一次有界算子／数组归因确认真实减少，构建成本计入测量。实际分配、峰值和耗时现均未测。

## 有限反例和独立依据

第一步仅执行主线规定的 E 两个叶核探针。三角为 `(0,0,0),(1,0,0),(1,2^-30,0)`，查询点分别为 `(2,2^-30,1)` 和 `(2,0,0)`，独立距离平方分别为 2 和 1。旧值预测分别为 1 和 0，当前均标为尚未产品复现。

随后对主线唯一封闭构造执行一次 budget、support、measure、完整 task 及私有 scalar/witness 诊断，每 arm 各一组。构造源于主线 `code/ANALYTIC_COUNTEREXAMPLE.json`。左体为 `[2,3]×[0,1]×[0,1]`，右体先按原序放六个 0.5m 盒，再接细长三棱柱，共 54V/80F。最近盒面 x=1.75，独立间隙为 0.25m。面绕向或索引若有具体错误，保留首次失败后最多作一次有几何依据的拓扑修正。支持路径未触达时记录拦截原因，叶核结论单列。

额外八个变体事前固定如下。令 `T(h)` 为上述薄三角，`h0=2^-30`，`R=[[1,2,-2],[2,1,2],[2,-2,-1]]/3`。

| 变体 | 固定生成规则 | 独立距离平方 |
| --- | --- | --- |
| 高度控制一 | h=2^-24，P=(2,h,1) | 2 |
| 高度控制二 | h=2^-38，P=(2,h,1) | 2 |
| 旋转 | 对 T(h0)、P=(2,h0,1) 同施 R | 以最终 binary64 数组精确计算 |
| 旋转远平面 | 对 T(h0)、P=(3/4,h0/2,2^20) 同施 R | 同上，失败原样保留 |
| 边界内侧 | P=(1-2^-30,h0/2,0) | 0 |
| 边界外侧，低于 1nm | P=(1+2^-30,h0/2,0) | 2^-60 |
| 边界外侧，高于 1nm | P=(1+2^-29,h0/2,0) | 2^-58 |
| 大平移 | 原非零反例整体加 (2^22,2^22,2^22) | 2，薄高恰为一个 ULP |

总量为两原始叶核、八变体及一个封闭构造。叶核及几何预期写在 `verification/perf030_002_cases.py`。独立 oracle 将最终 float 精确转成 Fraction，求受约束面投影和三条边的精确最小值。叶核距离平方以 `max(8*ulp(真值转float),1e-30)` 检查数值计算。该探针阈值用于浮点平方量的独立核验，公开物理容差继续按既有入口执行。

原 12 个解析对从 001 固定 inputs.json 读取。新增定向测试覆盖这 12 对的标量、witness 距离、独立三角面归属，跨原 64 点块的首 witness、原 ring 的近似平局。保留 concave、surface scope、strict execution、local SAT、scene cache、mesh mutation cache、task query 中适用回归及隔离宿主的 preview/readback/goal 反例。

已证明错误的 E 值单列。普通路径作差分，不能强制新公式复制旧错值。完整 task_response 将逐字段保存，包括 binding、schema、pair_order、unit、coordinate_frame、facts、status 和 execution_authority。固定 fingerprint、revision、source 取相同预登记值，动态差异单独列明。完整测量字典、witness 和诊断另存。

## 固定源码装载

两个独立持久 arm 进程采用相同 QA bootstrap。窗口内从 E 和冻结候选提交导出 130 份产品源 bytes 到本线证据快照根，逐文件绑定提交与 SHA。源快照提取和初始化成本独立记录。

QA worker 放在快照根外，按固定 SHA 核对后从同一份 bytes compile/exec。它先读取并校验 snapshot 内 verified_source_loader.py 的固定 bytes，compile 成 helper，再调用现有 install 并传 bootstrap_module，之后才导入产品。全部产品依赖及延迟导入由原 SourceGuard 覆盖。启动和结束各验证一次执行见证，保存 guard._executed 清单、源摘要及实际解释器／依赖身份。

每个 arm 一个代际。正式 worker 直接读取冻结 JSON 和 MeshEntity3D.from_dict，避免导入 001 的 QA helper。定向 QA 源也按冻结 SHA 从 bytes 编译，现有测试文件在快照根外执行。初始化扫描单独计量，内核循环采用原产品调用。

正式 worker 以 `-I` 启动，cwd 指向对应 arm 快照，QA/workspace 根不进入其模块搜索路径。执行身份依据为已核验 bytes 的编译见证。NumPy、Pillow/PIL、Python 与标准库属于信任外部依赖，记录实际版本及路径。QA 阶段的辅助源按冻结字节编译，产品模块继续接受原 guard 的校验。

静态正常导入链闭合于 130 源及上述外部依赖。1.4／1.5 模块在 ImportError 后存在短名兄弟文件回退，覆盖范围超出原 guard 的名称映射，异常回退尚未执行验证。窗口内通过实际模块来源和执行见证核对本轮路径，发现清单外产品来源时记身份失败。

## 正式序列和统计公式

候选通过有限正确性后才运行一次序列。对象对沿用 001 的 12 case，cold、pose_miss、geometry_miss、hot 四模式，两入口，5 block，每 arm／case／mode／block／entry 为 3 次，总计 2,880 条。原序列没有异常自动补跑规则，本批同样保留每条异常和超时。

顺序固定为 case、block、mode、entry、repeat、arm。block 偶数 E 先行，奇数候选先行，共三次 E 先行、两次候选先行。每个 case 的每 arm 15 点按中位数比较，改善率为 `1-candidate_median/E_median`。每 case 同时报告 5 个 block 的 3 点中位数配对改善及获益 block 数。五个有效目标 case 的改善率再取中位数，至少 4/5 case 获益作为组条件。补充 block 统计单列。

p95 为 15 点升序线性插值，即第 14 点乘 0.7 加第 15 点乘 0.3。对每个有效 case／entry／mode 单列数值修复的非退化门限，中位回退不超过 `max(0.2ms,2% E)`，p95 回退不超过 `max(1ms,5% E)`。cold／pose miss／geometry miss 的两个入口仍逐项报告 M3 20% 模块目标。正确性判定、非退化判定和 20% 模块目标分别给出。

miss 沿用 001 正式修订。pose 的 z 位移为 `max(1um,2*spacing(max_abs_focal_vertex))`。geometry 以最低 z 为锚，缩放因子为 `1+max(0.0001,4*spacing(max_abs_focal_vertex)/height)`。每 case／mode 在计时外保存一次最终顶点摘要、真实变化和锚点，两 arm 核对相同输入。cold 代表已导入进程中的新 pair/cache。有效 task hot 代表原 pair cache，直接 measure hot 只代表同对象支持信息复用。

## 完整成本与资源预算

分别计量源快照提取、源核验／编译／导入、进程启动／ready、对象构造、姿态／顶点修改、2,160 次明确的原 pair prime、内核、请求往返、结果发布和完整过程墙钟。task 内核边界继续含 scene/query 构造及 task_result。host／MCP／真实 fingerprint 属未测范围。

tracemalloc current/peak、RSS 和累计 allocator 次数分别标识。能测哪项就报告哪项，未取得的累计项标未测。新模型消费答案为 0，token 费用未测。

申请一个连续 CPU 窗口，计划墙钟上限 300 秒。准备与固定装载预留 60 秒，有限探针及回归预留 90 秒，唯一序列预留 120 秒，封存预留 30 秒。只顺序执行各 CPU 阶段，两 arm 闲置时保持进程等待。超时保留部分记录并终止本批采样，随后交付失败或未知状态。公式未通过时跳过正式性能序列，交付有界失败。

授窗后的最终回报采用一次 `PERF030_002_COMPLETE` 或真实 `BLOCKED`，附固定版本、报告 SHA、公开可达范围、独立真值、所有失败／未知、三个独立判定、完整成本及窗口释放。当前静态准备将以一次 `PERF030_002_WINDOW_REQUEST` 交接。
