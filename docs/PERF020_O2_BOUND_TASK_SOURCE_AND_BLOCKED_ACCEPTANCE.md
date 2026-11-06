# PERF-020-O2 绑定身份检查与正式验收阻塞

## 判定

D 已实现只读任务全局模块审计的删除。C/D 各六次真实入口资格通过，D 每次任务的全局扫描、模块遍历及其来源路径解析均为零，每次仍重新采集场景并返回正确的五类事实。开发源码和固定安装分别通过 38 项受影响机制测试及 54 项传输与未知回执回归。

唯一正式 A/D 序列完成 10 次运行、100 次观察后，在第 11 次运行启动时打开 `SERVICE_READY.json` 遇到 PermissionError。该运行尚未 initialize 或 capture，另外 19 次运行未执行，共 200 次观察未尝试。原评分器调用一次，返回序列不完整，分类结果为空。D 的整版性能准入仍待完整证据。

本批以 `PERF020_O2_BLOCKED` 回传主复核。提交 `e43f0875cb486598cfd787dd9df65ae657c1fb80` 已恢复 A 工作源码，D 提交、wheel、私有安装及所有失败原件保留。后续需要主复核明确 READY 访问恢复语义和新的前瞻验收批次。

## 固定版本

| 项目 | 值 |
| --- | --- |
| 分支 | `codex/perf010-direct-task-query` |
| 初始控制 HEAD | `5bf3e032fd46a1a7468cb6999803cca90e7cc285` |
| 正式基线 A | `616cbfb719ae2cbeb43247a57d79447227eaddeb` |
| A 的 130 源文件摘要 | `41dc307f8ab37d5ce910ef92660d9e7061a1e8c7e3ce7a2c70316ca864e9172e` |
| 算法基础 C | `a130d392b8c3a926d4f321d1f911a10e5f012a3e` |
| C 的源摘要 | `8fca8d80d1214f46ce9be74ff3423307bc6fab541703a1d039a5d23b558e7962` |
| 唯一候选 D 及正式控制 HEAD | `a3c35733f1c3226c1a3b4446b89f48d0477b4592` |
| D 的 130 源文件摘要 | `4dd14da7884ae0b13de2ab6b654121cfb3e4178aac1af7a67267a42281e9ca0c` |
| D wheel SHA256 | `17d7895e09e882500fe172f53550fc02b771072b8191e15bdd64b3d2d5f84ab0` |
| D ENTRY 记录 SHA256 | `c0a9d7c924a5162447bbb9c278fa78219cfbcf4d4b1cc68442b84b6edf45af45` |
| 正式 FREEZE SHA256 | `297050cb7b54911833f76a8e9ace76b81a2830d004cdc139cc2ac5c8066bec86` |
| 正式 SUMMARY SHA256 | `fe3a433dc37dc8455131cbdc133ae5f223fe0784f7a934544c1f88b72452c7e0` |
| 原评分器 SHA256 | `38be06a5e82532f6691bb543389ad5324ccddb2c453ff10fdf93c11bb733ee79` |

D 从本端历史恢复 C 的接收器及对应测试，在 C 上只修改 `runtime_identity.py`、`live_service.py`，包括版本身份更新。Git、130 源文件、137 个 wheel 成员、RECORD、安装及实际入口身份经批内独立核对。接收器、Blender host 和 verified loader 保持 C 的对应字节。此前未准入的批量 RNA 改动未进入 D。

## 删除的工作和明确的职责变化

`check_task_source()` 删除了逐请求调用全局 `verify_loaded()` 的两行逻辑。已有 guard、冻结 sources、loader、runtime module 和 verify 函数对象的固定身份比较继续执行。只读检查结果保留 `status='loaded_generation'`、`compatible`、`check_complete` 和 `disk_status='disk_not_checked'`，增加 `source_check_scope='bound_generation_identity'`。公开 task binding 保留 `source_status`、`disk_status`，并转发同一个 scope。

`check_complete` 表示该绑定身份检查已完成。只读任务对任意外部 alias、`sys.modules` 或 junction 改动的即时检出保证在本候选中收窄。完整来源诊断、启动及写路径继续执行原有审计，实际 lazy、alias 和 worker 执行继续使用原有冻结字节校验。普通 SDK fallback 继续进行磁盘比较。

此次删除全进程模块遍历及来源路径解析。130 源逐请求读取和重哈希此前已经移出该入口。现存每观察 host 来源读取/哈希、首次 lazy 读取、场景采集与数值计算分别保留。

## 真实 C/D 资格

每版在 8、64 对象两档各启动一个固定受控入口进程，首次读一次、warm 两次，使用真实 BlenderMCPHost，共 12 次有效观察。查询、场景和三次只读序列相同，五类事实、完整点面数量及来源均通过，产品 setter 和 QA 位姿控制均为零。

| 每次任务的实际工作 | C 首次 | C warm | D 六次 |
| --- | ---: | ---: | ---: |
| `check_task_source` | 1 | 1 | 每次 1 |
| 全局 `verify_loaded` | 1 | 1 | 每次 0 |
| 模块循环位置 | 369 | 373 | 每次 0 |
| 来源解析 | 322 | 326 | 每次 0 |
| 原生 final-path 解析 | 322 | 326 | 每次 0 |
| 全局审计下的源内容读/哈希 | 0/0 | 0/0 | 每次 0/0 |

startup 和 EOF 的全局审计仍有正计数，每个 D task 都观测到实际身份函数，因此零扫描具有正向可观测依据。首次真实 lazy 执行在每个进程读取 `goal_execution.py` 一次，warm 无该读取。资格插桩没有替换已绑定函数。

资格 `check_task_source` 插桩累计墙钟，C 约为 130.8723–142.2999 ms，D 约为 0.0259–0.0314 ms。两者包含 profile/trace 的显著额外工作，嵌套项不能相加，可省的未插桩耗时尚待完整正式验收。本批未采用历史 44–56 ms 作为当前收益。

同一资格任务的解码后公开文本从 C 的 1,936 增至 D 的 1,985 个 UTF-8 字节，增加 49 字节，用于准确标注 scope。此数值对应当前固定查询。

## 作者执行与独立核对

| 内容 | 作者执行 | 批内独立核对 |
| --- | --- | --- |
| 受影响机制 | 开发和固定安装各 38/38，29 项 task 方法加九项既有加载/worker/来源子集 | 审阅测试职责、全部断言、源快照、安装来源和结果 |
| C 接收及未知回执 | 开发和固定安装各 54/54 | 审阅继承方法、结果及 C 字节一致性 |
| 实际资格 | C 六次、D 六次 | 从原始输入/输出、worker、host、绑定、进程及 profile 独立审核 |
| D 包体 | 一次构建、隔离安装和实际 identity CLI | 独立重算 130 源、137 成员和 RECORD，核对入口及安装 |
| 正式序列 | 一次启动，100/300 观察完成 | 独立审核保留的 100 次事实、scope、来源、资源及中断 |

旧测试按新职责明确调整，外部注入 alias 和异常 namespace 由显式完整检查拒绝。固定对象替换、SDK fallback、同大小同 mtime 的首次 lazy 修改、真实 alias 再执行、worker 和无害 pyc 行为保留。作者与独立分母分别记录。

## 正式中断与恢复边界

预注册采用原 8/64/256 场景、查询、五组 AB/BA/AB/BA/AB 顺序、每运行首次一项/静态三项/姿态三项/几何三项。原 10 秒 TCP、64 MiB、60 秒启动期限及 12 类性能门限保持冻结。

第 11 次为 `block01-tier256-B`，B 槽绑定 D。失败发生于 QA `wait_for_json()` 的 `Path.open('rb')`，错误为 `completed_record_read_failed` 包装的 PermissionError。原失败读取没有字节，长度、SHA256 和前缀均为 null。旧诊断只存异常类型和文本，原生 winerror、原 errno 属性及锁持有者缺失，具体原因无法从当前证据恢复。

后续只读诊断成功读取 2,161 字节，SHA256 为 `a96eac97507dcc61185fa2f4ea6d62bdd94ed0cc6043865e66960ab93efb981c`。它证明后续时刻文件可读且绑定正确，失败时刻的字节状态仍未知。当前 ACL 和文件属性也仅属于后续诊断。

失败运行的 worker、控制器请求和 host 请求均为零，另 19 个注册运行未启动。原评分器返回 `series_complete=False`、`categories=[]`。12 类正式收益和总体尾部仍缺完整分母。C 的旧 8/12 失败保留，本轮零扫描机制资格与正式收益分开判定。

现有 QA 对已发布记录读取失败执行终止。允许打开阶段 PermissionError 在原期限内等待，是一种可研究的访问恢复语义，需要确定性见证和新的前瞻合同。当前没有执行该探针、修改 READY 助手或续接/重跑正式序列。主复核需要决定下一批的规则和新序列范围。

## 已发生的成本与回收

已完成 100 次 capture RPC、110 个 stdio 响应，五类事实均核验通过。产品 setter 为零，独立 QA 属性赋值为 90。下列为实际保留数据，传输层分别计量。

| 范围 | 字节 |
| --- | ---: |
| capture RPC 请求应用负载 | 340,300 |
| capture RPC 外层响应 | 317,571,610 |
| 有实际日志的 stdio 输入 | 51,280 |
| stdio 输出 | 244,360 |
| 解码后 task `content.text` UTF-8 | 196,050 |

RPC 数值排除 TCP/IP 头与独立 QA 控制通信。旧 `physical_rpc_bytes` 字段对应外层响应方向。stdio 包含 initialize，公开 task 文本排除 JSON framing。失败启动缺少 STDIN 日志，该项记为 unknown，实际 STDOUT 文件为零字节，汇总只计已观测日志。

`PARTIAL_METRICS.json` 保留逐调用完整 RTT、host capture 墙钟、每运行真实 service/launcher/Blender CPU、存活内存采样和完整受控生命周期。失败启动单列，受控生命周期 1.7657434 秒，实际服务 CPU 796.875 ms、Blender CPU 500 ms。当前成本清单用于说明已发生的工作，分类收益仍待正式完整分母。

11 次正式运行的 33 个进程实例均正常退出 0，reader、实际进程句柄及 Popen 句柄回收通过，无 forced cleanup 或清理错误。资格使用的独占进程另行回收，原四个背景进程保留。内存观测保留既有采样边界及 QA 首 payload 保留范围，退出后内存为 unknown。新增模型答案为零，token 与费用未测。

## 仪表及后处理修正记录

C 资格初次在 startup 阶段出现 profiler pending 断言，实际观察为零。原生回调见证及独立反例证明 `Path.read_bytes` 的 CPython call/return 可使用不同临时方法对象、相同 owner。计数器改为函数名称/module 加 owner 身份匹配，保留空栈断言，独立四项探针修复后全通过，随后才执行有效 C 六次。旧失败、脚本及修复见证均保留。

离线部分汇总先后错误要求失败启动拥有 STDIN 日志和成功行的 `host_requests` 字段，两次均在结果发布前停止。两版源码和错误另存 `postprocess_attempt01/02`。最终缺失日志明确记为 unknown，并从失败运行实际 `BLENDER_RESULT` 的空请求记录确认零 capture，失败进程成本仍单列。原始数据、正式助手和评分均保持冻结。

预先准备的完整 30 运行 metrics/bytes 汇总脚本因分母不足未执行。当前发布的是明确标注部分分母的独立汇总文件。

## 五项复核问题

| 问题 | 当前答案 |
| --- | --- |
| 哪些工作消失 | D 六次只读任务的全局模块扫描和其来源解析消失，固定对象身份比较继续执行 |
| 剩余最大成本 | 完整场景采集、host 来源检查、世界几何与拓扑、JSON、全量 RPC 及外部验证仍存在 |
| 更简单的替代 | 本候选已经直接删除全局审计，复用现有固定比较，未引入缓存或观察器 |
| 收益是否进入完整任务 | 机制已在真实受控入口确认，D 的完整正式收益因序列中断尚未验收，模型消费另待验证 |
| 下一批为何值得做 | 先明确 QA 启动访问恢复和新前瞻验收范围，使同一固定 D 获得完整分母，再依据结果选择下一项产品瓶颈 |

本批作为已实现、已资格验证但正式验收阻塞的候选收口。PERF-020 驻留/增量、共享 GUI/addon 生态与模型任务价值继续开放。

证据位于 `D:/hefe/verification/fixes/20261106_perf020_o2/`。主要入口为 [正式中断原件](D:/hefe/verification/fixes/20261106_perf020_o2/cost/formal_01/SUMMARY.json)、[原评分器结果](D:/hefe/verification/fixes/20261106_perf020_o2/FORMAL_SCORE.json)、[部分成本清单](D:/hefe/verification/fixes/20261106_perf020_o2/PARTIAL_METRICS.json)、[故障诊断](D:/hefe/verification/fixes/20261106_perf020_o2/environment/formal_stop_01/DIAGNOSTIC.json) 和 [批内独立复核](D:/hefe/verification/fixes/20261106_perf020_o2/review/REVIEW.md)。
