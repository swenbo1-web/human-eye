# DEGENERATE-SURFACE-001

原 T04 的退化焦点现在得到 complete 表面距离：0.004000000189989805 米，唯一最近对象 M4_Near，四个目标均有效、零未决。名称观察和返回 focal.id 的旧入口观察语义相同。只交付一个候选：0ad59befeee43c2fad752e3bad2ee69f87af3136；131 源 canonical SHA256 82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6。最终证据提交及索引/报告哈希在一次完成回传中固定。

## 实现与边界

每个原三顶点面的闭凸包按精确零法向保留为三角形、线段或点。三点共线时取真实字典序两端，重复顶点不会生成零长边。网格仍是原各面集合的并集，不计算全局凸包。点线/点面/线线继续复用原精确特征，线穿面内部用原重心判据的齐次整数形式判定；有理交点在 witness 阶段构造。点点有独立见证描述符，零距离方向保持 not_applicable。有效距离与见证/方向可发布性继续分开。

产品只改 surface_proximity.py 和 task_query.py 的两类缓存算法版本。METHOD 为 exact_binary64_triangle_surface_hulls_v3；普通缓存 task-surface-proximity-exact-aabb-v3，精确排名缓存 task-surface-proximity-exact-world-rank-v2。旧退化 unknown 缓存不能命中，普通/精确排名仍分离。MAX_FACES=4096、MAX_TRIANGLE_PAIRS=16384、MAX_BITS=4096、发布容差、AABB 严格剪枝、world 精确排名和并列规则不变。坏索引、非有限、位宽/规模超限、取消与原期限仍保留其拒绝或传播语义。

普通三角形复用原 5-tuple、3 顶点/3 边，新增维数布尔门控及变长端点索引（每面三次 len(points)）；普通单面对计数仍为 intersection/point-face/point-edge/edge-edge=1/6/18/9。这些常量级检查也是实际工作。点/线段记录保留 1/2 顶点与 0/1 非零边；点点没有点面/点边/边边工作。只在退化段与面组合构造齐次临时量，没有新增模块、服务或缓存层。临时堆字节、CPU 周期与完整模型收益未测，不把静态结构计数当作这些测量。SAT、实体判定、动作/写权限、名称入口、参数/字段/说明均未改。

## 离线数学、链路与回归

首遍也是唯一一遍离线执行：83/83 方法通过，零失败、错误或跳过。新增定向组严格为 12 个方法，其余是与改动有关的既有回归；旧退化 unknown 断言按合同更新，partial/unknown 另用真实有限位宽超限输入保留。旧运行原件未覆盖。

| 组 | 方法 | 失败 | 错误 | 跳过 |
|---|---:|---:|---:|---:|
| ENTRY | 19 | 0 | 0 | 0 |
| DIRECTED_MATH | 12 | 0 | 0 | 0 |
| SURFACE_REGRESSION | 41 | 0 | 0 | 0 |
| PRUNING_CACHE_REGRESSION | 11 | 0 | 0 | 0 |

独立 oracle 用 Fraction 枚举各面非空支持集并以 KKT 高斯消元求约束驻点，另核明确解析平方距离；不调用产品特征生成答案。覆盖点/线/面组合、顶点全排列、真实凸包端点、端点都在面外的内部穿面、共面/平行/重叠、原 T04、实际 binary64 平移旋转、极近非零、预算与取消、全部并列、严格排除、两类缓存及见证精度。tests/TEST_PLAN.md 固定全部 12 组变体。

原 verified_source_loader 从冻结的 131 份相同源码安装，guard_verify_loaded=True；已加载产品模块的执行/namespace witness 随 EXECUTION_IDENTITY 保存。测试 raw SHA→compile 文件名和 EXECUTED_BYTES.zip 同时封存，不以磁盘同名文件代替执行字节。原 T04 fake-RNA 链路冷请求 kernel_calls/cache_hits=4/0，重复为0/4；普通焦点并列变体仍有2有效/1严格排除。普通/rank 缓存各第一次计算、第二次命中，旧版本 seed 被隔离。

离线内部耗时 2.4231960 秒，外层 exec 观测 2.7327832 秒。两个既有 renderer bbox add overflow RuntimeWarning 在工具合并输出中保留为 OFFLINE_INVOCATION 观测，没有测试失败。首遍没有另捕获外层 stdout/stderr 原始文件，该边界明确未测；完整 unittest 文本、结果和执行 ZIP 均保留。未为取得干净日志重复执行。

## Independent T04 geometry audit

Both finished raw socket captures and public stdio returns pass independent geometry checks. No product module or test module was imported; no model, Blender, RPC or test was rerun.

The actual focal vertices are `(0,0,0), (0,1,0), (0,0,0)`, so its closed face hull is a segment. Every actual target face is `(x,0,0), (x,1,0), (x,0,1)`. With focal p=(0,t,0) and target q=(x,s,u), squared distance is x²+(t−s)²+u² ≥ x². The lower bound is attained at paired y=z=0 vertices. This proof uses exact Fractions of the parsed binary64 coordinates, independently of the product distance kernel.

| Actual target | Exact distance metres | Binary64 distance metres |
|---|---:|---:|
| M4_Near | 8589935/2147483648 | 0.004000000189989805 |
| M4_Far_00 | 1/1 | 1.0 |
| M4_Far_01 | 2/1 | 2.0 |
| M4_Far_02 | 3/1 | 3.0 |

The exact nearest distance is 8589935/2147483648 m = `0.004000000189989805` m. The sole nearest object is `M4_Near`; all four actual candidate distances are finite and independently proved. Both public packets report complete, coverage 4 valid / 0 strictly excluded / 0 unresolved, metres, unchanged focal identity and no execution authority. The second request's legacy focal_id is exactly the first return's focal.id; all public semantic fields, including bindings, are identical except trace_id. Captured geometry is identical.

The actual asset has no multiple nearest-object tie and no strict AABB exclusion. Its degenerate focal has no original nondegenerate triangle acquisition witness or finite upper seed, so all four targets remain retained. Multiple exact ties and strict exclusion are demonstrated by the distinct fixed offline variants, not claimed from this real sample.

The original offline record reports 12/12 directed groups passed, 0 failures/errors/skips; 83 related methods overall. The twelve groups cover point/line/face combinations, all collinear vertex orders and zero edges, interior segment/face crossing, coplanar cases, face-union semantics, actual binary64 transforms, near-nonzero geometry, bit/work/deadline limits, real read-only fake-RNA chain and ties/pruning, normal/rank cache identities, and distance/witness separation. That is offline verified-source evidence. These two actual Blender captures establish only this real T04's supported segment-to-triangle geometry and name/legacy equivalence.

Candidate `0ad59befeee43c2fad752e3bad2ee69f87af3136`, raw reported runtime source `82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6`. Source execution proof and owner/asset closure are separate audits; this geometry audit does not substitute for missing receipts. All 61 QA files were hash-inventoried before and after and remained byte-identical. Inputs and exact fractions are retained in GEOMETRY_AUDIT.json. This audit does not claim model adoption, task savings, provider requests or fees.

## 唯一真实 QA 与完整成本

源码先提交固定后才执行真实 QA。原 controlled stdio、原已核验 helper 与私有 T04 副本；1 NativeSession、2 公开观察、1 owner close，共3物理 RPC。没有 profile setup、资产编辑/保存、额外观察、新模型消费者或外部 API。worker 600秒、单请求20秒、host/native10秒均沿用原框架。prepare 在候选冻结后执行一次，只做字节/身份/资产/窗口核对和准备。

QA prepare 内部 5.5251984 秒（工具外层5.7833808秒）；完整 QA 外层 2.4100212 秒，从 2026-11-08T11:20:20.158347+00:00 至 2026-11-08T11:20:22.568970+00:00。controller 内部 2.1658552 秒，Native 启动 1.2268682 秒，close 包装 0.1350883 秒。以下单请求时间含在外层中，不相加、不扣除准备或测量开销，也不作冷暖模型收益推断。

| 公开调用 | 包装秒数 | 物理 RPC |
|---|---:|---:|
| direct_name | 0.0596827 | 1 |
| legacy_id | 0.0613907 | 1 |

原始字节边界：control TX/RX=17/62 B；product socket TX/RX=7617/15070 B；stdio 完整 TX/RX=811/24723 B。这些边界重叠，不能相加成模型输入或服务费用。无新增模型消费者；作者/子审 token 和费用未测。MANAGEMENT_START/CLOCK 另记本回合从任务开始至封存的完整 elapsed 下界，包含嵌套实施、测试、Git、准备、QA及并行审计；最终提交/回传尾段由完成聊天 metadata 补全，较早回合不混入。

## DEGENERATE-SURFACE-001 raw QA audit

Independent existing-byte audit: passed=True; 75 consistency checks, 0 failed. All 66 original QA/outer files remained byte-identical. No additional product import, Blender session, RPC, model, process signal or global process enumeration was performed.

Candidate 0ad59befeee43c2fad752e3bad2ee69f87af3136; 131-source canonical 82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6. Current disk, offline engine snapshot and fixed Git blobs match. Exact frozen controller/proof hashes, original T04 asset/copy, helper and Blender hashes match. The actual production stdio guard reports 57 loaded modules, every loaded module witnessed, compatible generation. Worker scripts independently bind the expected unchanged readonly host bytes.

One NativeSession; exactly three physical RPCs: name surface_nearest, returned focal.id legacy surface_nearest, owner close. No setup/profile RPC. MCP sequence is initialize, initialized notification, tools/list, two tools/call frames. Both public observations are complete, have unit m, no execution authority, all four targets distance-valid, zero unresolved/strictly-excluded, nearest ['M4_Near'], distance 0.004000000189989805. Semantic fields are identical. The independent oracle uses actual returned binary64 coordinates: target constant x is a lower bound achieved at y=z=0. The exact minimum is 8589935/2147483648 m, above or equal to 3mm=True. This is a QA distance check, not a new consumer answer.

Original worker deadline remains 600 seconds; product request/host budgets remain 20/10 seconds. Two logical code hashes match worker events and physical execute_code payloads, two worker stdout bodies match socket outputs, and both source captures match. Actual profile diagnostics retain first request kernel/cache 4/0 and second request 0/4; cold/warm durations do not establish task benefit.

Time boundaries (nested, not additive): preparation 5.5251984s; outer Popen/wait 2.4100212s; controller 2.1658552s; Native startup 1.2268682s; public calls [0.0596827, 0.0613907]s; stdio lifetime 0.7720516s; native close 0.1234173s; close wrapper 0.1350883s; profile overhead 0.0002221s. Management/implementation/offline time is outside these QA boundaries. No overhead is removed as free work.

Bytes: product socket TX/RX 7617/15070; close TX/RX 17/62; complete stdio TX/RX 811/24723. These transport boundaries overlap and are not provider tokens. Render event counts remain zero; no generated PNG changes were recorded.

Owner receipts: outer Popen 34568 exit0/reaped; stdio Popen 35128 exit0/reaped; Native 18584 exit0/reaped with closed response, unchanged original deadline, helper/assets and geometry fingerprints, poisoned=false. Controller self PID 35356 differs from the outer Popen handle; no direct owner-wait receipt for that self PID is invented. All 4 distinct recorded PIDs were independently observed stopped using zero-time SYNCHRONIZE waits. This cannot exclude PID reuse or unknown descendants.

The third worker event remains status='unknown'. A separate close response and owner wait support closure but do not turn that unknown event into graceful success. Missing owner/descendant coverage, author usage and fees remain unknown. Terminal fingerprint/file checks do not prove absence of reverted transient mutation or a Python sandbox. No model/task benefit claim is made.

First bookkeeping audit is preserved as QA_AUDIT_01.json/md and qa_audit_01.py: 71 checks, 4 false comparisons caused by conflating LF logical text with CRLF disk artifacts. This corrected audit proves, byte-for-byte, disk SCRIPT == logical wire code with each LF written as CRLF, while worker event SHA == logical code SHA. Script logical/disk bytes are [(3638, 3677), (3677, 3716)]; stdout logical/disk bytes are [(6982, 6983), (6982, 6983)]. Original CRLF counts and independent hashes are retained. No QA was replayed, no raw file changed, and original four PID observations were reused without additional queries.

## DEGENERATE-SURFACE-001 independent source review

PASS. Candidate `0ad59befeee43c2fad752e3bad2ee69f87af3136` has exactly seven changed Git files, all matching current bytes. Independent enumeration and canonical recomputation bind all 131 product sources to `82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6`; current/Git/offline-engine/EXECUTED_BYTES.zip product bytes agree. The four actual test byte streams and runner byte stream match the 136-member executed archive.

Original offline evidence records 83/83 passing methods: ENTRY19, DIRECTED_MATH12, SURFACE_REGRESSION41, PRUNING_CACHE_REGRESSION11; zero failures/errors/skips/omissions. Every raw unittest log has the expected ok-line count, Ran summary and OK terminator. Original guard is true, loader hash matches fixed product bytes, and 56 loaded product path witnesses are retained. No test was rerun.

Only surface_proximity.py and task_query.py change in the product. Existing face representation stays a five-tuple. Exact-zero normal reduces each original face independently to its actual point/segment hull. Nonzero faces retain the original geometry formulas; one finite homogeneous segment/face interior-contact predicate is added. Zero-length edges are not generated, pointpoint has its own witness descriptor, and segment-face rational witness construction is deferred.

AST comparison identifies only _integer_frame, _nearest and _witness as modified existing kernel functions, plus _segment_face_contact added. Admission, original intersection/features, bounded arithmetic, strict AABB pruning, exact rank, distance rounding and witness publication are unchanged. MAX_FACES4096/MAX_TRIANGLE_PAIRS16384/MAX_BITS4096, scratch limit and publication tolerance are unchanged. The task_query AST is identical after restoring only the two cache-version literals. No new product module, SAT, action, name or public-schema change exists.

Recorded ordinary work retains intersection/point-face/point-edge/edge-edge counts 1/6/18/9. Degenerate point work and cache records remain in DIRECTED_EVIDENCE. Normal and exact-rank cache versions remain distinct; each computes once, then has a hit with no kernel work. CPU cycles, heap bytes and full model-task performance are unmeasured; constant dimension guards remain real work.

The new Fraction oracle is independent support enumeration with exact Gaussian elimination of convex-QP stationarity. Feasible minimal supports cover lower-dimensional and flat-minimizer boundaries; explicit analytic d-squared fixtures also check it. It reads actual represented binary64 inputs. This is math/source review, not extra execution or actual Blender evidence.

All fourteen specified older marker files match their recorded SHA and baseline Git blob. No broad older-directory scan was used. Two prior renderer bbox overflow RuntimeWarnings remain documented in OFFLINE_INVOCATION; lack of separate raw outer stderr is retained, without rerun. Standard/test/third-party dependencies are outside the product guard. QA bytes and owner cleanup are reviewed separately.

This review added zero product/test calls, Blender sessions, RPCs or model answers. SOURCE_REVIEW.json retains the exact hashes, identities, AST findings and recorded work.

The JSON verification_script_elapsed_ns covers the final hash/AST bookkeeping script only. Earlier code/oracle reading and tool/report/callback time are outside it; complete reviewer elapsed/tokens/fees are unmeasured.

## 封存与未测事项

RAW_ORIGINALS.zip 与逐成员索引完整保留 offline_01、qa_01、qa_invocation_01，包括原始 bytecode；原目录不删移。PRESERVATION 固定14个旧标记及本批原始字节。EVIDENCE_INDEX 覆盖两产品源、三份必要旧测试及本批文件，排除索引自身和直接 bytecode/cache（其原始字节在 ZIP 内）。提交前后都核对磁盘、索引、Git blob和限定变更范围。原 RUN001–005、两个 M1 离线尝试及 raw QA 均保持。

本批没有 RUN006，也没有新模型消费收益结论。真实 QA 只覆盖原 T04 的名称/旧ID两观察，不扩大为所有退化网格或实际源类型验收。有限精确算术与原规模/期限拒绝仍有效。STATE/window 由根管理，本分支未写 STATE；Google付费、原资产、共享GUI/default9876、正式配置和竞争分支保持原边界。本批完成回传后停止，等待根深审。
