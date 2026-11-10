# SCALE-OPT-001：精确整数位宽检查的单一候选

2026-11-10。本批依管理员 `64a6001b976230a21eb121ad031ed8302f011df8` 的 ROOT_REVIEW / SCALE_OPT_001 合同实施，父提交为 `b39a5d9f58aed2782225287738413982beac4920`。唯一产品变化是surface_proximity._bounded中4行builtin int快路径；未改位宽、叶算法、遍历顺序、准入、缓存、方法版本、默认MCP/Hook配置。当前桌面默认旧插件与隔离基线并非同版，本文成绩只对应下面的实际隔离安装。后续默认切换由管理员按用户已有授权独立执行。

## 判定

工程目标（D48 cold完整入口及T整链中位各减少至少25%）均达到；固定78格全部保留，一次正式交错执行，没有补刷、替换场景或第三候选。旧O正确完成30/39，新C为32/39。最终接纳与部署交管理员复核，本报告不宣称p95、全部复杂域或大模型端到端收益。

- D48 cold入口：O 18.825541秒 → C 7.927205秒，减少57.89%。
- T整链中位：O 121.193847秒 → C 49.674981秒，减少59.01%。整链包含原setup、必要读取、管理变化/重载、原始证据发布与清理；新增wrapper全成本及进程全耗时另列。

## 为何只改这4行

根复核纠正了此前工作计数的口径：D48 N54824是实际叶，而P169200包括遍历和剔除，P实际intersection_tests为54871，叶数近似相同，不能据此声称BVH少三倍精算。根单pair cProfile发现大量_bounded/Fraction ABC类型判断。本候选只让`type(value) is int`直接检查一次既有MAX_BITS=4096的bit_length并原样返回；负整数bit_length与abs后的位数相同，恒为1的分母不必重复检查。bool、整数子类、Fraction及其他类型继续旧分支。根noop checkpoint配对探针仅是方向依据，不冒充真实入口成绩。

## 源码、wheel与实际安装

- O canonical `a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b`，实际Python `C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe\.plugin_ab_runtime\B\venv\Scripts\python.exe`，installed_root `C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe\.plugin_ab_runtime\B\venv\Lib\site-packages`。
- C canonical `3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd`，实际Python `C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe\.scale_opt_001_runtime\candidate\venv\Scripts\python.exe`，installed_root `C:\Users\Administrator\.codex\worktrees\m4-single-pass-acquisition\hefe\.scale_opt_001_runtime\candidate\venv\Lib\site-packages`。

新候选实际构建wheel并在 `.scale_opt_001_runtime` 新venv离线安装；O直接复用旧 `.plugin_ab_runtime/B`，没有复制旧安装或旧证据进入新批。NumPy2.3.5/Pillow12.3.0一致，BASE_VERSION/IMPLEMENTATION_REVISION/METHOD不变。137源在候选工作区快照、wheel和实际site-packages逐字节一致；相对O只surface_proximity.py变化，实际isolated来源为installed_distribution。INSTALLS及每链IDENTITY记录完整绑定。旧/新canonical按源码正常变化，没有复用旧身份。

## 正确性：不把旧断言冲突改成绿灯

107项边界/类型/返回对象身份/异常类型message及args均与git d01原函数等价；含0、负数、4096位边界及越界、Fraction、bool、整数子类陷阱。surface现有测试没有修改MAX_BITS；deformation_anchors的patch8属于另一模块。五个冻结pair完整surface返回（含unknown原因、exact rank和全部work）旧新相等；四个正常closed-solid的分离、接触、穿插、包含完整返回也相等。

193项既有回归新旧均191通过、同2失败，零新增差异；原始红灯保留，没有改旧测试使它们通过。独立复查表明：(1) test_task_query旧断言要求只读task清空动作sessions，与当前ReadContext“动作账本原样不触碰”合同相反，不能由账本仍存在推断它被用于读请求授权；(2) exact_rank旧测试仍把共线三角形当unknown，与d01已有hulls_v3的segment hull合同相反。当前resident-task12及degenerate-hulls12实际24/24通过。其测试后来源审计因verification fixture位于workspace root的布局报错，runner_completed/post_test_audit_passed均为false；该失败保留，不能声称这次审计全绿。安装与正式运行的137源核验另外独立通过。

早期自编回归wrapper存在box helper参数错误及AST查找class method错误，均为正式采样前的测试准备错误，原件/纠正记录保留；有效box对照使用明确center/size参数。没有因此改产品、重试未知动作或替换性能样本。最终来源见REGRESSION_REVIEW、REGRESSIONS_CANDIDATE/BASELINE、CURRENT_CONTRACT_REGRESSIONS与BOUNDED_EQUIVALENCE。

## 固定实验与全部静态结果

只引用SCALE-DIAG-001的五份blend、12份最终worldmesh及独立599对oracle，不复制它们。六静态格各组一冷两暖；T7各组三轮。九个配对区块按O,C / C,O交替，18条独立链、每组39格共78实际逻辑请求。每链独立cold/缓存，轮内保持本路状态，原期限30秒、worker570秒不变。每轮同一初态、同等变化信息和fullmesh回读。没有重跑Native或LLM消费者。

以下单位毫秒。setup只计首次，cold合计为入口+setup；暖栏为两次全部值，退出耗时不是正确任务的速度。

|格|组|正确/3|cold入口|setup|cold合计|warm两次|状态|
|---|---|---:|---:|---:|---:|---|---|
|G_low|O|3/3|358.857|1026.574|1385.431|15.020 / 14.934|complete_correct, complete_correct, complete_correct|
|G_low|C|3/3|193.402|964.500|1157.901|14.891 / 14.752|complete_correct, complete_correct, complete_correct|
|G_mid|O|0/3|64.294|1001.100|1065.394|21.886 / 44.009|unknown, unknown, unknown|
|G_mid|C|0/3|66.975|1494.786|1561.761|21.756 / 22.256|unknown, unknown, unknown|
|G_high|O|0/3|233.049|1176.953|1410.001|102.693 / 94.180|unknown, unknown, unknown|
|G_high|C|0/3|256.781|1104.367|1361.148|104.030 / 97.946|unknown, unknown, unknown|
|D_low|O|3/3|3205.683|967.754|4173.436|17.743 / 22.036|complete_correct, complete_correct, complete_correct|
|D_low|C|3/3|1303.087|962.745|2265.833|17.687 / 21.829|complete_correct, complete_correct, complete_correct|
|D_mid|O|3/3|18825.541|1037.447|19862.988|42.953 / 52.783|complete_correct, complete_correct, complete_correct|
|D_mid|C|3/3|7927.205|1026.760|8953.965|42.199 / 52.331|complete_correct, complete_correct, complete_correct|
|D_high|O|0/3|29986.795|1184.013|31170.808|29996.469 / 29993.240|expired, expired, expired|
|D_high|C|2/3|29996.923|1213.082|31210.005|12390.817 / 169.846|expired, complete_correct, complete_correct|

G508/G4092的surface/closed-solid原准入原因均保持unknown，本候选不扩大可用几何域。D192首次冷读两版仍超时，C仅两个暖请求完成，没有通过提高期限使其完成。源码/身份不同和trace/scene代际不能要求逐字节相等；来源绑定分别核对，几何事实、可比较的见证/原因/工作计数另独立检查。

## T七步、所有整链成本

|步骤|O入口中位ms|C入口中位ms|O/C内核调用数（三轮）|
|---|---:|---:|---|
|0 初读|19141.063|7702.214|[47, 47, 47] / [47, 47, 47]|
|1 原样复读|54.436|54.017|[0, 0, 0] / [0, 0, 0]|
|2 仅改名|19797.797|7379.961|[47, 47, 47] / [47, 47, 47]|
|3 移动竞争件|20148.831|8023.751|[47, 47, 47] / [47, 47, 47]|
|4 局部网格修改|19887.127|8013.824|[47, 47, 47] / [47, 47, 47]|
|5 删除竞争件|20192.238|8020.504|[46, 46, 46] / [46, 46, 46]|
|6 重载初态|20181.984|7952.974|[47, 47, 47] / [47, 47, 47]|

沿用原整链：O [121.621718, 121.099169, 121.193847]秒，中位121.193847秒；C [49.044153, 49.674981, 49.900962]秒，中位49.674981秒。

加新wrapper的整链：O [121.639186, 121.117236, 121.211531]秒，中位121.211531秒；C [49.061661, 49.692298, 49.918436]秒，中位49.692298秒。

加子进程启动/退出的全进程：O [121.753987, 121.242769, 121.329208]秒，中位121.329208秒；C [49.182803, 49.808401, 50.034764]秒，中位49.808401秒。

D192新C第一次完整回答之前，已支付首读expired 29.996923秒与第二次请求12.390817秒，累计入口42.387740秒，setup另计；第三次为0.169846秒。两个完成格是连续暖状态收益，不能冒充两次独立cold成功。

每组T只有同一固定资产的三次重复，不是三个未见资产，不推断p95。M2宽失效未修改，改名、局部编辑和删除仍会重做未变化配对；实际每步调用数已列出。没有把数学快路径改名为新的空间理解、训练或小脑能力。

## 独立评分、工作与物理开销

独立QUALITY_REVIEW核对FREEZE/INSTALLS、实际来源、18初态及42次T全字段状态/receipt，使用原oracle外向L/U，精度1e-6米；不使用已知可能少报半ulp的中点半宽字段。每格是否完整/数值/最近者/闭体分别评分。LEDGER/原始MEASUREMENT保留全部值、inclusive阶段、目录/资源展开/decoder/缓存记账、socket实测字节、响应编码和actor/Blender RSS。可比较的O/C全几何事实、见证、原因及surface工作量都核对；O超时而C成功时作为任务完成变化而非假等价。

阶段为inclusive不可相加。triangle_pairs是遍历，intersection_tests才是本产品实际叶；计数口径不跨Native强行比较。超时当前内核未返回的工作量未知，已返回调用之和是下界。source/expanded计数描述采集规模，不冒充每次新to_mesh；未暴露的宿主内部目录/求值耗时仍未测。scene_cache.accounted_bytes、数组nbytes、ReadContext/decoder缓存与进程生涯peak RSS不是同一口径。


D48首次完整入口的实际分段（inclusive，不相加）：

|组|capture ms|decode/world ms|nearest loop ms|遍历triangle_pairs|实际叶intersection_tests|
|---|---:|---:|---:|---:|---:|
|O|145.189|9.386|18497.648|169200|54871|
|C|129.391|9.299|7667.122|169200|54871|

物理计数（各项有包含关系，不混作逻辑分母）：`{"capture_task": 18, "worker_request_events": 192, "initial_readbacks": 18, "T_readbacks": 42, "coordinator_mutations": 36, "close_attempts": 18, "capture_nearest_candidates": 60}`。78次逻辑请求外，18初态读取、42次T读取、36协调变更、18关闭共192次协调层尝试；原始worker event另核对。tokens/费用N/A，协调模型准备/复核成本未暴露，单列未测。

## 剩余范围与交付

本批收益来自去掉重复整数类型/位数开销，精算叶、精度、遍历、缓存及几何准入未扩大。余下主要成本仍是距离遍历中每叶精确算术，M2整场景失效继续反复触发它；G中高档准入与D大目录的期限出口继续按实测保留。这些不在本批混改，也不在此自动开启第三候选。

根将独立复核后决定接纳与默认插件部署。当前用户已授权后续最新版切换，但本批没有改默认MCP、Hook、共享GUI或原资产。所有Blender只在owned后台测试副本，进程清理见CLEANUP；新candidate wheel/venv保留在ignored runtime供管理员核查/后续安装，旧O保持。当前AL无合法绑定（host_epoch5/context_bound=false/rebind_required=true），未借他聊天句柄登记，状态待合法重绑同步。

回放：FREEZE绑定单一候选及共享输入，measurements保留原一次执行，不在封存目录重跑覆盖；analysis与独立quality脚本仅用于重算。SEAL为新批文件和产品surface源码绑定，旧证据及安装只引用。完成后发送SCALE-OPT-001_COMPLETE并结束实施批，不自行开启下一方向。
