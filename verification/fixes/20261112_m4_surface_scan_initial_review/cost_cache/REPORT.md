# 全场扫描初版：独立成本复算与对象依赖缓存设计

2026-11-12。子任务 `/root/scan_initial_cost_cache_audit`，自身 Agent Learning assignment `be3f6118-135d-452e-a0c4-5f128b15eadc`，父任务 `73781a86-c536-4ae9-9154-28e95023c0b5`。仅离线读取固定原件和源码，自写标准库复算；没有导入或执行产品、作者汇总器/验收器，也没有新增 Blender、模型或 API 调用。

结论：作者初版的主要时延和工作量陈述成立。宿主已经复用资源，局部姿态变化的主要重复工作在服务端 pair 缓存。下一轮应只缩小表面测量缓存的依赖范围：本冻结序列可验证 **edit 114 次新核 → 10 次新核 + 104 次缓存命中**。这是工作量验收目标，时间收益仍须同版实测。

## 1. 独立范围与原件

固定证据提交 `726e88efba548e85eba1eb148b91486470c5d2c1`、产品 `c6355a01a4c6ee204a0d676cd9309f02428fe3ba`。本脚本实际读取 218 个唯一文件，逐文件核 SHA256、字节长度及该提交 Git blob，318 条断言通过。包含五序列全部 15 次客户端请求/响应、15 次 trace/observe、全部 35 次宿主 wire、worker 原始计数、Process 路径和相关源码；这些检查数不是独立任务样本。

本子审成本分母：一个场景、两个几何状态、五个独立进程序列、15 个普通 MCP 观察请求，以及一条另列的 Process directed 请求。几何真值和公开见证的专业裁决由根质量子审负责，本报告不以成本正确替代几何正确。

脚本初次将 socket 响应中的 stdout 与磁盘 stdout 按字符串逐字比较，因磁盘 CRLF 与 wire LF 差一个字节失败。检查现改为保留两份原始字节哈希、只在这条文本对应断言规范化行尾；实际 wire 长度仍直接取原始二进制。其他探索时误按 JSON 读取带 marker 的 stdout、一次 PowerShell glob 搜索失败均未改证据或触发产品调用。

## 2. 原始时间复算

client 时界由 `*_RESPONSE_RECEIPT.json` 的 ended−started 重算，再与 raw Peer receipt 对齐；raw TX/RX 解码与请求、响应、body 一致。trace 用 body.trace_id 对应 audit 中唯一 observe 与 request_trace，核 `stdio_write_completed` 和编码/写入 span 确实包含在 duration 内。

| 序列 | cold client ms | repeat client ms | edit client ms |
| --- | ---: | ---: | ---: |
| 1 | 1781.7637 | 42.5225 | 1751.3137 |
| 2 | 1767.1953 | 41.5522 | 1719.0451 |
| 3 | 1836.7161 | 41.4728 | 1772.2850 |
| 4 | 1776.4201 | 40.7539 | 1738.8051 |
| 5 | 1770.4603 | 40.4625 | 1733.4936 |
| 中位 | **1776.4201** | **41.4728** | **1738.8051** |

| 相关窗口中位 ms | cold | repeat | edit |
| --- | ---: | ---: | ---: |
| 完整服务器 trace | 1771.4607 | 39.1257 | 1733.5657 |
| host.capture | 121.2943 | 34.3489 | 54.5996 |
| observation.surface_scan | 1641.0901 | 0.9588 | 1677.2907 |
| scene.validate（嵌套） | 3.3926 | 0 | 3.3199 |
| surface_scan.validate_packet | 0.7945 | 0.7766 | 0.7765 |

这些是各窗口自己的中位数，父子 span 不相加。trace 的 audit writer 被明确排除；客户端窗口包含 Peer 的 TX/RX、RECEIPT/RPC 证据 I/O 和响应解析，包含收到响应后 Peer finally 的记录工作。外层 `*_RESPONSE_RECEIPT.json` 写盘、body 解析、请求前后内存采样以及后续质量核验不在此 client 窗口，包含在更大的序列窗口或准备中。

五完整序列分别 6.2069948、5.9649576、6.1523242、6.0961810、6.0043630 秒；其中三业务请求合计分别 3.5755999、3.5277926、3.6504739、3.5559791、3.5444164 秒。其余启动、QA 快照、登记修改、关闭、核验等成本不能消失，也不能再叠加到已含它们的序列窗口。

准备另列：隔离构建/安装外层 4.0393977 s；其内 build 1.6404661 s、install 1.8431836 s。oracle 原始 started/ended 差 79.7306699 s。owned Blender 启动外层中位 0.9150915 s（其内部 session startup 中位 0.8362910 s）；产品启动与 metadata 中位 0.8007167 s。两种 startup 边界不能混称同一数值。

另一个 Process directed 状态不并入五序列：仅 capabilities/capture_surface_scan/shutdown，原始 stdin 解出三命令；MCP observe trace 1.7232311 s，metadata+scan+close 窗口 1.8286209 s，Blender start+capabilities 0.874423 s，完整记录窗口 3.5079535 s。

## 3. 实际采集、计算和线缆

15 次请求各恰好一个宿主执行；五序列各 7 次物理宿主请求＝3 次扫描＋2 次 QA 导出＋1 次登记姿态修改＋1 次关闭，合计 35。实际错误、自动重试、渲染和新增 PNG 均为 0。五序列 product launcher、runtime handle、owned Blender 关闭回执相互核对，均有退出和回收证据；没有把旧任务的 thin EXIT 情况套到本批。

| 实际工作，每序列 | cold | repeat | edit |
| --- | ---: | ---: | ---: |
| 新驻留资源 | 24 | 0 | 0 |
| 资源坐标读取 | 530 | 0 | 0 |
| 资源三角面读取 | 978 | 0 | 0 |
| 宿主世界变换点数 | 530 | 0 | 8 |
| 来源资格缓存命中 | 0 | 0（整包命中） | 24 |
| 新几何核调用 | 112 | 0 | 114 |
| 规范化 | 1 | 0 | 1 |
| 包围界测试实际增量 | 276 | 0 | 276 |

从 worker 的 before/after 累计计数重算全部 residency_delta，与 host 原始 packet 和 observe 诊断三方一致；新资源数组又按 resource revision 比较。`expanded_vertices=530`、`expanded_faces=978` 是当前 union 逻辑体积，repeat/edit 仍显示该数，不能解释为每次重新采集这些元素。SceneDeltaDecoder 在普通 JSON 解码后仍会复制当前列表；“新资源读取/世界变换0”也不等于全链零几何内存拷贝。

| 实际业务 wire，TX+RX bytes | cold | repeat | edit |
| --- | ---: | ---: | ---: |
| MCP stdio（模型工具侧） | 37492 | 37496 | 37979 |
| 宿主连接 | 247339 | 98398 | 98377 |

宿主 wire 含一次受控代码/命令与返回包络；数值来自二进制文件长度并核 INDEX 的 sendall completed。每序列三次业务宿主 wire 合计 444114 B；所有宿主请求含 QA/关闭合计约 1.38649 MB。热态仍传约 98 KB，因为目录、pair 分区和元数据仍传，不可把零几何资源 delta 叫做零传输。每次仍核全目录和排除分区，但其 service 直接校验中位仅约 0.78 ms，当前优先级低于重复几何核。

读取到的内存为 GetProcessMemoryInfo 请求前/后工作集和进程生存期峰值。cold 后中位 Blender 216756224 B、runtime 63242240 B；repeat 后 216817664/63291392 B；edit 后 218198016/63520768 B。runtime 生存期峰值中位始终 94040064 B，已受启动影响。它们不是请求局部峰值，也不是精确缓存占用；本批没有独立 tracemalloc 分配峰值，不据此证明不存在临时放大。

## 4. 局部移动为何近似冷算

五序列的 wire 证据均显示：host instance 和 epoch 不变，capture revision 从 1 到 2；24 个 resource id/revision 全部不变，只有 `Obj_008` 的 matrix Z 平移变为 `-0.000750000006519258`。完整 object_instances 和 document epoch 不变。edit 的 114 个候选中，104 个不涉及 Obj_008，且这 104 个全都在 cold 的 112 个候选中已经计算过。

源码链：

1. `read_context.capture_key` 把 instance/epoch/revision/selection 都纳入；`activate` 的 generation 是前三者，revision 变动触发 `reset()`，清当前 progress/normalization/results。
2. reset 没有默认清除 `scene_cache._measurements`，但 `_bind_read_meshes` 把每个规范化 mesh 绑定到 `(整个 capture key, object_id)`。
3. `scene_cache._measurement_mesh` 使用该快键，`pair_measurement` 再组合双方快键、算法和参数。新 generation 的所有 mesh 快键都变了，因此旧 pair 记录虽仍在 LRU 中也无法命中。
4. host resource/pose delta 已经生效，瓶颈不是网格全部重采。`observation.surface_scan` 约 1.68 秒包含重复求解，远大于约 55 ms 的 host.capture。

edit 每序列总工作 716565 units、184 棵距离树；104 个无关 pair 占 679260 units、170 棵树、10222 个 narrow tests。单位来自实际计数复算，不是 CPU 指令，也没有每 pair 独立时段。不能按 104/114 或 units 比例估算完整时间降幅。

## 5. 下一轮最小实现建议

**只给扫描的 unsigned surface pair 缓存增加对象依赖快键，保留现有 2 MiB 有界 measurement store。** 当前进度和 complete 结果仍绑定当前全目录，重新宽筛与覆盖；跨 revision 只复用已证明相同几何输入的测量。这样无需另建扫描数据库或改变完整性流程。

`SceneDeltaDecoder._apply` 已核 resource revision 并用 `(resource id, revision, matrix, scale)` 缓存世界坐标，但随后 `mesh.pop('_scene_resource')`，服务端丢失了便宜依赖来源。最小接线是 decoder 成功提交后保留**当前返回 capture 的私有 sidecar**，经宿主适配器交给 ReadContext；直接宿主路径也可从本次 resident wire 绑定生成同语义 sidecar。它不接受 query/任意 scene JSON 的同名字段，不写入公共 mesh/schema，不用于动作授权。decoder 返回失败/非 delta、host 重连或 sidecar 与 capture 不匹配时，走现有完整内容或全 generation 路径，不猜版本。

每对象依赖应绑定：当前 host 实例、residency epoch、document epoch、object incarnation、resource id/revision、完整 matrix 和物理 scale，以及适用的 surface source 模式/算法域。物理矩阵数值采用 decoder 现有 `_world_number_key` 语义，保留有意义的 signed zero，不用短四舍五入字符串。source/单位/world frame、witness tolerance、exact-rank 选项和算法版本继续在 pair 参数中。资源 revision 由现有 dirty/geometry guards 更新，不能以同名、相同点面数或同矩阵代替。

仅扫描 opt-in：ReadContext 为当前规范化 mesh 对象建立受信 surface 绑定；surface 测量调用明确选择该 namespace，其他通用 pair、solid support 和动作缓存仍走原有 `_measurement_mesh`。可以给现有 measurement key 生成加一个私有 surface 选项，复用同一查找/记账/驱逐逻辑，避免复制一套 cache。不要直接把全局 `_measurement_mesh` 改成省略 axes/pivot/identity 的几何键，旧 solid 合同依赖不同。

pair 保持**有序**，先沿既有 lexical object_id 规范方向；若反向复用，必须同时交换两个见证并处理方向，否则直接反向键 miss。最小实现保持有序命中即可。labels/name/active 不影响几何测量，始终从本次目录生成公开名称；重命名若使 object_id 改变也不能仅按旧名字复用，可按稳定 incarnation 找依赖且仍保留有序方向。阈值不进入距离测量键，改变阈值重新做精确分类和候选/覆盖；只对已存的有效距离复用，不能沿用旧阈值的排除判断。

删除对象、实例替换、geometry dirty、pose/scale、document/undo/load epoch、来源资格变化都须更新当前范围并使相应关系失效。未变的远端 pair 可以复用；未知或异常测量不缓存成已知。支持域资格仍按新 packet 核查，不能因为旧键命中而跳过当前 unsupported 状态。checkpoint 保持每 pair；命中不扣 new-kernel 工作上限。

## 6. 可执行验收与停止

固定 c635 初版与一个优化候选，输入、276 对真值、2 mm、状态序列和计量边界不变。建议五组 old/new 配对独立进程，交错顺序；主业务均 cold/repeat/edit。已有初版原件保留，用同窗旧版对照控制环境漂移，不把历史最佳值拼进候选。

机制门：cold 112 新核；repeat 0；edit **10 新核、104 surface-cache hits**，无关 pair 新核 0，全部分区/距离/见证与初版及独立真值一致。宿主 RPC 仍每请求1，edit资源读取0、变换8点；新增绑定元数据若增加 wire/内存须实测列出。已测104个有效测量的复用记录应能逐对映射到前态。

工程反例至少覆盖：同名替换、相同点面数的几何变更、单对象姿态与单位缩放、删除/撤销/新document epoch、缺失/失效sidecar、阈值 A/B/A、name/active变化、pair交换后的见证方向、未知后恢复、低cap续查和既有普通task/solid cache回归。现有测试可复用，不借这一轮扩传输、图像或实体算法。

建议在候选运行前登记接受标准：质量和上述工作量门全过；edit完整client配对中位至少改善30%；cold配对中位不回退超过5%，repeat不回退超过 `max(2 ms, 初版5%)`；三个请求合计中位也改善，不能把成本移到准备。这里的百分比是供根决定的验收建议，不是已取得的收益或重新授权。同步报告实际工作集/峰值和measurement store计量，保留2MiB有界store，不用无限缓存换命中。

一次实质优化候选交根复审。未达工作量门先定位原因；工作量达标而时间未达时记录剩余成本，保留更优实现，不追加新场景或修改阈值刷过。完整模型/N-P收益仍在工程复审后单独开展，本批纯工程不能宣称已经赢原生消费者。

材料：[RESULTS.json](D:/hefe/verification/fixes/20261112_m4_surface_scan_initial_review/cost_cache/RESULTS.json)、[原件哈希](D:/hefe/verification/fixes/20261112_m4_surface_scan_initial_review/cost_cache/SOURCES.json)、[独立脚本](D:/hefe/verification/fixes/20261112_m4_surface_scan_initial_review/cost_cache/recompute.py)。
