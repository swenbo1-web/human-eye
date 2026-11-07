# NEAREST-CONTRACT-M2-001：求值网格包络的来源前提

本轮静态核查完成，可交管理员汇合；**不代表 nearest 产品准入**。结论是有条件成立：在同一求值状态、有效三角索引、有限被引用坐标和新鲜顶点范围成立时，局部 AABB 可以包住全部三角表面，无需先输出完整世界坐标/面数组。当前入口的首面见证、有限盒角和计数复核，尚不能独立证明这些全对象前提。不能把所有 M3 unknown 都当作包络失效，也不能据此宣称与旧全场景结果完全等价。

## 固定版本与证据范围

- 产品基线：`3f1d9d9e46d51643b67fdebac090cf9b825a15c0`；131 个产品源全部逐文件复核，源摘要 `2ef16a5e5b316453fff343ab8d2ff36b7b7c82113580137094f18896f1509664`。
- host：`62a50124424afdbc22ee184576a49a7edeae5ef3c9aaf7368e60b9947904f0a6`。本轮只新增此目录，产品及既有 QA/优化记录不改。
- 既有 QA 原件记录宿主为 `5.2.1 LTS`，二进制摘要 `284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb`。依据是既有 `m4_capture_qa_001/run_01/assets/ASSETS.json` 与 `FROZEN_PLAN.json`；本轮没有运行 Blender、重读二进制或取得本机 `build_hash`。
- [官方仓库 tag API](https://api.github.com/repos/blender/blender/git/ref/tags/v5.2.1) 返回 `v5.2.1 → 9e2066aef7ef7e20c142ad7bd3303138a4304c93`。8 个相关源文件先读 tag，再读这个不可变 commit，内容 SHA256 全部相同；见 `OFFICIAL_TAG.json`、`OFFICIAL_SOURCE_INDEX.json`。
- 某些 web 抓取入口返回 DisabledError、不可访问或 HTTP 402；随后通过标准库 HTTPS 成功读取官方 raw 文本，未下载运行外部代码。没有用 current/5.1/5.3 文档替代 5.2.1 源码。**官方 tag 已核到，本地二进制对应这个 commit 尚未证明。**
- 0 产品导入/执行、0 Blender、0 性能采样、0 消费者/付费 API、0 安装、0 子代理。四个标准库例子是条件逻辑推演，不是 bpy 行为实测。

## 证据表

| 项目 | 判定 | 依据与边界 |
|---|---|---|
| 当前 Python 入口覆盖 scene mesh，包含隐藏对象 | 可证明代码行为 | `_objects` 428–445：从 `scene.objects` 取全集；限制 1–256，拒绝不支持几何、instancer、Geometry Nodes 与求值实例；指定名称必须覆盖全部 mesh。不在当前求值域的对象必须通过 `is_evaluated is True`，不能默默丢弃。不是任意实例场景支持。 |
| 同一个图、单位与同步窗口 | 可证明代码结构 | `_depsgraph` 416–426 先 update；880–910 在主线程和 host 锁内取得一次图、正有限单位、身份与帧。`_capture` 复用这些对象引用；没有第二次图 update。不是内容版本号，也不是任意外部写入的锁。 |
| 静态来源限制 | 可证明代码行为 | 913–935 拒绝父子层级、约束、modifier、动画、刚体、shape key、链接、编辑模式等；同时保留总顶点/面预算。仅此受限入口。 |
| evaluated bounds 与 evaluated data 的通常关联 | 仅条件成立 | 官方 getter 链见下一节。正常 MDATA 路径从该对象数据顶点求界；缓存和 wrapper 路径仍有前提。不是原始对象任意 bounds 都等于求值表面。 |
| evaluated data 与 `to_mesh()` 的几何一致 | 仅条件成立 | 官方默认 `preserve_all_data_layers=false`，静态、非 edit、无 subdiv 的 MESH 路径复制同一对象的数据。RNA data getter 与转换均有 wrapper/subdivision 处理；不能由“都是 evaluated”跳过这些条件。 |
| 数值包络变换 | 既有算术证明，本轮不重测 | `_acquisition_bounds` 208–242 检查有限八角/端点组合，用向外区间处理仿射变换与单位；溢出返回不可用。前提是输入盒确实包住目标局部几何。 |
| 全部坐标与面索引有效 | 仍未证 | 927–948 只有集合/计数、总 loop 数、有限盒角及首面三点；`_acquisition_witness` 265–285 只读第一面。没有遍历被排除对象的全部坐标和角索引。合法 Blender mesh 的内部不变量可作来源合同前提，但本轮没有证明任意接收数据均满足它。 |
| 本窗口内容与 bounds 始终同状态 | 仍未独立证 | 1005–1014 复核成员、身份、帧、单位、guard、矩阵、顶点/面计数；不比较全部内容，也无内容代际。官方存在正常 dirty 路径，不能因此断言缓存已坏；相同计数也不能独立证明缓存新鲜。 |
| 首面见证与实际保留捕获 | 可证明局部回读 | 993–1002 对 focal/seed 回读三点和面，核对 `to_mesh` 结果；不覆盖被排除对象全部表面。 |
| acquisition 已是全场景 nearest 结果 | 明确不成立 | 1015–1037 明示 `M3_qualification_performed=false` 与 acquisition-only。此轮不改协议、成功状态或 unknown 语义。 |

## 官方 5.2.1 最小实现链

以下链接均固定到上述 commit；行号也是该内容的行号。记录的是已读代码路径，推论另作条件标明，没有运行这些代码。

1. [rna_object.cc L515 与 L1900](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/makesrna/intern/rna_object.cc#L1900)：data getter 读取对象 data，mesh 分支先处理 subdivision wrapper；bound_box getter 调用 `BKE_object_boundbox_eval_cached_get` 并展开角点。无 bounds 时此版本填零，不能把其他版本文档的 -1 描述当成此实现证明。当前有效非退化首面不可能完全放在零体积零盒中，首面核对通常会使该盒不可用；这仍不是全网格证明。
2. [object.cc L3693–3727](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/blenkernel/intern/object.cc#L3693)：先返回已有 runtime bounds，否则 MESH 路径调用该对象 data 的 `bounds_min_max`。同文件 [L5601](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/blenkernel/intern/object.cc#L5601) 的转换入口清旧临时 mesh 后创建新副本，不是持久编辑。
3. [mesh.cc L1923–1941](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/blenkernel/intern/mesh.cc#L1923)：零顶点返回无界数据；其余使用 bounds cache。MDATA/SUBD 分支对 `vert_positions` 求范围，BMESH 有另一条 edit cache 路径。它不是面索引有效性校验器。缓存命中与首次构建不能混作同一种成本。
4. [rna_object_api.cc L426 与 L1089](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/makesrna/intern/rna_object_api.cc#L426)：RNA `to_mesh` 转入 BKE，默认不保留所有数据层。[mesh_convert.cc L812–828、884–928](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/blenkernel/intern/mesh_convert.cc#L812)：默认普通 MESH 路径取 object data，处理 wrapper 后复制；保留全部层和 edit mesh 有分支。因此只能在相应条件满足时推断本入口的坐标/索引同源，不能把返回副本理解成独立来源认证。
5. [mesh_runtime.cc L395–407](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/blenkernel/intern/mesh_runtime.cc#L395) 有位置变化时标脏 bounds cache 的路径；[object_update.cc L283–285](https://github.com/blender/blender/blob/9e2066aef7ef7e20c142ad7bd3303138a4304c93/source/blender/blenkernel/intern/object_update.cc#L283) 把求值 bounds 回写 original runtime。它们支持正常生命周期解释，不是“当前 evaluated 缓存已过期”的证据，也没有覆盖所有修改途径的证明。

在有限顶点、合法索引、同一状态和新鲜 min/max 前提下，每个三角点是三个顶点的凸组合，因此落在局部 AABB；仿射映射后仍被正确变换的包络包含。这条数学推论不要求闭合实体、流形或非零三角面积。它也不证明 M3 在当前资源/数值合同内必须给出 measured。

## 边界分别意味着什么

| 情况 | 对包络的影响 | 当前入口 / M3 含义 |
|---|---|---|
| 被面引用的 NaN/Inf 坐标 | 有限欧氏表面前提缺失；有限首面和盒不能替代全量有限性 | 已展开对象在 `_capture` 611–621 检查世界坐标；被排除对象不展开。M3 166–180 检查引用坐标。没有实测 bpy 是否接受这些值、以及 NaN 经过实际范围归约的行为。 |
| 后续面索引越界或非三角数据 | 面集合可能未定义；需有效拓扑前提，不能仅归为“界太松” | `3 × polygon_count == loop_count` 是计数；若另信任每面至少三角的合法 mesh 不变量才可据此推出全为三角。M3 151–155 显式检查每面索引。未实测 bpy 创建/读取非法网格。 |
| 整体空网格/空表面 | 空集不会突破盒，但没有通常意义的有限表面距离 | 当前目录直接拒绝顶点不足或无 polygon；后续缺有效面也拒绝。不能把 empty 自动当成 measured 无穷远；也不能说“空”本身导致不包络。 |
| 有效索引、有限但共线/重复点三角 | 三角凸包依旧有界；不破坏已有正确顶点盒 | M3 195–197 按合同返回 `surface_degenerate_triangle`；首面无有效见证时不作排除。后续退化面可被首面采样遗漏，影响全场景 unknown 等价，交 M1 汇合。 |
| 有限孤立顶点 | 全顶点盒可能变大，仍安全；孤点不属于三角表面 | 不能拿未被面引用的孤点作 U 见证。当前首面三点避免这种见证错误；单凭盒不能区分孤点。 |
| 非有限孤立顶点 | 不一定破坏有效三角表面本身；但全顶点 bounds 的数值行为另需保证 | M3 只看引用顶点，host 全量捕获则检查所有顶点的世界坐标。两层合同不同。保守 gate 可以拒绝，不能因此宣称表面数学上必坏。 |
| 缓存过期 / bounds 与实际捕获网格不对应 | 即使盒有限、首面通过，也可能不再包住全部表面 | 是来源/状态前提问题。本轮只有条件反例，没有证明实际 Blender 正常 API 存在此 bug。 |
| M3 面数、配对、整数位数或期限预算不足 | 几何可能完全有限且有界；计算合同无法完成 | `surface_proximity.py` 144–147、166–207 与 budget 检查。应保留相应 unknown，不能推成包络失效或用少读结果冒充旧全域成功。 |

## 四个静态例子与未测边界

`static_examples.py` 仅标准库，四项断言全部通过，输入与推导可重放；`STATIC_RESULTS.json` 不含非标准 JSON NaN。

| ID | 证明到的事实 | 没有证明的事实 |
|---|---|---|
| later_nonfinite_reference | 首面有限且在有限盒内，不蕴含后续引用坐标有限 | 没有伪造 getter 如何处理 NaN 的实测结果 |
| same_counts_hypothetical_stale_box | 移动后续顶点可保持目录计数/首面不变，并落在旧盒外 | 没有声称 Blender 会漏标脏 |
| bounded_degenerate_face_and_isolated_finite_vertex | 退化面仍在盒内；孤点使盒变松而不成为表面见证 | 没有把 M3 unknown 改成 measured |
| later_invalid_index | 合计 loop 数和首面有效不能独立证明全部面索引有效 | 没有声称 bpy 正常网格允许此构造 |

旧 11 资产通过只支持那些具体原件的几何关系，不能增加到任意异常网格来源保证。本轮未追加资产、QA、样本次数或覆盖域，也未测试本机 getter/cache 实际行为。

## 唯一最小后续动作

建议根只考虑一个**同窗口宿主流式包络验证 gate**：对绑定的同一 evaluated mesh，逐点检查局部坐标并归约新鲜 min/max，逐面核三角结构及全部角索引。先核定本机 build 与上述普通静态 MESH 数据/副本路径对应；无法建立对应、来源变化、超时或不支持时保持未证明，不能借用旧盒给成功资格。该 gate 只保证来源与包络，不悄悄做完整 M3 或改变结果语义；本轮没有实现它。

这是 O(V + F) 的宿主内部读取，不能声称首次 getter 本来就 O(1)。官方 bounds 构建可能已在 C++ 内做 O(V) 扫描，但没有同时提供完整索引与有限性准入承诺；Python 逐点读取的实际成本尚未测，不能承诺新 gate 会更快。

即便需要扫描，仍可边读边归约，不保留全量 Python 坐标/面列表；可省被排除对象的额外 `to_mesh()` 副本、全部顶点世界变换、loop-triangle 物化、边数组/材质附加输出，以及完整几何 JSON 编码和传输。已有 evaluated 三角数据可逐面访问，不能把“读取全部坐标/索引”说成“必须全量 JSON”。这些是可省工作种类，不是新性能结论；若 wrapper/来源前提不成立，应保留对象或退出，不能通过省略校验取得收益。

交付边界：`acquisition_only_not_nearest_result` 保持原义；不开放默认入口、不恢复或替换 E/F、不重启已停止的预筛性能路线。由管理员与 M1 的条件化结果语义合并后，再决定是否实施这个 gate。
