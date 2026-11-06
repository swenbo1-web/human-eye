# PERF-INTEGRATED-001 静态准备

2026-11-07。当前交付为固定方案、必要 fixture 和既有适配的有限更新。产品、Python 编译、测试、Blender、资格采样及新模型任务回答的实际执行数均为 0。实际提交及逐文件 SHA 由本批 `static_freeze.json` 和 READY 回报绑定。

## 候选与边界

复用 `326b64c74b2672fd620ddb9cac83bf47dd5355f2`，130 源摘要为 `20fe8507cf3f802bd9471d2e8f7d00470f6013a6236f40e82258bd6aa6e7c5a0`。该版本已包含接受的 M2 E 和 M3 双 PT 修复。当前准备从本线 `14016f4bdf15cf779fe92156909787a1ac0cfe25` 开始，继续使用 `codex/perf030-003-convex-preparation` 分支。

主线收口文件 `CONVERGENCE_AND_TASK_COMPARISON.md` 的 SHA256 为 `c682f30bb928ded661d7963262116845f766c753eb50e00b8f73613547745236`。003 主线终审 SHA256 为 `5329fe346aea6f207ee2b28f125c7f98bcaa58cdf811560fb79c367674569b2d`。003 已以 0/5 结束 topology-only 路线，历史性能失败仍保留，M3 整模块性能准入继续开放。

当前授权为静态阅读、编辑及本线 Git。M2 所持窗口按派单记录为 `PERF020-O5B-WINDOW-01`，本线完成一次 READY 后等主线另发执行窗口。Google／API／Key／503 和旧费用预留继续暂停。新写入仅在本工作树内，执行时资产为本批新建隔离副本。

Agent Learning 在中断前已登记任务 `96d35735-b165-4d51-bb8e-54810f3eadd8`。恢复时工具一度未提供，先发生只读核查和三个静态子任务的重新委派。工具恢复后核得 paused／write_version 11，已显式恢复为 revision 1／write_version 12 active。恢复前事件保留原顺序。

## 两个固定任务与作者真值

公开问题和共同预算在 `verification/fixtures/perf_integrated_001_tasks.json`。消费者收到该文件中相应题目的精简文字、共同能力说明及自己的 CLI 路径。fixture 源码、评分真值、作者快照、历史答案和其他消费者上下文均留在作者侧。

| 任务 | 目标与候选 | 首次／未变再查 | 局部改变后 |
| --- | --- | --- | --- |
| control | 两个闭合盒体，各 8 顶点／12 三角面 | 分离，最小间隙 0.010m，目标到候选方向 +X | 目标 +X 面四顶点由 x=.05 改为 .065，实体穿插 0.005m |
| assembly | 连通带孔 12 边环目标 48 顶点／96 三角面，加三个盒体探针 | Object_02 分离 0.010m，Object_03 穿插，Object_04 分离 0.040m，最近分离件为 02 | 目标 +X 内壁四顶点由 x=.6 改为 .58，02／03 均穿插，04 保持分离 0.040m，最近分离件为 04 |

control 的目标局部范围为 `[-.05,.05]^3`，候选为 x∈[.06,.08]、y/z∈[-.01,.01]。assembly 为内切距 .6m／外切距 1m、z∈[-.1,.1] 的正 12 边环形挤出。02 为孔内盒 x∈[.55,.59]、y∈[-.02,.02]、z∈[-.025,.025]。03 中心为 `(-.605,0,0)`，半尺寸 `(.02,.01,.025)`，另绕局部 Z 旋转，cos=.6、sin=.8。04 为 x∈[-.025,.025]、y∈[1.04,1.08]、z∈[-.025,.025]。所有装配件再共同施加有理正交矩阵 `[[1,2,-2],[2,1,2],[2,-2,-1]]/3`。

环目标自身有孔且复杂于控制盒。02 位于孔内，04 位于外缘之外，但旋转后的世界 AABB 都与目标 AABB 重叠。题目要求逐候选实体关系、全部穿插件、分离间隙、最近分离件和包围盒局限。复杂穿插仅要求几何依据。

`perf_integrated_001_fixture.py` 在新后台 Blender 中构造 baseline，读回实际局部顶点、三角面和变换，并由这些值用 Python affine 算术派生 world_vertices。作者构造阶段临时应用并恢复四顶点 patch，以读回 changed 真值快照，资产文件仅保存 baseline。两条路径各加载相同 baseline bytes。

`perf_integrated_001_truth.py` 仅用 stdlib，独立重建预期边界，核验实际读回 mesh／变换／闭合拓扑，并用独立二维环材料／边界距离加 Z 区间计算三维分离间隙。穿插由严格内部共同点证明。它不调用产品求解器。实际坐标验证容差为 1e-7m，回答距离容差为 1e-6m。真值 JSON 和资产／patch SHA 必须在四个消费者中的首个作答之前全部冻结。

assembly 对各盒体的静态保守 SAT 工作量为 586,656，低于 2,000,000，整个四对象场景估计 1,871,712，低于 8,000,000。目标为带孔凹件且共同旋转，按当前固定支持域预计 `unsupported_solid_geometry`，原生回退为预期可能路径。预算和目标几何保持预登记值，实际 rejection／unknown／fallback 均入账。

评分由主线独立执行。每份回答分别核对正确性、遗漏、unknown 解释、几何依据和当前状态依据。两次再查需要实际当前几何／有效版本证据，纯复述旧答案的当前核查维度记失败。整体任务质量不足记失败。这里的两题用于定位完整任务瓶颈。

## 既有入口与一次 QA 更新

继续使用 `perf010_qualification.py` 的候选 pin 和 `perf000_scene_tool.py` 的普通 native／observe CLI，复用 `visual004_native/session/product`。N 可自由使用普通 bpy、Python、数学库、自编脚本和持久 namespace。P 具有相同 native 能力，另可选固定 Human Eye。工具选择由消费者决定。

原 worker 每次核对固定初始 fingerprint，几何改变会结束会话。本批在该 QA worker 增加显式 opt-in `qa_vertex_patch`。patch schema 为 `{target_name, vertices:[{index,co:[x,y,z]}]}`，只接受冻结的绝对局部坐标。`NativeSession.start`／`serve` 的参数默认值保持兼容，perf010 CLI 新增 `--qa-vertex-patch`。操作者在第二份回答结束后调用 `NativeSession.open(workspace).qa_advance()`。

该一次控制更新核验 patch SHA、目标、唯一 index、有限坐标、当前 fingerprint、源文件和 float32 读回，只接受预登记顶点的完整 scene-state 差异。保留原 initial 与更新后 current 指纹，成功后原进程、namespace、产品 service 和缓存继续使用。实际缓存失效由当前几何变化触发。部分写入、未知回执或失败进入 poison，排他 attempt 原件阻止重放。消费者 broker 的公开 OPS 集合保持既有值，更新属于试验操作者控制。既有 Python 宿主仍按实验协议隔离，完整 Python 安全沙箱未提供。

新增测试覆盖 opt-in、三状态持久性、一次性／重开、坏索引与源变更、部分 setter 失败、非目标变化及更新后的消费者越界变化。当前全部仅写入源码。

## 隔离安装与相关回归

运行目录预定为 `verification/fixes/perf_integrated_001/run_01/`，必须新建。使用已有 `verification/build_candidate_release.py` 原字节 manifest wheel 入口，版本标签为 `9.7.2+perf.integrated.1`。标签与 130 产品源摘要分别记录。

以下为授窗后的命令模板。`$repoRoot` 为本工作树绝对路径，`$runRoot` 为上述全新目录，`$bootstrap` 为已有 Python 3.12 解释器。

```powershell
& $bootstrap -I -B "$repoRoot/verification/build_candidate_release.py" --output "$runRoot/build" --version 9.7.2+perf.integrated.1
& $bootstrap -I -B -m venv --copies "$runRoot/venv"
$trialPython = "$runRoot/venv/Scripts/python.exe"
& $trialPython -I -B -m pip install --no-index --no-compile --disable-pip-version-check --find-links D:/hefe/artifacts/local_release_dependency_cache "$runRoot/build/human_eye_spatial_plugin-9.7.2+perf.integrated.1-py3-none-any.whl" numpy==2.3.5 Pillow==12.3.0
```

依赖复用现有离线 wheel，SHA 进入 freeze。安装日志、wheel RECORD／源 bytes、installed distribution identity、产品实际路径及 drift 实测入账。安装前后均核 130／20fe。新 venv 的 purelib 中仅增加本批需要的 `verification` QA 文件和空 `__init__.py`。

五个适配文件复制到 `venv/Lib/site-packages/verification`，以该 venv 的 `-I -B` 调用复制的入口。这样 QA 的 ROOT 和产品来源同为 purelib，满足 `BlenderMCPHost` 的 `ROOT/human_eye_plugin/blender_host.py` 契约。实际断言产品 `__file__` 位于 purelib、`source_kind=installed_distribution`。工作树入口只用于本批 wheel 构建和作者 fixture 构造。

相关回归固定九个模块加一个既有方法，真实运行分母由 unittest loader／testsRun 保存。

- `test_visual004_native`、`test_visual004_session`、`test_visual004_product`、`test_perf000_scene_tool`
- `test_task_query`、`test_selected_task_query`、`test_scene_cache`
- `test_perf030_002_pt_dual`、`test_perf030_003_goal`
- `test_concave_geometry.ConcaveGeometryTests.test_general_rotation_is_unknown_without_snapping`

额外复制依赖为 `test_host_runtime`、`test_live_service`、`test_auto_router`、`test_concave_geometry`、`test_blender_mcp_host`、`test_complex_scene_quality`、`perf030_002_cases`，以及固定 `fixes/perf030_001/inputs.json`。测试与模型会话使用独立进程和资产副本。安装／回归失败则保留失败和实际前缀，模型分母为 0，交主线复核。

作者构造与真值入口为以下模板，Blender 为已有 `D:/Tools/blender5.2/blender.exe`。所有输出位于本批目录。

```powershell
& $blender --factory-startup --disable-autoexec --background --python-exit-code 1 --python "$repoRoot/verification/perf_integrated_001_fixture.py" -- --case control --output "$runRoot/author/control"
& $blender --factory-startup --disable-autoexec --background --python-exit-code 1 --python "$repoRoot/verification/perf_integrated_001_fixture.py" -- --case assembly --output "$runRoot/author/assembly"
& $trialPython -I -B "$repoRoot/verification/perf_integrated_001_truth.py" --case control --snapshots "$runRoot/author/control/author_mesh_snapshots.json" --output "$runRoot/author/control/TRUTH.json"
& $trialPython -I -B "$repoRoot/verification/perf_integrated_001_truth.py" --case assembly --snapshots "$runRoot/author/assembly/author_mesh_snapshots.json" --output "$runRoot/author/assembly/TRUTH.json"
```

两个作者快照分别经独立 truth CLI 验证，输出作者私有 JSON。入口资格固定四个会话，即两题各 P/N，单会话 120 秒。每会话三状态各一次普通 native mesh 读回，共 12 次；P 在每状态对题目所有目标／候选 pair 各一次 task observe，control 为 3 次，assembly 为 9 次，合计 12 次。每会话一次 QA 更新，共 4 次。保存 actual current binding／unknown／回退原因并核验源资产字节。资格复用已安装五个 QA 文件，结束并回收资格进程后才开始消费者。P/N 模型会话均为新 Blender worker、新 broker、新消费者，OS 磁盘缓存未清理。

## 固定 P/N 三状态链

顺序为 control N→P，assembly P→N，各链串行。每链首问创建一个 `fork_turns=none` 消费者，随后对该同一消费者 followup 两次，共四个消费者、最多 12 份任务回答。使用相同继承模型设置，保存实际宿主模型／provider alias／effort 等已暴露字段，实际设置不匹配则保留并结束有效对照。精确后端及 Pro 身份未暴露时记未测。

每链三个状态为 initial、unchanged_current、changed_current，分别映射作者 truth 的 initial、unchanged、changed。第二状态的场景保持既有几何，第三状态之前由操作者执行一次固定 QA patch。模型可保留脚本和缓存，自行进行当前性判断。原生求解器、跨续问复用及 P 原生回退均可使用。

每链启动命令使用 purelib 中的 `verification/perf010_qualification.py`，参数为 baseline `.blend`、全新 `runs/<task>/<P或N>`、固定 Blender、condition、20fe pin、实际 baseline SHA、`--seconds 600` 和固定 `qa_patch.json`。对消费者提供相同 `perf000_scene_tool.py native --workspace ... --script ...`，P 另提供其 observe 命令和简短 schema。

外层链墙钟从启动资格入口之前起计 600 秒，单回答外层 150 秒。P 的 bind_candidate 在 serve 之前，额外 pin／策略准备计入链启动成本，外层时限覆盖该范围。现有 broker 48 次公开调用、256KiB 数据、98,304B 控制预算及 native 最大 256KiB code 共用于完整三状态链。worker 原始 RPC 上限 128，一次 QA 控制更新也计入该上限。native 单调用至多 30 秒，P 单请求 20 秒。全部上限双方相同，实际子请求与失败另计。

本轮选用既有数值薄入口，实际交付图片预算为 0，正文和工具文本按真实 UTF-8 bytes 记录。消费者获得精简任务／工具用法，试验管理由操作者负责。

任何已开始／响应未知的任务回答或 QA 更新均保留实际分母，自动模型重试为 0。回答完成后继续下一预登记状态，几何／传输未知、poison 或时限耗尽则结束该链并清理，不补足失败回答。所有程序性失败和资源预算失败均与题目质量分列。

## 完整成本与收口

每链记录实际 argv、UTC/QPC 启止、launcher／worker／broker 身份、退出码、stdout／stderr、cleanup。逐回答记录 dispatch UTC、host turn 开始／结束与原始 final，分别报告完整链启动、答题墙钟及试验管理间隔。嵌套阶段按范围分列。

复用现有 broker REQUEST／PUBLIC_RESPONSE／BROKER_STATE、native WORKER_EVENTS／SCRIPT／stdout 和产品 COST／MCP trace／native_private_evidence。实际 capture envelope 的 meshes 可重算返回对象／顶点／三角面和重复几何 hash，这支持重复采集记录／交付计数。产品 trace 的 host.capture／scene.validate／observation.task_facts 等为 inclusive span，task_work.exact_pair_count／pair_cache_hit 和 SceneCache stats 分别记录实际计算／缓存。accounted_bytes 属 immutable payload 加 entry allowance。FULL_RESULT／PUBLIC_RESPONSE 记录实际应用编码／公开 bytes，按固定 encoder 重建的下层大小标 derived application-payload bytes。TCP 字节与纯传输时长未单独采样。QA 全场景 fingerprint 扫描也属于实际管理成本。原生自由脚本的求值次数、缓存命中或纯求解时间缺少显式证据时记未测，临时分配／RSS／峰值同样单列未测。

复用 PERF-000 的白名单计量器 `extract_usage.py`，SHA256 为 `86ecb964892ee6be2ce705b28e2152e7e371fd4e3c3771060ba4b30c06458242`。复制其原字节到本批 measurement，再以短管理员入口绑定本批 BASE／HERE／PLAN_SHA256，保持其 exact UUID、sanitized read_thread 全分页和 rollout 白名单读取。mapping 在实际创建消费者后记录四个真实 UUID／agent_path／workspace／三个 stage。读取范围为元数据、实际 usage 和公共工具项。

累计 token 增量按实际 turn 归属，last_usage 只作核对，cached input／reasoning output 保持子集。完整 public 工具与 final 文本分别记录，字节保持字节单位。provider 请求数、费用、未暴露 usage、精确后端和真实 Pro 身份均保留未测。QA advance 的 ATTEMPT／RECEIPT／FAILURE／worker event 另行入账，旧提取器没有这些新字段的专门汇总。

静态 freeze 固定本方案、公开输入、fixture／truth 源码、修改后的适配／测试、安装构建器、130 源清单及外部 wheel／计量器 SHA。运行前由主线复核并授一次唯一资源窗口，建议覆盖安装资格与最多四条 600 秒链，申请上限 3,600 秒。正常结束、质量失败、unknown 和预算停止均提交实际原件。最终由主线独立评分，依据完整任务账只选下一项真实瓶颈。

当前静态批次完成后发送一次 `PERF_INTEGRATED_001_READY`，附实际 HEAD、文件摘要、固定题目／真值、入口／预算和未运行分母，随后结束等待授窗。
