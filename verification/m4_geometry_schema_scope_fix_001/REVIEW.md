# Geometry schema scope 修正复核

本次复核支持本项协议修正收口。通用 query 的 geometry 适用域已收紧到显式 target/candidates 的 task-set，两个登记反例得到准确拒绝，合法控制与旧缺省控制通过。复核读取源码及 r1 原件，另做纯 AST/字节分析，未重新执行产品、验证器、Blender 或性能测试。

## 唯一修正与简化决定

`live_spatial_mcp.py` 在 `_QUERY_SCHEMA.allOf` 末尾增加一个条件，geometry 属性存在时要求 mode、target、candidates，mode 固定为 task。两项必需关系事实和 objects 排除继续由现有 task-set 分支约束。

本次简化审查选择保留这一个 if/then 条件。它复用了现有分支，表达完整适用域所需的改动已经集中于一个 schema 节点。重新合并旧 oneOf、增设运行时校验或包装层都会扩大本次审查范围，当前没有需要这些变化的证据。

已独立从 Git `be2de48bd9656787c4cdfbc5767c2551defcaada` 读取原文件并与磁盘候选核对。旧文件 61485 B，新文件 61673 B，精确插入 188 B，前 7974 B 与后 53511 B 逐字节相同。新增条件与冻结结构相等，移除这个字典后，整个模块 AST 与旧版本严格相等。

原 MCP 文件 SHA-256 为 `b52f6468e6b71eb10b065a89b3417c1ee025e464b9be84d32b0b5625cd1b6275`，候选为 `0bb0733babb117a6ef6b0afc20bd451a700c347f047f867c4b10434d9222f326`。这项范围核验覆盖参数归一化、几何附件、绑定、缓存、求解与精简工具定义的原源码。SOURCE_DIFF 登记本批 137 源 canonical SHA-256 为 `4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c`。

## 定向控制与原件

r1 唯一执行记录为 4 个方法、20 个固定 query 案例、3 个 compact schema/validator 控制及 3 次内存宿主实际分发，全部通过，失败、异常和外部操作尝试为空。RESULTS.json SHA-256 为 `16ce7f2a7a4a906464469c3c41fa2d47617c88bb50b5d42ed942c1af0d69df40`。这些分母分别表示方法、输入和分发，不计为新资产覆盖。

- 登记的 overview+geometry 和 legacy objects/AABB+geometry 两个反例均由旧 schema 接受、由候选 schema 与实际 runtime 校验拒绝。geometry-only 的缺省 mode 反例也得到相同纠正。
- 合法 target/candidates 的 vertices、full+AABB 和缺省无 geometry 请求，schema 与 runtime 均接受。
- 缺 mode、target、candidates、requested_facts、必需事实，以及混用 legacy objects、域外事实、空 geometry 选择和非 boolean triangles，均准确拒绝。保存记录还核对实际错误原因与输入未被修改。
- 旧 overview、缺省 query、旧 task objects/AABB 和 nearest 在无 geometry 时继续接受，nearest+geometry 继续拒绝。
- compact OFF、vertices、full 的公开定义和实际校验通过。三个内存分发保持同一核心结果，几何字段对应原内存宿主数据，记录为 3 次原选定捕获、0 次 host write、0 次实际 RPC。

旧、新完整 compact schema 保存文件的 SHA-256 均为 `cfae9386aa77d610157d854d4e42f2c227fdfdac1dee30c8e78cb7702f48e6ac`，逐字节相同。当前控制足以覆盖本次适用域缺陷及相关旧分支，未发现要求扩大场景或重跑七会话的具体遗漏。

## 校验器与来源口径

旧 schema 由原 Git 字节中的实际赋值 AST 求值得到，引用的 selector 及常量由整模块减单节点相等核验支持。旧 validator 的 AST 和函数原文也与当前精确相等。实际 runtime 调用执行本次守护源码，`baseline_runtime_reexecuted=false` 清楚记录这一范围。

定向 evaluator 只提取原 `accepts` 函数，完整新旧 schema、所访关键词和案例结果均保存。未知受访关键词产生显式异常，并有对应控制。该工具明确声明 `full_JSON_Schema_validator=false`，本次结果覆盖固定案例经过的规则。

单一物理 snapshot 包含 137 源，原 verified loader 核验通过。当前源码、snapshot、测试、参考 evaluator 和冻结输入的保存前后字节检查均通过。身份标为 `unregistered_runtime`。本批新增安装及业务进程数量均为 0。

EDIT_RECORD 保留了首次 CRLF 锚点断言退出，记录确认该次发生在产品写入前，随后按实际 LF 唯一位置插入。r1 的首轮有效运行全通过，预期拒绝案例完整保留。本次没有删除或覆盖前批失败、来源纠正及性能原件。

## 判定边界

本项通过表示已修正公开 geometry 字段适用域，并验证固定合法与旧控制。原 a81 候选默认暖延时约 +3.57% 的未决结果继续有效，完整准入仍保持未通过。本批没有性能重采样、实际新安装/stdio/Blender 验收或模型消费，不能将前批运行记录拼为新 canonical 版本的完整验收。

没有发现阻塞本最小 schema 修正提交与回报的具体问题。完成本次审查后停止该子任务，由主会记录最终提交并回报管理员。
