# OPT1 配对成本与完整生命周期上界：独立复核

结论：按根预登记公式重算，五项工程成本门成立。完整生命周期的五个配对比值中位可以由 **0.7537327451783967 的保守上界**判门；精确 full 中位未测。`0.743986174814158` 是终止于最终 RESULTS 写盘前的 prefix 比值中位，不能标为精确完整生命周期。

本审按自身 Agent Learning 句柄读取 assignment `43cadbe2-7eee-4ce6-912a-33cad43c3ac4`；父任务 `2ceda2c3-5d8c-4544-8471-d6807eb70579` / revision 1。使用 learning-worker 既有工作边界。新写标准库 `recompute.py`，未执行作者 summary/audit，没有导入产品；新增 Blender、消费者、网络业务 API 为0，未修改实施树或 Git。

## 固定证据与实际范围

交付固定 `860b87138d40de9cc08b01c947dd864d58da9295`。读取主十个序列全部30请求的原始 receipt、stdio TX/RX、audit、worker计数、70次物理host wire及索引，另读Process三状态和预登记/控制器/准备。最终 **330 个实际使用文件**逐份SHA/字节和Git blob核对，**1781条断言**通过。检查数量不是独立实验数，实际仍是一个装配、两个状态、五组A/B配对及一个另列Process序列。

专业几何真值、完整安装来源、全部失效反例由根其他分项复核；本审不以成本通过替代这些验收。没有用作者“passed”单独判定业务计量：实际时界、收到的原始字节、trace、work增量和退出分别核对。

## 预登记公式逐项复算

固定顺序 AB、BA、AB、BA、AB，每版本 fresh owned Blender/产品进程，cold→repeat→EDIT。30计划行均出现一次；未发现错误、自动重试或新增样本。全部客户端原始 ended−started 与保存的完整请求值一致；stdio receipt/TX/RX、公开body、唯一audit trace和observe相互一致。

| 指标 | 独立实际值 | 原门 | 结论 |
| --- | ---: | ---: | --- |
| median(B_edit/A_edit) | 0.09318891694666472 | ≤0.70 | 通过 |
| median(B_cold−A_cold) | +9.4775 ms | ≤88.26019 ms | 通过 |
| median(B_repeat−A_repeat) | +1.6160 ms | ≤2.04959 ms | 通过 |
| median(三业务B总和/A总和) | 0.5630416534311025 | <1 | 通过 |
| median(完整序列B/A)上界 | 0.7537327451783967 | ≤1.05 | 保守证明通过 |

差值门的 allowance 精确按 `max(0.05*median(A),2ms)` 计算，没有把中位差换成中位数之差，也没有用两个单独中位数相除判比值门。

| 配对 | A cold/repeat/edit，ms | B cold/repeat/edit，ms |
| --- | --- | --- |
| 1 | 1779.8854 / 41.6520 / 1705.4856 | 1799.0802 / 43.2680 / 160.1133 |
| 2 | 1765.2038 / 40.3287 / 1696.2618 | 1774.6813 / 40.9959 / 158.0728 |
| 3 | 1763.4408 / 40.2833 / 1710.8078 | 1762.2169 / 41.8994 / 160.3426 |
| 4 | 1757.9456 / 41.2554 / 1723.8197 | 1770.6125 / 54.1106 / 158.8843 |
| 5 | 1769.5204 / 40.9918 / 1723.9927 | 1771.8144 / 41.8090 / 158.1132 |

第4组repeat增加12.8552ms保留，不能从五组中位门推出每次都不退化或尾部改善。EDIT配对中位降低约90.6811%，三业务和约43.6958%；这是固定工程序列，不是模型端到端收益。

单独请求中位A/B：cold1765.2038/1771.8144ms，repeat40.9918/41.8994ms，edit1710.8078/158.8843ms。server trace中位分别为1761.6375/1769.5308、38.9467/39.6708、1705.5929/156.6291ms；其包含外层wire_encode和stdio_write，audit writer另标排除。客户端还包含Peer记录I/O，后续质量核验及最终RESULTS写盘不在请求窗口内。

## 为什么完整中位上界证明有效

独立读 `sequence.py`、`run_pairs.py`、`common.py` 并核它们与运行前INPUT_BINDINGS及HARNESS_FREEZE的哈希，检查如下真实顺序：

1. 同一串行controller内，`run_sequence` 用 `time.perf_counter_ns()` 记录开始。
2. 其 finally 在已完成退出、原件enrich及输入复核后记录 `ended_ns`。这是prefix终点。
3. 随后同步调用 `save(RESULTS.json)`；save在with文件块内编码、写入并关闭，返回以后才返回run_sequence。
4. controller等该调用返回，再启动下一序列。没有异步spawn下一个sequence。因此下一序列start在前序最终save关闭之后。相邻原件时间也全部严格有序。

设A、B真实完整时长为a、b，已保存prefix为a₀、b₀；则a≥a₀。对有下一序列的B，`next_start−B_start` 给b的上界u，因此 `b/a≤u/a₀`。全部时间由同一个controller的同一单调时钟取得，没有混用UTC或两个无关进程时钟。这里的完整结束是既有文件API同步写关完成，不声称物理介质fsync持久化。

| 组 | A prefix下界ns | B完整上界ns | B尾部上界ns | 配对比值上界 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 5903523800 | 4449679200 | 22795000 | 0.7537327451783967 |
| 2 | 5955839500 | 4368469800 | 22990600 | 0.7334767500030852 |
| 3 | 5862749400 | 4386291400 | 24486900 | 0.7481628670671135 |
| 4 | 5857246800 | 4464478400 | 23804000 | 0.7622144929935340 |
| 5 | 已计prefix | 未设有限上界 | 未测 | +∞ |

逐分量上界保持次序统计量不等式。五个比值中位是第三顺位；保留第五个+∞后，四个有限上界中的第三小值就是 `22248396/29517619`。所以全部五组的真实full比值中位≤该数<1<1.05。没有删第五组，也不需要知道第五组尾部精确值。

该证明支持原门和本五组**配对中位**下降，不证明每一组full时长下降、精确full中位、整个批次总用时或未来尾部。尤其不能把未知第五B尾部带来的总和缺口隐藏掉。原报告主表“完整序列计量窗口0.743986”建议改标prefix；正文后续上界解释本身成立。

## 机制、容量和成本搬移检查

每请求恰好一个host执行，主每序列7个物理请求（扫描3、QA导出2、登记修改1、关闭1），十序列共70。实际worker before/after累计工作与host packet、audit residency_delta一致；enabled/resident_resources是状态量，不作为累计工作相减。

每A新核112/0/114，每B112/0/10。五B的每个EDIT都独立逐pair核：104命中键与本组cold相同、无Obj_008参与、核计数0；10 miss均涉及Obj_008且键改变或是新候选、核计数1。仅该104/10映射并不替代键来源源码安全审计。

B cold前measurement entries/computations/accounted_bytes均为0，cold后112项/181984B，EDIT后122项/198307B、命中104。配置保持2MiB/256项。cold112新核证明没有在metadata/QA预填本轮测量；序列源码显示metadata阶段零host RPC，首次QA是原生只读快照。A没有对应cache telemetry，不能把B字段反推为A实测；A容量由固定源码/来源审承担。

宿主资源读取与变换仍为cold530点978面/变换530点，repeat0/0，EDIT资源读取0、变换8点。两组MCP公开wire相同：37492/37496/37979B。宿主wire：A247339/98398/98377B，B249135/98398/98377B；B冷态增加1796B，已进入请求计时。没有靠缩短答案或减少匹配取胜。

EDIT后runtime工作集中位A63299584B、B63266816B，差异32768B，未作为内存收益。峰值是进程生存期峰值，原measurement accounted bytes也明确排除临时工作；没有用RSS证明无临时分配。启动、QA、质量核查和退出均在prefix内，原字段另列，父子区间不相加。

准备另列：旧安装4.0393977s，新安装4.0792139s。历史oracle从原started/ended相减为79.7306697s，其elapsed字段79.7306699s多200ns；源码连续两次采时解释该差异。本报告保留两个字段，不影响任何本轮预登记门。最终离线summary/分析属于整批额外准备/审计，非单个sequence；完整批次总时长仍未由此证明。

Process三次另列：1744.2806/19.6012/146.9373ms，核112/0/10，均一次host RPC；实际stdin含capabilities、三scan、shutdown及三个显式QA命令。该路径无独立A/B成本配对，不混入五组门。主产品/Blender退出回执和Process进程/读线程回收有证据。

## 保留的本审错误与未测

本审第一次错误把worker enabled/resident_resources状态量纳入累计delta等值比较，修正为明确工作计数后重跑；第二次要求历史oracle elapsed与两端点严格相等，发现200ns不同采时后保留原字段改为双列。`FAILED.json`、`FAILED_2.json`保留。另一次Windows rg带shell glob查找失败随即用目录加glob过滤修正。这些不是产品运行失败，没有因此重跑任何业务或删结果。

首个失败的精确原件是1A cold：worker before为空列表，after有enabled=true和resident_resources=24；初版相减产生两个多余键enabled=1、resident_resources=24。其余18个工作计数与host residency_delta完全相等，包括resource_builds=24、resource_vertices_read=530、resource_faces_read=978、world_vertices_transformed=530和scan_bound_tests=276。因此这里不是QA累积窗口差异，更不是产品漏记工作；修正只移除两个非工作状态字段，未移除不匹配的工作计数，最终30请求均按各自worker before/after独立核对。历史oracle差异的源码依据为qualification/oracle.py末尾给ended_ns和elapsed_ns连续两次调用perf_counter_ns；本审不再断言这两次采样应该严格相等。

本轮没有重测224项作者回归、实际网络阻塞、Google/模型费用、模型质量或跨场景性能。保留根已知传输等待、隐藏来源和旧g06；这些不会因当前成本门通过而自动关闭。

产物：`recompute.py`、`RESULTS.json`、`CHECKS.json`、`SOURCES.json`。原件不改，所有新文件仅在本根复核cost目录。
