# 源码与验证材料复核

本次只读检查固定候选 `a81e530a`、三个产品文件、离线 b2/c2 原件、新定向测试及当前实际入口 harness。候选包含 137 个运行源码，canonical SHA-256 为 `9f287f28a9be9ad0a06c0689b1fda3b15e9181efae0e280c0f2bcfed2d3ef504`。基线为 `0bcd1660`，canonical 为 `53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732`。

本次审查仅新增本文，读取保存的 JSON 做两项默认结果精确比较。产品、Blender、安装、离线测试和实际入口均由其授权执行者运行，本审查没有重跑。

## 字段与来源

`geometry` 经过现有 task-set 归一化。缺省关闭，显式对象集合限制为 1..4 个既有 selector，`include_triangles` 为严格 boolean。普通 task-set 桥接和精简关系工具使用相同归一化。legacy pair/AABB 及 nearest 的运行时入口继续拒绝该选项。

原 target/candidates 决定宿主选择及关系求解。投影复用 `result.binding.objects`，成功绑定仅按 object ID 去重检查别名歧义，输出保留 geometry 请求顺序和重复。原 exact unresolved selector 优先于成功对象的 name alias，既有歧义和未找到理由得以保留。不同 ID 的同名对象产生未知行。集合外 selector 被拒绝，既有捕获范围保持原 target/candidates 集合。

顶点与可选三角片直接来自本次归一化 mesh 的数组，坐标已经处于世界米。输出使用新建普通列表，三角片保持原顺序并索引同一顶点数组。源版本、指纹、宿主身份、单位和坐标系沿用关系结果公共绑定。顶点投影没有重新施加矩阵或 scale。

## 暂留与默认路径

显示选项在进入 ReadContext 的关系 key 前被分离，capture selectors 与 selection key 仍取原查询对象。`ReadContext.result` 在冷、暖路径都返回 detached copy，geometry 在锁内附加到此返回值，随后执行原来源绑定。新数组和新字典不进入关系结果缓存。

默认路径跳过 geometry helper、对象别名解析、数组转换和 geometry contract 构造。参数存在性及查询形状检查有少量新增工作，实际耗时应由固定入口测量报告。

已独立读取 b2/c2 的 `default_cold`、`default_warm` 保存结果，先分别确认完整 baseline/candidate runtime source SHA，仅将这一已核身份字段替换为共同标记并移除瞬态 trace_id。其余全部结果字段严格相等，两版 geometry 均缺省，counts 和 residency_delta 也逐值相等。没有删除未知、来源状态、几何事实或诊断字段来获得相等。

## 离线原件

| 原件 | 结果与范围 |
|---|---|
| offline/b2/RESULTS.json | 22 个登记方法，8 个 candidate-only skip，其余 14 个执行通过 |
| offline/c2/RESULTS.json | 22 个方法全部执行通过，零失败与异常 |
| b2/c2 EXECUTION_IDENTITY.json | 137 源守护加载核验通过，checkout、测试与所读旧证据的字节保持检查均为 true |
| tests/test_selected_geometry.py | SHA-256 `6999e1d5bd2f42d117ac108a2966423c1ae0fa988eb2c9aba653af0222212338` |
| offline/run_offline.py | SHA-256 `e44fb7bb07f73e57f418927fecee6358e7f316b603b31564bf547d7654cc8a56` |

新测试的世界坐标期望由 raw vertex.co、实际 matrix_world 和单位的 Fraction 前向表达式给出。固定 RNA 使用可精确表示的变换及 scale。三角片期望直接取实际 loop_triangles 的原顺序，覆盖了原 polygon 与捕获三角片的区别。生产几何返回没有用来生成这些期望。

实际记录覆盖原 unknown 优先级、同 ID 多次绑定、不同 ID 同名、子集和请求重排、单位、可选三角片、缺省无投影、冷态等工作量、暖态切换、返回值修改隔离，以及姿态和局部网格变化后的新证据。集合外请求断言只捕获原关系对象。原 minimum/name-ID 方法同时覆盖 nearest 等价，其他旧方法覆盖来源拒绝及 ReadContext 失效。

c1 的三项失败及初版测试保留完整。三项均停止于公共 call helper 将 wholly unknown 结果错误预期为 isError=false 的断言。修订将该断言对应到既有 observed/partial 与 unknown 的传输语义，原几何、歧义和关系断言继续执行。产品源码在这一 QA 修订期间固定。

离线结果的身份声明是 guarded physical source snapshot、fake RNA 和实际内核。实际 installed/stdin/Blender 的来源与成本由后续受控入口材料给出。

## 实际入口 harness 静态检查

当前 `entry/run_entry.py` 直接复用既有 Peer stdio 客户端与 owned NativeSession，仅在独占测试副本加入固定 QA instrumentation 和登记变更。七个成功会话及最多十次启动预约有固定边界。产品先关闭，随后关闭并回收 owned Blender，失败和关闭错误写入结果。默认资产、源码 pin、实际 initialize 的 installed_distribution 身份及两个公开工具均有检查。

原生补读通过 evaluated_get/to_mesh 独立取得实际局部顶点、实际求值矩阵、单位与 loop_triangles。打印的几何字段与产品附件使用相同布局和精度，cold/changed 的 QA 事件另存原始 local/matrix/scale/triangle 材料，支持独立前向复核。当前几何 expected 来源是这一独立宿主读取。名义刚体变换与实际矩阵写回误差、旧冻结来源对应及真实世界坐标证明由主会核对。

harness 保存每次原请求、原返回、stdio TX/RX、计时、worker 事件、host residency 增量和关系诊断。同状态 core 比较只去 geometry 与瞬态 trace。原生补读成本单独登记，完整工程成本需计入该额外读取。QA profiling 的回调开销包含在实际测量范围内。

## 实际工程门限仍待 analysis gate

当前 harness 的 run_case passed 主要检查返回事实、geometry 对照、会话时界和退出清理。它收集 RPC、捕获、to_mesh、triangulation、world preparation、内核和 cache hit，但尚不能仅凭这个 passed 宣称所有计数门限通过。

冻结后的分析应从保存原件逐项核实冷态原有工作、同代显示切换的新增工作为零、暖关系缓存命中，以及登记变更后的新代关系和几何。跨 baseline/candidate 的实际默认结果也需精确核身份后比较，仅允许 runtime identity 和瞬态 trace 的明确差异。主会已将该 analysis gate 交给独立后处理任务。

已有 task_work 的 engine_invoked 与 kernel/result-cache 语义保持一致。暖 geometry 请求即使 engine_invoked=false，仍有列表转换与序列化成本，完整成本应由实际入口计时和字节表展示。

## 当前判定

本次源码与离线材料未发现阻塞候选冻结的具体问题。字段来源、子集绑定、未知优先级、默认结果及缓存隔离均有代码依据和定向原件。实际工程验收等待唯一受控入口与 analysis gate 的保存证据，模型消费和整任务收益保持待验证状态。本文到此结束审查子任务。
