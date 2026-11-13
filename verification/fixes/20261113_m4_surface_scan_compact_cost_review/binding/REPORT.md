# 九格成本解封：独立来源与生命周期复核

结论：**通过，没有发现应改变既有质量结论的来源错配或关闭阻塞。** 本轮针对固定 `e089a7ba`，独立离线脚本完成 **3,067 项检查，0 项失败，记录 1,194 个输入路径的原字节摘要**。检查数不是消费者分母；消费者仍为原九格，本轮新增 Blender、产品、模型和 API 实验均为零。

## 版本与审核阶段

本次只核新增 cost 的 26 个内容文件及 manifest 自身，共 27 个 Git 变更；原 `f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907` 至当前提交没有其他路径变化。cost 清单成员、集合、原字节 SHA256 与 Git blob 一致。作者工作树检查前后干净，HEAD 不变。

原 2,335 文件的全量 Git 盲算复用上一轮独立包审，不再重跑该矩阵。核对原 manifest 与上一审 INPUT_HASHES 一致；本轮实际解读的每份 ZIP 原件仍独立核字节、provenance 与当前固定 Git。

根质量 seal SHA256 `c054d8b5ea8ef672a9b3558c9fd33d485e87593fc53c87df6f2ec0ba6a82d9eb`，与根磁盘、管理员提交 `1f1a23dda3413721d6c71bd1db95f3a40a7c4977` 及交付副本逐字一致。r2 ZIP 与最终 42 文件 canonical 不变，行政 redaction 回执与上一轮独立输入摘要一致；原两字段修正不重做、不扩写。

## 私有运行到封存答案

| 真实格 | seal 匿名 ID | 执行状态 | 本轮实际绑定 |
| --- | --- | --- | --- |
| N1 | answer_89dab9e90194dcbf | completed | 通过 |
| O1 | answer_4a4a77418ce1424c | completed | 通过 |
| C1 | answer_9297e204cfb1d7f7 | completed | 通过 |
| O2 | answer_4c4c0fa03baa1ee8 | failed | 通过，错误保留 |
| C2 | answer_dccb27e1bc47c94f | completed | 通过 |
| N2 | answer_3990a6a4bf660eee | failed | 通过，错误保留 |
| C3 | answer_9ee63c86af8ff66d | completed | 通过 |
| N3 | answer_bb2c246d257d7867 | completed | 通过 |
| O3 | answer_11a4c8ec025d6a16 | completed | 通过 |

预建 MAP 原件、handoff MAP 与 PLAN 摘要一致。九份原始 ZIP 共 **807 个成员**，集合及每个成员分别与对应磁盘原件、私有 provenance 摘要和固定 Git 字节对应。没有采用作者 checker 的通过数，本轮也未执行作者核验器。

九个 `consumer.final`、最后 `agent_message`、CLI final 文件、PUBLIC_FINAL、匿名 answer、匿名 CLI 文本及根 seal 摘要逐字相同。两格原始 error 事件与消费者记录、公开 INDEX、seal 对应，N2/O2 的 valid_completion 继续 false；正常 turn 完成、CLI exit0 和 final 存在没有覆盖执行失败。

27 次业务请求逐项绑定 owner REQUEST/RESPONSE/ATTEMPT、公开投影、真实线程元数据与实际开始/结束事件。54 条公开工具事件逐一匹配原事件内容、原行 SHA256、完整 events 文件摘要。CLI 工具结果的 content 与 RPC content 完全一致；CLI 使用 `structured_content` 与单独 error 状态，RPC 使用 `structuredContent`／`isError`，按实际两端格式核查而不假定外层包装相同。

公开 source_consistency 的六类来源记录摘要已反绑到真实文件；ACTOR_CONFIG、owner IDENTITY、CLOSE 中保留字段逐项对应，初末快照摘要和引用一致。

## 来源、真实入口和几何

- O 为旧扫描 OPT1 `c1cb2da3`／`c4832b1a…1943`；C 为紧凑候选 `452b44d2`／`4067c864…a9f6`，未误用主干或其他旧版本。
- 两份安装各 138 源重新算源聚合并逐文件比对，入口和 binding 摘要与 PLAN/READY 一致；PLAN 的 external bindings 也核当前字节。既有 wheel 构建矩阵按同源记录复用，没有重新安装或运行 identity。
- 六个实际产品 initialize、配置 pin、启动入口、audit build/PID、工具说明与冻结 schema 对应。每格消费者真正收到的 tools/list 与该组冻结 schema 相同，共同原生工具 schema 一致。
- 每个产品格实际发往 Blender 的首个扫描代码内六份压缩源独立解码，与该格安装源摘要一致。首 scan 的 measurement cache entries 为零、kernel 为 112；本结论不等于操作系统或 provider 冷缓存。
- 九个实际 CLI thread、九个 Blender PID、九个 owner PID、九个消费者 PID 均各自独立，六个产品 runtime PID 独立。CLI 实际 argv 的隔离开关、禁用 hooks/shell、请求模型和 effort 及 Pro 接点一致；这证明请求配置，不证明 provider 最终解析的型号与 effort。
- **18 份几何快照**按 `unit_scale_m`、对象名、全部本地点／面／世界矩阵与冻结 BASE 对应；snapshot receipt、worker stdout 与记录脚本 hash 相符。它们是完整几何数组投影，不能据此声称核过 BASE 的全部附加元数据。独占 input.blend 与原 BASE 字节一致。

## 关闭和 570 秒原期限

每格实际 owner launcher 与 owner runtime 的父子 PID、owned worker 和消费者各自对上；产品格另核 launcher/runtime 的父链与创建时间。新的消费者记录明确 `before_stdin=false`：初始 QA 完成、四次 metadata 交互、runtime 归属证明、首业务依次发生。本轮没有沿用早期工程批的错误 before_stdin 标签。

每格原期限均为 cell 起点加 **570,000,000,000 ns**，与 actor/launch/native/worker 回执一致。完整终点晚于消费者清理与 owned 清理，并覆盖最终业务记录关闭；九格均在原期限内，下一格起点晚于前格计时回执发布结束。

消费者进程/reader、owner launcher、Blender Popen、适用产品 launcher 与 retained runtime handle 分别有关闭或退出码 0 记录。九份 thin-client EXIT 仍缺失，全部 `unknown` 保留；它们不冒充已确认关闭，也不替代后端独立关闭证据。几何初末指纹、资产摘要与 source_file/protected_file 记录保持原范围。

本轮没有重演过去进程内存，不能排除所有已撤销瞬时操作；没有确认 fsync 级持久化。source_consistency、计时发布与通用关闭 event 各自原范围继续保留。

## 使用结论与本轮修正

质量 seal 的内容正确口径与执行有效口径均可绑定到相同九格原件，允许根继续独立成本/机制分析。不能将九份最终内容正确改成九份有效完成；两份 execution_failure 继续进入原成本分母。完整墙钟、reported usage、provider 请求总数和真实费用的解释交由根的成本核查，不由本轮来源核验外推。

首次探索误猜 MAP 路径，收到 FileNotFoundError 后改用实际目录索引。首版核验器误把 `owner/TOOLS.json` 的尝试账本当 tools/list schema，并直接比较 CLI/RPC 两种包装，产生失败；已保留 `ATTEMPT_01.json`，按真实原件合同修正，原件未改。之后补充原行 hash、source_consistency 反绑及实际嵌入源核查均通过。详见 `SELF_ISSUES.json`。本轮没有遇到 exec `-1073741502`，未进行失败进程重试。

AL 自身旧 assignment 仍 current=false，没有借根句柄或改父任务；此范围依据根 task75ca5929 的直接委派。产物仅写本复核 binding 目录，包括脚本、RESULTS、CHECKS、INPUTS、失败记录和产物 manifest。
