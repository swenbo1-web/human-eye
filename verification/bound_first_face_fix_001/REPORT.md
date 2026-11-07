# BOUND-FIRST-FACE-FIX-001：首面先校验、再读取有界索引

**BOUND_FIRST_FACE_FIX_001_COMPLETE。** 已移除首面见证对 `polygon.vertices` 的整数组读取。源码及固定字节哨兵证明：先检查首面布局，才读取三个loop索引；坏布局不取角或坐标，坏索引不取坐标。随后原完整helper给出具体来源错误，未进入原生展开。本批没有启动Blender或真实RPC，**不宣称破坏首面原生崩溃试验已通过**，也不构成完整nearest准入。

## 唯一产品候选

- 基线 `3b0f67abd6ed5bdab023b2b243e395aa1e8ff109`，原131源ae3bd4a3。
- 产品候选 `e55310a373a539dd40a2ad1707d875cf0faa8f28`；只改 `blender_host.py` 的 `_acquisition_witness`，7新增/2删除行。
- 新131源摘要 `c3a8fde463241912657b14f41d85b5d93aaf9877e341cf9ce62c308c51c2bd6c`；host SHA256 `de429b26288bb0dea8c43be01064e27d796adeaaea739a77cca29247d6a71f99`。
- 验证器修正固定提交 `a28aec566693ec118bbced411263f1974d027cbb`，产品字节与上述候选相同；不是第二个产品候选。
- 任务书SHA256 `683e95db2c6e7ea8530a5c969b7d5f73e007f6064e1bce1d0a6d20d42a4b5945`。

新顺序：取首poly的 `loop_start`、`loop_total` → 两者必须为int（排除bool）、total恰3、start非负、start+3不超loops范围 → 只读三个 `loop.vertex_index` → 原顶点索引类型/范围检查 → 原坐标/世界变换/Fraction非退化见证。任何失败仍返回原来的无见证None，完整acquisition稍后的既有helper具体拒绝；未把全helper前移或多扫一遍。

`SOURCE_AUDIT.json` 核定只有这一个顶层函数AST改变，其他130产品文件相同；完整helper和旧_capture保持，runtime_identity/M3/MCP/public schema均未改。正常点序、循环顺序、世界坐标、单位、退化/非有限处理及九点对选择原义保持。常数工作不包含新min/max、完整几何数组、缓存、预算或权限层。

## 实际执行字节证据

`run_fixed.py` 对基线和候选分别 `git show <完整commit>:human_eye_plugin/blender_host.py` 取字节，直接 `exec(compile(blob, git:<commit>:path, dont_inherit=True))`。候选字节先与当前磁盘逐字节比较；`_acquisition_witness` 与 `BlenderSceneHost.capture_nearest_candidates` 的 `co_filename` 必须来自这个固定Git编译。fixture的模块、host类和新测试捕获入口明确绑定到该候选，而非普通import命中缓存。

9项首面测试及原16项测试本身也从固定Git blob编译执行；`EXECUTION_IDENTITY.json` 记录四个执行模块的commit、字节数、SHA256与编译文件名。验证器自身启动时另用命令参数中的SHA核对读入字节，并核其固定Git版本。`-B`仅控制写缓存，**不是本批字节执行保证的依据**。

旧17路径使用同一固定候选类；生成wire模板的独立host加载仍以当前候选文件SHA检查后compile。旧fake接口适配只用于这一组：根据原fake polygon视图，填充/同步专门标记的自动RNA布局/索引，不覆盖明确提供的非法字段。新恶例和原16定向组不经过这个适配，没有为测试恢复产品危险getter。

## 验收结果

| 组别 | 结果 | 关键事实 |
|---|---:|---|
| 新首面用例 | 9方法通过 | 固定旧函数会触发禁止getter哨兵；新函数不触发；坏offset/长度先拒绝，坏index不解引用；完整capture在to_mesh/三角化前具体拒绝 |
| 正常值/顺序子例 | 36组合，包含在上述9方法内 | 3循环顺序×2世界矩阵×3单位×2合法起点；indices、world三点、point_world逐值等于固定前版 |
| 原SOURCE-FIX定向 | 16方法通过 | 四角色索引、后续NaN、结构/范围、去重、retained坐标复用、退化和期限/数量保持 |
| 明确RNA适配的旧M4/九点对 | 17方法通过 | 原选择/循环关系保持；不称旧不完整fake原样全绿 |

首面坏布局含负/越界offset、bool/float/string类型、total非3，以及6loops/2faces而首total8/后total-2的计数补偿例。getter为不可调用哨兵，布局失败时loop读取和坐标读取都是零。坏索引含负数、13、bool、float、字符串，三个角读取后仍零坐标解引用。正常有效face也不调用polygon.vertices。有限退化/NaN/Inf仍无见证，与固定前版一致。完整坏输入对原生展开设置双哨兵，所有对象mesh调用计数为零。

## 如实保留的runner失败

首次运行已从固定Git成功编译产品和测试模块，但 `loadTestsFromNames` 沿父namespace查属性，手工注册模块未作为父包属性，造成两项 `_FailedTest` discovery error；这时新9及原16尚未执行。旧17项当次已全部通过。原始日志/身份/RESULTS保留在 `*_INITIAL.*`，不是产品失败或实际Blender失败。

仅修正验证器：对已由固定字节执行并注册的模块对象直接 `loadTestsFromModule`。产品候选未变；随后只执行先前未执行的9+16，已通过旧17从同候选初次身份和成功记录复核沿用，未再跑。最终42个有意义方法通过，另两项发现错误保留，不能写成首次全绿。更早 SOURCE-FIX 的旧fake/初适配失败也仍在原目录，未编辑。

## 范围与后续

0新Blender session、0真实RPC、0asset builder、0正式性能/模型消费者/API/安装/默认切换。没有故意构造或执行原生坏首面；根提供的固定RNA源码路径与本批Python哨兵证据分开。测试是离线double，未把9+16+17通过推广成新增真实资产覆盖。一个工程子代理只读复审源码，无执行或写入。费用/token未测，测试时长不作为速度证据。

只在本方分支提交source和本目录；原资产、前五态实测、默认安装及另一线M3候选均未改变。后续交根同版本nearest整合，再做必要真实正路径；不重开B2/旧F或性能优化路线。
