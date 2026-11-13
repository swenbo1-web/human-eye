# FIX1 capture 阶段独立复核

2026-11-13，固定交付 `1875bf45c09e8cca606f4de3fd8f0e821cc0d8a5`。父任务 `68dc02bb-4913-406a-bf20-63b873071fac` revision 1 / write 622；子代理旧 AL assignment 仍旧，未借用父句柄。只读作者材料，未运行作者整套 checker、产品、Blender、模型或 API，未修改作者文件。

**推荐将数值/事实资格移至唯一 finish 确认之后，复用现有 WIRE reader。在线 call reader 可以修复当前缺文件问题，但本任务没有必要新增这条证据路径。** 三轮都是预登记只读扫描；下一轮不读取上一轮 facts/kernel/matches，唯一 EDIT 为固定外层姿态变更，具备独立在线回读。因此没有发现后验方案的执行依赖阻碍。

## 已核实的发布顺序

固定 `pose_native_metered.py` 的实际 SHA 与本次 `owner/native/CONFIG.json.helper_sha256` 一致。源码顺序为：

| 阶段 | 行 | 已完成的动作 |
| --- | ---: | --- |
| 执行前 | 319 | SCRIPT.py write_text 返回，文件已关闭 |
| 执行后 | 326 | stdout/stderr write_text 返回，文件已关闭 |
| 终态记录 | 331–336 | 脚本 SHA、原输出长度、状态及保护结果 |
| 事件发布 | 345–346 | finish_rpc 仅收集内存计量；append 调用 flush/fsync（函数24–25） |
| 传输 | 347–351 | 编码响应后 sendall；失败另记 unknown |
| worker 结束 | 365 | meter.flush 首次写 WIRE/INDEX 及 request/response 文件 |

`engineering/run_candidate.py:156–170` 的真实路径在 thin 成功退出、响应已取回、end_turn 完成之后调用 verify_business，worker 尚存活。因此此时 call 文件和事件已经可见，WIRE 尚未发布。旧 reader 的 FileNotFoundError 符合源码时序，不能由终态 fixture 中有 INDEX 推断在线可读。

## 独立离线证据

同目录 `review_phase.py` 仅 AST 提取候选 reader、旧 reader、真实 runner 的 verify_business；未调用完整作者评分器。对真实 FIX1 BASE 和既有历史 REPEAT/EDIT 提供显式可见文件集合，当前及历史 call 可读，WIRE、FINAL、WORKER_CLOSED、未来 call 均不提供。实际 runner 接线用独立 callback 核 capture、对象来源及返回 binding；这不是重新完成整套数值真值评分。

**26/26 检查通过**，明细及输入 SHA 分别在 `RESULTS.json`、`INPUT_SHA256.json`。

| 原件 | 当前 sequence | 本次 resources | 解析保留资源 | 来源 |
| --- | ---: | ---: | ---: | --- |
| FIX1 BASE | 2 | 24 | 24 | sequence 2 |
| 历史 base_brief | 3 | 0 | 24 | sequence 2 |
| 历史 edit_default | 7 | 0 | 24 | sequence 2 |

三者当前 pose、单位、local vertices、faces 重建后均等于其相应实际 source snapshot；未借未来 capture 的资源。在线阶段旧 reader 均在 INDEX 失败，候选均可读取。单独开放终态 WIRE 后，原 reader 按每轮 sequence 前缀解析，得到与候选相同的 delta、保留资源、origin、脚本绑定；只开放不晚于目标序号的 WIRE 文件也能完成。历史 repeat/EDIT 是旧实测原件回放，不是本 FIX1 已执行的新轮次。

CRLF helper 只在物理 bytes 与精确 CRLF→LF 两种去重候选中选择，脚本使用 SHA、输出使用原长度。独立核了正例、无匹配、不能 trim、不能将 lone CR 转 LF。**长度不是内容真实性证明**：同长度不同字节可能通过这个 helper，仍依赖后续事实/来源核验和最终传输记录；不能宣传成输出防篡改哈希。候选还先解析整个事件文件再筛选 sequence，后验/并发使用时会受未来不完整事件尾影响；当前逐轮串行 runner 在资格点没有未来 writer，不构成此次在线阻塞。既已选择后验方案，无需再优化或推广此候选。

## 后验方案为何更小

真实 runner 的 report 只写 c_reports、row.verification，后续控制不消费它。BASE/REPEAT source 来自已保存 INITIAL；EDIT source 来自 registered_pose.snapshot，并有 ADMIN 回执。各轮请求、响应、trace 时间区间和结束状态都可在关闭前保存。关闭后 WIRE reader 本来就支持逐序号历史资源解析；无需新增文件协议、CRLF 重建或并列评分器。

在线仍保留成功返回、thin 退出、backend/session/endpoint、原 deadline、登记 EDIT 与回读、每轮 EOF 等执行条件。失败立即按原真实状态停止；后验只延后不参与执行控制的几何/事实/kernel/sequence 资格。

FIX2 的关键落点：

1. finish 只调用一次且必须确认，随后才评分；finish 失败、WIRE 缺失/不完整或原 deadline 耗尽不能通过。
2. **保留每轮实际业务 started_ns/ended_ns。** 当前异常分支第175行会重写 ended_ns；不能将其挪用到后验资格异常，否则时界会包住后续轮/最终 QA，破坏 request-local host 筛选。另记资格时界与异常。
3. 逐轮区分执行返回、资格通过、资格失败、未资格。原第195–199行仅用 row.errors 和业务数量计算完成，会漏掉关闭后未评分轮次；未评分不得算 complete。序列核验也须明确完成后才可总体通过。
4. 用一个阶段集成测试约束同一 runner：fake finish 之前 WIRE 不可见、之后才开放；验证三轮收集先于资格，失败路径不误计完成。无需再建另一套 reader 测试平台。

原 FIX1 C 保持 **planned 3 / attempted 1 / completed 0 / failed 1 / not_run 2**。本复核未修改这份记录，未启动补跑。待最小 runner 调序及分母修复冻结后，按根计划执行唯一新 C；N、actor、consumer、产品若字节不变，无需重跑其已通过矩阵。
