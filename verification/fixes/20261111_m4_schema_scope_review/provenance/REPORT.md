# Schema适用域修复：来源复核及一次归因设计复核

接受 `00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4` 的有限来源/改动范围核验。它确实只修改通用query schema的一个适用域条件；不是新的几何算法或性能修复。旧a81默认暖延时增加1.341ms的未决结果继续保留，新4eb来源未获得安装、真实入口、性能或完整准入。

## 实际独立核验

本子审以只读Git、文件摘要及静态AST重算，未执行验证器、项目模块、产品、Blender、模型或新性能测试。`audit.py`和`audit.json`保存在本目录，首次运行**622项机械检查通过、0失败**。

| 核查 | 独立结果 |
|---|---|
| INDEX成员 | 159个唯一成员，4,267,582B；加INDEX/SCHEMA_FIX_READY为161文件 |
| Git/磁盘/集合 | 161/161精确一致；长度及SHA一致；按已声明规则排除本地bytecode |
| 运行源 | 137个；固定Git、工作树、r1/e执行快照逐字节一致 |
| canonical | 独立按静态版本常量与完整manifest重算为`4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c` |
| 旧基线 | be2de48b的137源与a81e530a相同；9f28旧来源绑定没有混入e077 |
| 产品变化 | 仅`human_eye_plugin/live_spatial_mcp.py`变化，其他136源不变 |
| 字节边界 | 一次精确锚点替换可将旧文件变成新文件，增加188B |
| AST边界 | 仅移除新增`_QUERY_SCHEMA.allOf`末尾条件后，整个模块AST与旧版相等 |
| 精简schema | 保存的BASELINE/CANDIDATE_COMPACT_SCHEMAS逐字节相同 |
| 执行绑定 | runner、tests、SOURCE_DIFF、WORK_ORDER、137快照与EXECUTION_IDENTITY摘要对应 |
| 历史证据 | be2de48b→00b13060对上一1976文件批目录的Git diff为空；旧EVIDENCE_READY仍记默认37.53295→38.87395ms、full_admission=false |

新增条件是“出现geometry时要求mode、target和candidates，mode必须为task”。现有task分支继续约束必需facts和禁止旧objects混用。范围核验支持运行时校验函数、缓存、绑定、求解和精简工具定义均未改；不把该结论扩大为新来源已经跑过实际安装或Blender。

既有r1记录为4个测试方法、20固定通用query、3组compact控制、3次内存宿主派发，错误/失败为空。这是作者保存的执行记录，本子审核对了原件身份及分母，**未重跑这些测试**。有限规则求值器不能当作完整JSON Schema标准验证器，基线运行时也未重新执行。相关行为独立深审由本轮其他子审负责。

旧CRLF编辑锚点失败的说明仍在EDIT_RECORD，修正发生前断言阻止写入；没有用它冒充产品失败。旧unknown预期、binary32预期和分析脚本错误均在上批Git原件中保留。本子审没有再次重算旧1976文件的全部磁盘摘要，不将Git历史未变夸称成重复执行旧验收。

复现：

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 'D:/hefe/verification/fixes/20261111_m4_schema_scope_review/provenance/audit.py' --output 'D:/hefe/verification/fixes/20261111_m4_schema_scope_review/provenance/audit_recheck.json'
```

## 一次默认延时归因计划：建议采用，限定其回答范围

已读取 `D:/hefe/docs/M4_DEFAULT_LATENCY_ATTRIBUTION_001_PLAN.md`。它有新的信息增量：旧测试baseline/candidate存在不同请求历史，且全部启用QA profiler；新计划固定同一OFF业务历史，再在各进程内对比callback ON/OFF。因而不是只换名字重复旧矩阵。

选择精确旧版本对是合理的：B=e077/53db，C=a81/9f28，直接复用已核验隔离安装。当前schema修复4eb不混入实验，避免将新来源与旧延时数据拼接；即使实验有利，也不会证明4eb已经完成同版本安装/入口验收。

计划四会话B、C、C、B。每会话1个cold、1个预热，profiler均OFF；随后10组ON/OFF配对，每种先后顺序各5组，B/C各有一场相反起始序列。合计88个关系请求；关闭、必要初始化与完整准备成本另记。此规模足够得到**限定资产/请求中的profiling影响和源版本差异描述**，不足以证明生产等价、稳定尾延时或总体无回归。无需为这项有限问题自动扩成8会话。

程序必须只切callback，不能关闭整个QA helper。原先`before_rpc`的host_work、指纹、保护、计时、输出及`after_rpc`回执都保留；每次仍建立相同基础state和计量边界。OFF的Python/C callback计数应写未采集，不能写“0次实际工作”。完整profile_scope包含宿主业务，不能从入口耗时中整段扣掉。ON/OFF产生的计数输出差异也应保留在实际成本中，而不是声称测得纯callback CPU纳秒数。

**唯一建议补明确的退出细节**：若`sys.getprofile()`初始已有非本实验callback，或调用结束后无法恢复相同初始状态，无法将该段解释为本实验的ON/OFF。应保留记录并停止矩阵，不通过清掉其他profiler后继续来补救。其余错误/状态变更/资源冲突停止条件已在计划里写明。

进程内交叉仍有carryover：ON产生的临时分配、GC/缓存变化或耗时可影响下一次OFF；顺序平衡有助发现和部分抵消，但不会数学消除。计划要求按配对位置、前一profile状态及会话分组展示，正确保留了该限制。不要额外插入未登记“洗掉状态”的请求，也不要强制GC直到结果更好。若顺序效应明显，一轮结论应是尚不能归因，随后封存停止。

源版本的独立比较单位只有4会话、每版2会话；40次测量请求/版本不能当40个独立重复。不显著不等于等价。应同时给每会话ON/OFF原始样本、配对差和版本差，并明确以下可能出口：

- 差异在同一业务历史、profiler关闭时仍出现：保留具体区间和源码身份，说明新的定位线索；仍不能仅凭小样本认定某行代码有错。
- 差异明显依赖profile或请求位置：证明旧数字受此条件影响；不能倒写为生产无回归。
- 仍有会话波动/交互或结果矛盾：本次归因未解决，按一次性规则停止，不继续补样本。

计划没有新增百分比容忍线，不用统计不显著宣称通过；原批不准入结论不变。结束只回报归因，由根决定是否值得一个具体最小修复或继续保留候选，不自动进入消费者、Hook或默认发布。当前没有理由将schema修复再改写成性能优化任务。

本轮已用自己的Agent Learning句柄读取绑定，看到父任务revision8/write555及parent_read_only；子assignment仍为旧revision2，未冒用/改写父任务。本次行为依本轮明确委派限于只读复核和自己的审核文件。
