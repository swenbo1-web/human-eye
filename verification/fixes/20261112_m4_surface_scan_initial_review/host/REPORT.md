# 全场扫描初版：公开入口与宿主独立复核

2026-11-12。父任务 `73781a86-c536-4ae9-9154-28e95023c0b5` / revision 1 / write_version 605；自身 assignment `8466f8a6-352d-4c86-8e8e-9aed70a6f37a`，已用自身 Hook 句柄核对 `parent_read_only`。

结论：普通入口、两条宿主命令、完整目录与候选 union、空结果和未完成交付的接线可从固定源码核对。未发现当前已交付正常场景会错误宣称 complete 的新缺陷。作者披露的两类边界确实存在，并由本轮独立条件探针进一步确认：传输等待可能超过父期限；隐藏源的部分异常会失去已有 fallback 或未知界处理。这些仍需记为未关闭的能力/失败时延限制，不能把正常请求通过扩大为故障路径全部通过。

建议继续已定位的 pair 依赖缓存优化，保留上述边界和后续定向修复项。它们不构成继续正常隔离性能工作的阻塞，也没有证据支持因此增加一层通用防御框架。

## 范围与证据

实施树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`，证据提交 `726e88efba548e85eba1eb148b91486470c5d2c1`，产品固定 `c6355a01a4c6ee204a0d676cd9309f02428fe3ba`。读取根计划、产品相对 `e836e03f4b3821f869c72ac3e50df5204f28b50f` 的相关 diff、11 个产品文件的具体函数、公开入口/宿主测试代码和作者报告。16 个直接采用文件的字节与对应 Git blob 核对一致，清单在 `SOURCES.json`。这不是对所有 138 源的完整语义审查。

独立执行 `probe_boundaries.py`：载入固定 host 源字节，另外提取 MCP/Process **未修改的方法体**，以自写 API doubles 和假时钟探查分支。8 个案例结果在 `PROBES.json`。没有读取/修改实时 Blender、启动产品进程、发送网络请求、运行消费者或付费 API。没有直接执行作者测试或审计脚本，也没有重做作者 15 次工程调用。

第一次独立 harness 漏提供标准库 math 导致 NameError，记录于 `PROBE_HISTORY.json`；补足 harness 后全部重跑通过。这是复核工具错误，不计作产品失败，也不抹掉原记录。

## 入口和覆盖接线

| 边界 | 固定源码发现 | 本次判断 |
| --- | --- | --- |
| query/schema | `query_policy.py` 转交 `validate_surface_scan_query`；只接受 mode/threshold，有限非负数，bool/NaN/Inf/额外字段拒绝；schema 的非 scan 分支恢复旧阈值约束 | 新查询没有顺带扩大旧结构入口的阈值合同 |
| 普通 MCP | `live_spatial_mcp.py:874` 为 scan 默认文字，验证器拒绝对象选择与图片；返回直接事实；complete/partial/unknown 分别保留，发布前检查原请求预算 | 无需新工具或模型拼接 requested_facts；unknown 未伪装为完成 |
| service | `live_service.py:1380` 用原预算剩余量构造 host 期限；每次捕获后先 `_packet` 验全目录与分区，再进入结果缓存；selection 含 query、完整 binding、scope issues | 缓存命中也不跳过当前目录身份与全 pair 约束 |
| mesh 全目录 | `blender_host.py:780` 的专属 scan 分支含 scene 中全部 mesh，包括隐藏；0..256 合法；object_names 若指定须覆盖全集 | 空场景不是虚构焦点；旧入口仍走原 1..256 合同 |
| 实例与范围 | `_sync_residency` 对 scan 加入 instancer flags、graph 实例存在性；scope issues 在 warm cache 命中前重新核；目录/范围又写入 capture revision | 端点 union 不变也会使旧完整结果失效；无静默实例省略后 complete 的路径 |
| 宽筛与 union | 未知包围界下界为0，严格 `lower > threshold` 才排除；来源不支持的 pair 进入 unknown_source；源资格后再次更新分区；每个保留端点只进入一次 `_capture` | 排序不是 Top-K；非候选 source 不因距离远就免除来源资格 |
| empty union | scan 专属 `_validated_scene` 允许0 meshes，host 的目录 identity 与 union identity 分开；reducer 仍验证所有 pair | 0对象、1对象、全排除可以返回空集合而保持准确分母 |
| 状态与交付 | reducer 保持完整 pair 守恒；scope issue→unknown，unknown/deferred→partial；超过 reducer 字节预算则截断匹配列表并公开 incomplete delivery，外层仍有传输限制 | 完成判断和交付完整性被分别保留，没有把 Top-K 截断叫找全 |
| 续查 | `ReadContext.result(... cache_partial=False)`；scan progress 保留已测总结，阈值/selection 切换清当前进度及相应完整结果；未知 pair 可重试，cap 拦住的新计算计 deferred | 不是把一次 partial 永久当终局。缓存命中与新计算的预算分工可核 |

扫描 reducer 的判定使用 `_exact_distance_sq` 与 binary64 阈值平方，未用展示距离舍入值。当前表面谓词不包含实体穿入/包含；结果 `solid_relation=not_evaluated`，没有从包含控制的 surface nonmatch 推出无碰撞。

host 冷态仍检查全部静态源的坐标、拓扑和非退化性，`_scan_local_summary` 与 `_scan_world_precision` 的有理摘要用于避免仅对被选对象做资格。不能把该获取成本宣传成只读取候选，或者纯 O(N) 元数据扫描。服务侧 M3 只对保留 pair 精测，昂贵求解不在 Blender 主线程。

`scene_residency` 的资源 stamp 是已有几何 incarnation/dirty/guard 依赖，源资格只保留小摘要，没有第二份常驻几何数组。普通 capture、nearest 不传 prepared local 时沿旧路径执行；新 scan 的静态原始隐藏 fallback 没有扩大普通 capture 的来源许可。

## 已确认的期限限制

位置：`blender_mcp_host.py:315,574,697`，`blender_process.py:340,617,635`。

- MCP 的 scan 入口把父绝对期限传给宿主，并在返回后拒绝迟到结果。但 `_request` 的 `_exchange(payload)` 不接收该期限，后者仍以 `time.monotonic()+self.timeout_s` 建传输期限。独立 AST 核对 `_exchange` 与 e836 基线完全相同。
- Process scan 入口把剩余时间作为 `_capture_request(timeout=...)` 参数。`_request` 只对 apply/forward_deadline 创建 `stop_ns`，scan 走同步 stdin write/flush，再使用原相对 timeout 等队列；编码与写入耗时没有从该等待时间扣除。

独立假时钟案例：父期限100ms、连接器 timeout30s，MCP 实际传给 `_connect` 的仍是30s。另一个 Process 案例让 write/flush 合计消耗500ms，此后队列仍获100ms等待 allowance，外层在模拟600ms时才拒绝迟到成功。两条路径的迟到成功拒绝均实际跑过。**这不是在真实 socket/pipe 上实测600ms延迟**，它证明相应方法的预算传递语义，实际阻塞延迟上限仍未验。

影响是失败返回时延、取消响应以及硬端到端期限声明；没有观察到过期测量被发布为成功或重复写入。继承旧 wait 实现并不表示缺口已修复，新扫描也不能宣称严格等待期限全部通过。

最小后续修复可复用既有 transport stop：MCP 给连接/发送/读取共用父期限剩余量，Process 将 scan 同样纳入绝对 stop 的 writer 和 queue 等待。独立测 delayed connect/send/read、blocked pipe、正常成功和清理耗时。没有必要增加策略服务；此处不改候选，也不代根决定抢占缓存优化。

## 隐藏来源异常的准确影响

位置：`blender_host.py:1344–1378`，目录 catch 位于1663行。

独立 API double 的五组结果：

| 输入条件 | helper 实际结果 | scan 上层含义 |
| --- | --- | --- |
| 静态隐藏，evaluated_get 返回非 evaluated 对象，正常bbox | `static_original_hidden`，有效界 | 正常支持路径 |
| 同样隐藏原始 fallback，但 raw bbox getter 抛 RuntimeError | helper 抛 RuntimeError | 目录 catch 后该源 unsupported，相关pair未知 |
| 已 evaluated 对象 bbox getter 抛同一 RuntimeError | 仍支持，bounds=None | 保留候选继续精查 |
| evaluated_get 抛 RuntimeError | 在 hidden fallback 前传播 | 目录 catch 后源 unsupported，没有尝试已有静态原始 fallback |
| evaluated_get 抛 ReferenceError | helper 传播，目录 catch 不含该类型 | 请求失败，不是完整结果 |

这些是明确分支行为，未证明固定 Blender 资产实际触发相同 getter 错误。第二行与第三行对“有效几何但包围界不可用”的处理不一致，属于保守覆盖损失。没有发现这两类异常产生 false complete。

最小改法是让静态隐藏 adapter 与 evaluated 路径共享受控 bbox 读取，getter不可用时保留源并用未知界。评价失败是否允许原始 fallback，应限已确认当前、独立静态且隐藏的来源；ReferenceError 可能代表对象失效，不应无条件回退成有效来源。该改动须独立验证完整来源和 pair 未知语义。

## 本次没证明的事项与下一步

189项作者定向回归、15次实际宿主运行和旧g06基线失败不由本子审重新执行认证；它们属于根质量/来源审核范围。本文没有把正常API doubles等同实际Blender，也没有新增性能样本、模型收益或实际故障注入。共享 GUI、默认安装和原作者资产未触碰。

从本子审证据看，可继续针对局部变化引起的无关 pair 重算做一轮实质优化，保持现有全目录验证/覆盖和必要来源依赖。缓存优化不应依赖对象名或仅用全场token之外的一两个弱字段；实际依赖设计由成本/cache分项审核。期限和隐藏异常仍作为明确未关闭项，不塞进“初版全过”口径，也不为这两项在本批同时扩建通用架构。

复核产物：`probe_boundaries.py`、`PROBES.json`、`PROBE_HISTORY.json`、`SOURCES.json`。所有写入仅位于本根复核 host 子目录。
